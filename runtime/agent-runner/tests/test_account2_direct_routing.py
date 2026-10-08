#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "runtime" / "agent-runner" / "config.json"
sys.path.insert(0, str(CONFIG.parent))
from agent_runner import resolve_provider_profiles  # noqa: E402


class CodexProfileRoutingTest(unittest.TestCase):
    def test_all_task_classes_expand_codex_candidates_through_configured_failover_order(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        provider = config["providers"]["codex"]
        profiles = provider["profiles"]
        order = provider["account_profile_order"]
        self.assertEqual(set(profiles), {"acct1", "acct2"})
        self.assertEqual(order, ["acct1", "acct2"])

        for task_name, task in config["task_classes"].items():
            logical_candidates = task.get("candidates", [])
            resolved = resolve_provider_profiles(logical_candidates, config["providers"])
            cursor = 0
            for logical in logical_candidates:
                if logical.get("provider") != "codex":
                    self.assertEqual(resolved[cursor], logical, task_name)
                    cursor += 1
                    continue

                routed_order = order[order.index(logical["profile_alias"]):]
                for position, profile_alias in enumerate(routed_order):
                    with self.subTest(task_class=task_name, model=logical.get("model"), profile=profile_alias):
                        expected = {
                            **logical,
                            "profile_alias": profile_alias,
                            "automation_home": profiles[profile_alias]["automation_home"],
                            "auth_file": profiles[profile_alias]["auth_file"],
                            "account_fallback_next": position < len(routed_order) - 1,
                        }
                        self.assertEqual(resolved[cursor], expected)
                    cursor += 1

            self.assertEqual(cursor, len(resolved), task_name)


if __name__ == "__main__": unittest.main()


class CodexBusyLockFailsFastBeforeFallbackTest(unittest.TestCase):
    def test_codex_candidate_with_a_later_fallback_never_waits_silently_on_a_busy_lock(self):
        """2026-10-09: Capafy CP1 (application-lane-agent) waited 420s on a busy acct1 lock and was
        killed by the silent-start watchdog, although claude-direct was configured right behind it."""
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        offenders = []
        for name, task in config["task_classes"].items():
            candidates = task.get("candidates", [])
            for index, candidate in enumerate(candidates):
                later_fallback = any(c.get("provider") != "codex" for c in candidates[index + 1:])
                if candidate.get("provider") == "codex" and later_fallback \
                        and not candidate.get("fail_fast_provider_lease"):
                    offenders.append((name, index))
        self.assertEqual(offenders, [])
