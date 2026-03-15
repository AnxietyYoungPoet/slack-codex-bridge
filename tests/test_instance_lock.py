import tempfile
import unittest
from pathlib import Path

from slack_codex_bridge.instance_lock import InstanceLock, SingleInstanceError


class InstanceLockTests(unittest.TestCase):
    def test_second_lock_fails_until_first_releases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bridge.lock"
            first = InstanceLock(path)
            second = InstanceLock(path)

            first.acquire()
            with self.assertRaises(SingleInstanceError):
                second.acquire()

            first.release()
            second.acquire()
            second.release()


if __name__ == "__main__":
    unittest.main()
