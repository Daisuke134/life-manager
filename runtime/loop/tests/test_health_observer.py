import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from runtime.loop.health_observer import (
    build_recovery_intent,
    load_health_snapshot,
    observe_health,
    write_latest,
)


def health_document(*, state="failed", generated_at="2026-10-01T00:00:00+00:00"):
    return {
        "schema_version": "lm-loop.health.v1",
        "generated_at": generated_at,
        "scope": {"kind": "fleet", "target": None},
        "summary": {
            "effect_unknown": 0,
            "failed": int(state == "failed"),
            "healthy": int(state == "healthy"),
            "human_required": 0,
            "running": 0,
            "safely_fenced": 0,
            "telemetry_gap": 0,
            "total": 1,
        },
        "jobs": [{
            "job_id": "example-loop",
            "label": "ai.anicca.example-loop",
            "product_loop_id": None,
            "system_role": "control",
            "state": state,
            "facets": {
                "runtime": {"status": "degraded" if state == "failed" else "ok", "reason": "entrypoint_exit_1" if state == "failed" else None},
                "productivity": {"status": "degraded" if state == "failed" else "ok", "reason": "entrypoint_exit_1" if state == "failed" else None},
                "effect_safety": {"status": "not_applicable", "reason": "entrypoint_exit_1" if state == "failed" else None},
                "business": {"status": "not_applicable", "reason": None},
                "recovery": {"status": "degraded" if state == "failed" else "ok", "reason": "reconcile_owner" if state == "failed" else "none"},
            },
            "clocks": {
                "last_attempt": generated_at,
                "last_success": generated_at if state == "healthy" else None,
                "last_effect": None,
                "last_receipt": None,
            },
            "diagnostic": {
                "release_sha": "a" * 40,
                "run_id": "run-1",
                "owner_id": "example-loop",
                "occurrence_id": "example-loop:run-1",
                "effect": {"class": "none", "status": "not_applicable"},
                "readback": None,
                "provider_receipt_id": None,
                "error_class": "entrypoint_exit_1" if state == "failed" else None,
                "retryable": state == "failed",
                "next_action": "reconcile_owner" if state == "failed" else "none",
            },
        }],
    }


def jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


