from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class SessionRecord:
    slack_channel_id: str
    conversation_key: str
    workspace_root: str
    codex_thread_id: str | None
    created_at: float
    updated_at: float


class SessionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, SessionRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text())
        records: dict[str, SessionRecord] = {}
        migrated = False
        for key, value in raw.items():
            if "conversation_key" not in value and "slack_thread_ts" in value:
                value = {
                    **value,
                    "conversation_key": value["slack_thread_ts"],
                }
                value.pop("slack_thread_ts", None)
                migrated = True
            if "workspace_root" not in value:
                value = {
                    **value,
                    "workspace_root": "",
                }
                migrated = True
            records[key] = SessionRecord(**value)
        self._records = records
        if migrated:
            self._save()

    def _save(self) -> None:
        payload = {key: asdict(value) for key, value in self._records.items()}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    @staticmethod
    def _key(channel_id: str, conversation_key: str) -> str:
        return f"{channel_id}:{conversation_key}"

    def get(self, channel_id: str, conversation_key: str) -> SessionRecord | None:
        return self._records.get(self._key(channel_id, conversation_key))

    def upsert(
        self,
        channel_id: str,
        conversation_key: str,
        workspace_root: str,
        codex_thread_id: str | None,
    ) -> SessionRecord:
        now = time.time()
        key = self._key(channel_id, conversation_key)
        record = self._records.get(key)
        if record is None:
            record = SessionRecord(
                slack_channel_id=channel_id,
                conversation_key=conversation_key,
                workspace_root=workspace_root,
                codex_thread_id=codex_thread_id,
                created_at=now,
                updated_at=now,
            )
        else:
            record.workspace_root = workspace_root
            record.codex_thread_id = codex_thread_id
            record.updated_at = now
        self._records[key] = record
        self._save()
        return record

    def set_workspace(self, channel_id: str, conversation_key: str, workspace_root: str) -> SessionRecord:
        return self.upsert(channel_id, conversation_key, workspace_root, None)

    def delete(self, channel_id: str, conversation_key: str) -> bool:
        removed = self._records.pop(self._key(channel_id, conversation_key), None)
        if removed is not None:
            self._save()
            return True
        return False

    def touch(self, channel_id: str, conversation_key: str) -> None:
        record = self.get(channel_id, conversation_key)
        if record is None:
            return
        record.updated_at = time.time()
        self._save()

    def delete_stale(self, max_age_seconds: int) -> int:
        cutoff = time.time() - max_age_seconds
        stale_keys = [key for key, value in self._records.items() if value.updated_at < cutoff]
        for key in stale_keys:
            del self._records[key]
        if stale_keys:
            self._save()
        return len(stale_keys)
