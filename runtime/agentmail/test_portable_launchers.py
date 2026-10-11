import unittest
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class PortableAgentmailLauncherTest(unittest.TestCase):
    def test_tick_output_inherits_managed_capture_without_private_log_growth(self):
        for name in ("nudge", "replier"):
            with self.subTest(wrapper=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                node = root / "node"
                node.write_text('#!/bin/sh\nprintf "node-out:%s\\n" "$1"\nprintf "node-err:%s\\n" "$1" >&2\nexit 7\n')
                node.chmod(0o700)
                env = {**os.environ, "HOME": str(root), "LIFE_MANAGER_ENV_FILE": str(root / "absent-env"),
                       "AGENTMAIL_STATE_ROOT": str(root / "state"), "NODE_BIN": str(node)}
                for _ in range(2):
                    result = subprocess.run(["bash", str(ROOT / f"runtime/agentmail/{name}-tick.sh")],
                                            env=env, capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 7)
                    self.assertIn(f"node-out:{name}.ts", result.stdout)
                    self.assertIn(f"node-err:{name}.ts", result.stderr)
                    self.assertFalse((root / f"state/logs/agentmail-{name}.log").exists())

    def test_agentmail_launchers_discover_node(self):
        for relative in (
            "runtime/agentmail/nudge-tick.sh",
            "runtime/agentmail/replier-tick.sh",
            "runtime/agentmail/launch.sh",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("command -v node", source, relative)
            self.assertIn('"status":"setup_required"', source, relative)
            self.assertNotIn("/opt/homebrew/bin/node", source, relative)


if __name__ == "__main__":
    unittest.main()
