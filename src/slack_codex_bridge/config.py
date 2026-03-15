from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(slots=True)
class Settings:
    slack_bot_token: str
    slack_app_token: str
    slack_signing_secret: str
    allowed_slack_user_ids: set[str]
    workspace_root: Path
    codex_bin: str
    codex_extra_args: list[str]
    session_idle_timeout_seconds: int
    max_output_chars: int
    runtime_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        missing = [
            key
            for key in (
                "SLACK_BOT_TOKEN",
                "SLACK_APP_TOKEN",
                "SLACK_SIGNING_SECRET",
                "ALLOWED_SLACK_USER_IDS",
                "WORKSPACE_ROOT",
            )
            if not os.environ.get(key)
        ]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        workspace_root = Path(os.environ["WORKSPACE_ROOT"]).expanduser().resolve()
        runtime_dir = Path(os.environ.get("RUNTIME_DIR", ".runtime")).expanduser()
        if not runtime_dir.is_absolute():
            runtime_dir = workspace_root / runtime_dir

        codex_extra_args = _split_csv(os.environ.get("CODEX_EXTRA_ARGS", "--full-auto"))

        return cls(
            slack_bot_token=os.environ["SLACK_BOT_TOKEN"],
            slack_app_token=os.environ["SLACK_APP_TOKEN"],
            slack_signing_secret=os.environ["SLACK_SIGNING_SECRET"],
            allowed_slack_user_ids=set(_split_csv(os.environ["ALLOWED_SLACK_USER_IDS"])),
            workspace_root=workspace_root,
            codex_bin=os.environ.get("CODEX_BIN", "codex"),
            codex_extra_args=codex_extra_args,
            session_idle_timeout_seconds=int(os.environ.get("SESSION_IDLE_TIMEOUT_SECONDS", "14400")),
            max_output_chars=int(os.environ.get("MAX_OUTPUT_CHARS", "6000")),
            runtime_dir=runtime_dir,
        )
