import plistlib
import unittest
from pathlib import Path


class LaunchdTests(unittest.TestCase):
    def test_plists_have_separate_recurring_schedules(self):
        root = Path(__file__).parents[1] / "launchd"
        browser = plistlib.loads(
            (root / "ai.anicca.job-search-browser.plist").read_bytes()
        )
        daily = plistlib.loads((root / "ai.anicca.job-search-daily.plist").read_bytes())
        inbox = plistlib.loads((root / "ai.anicca.job-search-inbox.plist").read_bytes())
        learning = plistlib.loads(
            (root / "ai.anicca.job-search-learning.plist").read_bytes()
        )
        self.assertTrue(daily["RunAtLoad"])
        self.assertTrue(browser["RunAtLoad"])
        self.assertTrue(browser["KeepAlive"])
        self.assertEqual(browser["Label"], "ai.anicca.job-search-browser")
        self.assertEqual(daily["StartInterval"], 1800)
        self.assertEqual(inbox["StartInterval"], 900)
        self.assertTrue(learning["RunAtLoad"])
        self.assertEqual(
            learning["StartCalendarInterval"],
            {"Hour": 9, "Minute": 15},
        )
        self.assertNotEqual(daily["Label"], inbox["Label"])
        self.assertNotEqual(daily["ProgramArguments"][0], inbox["ProgramArguments"][0])
        self.assertNotEqual(
            learning["ProgramArguments"][0], daily["ProgramArguments"][0]
        )

    def test_inbox_shell_uses_deterministic_prefilter_before_model(self):
        root = Path(__file__).parents[1]
        script = (root / "scripts" / "run-inbox.sh").read_text(encoding="utf-8")
        self.assertIn("job_search_loop.inbox scan", script)
        self.assertIn(
            'if [[ "$NEW_COUNT" == "0" && "$PENDING_PREP_COUNT" == "0" ]]',
            script,
        )
        self.assertIn("job_search_loop.inbox mark", script)
        self.assertIn(".result_path", script)
        self.assertIn('--result "$RESULT_PATH"', script)

    def test_inbox_shell_processes_due_preps_without_new_email(self):
        root = Path(__file__).parents[1]
        script = (root / "scripts" / "run-inbox.sh").read_text(encoding="utf-8")
        self.assertIn("job_search_loop.interview_prep deliver", script)
        self.assertIn("job_search_loop.interview_prep append-prompt", script)
        self.assertIn("PENDING_PREP_COUNT", script)
        self.assertIn(
            'if [[ "$NEW_COUNT" == "0" && "$PENDING_PREP_COUNT" == "0" ]]',
            script,
        )
        self.assertLess(
            script.index("job_search_loop.interview_prep deliver"),
            script.index('if [[ "$NEW_COUNT"'),
        )

    def test_daily_shell_has_no_product_daily_quota_gate(self):
        root = Path(__file__).parents[1]
        script = (root / "scripts" / "run-daily.sh").read_text(encoding="utf-8")
        self.assertNotIn("daily_slot_count", script)
        self.assertNotIn("daily_quota_reached", script)

    def test_healthcheck_covers_scheduler_ledger_and_private_state(self):
        root = Path(__file__).parents[1]
        script = (root / "scripts" / "healthcheck.sh").read_text(encoding="utf-8")
        self.assertIn('"$JOB_SEARCH_PLUTIL" -lint', script)
        self.assertIn("PRAGMA integrity_check", script)
        self.assertIn('if (candidate / "summary.json").is_file()', script)
        self.assertIn("interview-prep.sqlite3", script)
        self.assertIn("interview_preps", script)
        self.assertIn("ai.anicca.job-search-daily", script)
        self.assertIn("ai.anicca.job-search-inbox", script)
        self.assertIn("ai.anicca.job-search-learning", script)
        self.assertIn('"learning-": 8 * 24 * 3600', script)
        self.assertIn('candidate / "workday-fast-path.json"', script)
        self.assertIn('candidate / "wake-report.json"', script)
        self.assertIn('"$STATUS" == *"state=running"*', script)
        self.assertIn("ai.anicca.life-manager-daily-driver", script)
        self.assertNotIn("ai.anicca.job-search-browser unhealthy", script)
        self.assertNotIn("ashby-fast-path-combined.json", script)
        self.assertNotIn("cat /Users/anicca/.openclaw/.env", script)

    def test_health_failure_stays_in_private_evidence(self):
        root = Path(__file__).parents[1]
        script = (root / "scripts" / "run-health.sh").read_text(encoding="utf-8")
        self.assertIn('"delivery": "suppressed"', script)
        self.assertNotIn("job_search_loop.telegram import send_once", script)
        self.assertNotIn("job-search-health:", script)
        self.assertNotIn("openclaw message send", script)
        self.assertNotIn("Codex:::", script)
        self.assertNotIn("[Job Hunter]", script)


if __name__ == "__main__":
    unittest.main()
