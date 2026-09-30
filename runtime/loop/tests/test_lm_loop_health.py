import json
import io
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import runtime.loop.lm_loop as lm_loop
from runtime.loop.lm_loop import main as lm_loop_main
import runtime.loop.health as health


ROOT = Path(__file__).resolve().parents[3]


class LmLoopHealthTest(unittest.TestCase):
    @staticmethod
    def status_row(loop_id="example", **overrides):
        row = {
            "classification": "managed",
            "loop_id": loop_id,
            "label": f"ai.anicca.{loop_id}",
            "product_loop_id": None,
            "system_role": "platform",
            "launchd_state": "loaded-idle",
            "last_terminal_result": "pass",
            "last_pass": "2026-10-01T00:00:00+00:00",
            "effect_class": "none",
            "effect_status": "not_applicable",
            "event_release_sha": "a" * 40,
            "run_id": "run-1",
            "owner_id": loop_id,
            "occurrence_id": f"{loop_id}:run-1",
            "provider_receipt_id": None,
            "official_readback_ref": None,
            "error_class": None,
            "retryable": False,
            "next_action": "none",
            "diagnostic_complete": True,
            "blocker": None,
            "admission_effect_unknown": False,
        }
        row.update(overrides)
        return row

    def test_every_managed_job_has_exactly_one_health_classification(self):
        """Removing either catalog membership or system_role must uncover that job."""
        registry = json.loads(
            (ROOT / "config/loop-registry.json").read_text(encoding="utf-8")
        )["loops"]
        catalog = json.loads(
            (ROOT / "apps/life-manager/config/product-loop-catalog.json").read_text(
                encoding="utf-8"
            )
        )["loops"]
        product_jobs = {
            job_id
            for product_loop in catalog
            for job_id in product_loop["job_ids"]
        }
        system_jobs = {
            job_id
            for job_id, entry in registry.items()
            if entry.get("system_role") in {"platform", "control", "shared"}
        }

        self.assertEqual(product_jobs & system_jobs, set())
        self.assertEqual(
            product_jobs | system_jobs,
            set(registry),
            "every managed job must have product_loop_id or typed system_role",
        )

    def test_status_system_role_ignores_stale_event_product_classification(self):
        registry = json.loads(
            (ROOT / "config/loop-registry.json").read_text(encoding="utf-8")
        )
        registry["loops"] = {
            "compute-proxy": registry["loops"]["compute-proxy"],
        }
        with patch("runtime.loop.lm_loop._latest_harness_failure", return_value=None):
            row = lm_loop.status_rows(
                registry,
                loaded={},
                disabled={},
                events={"compute-proxy": {"product_loop_id": "stale-product"}},
                installed_releases={},
                product_by_job={},
            )[0]

        self.assertEqual(row["system_role"], "platform")
        self.assertIsNone(row["product_loop_id"])
        self.assertEqual(
            health.project_health([row])["jobs"][0]["system_role"],
            "platform",
        )

    def test_health_rejects_unknown_option_with_typed_diagnostic(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = lm_loop_main(["health", "--bogus"])

        self.assertEqual(result, 2)
        self.assertTrue(output.getvalue())
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["error_class"], "invalid_input")
        self.assertFalse(payload["retryable"])

    def test_health_rejects_unknown_loop_with_typed_diagnostic(self):
        output = io.StringIO()
        with (
            patch("runtime.loop.lm_loop.snapshot", return_value=[]),
            redirect_stdout(output),
        ):
            result = lm_loop_main([
                "health", "--loop", "does-not-exist", "--explain",
            ])

        self.assertEqual(result, 2)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["error_class"], "invalid_input")
        self.assertIn("unknown health loop", payload["error"])

    def test_health_timeout_fallback_rejects_unknown_loop(self):
        registry = json.loads(
            (ROOT / "config/loop-registry.json").read_text(encoding="utf-8")
        )
        with self.assertRaisesRegex(ValueError, "unknown health loop"):
            lm_loop._health_snapshot_timeout_rows(registry, "does-not-exist")

    def test_health_deadline_rejects_non_positive_budget(self):
        with self.assertRaisesRegex(ValueError, "health deadline"):
            with health.health_deadline(0):
                pass

    def test_health_json_emits_v1_contract(self):
        status_row = {
            "classification": "managed",
            "loop_id": "writer-report",
            "label": "ai.anicca.writer-report",
            "product_loop_id": "writer",
            "system_role": None,
            "launchd_state": "loaded-idle",
            "last_terminal_result": "pass",
            "last_pass": "2026-10-01T00:00:00+00:00",
            "effect_class": "none",
            "effect_status": "not_applicable",
            "event_release_sha": "a" * 40,
            "run_id": "run-1",
            "owner_id": "writer-report",
            "occurrence_id": "writer-report:run-1",
            "provider_receipt_id": None,
            "official_readback_ref": None,
            "error_class": None,
            "retryable": False,
            "next_action": "none",
            "diagnostic_complete": True,
            "blocker": None,
            "admission_effect_unknown": False,
        }
        output = io.StringIO()
        with (
            patch("runtime.loop.lm_loop.snapshot", return_value=[status_row]),
            redirect_stdout(output),
        ):
            result = lm_loop_main(["health", "--json"])

        self.assertEqual(result, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema_version"], "lm-loop.health.v1")
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["jobs"][0]["job_id"], "writer-report")
        self.assertEqual(
            set(payload["jobs"][0]["clocks"]),
            {"last_attempt", "last_success", "last_effect", "last_receipt"},
        )
        self.assertEqual(
            set(payload["jobs"][0]["facets"]),
            {"runtime", "productivity", "effect_safety", "business", "recovery"},
        )

    def test_health_json_schema_is_generated_from_validator_contract(self):
        schema_path = ROOT / "runtime/loop/health.schema.json"
        self.assertEqual(schema_path.read_bytes(), health.render_health_json_schema())
        schema = health.health_json_schema()
        self.assertEqual(schema["properties"]["schema_version"]["const"], "lm-loop.health.v1")
        self.assertEqual(
            set(schema["$defs"]["job"]["properties"]["state"]["enum"]),
            health.HEALTH_STATES,
        )

    def test_one_slow_adapter_becomes_telemetry_gap_without_blocking_fleet(self):
        rows = [
            {
                "loop_id": "slow", "label": "ai.anicca.slow",
                "product_loop_id": None, "system_role": "platform",
                "diagnostic_complete": True, "last_pass": "2026-10-01T00:00:00+00:00",
                "last_terminal_result": "pass", "launchd_state": "loaded-idle",
                "effect_class": "none", "effect_status": "not_applicable",
                "retryable": False, "next_action": "none",
            },
            {
                "loop_id": "fast", "label": "ai.anicca.fast",
                "product_loop_id": None, "system_role": "platform",
                "diagnostic_complete": True, "last_pass": "2026-10-01T00:00:00+00:00",
                "last_terminal_result": "pass", "launchd_state": "loaded-idle",
                "effect_class": "none", "effect_status": "not_applicable",
                "retryable": False, "next_action": "none",
            },
        ]

        def adapter(row):
            if row["loop_id"] == "slow":
                time.sleep(0.5)
            return row

        started = time.monotonic()
        value = health.project_health(rows, adapter=adapter, adapter_timeout_seconds=0.02)
        elapsed = time.monotonic() - started

        by_id = {job["job_id"]: job for job in value["jobs"]}
        self.assertEqual(by_id["slow"]["state"], "telemetry_gap")
        self.assertEqual(by_id["slow"]["diagnostic"]["error_class"], "health_adapter_timeout")
        self.assertEqual(by_id["fast"]["state"], "healthy")
        self.assertLess(elapsed, 0.3)

    def test_health_ignores_non_managed_status_inventory_rows(self):
        managed = self.status_row("managed")
        unmanaged = self.status_row(
            "ai.anicca.unmanaged", classification="unmanaged",
            product_loop_id=None, system_role=None,
        )
        value = health.project_health([managed, unmanaged])
        self.assertEqual(value["summary"]["total"], 1)
        self.assertEqual([job["job_id"] for job in value["jobs"]], ["managed"])

    def test_health_distinguishes_typed_safety_states_and_failure(self):
        rows = [
            self.status_row("fenced", admission_effect_unknown=True),
            self.status_row(
                "unknown", effect_class="publish", effect_status="unknown",
            ),
            self.status_row("gap", diagnostic_complete=False),
            self.status_row("human", next_action="human_required"),
            self.status_row("failed", last_terminal_result="fail", error_class="entrypoint_exit"),
        ]
        value = health.project_health(rows)
        self.assertEqual(
            {job["job_id"]: job["state"] for job in value["jobs"]},
            {
                "fenced": "safely_fenced",
                "unknown": "effect_unknown",
                "gap": "telemetry_gap",
                "human": "human_required",
                "failed": "failed",
            },
        )
        self.assertEqual(health.health_exit_code(value), 1)

    def test_health_state_preserves_adapter_gap_then_human_then_fence_priority(self):
        cases = {
            "adapter-timeout-human": ({
                "health_adapter_status": "timeout",
                "next_action": "human_required",
                "admission_effect_unknown": True,
                "diagnostic_complete": False,
                "last_pass": None,
            }, "telemetry_gap"),
            "adapter-error-fence": ({
                "health_adapter_status": "error",
                "admission_effect_unknown": True,
                "diagnostic_complete": False,
                "last_pass": None,
            }, "telemetry_gap"),
            "human-before-fence-and-gap": ({
                "next_action": "human_required",
                "admission_effect_unknown": True,
                "diagnostic_complete": False,
                "last_pass": None,
            }, "human_required"),
            "fence-before-gap": ({
                "admission_effect_unknown": True,
                "diagnostic_complete": False,
                "last_pass": None,
            }, "safely_fenced"),
            "plain-diagnostic-gap": ({
                "diagnostic_complete": False,
                "last_pass": None,
            }, "telemetry_gap"),
        }
        rows = [
            self.status_row(loop_id, **overrides)
            for loop_id, (overrides, _) in cases.items()
        ]
        states = {
            job["job_id"]: job["state"]
            for job in health.project_health(rows)["jobs"]
        }
        self.assertEqual(
            states,
            {loop_id: expected for loop_id, (_, expected) in cases.items()},
        )

    def test_safely_fenced_alone_returns_degraded_exit(self):
        value = health.project_health([
            self.status_row("fenced", admission_effect_unknown=True),
        ])
        self.assertEqual(value["summary"]["safely_fenced"], 1)
        self.assertEqual(health.health_exit_code(value), 1)

    def test_health_cli_bounds_the_live_snapshot(self):
        output = io.StringIO()

        def slow_snapshot(*_args, **_kwargs):
            time.sleep(0.5)
            return []

        started = time.monotonic()
        with (
            patch("runtime.loop.lm_loop.snapshot", side_effect=slow_snapshot),
            patch("runtime.loop.lm_loop.HEALTH_SNAPSHOT_TIMEOUT_SECONDS", 0.02),
            redirect_stdout(output),
        ):
            result = lm_loop_main(["health", "--json"])
        elapsed = time.monotonic() - started

        self.assertEqual(result, 1)
        self.assertLess(elapsed, 0.3)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema_version"], "lm-loop.health.v1")
        self.assertEqual(payload["summary"]["total"], 176)
        self.assertEqual(payload["summary"]["telemetry_gap"], 176)
        self.assertTrue(all(
            job["diagnostic"]["error_class"] == "health_snapshot_timeout"
            for job in payload["jobs"]
        ))

    def test_health_human_skill_and_loop_explain_surfaces(self):
        row = self.status_row("writer-report", product_loop_id="writer", system_role=None)
        human = io.StringIO()
        skill = io.StringIO()
        explain = io.StringIO()
        with patch("runtime.loop.lm_loop.snapshot", return_value=[row]):
            with redirect_stdout(human):
                self.assertEqual(lm_loop_main(["health"]), 0)
            with redirect_stdout(skill):
                self.assertEqual(lm_loop_main(["health", "--skill"]), 0)
            with redirect_stdout(explain):
                self.assertEqual(
                    lm_loop_main(["health", "--loop", "writer-report", "--explain"]),
                    0,
                )
        self.assertIn("health total=1 healthy=1", human.getvalue())
        self.assertEqual(json.loads(skill.getvalue())["job_id"], "writer-report")
        explained = json.loads(explain.getvalue())
        self.assertEqual(explained["scope"], {"kind": "loop", "target": "writer-report"})
        self.assertEqual(explained["jobs"][0]["diagnostic"]["run_id"], "run-1")

    def test_health_validator_rejects_unknown_state(self):
        value = health.project_health([self.status_row()])
        value["jobs"][0]["state"] = "invented"
        with self.assertRaisesRegex(ValueError, "health job state"):
            health.validate_health_document(value)

    def test_health_schema_requires_summary_and_diagnostic_contracts(self):
        schema = health.health_json_schema()
        summary = schema["properties"]["summary"]
        self.assertEqual(
            set(summary["required"]),
            {*health.HEALTH_STATES, "total"},
        )
        self.assertFalse(summary["additionalProperties"])
        diagnostic = schema["$defs"]["diagnostic"]
        self.assertEqual(
            set(diagnostic["required"]),
            {
                "release_sha", "run_id", "owner_id", "occurrence_id", "effect",
                "readback", "provider_receipt_id", "error_class", "retryable",
                "next_action",
            },
        )
        self.assertFalse(diagnostic["additionalProperties"])
        self.assertFalse(diagnostic["properties"]["effect"]["additionalProperties"])

    def test_health_validator_rejects_invalid_scope_shape(self):
        value = health.project_health([self.status_row()])
        value["scope"]["extra"] = True
        with self.assertRaisesRegex(ValueError, "health scope"):
            health.validate_health_document(value)

    def test_health_validator_rejects_inexact_job_and_diagnostic_shapes(self):
        value = health.project_health([self.status_row()])
        del value["jobs"][0]["label"]
        with self.assertRaisesRegex(ValueError, "health job fields"):
            health.validate_health_document(value)

        value = health.project_health([self.status_row()])
        del value["jobs"][0]["diagnostic"]["owner_id"]
        with self.assertRaisesRegex(ValueError, "health diagnostic"):
            health.validate_health_document(value)

        value = health.project_health([self.status_row()])
        value["jobs"][0]["diagnostic"]["effect"]["extra"] = True
        with self.assertRaisesRegex(ValueError, "health diagnostic effect"):
            health.validate_health_document(value)

    def test_health_validator_rejects_summary_job_mismatch(self):
        value = health.project_health([self.status_row()])
        value["summary"]["healthy"] = 0
        with self.assertRaisesRegex(ValueError, "health summary does not match jobs"):
            health.validate_health_document(value)


if __name__ == "__main__":
    unittest.main()
