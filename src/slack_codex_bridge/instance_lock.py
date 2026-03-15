from __future__ import annotations

import atexit
import fcntl
import os
from pathlib import Path


class SingleInstanceError(RuntimeError):
    """Raised when another bridge instance already holds the lock."""


class InstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: os.TextIOWrapper | None = None

    def acquire(self) -> None:
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise SingleInstanceError(f"Another slack_codex_bridge instance is already running (lock: {self.path}).") from exc

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        atexit.register(self.release)

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
