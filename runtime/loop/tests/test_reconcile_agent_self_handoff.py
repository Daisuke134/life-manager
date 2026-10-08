import fcntl
import json
import os
import plistlib
import re
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from runtime.loop.lm_loop import _label_apply_lock_path


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
service_active() {
  if [ -n "${FAKE_ACTIVE_UNTIL_EPOCH:-}" ]; then
    [ "$(date +%s)" -lt "$FAKE_ACTIVE_UNTIL_EPOCH" ]
  else
    [ -n "${FAKE_ACTIVE_SERVICE_PID:-}" ] \
      && kill -0 "$FAKE_ACTIVE_SERVICE_PID" 2>/dev/null
  fi
}
printf '%s\n' "$*" >> "$log_file"
case "${1:-}" in
  preflight)
    exit 0
    ;;
  print)
    service="$2"
    state="$(cat "$state_file")"
    case "$service:$state" in
      gui/*/ai.anicca.life-manager-release-reconciler:not_running)
        printf 'state = not running\n'
        exit 0
        ;;
      gui/*/ai.anicca.life-manager-release-reconciler:waiting_then_not_running)
        reads_file="${state_file}.reads"
        reads="$(cat "$reads_file" 2>/dev/null || printf '0')"
        reads=$((reads + 1))
        printf '%s' "$reads" > "$reads_file"
        if [ "$reads" -eq 1 ]; then
          printf 'state = waiting\n'
        else
          printf 'state = not running\n'
        fi
        exit 0
        ;;
      gui/*/ai.anicca.life-manager-release-reconciler:not_running_pid)
        printf 'state = not running\n'
        printf 'pid = 42\n'
        exit 0
        ;;
      gui/*/ai.anicca.life-manager-release-reconciler:unknown)
        printf 'state = bootstrapping\n'
        exit 0
        ;;
      gui/*/ai.anicca.life-manager-release-reconciler:old)
        if service_active; then
          printf 'state = running\n'
          printf 'pid = %s\n' "$FAKE_ACTIVE_SERVICE_PID"
        else
          printf 'state = waiting\n'
        fi
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
        if service_active; then
          printf 'bootout_while_active\n' >> "$log_file"
        fi
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

    def _run_handoff_fixture(self, root: Path, launchd_state: str):
        home = root / "home"
        (home / "loops").mkdir(parents=True)
        label = "ai.anicca.life-manager-release-reconciler"
        fake_launchctl = self._fake_launchctl(root)
        state_file = root / "launchd-state"
        state_file.write_text(launchd_state, encoding="utf-8")
        log_file = root / "launchd.log"
        handoff_plist = root / "self-handoff.plist"
        handoff_plist.write_bytes(plistlib.dumps({
            "Label": "ai.anicca.life-manager-release-reconciler-self-handoff",
            "ProgramArguments": [str(HANDOFF)],
        }))
        target_plist = root / "target.plist"
        target_plist.write_bytes(plistlib.dumps({
            "Label": label,
            "ProgramArguments": [
                "/target/bin/lm-loop-run",
                "life-manager-release-reconciler",
                "/target",
            ],
            "EnvironmentVariables": {
                "LIFE_MANAGER_RELEASE_SHA": "0123456789012345678901234567890123456789",
            },
        }))
        receipt = root / "self-handoff-receipt.json"
        watcher_parent = subprocess.Popen(["/usr/bin/true"])
        watcher_pid = str(watcher_parent.pid)
        self.assertEqual(watcher_parent.wait(), 0)
        env = {
            **os.environ,
            "HOME": str(home),
            "TMPDIR": str(root),
            "PYTHONPATH": str(ROOT),
            "FAKE_LAUNCHD_STATE": str(state_file),
            "FAKE_LAUNCHD_LOG": str(log_file),
            "LIFE_MANAGER_RUNTIME_PYTHON": os.environ.get("PYTHON", "python3"),
            "LIFE_MANAGER_RECONCILER_HANDOFF_LOCK_WAIT_SECONDS": "5",
        }
        result = subprocess.run(
            [
                "/bin/bash", str(HANDOFF),
                "--parent-pid", watcher_pid,
                "--old-service", label,
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
        evidence = json.loads(receipt.read_text(encoding="utf-8"))
        commands = log_file.read_text(encoding="utf-8").splitlines()
        return result, evidence, commands, state_file, target_plist

    def test_handoff_accepts_not_running_old_service_without_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, evidence, commands, state_file, target_plist = self._run_handoff_fixture(
                root, "not_running",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(evidence["status"], "ok")
            self.assertEqual(evidence["old_service_state"], "not running")
            self.assertEqual(evidence["target_release_sha"],
                             "0123456789012345678901234567890123456789")
            domain = f"gui/{os.getuid()}"
            old_service = f"{domain}/ai.anicca.life-manager-release-reconciler"
            bootout_index = commands.index(f"bootout {old_service}")
            self.assertGreaterEqual(
                sum(command == f"print {old_service}" for command in commands[:bootout_index]),
                2,
            )
            self.assertIn(f"bootstrap {domain} {target_plist}", commands)
            self.assertEqual(state_file.read_text(encoding="utf-8"), "target")

    def test_handoff_fails_closed_when_not_running_has_pid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, evidence, commands, _, _ = self._run_handoff_fixture(root, "not_running_pid")
            self.assertEqual(result.returncode, 69, result.stderr)
            self.assertEqual(evidence["error"], "old_service_not_running_pid_present")
            self.assertEqual(evidence["old_service_state"], "not running")
            domain = f"gui/{os.getuid()}"
            self.assertNotIn(
                f"bootout {domain}/ai.anicca.life-manager-release-reconciler",
                commands,
            )

    def test_handoff_requires_two_consecutive_not_running_observations_after_waiting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result, evidence, commands, _, _ = self._run_handoff_fixture(
                root, "waiting_then_not_running",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(evidence["status"], "ok")
            self.assertEqual(evidence["old_service_state"], "not running")
            domain = f"gui/{os.getuid()}"
            old_service = f"{domain}/ai.anicca.life-manager-release-reconciler"
            bootout_index = commands.index(f"bootout {old_service}")
            self.assertGreaterEqual(
                sum(command == f"print {old_service}" for command in commands[:bootout_index]),
                3,
            )

    def test_handoff_waits_for_parent_then_bootstraps_target_and_records_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / "loops").mkdir(parents=True)
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
                "HOME": str(home),
                "TMPDIR": str(root),
                "PYTHONPATH": str(ROOT),
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

    def test_handoff_waits_for_active_old_service_after_watcher_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / "loops").mkdir(parents=True)
            fake_launchctl = self._fake_launchctl(root)
            state_file = root / "launchd-state"
            state_file.write_text("old", encoding="utf-8")
            log_file = root / "launchd.log"
            handoff_plist = root / "self-handoff.plist"
            handoff_plist.write_bytes(plistlib.dumps({
                "Label": "ai.anicca.life-manager-release-reconciler-self-handoff",
                "ProgramArguments": [str(HANDOFF)],
            }))
            target_plist = root / "target.plist"
            target_plist.write_bytes(plistlib.dumps({
                "Label": "ai.anicca.life-manager-release-reconciler",
                "ProgramArguments": ["/target/bin/lm-loop-run", "life-manager-release-reconciler", "/target"],
                "EnvironmentVariables": {
                    "LIFE_MANAGER_RELEASE_SHA": "0123456789012345678901234567890123456789",
                },
            }))
            receipt = root / "self-handoff-receipt.json"
            watcher_parent = subprocess.Popen(["/usr/bin/true"])
            watcher_pid = str(watcher_parent.pid)
            self.assertEqual(watcher_parent.wait(), 0)
            active_until = str(int(time.time()) + 2)

            env = {
                **os.environ,
                "HOME": str(home),
                "TMPDIR": str(root),
                "PYTHONPATH": str(ROOT),
                "FAKE_LAUNCHD_STATE": str(state_file),
                "FAKE_LAUNCHD_LOG": str(log_file),
                "FAKE_ACTIVE_SERVICE_PID": str(os.getpid()),
                "FAKE_ACTIVE_UNTIL_EPOCH": active_until,
                "LIFE_MANAGER_RUNTIME_PYTHON": os.environ.get("PYTHON", "python3"),
                "LIFE_MANAGER_SELF_HANDOFF_WAIT_SECONDS": "5",
            }
            started_at = time.monotonic()
            result = subprocess.run(
                [
                    "/bin/bash", str(HANDOFF),
                    "--parent-pid", watcher_pid,
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
            elapsed = time.monotonic() - started_at

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreaterEqual(elapsed, 1.0)
            self.assertNotIn("bootout_while_active", log_file.read_text().splitlines())
            evidence = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "ok")

    def test_handoff_fails_closed_if_active_old_service_exceeds_wait_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / "loops").mkdir(parents=True)
            fake_launchctl = self._fake_launchctl(root)
            state_file = root / "launchd-state"
            state_file.write_text("old", encoding="utf-8")
            log_file = root / "launchd.log"
            handoff_plist = root / "self-handoff.plist"
            handoff_plist.write_bytes(plistlib.dumps({
                "Label": "ai.anicca.life-manager-release-reconciler-self-handoff",
                "ProgramArguments": [str(HANDOFF)],
            }))
            target_plist = root / "target.plist"
            target_plist.write_bytes(plistlib.dumps({
                "Label": "ai.anicca.life-manager-release-reconciler",
                "ProgramArguments": ["/target/bin/lm-loop-run", "life-manager-release-reconciler", "/target"],
                "EnvironmentVariables": {
                    "LIFE_MANAGER_RELEASE_SHA": "0123456789012345678901234567890123456789",
                },
            }))
            receipt = root / "self-handoff-receipt.json"
            watcher_parent = subprocess.Popen(["/usr/bin/true"])
            watcher_pid = str(watcher_parent.pid)
            self.assertEqual(watcher_parent.wait(), 0)
            active_until = str(int(time.time()) + 5)

            env = {
                **os.environ,
                "HOME": str(home),
                "TMPDIR": str(root),
                "PYTHONPATH": str(ROOT),
                "FAKE_LAUNCHD_STATE": str(state_file),
                "FAKE_LAUNCHD_LOG": str(log_file),
                "FAKE_ACTIVE_SERVICE_PID": str(os.getpid()),
                "FAKE_ACTIVE_UNTIL_EPOCH": active_until,
                "LIFE_MANAGER_RUNTIME_PYTHON": os.environ.get("PYTHON", "python3"),
                "LIFE_MANAGER_SELF_HANDOFF_WAIT_SECONDS": "1",
            }
            result = subprocess.run(
                [
                    "/bin/bash", str(HANDOFF),
                    "--parent-pid", watcher_pid,
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

            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertNotIn(
                "bootout gui/501/ai.anicca.life-manager-release-reconciler",
                log_file.read_text(encoding="utf-8").splitlines(),
            )
            self.assertIn(
                "bootout gui/501/ai.anicca.life-manager-release-reconciler-self-handoff",
                log_file.read_text(encoding="utf-8").splitlines(),
            )
            evidence = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "failed")
            self.assertEqual(evidence["error"], "old_service_active_timeout")

    def test_handoff_waits_for_the_existing_reconciler_run_lock_before_bootout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / "loops").mkdir(parents=True)
            label = "ai.anicca.life-manager-release-reconciler"
            lock_path = _label_apply_lock_path(home / "loops/current", label)
            lock_path.parent.mkdir(parents=True)
            lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fake_launchctl = self._fake_launchctl(root)
            state_file = root / "launchd-state"
            state_file.write_text("old", encoding="utf-8")
            log_file = root / "launchd.log"
            handoff_plist = root / "self-handoff.plist"
            handoff_plist.write_bytes(plistlib.dumps({
                "Label": "ai.anicca.life-manager-release-reconciler-self-handoff",
                "ProgramArguments": [str(HANDOFF)],
            }))
            target_plist = root / "target.plist"
            target_plist.write_bytes(plistlib.dumps({
                "Label": label,
                "ProgramArguments": ["/target/bin/lm-loop-run", "life-manager-release-reconciler", "/target"],
                "EnvironmentVariables": {
                    "LIFE_MANAGER_RELEASE_SHA": "0123456789012345678901234567890123456789",
                },
            }))
            receipt = root / "self-handoff-receipt.json"
            watcher_parent = subprocess.Popen(["/usr/bin/true"])
            watcher_pid = str(watcher_parent.pid)
            self.assertEqual(watcher_parent.wait(), 0)
            env = {
                **os.environ,
                "HOME": str(home),
                "TMPDIR": str(root),
                "PYTHONPATH": str(ROOT),
                "FAKE_LAUNCHD_STATE": str(state_file),
                "FAKE_LAUNCHD_LOG": str(log_file),
                "LIFE_MANAGER_RUNTIME_PYTHON": os.environ.get("PYTHON", "python3"),
                "LIFE_MANAGER_RECONCILER_HANDOFF_LOCK_WAIT_SECONDS": "5",
            }
            process = subprocess.Popen(
                [
                    "/bin/bash", str(HANDOFF),
                    "--parent-pid", watcher_pid,
                    "--old-service", label,
                    "--helper-service", "ai.anicca.life-manager-release-reconciler-self-handoff",
                    "--target-plist", str(target_plist),
                    "--handoff-plist", str(handoff_plist),
                    "--receipt", str(receipt),
                    "--launchctl", str(fake_launchctl),
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 2
                commands = []
                while time.monotonic() < deadline:
                    if log_file.exists():
                        commands = log_file.read_text(encoding="utf-8").splitlines()
                    if process.poll() is not None or len(commands) > 1:
                        break
                    time.sleep(0.05)
                if log_file.exists():
                    commands = log_file.read_text(encoding="utf-8").splitlines()
                still_waiting = process.poll() is None
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(commands, ["preflight"])
            self.assertTrue(still_waiting, "handoff must wait while the owner run holds its lock")
            self.assertEqual(process.returncode, 0, f"{stdout}\n{stderr}")
            evidence = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "ok")
            self.assertEqual(evidence["run_lock"]["status"], "acquired")
            self.assertEqual(evidence["old_service_state"], "waiting")
            commands = log_file.read_text(encoding="utf-8").splitlines()
            domain = f"gui/{os.getuid()}"
            self.assertLess(commands.index(f"bootout {domain}/{label}"),
                            commands.index(f"bootstrap {domain} {target_plist}"))

    def test_handoff_leaves_old_service_loaded_when_run_lock_wait_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / "loops").mkdir(parents=True)
            label = "ai.anicca.life-manager-release-reconciler"
            lock_path = _label_apply_lock_path(home / "loops/current", label)
            lock_path.parent.mkdir(parents=True)
            lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fake_launchctl = self._fake_launchctl(root)
            state_file = root / "launchd-state"
            state_file.write_text("old", encoding="utf-8")
            log_file = root / "launchd.log"
            handoff_plist = root / "self-handoff.plist"
            handoff_plist.write_bytes(plistlib.dumps({
                "Label": "ai.anicca.life-manager-release-reconciler-self-handoff",
                "ProgramArguments": [str(HANDOFF)],
            }))
            target_plist = root / "target.plist"
            target_plist.write_bytes(plistlib.dumps({
                "Label": label,
                "ProgramArguments": ["/target/bin/lm-loop-run", "life-manager-release-reconciler", "/target"],
                "EnvironmentVariables": {
                    "LIFE_MANAGER_RELEASE_SHA": "0123456789012345678901234567890123456789",
                },
            }))
            receipt = root / "self-handoff-receipt.json"
            watcher_parent = subprocess.Popen(["/usr/bin/true"])
            watcher_pid = str(watcher_parent.pid)
            self.assertEqual(watcher_parent.wait(), 0)
            env = {
                **os.environ,
                "HOME": str(home),
                "TMPDIR": str(root),
                "PYTHONPATH": str(ROOT),
                "FAKE_LAUNCHD_STATE": str(state_file),
                "FAKE_LAUNCHD_LOG": str(log_file),
                "LIFE_MANAGER_RUNTIME_PYTHON": os.environ.get("PYTHON", "python3"),
                "LIFE_MANAGER_RECONCILER_HANDOFF_LOCK_WAIT_SECONDS": "1",
            }
            try:
                result = subprocess.run(
                    [
                        "/bin/bash", str(HANDOFF),
                        "--parent-pid", watcher_pid,
                        "--old-service", label,
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
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)

            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertEqual(state_file.read_text(encoding="utf-8"), "old")
            commands = log_file.read_text(encoding="utf-8").splitlines()
            domain = f"gui/{os.getuid()}"
            self.assertNotIn(f"bootout {domain}/{label}", commands)
            self.assertIn(f"bootout {domain}/ai.anicca.life-manager-release-reconciler-self-handoff", commands)
            evidence = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(evidence["error"], "handoff_run_lock_timeout")
            self.assertEqual(evidence["run_lock"]["status"], "timeout")

    def test_handoff_bootstraps_target_when_old_service_is_already_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / "loops").mkdir(parents=True)
            label = "ai.anicca.life-manager-release-reconciler"
            fake_launchctl = self._fake_launchctl(root)
            state_file = root / "launchd-state"
            state_file.write_text("absent", encoding="utf-8")
            log_file = root / "launchd.log"
            handoff_plist = root / "self-handoff.plist"
            handoff_plist.write_bytes(plistlib.dumps({
                "Label": "ai.anicca.life-manager-release-reconciler-self-handoff",
                "ProgramArguments": [str(HANDOFF)],
            }))
            target_plist = root / "target.plist"
            target_plist.write_bytes(plistlib.dumps({
                "Label": label,
                "ProgramArguments": ["/target/bin/lm-loop-run", "life-manager-release-reconciler", "/target"],
                "EnvironmentVariables": {
                    "LIFE_MANAGER_RELEASE_SHA": "0123456789012345678901234567890123456789",
                },
            }))
            receipt = root / "self-handoff-receipt.json"
            watcher_parent = subprocess.Popen(["/usr/bin/true"])
            watcher_pid = str(watcher_parent.pid)
            self.assertEqual(watcher_parent.wait(), 0)
            env = {
                **os.environ,
                "HOME": str(home),
                "TMPDIR": str(root),
                "PYTHONPATH": str(ROOT),
                "FAKE_LAUNCHD_STATE": str(state_file),
                "FAKE_LAUNCHD_LOG": str(log_file),
                "LIFE_MANAGER_RUNTIME_PYTHON": os.environ.get("PYTHON", "python3"),
                "LIFE_MANAGER_RECONCILER_HANDOFF_LOCK_WAIT_SECONDS": "5",
            }
            result = subprocess.run(
                [
                    "/bin/bash", str(HANDOFF),
                    "--parent-pid", watcher_pid,
                    "--old-service", label,
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
            self.assertEqual(evidence["old_service_state"], "not_loaded")
            self.assertEqual(evidence["readback"]["loaded_release_sha"],
                             "0123456789012345678901234567890123456789")
            commands = log_file.read_text(encoding="utf-8").splitlines()
            domain = f"gui/{os.getuid()}"
            self.assertNotIn(f"bootout {domain}/{label}", commands)
            self.assertIn(f"bootstrap {domain} {target_plist}", commands)

    def test_handoff_fails_closed_on_unknown_old_service_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / "loops").mkdir(parents=True)
            label = "ai.anicca.life-manager-release-reconciler"
            fake_launchctl = self._fake_launchctl(root)
            state_file = root / "launchd-state"
            state_file.write_text("unknown", encoding="utf-8")
            log_file = root / "launchd.log"
            handoff_plist = root / "self-handoff.plist"
            handoff_plist.write_bytes(plistlib.dumps({
                "Label": "ai.anicca.life-manager-release-reconciler-self-handoff",
                "ProgramArguments": [str(HANDOFF)],
            }))
            target_plist = root / "target.plist"
            target_plist.write_bytes(plistlib.dumps({
                "Label": label,
                "ProgramArguments": ["/target/bin/lm-loop-run", "life-manager-release-reconciler", "/target"],
                "EnvironmentVariables": {
                    "LIFE_MANAGER_RELEASE_SHA": "0123456789012345678901234567890123456789",
                },
            }))
            receipt = root / "self-handoff-receipt.json"
            watcher_parent = subprocess.Popen(["/usr/bin/true"])
            watcher_pid = str(watcher_parent.pid)
            self.assertEqual(watcher_parent.wait(), 0)
            env = {
                **os.environ,
                "HOME": str(home),
                "TMPDIR": str(root),
                "PYTHONPATH": str(ROOT),
                "FAKE_LAUNCHD_STATE": str(state_file),
                "FAKE_LAUNCHD_LOG": str(log_file),
                "LIFE_MANAGER_RUNTIME_PYTHON": os.environ.get("PYTHON", "python3"),
                "LIFE_MANAGER_RECONCILER_HANDOFF_LOCK_WAIT_SECONDS": "5",
            }
            result = subprocess.run(
                [
                    "/bin/bash", str(HANDOFF),
                    "--parent-pid", watcher_pid,
                    "--old-service", label,
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
            self.assertEqual(result.returncode, 69, result.stderr)
            self.assertEqual(state_file.read_text(encoding="utf-8"), "unknown")
            evidence = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(evidence["error"], "old_service_state_unknown")
            self.assertEqual(evidence["old_service_state"], "bootstrapping")
            self.assertEqual(evidence["run_lock"]["status"], "acquired")
            commands = log_file.read_text(encoding="utf-8").splitlines()
            domain = f"gui/{os.getuid()}"
            self.assertNotIn(f"bootout {domain}/{label}", commands)
            self.assertIn(
                f"bootout {domain}/ai.anicca.life-manager-release-reconciler-self-handoff",
                commands,
            )

    def test_handoff_does_not_mutate_launchd_when_parent_does_not_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / "loops").mkdir(parents=True)
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
                    "HOME": str(home),
                    "TMPDIR": str(root),
                    "PYTHONPATH": str(ROOT),
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
