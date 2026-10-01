import json
import os
import plistlib
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HANDOFF = ROOT / "bin/reconcile-agent-self-handoff.sh"
RUNNER = ROOT / "bin/reconcile-agent-runner-release.sh"
WATCHER_LABEL = "ai.anicca.life-manager-release-reconciler-handoff"


class ReconcilerSelfHandoffTest(unittest.TestCase):
    def test_runner_uses_a_distinct_helper_service_label(self):
        source = RUNNER.read_text(encoding="utf-8")
        match = re.search(r'local helper_label="([^"]+)"', source)
        self.assertIsNotNone(match, "runner must declare the helper service label")
        self.assertNotEqual(match.group(1), WATCHER_LABEL)

    def _fake_launchctl(self, root: Path) -> Path:
        script = root / "launchctl-safe"
        script.write_text(
            """#!/bin/sh
set -eu
state_file="$FAKE_LAUNCHD_STATE"
log_file="$FAKE_LAUNCHD_LOG"
printf '%s\n' "$*" >> "$log_file"
case "${1:-}" in
  preflight)
    exit 0
    ;;
  print)
    service="$2"
    state="$(cat "$state_file")"
    case "$service:$state" in
      gui/*/ai.anicca.life-manager-release-reconciler:old)
        printf 'state = running\n'
        exit 0
        ;;
      gui/*/ai.anicca.life-manager-release-reconciler:target)
        printf 'arguments = {\n'
        printf '  /target/bin/lm-loop-run\n'
        printf '  life-manager-release-reconciler\n'
        printf '  /target\n'
        printf '}\n'
        printf 'environment = {\n'
        printf '  LIFE_MANAGER_RELEASE_SHA => 0123456789012345678901234567890123456789\n'
        printf '}\n'
        exit 0
        ;;
    esac
    printf 'Could not find service\n' >&2
    exit 113
    ;;
  bootout)
    service="$2"
    case "$service" in
      gui/*/ai.anicca.life-manager-release-reconciler)
        printf 'absent' > "$state_file"
        ;;
      gui/*/ai.anicca.life-manager-release-reconciler-self-handoff)
        printf 'helper-absent' > "$state_file.helper"
        ;;
    esac
    exit 0
    ;;
  bootstrap)
    printf 'target' > "$state_file"
    exit 0
    ;;
esac
exit 64
""",
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return script

    def test_handoff_waits_for_parent_then_bootstraps_target_and_records_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_launchctl = self._fake_launchctl(root)
            state_file = root / "launchd-state"
            state_file.write_text("old", encoding="utf-8")
            log_file = root / "launchd.log"
            handoff_plist = root / "self-handoff.plist"
            handoff_plist.write_bytes(
                plistlib.dumps({
                    "Label": "ai.anicca.life-manager-release-reconciler-self-handoff",
                    "ProgramArguments": [str(HANDOFF)],
                })
            )
            target_plist = root / "target.plist"
            target_plist.write_bytes(
                plistlib.dumps({
                    "Label": "ai.anicca.life-manager-release-reconciler",
                    "ProgramArguments": [
                        "/target/bin/lm-loop-run",
                        "life-manager-release-reconciler",
                        "/target",
                    ],
                    "EnvironmentVariables": {
                        "LIFE_MANAGER_RELEASE_SHA": "0123456789012345678901234567890123456789",
                    },
                })
            )
            receipt = root / "self-handoff-receipt.json"
            parent = subprocess.Popen(["/usr/bin/true"])
            parent_pid = str(parent.pid)
            self.assertEqual(parent.wait(), 0)

            env = {
                **os.environ,
                "FAKE_LAUNCHD_STATE": str(state_file),
                "FAKE_LAUNCHD_LOG": str(log_file),
                "LIFE_MANAGER_RUNTIME_PYTHON": os.environ.get("PYTHON", "python3"),
            }
            result = subprocess.run(
                [
                    "/bin/bash",
                    str(HANDOFF),
                    "--parent-pid", parent_pid,
                    "--old-service", "ai.anicca.life-manager-release-reconciler",
                    "--helper-service", "ai.anicca.life-manager-release-reconciler-self-handoff",
                    "--target-plist", str(target_plist),
                    "--handoff-plist", str(handoff_plist),
                    "--receipt", str(receipt),
                    "--launchctl", str(fake_launchctl),
                ],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "ok")
            self.assertEqual(evidence["target_release_sha"],
                             "0123456789012345678901234567890123456789")
            self.assertEqual(evidence["readback"]["loaded_arguments"], [
                "/target/bin/lm-loop-run",
                "life-manager-release-reconciler",
                "/target",
            ])
            self.assertEqual(state_file.read_text(encoding="utf-8"), "target")
            self.assertFalse(handoff_plist.exists())
            commands = log_file.read_text(encoding="utf-8").splitlines()
            self.assertLess(
                next(i for i, row in enumerate(commands) if row.startswith("bootout ")),
                next(i for i, row in enumerate(commands) if row.startswith("bootstrap ")),
            )

    def test_handoff_does_not_mutate_launchd_when_parent_does_not_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_launchctl = self._fake_launchctl(root)
            state_file = root / "launchd-state"
            state_file.write_text("old", encoding="utf-8")
            log_file = root / "launchd.log"
            handoff_plist = root / "self-handoff.plist"
            target_plist = root / "target.plist"
            target_plist.write_bytes(plistlib.dumps({
                "Label": "ai.anicca.life-manager-release-reconciler",
                "ProgramArguments": ["/target/bin/lm-loop-run", "life-manager-release-reconciler", "/target"],
                "EnvironmentVariables": {
                    "LIFE_MANAGER_RELEASE_SHA": "0123456789012345678901234567890123456789",
                },
            }))
            receipt = root / "self-handoff-receipt.json"
            parent = subprocess.Popen(["/bin/sleep", "5"])
            try:
                env = {
                    **os.environ,
                    "FAKE_LAUNCHD_STATE": str(state_file),
                    "FAKE_LAUNCHD_LOG": str(log_file),
                    "LIFE_MANAGER_SELF_HANDOFF_WAIT_SECONDS": "0",
                }
                result = subprocess.run(
                    [
                        "/bin/bash", str(HANDOFF),
                        "--parent-pid", str(parent.pid),
                        "--old-service", "ai.anicca.life-manager-release-reconciler",
                        "--helper-service", "ai.anicca.life-manager-release-reconciler-self-handoff",
                        "--target-plist", str(target_plist),
                        "--handoff-plist", str(handoff_plist),
                        "--receipt", str(receipt),
                        "--launchctl", str(fake_launchctl),
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            finally:
                parent.terminate()
                parent.wait()

            self.assertEqual(result.returncode, 75, result.stderr)
            evidence = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "failed")
            self.assertEqual(evidence["error"], "parent_timeout")
            self.assertEqual(state_file.read_text(encoding="utf-8"), "old")
            self.assertFalse(log_file.exists(), "launchd must not be touched before parent exit")


if __name__ == "__main__":
    unittest.main()