class HealthObserverTest(unittest.TestCase):
    def test_latest_uses_atomic_replace(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "latest.json"
            real_replace = __import__("os").replace
            calls = []

            def recording_replace(source, target):
                calls.append((Path(source), Path(target)))
                real_replace(source, target)

            with patch("runtime.loop.health_observer.os.replace", side_effect=recording_replace):
                write_latest(destination, health_document())

            self.assertEqual(calls[-1][1], destination)
            self.assertEqual(json.loads(destination.read_text())["schema_version"], "lm-loop.health.v1")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_history_is_append_only_and_unchanged_state_dedupes_alert(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            built = []

            def build_intent(job, observer_run_id):
                built.append((job["job_id"], observer_run_id))
                return {
                    "schema_version": 1,
                    "intent_id": "intent-1",
                    "loop_id": job["job_id"],
                    "action": "reconcile_owner",
                    "mutates_external_effect": False,
                }

            first = observe_health(health_document(), root, intent_builder=build_intent)
            second = observe_health(
                health_document(generated_at="2026-10-01T00:05:00+00:00"),
                root,
                intent_builder=build_intent,
            )

            self.assertTrue(first["alert_emitted"])
            self.assertFalse(second["alert_emitted"])
            history = jsonl(root / "history.jsonl")
            self.assertEqual(len(history), 2)
            self.assertEqual(history[-1]["schema_version"], "lm-loop.health-observation.v1")
            self.assertNotIn("clocks", history[-1]["jobs"]["example-loop"])
            self.assertEqual(len(jsonl(root / "alerts.jsonl")), 1)
            self.assertEqual(len(built), 1)
            self.assertEqual(json.loads((root / "latest.json").read_text())["generated_at"], "2026-10-01T00:05:00+00:00")

    def test_state_change_emits_exactly_one_new_alert(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            build_intent = lambda job, observer_run_id: {
                "schema_version": 1,
                "intent_id": f"intent-{job['job_id']}",
                "loop_id": job["job_id"],
                "action": "reconcile_owner",
                "mutates_external_effect": False,
            }
            observe_health(health_document(), root, intent_builder=build_intent)
            result = observe_health(
                health_document(state="healthy", generated_at="2026-10-01T00:05:00+00:00"),
                root,
                intent_builder=build_intent,
            )

            alerts = jsonl(root / "alerts.jsonl")
            self.assertTrue(result["alert_emitted"])
            self.assertEqual(len(alerts), 2)
            self.assertEqual(alerts[-1]["changed_jobs"], ["example-loop"])
            self.assertEqual(alerts[-1]["recovery_intents"], [])

    def test_alert_append_survives_state_checkpoint_loss_without_duplicate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            build_intent = lambda job, observer_run_id: {
                "schema_version": 1,
                "intent_id": f"intent-{job['job_id']}",
                "loop_id": job["job_id"],
                "action": "reconcile_owner",
                "mutates_external_effect": False,
            }
            observe_health(health_document(), root, intent_builder=build_intent)
            (root / "alert-state.json").unlink()

            result = observe_health(
                health_document(generated_at="2026-10-01T00:05:00+00:00"),
                root,
                intent_builder=build_intent,
            )

            self.assertFalse(result["alert_emitted"])
            self.assertEqual(len(jsonl(root / "alerts.jsonl")), 1)

    def test_new_receipt_id_does_not_become_a_health_state_alert(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = health_document(state="healthy")
            second = health_document(
                state="healthy", generated_at="2026-10-01T00:05:00+00:00",
            )
            second["jobs"][0]["diagnostic"]["provider_receipt_id"] = "receipt-2"
            second["jobs"][0]["diagnostic"]["readback"] = "provider://receipt-2"

            observe_health(first, root)
            result = observe_health(second, root)

            self.assertFalse(result["alert_emitted"])
            self.assertFalse((root / "alerts.jsonl").exists())

    def test_effect_unknown_intent_never_mutates_or_retries_effect(self):
        with TemporaryDirectory() as directory:
            document = health_document()
            job = document["jobs"][0]
            job["state"] = "effect_unknown"
            job["diagnostic"]["effect"] = {"class": "publish", "status": "unknown"}
            job["diagnostic"]["next_action"] = "official_readback_required"
            document["summary"]["failed"] = 0
            document["summary"]["effect_unknown"] = 1

            result = observe_health(document, Path(directory))
            intent = result["recovery_intents"][0]

            self.assertFalse(intent["mutates_external_effect"])
            self.assertFalse(intent["retryable"])
            self.assertEqual(intent["effect_fence"], "required")
            self.assertIn(intent["action"], {"hold_effect_unknown", "escalate_repeated_failure"})

    def test_registry_runs_read_only_observer_every_five_minutes(self):
        root = Path(__file__).resolve().parents[3]
        registry = json.loads((root / "config/loop-registry.json").read_text())
        row = registry["loops"]["life-manager-health-observer"]

        self.assertEqual(row["cadence"], {"start_interval_seconds": 300})
        self.assertEqual(row["effect_class"], "none")
        self.assertEqual(row["provider_route"], "deterministic")
        self.assertEqual(row["system_role"], "control")
        self.assertEqual(row["entrypoint"], "runtime/loop/health_observer.py")

    def test_snapshot_loader_invokes_only_read_only_health_cli(self):
        completed = SimpleNamespace(
            returncode=1,
            stdout=json.dumps(health_document()),
            stderr="",
        )
        with patch("runtime.loop.health_observer.subprocess.run", return_value=completed) as run:
            value = load_health_snapshot()

        argv = run.call_args.args[0]
        self.assertEqual(argv[1:], ["-m", "runtime.loop.lm_loop", "health", "--json"])
        self.assertEqual(value["schema_version"], "lm-loop.health.v1")

    def test_intent_builder_invokes_only_local_classifier(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "schema_version": 1,
                "intent_id": "intent-1",
                "loop_id": "example-loop",
                "action": "reconcile_owner",
                "mutates_external_effect": False,
            }),
            stderr="",
        )
        with patch("runtime.loop.health_observer.subprocess.run", return_value=completed) as run:
            intent = build_recovery_intent(health_document()["jobs"][0], "observer-run")

        argv = run.call_args.args[0]
        self.assertTrue(argv[1].endswith("runtime/loop/recovery-intent-cli.mjs"))
        self.assertEqual(argv[2], "--input")
        self.assertFalse(intent["mutates_external_effect"])


if __name__ == "__main__":
    unittest.main()
