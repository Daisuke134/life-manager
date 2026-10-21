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

if __name__ == "__main__":
    unittest.main()
