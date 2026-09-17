import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


AUTO = Path(__file__).resolve().parents[1]
KEY_GATE = AUTO / "scripts" / "key_health_gate.sh"
BUILD_CONFIG = AUTO / "scripts" / "build_config.py"
LINT_LISTING = AUTO / "scripts" / "lint_listing.py"
CANONICAL_PAID_ONLY_FILES = (
    AUTO / "BEST_PRACTICES.md",
    AUTO / "SKILL.md",
    AUTO / "PUBLISHING_RUNBOOK.md",
    AUTO / "references" / "pricing.md",
    AUTO.parent / "capafy" / "catalog" / "youtube-script-writer" / "LISTING.md",
)
KEY_GATE_CALL_SITES = (
    AUTO / "scripts" / "daily_loop.sh",
    AUTO / "scripts" / "publish_prepare.sh",
    AUTO / "scripts" / "publish_finish.sh",
    AUTO.parent / "self" / "capafy-loop" / "capafy-loop-healthcheck.sh",
)


class KeyHealthGateTest(unittest.TestCase):
    def run_gate(self, key_response, enable_alert=False, credits_remaining=25,
                 management_key="", healed_key_response=None, hard_cap="50",
                 hosted_model_id=None, hosted_max_tokens=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            calls = root / "curl-calls.txt"
            fake_curl = fake_bin / "curl"
            fake_curl.write_text(
                """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_CURL_CALLS"
case "$*" in
  *-X\\ PATCH*https://openrouter.ai/api/v1/keys/*)
    : > "$FAKE_PATCH_MARKER"
    printf '%s\\n' '{"data":{"limit":15,"limit_reset":"daily"}}'
    ;;
  *https://openrouter.ai/api/v1/key*)
    if [ -f "$FAKE_PATCH_MARKER" ]; then
      printf '%s\\n' "$FAKE_HEALED_KEY_RESPONSE"
    else
      printf '%s\\n' "$FAKE_KEY_RESPONSE"
    fi
    ;;
  *https://openrouter.ai/api/v1/credits*) printf '%s\\n' "$FAKE_CREDITS_RESPONSE" ;;
  *https://openrouter.ai/api/v1/chat/completions*) printf '%s\\n' '{"choices":[{"message":{"content":"ok"}}]}' ;;
  *) exit 1 ;;
esac
""",
                encoding="utf-8",
            )
            fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IXUSR)
            alert_calls = root / "openclaw-calls.txt"
            if enable_alert:
                fake_sender = fake_bin / "send-telegram.sh"
                fake_sender.write_text(
                    """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_OPENCLAW_CALLS"
exit 0
""",
                    encoding="utf-8",
                )
                fake_sender.chmod(fake_sender.stat().st_mode | stat.S_IXUSR)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{fake_bin}:{env['PATH']}",
                    "CAPAFY_HOST_OPENROUTER_KEY": "key-must-not-print",
                    "FAKE_KEY_RESPONSE": json.dumps(key_response),
                    "FAKE_HEALED_KEY_RESPONSE": json.dumps(
                        healed_key_response or key_response
                    ),
                    "FAKE_PATCH_MARKER": str(root / "patched"),
                    "FAKE_CREDITS_RESPONSE": json.dumps(
                        {"data": {"total_credits": credits_remaining, "total_usage": 0}}
                    ),
                    "FAKE_CURL_CALLS": str(calls),
                    "FAKE_OPENCLAW_CALLS": str(alert_calls),
                    "LIFE_MANAGER_STATE_HOME": str(root / "state"),
                    "CAPAFY_OPENROUTER_MANAGEMENT_KEY": management_key,
                    "CAPAFY_KEY_DAILY_HARD_CAP_USD": hard_cap,
                }
            )
            if enable_alert:
                env["TELEGRAM_ALERT_CHAT_ID"] = "test-chat"
                env["CAPAFY_TELEGRAM_SENDER"] = str(fake_sender)
            else:
                env.pop("TELEGRAM_ALERT_CHAT_ID", None)
            if hosted_model_id:
                env["CAPAFY_HOSTED_MODEL_ID"] = hosted_model_id
            if hosted_max_tokens:
                env["CAPAFY_HOSTED_MAX_TOKENS"] = str(hosted_max_tokens)
            result = subprocess.run(
                ["bash", str(KEY_GATE)],
                env=env,
                text=True,
                capture_output=True,
            )
            return (
                result,
                calls.read_text(encoding="utf-8") if calls.exists() else "",
                alert_calls.read_text(encoding="utf-8") if alert_calls.exists() else "",
                len(list((root / "state" / "state").glob(".capafy-funding-alert-*"))),
            )

    def test_blocks_zero_or_negative_per_key_limit_before_live_probe(self):
        for remaining in (0, -0.01):
            with self.subTest(remaining=remaining):
                result, call_text, _, _ = self.run_gate({"data": {"limit_remaining": remaining}})
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("key_limit_exhausted", output)
                self.assertNotIn("key-must-not-print", output)
                self.assertIn("https://openrouter.ai/api/v1/key", call_text)
                self.assertNotIn("https://openrouter.ai/api/v1/chat/completions", call_text)

    def test_unlimited_key_keeps_existing_balance_and_live_probe_checks(self):
        result, call_text, _, _ = self.run_gate({"data": {"limit_remaining": None}})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("live_probe=200", result.stdout)
        self.assertIn("https://openrouter.ai/api/v1/key", call_text)
        self.assertIn("https://openrouter.ai/api/v1/credits", call_text)
        self.assertIn("https://openrouter.ai/api/v1/chat/completions", call_text)

    def test_default_probe_uses_bounded_deepseek_contract(self):
        result, call_text, _, _ = self.run_gate({"data": {"limit_remaining": None}})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("deepseek/deepseek-v4.1-flash", call_text)
        self.assertIn('"max_tokens": 8192', call_text)

    def test_deepseek_probe_uses_packaged_bounded_model_contract(self):
        result, call_text, _, _ = self.run_gate(
            {"data": {"limit_remaining": 25}},
            hosted_model_id="deepseek/deepseek-v4.1-flash", hosted_max_tokens=8192,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("deepseek/deepseek-v4.1-flash", call_text)
        self.assertIn('"max_tokens": 8192', call_text)

    def test_positive_key_limit_below_one_capafy_request_blocks_before_probe(self):
        result, call_text, _, _ = self.run_gate(
            {"data": {"limit_remaining": 1.50}}, credits_remaining=20
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("key_limit_self_heal_failed", output)
        self.assertNotIn("https://openrouter.ai/api/v1/chat/completions", call_text)

    def test_low_key_headroom_self_heals_then_runs_live_probe(self):
        result, call_text, _, _ = self.run_gate(
            {"data": {"limit": 10, "limit_remaining": 1.50,
                      "usage_daily": 8.50, "limit_reset": "daily"}},
            credits_remaining=20,
            management_key="management-key-must-not-print",
            healed_key_response={"data": {"limit": 35, "limit_remaining": 26.50,
                                          "usage_daily": 8.50,
                                          "limit_reset": "daily"}},
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("KEY_SELF_HEAL=OK", output)
        self.assertIn("-X PATCH", call_text)
        self.assertIn("https://openrouter.ai/api/v1/chat/completions", call_text)
        self.assertNotIn("management-key-must-not-print", output)

    def test_exhausted_key_self_heals_then_runs_live_probe(self):
        result, call_text, _, _ = self.run_gate(
            {"data": {"limit": 10, "limit_remaining": 0,
                      "usage_daily": 10, "limit_reset": "daily"}},
            credits_remaining=20,
            management_key="management-key-must-not-print",
            healed_key_response={"data": {"limit": 30, "limit_remaining": 20,
                                          "usage_daily": 10,
                                          "limit_reset": "daily"}},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("KEY_SELF_HEAL=OK", result.stdout)
        self.assertIn("-X PATCH", call_text)
        self.assertIn("https://openrouter.ai/api/v1/chat/completions", call_text)

    def test_self_heal_fails_closed_at_configured_hard_cap(self):
        result, call_text, _, _ = self.run_gate(
            {"data": {"limit": 50, "limit_remaining": 1.50,
                      "usage_daily": 48.50, "limit_reset": "daily"}},
            credits_remaining=100,
            management_key="management-key-must-not-print",
            hard_cap="100",
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("key_limit_self_heal_cap_reached", output)
        self.assertNotIn("-X PATCH", call_text)
        self.assertNotIn("management-key-must-not-print", output)

    def test_balance_below_default_safety_floor_blocks(self):
        result, _, _, _ = self.run_gate(
            {"data": {"limit_remaining": 25}}, credits_remaining=19.99
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("balance_too_low", result.stdout + result.stderr)

    def test_balance_at_default_safety_floor_runs_live_probe(self):
        result, call_text, _, _ = self.run_gate(
            {"data": {"limit_remaining": 25}}, credits_remaining=20
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("https://openrouter.ai/api/v1/chat/completions", call_text)

    def test_production_call_sites_do_not_override_the_safety_floor(self):
        for path in KEY_GATE_CALL_SITES:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"key_health_gate\.sh[\"']?\s+5\.00")
                self.assertNotRegex(text, r"\$KEY_GATE[\"']?\s+5\.00")

    def test_warning_and_block_alerts_have_distinct_truthful_messages(self):
        warning, _, warning_text, warning_markers = self.run_gate(
            {"data": {"limit_remaining": 25}},
            credits_remaining=24.99,
            enable_alert=True,
        )
        self.assertEqual(warning.returncode, 0, warning.stdout + warning.stderr)
        self.assertIn("approaching the publishing safety floor", warning_text)
        self.assertEqual(warning_markers, 1)

        blocked, _, blocked_text, blocked_markers = self.run_gate(
            {"data": {"limit_remaining": 25}},
            credits_remaining=19.99,
            enable_alert=True,
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("Publishing is blocked until funding recovers", blocked_text)
        self.assertEqual(blocked_markers, 1)

    def test_exhausted_key_calls_deduped_alert_without_printing_key(self):
        result, _, alert_text, marker_count = self.run_gate(
            {"data": {"limit_remaining": 0}}, enable_alert=True
        )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("key_limit_exhausted", output)
        self.assertNotIn("key-must-not-print", output)
        self.assertEqual(len(alert_text.splitlines()), 1)
        self.assertIn("test-chat", alert_text)
        self.assertNotIn("key-must-not-print", alert_text)
        self.assertEqual(marker_count, 1)


class PaidListingTest(unittest.TestCase):
    def listing(self, trial):
        return f"""Primary Model: Claude Sonnet 4.6 · category: ライティング · tags: writing, copy, youtube

| cycle | price | cap | trial |
| week | $9.99 | 20 | {trial} |

## Title
YouTube Script Writer
## shortDescription
Write a concise YouTube script from your topic.
## welcomeMessage
👋 I write scripts. Example: \"a launch story\"
## detailedDescription
Structured script output from your brief.
"""

    def run_tools(self, trial):
        with tempfile.TemporaryDirectory() as td:
            listing = Path(td) / "LISTING.md"
            listing.write_text(self.listing(trial), encoding="utf-8")
            lint = subprocess.run(
                [sys.executable, str(LINT_LISTING), str(listing)],
                text=True,
                capture_output=True,
            )
            build = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_CONFIG),
                    str(listing),
                    "/tmp/icon.png",
                ],
                text=True,
                capture_output=True,
            )
            return lint, build

    def test_non_no_free_trial_is_rejected_by_lint_and_build(self):
        lint, build = self.run_tools("24h")
        self.assertNotEqual(lint.returncode, 0, lint.stdout + lint.stderr)
        self.assertIn("No Free Trial", lint.stdout + lint.stderr)
        self.assertNotEqual(build.returncode, 0, build.stdout + build.stderr)
        self.assertIn("No Free Trial", build.stdout + build.stderr)

    def test_no_free_trial_builds_a_config_without_trial(self):
        lint, build = self.run_tools("No Free Trial")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        config = json.loads(build.stdout)
        self.assertEqual(config["model_id"], "anthropic/claude-sonnet-4.6")
        self.assertEqual(config["max_tokens"], 128000)
        self.assertEqual(config["plans"], [{"cycle": "week", "price": "9.99", "cap": "20", "trial": None}])
        self.assertNotIn("edit_url", config)

    def test_deepseek_listing_builds_exact_hosted_model_contract(self):
        listing = AUTO.parent / "capafy/catalog/marketing-strategist/LISTING.md"
        icon = AUTO.parent / "capafy/catalog/marketing-strategist/icon.webp"
        result = subprocess.run(
            [sys.executable, str(BUILD_CONFIG), str(listing), str(icon)],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config["model_id"], "deepseek/deepseek-v4.1-flash")
        self.assertEqual(config["max_tokens"], 8192)
        self.assertEqual([plan["trial"] for plan in config["plans"]], [None, None])
        serialized = json.dumps(config, ensure_ascii=False)
        self.assertNotIn("draftKey", serialized)
        self.assertNotIn("token=", serialized)

    def test_config_file_is_private_and_contains_no_browser_url(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            listing = root / "LISTING.md"
            listing.write_text(self.listing("No Free Trial"), encoding="utf-8")
            private_dir = root / "private"
            private_dir.mkdir(mode=0o755)
            output = private_dir / "cfg_one.json"
            build = subprocess.run(
                [sys.executable, str(BUILD_CONFIG), str(listing), "/tmp/icon.png", str(output)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(private_dir.stat().st_mode), 0o700)
            config = json.loads(output.read_text(encoding="utf-8"))
            self.assertNotIn("edit_url", config)
            serialized = json.dumps(config, ensure_ascii=False)
            self.assertNotIn("draftKey", serialized)
            self.assertNotIn("token=", serialized)

    def test_config_builder_rejects_wrong_arity(self):
        build = subprocess.run(
            [sys.executable, str(BUILD_CONFIG)],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(build.returncode, 0)

    def test_canonical_paid_only_docs_have_no_enabled_free_trial_guidance(self):
        normative_patterns = (
            r"enable\s+free\s+trial",
            r"\bif\s+enable\b",
            r"free\s+trial\s*を必ず",
            r"per-plan\s+trial\s*=\s*winner",
            r"trial\s*=\s*winner\s+config",
            r"TRIAL\s+config\s*=\s*COPY\s+THE\s+WINNER",
            r"copy\s+billings?[^\n]*\btrial\b",
        )
        for path in CANONICAL_PAID_ONLY_FILES:
            text = path.read_text(encoding="utf-8")
            for pattern in normative_patterns:
                self.assertIsNone(
                    re.search(pattern, text, re.I),
                    f"normative free-trial guidance remains: {pattern} in {path}",
                )

        listing = CANONICAL_PAID_ONLY_FILES[-1].read_text(encoding="utf-8")
        rows = re.findall(
            r"\|\s*(day|week|month)\s*\|\s*\$?[0-9.]+\s*\|\s*[0-9]+\s*\|\s*([^|]+)\|",
            listing,
            re.I,
        )
        self.assertTrue(rows)
        self.assertTrue(all(re.fullmatch(r"no[\s_-]+free[\s_-]+trial", trial.strip(), re.I) for _, trial in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
