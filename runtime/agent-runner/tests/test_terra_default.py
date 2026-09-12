import json
import unittest
from pathlib import Path

from agent_runner import configured_task_classes


class TerraDefaultTest(unittest.TestCase):
    def test_cli_task_classes_come_from_the_runtime_config(self):
        config_path = Path(__file__).resolve().parents[1] / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(set(configured_task_classes(config)), set(config["task_classes"]))
        self.assertIn("paid-owner-agent", configured_task_classes(config))

    def test_codex_provider_uses_managed_current_cli_before_path(self):
        config_path = Path(__file__).resolve().parents[1] / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(config["providers"]["codex"]["executable"], "~/.local/bin/codex")

    def test_every_executable_agent_class_prefers_terra(self):
        config_path = Path(__file__).resolve().parents[1] / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        for name, task_class in config["task_classes"].items():
            candidates = task_class.get("candidates", [])
            if not candidates:
                continue
            with self.subTest(task_class=name):
                expected = [
                    {"provider": "codex", "model": "gpt-5.6-terra", "effort": "medium", "profile_alias": "acct2"},
                ]
                if name == "application-intent-planner":
                    expected = [
                        {"provider": "codex", "model": "gpt-5.6-luna", "effort": "high", "profile_alias": "acct2"},
                        {"provider": "codex", "model": "gpt-5.6-terra", "effort": "medium", "profile_alias": "acct2"},
                        {"provider": "claude-direct", "model": "claude-sonnet-5"},
                    ]
                if name == "reply-semantic-agent":
                    expected = [{"provider": "codex", "model": "gpt-5.6-luna",
                                 "effort": "medium", "timeout_seconds": 120,
                                 "profile_alias": "acct2"}]
                if name == "storefront-proposal-agent":
                    expected = [{"provider": "codex", "model": "gpt-5.6-terra",
                                 "effort": "medium", "timeout_seconds": 90,
                                 "profile_alias": "acct2"}]
                if name == "writer-sol-audit":
                    expected = [{"provider": "codex", "model": "gpt-5.6-sol",
                                 "effort": "medium", "profile_alias": "acct2"}]
                if name == "writer-repair-agent":
                    expected = [{"provider": "codex", "model": "gpt-5.6-terra",
                                 "effort": "medium", "profile_alias": "acct2"}]
                if name == "affiliate-marketing-agent":
                    expected = [{"provider": "codex", "model": "gpt-5.6-terra",
                                 "effort": "high", "profile_alias": "acct2"}]
                if name == "affiliate-escalation-agent":
                    expected = [{"provider": "codex", "model": "gpt-5.6-sol",
                                 "effort": "high", "profile_alias": "acct2"}]
                if name == "browser-lane-agent":
                    expected = [
                        {"provider": "codex", "model": "gpt-5.6-terra",
                         "effort": "high", "profile_alias": "acct2"},
                    ]
                # Every executable class now carries a working Claude fallback so a
                # codex quota outage cannot idle a money lane.
                fallback = {"provider": "claude-direct", "model": "claude-sonnet-5"}
                if fallback not in expected:
                    expected.append(fallback)
                self.assertEqual(candidates, expected)

    def test_a_restricted_candidate_carries_its_escalation_route(self):
        """Without the route the runner raises at the first wake, not at review time."""
        config_path = Path(__file__).resolve().parents[1] / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        for name, task_class in config["task_classes"].items():
            restricted = [
                candidate for candidate in task_class.get("candidates", [])
                if candidate.get("effort") in {"high", "xhigh", "max"}
                or "sol" in str(candidate.get("model") or "").lower()
            ]
            if not restricted:
                continue
            with self.subTest(task_class=name):
                self.assertTrue(task_class.get("requires_explicit_escalation"))

    def test_browser_lane_accepts_an_explicit_1800_second_timeout(self):
        config_path = Path(__file__).resolve().parents[1] / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        configured = config["task_classes"]["browser-lane-agent"]["timeout_seconds"]
        self.assertEqual(min(configured, 1800), 1800)


if __name__ == "__main__":
    unittest.main()
