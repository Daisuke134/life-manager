import unittest
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import plistlib
import time
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import runtime.loop.lm_loop as lm_loop
from runtime.loop.lm_loop import (
    _admission_effect_unknown_owners, _last_event, _launchctl,
    _pending_admission_owners, _release_from_plist, _safe_launchctl,
    _state_root_from_plist,
    doctor_report, explain_status_row, main as lm_loop_main, snapshot, status_rows,
)
from runtime.loop.runtime_event import build_runtime_event
from runtime.loop.runtime_event import build_runtime_start_event


REGISTRY = {"schema_version": 2, "loops": {"example": {
    "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example.sh",
    "cadence": {"start_interval_seconds": 60}, "effect_class": "application",
    "state_root": "~/.local/state/life-manager/example",
    "log_root": "~/.local/state/life-manager/example/logs",
    "cleanup": {"max_runs": 10, "max_age_days": 7},
    "provider_route": "shared-agent-runner",
}}}


class LmLoopReadonlyTest(unittest.TestCase):
    def test_browser_resolution_joins_loop_registry_to_resolver_readback(self):
        registry = {"schema_version": 2, "loops": {"connector": {
            "label": "ai.anicca.connector", "domain": "system", "entrypoint": "bin/connector.sh",
            "cadence": {"start_interval_seconds": 60}, "effect_class": "none",
            "state_root": "~/.local/state/life-manager/connector",
            "log_root": "~/.local/state/life-manager/connector/logs",
            "cleanup": {"max_runs": 10, "max_age_days": 7},
            "provider_route": "deterministic",
            "browser_identity": "interactive:dais",
            "browser_target_owner": "connector-native",
        }}}
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(
                command, 0,
                stdout=json.dumps({
                    "identity": "interactive:dais",
                    "profile": "/tmp/daily-driver",
                    "endpoint": "http://[::1]:9222",
                    "uuid": "browser-uuid",
                    "pid": 1592,
                    "reachable": True,
                    "http_status": 200,
                    "websocket_url_valid": True,
                }), stderr="",
            )

        result = lm_loop.browser_resolution(
            registry, "connector", browser_registry="/tmp/browsers.toml", runner=run,
        )
        self.assertEqual(result, {
            "browser_identity": "interactive:dais",
            "browser_uuid": "browser-uuid",
            "derived_endpoint": "http://[::1]:9222",
            "http_status": 200,
            "lease_status": "not_checked",
            "loop_id": "connector",
            "profile": "/tmp/daily-driver",
            "process_owner": 1592,
            "target_owner": "connector-native",
            "websocket_url_valid": True,
        })
        self.assertEqual(calls[0][0][0:3], [sys.executable, str(Path(__file__).resolve().parents[3] / "skills/browser/resolve_cdp_endpoint.py"), "--registry"])
        self.assertEqual(calls[0][0][-2:], ["--identity", "interactive:dais"])
        self.assertEqual(calls[0][1]["capture_output"], True)
        self.assertEqual(calls[0][1]["text"], True)

    def test_browser_resolve_cli_returns_json_only(self):
        output = io.StringIO()
        value = {
            "browser_identity": "interactive:dais",
            "browser_uuid": "browser-uuid",
            "derived_endpoint": "http://[::1]:9222",
            "http_status": 200,
            "lease_status": "not_checked",
            "loop_id": "life-manager-connector-native",
            "profile": "/tmp/daily-driver",
            "process_owner": 1592,
            "target_owner": "life-manager-connector-native",
            "websocket_url_valid": True,
        }
        with (patch("runtime.loop.lm_loop.browser_resolution", return_value=value),
              redirect_stdout(output)):
            result = lm_loop_main(["browser", "resolve", "life-manager-connector-native", "--json"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), {"ok": True, **value})

    def test_browser_resolve_cli_accepts_connector_alias(self):
        output = io.StringIO()
        value = {
            "browser_identity": "interactive:dais",
            "browser_uuid": "browser-uuid",
            "derived_endpoint": "http://[::1]:9222",
            "http_status": 200,
            "lease_status": "not_checked",
            "loop_id": "life-manager-connector-native",
            "profile": "/tmp/daily-driver",
            "process_owner": 1592,
            "target_owner": "life-manager-connector-native",
            "websocket_url_valid": True,
        }
        with (patch("runtime.loop.lm_loop.browser_resolution", return_value=value) as resolve,
              redirect_stdout(output)):
            result = lm_loop_main(["browser", "resolve", "connector", "--json"])
        self.assertEqual(result, 0)
        resolve.assert_called_once()
        self.assertEqual(resolve.call_args.args[1], "connector")
        self.assertEqual(json.loads(output.getvalue()), {"ok": True, **value})

    def test_status_reports_typed_admission_read_failure(self):
        output = io.StringIO()
        with (patch(
                "runtime.loop.lm_loop.snapshot",
                side_effect=sqlite3.OperationalError("database is locked"),
             ),
             redirect_stdout(output)):
            self.assertEqual(lm_loop_main(["status", "example"]), 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["error"], "admission_fence_read_failed")
        self.assertEqual(payload["error_class"], "admission_database_locked")
        self.assertTrue(payload["retryable"])
        self.assertEqual(payload["next_action"], "retry_admission_read")

    def test_pending_admission_read_retries_transient_sqlite_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "admission-v2.sqlite3"
            database.touch()
            calls = []

            class Connection:
                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

                def execute(self, *_):
                    class Cursor:
                        def fetchall(self):
                            return [("queued-owner",)]

                    return Cursor()

            def connect(*_args, **_kwargs):
                calls.append(True)
                if len(calls) == 1:
                    raise sqlite3.OperationalError("database is locked")
                return Connection()

            with (patch("runtime.loop.lm_loop.admission_root", return_value=Path(directory)),
                  patch("runtime.loop.lm_loop.sqlite3.connect", side_effect=connect),
                  patch("runtime.loop.lm_loop.time.sleep")):
                self.assertEqual(_pending_admission_owners(), {"queued-owner"})
            self.assertEqual(len(calls), 2)

    def test_effect_fence_read_does_not_turn_sqlite_lock_into_empty_fence_set(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "admission-v2.sqlite3"
            database.touch()
            with (patch("runtime.loop.lm_loop.admission_root", return_value=Path(directory)),
                  patch(
                      "runtime.loop.lm_loop.sqlite3.connect",
                      side_effect=sqlite3.OperationalError("database is locked"),
                  ),
                  patch("runtime.loop.lm_loop.time.sleep")):
                with self.assertRaisesRegex(sqlite3.OperationalError, "database is locked"):
                    _admission_effect_unknown_owners()

    def test_launchctl_readback_does_not_require_disk_tempfiles(self):
        completed = subprocess.CompletedProcess(
            ["launchctl", "list"], 0, stdout="loaded\n", stderr="",
        )
        with patch("runtime.loop.lm_loop.subprocess.run", return_value=completed) as run:
            self.assertEqual(_launchctl("list"), "loaded\n")
        self.assertEqual(run.call_args.args[0], ["launchctl", "list"])
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertTrue(run.call_args.kwargs["text"])
        self.assertEqual(run.call_args.kwargs["timeout"], 15)

    def test_safe_launchctl_keeps_stdout_and_stderr_in_memory(self):
        completed = subprocess.CompletedProcess(
            ["launchctl-safe", "print", "gui/501/example"], 7,
            stdout="stdout\n", stderr="stderr\n",
        )
        with patch("runtime.loop.lm_loop.subprocess.run", return_value=completed) as run:
            code, output = _safe_launchctl(
                Path("/tmp/launchctl-safe"), ["print", "gui/501/example"],
            )
        self.assertEqual((code, output), (7, "stdout\nstderr\n"))
        self.assertEqual(
            run.call_args.args[0],
            ["/tmp/launchctl-safe", "print", "gui/501/example"],
        )
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertTrue(run.call_args.kwargs["text"])
        self.assertEqual(run.call_args.kwargs["timeout"], 30)

    def test_status_exposes_complete_diagnostic_contract_and_catalog_product(self):
        event = build_runtime_event(
            loop_id="example", domain="earn", run_id="run-1", release_sha="b" * 40,
            provider="deterministic", profile_alias=None, effect_class="application",
            succeeded=False, blocker="entrypoint_exit_1", exit_code=1,
            product_loop_id=None, job_id="example", owner_id="example",
            wake_id="wake-1", claimed_occurrence_id="example:occurrence-1",
            loaded_argv_sha256="c" * 64, loaded_env_sha256="d" * 64,
        )
        row = status_rows(
            REGISTRY, loaded={}, disabled={}, events={"example": event},
            installed_releases={"ai.anicca.example": "b" * 40},
            product_by_job={"example": "connector"},
        )[0]
        self.assertTrue(row["diagnostic_complete"])
        self.assertEqual(row["diagnostic_missing_fields"], [])
        self.assertEqual(row["product_loop_id"], "connector")
        self.assertEqual(row["job_id"], "example")
        self.assertEqual(row["owner_id"], "example")
        self.assertEqual(row["run_id"], "run-1")
        self.assertEqual(row["wake_id"], "wake-1")
        self.assertEqual(row["occurrence_id"], "example:occurrence-1")
        self.assertEqual(row["loaded_argv_sha256"], "c" * 64)
        self.assertEqual(row["loaded_env_sha256"], "d" * 64)
        self.assertEqual(row["exit_code"], 1)
        self.assertEqual(row["failure_layer"], "entrypoint")
        self.assertEqual(row["error_class"], "entrypoint_exit_1")
        self.assertFalse(row["retryable"])
        self.assertEqual(row["next_action"], "official_readback_required")
        self.assertEqual(row["evidence_refs"], event["evidence_refs"])

    def test_status_explain_projects_cause_effect_and_honest_gaps(self):
        event = build_runtime_event(
            loop_id="example", domain="earn", run_id="run-1", release_sha="b" * 40,
            provider="deterministic", profile_alias=None, effect_class="application",
            succeeded=False, blocker="entrypoint_exit_1", exit_code=1,
            product_loop_id=None, job_id="example", owner_id="example",
            wake_id="wake-1", claimed_occurrence_id="example:occurrence-1",
            loaded_argv_sha256="c" * 64, loaded_env_sha256="d" * 64,
        )
        row = status_rows(
            REGISTRY, loaded={}, disabled={}, events={"example": event},
            installed_releases={"ai.anicca.example": "b" * 40},
        )[0]
        explained = explain_status_row(row)
        self.assertEqual(explained["schema_version"], "lm-loop.status-explain.v1")
        self.assertEqual(explained["loop_id"], "example")
        self.assertEqual(explained["release_sha"], "b" * 40)
        self.assertEqual(explained["occurrence"]["occurrence_id"], "example:occurrence-1")
        self.assertEqual(explained["cause_chain"][0]["stage"], "runtime")
        self.assertEqual(explained["cause_chain"][1]["stage"], "failure")
        self.assertEqual(explained["cause_chain"][1]["error_class"], "entrypoint_exit_1")
        self.assertEqual(explained["effect"]["status"], "unknown")
        self.assertEqual(explained["effect"]["provider_receipt_id"], None)
        self.assertEqual(explained["effect"]["evidence_refs"], event["evidence_refs"])
        self.assertEqual(explained["action_history_status"], "not_reported")
        self.assertEqual(explained["counter_status"], "not_reported")

    def test_status_explain_cli_accepts_connector_alias_and_json(self):
        output = io.StringIO()
        row = {
            "loop_id": "life-manager-connector-native",
            "label": "ai.anicca.life-manager-connector-native",
            "launchd_state": "loaded-idle",
            "pid": None,
            "last_exit": "0",
            "installed_release_sha": "b" * 40,
            "event_release_sha": "b" * 40,
            "owner_id": "connector-owner",
            "run_id": "run-1",
            "wake_id": "wake-1",
            "occurrence_id": "occurrence-1",
            "phase": "report",
            "last_terminal_result": "blocked",
            "failure_layer": "browser",
            "error_class": "browser_open_failed",
            "retryable": True,
            "next_action": "resolve_browser_endpoint",
            "blocker": "browser_endpoint_unavailable",
            "effect_class": "none",
            "effect_status": "not_applicable",
            "provider_receipt_id": None,
            "official_readback_ref": None,
            "evidence_refs": ["lm-loop://connector/run-1/summary.json"],
            "diagnostic_complete": True,
            "diagnostic_missing_fields": [],
            "diagnostic_error": None,
        }
        with (patch("runtime.loop.lm_loop.snapshot", return_value=[row]) as observe,
              redirect_stdout(output)):
            result = lm_loop_main(["status", "connector", "--explain", "--json"])
        self.assertEqual(result, 0)
        observe.assert_called_once()
        self.assertEqual(observe.call_args.args[1], "life-manager-connector-native")
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema_version"], "lm-loop.status-explain.v1")
        self.assertEqual(payload["target"], "life-manager-connector-native")
        self.assertEqual(payload["rows"][0]["next_action"], "resolve_browser_endpoint")

    def test_status_rejects_unknown_option_before_reading_state(self):
        output = io.StringIO()
        with (patch("runtime.loop.lm_loop.snapshot") as observe,
              redirect_stdout(output)):
            result = lm_loop_main(["status", "connector", "--bogus"])
        self.assertEqual(result, 2)
        observe.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["error"], "unknown status option: --bogus")

    def test_old_event_remains_visible_but_diagnostic_is_incomplete(self):
        event = {
            "timestamp": "2026-08-28T00:00:00Z", "status": "pass",
            "release_sha": "b" * 40, "effect_status": "not_applicable",
            "blocker": None, "run_id": "old-run", "phase": "report",
            "evidence_refs": ["lm-loop://example/old-run/summary.json"],
        }
        row = status_rows(
            REGISTRY, loaded={}, disabled={}, events={"example": event},
            installed_releases={"ai.anicca.example": "b" * 40},
            product_by_job={"example": "connector"},
        )[0]
        self.assertFalse(row["diagnostic_complete"])
        self.assertIn("owner_id", row["diagnostic_missing_fields"])
        self.assertEqual(row["product_loop_id"], "connector")
        self.assertEqual(row["job_id"], "example")
        self.assertEqual(row["run_id"], "old-run")

    def test_running_legacy_event_exposes_reload_action(self):
        event = {
            "timestamp": "2026-08-28T00:00:00Z", "status": "running",
            "release_sha": "b" * 40, "effect_status": "not_applicable",
            "blocker": None, "run_id": "old-run-123", "phase": "execute",
            "evidence_refs": ["lm-loop://example/old-run-123/summary.json"],
        }
        registry = {"schema_version": 2, "loops": {"example": {
            **REGISTRY["loops"]["example"],
            "cadence": {"keep_alive": True},
        }}}
        row = status_rows(
            registry,
            loaded={"ai.anicca.example": {"pid": "123", "last_exit": "0"}},
            disabled={},
            events={"example": event},
            installed_releases={"ai.anicca.example": "b" * 40},
        )[0]
        self.assertFalse(row["diagnostic_complete"])
        self.assertEqual(row["diagnostic_error"], "legacy_runtime_event_schema")
        self.assertEqual(row["error_class"], "legacy_runtime_event_schema")
        self.assertTrue(row["retryable"])
        self.assertEqual(row["next_action"], "reload_current_release")
        self.assertEqual(row["blocker"], "legacy_runtime_event_schema")

    def test_status_separates_runtime_and_business_truth(self):
        events = {"example": {"timestamp": "2026-08-28T00:00:00Z", "status": "blocked",
                  "effect_status": "unknown", "blocker": "provider_capacity",
                  "release_sha": "a" * 40, "provider": "openai", "profile_alias": "acct2"}}
        row = status_rows(REGISTRY,
            loaded={"ai.anicca.example": {"pid": "123", "last_exit": "0"}}, disabled={},
            events=events, installed_releases={"ai.anicca.example": "b" * 40})[0]
        self.assertEqual((row["launchd_state"], row["pid"], row["last_exit"]),
                         ("loaded-running", "123", "0"))
        self.assertEqual((row["last_terminal_result"], row["effect_status"], row["blocker"]),
                         ("blocked", "unknown", "provider_capacity"))
        self.assertNotEqual(row["installed_release_sha"], row["event_release_sha"])

    def test_status_marks_resolved_effect_unknown_event_as_stale(self):
        events = {"example": {
            "timestamp": "2026-08-28T00:00:00Z",
            "status": "pass",
            "effect_status": "unknown",
            "blocker": "host_admission_deferred:resource_effect_unknown",
            "release_sha": "a" * 40,
        }}
        row = status_rows(
            REGISTRY,
            loaded={},
            disabled={},
            events=events,
            installed_releases={},
            admission_effect_unknown=set(),
        )[0]
        self.assertIsNone(row["blocker"])
        self.assertFalse(row["admission_effect_unknown"])
        self.assertEqual(row["stale_event"], "resource_effect_unknown_resolved")

    def test_status_preserves_live_effect_unknown_fence(self):
        events = {"example": {
            "timestamp": "2026-08-28T00:00:00Z",
            "status": "blocked",
            "effect_status": "unknown",
            "blocker": "host_admission_deferred:resource_effect_unknown",
        }}
        row = status_rows(
            REGISTRY,
            loaded={},
            disabled={},
            events=events,
            installed_releases={},
            admission_effect_unknown={"example"},
        )[0]
        self.assertEqual(row["blocker"], "host_admission_deferred:resource_effect_unknown")
        self.assertTrue(row["admission_effect_unknown"])
        self.assertIsNone(row["stale_event"])

    def test_status_exposes_exact_live_admission_occurrences(self):
        row = status_rows(
            REGISTRY,
            loaded={},
            disabled={},
            events={},
            installed_releases={},
            admission_effect_unknown={"example"},
            admission_effect_unknown_occurrences={
                "example": ("example:current-fence",),
            },
        )[0]
        self.assertTrue(row["admission_effect_unknown"])
        self.assertEqual(
            row["admission_effect_unknown_occurrences"],
            ["example:current-fence"],
        )

    def test_doctor_lists_unmanaged_and_missing(self):
        report = doctor_report(REGISTRY,
            installed_labels={"ai.anicca.example", "ai.anicca.unmanaged"},
            loaded_labels={"ai.anicca.example", "ai.anicca.loaded-only"},
            existing_entrypoints=set())
        self.assertEqual(report["unmanaged_labels"],
                         ["ai.anicca.loaded-only", "ai.anicca.unmanaged"])
        self.assertEqual(report["missing_entrypoints"], ["example:bin/example.sh"])
        self.assertFalse(report["ok"])

    def test_doctor_does_not_call_explicit_external_label_unmanaged(self):
        registry = {**REGISTRY, "external_labels": ["ai.anicca.tsbridge"]}
        report = doctor_report(registry,
            installed_labels={"ai.anicca.example", "ai.anicca.tsbridge"},
            loaded_labels={"ai.anicca.example", "ai.anicca.tsbridge"},
            existing_entrypoints={"bin/example.sh"})
        self.assertEqual(report["unmanaged_labels"], [])
        self.assertTrue(report["ok"])

    def test_live_colors_hachioji_owner_is_classified_as_external(self):
        root = Path(__file__).resolve().parents[3]
        registry = json.loads((root / "config/loop-registry.json").read_text(encoding="utf-8"))
        label = "ai.anicca.provision-browser.colors-hachioji.owner-18211957"
        report = doctor_report(registry, installed_labels={label}, loaded_labels={label},
                              existing_entrypoints={entry["entrypoint"] for entry in registry["loops"].values()})
        self.assertEqual(report["unmanaged_labels"], [])
        self.assertTrue(report["ok"])

    def test_no_event_never_becomes_success_from_pid_or_exit(self):
        row = status_rows(REGISTRY, loaded={}, disabled={}, events={}, installed_releases={})[0]
        self.assertEqual(row["next_eligible_run"], "interval:60s")
        self.assertIsNone(row["last_terminal_result"])
        self.assertEqual(row["effect_status"], "unknown")

    def test_watch_snapshot_updates_from_event_envelopes(self):
        first = status_rows(REGISTRY, loaded={}, disabled={}, events={"example": {
            "status": "blocked", "effect_status": "unknown",
        }}, installed_releases={})
        second = status_rows(REGISTRY, loaded={}, disabled={}, events={"example": {
            "status": "pass", "effect_status": "verified",
        }}, installed_releases={})
        self.assertEqual(first[0]["last_terminal_result"], "blocked")
        self.assertEqual(second[0]["last_terminal_result"], "pass")
        self.assertEqual(second[0]["effect_status"], "verified")

    def test_wrapper_runs_outside_repository_working_directory(self):
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            [str(root / "bin/lm-loop"), "status", "fundraiser"],
            cwd="/tmp", capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["loop_id"], "fundraiser")

    def test_single_managed_status_collects_only_the_requested_loop(self):
        registry = {
            "schema_version": 2,
            "loops": {
                "example": REGISTRY["loops"]["example"],
                "second": {
                    **REGISTRY["loops"]["example"],
                    "label": "ai.anicca.second",
                    "state_root": "~/.local/state/life-manager/second",
                    "log_root": "~/.local/state/life-manager/second/logs",
                },
            },
        }
        captured = []

        def collect(value, **options):
            captured.append((value, options))
            return {}, {}, {}, {}, set()

        with patch("runtime.loop.lm_loop.collect_live", side_effect=collect):
            rows = snapshot(registry, "example")
        self.assertEqual([row["loop_id"] for row in rows], ["example"])
        self.assertEqual(list(captured[0][0]["loops"]), ["example"])
        self.assertEqual(captured[0][1], {"full_inventory": False})

    def test_invalid_event_cannot_spoof_pass_or_verified_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "events.jsonl").write_text('{"status":"pass","effect_status":"verified"}\n')
            self.assertIsNone(_last_event(str(root)))

    def test_last_event_filters_shared_state_by_loop_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [
                {"version":1,"event_id":"a"*24,"timestamp":"2026-08-28T00:00:00Z","loop_id":"a","domain":"system","run_id":"run-a","phase":"report","status":"pass","release_sha":"b"*40,"provider":"deterministic","profile_alias":None,"effect_class":"none","effect_status":"not_applicable","blocker":None,"evidence_refs":["lm-loop://a/run-a/summary.json"]},
                {"version":1,"event_id":"c"*24,"timestamp":"2026-08-28T00:01:00Z","loop_id":"b","domain":"system","run_id":"run-b","phase":"report","status":"fail","release_sha":"b"*40,"provider":"deterministic","profile_alias":None,"effect_class":"none","effect_status":"not_applicable","blocker":"entrypoint_exit_1","evidence_refs":["lm-loop://b/run-b/summary.json"]},
                {"version":1,"event_id":"d"*24,"timestamp":"2026-08-28T00:02:00Z","loop_id":"a","domain":"system","run_id":"install","phase":"plan","status":"pass","release_sha":"b"*40,"provider":"deterministic","profile_alias":None,"effect_class":"none","effect_status":"not_applicable","blocker":None,"evidence_refs":["lm-loop://a/install/summary.json"]},
            ]
            (root / "events.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
            event = _last_event(str(root), "a")
            self.assertEqual((event["status"], event["timestamp"]),
                             ("pass", "2026-08-28T00:00:00Z"))

    def test_last_event_stops_after_latest_requested_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            latest = {
                "version": 1, "event_id": "a" * 24,
                "timestamp": "2026-08-28T00:02:00Z", "loop_id": "a",
                "domain": "system", "run_id": "run-a", "phase": "report",
                "status": "pass", "release_sha": "b" * 40,
                "provider": "deterministic", "profile_alias": None,
                "effect_class": "none", "effect_status": "not_applicable",
                "blocker": None, "evidence_refs": ["lm-loop://a/run-a/summary.json"],
            }
            older = {
                **latest,
                "event_id": "b" * 24,
                "timestamp": "2026-08-28T00:01:00Z",
                "loop_id": "b",
                "run_id": "run-b",
                "evidence_refs": ["lm-loop://b/run-b/summary.json"],
            }
            (root / "events.jsonl").write_text(
                "\n".join(json.dumps(x) for x in (older, latest)) + "\n"
            )
            seen = []

            def record(value):
                seen.append(value["loop_id"])

            with patch("runtime.loop.lm_loop.validate_runtime_event", side_effect=record):
                event = _last_event(str(root), "a")

            self.assertEqual(event["loop_id"], "a")
            self.assertEqual(seen, ["a"])

    def test_last_event_targeted_cache_keeps_shared_loop_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for loop_id, timestamp in (("a", "2026-08-28T00:01:00Z"),
                                       ("b", "2026-08-28T00:02:00Z")):
                rows.append({
                    "version": 1, "event_id": loop_id * 24,
                    "timestamp": timestamp, "loop_id": loop_id,
                    "domain": "system", "run_id": f"run-{loop_id}",
                    "phase": "report", "status": "pass", "release_sha": "b" * 40,
                    "provider": "deterministic", "profile_alias": None,
                    "effect_class": "none", "effect_status": "not_applicable",
                    "blocker": None,
                    "evidence_refs": [f"lm-loop://{loop_id}/summary.json"],
                })
            (root / "events.jsonl").write_text(
                "\n".join(json.dumps(x) for x in rows) + "\n"
            )
            cache = {}
            self.assertEqual(_last_event(str(root), "b", cache)["loop_id"], "b")
            self.assertEqual(_last_event(str(root), "a", cache)["loop_id"], "a")

    def test_last_event_prefers_pid_bound_diagnostic_running_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = build_runtime_event(
                loop_id="browser", domain="growth", run_id="old-42",
                release_sha="a" * 40, provider="shared-agent-runner",
                profile_alias=None, effect_class="none", succeeded=False,
                blocker="entrypoint_exit_1", exit_code=1,
            )
            running = build_runtime_start_event(
                loop_id="browser", domain="growth", run_id="current-123",
                release_sha="b" * 40, provider="shared-agent-runner",
                profile_alias=None, effect_class="none", product_loop_id="affiliate",
                job_id="browser", owner_id="browser", wake_id="current-123",
                occurrence_id="browser:current-123", loaded_argv_sha256="c" * 64,
                loaded_env_sha256="d" * 64,
            )
            (root / "events.jsonl").write_text(
                "\n".join(json.dumps(row) for row in (report, running)) + "\n"
            )

            event = _last_event(str(root), "browser", running_pid="123")

            self.assertEqual(event, running)

    def test_status_projects_active_continuous_harness_failure(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            state = root / "instance" / "state"
            state.mkdir(parents=True, mode=0o700)
            running = build_runtime_start_event(
                loop_id="example", domain="earn", run_id="current-123",
                release_sha="b" * 40, provider="shared-agent-runner",
                profile_alias=None, effect_class="none", product_loop_id="connector",
                job_id="example", owner_id="example", wake_id="current-123",
                occurrence_id="example:current-123", loaded_argv_sha256="c" * 64,
                loaded_env_sha256="d" * 64,
            )
            harness = {
                "ts": int(time.time()), "wake_id": "wake-error", "kind": "skill_error",
                "layer": "tool_logic", "exit_code": 1,
                "detail": "spawn taskmarket ENOENT",
                "recovery_intent": {
                    "loop_id": "example", "run_id": "current-123",
                    "release_sha": "b" * 40, "retryable": True,
                    "action": "reconcile_owner",
                    "occurrence_id": "example:current-123",
                    "evidence_refs": ["lm-loop://example/current-123/failure"],
                },
            }
            path = state / "harness-failures.jsonl"
            path.write_text(json.dumps(harness) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
            registry = {"schema_version": 2, "loops": {"example": {
                **REGISTRY["loops"]["example"],
                "cadence": {"keep_alive": True},
                "state_root": f"~/{root.name}",
            }}}
            row = status_rows(
                registry, loaded={"ai.anicca.example": {"pid": "123", "last_exit": "0"}},
                disabled={}, events={"example": running},
                installed_releases={"ai.anicca.example": "b" * 40},
            )[0]
            self.assertEqual(row["last_terminal_result"], "fail")
            self.assertEqual(row["failure_layer"], "runtime")
            self.assertEqual(row["error_class"], "tool_missing")
            self.assertTrue(row["retryable"])
            self.assertEqual(row["next_action"], "reconcile_owner")
            self.assertEqual(row["blocker"], "harness_failure:tool_missing")
            self.assertTrue(row["latest_harness_failure"]["active"])

    def test_status_keeps_harness_failure_as_history_after_clean_wake(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as directory:
            root = Path(directory)
            state = root / "instance" / "state"
            state.mkdir(parents=True, mode=0o700)
            running = build_runtime_start_event(
                loop_id="example", domain="earn", run_id="current-123",
                release_sha="b" * 40, provider="shared-agent-runner",
                profile_alias=None, effect_class="none", product_loop_id="connector",
                job_id="example", owner_id="example", wake_id="current-123",
                occurrence_id="example:current-123", loaded_argv_sha256="c" * 64,
                loaded_env_sha256="d" * 64,
            )
            now = int(time.time())
            harness = {
                "ts": now - 2, "wake_id": "wake-error", "kind": "skill_error",
                "layer": "tool_logic", "exit_code": 1, "detail": "spawn taskmarket ENOENT",
                "recovery_intent": {
                    "loop_id": "example", "run_id": "current-123",
                    "release_sha": "b" * 40, "retryable": True,
                    "action": "reconcile_owner", "occurrence_id": "example:current-123",
                    "evidence_refs": ["lm-loop://example/current-123/failure"],
                },
            }
            ledger = {"ts": now, "wake_id": "wake-success", "kind": "wake"}
            path = state / "harness-failures.jsonl"
            path.write_text(json.dumps(harness) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
            ledger_path = state / "ledger.jsonl"
            ledger_path.write_text(json.dumps(ledger) + "\n", encoding="utf-8")
            os.chmod(ledger_path, 0o600)
            registry = {"schema_version": 2, "loops": {"example": {
                **REGISTRY["loops"]["example"],
                "cadence": {"keep_alive": True},
                "state_root": f"~/{root.name}",
            }}}
            row = status_rows(
                registry, loaded={"ai.anicca.example": {"pid": "123", "last_exit": "0"}},
                disabled={}, events={"example": running},
                installed_releases={"ai.anicca.example": "b" * 40},
            )[0]
            self.assertEqual(row["last_terminal_result"], "running")
            self.assertEqual(row["failure_layer"], "clean")
            self.assertFalse(row["latest_harness_failure"]["active"])

    def test_last_event_rejects_running_event_for_different_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = build_runtime_event(
                loop_id="browser", domain="growth", run_id="old-42",
                release_sha="a" * 40, provider="shared-agent-runner",
                profile_alias=None, effect_class="none", succeeded=False,
                blocker="entrypoint_exit_1", exit_code=1,
            )
            running = build_runtime_start_event(
                loop_id="browser", domain="growth", run_id="stale-999",
                release_sha="b" * 40, provider="shared-agent-runner",
                profile_alias=None, effect_class="none", product_loop_id="affiliate",
                job_id="browser", owner_id="browser", wake_id="stale-999",
                occurrence_id="browser:stale-999", loaded_argv_sha256="c" * 64,
                loaded_env_sha256="d" * 64,
            )
            (root / "events.jsonl").write_text(
                "\n".join(json.dumps(row) for row in (report, running)) + "\n"
            )

            event = _last_event(str(root), "browser", running_pid="123")

            self.assertEqual(event, report)

    def test_installed_release_uses_full_sha_from_generated_plist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.plist"
            path.write_bytes(plistlib.dumps({
                "ProgramArguments": ["/loops/releases/20260828T000000-12345678/bin/lm-loop-run"],
                "EnvironmentVariables": {"LIFE_MANAGER_RELEASE_SHA": "a" * 40},
            }))
            self.assertEqual(_release_from_plist(path), "a" * 40)

    def test_status_uses_installed_custom_state_root(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.plist"
            custom = str(Path(directory) / "custom-state")
            path.write_bytes(plistlib.dumps({
                "EnvironmentVariables": {"LIFE_MANAGER_STATE_ROOT": custom},
            }))
            self.assertEqual(_state_root_from_plist(path, "/default-state"), custom)


if __name__ == "__main__":
    unittest.main()
