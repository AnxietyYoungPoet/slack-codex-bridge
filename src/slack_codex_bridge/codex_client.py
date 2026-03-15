from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

IMAGE_REPLY_INSTRUCTION = (
    "When you want the Slack bridge to attach a local image, include a marker in your final reply "
    "using this exact format: [[image:/absolute/path/to/file.png]]. "
    "Use absolute paths only. You may include multiple image markers on separate lines. "
    "Do not use image markers unless you intend the bridge to upload those files.\n\n"
)


@dataclass(slots=True)
class CodexResult:
    codex_thread_id: str
    final_text: str
    raw_events: list[dict]


def _parse_json_events(stdout: str) -> CodexResult:
    events: list[dict] = []
    codex_thread_id = ""
    final_text = ""

    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            # Ignore malformed lines so incidental CLI noise does not abort the whole run.
            continue
        events.append(payload)
        if payload.get("type") == "thread.started":
            codex_thread_id = payload.get("thread_id", codex_thread_id)
        elif payload.get("type") == "item.completed":
            item = payload.get("item", {})
            if item.get("type") == "agent_message":
                final_text = item.get("text", final_text)
        elif payload.get("type") == "error":
            raise RuntimeError(payload.get("message", "Codex returned an error"))

    if not codex_thread_id:
        raise RuntimeError("Codex did not emit a thread ID")
    if not final_text:
        raise RuntimeError("Codex did not emit a final agent message")

    return CodexResult(codex_thread_id=codex_thread_id, final_text=final_text, raw_events=events)


class CodexClient:
    def __init__(self, codex_bin: str, workspace_root: Path, extra_args: list[str]) -> None:
        self.codex_bin = codex_bin
        self.workspace_root = workspace_root
        self.extra_args = extra_args

    def run(self, prompt: str, session_id: str | None = None, workspace_root: Path | None = None) -> CodexResult:
        cwd = workspace_root or self.workspace_root
        if session_id:
            command = [
                self.codex_bin,
                "exec",
                "resume",
                "--skip-git-repo-check",
                session_id,
                "--json",
                prompt,
            ]
        else:
            prompt = IMAGE_REPLY_INSTRUCTION + prompt
            command = [
                self.codex_bin,
                "exec",
                "--skip-git-repo-check",
                "--json",
                *self.extra_args,
                prompt,
            ]

        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(stderr or f"Codex exited with code {completed.returncode}")

        return _parse_json_events(completed.stdout)
