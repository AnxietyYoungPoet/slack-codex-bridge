import unittest

from slack_codex_bridge.codex_client import IMAGE_REPLY_INSTRUCTION, _parse_json_events


class ParseJsonEventsTests(unittest.TestCase):
    def test_parse_thread_and_message(self) -> None:
        payload = "\n".join(
            [
                '{"type":"thread.started","thread_id":"thread-123"}',
                '{"type":"turn.started"}',
                '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"done"}}',
            ]
        )
        result = _parse_json_events(payload)
        self.assertEqual(result.codex_thread_id, "thread-123")
        self.assertEqual(result.final_text, "done")

    def test_error_event_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            _parse_json_events('{"type":"error","message":"bad"}')

    def test_ignores_malformed_json_lines(self) -> None:
        payload = "\n".join(
            [
                "Codex debug output",
                '{"type":"thread.started","thread_id":"thread-123"}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"unterminated"}',
            ]
        )
        result = _parse_json_events(payload)
        self.assertEqual(result.codex_thread_id, "thread-123")
        self.assertEqual(result.final_text, "done")

    def test_image_reply_instruction_mentions_marker_format(self) -> None:
        self.assertIn("[[image:/absolute/path/to/file.png]]", IMAGE_REPLY_INSTRUCTION)


if __name__ == "__main__":
    unittest.main()
