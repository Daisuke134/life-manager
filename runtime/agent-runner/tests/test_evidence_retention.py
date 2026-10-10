import os
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_runner import ensure_evidence_capacity, reclaim_completed_evidence
import agent_runner as runner


class EvidenceRetentionTest(unittest.TestCase):
    def test_registered_flat_evidence_prunes_only_closed_unsealed_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            state = base / "state"
            root = base / "writer/agent-runner-evidence"
            config = base / "repo/config"
            config.mkdir(parents=True)
            owner = "capafy-distribute-daily"
            policy = json.loads((runner.REPO_ROOT / "config/storage-policy.json").read_text())
            policy["defaults"]["owner_diagnostic_retained_bytes"] = 64
            policy["defaults"]["host_diagnostic_retained_bytes"] = 64
            (config / "storage-policy.json").write_text(json.dumps(policy))
            (config / "loop-registry.json").write_text(json.dumps({"loops": {owner: {"state_root": str(state)}}}))
            primaries = ("result.json", "usage.json", "attempts.jsonl")
            captures = {}
            for kind in ("current", "sealed", "dangling-seal", "foreign-owner", "receipt-mismatch", "active"):
                run = root / f"agent-{kind}"
                relay = run / "attempt-01.capture/stdout"
                relay.mkdir(parents=True, mode=0o700)
                binding = {"owner_id": owner if kind != "foreign-owner" else "other-owner",
                    "run_id": run.name, "occurrence_id": f"{owner}:{run.name}", "release_sha": "a" * 40}
                marker = relay / ".lm-regenerable"
                marker.write_text(json.dumps({"role": "diagnostic_only", "binding": binding}))
                marker.chmod(0o600)
                receipt_binding = binding if kind != "receipt-mismatch" else {**binding, "run_id": "other-run"}
                (relay / "relay-result.json").write_text(json.dumps({"binding": receipt_binding, "eof": True}))
                (relay / "stderr.log").write_bytes(b"x" * 256)
                for name in (*primaries, "summary.json"):
                    (run / name).write_bytes(b"authoritative")
                if kind == "active":
                    (run / "summary.json").unlink()
                elif kind == "sealed":
                    (run / "evidence-seal.json").write_text('{"files":["attempt-01.capture/stdout/stderr.log"]}')
                elif kind == "dangling-seal":
                    (run / "evidence-seal.json").symlink_to("missing-seal")
                captures[kind] = relay
            run = captures["current"].parent.parent
            self.assertEqual(runner.reclaim_completed_evidence(run, max_evidence_bytes=0),
                             {"reclaimed_bytes": 0, "reclaimed_runs": 0})
            self.assertIsNone(runner.evidence_root_for(run))
            with (patch.dict(os.environ, {"LIFE_MANAGER_LOOP_ID": owner,
                                          "LIFE_MANAGER_STATE_ROOT": str(state)}),
                  patch.object(runner, "REPO_ROOT", config.parent)):
                result = runner.finish_evidence_run(run, {"status": "failed"})
                runner.finish_evidence_run(base / "unmanaged/run", {"status": "success"})
            self.assertFalse(captures["current"].exists())
            self.assertEqual(result["postrun_evidence_reclamation"]["removed"], 1)
            self.assertEqual(result["postrun_evidence_reclamation"]["errors"], 0)
            self.assertEqual(result["status"], "failed")
            for relay in captures.values():
                for name in primaries:
                    self.assertEqual((relay.parent.parent / name).read_bytes(), b"authoritative")
            for kind, relay in captures.items():
                if kind != "current":
                    self.assertEqual((relay / "stderr.log").read_bytes(), b"x" * 256)

    def test_registered_state_evidence_prunes_only_unsealed_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            state = base / "state"
            config = base / "repo/config"
            config.mkdir(parents=True)
            owner = "job-search-daily"
            policy = json.loads((runner.REPO_ROOT / "config/storage-policy.json").read_text())
            policy["defaults"]["owner_diagnostic_retained_bytes"] = 64
            policy["defaults"]["host_diagnostic_retained_bytes"] = 64
            (config / "storage-policy.json").write_text(json.dumps(policy))
            (config / "loop-registry.json").write_text(json.dumps({"loops": {owner: {"state_root": str(state)}}}))
            primaries = ("result.json", "usage.json", "attempts.jsonl")
            captures = {}
            for kind, run in (("current", state / "evidence/daily-1"),
                              ("sealed", state / "evidence/daily-0"),
                              ("foreign", base / "foreign/evidence/daily-2")):
                relay = run / "attempt-01.capture/stdout"
                relay.mkdir(parents=True, mode=0o700)
                binding = {"owner_id": owner, "run_id": run.name,
                    "occurrence_id": f"{owner}:{run.name}", "release_sha": "a" * 40}
                marker = relay / ".lm-regenerable"
                marker.write_text(json.dumps({"role": "diagnostic_only", "binding": binding}))
                marker.chmod(0o600)
                (relay / "relay-result.json").write_text(json.dumps({"binding": binding, "eof": True}))
                (relay / "stderr.log").write_bytes(b"x" * 256)
                for name in (*primaries, "summary.json"):
                    (run / name).write_bytes(b"authoritative")
                if kind == "sealed":
                    (run / "evidence-seal.json").write_bytes(b'{"files":["attempt-01.capture/stdout/stderr.log"]}')
                captures[kind] = relay
            run = captures["current"].parent.parent
            with (patch.dict(os.environ, {"LIFE_MANAGER_LOOP_ID": owner,
                                          "LIFE_MANAGER_STATE_ROOT": str(state)}),
                  patch.object(runner, "REPO_ROOT", config.parent),
                  patch.object(runner, "reclaim_completed_evidence") as legacy):
                result = runner.finish_evidence_run(run, {"status": "success"})
                runner.finish_evidence_run(captures["foreign"].parent.parent, {"status": "success"})
            self.assertFalse(captures["current"].exists())
            self.assertEqual(result["postrun_evidence_reclamation"]["removed"], 1)
            self.assertEqual(result["status"], "success")
            for name in primaries:
                self.assertEqual((run / name).read_bytes(), b"authoritative")
            self.assertEqual((captures["sealed"] / "stderr.log").read_bytes(), b"x" * 256)
            self.assertEqual((captures["sealed"].parent.parent / "evidence-seal.json").read_bytes(),
                             b'{"files":["attempt-01.capture/stdout/stderr.log"]}')
            self.assertTrue(captures["foreign"].exists())
            legacy.assert_not_called()

    def test_finished_run_prunes_diagnostics_without_waiting_for_another_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            config = base / "repo/config"
            config.mkdir(parents=True)
            policy = json.loads((runner.REPO_ROOT / "config/storage-policy.json").read_text())
            policy["defaults"]["owner_diagnostic_retained_bytes"] = 64
            policy["defaults"]["host_diagnostic_retained_bytes"] = 64
            (config / "storage-policy.json").write_text(json.dumps(policy))
            owner = "life-manager-disk-cleanup"
            (config / "loop-registry.json").write_text(json.dumps({"loops": {owner: {}}}))
            run = base / "agent-runner-evidence/task/run-1"
            relay = run / "attempt-01.capture/stderr-relay"
            relay.mkdir(parents=True, mode=0o700)
            binding = {"owner_id": owner, "run_id": "run-1"}
            marker = relay / ".lm-regenerable"
            marker.write_text(json.dumps({"role": "diagnostic_only", "binding": binding}))
            marker.chmod(0o600)
            (relay / "relay-result.json").write_text(json.dumps({"binding": binding}))
            (relay / "stderr.log").write_bytes(b"x" * 256)
            primary = {name: b"authoritative" for name in ("result.json", "usage.json", "attempts.jsonl")}
            for name, payload in primary.items():
                (run / name).write_bytes(payload)
            summary = {"status": "failed", "attempt_count": 1}

            with patch.dict(os.environ, {"LIFE_MANAGER_LOOP_ID": owner}), patch.object(runner, "REPO_ROOT", config.parent):
                result = runner.finish_evidence_run(run, summary)

            self.assertFalse(relay.exists(), "a completed run must prune its own excess diagnostics")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["postrun_evidence_reclamation"]["removed"], 1)
            self.assertEqual(json.loads((run / "summary.json").read_text())["status"], "failed")
            for name, payload in primary.items():
                self.assertEqual((run / name).read_bytes(), payload)

    def test_finished_run_preserves_summary_and_business_status_on_cleanup_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "agent-runner-evidence/task/run-1"
            summary = {"status": "success", "result_path": "result.json"}
            with (patch.dict(os.environ, {"LIFE_MANAGER_LOOP_ID": "life-manager-disk-cleanup"}),
                  patch.object(runner, "prune_closed_diagnostics", side_effect=PermissionError(13, "private"))):
                result = runner.finish_evidence_run(run, summary)
            self.assertEqual(result["status"], "success")
            self.assertEqual(json.loads((run / "summary.json").read_text())["status"], "success")

    def test_finished_unmanaged_run_does_not_use_legacy_whole_run_gc(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "agent-runner-evidence/task/run-1"
            with patch.dict(os.environ, {}, clear=True), patch.object(runner, "reclaim_completed_evidence") as legacy:
                runner.finish_evidence_run(run, {"status": "success"})
            legacy.assert_not_called()
            self.assertTrue((run / "summary.json").is_file())

    def test_finished_unregistered_owner_preserves_other_runs_primary_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "agent-runner-evidence"
            previous = self.completed_run(root, "other-owner", "previous", b"diagnostic")
            primary = ("summary.json", "result.json", "usage.json", "attempts.jsonl")
            for name in primary:
                (previous / name).write_text("authoritative")
            current = root / "unknown-owner/current"
            with patch.dict(os.environ, {"LIFE_MANAGER_LOOP_ID": "unregistered-test-owner",
                                         "AGENT_RUNNER_EVIDENCE_MAX_BYTES": "0"}):
                runner.finish_evidence_run(current, {"status": "success"})
            for name in primary:
                self.assertEqual((previous / name).read_text(), "authoritative")

    def completed_run(self, root: Path, task: str, name: str, payload: bytes) -> Path:
        run = root / task / name
        run.mkdir(parents=True)
        (run / "summary.json").write_text("{}", encoding="utf-8")
        (run / "attempt-01.stdout.log").write_bytes(payload)
        return run

    def test_evicts_oldest_completed_runs_but_preserves_current_and_active(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "state" / "agent-runner-evidence"
            old = self.completed_run(root, "capafy", "old", b"a" * 64)
            time.sleep(0.01)
            current = self.completed_run(root, "capafy", "current", b"b" * 64)
            active = root / "capafy" / "active"
            active.mkdir()
            (active / "runner.stdout.log").write_bytes(b"c" * 64)

            result = reclaim_completed_evidence(
                current, max_evidence_bytes=150,
            )

            self.assertEqual(result["reclaimed_runs"], 1)
            self.assertFalse(old.exists())
            self.assertTrue(current.exists())
            self.assertTrue(active.exists())

    def test_unmanaged_path_is_never_reclaimed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "arbitrary" / "run"
            path.mkdir(parents=True)
            result = reclaim_completed_evidence(path, max_evidence_bytes=0)
            self.assertEqual(result, {"reclaimed_bytes": 0, "reclaimed_runs": 0})

    def test_zero_free_bytes_does_not_block_managed_agent_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "agent-runner-evidence" / "self-fix" / "current"
            evidence.mkdir(parents=True)
            with patch.dict(os.environ, {"AGENT_RUNNER_EVIDENCE_MIN_FREE_BYTES": "999999999999"}), \
                    patch("agent_runner.shutil.disk_usage",
                          return_value=SimpleNamespace(free=0)):
                result = ensure_evidence_capacity(evidence)
            self.assertEqual(result, {"reclaimed_bytes": 0, "reclaimed_runs": 0})


if __name__ == "__main__":
    unittest.main()
