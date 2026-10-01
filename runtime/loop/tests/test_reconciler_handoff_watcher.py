import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WATCHER = ROOT / "bin/reconcile-agent-handoff-watch.sh"


class ReconcilerHandoffWatcherTest(unittest.TestCase):
    def test_watcher_delegates_to_current_release_in_handoff_only_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "release"
            bin_dir = release / "bin"
            bin_dir.mkdir(parents=True)
            log = Path(directory) / "delegation.json"
            runner = bin_dir / "reconcile-agent-runner-release.sh"
            runner.write_text(
                "#!/bin/sh\n"
                "printf '%s|%s|%s' \"$LIFE_MANAGER_RELEASE_ROOT\" "
                "\"$LIFE_MANAGER_RECONCILER_HANDOFF_ONLY\" \"$LIFE_MANAGER_LOOP_ID\" "
                "> \"$WATCHER_TEST_LOG\"\n",
                encoding="utf-8",
            )
            runner.chmod(runner.stat().st_mode | stat.S_IEXEC)

            result = subprocess.run(
                ["/bin/bash", str(WATCHER)],
                env={
                    **os.environ,
                    "LIFE_MANAGER_RELEASE_ROOT": str(release),
                    "LIFE_MANAGER_LOOP_ID": "aa-release-reconciler-handoff",
                    "WATCHER_TEST_LOG": str(log),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                log.read_text(encoding="utf-8"),
                f"{release}|1|aa-release-reconciler-handoff",
            )


if __name__ == "__main__":
    unittest.main()
