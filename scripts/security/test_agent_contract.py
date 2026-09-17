from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-agent-contract.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "sec-scan.yml"
CONTROL_ROOM = Path("control-room") / "CLAUDE.md"
HYPERFRAMES = Path("skills/video/hyperframes/capafy-o13-review")


class AgentContractTests(unittest.TestCase):
    def run_gate(self, root: Path) -> subprocess.CompletedProcess[str]:
        environment = {key: value for key, value in os.environ.items() if key != "LIFE_MANAGER_REPO"}
        return subprocess.run(
            ["bash", str(SCRIPT), str(root)],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )

    def fixture(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="agent-contract-"))
        (root / "AGENTS.md").write_text(
            """# Life Manager project instructions

canonical remote https://github.com/Daisuke134/life-manager.git
Read superpowers:using-superpowers first.
Use Astra Advisor orchestration when available.
Use Ponytail for the smallest implementation.
Remove that exact worktree without force.
""",
            encoding="utf-8",
        )
        (root / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        control_room = root / CONTROL_ROOM
        control_room.parent.mkdir(parents=True)
        control_room.write_text(
            "# control-room context\n\ninherited from repository root ../AGENTS.md\n",
            encoding="utf-8",
        )
        hyperframes = root / HYPERFRAMES
        hyperframes.mkdir(parents=True)
        (hyperframes / "AGENTS.md").write_text("local rules\n", encoding="utf-8")
        (hyperframes / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        return root

    def test_canonical_agent_contract_passes(self):
        root = self.fixture()
        try:
            result = self.run_gate(root)
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            shutil.rmtree(root)

    def test_security_workflow_runs_the_gate(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("agent-contract:", workflow)
        self.assertIn("scripts/verify-agent-contract.sh", workflow)

    def test_stale_checkout_reference_fails(self):
        root = self.fixture()
        try:
            (root / "AGENTS.md").write_text(
                (root / "AGENTS.md").read_text(encoding="utf-8") + "Use " + "/" + "Users/anicca/anicca-project.\n",
                encoding="utf-8",
            )
            result = self.run_gate(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("stale checkout", result.stderr)
        finally:
            shutil.rmtree(root)

    def test_stale_nested_control_room_reference_fails(self):
        root = self.fixture()
        try:
            (root / CONTROL_ROOM).write_text(
                "inherited from " + "~/" + "anicca-project/CLAUDE.md\n", encoding="utf-8",
            )
            result = self.run_gate(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("nested", result.stderr)
        finally:
            shutil.rmtree(root)

    def test_nested_hyperframes_claude_must_import_local_agents(self):
        root = self.fixture()
        try:
            nested = root / HYPERFRAMES
            (nested / "CLAUDE.md").write_text("duplicate local rules\n", encoding="utf-8")
            result = self.run_gate(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("nested", result.stderr)
        finally:
            shutil.rmtree(root)

    def test_missing_nested_control_room_contract_fails(self):
        root = self.fixture()
        try:
            (root / CONTROL_ROOM).unlink()
            result = self.run_gate(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("control-room", result.stderr)
        finally:
            shutil.rmtree(root)

    def test_missing_nested_hyperframes_agents_fails(self):
        root = self.fixture()
        try:
            (root / HYPERFRAMES / "AGENTS.md").unlink()
            result = self.run_gate(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("HyperFrames AGENTS.md", result.stderr)
        finally:
            shutil.rmtree(root)

    def test_missing_nested_hyperframes_claude_fails(self):
        root = self.fixture()
        try:
            (root / HYPERFRAMES / "CLAUDE.md").unlink()
            result = self.run_gate(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("HyperFrames CLAUDE.md", result.stderr)
        finally:
            shutil.rmtree(root)

    def test_nested_hyperframes_claude_rejects_extra_content(self):
        root = self.fixture()
        try:
            (root / HYPERFRAMES / "CLAUDE.md").write_text(
                "@AGENTS.md\nextra instruction\n", encoding="utf-8",
            )
            result = self.run_gate(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("nested HyperFrames CLAUDE.md", result.stderr)
        finally:
            shutil.rmtree(root)

    def test_missing_claude_import_fails(self):
        root = self.fixture()
        try:
            (root / "CLAUDE.md").unlink()
            result = self.run_gate(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CLAUDE.md", result.stderr)
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
