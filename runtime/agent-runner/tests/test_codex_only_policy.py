"""The local Life Manager model boundary is Codex-only."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "runtime" / "agent-runner"))


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

if __name__ == "__main__":
    unittest.main()
