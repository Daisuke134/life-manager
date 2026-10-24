"""The local Life Manager model boundary is Codex-only."""

from __future__ import annotations

import json
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "runtime" / "agent-runner"))
import agent_runner


class CodexOnlyPolicyTests(unittest.TestCase):
    def test_managed_agent_runner_configs_have_no_non_codex_provider(self) -> None:
        configs = (
            ROOT / "runtime" / "agent-runner" / "config.json",
            ROOT / "apps" / "job-search-loop" / "agent-runner" / "config.json",
        )
        for path in configs:
            with self.subTest(config=str(path.relative_to(ROOT))):
                config = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(set(config["providers"]), {"codex"})
                for task_name, task in config["task_classes"].items():
                    for candidate in task.get("candidates", []):
                        self.assertEqual(
                            candidate["provider"], "codex",
                            f"{task_name} can route to {candidate['provider']}",
                        )

    def test_environment_selected_config_cannot_reintroduce_claude(self) -> None:
        config = json.loads((ROOT / "runtime" / "agent-runner" / "config.json").read_text())
        config["providers"]["claude"] = {"executable": "claude"}
        config["task_classes"]["composition-agent"]["candidates"].append(
            {"provider": "claude", "model": "fixture-claude"}
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "override.json"
            schema_path = root / "schema.json"
            schema_path.write_text('{"type":"object"}', encoding="utf-8")
            config_path.write_text(json.dumps(config), encoding="utf-8")
            argv = [
                "agent_runner.py", "--task-class", "composition-agent", "--prompt-stdin",
                "--schema", str(schema_path), "--evidence-dir", str(root / "evidence"),
                "--task-label", "codex-only-override", "--read-only",
            ]
            with patch.dict(os.environ, {"AGENT_RUNNER_CONFIG": str(config_path)}):
                with patch.object(sys, "argv", argv), patch.object(sys, "stdin", io.StringIO("task " * 100)):
                    with patch("agent_runner.resolve_provider_profiles", return_value=[]) as resolve:
                        agent_runner.run()
            resolve.assert_not_called()


class CodexLimitFallbackTests(unittest.TestCase):
    """Claude is allowed only as the LAST candidate of composition-agent, and only for a usage-limit outage."""

    def _config(self):
        return json.loads((ROOT / "runtime" / "agent-runner" / "config.json").read_text())

    def test_default_config_still_has_no_claude_anywhere(self) -> None:
        config = self._config()
        agent_runner.validate_codex_only_config(config)  # must not raise
        self.assertNotIn("claude", config["providers"])
        for task in config["task_classes"].values():
            self.assertTrue(all(c["provider"] == "codex" for c in task["candidates"]))

    def test_the_fallback_config_is_valid_and_only_adds_the_scoped_claude_candidate(self) -> None:
        base = self._config()
        fallback = json.loads((ROOT / "runtime" / "agent-runner" / "config.codex-limit-fallback.json").read_text())
        agent_runner.validate_codex_only_config(fallback)
        self.assertEqual(set(fallback["providers"]) - set(base["providers"]), {"claude"})
        for name, task in fallback["task_classes"].items():
            extra = [c for c in task["candidates"] if c["provider"] != "codex"]
            if name == "composition-agent":
                self.assertEqual(len(extra), 1)
                self.assertEqual(task["candidates"][-1], extra[0])
                self.assertEqual(extra[0]["only_when"], "codex_usage_limit")
            else:
                self.assertEqual(extra, [])
            self.assertEqual([c for c in task["candidates"] if c["provider"] == "codex"],
                             base["task_classes"][name]["candidates"])

    def test_claude_is_allowed_only_as_the_last_composition_agent_candidate(self) -> None:
        config = self._config()
        config["providers"]["claude"] = {"executable": "claude"}
        config["task_classes"]["composition-agent"]["candidates"].append(
            {"provider": "claude", "model": "fixture-claude", "only_when": "codex_usage_limit"})
        agent_runner.validate_codex_only_config(config)  # explicit, scoped exception

    def test_claude_first_in_the_list_is_rejected(self) -> None:
        config = self._config()
        config["providers"]["claude"] = {"executable": "claude"}
        config["task_classes"]["composition-agent"]["candidates"].insert(
            0, {"provider": "claude", "model": "fixture-claude", "only_when": "codex_usage_limit"})
        with self.assertRaises(ValueError):
            agent_runner.validate_codex_only_config(config)

    def test_claude_without_the_usage_limit_condition_is_rejected(self) -> None:
        config = self._config()
        config["providers"]["claude"] = {"executable": "claude"}
        config["task_classes"]["composition-agent"]["candidates"].append(
            {"provider": "claude", "model": "fixture-claude"})
        with self.assertRaises(ValueError):
            agent_runner.validate_codex_only_config(config)

    def test_claude_on_any_other_task_class_is_rejected(self) -> None:
        config = self._config()
        config["providers"]["claude"] = {"executable": "claude"}
        other = next(name for name in config["task_classes"] if name != "composition-agent")
        config["task_classes"][other]["candidates"].append(
            {"provider": "claude", "model": "fixture-claude", "only_when": "codex_usage_limit"})
        with self.assertRaises(ValueError):
            agent_runner.validate_codex_only_config(config)

if __name__ == "__main__":
    unittest.main()
