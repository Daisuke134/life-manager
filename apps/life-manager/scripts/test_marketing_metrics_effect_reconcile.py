import importlib.util
import gzip
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from runtime.loop.runtime_event import build_runtime_event, build_runtime_start_event


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "apps/life-manager/scripts/marketing-metrics-effect-reconcile.py"
OWNER = "life-manager-tiktok-metrics"
OCCURRENCE = f"{OWNER}:run-1"
RUN_ID = "run-1"
RELEASE_SHA = "a" * 40
START = "2026-10-13T19:33:39.294865+00:00"
END = "2026-10-13T19:38:53.136715+00:00"


def _load_module():
    if not SCRIPT.is_file():
        raise AssertionError("metrics effect reconciler is missing")
    spec = importlib.util.spec_from_file_location("metrics_effect_reconcile", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("metrics effect reconciler cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    path.chmod(0o600)


def _run_events(run_id=RUN_ID, start=START, end=END, *, release_sha=RELEASE_SHA,
                effect_class="message"):
    start_event = build_runtime_start_event(
        loop_id=OWNER, domain="growth", run_id=run_id, release_sha=release_sha,
        provider="deterministic", profile_alias=None, effect_class=effect_class,
        owner_id=OWNER, job_id=OWNER, wake_id=run_id,
        occurrence_id=OCCURRENCE,
    )
    start_event["timestamp"] = start
    terminal = build_runtime_event(
        loop_id=OWNER, domain="growth", run_id=run_id, release_sha=release_sha,
        provider="deterministic", profile_alias=None, effect_class=effect_class,
        succeeded=False, blocker="entrypoint_exit_124", claimed_occurrence_id=OCCURRENCE,
        owner_id=OWNER, job_id=OWNER, wake_id=run_id, exit_code=124,
        error_class="entrypoint_exit_124", retryable=True,
    )
    terminal["timestamp"] = end
    return [start_event, terminal]


def _write_gzip_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.writelines(json.dumps(row) + "\n" for row in rows)
    path.chmod(0o600)


def _fixture(root: Path, jobs=(), receipts=(), *, terminal=True, effect_class="message"):
    state_root = root / "state"
    data_root = root / "data"
    events = _run_events(effect_class=effect_class)
    if not terminal:
        events = events[:1]
    _write_jsonl(state_root / "events.jsonl", events)
    _write_jsonl(data_root / "marketing/jobs.jsonl", jobs)
    _write_jsonl(data_root / "marketing/receipts.jsonl", receipts)
    return state_root, data_root


class MetricsEffectReconcileTest(unittest.TestCase):
    def test_metrics_boot_rejects_data_root_different_from_registry_root(self):
        scripts = ROOT / "apps/life-manager/scripts"
        for script in (
            scripts / "tiktok-metrics-production-boot.sh",
            scripts / "instagram-metrics-production-boot.sh",
        ):
            with self.subTest(script=script.name), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                env_file = home / "metrics.env"
                env_file.write_text("LM_DATA_DIR=/tmp/different-life-manager-root\n", encoding="utf-8")
                result = subprocess.run(
                    ["bash", str(script)],
                    env={**os.environ, "HOME": str(home), "LIFE_MANAGER_ENV_FILE": str(env_file)},
                    capture_output=True, text=True, check=False,
                )

            self.assertEqual(result.returncode, 78)
            self.assertIn("LM_DATA_DIR", result.stderr)

    def test_reconciler_rejects_inherited_data_root_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "--owner-id", OWNER,
                    "--occurrence-id", OCCURRENCE,
                    "--state-root", str(root / "state"),
                    "--data-root", str(root / "data"),
                ],
                env={**os.environ, "HOME": str(root), "LM_DATA_DIR": str(root / "other-data")},
                capture_output=True, text=True, check=False,
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["verified"])
        self.assertEqual(payload["reason"], "data_root_environment_mismatch")

    def test_durable_dispatch_in_rotated_attempt_history_keeps_fence(self):
        module = _load_module()
        old_start, old_end = "2026-10-13T19:31:00Z", "2026-10-13T19:32:00Z"
        job = {
            "schema_version": 1, "kind": "job", "event": "enqueue",
            "job": {
                "job_id": "marketing-liveness:old-attempt",
                "capability": "marketing.liveness.telegram", "effect_class": "message",
                "enqueued_at": "2026-10-13T19:31:30Z", "updated_at": "2026-10-13T19:31:30Z",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory), jobs=[job])
            _write_gzip_jsonl(
                state_root / "events-20261013T193300000000Z.jsonl.gz",
                _run_events("run-old", old_start, old_end),
            )
            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=False,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "telegram_job_in_run_window")

    def test_invalid_rotated_event_archive_keeps_fence(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory))
            archive = state_root / "events-20261013T193300000000Z.jsonl.gz"
            archive.write_bytes(b"not a gzip archive")
            archive.chmod(0o600)
            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=False,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "event_archive_invalid")

    def test_message_effect_class_is_pre_effect_for_metrics_notification(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory), effect_class="message")
            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=False,
            )

        self.assertTrue(result["verified"])
        self.assertEqual(result["proof_type"], "pre_effect")

    def test_legacy_publish_run_with_unbound_historical_root_cannot_resolve(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_root = root / "state"
            historical_data_root = root / "historical-data"
            current_data_root = root / "current-data"
            _write_jsonl(state_root / "events.jsonl", _run_events(effect_class="publish"))
            _write_jsonl(historical_data_root / "marketing/jobs.jsonl", [{
                "schema_version": 1, "kind": "job", "event": "enqueue",
                "job": {
                    "job_id": "marketing-liveness:legacy-run",
                    "capability": "marketing.liveness.telegram",
                    "effect_class": "message", "enqueued_at": "2026-10-13T19:35:00Z",
                    "updated_at": "2026-10-13T19:35:00Z",
                },
            }])
            _write_jsonl(historical_data_root / "marketing/receipts.jsonl", [])
            _write_jsonl(current_data_root / "marketing/jobs.jsonl", [])
            _write_jsonl(current_data_root / "marketing/receipts.jsonl", [])
            calls = []

            def resolver(*args, **kwargs):
                calls.append((args, kwargs))
                return True

            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=current_data_root,
                resolve=True, resolver=resolver,
            )

        self.assertFalse(result["verified"])
        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "legacy_effect_class_unbound")
        self.assertEqual(calls, [])

    def test_unknown_effect_class_keeps_fence(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory), effect_class="money")
            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=False,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "run_terminal_not_provable")

    def test_exact_run_with_no_durable_telegram_dispatch_is_pre_effect(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory))
            seen = []

            def resolver(owner_id, occurrence_id, *, pre_effect_readback, expected_state):
                proof = pre_effect_readback()
                seen.append((owner_id, occurrence_id, proof, expected_state))
                return proof.get("verified") is True

            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=True, resolver=resolver,
            )

        self.assertTrue(result["resolved"])
        self.assertEqual(seen[0][0:2], (OWNER, OCCURRENCE))
        self.assertEqual(seen[0][2]["proof_type"], "pre_effect")
        self.assertEqual(seen[0][2]["release_sha"], RELEASE_SHA)
        self.assertTrue(seen[0][2]["evidence_ref"].startswith("lm-no-effect://"))

    def test_durable_telegram_job_in_occurrence_window_keeps_fence(self):
        module = _load_module()
        job = {
            "schema_version": 1, "kind": "job", "event": "enqueue",
            "job": {
                "job_id": "marketing-liveness:report-1",
                "capability": "marketing.liveness.telegram",
                "effect_class": "message", "enqueued_at": "2026-10-13T19:35:00Z",
                "updated_at": "2026-10-13T19:35:00Z",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory), jobs=[job])
            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=False,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "telegram_job_in_run_window")

    def test_telegram_receipt_in_occurrence_window_keeps_fence(self):
        module = _load_module()
        receipt = {
            "schema_version": 1, "kind": "receipt", "job_id": "marketing-liveness:report-1",
            "tenant_id": "dais-local",
            "receipt": {
                "kind": "telegram_marketing_liveness", "message_id": 42,
                "chat_id_hash": "b" * 64, "sent_at": "2026-10-13T19:35:01Z",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory), receipts=[receipt])
            calls = []

            def resolver(*args, **kwargs):
                calls.append((args, kwargs))
                return True

            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=True, resolver=resolver,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "telegram_receipt_in_run_window")
        self.assertEqual(calls, [])

    def test_malformed_telegram_job_timestamp_keeps_fence(self):
        module = _load_module()
        job = {
            "schema_version": 1, "kind": "job", "event": "claim",
            "job": {
                "job_id": "marketing-liveness:report-1",
                "capability": "marketing.liveness.telegram",
                "effect_class": "message", "enqueued_at": "2026-10-13T18:00:00Z",
                "updated_at": "not-a-time",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory), jobs=[job])
            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=False,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "telegram_job_timestamp_invalid")

    def test_incomplete_run_history_keeps_fence(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory), terminal=False)
            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=False,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "run_terminal_missing")

    def test_non_metrics_owner_cannot_be_resolved_by_this_adapter(self):
        module = _load_module()
        owner = "life-manager-anicca-en-affirmation-tiktok"
        occurrence = f"{owner}:run-1"
        calls = []

        def resolver(*args, **kwargs):
            calls.append((args, kwargs))
            return True

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = module.reconcile(
                owner, occurrence, state_root=root / "state", data_root=root / "data",
                resolve=True, resolver=resolver,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "identity_not_allowlisted")
        self.assertEqual(calls, [])

    def test_admission_database_error_keeps_proof_unresolved(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory))
            calls = []

            def resolver(*args, **kwargs):
                calls.append((args, kwargs))
                raise sqlite3.OperationalError("database is locked")

            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=True, resolver=resolver,
            )

        self.assertFalse(result["verified"])
        self.assertFalse(result["resolved"])
        self.assertEqual(result["reason"], "admission_resolution_failed")
        self.assertEqual(len(calls), 1)

    def test_message_in_any_attempt_window_keeps_shared_occurrence_fenced(self):
        module = _load_module()
        job = {
            "schema_version": 1, "kind": "job", "event": "enqueue",
            "job": {
                "job_id": "marketing-liveness:report-old",
                "capability": "marketing.liveness.telegram",
                "effect_class": "message", "enqueued_at": "2026-10-13T18:00:30Z",
                "updated_at": "2026-10-13T18:00:30Z",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory), jobs=[job])
            _write_jsonl(state_root / "events.jsonl", _run_events())
            _write_gzip_jsonl(
                state_root / "events-20261013T180200000000Z.jsonl.gz",
                _run_events("run-old", "2026-10-13T18:00:00Z", "2026-10-13T18:01:00Z"),
            )
            calls = []

            def resolver(*args, **kwargs):
                calls.append((args, kwargs))
                return True

            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=True, resolver=resolver,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "telegram_job_in_run_window")
        self.assertEqual(calls, [])

    def test_shared_occurrence_with_different_release_shas_keeps_fence(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            state_root, data_root = _fixture(Path(directory))
            _write_jsonl(state_root / "events.jsonl", _run_events())
            _write_gzip_jsonl(
                state_root / "events-20261013T180200000000Z.jsonl.gz",
                _run_events("run-old", "2026-10-13T18:00:00Z", "2026-10-13T18:01:00Z",
                            release_sha="b" * 40),
            )
            calls = []

            def resolver(*args, **kwargs):
                calls.append((args, kwargs))
                return True

            result = module.reconcile(
                OWNER, OCCURRENCE, state_root=state_root, data_root=data_root,
                resolve=True, resolver=resolver,
            )

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "run_release_mismatch")
        self.assertEqual(calls, [])

if __name__ == "__main__":
    unittest.main()
