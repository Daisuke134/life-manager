#!/usr/bin/env python3
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HEALTHCHECK = ROOT / "skills" / "self" / "capafy-loop" / "capafy-loop-healthcheck.sh"


class CapafyHealthcheckQuotaBackoffTest(unittest.TestCase):
    def install_test_release(self, root, lifecycle_returncode=0):
        release_root = root / "release"
        healthcheck = release_root / "skills" / "self" / "capafy-loop" / "capafy-loop-healthcheck.sh"
        healthcheck.parent.mkdir(parents=True)
        healthcheck.write_text(HEALTHCHECK.read_text(encoding="utf-8"), encoding="utf-8")
        key_gate = release_root / "skills" / "capafy-autopublish" / "scripts" / "key_health_gate.sh"
        key_gate.parent.mkdir(parents=True)
        key_gate.write_text(
            "#!/bin/sh\nprintf '%s\\n' gate >> \"$CAPAFY_TEST_KEY_GATE_CALLS\"\nexit \"$CAPAFY_TEST_KEY_GATE_RC\"\n",
            encoding="utf-8",
        )
        key_gate.chmod(0o755)
        lifecycle_calls = root / "lm-loop-calls"
        control = release_root / "bin" / "lm-loop"
        control.parent.mkdir(parents=True)
        control.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$CAPAFY_TEST_LM_LOOP_CALLS\"\n"
            "exit \"$CAPAFY_TEST_LM_LOOP_RC\"\n",
            encoding="utf-8",
        )
        control.chmod(0o755)
        return healthcheck, lifecycle_calls, lifecycle_returncode

    def run_stale_owner_healthcheck(self, lifecycle_returncode=0, launchctl_output="",
                                    terminal_event=None, key_gate_returncode=0):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_home = root / "state-home"
            marker = state_home / "state" / "capafy-autopublish" / ".capafy-healthy-pass"
            marker.parent.mkdir(parents=True)
            marker.touch()
            stale = time.time() - (31 * 60 * 60)
            os.utime(marker, (stale, stale))
            if terminal_event is not None:
                (state_home / "events.jsonl").write_text(
                    json.dumps(terminal_event) + "\n", encoding="utf-8")

            healthcheck, lifecycle_calls, lifecycle_returncode = self.install_test_release(
                root, lifecycle_returncode)
            calls = root / "launchctl-calls"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            launchctl = fake_bin / "launchctl"
            launchctl.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$CAPAFY_TEST_CALLS\"\n"
                "[ \"$1\" != print ] || printf '%s\\n' \"$CAPAFY_TEST_LAUNCHCTL_OUTPUT\"\n"
                "exit 0\n",
                encoding="utf-8",
            )
            launchctl.chmod(0o755)

            env = os.environ | {
                "LIFE_MANAGER_STATE_HOME": str(state_home),
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "CAPAFY_TEST_CALLS": str(calls),
                "CAPAFY_TEST_LM_LOOP_CALLS": str(lifecycle_calls),
                "CAPAFY_TEST_LM_LOOP_RC": str(lifecycle_returncode),
                "CAPAFY_TEST_LAUNCHCTL_OUTPUT": launchctl_output,
                "CAPAFY_TEST_KEY_GATE_CALLS": str(root / "key-gate-calls"),
                "CAPAFY_TEST_KEY_GATE_RC": str(key_gate_returncode),
            }
            result = subprocess.run(
                ["bash", str(healthcheck)], env=env, text=True, capture_output=True, check=False
            )
            recorded = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
            lifecycle = lifecycle_calls.read_text(encoding="utf-8").splitlines() if lifecycle_calls.exists() else []
            log_path = state_home / "logs" / "capafy-loop-healthcheck.log"
            log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
            return result, recorded, lifecycle, log

    def run_healthcheck(self, error_class, incomplete_name, expected_return=0,
                        incomplete_lane="capafy-marketplace"):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_home = root / "state-home"
            marker = state_home / "state" / "capafy-autopublish" / ".capafy-healthy-pass"
            marker.parent.mkdir(parents=True)
            marker.touch()
            stale = time.time() - (31 * 60 * 60)
            os.utime(marker, (stale, stale))

            evidence = state_home / "state" / "agent-runner-evidence" / "capafy-marketplace" / "100-1"
            evidence.mkdir(parents=True)
            (evidence / "summary.json").write_text(
                json.dumps({"status": "failed", "finished_at": "2026-08-24T00:00:00Z"}),
                encoding="utf-8",
            )
            (evidence / "attempts.jsonl").write_text(
                json.dumps({"provider": "codex", "error_class": error_class}) + "\n",
                encoding="utf-8",
            )
            incomplete = state_home / "state" / "agent-runner-evidence" / incomplete_lane / incomplete_name
            incomplete.mkdir(parents=True)

            healthcheck, lifecycle_calls, _ = self.install_test_release(root)
            calls = root / "launchctl-calls"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            launchctl = fake_bin / "launchctl"
            launchctl.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CAPAFY_TEST_CALLS\"\nexit 0\n",
                encoding="utf-8",
            )
            launchctl.chmod(0o755)

            env = os.environ | {
                "LIFE_MANAGER_STATE_HOME": str(state_home),
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "CAPAFY_TEST_CALLS": str(calls),
                "CAPAFY_TEST_LM_LOOP_CALLS": str(lifecycle_calls),
                "CAPAFY_TEST_LM_LOOP_RC": "0",
                "CAPAFY_TEST_KEY_GATE_CALLS": str(root / "key-gate-calls"),
                "CAPAFY_TEST_KEY_GATE_RC": "0",
            }
            result = subprocess.run(
                ["bash", str(healthcheck)], env=env, text=True, capture_output=True, check=False
            )

            self.assertEqual(result.returncode, expected_return, result.stderr)
            recorded = calls.read_text(encoding="utf-8")
            lifecycle = lifecycle_calls.read_text(encoding="utf-8").splitlines() if lifecycle_calls.exists() else []
            receipt_path = state_home / "state" / "capafy-provider-backoff.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else None
            return recorded, receipt, lifecycle

    def test_stale_marker_with_quota_does_not_kickstart(self):
            recorded, receipt, lifecycle = self.run_healthcheck("transient_quota", "101-2")
            self.assertNotIn("kickstart", recorded)
            self.assertEqual(lifecycle, [])
            self.assertEqual(receipt["error_class"], "transient_quota")
            self.assertGreater(receipt["next_eligible_at_epoch"], int(time.time()))

    def test_recent_incomplete_attempt_gets_grace_without_kickstart(self):
            recorded, _, lifecycle = self.run_healthcheck("transient_unavailable", f"{int(time.time())}-2")
            self.assertNotIn("kickstart", recorded)
            self.assertEqual(lifecycle, [])

    def test_recent_offline_build_gets_grace_without_restart(self):
            recorded, _, lifecycle = self.run_healthcheck(
                "transient_unavailable", f"{int(time.time())}-2",
                incomplete_lane="capafy-offline-build")
            self.assertNotIn("kickstart", recorded)
            self.assertEqual(lifecycle, [])

    def test_stale_nonquota_receipt_restarts_once_via_lm_loop(self):
            recorded, _, lifecycle = self.run_healthcheck(
                "transient_unavailable", "101-2", expected_return=0)
            self.assertNotIn("kickstart", recorded)
            self.assertEqual(lifecycle, ["restart capafy-loop-daily"])

    def test_stale_owner_without_attempt_or_quota_restarts_once_and_records_success(self):
            result, recorded, lifecycle, log = self.run_stale_owner_healthcheck()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("kickstart", recorded)
            self.assertEqual(lifecycle, ["restart capafy-loop-daily"])
            self.assertIn("restarted ai.anicca.capafy-loop-daily", log)

    def test_stale_owner_does_not_record_success_when_lm_loop_restart_fails(self):
            result, recorded, lifecycle, log = self.run_stale_owner_healthcheck(lifecycle_returncode=17)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertNotIn("kickstart", recorded)
            self.assertEqual(lifecycle, ["restart capafy-loop-daily"])
            self.assertNotIn("restarted ai.anicca.capafy-loop-daily", log)
            self.assertIn("failed to restart ai.anicca.capafy-loop-daily", log)

    def test_provider_gate_failure_never_restarts_owner(self):
            result, recorded, lifecycle, log = self.run_stale_owner_healthcheck(
                key_gate_returncode=1
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(recorded, [])
            self.assertEqual(lifecycle, [])
            self.assertIn("provider admission unhealthy; no owner restart", log)

    def test_fresh_success_terminal_does_not_restart_for_stale_marker(self):
            now = time.time()
            result, recorded, lifecycle, _ = self.run_stale_owner_healthcheck(
                launchctl_output="last exit code = 0",
                terminal_event={
                    "loop_id": "capafy-loop-daily",
                    "phase": "report",
                    "status": "pass",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(any(row.startswith("print ") for row in recorded), recorded)
            self.assertEqual(lifecycle, [])


if __name__ == "__main__":
    unittest.main()
