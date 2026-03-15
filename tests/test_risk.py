import unittest

from slack_codex_bridge.risk import classify_risk


class RiskClassifierTests(unittest.TestCase):
    def test_readonly_question_stays_readonly(self) -> None:
        decision = classify_risk("Explain why the Slack connection fails on startup.")
        self.assertEqual(decision.level, "readonly")

    def test_edit_request_is_high_risk(self) -> None:
        decision = classify_risk("Implement the retry logic and update the Slack client.")
        self.assertEqual(decision.level, "high_risk")

    def test_package_install_is_high_risk(self) -> None:
        decision = classify_risk("Run npm install and fix the lockfile.")
        self.assertEqual(decision.level, "high_risk")

    def test_chinese_edit_request_is_high_risk(self) -> None:
        decision = classify_risk("对这个仓库做个小修改")
        self.assertEqual(decision.level, "high_risk")


if __name__ == "__main__":
    unittest.main()
