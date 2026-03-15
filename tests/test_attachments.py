import tempfile
import unittest
from pathlib import Path

from slack_codex_bridge.attachments import parse_response_attachments, validate_image_path


class AttachmentTests(unittest.TestCase):
    def test_parse_response_attachments(self) -> None:
        parsed = parse_response_attachments("Done.\n[[image:/tmp/a.png]]\n[[image:/tmp/b.jpg]]")
        self.assertEqual(parsed.text, "Done.")
        self.assertEqual(parsed.image_paths, [Path("/tmp/a.png"), Path("/tmp/b.jpg")])

    def test_validate_image_path_allows_workspace_and_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            image = workspace / "out.png"
            image.write_bytes(b"fake")
            self.assertIsNone(validate_image_path(image, workspace))

    def test_validate_image_path_rejects_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            self.assertEqual(
                validate_image_path(Path("relative.png"), workspace),
                "image path must be absolute",
            )


if __name__ == "__main__":
    unittest.main()
