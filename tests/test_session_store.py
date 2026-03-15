import tempfile
import unittest
from pathlib import Path

from slack_codex_bridge.session_store import SessionStore


class SessionStoreTests(unittest.TestCase):
    def test_upsert_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sessions.json"
            store = SessionStore(path)
            store.upsert("C1", "123.45", "/tmp/repo", "codex-thread-1")

            reloaded = SessionStore(path)
            record = reloaded.get("C1", "123.45")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.codex_thread_id, "codex-thread-1")
            self.assertEqual(record.conversation_key, "123.45")
            self.assertEqual(record.workspace_root, "/tmp/repo")

    def test_delete_missing_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sessions.json"
            store = SessionStore(path)
            self.assertFalse(store.delete("C1", "123.45"))

    def test_same_thread_conversation_key_reuses_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sessions.json"
            store = SessionStore(path)
            store.upsert("D1", "thread-1", "/tmp/repo", "codex-thread-1")
            store.upsert("D1", "thread-1", "/tmp/repo", "codex-thread-1")

            record = store.get("D1", "thread-1")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.codex_thread_id, "codex-thread-1")

    def test_set_workspace_clears_existing_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sessions.json"
            store = SessionStore(path)
            store.upsert("D1", "thread-1", "/tmp/repo-a", "codex-thread-1")

            record = store.set_workspace("D1", "thread-1", "/tmp/repo-b")

            self.assertEqual(record.workspace_root, "/tmp/repo-b")
            self.assertIsNone(record.codex_thread_id)


if __name__ == "__main__":
    unittest.main()
