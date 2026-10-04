import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("token-daily-report.sh")


class TokenDailyReportContractTest(unittest.TestCase):
    def run_isolated_report(self, *, token_target=None, alert_target=None, sender_env_target=None):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        script_dir = root / "skills" / "self"
        script_dir.mkdir(parents=True)
        script = script_dir / SCRIPT.name
        shutil.copy2(SCRIPT, script)

        sender = root / "skills" / "_shared" / "send-telegram.sh"
        sender.parent.mkdir(parents=True)
        sender.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
: > "$SENDER_REACHED"
LIFE_MANAGER_ENV_FILE="${LIFE_MANAGER_ENV_FILE:-${LIFE_MANAGER_STATE_HOME:-$HOME/.local/state/life-manager}/.env}"
[ -f "$LIFE_MANAGER_ENV_FILE" ] && set -a && source "$LIFE_MANAGER_ENV_FILE" && set +a
MSG="${1:?usage: send-telegram.sh \"<message>\" [chat_id]}"
CHAT_ID="${2:-${TELEGRAM_ALERT_CHAT_ID:?chat_id argument or TELEGRAM_ALERT_CHAT_ID is required}}"
printf '%s' "$CHAT_ID" > "$TARGET_CAPTURE"
""",
            encoding="utf-8",
        )
        sender.chmod(0o755)

        private_env = root / "private.env"
        if sender_env_target is not None:
            private_env.write_text(f"TELEGRAM_ALERT_CHAT_ID={sender_env_target}\n", encoding="utf-8")
        report = root / "usage-report.py"
        report.write_text("print('{\"totals\": {\"attempts\": 0}}')\n", encoding="utf-8")
        bash_env = root / "bash-env"
        bash_env.write_text("npx() { printf '%s\\n' '{\"daily\": []}'; }\n", encoding="utf-8")

        env = os.environ.copy()
        env.pop("TOKEN_REPORT_TELEGRAM_TARGET", None)
        env.pop("TELEGRAM_ALERT_CHAT_ID", None)
        if token_target is not None:
            env["TOKEN_REPORT_TELEGRAM_TARGET"] = token_target
        if alert_target is not None:
            env["TELEGRAM_ALERT_CHAT_ID"] = alert_target
        env.update({
            "AGENT_USAGE_REPORT_BIN": str(report),
            "BASH_ENV": str(bash_env),
            "LIFE_MANAGER_ENV_FILE": str(private_env),
            "SENDER_REACHED": str(root / "sender-reached"),
            "TARGET_CAPTURE": str(root / "target"),
        })
        completed = subprocess.run(
            ["/bin/bash", str(script)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed, root

    def test_report_is_one_exact_jst_day_all_agents_and_pinned_tool(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ccusage@20.0.18 daily", text)
        self.assertIn('--since "$YESTERDAY"', text)
        self.assertIn('--until "$YESTERDAY"', text)
        self.assertIn("--timezone Asia/Tokyo", text)
        self.assertIn("--by-agent", text)
        self.assertNotIn("ccusage@latest", text)
        self.assertIn("API換算", text)

    def test_report_includes_loop_attributed_runner_telemetry(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("usage_report.py", text)
        self.assertIn("AGENT_USAGE_REPORT_BIN", text)
        self.assertNotIn("profitable-claude", text)
        self.assertIn('--date "$YESTERDAY_ISO"', text)
        self.assertIn("loop別runner実測", text)

    def test_report_uses_repository_owned_telegram_sender(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('../_shared/send-telegram.sh', text)
        self.assertNotIn("openclaw message send", text)

    def test_missing_caller_target_uses_sender_private_env_target(self):
        completed, root = self.run_isolated_report(sender_env_target="private-fallback-id")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue((root / "sender-reached").exists())
        self.assertEqual((root / "target").read_text(encoding="utf-8"), "private-fallback-id")

    def test_explicit_token_target_then_alert_target_take_priority(self):
        for kwargs, expected in (
            ({"token_target": "token-target", "alert_target": "alert-target"}, "token-target"),
            ({"alert_target": "alert-target"}, "alert-target"),
        ):
            with self.subTest(expected=expected):
                completed, root = self.run_isolated_report(sender_env_target="private-fallback-id", **kwargs)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual((root / "target").read_text(encoding="utf-8"), expected)

    def test_missing_caller_and_sender_targets_fail_closed_at_sender(self):
        completed, root = self.run_isolated_report()
        self.assertNotEqual(completed.returncode, 0)
        self.assertTrue((root / "sender-reached").exists())
        self.assertFalse((root / "target").exists())
        self.assertIn("chat_id argument or TELEGRAM_ALERT_CHAT_ID is required", completed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
