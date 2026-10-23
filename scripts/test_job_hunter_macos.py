import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class JobHunterMacTest(unittest.TestCase):
    def test_preflight_accepts_both_supported_mac_architectures(self):
        for cpu, system, expected in (("arm64", "Darwin", 0), ("x86_64", "Darwin", 0),
                                      ("ppc", "Darwin", 2), ("x86_64", "Linux", 2)):
            with self.subTest(cpu=cpu, system=system), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                tools = home / "bin"
                tools.mkdir()
                for name, text in {
                    "uname": f'if [ "$1" = -s ]; then echo {system}; else echo {cpu}; fi',
                    "codex": "exit 0", "python": "exit 0",
                    "df": "echo 'Filesystem 1024-blocks Used Available Capacity Mounted'; echo 'fixture 9000000 1 8999999 1% /'",
                }.items():
                    path = tools / name
                    path.write_text("#!/bin/sh\n" + text + "\n")
                    path.chmod(0o755)
                browser = home / ".cloakbrowser/chromium-fixture/Chromium.app/Contents/MacOS/Chromium"
                browser.parent.mkdir(parents=True)
                browser.touch()
                browser.chmod(0o755)
                result = subprocess.run([shutil.which("zsh"), str(ROOT / "apps/job-search-loop/scripts/install-oss.sh"), "preflight"],
                    env={**os.environ, "HOME": str(home), "PATH": f"{tools}:{os.environ['PATH']}",
                         "JOB_SEARCH_PYTHON": str(tools / "python")}, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], "ready" if expected == 0 else "blocked")

    def test_host_agent_configuration_survives_runtime_paths(self):
        result = subprocess.run([shutil.which("zsh"), "-c",
            'source "$1/apps/job-search-loop/scripts/runtime-paths.sh"; printf "%s" "$AGENT_RUNNER_CONFIG"',
            "fixture", str(ROOT)], env={**os.environ, "AGENT_RUNNER_CONFIG": "/own/agent-runner.json"},
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "/own/agent-runner.json")


if __name__ == "__main__":
    unittest.main()
