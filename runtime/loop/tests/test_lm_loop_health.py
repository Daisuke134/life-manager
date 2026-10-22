import gzip
import json
import io
import copy
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

import runtime.loop.lm_loop as lm_loop
from runtime.loop.lm_loop import main as lm_loop_main
import runtime.loop.health as health
from runtime.loop.runtime_event import (
    append_runtime_event,
    build_runtime_event,
    build_runtime_start_event,
    validate_runtime_event,
)


ROOT = Path(__file__).resolve().parents[3]


class LmLoopHealthTest(unittest.TestCase):
    def setUp(self):
        storage = patch.object(lm_loop, "read_storage_snapshot", return_value=None)
        storage.start()
        self.addCleanup(storage.stop)
    def test_storage_recovery_matches_exact_cleanup_run_and_is_separate_from_health(self):
        row = self.status_row("life-manager-disk-cleanup")
        binding = {"owner_id": row["owner_id"], "run_id": row["run_id"],
                   "occurrence_id": row["occurrence_id"], "release_sha": "a" * 40}
        observed = health.datetime.now(health.timezone.utc).isoformat()
        receipt = {"identity": binding, "observed_at": observed,
                   "free_after": 600 * 1024**2, "ok": True,
                   "capacity_recovery": {"status": "unmet", "recovery_floor_bytes": 2 * 1024**3}}
        value = health.project_health([row], storage_snapshot=receipt)
        self.assertEqual(value["jobs"][0]["state"], "healthy")
        self.assertEqual(value["host_storage"]["status"], "unmet")
        self.assertFalse(value["host_storage"]["capacity_recovered"])
        self.assertIn("capacity=unmet", health.render_human(value))
        Draft202012Validator(health.health_json_schema(), format_checker=FormatChecker()).validate(value)
        for patch_value in ({"identity": {**binding, "run_id": "other"}},
                            {"observed_at": "2026-01-01T00:00:00Z"},
                            {"free_after": True}):
            bad = health.project_health([row], storage_snapshot={**receipt, **patch_value})
            self.assertEqual(bad["host_storage"]["status"], "unknown")
            self.assertIsNone(bad["host_storage"]["capacity_recovered"])

    def test_cli_health_reads_storage_snapshot(self):
        row = self.status_row("life-manager-disk-cleanup")
        receipt = {"identity": {"owner_id": row["owner_id"], "run_id": row["run_id"],
                   "occurrence_id": row["occurrence_id"], "release_sha": "a" * 40},
                   "observed_at": health.datetime.now(health.timezone.utc).isoformat(),
                   "free_after": 600 * 1024**2, "ok": True,
                   "capacity_recovery": {"status": "unmet", "recovery_floor_bytes": 2 * 1024**3}}
        output = io.StringIO()
        with patch.object(lm_loop, "snapshot", return_value=[row]), \
             patch.object(lm_loop, "read_storage_snapshot", return_value=receipt, create=True), \
             redirect_stdout(output):
            lm_loop_main(["health", "--json"])
        self.assertEqual(json.loads(output.getvalue())["host_storage"]["status"], "unmet")

    def test_health_uses_fresh_unbound_watchdog_receipt_without_claiming_owner_identity(self):
        from datetime import timedelta

        state = Path(tempfile.mkdtemp())
        now = health.datetime.now(health.timezone.utc)
        old_bound = {
            "identity": {"owner_id": "life-manager-disk-cleanup", "run_id": "old",
                         "occurrence_id": "life-manager-disk-cleanup:old", "release_sha": "a" * 40},
            "observed_at": (now - timedelta(hours=4)).isoformat(),
            "free_after": 500 * 1024**2,
            "ok": True,
            "capacity_recovery": {"status": "unmet", "recovery_floor_bytes": 2 * 1024**3},
        }
        fresh_watchdog = {
            "observed_at": now.isoformat(),
            "free_after": 3 * 1024**3,
            "ok": True,
            "errors": 0,
            "protected_deletions": 0,
            "capacity_recovery": {"status": "met", "recovery_floor_bytes": 2 * 1024**3},
        }
        bound_path = state / "last-receipt.json"
        bound_path.write_text(json.dumps(old_bound))
        bound_path.chmod(0o600)
        watchdog_path = state / "last-unbound-receipt.json"
        watchdog_path.write_text(json.dumps(fresh_watchdog))
        watchdog_path.chmod(0o600)

        sample = health.read_storage_snapshot(state)
        value = health.project_health([], storage_snapshot=sample)

        self.assertEqual(value["host_storage"]["status"], "met")
        self.assertEqual(value["host_storage"]["free_bytes"], 3 * 1024**3)
        self.assertNotIn("identity", json.loads(watchdog_path.read_text()))

    def test_stale_unbound_watchdog_receipt_does_not_verify_host_storage(self):
        from datetime import timedelta

        state = Path(tempfile.mkdtemp())
        observed = health.datetime.now(health.timezone.utc) - timedelta(minutes=11)
        receipt = {
            "observed_at": observed.isoformat(),
            "free_after": 3 * 1024**3,
            "ok": True,
            "errors": 0,
            "protected_deletions": 0,
            "capacity_recovery": {"status": "met", "recovery_floor_bytes": 2 * 1024**3},
        }
        path = state / "last-unbound-receipt.json"
        path.write_text(json.dumps(receipt))
        path.chmod(0o600)

        sample = health.read_storage_snapshot(state)
        value = health.project_health([], storage_snapshot=sample)

        self.assertEqual(value["host_storage"]["status"], "unknown")

    def test_unbound_watchdog_receipt_with_identity_is_rejected(self):
        state = Path(tempfile.mkdtemp())
        receipt = {
            "observed_at": health.datetime.now(health.timezone.utc).isoformat(),
            "free_after": 3 * 1024**3,
            "ok": True,
            "capacity_recovery": {"status": "met", "recovery_floor_bytes": 2 * 1024**3},
            "identity": None,
        }
        path = state / "last-unbound-receipt.json"
        path.write_text(json.dumps(receipt))
        path.chmod(0o600)

        self.assertIsNone(health.read_storage_snapshot(state))

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
            {"runtime", "productivity", "effect_safety", "business", "recovery", "revenue"},
        )

    def test_health_current_and_history_share_one_collection(self):
        row = self.status_row("example")
        output = io.StringIO()
        with patch.object(lm_loop, "snapshot", return_value=[row]) as collect, \
             redirect_stdout(output):
            self.assertEqual(lm_loop_main(["health", "--json"]), 0)
        self.assertEqual(collect.call_count, 1)
        self.assertTrue(collect.call_args.kwargs["include_health_clocks"])

    def test_bounded_history_miss_does_not_reuse_a_current_only_cache_entry(self):
        import runtime.loop.runtime_event as runtime_event

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.jsonl")
            first = build_runtime_event(
                loop_id="old", domain="system", run_id="pass", release_sha="a" * 40,
                provider="deterministic", profile_alias=None, effect_class="none",
                succeeded=True, blocker=None,
            )
            append_runtime_event(path, first)
            other = {**first, "loop_id": "other", "event_id": "d" * 24}
            with path.open("a") as stream:
                stream.write((json.dumps(other) + "\n") * 10)
            cache = {}
            self.assertIsNotNone(lm_loop._last_event(directory, "old", cache))
            with patch.object(runtime_event, "HEALTH_CATCHUP_BYTES", 2048):
                self.assertIsNone(lm_loop._last_event(directory, "old", cache, include_health_clocks=True))
                self.assertIsNone(lm_loop._last_event(directory, "old", cache, include_health_clocks=True))

    def test_new_verified_outcomes_recover_after_an_older_history_gap_and_can_age(self):
        from datetime import timedelta
        import runtime.loop.runtime_event as runtime_event

        now = health.datetime.now(health.timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.jsonl")
            for index in range(5):
                old = build_runtime_event(
                    loop_id="old", domain="system", run_id=f"old-{index}", release_sha="a" * 40,
                    provider="deterministic", profile_alias=None, effect_class="none",
                    succeeded=True, blocker=None,
                )
                with gzip.open(Path(directory, f"events-{index:04d}.jsonl.gz"), "wt") as stream:
                    stream.write(json.dumps(old) + "\n")
            for index in range(2):
                event = build_runtime_event(
                    loop_id="fresh", domain="earn", run_id=f"new-{index}", release_sha="b" * 40,
                    provider="deterministic", profile_alias=None, effect_class="publish",
                    succeeded=True, blocker=None, provider_receipt_id=f"receipt-{index}",
                    official_readback_ref=f"lm-proof://fresh/new-{index}",
                )
                event.update(timestamp=(now + timedelta(minutes=index)).isoformat(), effect_status="verified")
                append_runtime_event(path, event)
                projected = runtime_event.read_runtime_health_projection(path)
                self.assertFalse(projected["complete"])
                self.assertEqual(projected["history_status"], "health_history_gap")
                row = self.status_row(
                    "fresh", admission_class="revenue", registered_cadence={"start_interval_seconds": 300},
                    effect_class="publish", effect_status="verified", last_pass=event["timestamp"],
                    provider_receipt_id=event["provider_receipt_id"],
                    official_readback_ref=event["official_readback_ref"],
                    health_clocks=projected["clocks"]["fresh"], health_history_status=projected["history_status"],
                )
                value = health.project_health([row])
                self.assertEqual(value["jobs"][0]["facets"]["productivity"]["status"], "ok")
                self.assertEqual(value["jobs"][0]["facets"]["revenue"]["status"], "ok")
                self.assertEqual(health.health_exit_code(value), 0)
            later_at = now + timedelta(hours=6)

            class Later(health.datetime):
                @classmethod
                def now(cls, tz=None):
                    return later_at

            with patch.object(health, "datetime", Later):
                aged = health.project_health([row])
            self.assertEqual(aged["jobs"][0]["facets"]["revenue"]["status"], "blocked")
            self.assertTrue(health.revenue_attention(aged["jobs"][0]))
            self.assertEqual(health.health_exit_code(aged), 1)
            with path.open("a") as stream:
                stream.write('{"phase":"report"')
            pending = runtime_event.read_runtime_health_projection(path)
            self.assertEqual(pending["history_status"], "health_history_incomplete")
            row["health_history_status"] = pending["history_status"]
            self.assertEqual(health.project_health([row])["jobs"][0]["facets"]["revenue"]["status"], "unknown")

    def test_known_attempt_does_not_invent_a_missing_revenue_clock(self):
        now = health.datetime.now(health.timezone.utc).isoformat()
        row = self.status_row(
            "current", admission_class="revenue", registered_cadence={"start_interval_seconds": 300},
            last_terminal_result="running", effect_class="publish", effect_status="started",
            health_clocks={"last_attempt": now, "last_success": None, "last_effect": now,
                           "last_receipt": None, "last_verified_effect": None},
            health_history_status="health_history_gap",
        )
        value = health.project_health([row])
        job = value["jobs"][0]
        self.assertEqual(job["facets"]["productivity"]["status"], "ok")
        self.assertEqual(job["facets"]["revenue"], {"status": "unknown", "reason": "health_history_gap"})
        self.assertIsNone(job["clocks"]["last_success"])
        self.assertFalse(health.revenue_attention(job))
        self.assertEqual(health.health_exit_code(value), 1)
        self.assertIn("history_limited=1", health.render_human(value))

    def test_health_clocks_survive_rotation_and_long_cadence(self):
        from datetime import timedelta
        import runtime.loop.runtime_event as runtime_event

        weekly = build_runtime_event(
            loop_id="weekly", domain="growth", run_id="weekly-pass",
            release_sha="a" * 40, provider="deterministic", profile_alias=None,
            effect_class="none", succeeded=True, blocker=None,
        )
        weekly["timestamp"] = (health.datetime.now(health.timezone.utc)
                               - timedelta(days=6)).isoformat()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.jsonl")
            append_runtime_event(path, weekly)
            with patch.object(runtime_event, "_max_bytes", return_value=1):
                for index in range(3):
                    event = build_runtime_event(
                        loop_id="hourly", domain="growth", run_id=f"hourly-{index}",
                        release_sha="b" * 40, provider="deterministic", profile_alias=None,
                        effect_class="none", succeeded=True, blocker=None,
                    )
                    append_runtime_event(path, event)
            with patch.object(gzip, "open", side_effect=AssertionError("steady-state archive scan")):
                latest = lm_loop._last_event(directory, "weekly", include_health_clocks=True)
            self.assertEqual(latest["_health_clocks"]["last_success"], weekly["timestamp"])
            self.assertNotIn("_health_history_status", latest)

    def test_104_journal_clocks_use_the_durable_projection_without_reindexing(self):
        import runtime.loop.runtime_event as runtime_event

        with tempfile.TemporaryDirectory() as directory:
            roots = []
            for index in range(104):
                root = Path(directory, str(index))
                event = build_runtime_event(
                    loop_id=f"job-{index}", domain="system", run_id="test-pass",
                    release_sha="a" * 40, provider="deterministic", profile_alias=None,
                    effect_class="none", succeeded=True, blocker=None,
                )
                append_runtime_event(root / "events.jsonl", event)
                roots.append(root)
            started = time.monotonic()
            with patch.object(runtime_event, "_project_health_lines",
                              wraps=runtime_event._project_health_lines) as project_lines, \
                 patch.object(gzip, "open", side_effect=AssertionError("archive reindex")):
                for index, root in enumerate(roots):
                    latest = lm_loop._last_event(str(root), f"job-{index}", include_health_clocks=True)
                    self.assertEqual(latest["_health_clocks"]["last_success"], latest["timestamp"])
                    self.assertNotIn("_health_history_status", latest)
            self.assertTrue(all(not call.args[1] for call in project_lines.call_args_list))
            self.assertLess(time.monotonic() - started, lm_loop.HEALTH_SNAPSHOT_TIMEOUT_SECONDS)

    def test_history_never_replaces_a_newer_current_terminal_with_an_old_projection(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        loop_id = "compute-proxy"
        registry["loops"] = {loop_id: registry["loops"][loop_id]}
        current = build_runtime_event(
            loop_id=loop_id, domain="system", run_id="failed", release_sha="b" * 40,
            provider="deterministic", profile_alias=None, effect_class="none",
            succeeded=False, blocker="entrypoint_exit_1",
        )
        current["timestamp"] = "2026-10-22T00:01:00+00:00"
        for timestamp in ("2026-10-22T00:00:00+00:00", current["timestamp"]):
            with self.subTest(projection_timestamp=timestamp):
                stale = {**current, "status": "pass", "blocker": None, "event_id": "a" * 24,
                         "run_id": "older", "timestamp": timestamp}
                with patch.object(lm_loop, "collect_live", return_value=({}, {}, {loop_id: current}, {}, set())), \
                     patch.object(lm_loop, "_admission_effect_unknown_occurrences", return_value={}), \
                     patch.object(lm_loop, "_resolved_effect_unknown_occurrences", return_value=set()), \
                     patch.object(lm_loop, "_latest_harness_failure", return_value=None), \
                     patch.object(lm_loop, "_last_event", return_value=stale):
                    rows = lm_loop.snapshot(registry, loop_id, include_effect_details=False, include_health_clocks=True)
                self.assertEqual(rows[0]["last_terminal_result"], "fail")
                self.assertEqual(rows[0]["run_id"], "failed")
                self.assertEqual(rows[0]["health_history_status"], "health_history_gap")

    def test_snapshot_exposes_current_rows_before_one_collection_history_timeout(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        loop_id = "compute-proxy"
        registry["loops"] = {loop_id: registry["loops"][loop_id]}
        event = build_runtime_event(
            loop_id=loop_id, domain="system", run_id="failed", release_sha="a" * 40,
            provider="deterministic", profile_alias=None, effect_class="none",
            succeeded=False, blocker="entrypoint_exit_1",
        )
        current_rows = []
        with patch.object(lm_loop, "collect_live", return_value=({}, {}, {loop_id: event}, {}, set())) as collect, \
             patch.object(lm_loop, "_admission_effect_unknown_occurrences", return_value={}), \
             patch.object(lm_loop, "_resolved_effect_unknown_occurrences", return_value=set()), \
             patch.object(lm_loop, "_latest_harness_failure", return_value=None), \
             patch.object(lm_loop, "_last_event", side_effect=health.HealthTimeout("history")):
            with self.assertRaises(health.HealthTimeout):
                lm_loop.snapshot(registry, loop_id, include_effect_details=False,
                                 include_health_clocks=True, current_rows=current_rows)
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(current_rows[0]["last_terminal_result"], "fail")
        self.assertEqual(current_rows[0]["blocker"], "entrypoint_exit_1")

    def test_health_clocks_survive_a_newer_failed_runtime_event(self):
        loop_id = "agentmail-nudge"

        def event(run_id, timestamp, *, succeeded, effect_status, receipt=None):
            value = build_runtime_event(
                loop_id=loop_id,
                domain="earn",
                run_id=run_id,
                release_sha="a" * 40,
                provider="shared-agent-runner",
                profile_alias=None,
                effect_class="message",
                succeeded=succeeded,
                blocker=None if succeeded else "entrypoint_exit_1",
                provider_receipt_id=receipt,
            )
            value["timestamp"] = timestamp
            value["effect_status"] = effect_status
            return validate_runtime_event(value)

        history = [
            event("success", "2026-10-01T00:01:00+00:00", succeeded=True,
                  effect_status="planned"),
            event("effect", "2026-10-01T00:02:00+00:00", succeeded=False,
                  effect_status="verified"),
            event("receipt", "2026-10-01T00:03:00+00:00", succeeded=False,
                  effect_status="unknown", receipt="receipt-3"),
            event("latest-failure", "2026-10-01T00:04:00+00:00", succeeded=False,
                  effect_status="unknown"),
        ]
        registry = json.loads(
            (ROOT / "config/loop-registry.json").read_text(encoding="utf-8")
        )
        registry["loops"] = {loop_id: registry["loops"][loop_id]}
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "events.jsonl").write_text(
                "\n".join(json.dumps(row) for row in history) + "\n",
                encoding="utf-8",
            )
            latest = lm_loop._last_event(
                directory, loop_id, include_health_clocks=True,
            )
        with patch("runtime.loop.lm_loop._latest_harness_failure", return_value=None):
            status = lm_loop.status_rows(
                registry,
                loaded={},
                disabled={},
                events={loop_id: latest},
                installed_releases={},
                product_by_job={},
            )[0]

        clocks = health.project_health([status])["jobs"][0]["clocks"]
        self.assertEqual(clocks, {
            "last_attempt": "2026-10-01T00:04:00+00:00",
            "last_success": "2026-10-01T00:01:00+00:00",
            "last_effect": "2026-10-01T00:02:00+00:00",
            "last_receipt": "2026-10-01T00:03:00+00:00",
        })

    def test_health_clocks_read_rotated_journals_when_the_live_one_lacks_a_daily_run(self):
        # 2026-10-18: the shared journal rotates every ~15k lines (~16 h), so a daily loop's
        # last pass lived only in the newest archive and health read it as telemetry_gap "never".
        def event(loop_id, run_id, timestamp):
            value = build_runtime_event(
                loop_id=loop_id, domain="growth", run_id=run_id, release_sha="a" * 40,
                provider="deterministic", profile_alias=None, effect_class="none",
                succeeded=True, blocker=None,
            )
            value["timestamp"] = timestamp
            return json.dumps(validate_runtime_event(value)) + "\n"

        with tempfile.TemporaryDirectory() as directory:
            with gzip.open(Path(directory, "events-20261018T062703209718Z.jsonl.gz"), "wt",
                           encoding="utf-8") as archive:
                archive.write(event("capafy-goal-monitor", "daily", "2026-10-18T01:35:39+00:00"))
            Path(directory, "events.jsonl").write_text(
                event("capafy-goal-monitor-hourly", "hourly", "2026-10-18T07:27:49+00:00"),
                encoding="utf-8",
            )
            cache = {}
            self.assertIsNone(lm_loop._last_event(directory, "capafy-goal-monitor", cache))
            latest = lm_loop._last_event(
                directory, "capafy-goal-monitor", cache, include_health_clocks=True,
            )

        self.assertIsNotNone(latest)
        self.assertEqual(latest["_health_clocks"]["last_success"], "2026-10-18T01:35:39+00:00")

    def test_a_corrupt_rotated_archive_does_not_crash_health(self):
        # A deflate-corrupt gz raises zlib.error, which is not an OSError/EOFError.
        with tempfile.TemporaryDirectory() as directory:
            body = gzip.compress(b'{"loop_id": "x"}\n' * 200)
            Path(directory, "events-20261018T062703209718Z.jsonl.gz").write_bytes(
                body[:20] + b"\xff" * 40 + body[60:])
            Path(directory, "events.jsonl").write_text("", encoding="utf-8")
            latest = lm_loop._last_event(
                directory, "capafy-goal-monitor", include_health_clocks=True,
            )
        self.assertIsNone(latest)

    def test_health_clock_projection_reads_a_shared_journal_once(self):
        history = []
        for loop_id in ("agentmail-nudge", "agentmail-reply"):
            value = build_runtime_event(
                loop_id=loop_id,
                domain="earn",
                run_id=f"{loop_id}-run",
                release_sha="a" * 40,
                provider="shared-agent-runner",
                profile_alias=None,
                effect_class="message",
                succeeded=True,
                blocker=None,
            )
            history.append(validate_runtime_event(value))
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "events.jsonl").write_text(
                "\n".join(json.dumps(row) for row in history) + "\n",
                encoding="utf-8",
            )
            cache = {}
            with patch.object(lm_loop, "read_runtime_health_projection",
                              wraps=lm_loop.read_runtime_health_projection) as reads:
                first = lm_loop._last_event(
                    directory, "agentmail-nudge", cache,
                    include_health_clocks=True,
                )
                second = lm_loop._last_event(
                    directory, "agentmail-reply", cache,
                    include_health_clocks=True,
                )

        self.assertEqual(first["loop_id"], "agentmail-nudge")
        self.assertEqual(second["loop_id"], "agentmail-reply")
        self.assertEqual(reads.call_count, 1)

    def test_health_clock_projection_reuses_shared_journal_for_running_pids(self):
        history = []
        loop_pids = (("agentmail-nudge", "101"), ("agentmail-reply", "202"))
        for loop_id, pid in loop_pids:
            report = build_runtime_event(
                loop_id=loop_id,
                domain="earn",
                run_id=f"{loop_id}-past",
                release_sha="a" * 40,
                provider="shared-agent-runner",
                profile_alias=None,
                effect_class="message",
                succeeded=True,
                blocker=None,
            )
            running = build_runtime_start_event(
                loop_id=loop_id,
                domain="earn",
                run_id=f"{loop_id}-{pid}",
                release_sha="a" * 40,
                provider="shared-agent-runner",
                profile_alias=None,
                effect_class="message",
                product_loop_id="agentmail",
                job_id=loop_id,
                owner_id=loop_id,
                wake_id=f"wake-{pid}",
                occurrence_id=f"{loop_id}:wake-{pid}",
                loaded_argv_sha256="b" * 64,
                loaded_env_sha256="c" * 64,
            )
            history.extend((report, running))
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "events.jsonl").write_text(
                "\n".join(json.dumps(row) for row in history) + "\n",
                encoding="utf-8",
            )
            cache = {}
            selected = []
            with patch.object(lm_loop, "read_runtime_health_projection",
                              wraps=lm_loop.read_runtime_health_projection) as reads:
                for loop_id, pid in loop_pids:
                    selected.append(lm_loop._last_event(
                        directory,
                        loop_id,
                        cache,
                        running_pid=pid,
                        include_health_clocks=True,
                    ))

        self.assertEqual([event["phase"] for event in selected], ["execute", "execute"])
        self.assertEqual(reads.call_count, 1)

    def test_health_clocks_include_a_newer_running_execute_event(self):
        loop_id = "agentmail-nudge"
        report = build_runtime_event(
            loop_id=loop_id,
            domain="earn",
            run_id="past-success",
            release_sha="a" * 40,
            provider="shared-agent-runner",
            profile_alias=None,
            effect_class="message",
            succeeded=True,
            blocker=None,
        )
        report["timestamp"] = "2026-10-01T00:01:00+00:00"
        running = build_runtime_start_event(
            loop_id=loop_id,
            domain="earn",
            run_id="current-123",
            release_sha="a" * 40,
            provider="shared-agent-runner",
            profile_alias=None,
            effect_class="message",
            product_loop_id="agentmail",
            job_id=loop_id,
            owner_id=loop_id,
            wake_id="current-123",
            occurrence_id=f"{loop_id}:current-123",
            loaded_argv_sha256="b" * 64,
            loaded_env_sha256="c" * 64,
        )
        running["timestamp"] = "2026-10-01T00:02:00+00:00"
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "events.jsonl").write_text(
                "\n".join(json.dumps(row) for row in (report, running)) + "\n",
                encoding="utf-8",
            )
            latest = lm_loop._last_event(
                directory, loop_id, include_health_clocks=True,
            )

        self.assertEqual(latest["phase"], "report")
        self.assertEqual(latest["_health_clocks"]["last_attempt"], running["timestamp"])
        self.assertEqual(latest["_health_clocks"]["last_effect"], running["timestamp"])

    def test_health_cli_projects_snapshot_runtime_error_as_typed_gap(self):
        output = io.StringIO()
        raised = None
        try:
            with (
                patch("runtime.loop.lm_loop.snapshot", side_effect=RuntimeError("read failed")),
                redirect_stdout(output),
            ):
                result = lm_loop_main(["health", "--json"])
        except RuntimeError as exc:
            raised = exc
            result = None

        self.assertIsNone(raised)
        self.assertEqual(result, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema_version"], "lm-loop.health.v1")
        expected_jobs = len(json.loads(
            (ROOT / "config/loop-registry.json").read_text()
        )["loops"])
        self.assertEqual(payload["summary"]["telemetry_gap"], expected_jobs)
        self.assertTrue(all(
            job["diagnostic"]["error_class"] == "health_snapshot_error"
            for job in payload["jobs"]
        ))

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

    def test_pre_entrypoint_capacity_block_is_not_effect_unknown(self):
        for reason in ("resource_capacity_busy", "disk_floor_low"):
            with self.subTest(reason=reason):
                event = build_runtime_event(
                    loop_id="capacity-blocked-message", domain="earn", run_id="run-1",
                    release_sha="b" * 40, provider="deterministic", profile_alias=None,
                    effect_class="message", succeeded=False, deferred=True,
                    blocker=f"host_admission_deferred:{reason}", exit_code=75,
                )
                row = self.status_row(
                    "capacity-blocked-message", effect_class=event["effect_class"],
                    effect_status=event["effect_status"],
                    last_terminal_result=event["status"], blocker=event["blocker"],
                    error_class=event["error_class"], retryable=event["retryable"],
                    next_action=event["next_action"],
                )
                job = health.project_health([row])["jobs"][0]
                self.assertEqual(job["state"], "failed")
                self.assertEqual(job["facets"]["effect_safety"]["status"], "not_applicable")

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
        expected_jobs = len(json.loads(
            (ROOT / "config/loop-registry.json").read_text()
        )["loops"])
        self.assertEqual(payload["summary"]["total"], expected_jobs)
        self.assertEqual(payload["summary"]["telemetry_gap"], expected_jobs)
        self.assertTrue(all(
            job["diagnostic"]["error_class"] == "health_snapshot_timeout"
            for job in payload["jobs"]
        ))

    def test_history_timeout_preserves_current_states_without_revenue_inference(self):
        rows = [
            self.status_row("current-ok", admission_class="revenue",
                            registered_cadence={"start_interval_seconds": 3600}),
            self.status_row("current-failure", last_terminal_result="blocked",
                            error_class="host_admission_deferred:disk_floor_low",
                            blocker="host_admission_deferred:disk_floor_low"),
            self.status_row("current-fence", admission_effect_unknown=True,
                            effect_class="publish", effect_status="unknown"),
        ]
        output = io.StringIO()

        def slow_history(*_args, **kwargs):
            kwargs["current_rows"].extend(rows)
            time.sleep(0.5)
            return rows

        started = time.monotonic()
        with (
            patch.object(lm_loop, "snapshot", side_effect=slow_history),
            patch.object(lm_loop, "HEALTH_SNAPSHOT_TIMEOUT_SECONDS", 0.02),
            redirect_stdout(output),
        ):
            result = lm_loop_main(["health", "--json"])
        self.assertLess(time.monotonic() - started, 0.3)
        self.assertEqual(result, 1)
        value = json.loads(output.getvalue())
        self.assertEqual(value["summary"]["total"], 3)
        self.assertEqual(value["summary"]["healthy"], 1)
        self.assertEqual(value["summary"]["failed"], 1)
        self.assertEqual(value["summary"]["safely_fenced"], 1)
        self.assertEqual(value["summary"]["telemetry_gap"], 0)
        jobs = {job["job_id"]: job for job in value["jobs"]}
        self.assertEqual(jobs["current-failure"]["diagnostic"]["error_class"],
                         "host_admission_deferred:disk_floor_low")
        self.assertEqual(jobs["current-fence"]["facets"]["effect_safety"]["status"], "blocked")
        self.assertEqual(jobs["current-ok"]["facets"]["productivity"],
                         {"status": "unknown", "reason": "health_history_timeout"})
        self.assertEqual(jobs["current-ok"]["facets"]["revenue"],
                         {"status": "unknown", "reason": "health_history_timeout"})
        self.assertFalse(health.revenue_attention(jobs["current-ok"]))
        Draft202012Validator(health.health_json_schema()).validate(value)

    def test_missing_history_does_not_enqueue_repairs_for_current_healthy_owner(self):
        from runtime.loop.health_observer import observe_health

        for history_status in ("health_history_timeout", "health_history_gap",
                               "health_history_incomplete", "health_history_busy"):
            with self.subTest(history_status=history_status):
                value = health.project_health([self.status_row(
                    "current-ok", admission_class="revenue",
                    registered_cadence={"start_interval_seconds": 3600},
                    health_history_status=history_status,
                )])
                self.assertEqual(value["jobs"][0]["facets"]["productivity"]["reason"], history_status)
                self.assertEqual(health.health_exit_code(value), 1)
                self.assertIn("history_limited=1", health.render_human(value))
                self.assertFalse(health.revenue_attention(value["jobs"][0]))
                with tempfile.TemporaryDirectory() as directory:
                    intents = []
                    result = observe_health(
                        value, Path(directory),
                        intent_builder=lambda job, run_id: intents.append(job),
                    )
                self.assertEqual(intents, [])
                self.assertEqual(result["recovery_intents"], [])

    def test_health_deadline_cannot_be_swallowed_as_a_file_read_error(self):
        with patch.object(Path, "read_text", side_effect=health.HealthTimeout("deadline")):
            with self.assertRaises(health.HealthTimeout):
                lm_loop._last_event("/unused-health-fixture", "current-ok")

    def test_health_cli_deadline_includes_slow_fleet_projection(self):
        output = io.StringIO()
        original_project = health.project_health
        rows = [self.status_row(f"slow-{index}") for index in range(176)]

        def slow_fleet_project(rows, **kwargs):
            if rows and rows[0].get("error_class") == "health_snapshot_timeout":
                return original_project(rows, **kwargs)
            return original_project(
                rows,
                adapter=lambda row: (time.sleep(0.5), row)[1],
                adapter_timeout_seconds=0.5,
                **kwargs,
            )

        started = time.monotonic()
        with (
            patch("runtime.loop.lm_loop.snapshot", return_value=rows),
            patch("runtime.loop.lm_loop.project_health", side_effect=slow_fleet_project),
            patch("runtime.loop.lm_loop.HEALTH_SNAPSHOT_TIMEOUT_SECONDS", 0.02),
            redirect_stdout(output),
        ):
            result = lm_loop_main(["health", "--json"])
        elapsed = time.monotonic() - started

        self.assertEqual(result, 1)
        self.assertLess(elapsed, 0.3)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema_version"], "lm-loop.health.v1")
        self.assertEqual(payload["summary"]["telemetry_gap"], 176)
        self.assertTrue(all(
            job["diagnostic"]["error_class"] == "health_projection_timeout"
            for job in payload["jobs"]
        ))

    def test_snapshot_time_consumption_reduces_projection_deadline(self):
        output = io.StringIO()
        rows = [self.status_row("snapshot-clock")]
        projected = health.project_health(rows)

        class Clock:
            now = 100.0

            def monotonic(self):
                return self.now

        clock = Clock()

        def consuming_snapshot(*_args, **_kwargs):
            clock.now += 7.0
            return rows

        with (
            patch("runtime.loop.lm_loop.time", clock),
            patch("runtime.loop.lm_loop.snapshot", side_effect=consuming_snapshot),
            patch("runtime.loop.lm_loop.project_health", return_value=projected) as project,
            patch("runtime.loop.lm_loop.HEALTH_SNAPSHOT_TIMEOUT_SECONDS", 30.0),
            redirect_stdout(output),
        ):
            result = lm_loop_main(["health", "--json"])

        self.assertEqual(result, 0)
        project.assert_called_once()
        project_rows, = project.call_args.args
        self.assertEqual(project_rows, rows)
        self.assertEqual(project.call_args.kwargs, {
            "storage_snapshot": None,
            "scope": "fleet",
            "target": None,
            "deadline_monotonic": 130.0,
        })
        # Current state and history share the same seven-second collection.
        self.assertEqual(project.call_args.kwargs["deadline_monotonic"] - clock.now, 23.0)
        self.assertEqual(json.loads(output.getvalue()), projected)

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

    def test_health_schema_and_python_validator_reject_the_same_invalid_shapes(self):
        validator = Draft202012Validator(
            health.health_json_schema(), format_checker=FormatChecker(),
        )
        base = health.project_health([self.status_row()])

        def changed(mutator):
            value = copy.deepcopy(base)
            mutator(value)
            return value

        fixtures = {
            "numeric-product-loop": changed(lambda value: value["jobs"][0].update({
                "product_loop_id": 7, "system_role": None,
            })),
            "empty-product-loop": changed(lambda value: value["jobs"][0].update({
                "product_loop_id": "", "system_role": None,
            })),
            "empty-job-id": changed(
                lambda value: value["jobs"][0].update({"job_id": ""})
            ),
            "empty-label": changed(
                lambda value: value["jobs"][0].update({"label": ""})
            ),
            "fleet-target": changed(
                lambda value: value["scope"].update({"target": "unexpected"})
            ),
            "loop-target-null": changed(
                lambda value: value["scope"].update({"kind": "loop", "target": None})
            ),
            "bad-system-role": changed(
                lambda value: value["jobs"][0].update({"system_role": "worker"})
            ),
            "extra-job-field": changed(
                lambda value: value["jobs"][0].update({"extra": True})
            ),
            "missing-diagnostic-field": changed(
                lambda value: value["jobs"][0]["diagnostic"].pop("owner_id")
            ),
            "bad-generated-at": changed(
                lambda value: value.update({"generated_at": "not-a-date-time"})
            ),
            "space-separated-generated-at": changed(
                lambda value: value.update({
                    "generated_at": "2026-10-01 00:00:00+00:00",
                })
            ),
        }

        for name, value in fixtures.items():
            with self.subTest(name=name):
                self.assertFalse(validator.is_valid(value))
                accepted = True
                try:
                    health.validate_health_document(value)
                except ValueError:
                    accepted = False
                self.assertFalse(accepted)



class RevenueOutageTest(unittest.TestCase):
    """SH1: a revenue lane idle for >2x its cadence is an outage even when fenced."""

    @staticmethod
    def ago(hours):
        from datetime import datetime, timedelta, timezone
        return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    def row(self, loop_id="lane", *, idle_hours=1.0, cadence=None, **overrides):
        row = LmLoopHealthTest.status_row(
            loop_id, product_loop_id=loop_id, system_role=None,
            effect_class="publish", effect_status="verified",
            admission_class="revenue",
            registered_cadence=cadence or {"start_interval_seconds": 300},
            health_clocks={"last_attempt": self.ago(0.1), "last_success": None,
                           "last_effect": self.ago(0.1), "last_receipt": None,
                           "last_verified_effect": self.ago(idle_hours)},
        )
        row.update(overrides)
        return row

    def revenue(self, row):
        return health.project_health([row])["jobs"][0]["facets"]["revenue"]

    def test_fenced_revenue_lane_idle_past_twice_cadence_is_outage_with_occurrences(self):
        value = health.project_health([self.row(
            "writer", idle_hours=36, admission_effect_unknown=True,
            admission_effect_unknown_occurrences=["writer:occ-1", "writer:occ-2"],
        )])
        job = value["jobs"][0]
        self.assertEqual(job["state"], "safely_fenced")
        self.assertEqual(job["facets"]["revenue"]["status"], "blocked")
        reason = job["facets"]["revenue"]["reason"]
        self.assertTrue(reason.startswith("revenue_outage"))
        self.assertIn("resource_effect_unknown", reason)
        self.assertIn("writer:occ-1", reason)

    def test_healthy_state_revenue_outage_names_blocker_and_exits_nonzero(self):
        value = health.project_health([self.row(
            "lancers", idle_hours=5, error_class="disk_floor_low",
        )])
        job = value["jobs"][0]
        self.assertEqual(job["facets"]["revenue"]["status"], "blocked")
        self.assertIn("disk_floor_low", job["facets"]["revenue"]["reason"])
        self.assertEqual(health.health_exit_code(value), 1)

    def test_fresh_revenue_lane_is_ok_and_non_revenue_is_not_applicable(self):
        self.assertEqual(self.revenue(self.row(idle_hours=1.5))["status"], "ok")
        self.assertEqual(
            self.revenue(self.row(admission_class="borrow", idle_hours=99))["status"],
            "not_applicable")
        value = health.project_health([self.row(idle_hours=1.5)])
        self.assertEqual(health.health_exit_code(value), 0)

    def test_started_only_effect_clock_does_not_hide_outage(self):
        # A fenced wake writes execute/effect_status=started every few minutes;
        # that is not an effect, so it must not refresh the revenue clock.
        clocks = {"last_attempt": self.ago(0.1), "last_success": self.ago(40),
                  "last_effect": self.ago(0.1), "last_receipt": None}
        self.assertEqual(self.revenue(self.row(health_clocks=clocks))["status"], "blocked")

    def test_projection_records_verified_effect_only_from_reports(self):
        def event(ts, phase, status, effect_status):
            value = build_runtime_event(
                loop_id="lane", domain="earn", run_id=f"run-{phase}-{status}",
                release_sha="a" * 40, provider="deterministic", profile_alias=None,
                effect_class="publish", succeeded=status == "pass", blocker=None,
            )
            return {**value, "timestamp": ts, "phase": phase,
                    "status": status, "effect_status": effect_status}
        events = [
            event("2026-10-16T01:00:00+00:00", "report", "pass", "verified"),
            event("2026-10-16T02:00:00+00:00", "execute", "running", "started"),
            event("2026-10-16T02:00:01+00:00", "report", "blocked", "unknown"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "events.jsonl")
            for value in events:
                append_runtime_event(path, value)
            latest = lm_loop._last_event(directory, "lane", include_health_clocks=True)
        clocks = latest["_health_clocks"]
        self.assertEqual(clocks["last_effect"], "2026-10-16T02:00:00+00:00")
        self.assertEqual(clocks["last_verified_effect"], "2026-10-16T01:00:00+00:00")

    def test_falls_back_to_last_success_when_no_effect_clock(self):
        clocks = {"last_attempt": None, "last_success": self.ago(3),
                  "last_effect": None, "last_receipt": None}
        self.assertEqual(self.revenue(self.row(health_clocks=clocks))["status"], "blocked")

    def test_calendar_cadence_uses_largest_gap_and_daily_lane_waits_two_days(self):
        daily = {"calendar_interval": {"Hour": 4, "Minute": 20}}
        self.assertEqual(self.revenue(self.row(cadence=daily, idle_hours=30))["status"], "ok")
        self.assertEqual(self.revenue(self.row(cadence=daily, idle_hours=49))["status"], "blocked")
        three = {"calendar_interval": [{"Hour": 8, "Minute": 0}, {"Hour": 12, "Minute": 0},
                                        {"Hour": 16, "Minute": 0}]}
        # largest gap is 16:00 -> 08:00 = 16h, threshold 32h
        self.assertEqual(self.revenue(self.row(cadence=three, idle_hours=30))["status"], "ok")
        self.assertEqual(self.revenue(self.row(cadence=three, idle_hours=33))["status"], "blocked")
        hourly = {"calendar_interval": {"Minute": 7}}
        self.assertEqual(self.revenue(self.row(cadence=hourly, idle_hours=1.9))["status"], "ok")
        self.assertEqual(self.revenue(self.row(cadence=hourly, idle_hours=2.1))["status"], "blocked")

    def test_unreadable_revenue_data_is_telemetry_gap_not_healthy(self):
        no_clock = {"last_attempt": None, "last_success": None,
                    "last_effect": None, "last_receipt": None}
        for overrides in ({"health_clocks": no_clock, "last_pass": None},
                          {"registered_cadence": {"keep_alive": "weird"}},
                          {"health_clocks": {**no_clock, "last_verified_effect": "garbage"}}):
            facet = self.revenue(self.row(**overrides))
            self.assertEqual(facet["status"], "unknown", overrides)
            self.assertTrue(facet["reason"].startswith("telemetry_gap"), overrides)
        value = health.project_health([self.row(health_clocks=no_clock, last_pass=None)])
        self.assertEqual(health.health_exit_code(value), 1)

    def test_status_rows_carry_admission_class_for_health(self):
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        loop_id = next(k for k, v in registry["loops"].items()
                       if v.get("admission_class") == "revenue")
        rows = lm_loop.status_rows(
            {**registry, "loops": {loop_id: registry["loops"][loop_id]}},
            loaded={}, disabled={}, events={}, installed_releases={},
            product_by_job={})
        self.assertEqual(rows[0]["admission_class"], "revenue")


if __name__ == "__main__":
    unittest.main()
