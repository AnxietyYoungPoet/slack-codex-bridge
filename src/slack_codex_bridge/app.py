from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from .attachments import parse_response_attachments, validate_image_path
from .audit import AuditLogger
from .codex_client import CodexClient
from .config import Settings, load_dotenv
from .instance_lock import InstanceLock, SingleInstanceError
from .risk import RiskDecision, classify_risk
from .session_store import SessionStore


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger("slack_codex_bridge")


@dataclass(slots=True)
class PendingApproval:
    channel_id: str
    thread_ts: str
    conversation_key: str
    user_id: str
    prompt: str
    reason: str


class SlackCodexBridge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit = AuditLogger(settings.runtime_dir / "audit.log")
        self.sessions = SessionStore(settings.runtime_dir / "sessions.json")
        self.codex = CodexClient(settings.codex_bin, settings.workspace_root, settings.codex_extra_args)
        self.pending_approvals: dict[str, PendingApproval] = {}
        self.thread_locks: dict[str, threading.Lock] = {}
        self.app = App(token=settings.slack_bot_token, signing_secret=settings.slack_signing_secret)
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.app.event("app_mention")(self._handle_message_event)
        self.app.event("message")(self._handle_message_event)
        self.app.action("confirm_high_risk")(self._handle_confirm)
        self.app.action("cancel_high_risk")(self._handle_cancel)

    def _lock_for(self, channel_id: str, thread_ts: str) -> threading.Lock:
        key = f"{channel_id}:{thread_ts}"
        lock = self.thread_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            self.thread_locks[key] = lock
        return lock

    @staticmethod
    def _conversation_key(channel_id: str, channel_type: str, thread_ts: str) -> str:
        return thread_ts

    def start(self) -> None:
        SocketModeHandler(self.app, self.settings.slack_app_token).start()

    def _handle_message_event(self, event: dict, say, client, logger, ack=None) -> None:
        if ack is not None:
            ack()
        LOGGER.info(
            "Received Slack event type=%s channel_type=%s user=%s subtype=%s text=%r",
            event.get("type"),
            event.get("channel_type"),
            event.get("user"),
            event.get("subtype"),
            event.get("text"),
        )
        subtype = event.get("subtype")
        if subtype in {"bot_message", "message_changed", "message_deleted"}:
            return

        channel_type = event.get("channel_type")
        if channel_type not in {"im", "group", "channel"}:
            return
        if event.get("type") == "message" and channel_type != "im":
            return

        user_id = event.get("user")
        if user_id not in self.settings.allowed_slack_user_ids:
            logger.info("Ignored message from unauthorized user %s", user_id)
            return

        text = self._normalize_text(event.get("text", ""))
        if not text:
            return

        channel_id = event["channel"]
        thread_ts = event.get("thread_ts") or event["ts"]
        conversation_key = self._conversation_key(channel_id, channel_type, thread_ts)

        if text.startswith("/"):
            self._handle_control_command(channel_id, thread_ts, conversation_key, text, say)
            return

        decision = classify_risk(text)
        self.audit.log(
            action="message_received",
            channel_id=channel_id,
            thread_ts=thread_ts,
            conversation_key=conversation_key,
            user_id=user_id,
            channel_type=channel_type,
            risk_level=decision.level,
            reason=decision.reason,
            prompt=text,
        )
        if decision.level == "high_risk":
            self._request_confirmation(channel_id, thread_ts, conversation_key, user_id, text, decision, client)
            return

        self._launch_codex_run(channel_id, thread_ts, conversation_key, user_id, text, client)

    def _handle_control_command(self, channel_id: str, thread_ts: str, conversation_key: str, text: str, say) -> None:
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        if command == "/status":
            record = self.sessions.get(channel_id, conversation_key)
            if record is None:
                say(
                    text=f"Workspace: `{self.settings.workspace_root}`\nMapped Codex session: `none`",
                    thread_ts=thread_ts,
                )
                return
            say(
                text=f"Workspace: `{record.workspace_root or self.settings.workspace_root}`\nMapped Codex session: `{record.codex_thread_id or 'none'}`",
                thread_ts=thread_ts,
            )
            return

        if command in {"/reset", "/stop"}:
            removed = self.sessions.delete(channel_id, conversation_key)
            response = "Cleared the Codex session mapping for this thread." if removed else "This thread had no mapped Codex session."
            say(text=response, thread_ts=thread_ts)
            return

        if command == "/new":
            record = self.sessions.get(channel_id, conversation_key)
            workspace_root = record.workspace_root if record else str(self.settings.workspace_root)
            self.sessions.upsert(channel_id, conversation_key, workspace_root, None)
            say(text="This thread will start a fresh Codex session on the next request.", thread_ts=thread_ts)
            return

        if command == "/workspace":
            if not argument:
                say(text="Usage: `/workspace /absolute/path/to/repo`", thread_ts=thread_ts)
                return
            candidate = Path(argument).expanduser()
            if not candidate.is_absolute():
                say(text="Workspace path must be an absolute path.", thread_ts=thread_ts)
                return
            if not candidate.exists() or not candidate.is_dir():
                say(text=f"Workspace does not exist or is not a directory: `{candidate}`", thread_ts=thread_ts)
                return
            resolved = str(candidate.resolve())
            self.sessions.set_workspace(channel_id, conversation_key, resolved)
            say(
                text=f"Workspace set to `{resolved}`. Current Codex session cleared; the next request will start a new session in that directory.",
                thread_ts=thread_ts,
            )
            return

        say(text=f"Unknown command: `{command}`", thread_ts=thread_ts)

    def _request_confirmation(self, channel_id: str, thread_ts: str, conversation_key: str, user_id: str, prompt: str, decision: RiskDecision, client) -> None:
        approval_id = str(uuid.uuid4())
        self.pending_approvals[approval_id] = PendingApproval(
            channel_id=channel_id,
            thread_ts=thread_ts,
            conversation_key=conversation_key,
            user_id=user_id,
            prompt=prompt,
            reason=decision.reason,
        )
        self.audit.log(action="approval_requested", channel_id=channel_id, thread_ts=thread_ts, conversation_key=conversation_key, user_id=user_id, reason=decision.reason, prompt=prompt)
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"High-risk request detected: {decision.reason}",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*High-risk request detected*\nReason: {decision.reason}\n\n```{prompt[:1500]}```",
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "action_id": "confirm_high_risk",
                            "text": {"type": "plain_text", "text": "Confirm"},
                            "style": "danger",
                            "value": approval_id,
                        },
                        {
                            "type": "button",
                            "action_id": "cancel_high_risk",
                            "text": {"type": "plain_text", "text": "Cancel"},
                            "value": approval_id,
                        },
                    ],
                },
            ],
        )

    def _handle_confirm(self, ack, body, client, logger) -> None:
        ack()
        approval_id = body["actions"][0]["value"]
        pending = self.pending_approvals.get(approval_id)
        if pending is None:
            return
        actor = body["user"]["id"]
        if actor != pending.user_id:
            client.chat_postMessage(
                channel=pending.channel_id,
                thread_ts=pending.thread_ts,
                text="Only the original requester can confirm this action.",
            )
            return
        self.pending_approvals.pop(approval_id, None)
        self.audit.log(action="approval_confirmed", channel_id=pending.channel_id, thread_ts=pending.thread_ts, user_id=actor, prompt=pending.prompt)
        self._launch_codex_run(pending.channel_id, pending.thread_ts, pending.conversation_key, actor, pending.prompt, client)

    def _handle_cancel(self, ack, body, client, logger) -> None:
        ack()
        approval_id = body["actions"][0]["value"]
        pending = self.pending_approvals.get(approval_id)
        if pending is None:
            return
        actor = body["user"]["id"]
        if actor != pending.user_id:
            client.chat_postMessage(
                channel=pending.channel_id,
                thread_ts=pending.thread_ts,
                text="Only the original requester can cancel this action.",
            )
            return
        self.pending_approvals.pop(approval_id, None)
        self.audit.log(action="approval_cancelled", channel_id=pending.channel_id, thread_ts=pending.thread_ts, user_id=body["user"]["id"], prompt=pending.prompt)
        client.chat_postMessage(
            channel=pending.channel_id,
            thread_ts=pending.thread_ts,
            text="Cancelled the pending high-risk request.",
        )

    def _launch_codex_run(self, channel_id: str, thread_ts: str, conversation_key: str, user_id: str, prompt: str, client) -> None:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Processing request with Codex...",
        )
        worker = threading.Thread(
            target=self._run_codex_and_reply,
            args=(channel_id, thread_ts, conversation_key, user_id, prompt, client),
            daemon=True,
        )
        worker.start()

    def _run_codex_and_reply(self, channel_id: str, thread_ts: str, conversation_key: str, user_id: str, prompt: str, client) -> None:
        lock = self._lock_for(channel_id, conversation_key)
        if not lock.acquire(blocking=False):
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="A Codex task is already running for this thread. Wait for it to finish or use `/reset`.",
            )
            return

        try:
            self.sessions.delete_stale(self.settings.session_idle_timeout_seconds)
            existing = self.sessions.get(channel_id, conversation_key)
            workspace_root = Path(existing.workspace_root).resolve() if existing and existing.workspace_root else self.settings.workspace_root
            self.audit.log(
                action="codex_started",
                channel_id=channel_id,
                thread_ts=thread_ts,
                conversation_key=conversation_key,
                user_id=user_id,
                existing_session_id=existing.codex_thread_id if existing else None,
                workspace_root=str(workspace_root),
                prompt=prompt,
            )
            result = self.codex.run(
                prompt=prompt,
                session_id=existing.codex_thread_id if existing else None,
                workspace_root=workspace_root,
            )
            self.sessions.upsert(channel_id, conversation_key, str(workspace_root), result.codex_thread_id)
            parsed = parse_response_attachments(result.final_text)
            reply_text = self._truncate(parsed.text) if parsed.text else "Completed."
            client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=reply_text)
            self._upload_response_images(
                client=client,
                channel_id=channel_id,
                thread_ts=thread_ts,
                image_paths=parsed.image_paths,
                workspace_root=workspace_root,
            )
            self.audit.log(
                action="codex_completed",
                channel_id=channel_id,
                thread_ts=thread_ts,
                conversation_key=conversation_key,
                user_id=user_id,
                workspace_root=str(workspace_root),
                codex_thread_id=result.codex_thread_id,
            )
        except Exception as exc:
            LOGGER.exception("Codex run failed")
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"Codex run failed: {exc}",
            )
            self.audit.log(
                action="codex_failed",
                channel_id=channel_id,
                thread_ts=thread_ts,
                conversation_key=conversation_key,
                user_id=user_id,
                workspace_root=str(workspace_root) if "workspace_root" in locals() else str(self.settings.workspace_root),
                error=str(exc),
            )
        finally:
            lock.release()

    def _upload_response_images(self, client, channel_id: str, thread_ts: str, image_paths: list[Path], workspace_root: Path) -> None:
        for image_path in image_paths:
            validation_error = validate_image_path(image_path, workspace_root)
            if validation_error is not None:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"Skipped image `{image_path}`: {validation_error}.",
                )
                self.audit.log(
                    action="image_skipped",
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    workspace_root=str(workspace_root),
                    image_path=str(image_path),
                    reason=validation_error,
                )
                continue

            client.files_upload_v2(
                channel=channel_id,
                thread_ts=thread_ts,
                file=str(image_path),
                filename=image_path.name,
                title=image_path.name,
            )
            self.audit.log(
                action="image_uploaded",
                channel_id=channel_id,
                thread_ts=thread_ts,
                workspace_root=str(workspace_root),
                image_path=str(image_path),
            )

    @staticmethod
    def _normalize_text(text: str) -> str:
        parts = []
        for token in text.split():
            if token.startswith("<@") and token.endswith(">"):
                continue
            parts.append(token)
        return " ".join(parts).strip()

    def _truncate(self, text: str) -> str:
        if len(text) <= self.settings.max_output_chars:
            return text
        return text[: self.settings.max_output_chars - 20] + "\n\n[truncated]"


def main() -> None:
    load_dotenv(Path.cwd() / ".env")
    settings = Settings.from_env()
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    instance_lock = InstanceLock(settings.runtime_dir / "bridge.lock")
    try:
        instance_lock.acquire()
    except SingleInstanceError as exc:
        raise SystemExit(str(exc))
    bridge = SlackCodexBridge(settings)
    bridge.start()


if __name__ == "__main__":
    main()
