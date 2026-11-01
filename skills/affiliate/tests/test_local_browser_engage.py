import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import local_browser  # noqa: E402


class EngageScheduleTest(unittest.TestCase):
    def run_once(self, env, last=0.0, now=1000.0):
        calls = []
        with patch.dict("os.environ", env, clear=True):
            result = local_browser._maybe_engage(last, now, runner=lambda *a, **k: calls.append(a))
        return result, calls

    def test_off_by_default(self):
        self.assertEqual(self.run_once({"LIFE_MANAGER_LOOP_ID": "affiliate-x-browser"})[1], [])

    def test_only_on_x_browser_loop(self):
        env = {"LIFE_MANAGER_LOOP_ID": "affiliate-browser", "AFFILIATE_X_ENGAGE_ENABLED": "1"}
        self.assertEqual(self.run_once(env)[1], [])

    def test_runs_when_enabled_and_respects_interval(self):
        env = {"LIFE_MANAGER_LOOP_ID": "affiliate-x-browser", "AFFILIATE_X_ENGAGE_ENABLED": "1"}
        last, calls = self.run_once(env)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0][1].endswith("x_engage.py"))
        self.assertEqual(self.run_once(env, last=last, now=last + 30)[1], [])


if __name__ == "__main__":
    unittest.main()
