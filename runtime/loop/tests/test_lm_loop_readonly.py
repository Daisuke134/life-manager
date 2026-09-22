import unittest
import json
import subprocess
import tempfile
import plistlib
from pathlib import Path
from unittest.mock import patch

from runtime.loop.lm_loop import (
    _last_event, _release_from_plist, _state_root_from_plist,
    doctor_report, snapshot, status_rows,
)


REGISTRY = {"schema_version": 2, "loops": {"example": {
    "label": "ai.anicca.example", "domain": "earn", "entrypoint": "bin/example.sh",
    "cadence": {"start_interval_seconds": 60}, "effect_class": "application",
    "state_root": "~/.local/state/life-manager/example",
    "log_root": "~/.local/state/life-manager/example/logs",
    "cleanup": {"max_runs": 10, "max_age_days": 7},
    "provider_route": "shared-agent-runner",
}}}


def runtime_event(**overrides):
    value = {
        "version": 1,
        "event_id": "a" * 24,
        "timestamp": "2026-08-28T00:00:00Z",
        "loop_id": "example",
        "domain": "earn",
        "run_id": "run-example",
        "phase": "report",
        "status": "pass",
        "release_sha": "b" * 40,
        "provider": "deterministic",
        "profile_alias": None,
        "effect_class": "application",
        "effect_status": "verified",
        "blocker": None,
        "evidence_refs": ["lm-loop://example/run-example/summary.json"],
    }
    value.update(overrides)
    return value


class LmLoopReadonlyTest(unittest.TestCase):
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

    def test_status_explain_is_opt_in_and_uses_only_validated_event_evidence(self):
        default = status_rows(
            REGISTRY,
            loaded={"ai.anicca.example": {"last_exit": "0"}},
            disabled={}, events={"example": runtime_event()},
            installed_releases={"ai.anicca.example": "b" * 40},
        )[0]
        self.assertNotIn("explain", default)

        explained = status_rows(
            REGISTRY,
            loaded={"ai.anicca.example": {"last_exit": "0"}},
            disabled={}, events={"example": runtime_event()},
            installed_releases={"ai.anicca.example": "b" * 40},
            admission_effect_unknown=set(), explain=True,
        )[0]["explain"]
        self.assertEqual(explained, {
            "reason_code": "healthy",
            "next_action": "none",
            "event_id": "a" * 24,
            "run_id": "run-example",
            "phase": "report",
            "evidence_refs": ["lm-loop://example/run-example/summary.json"],
        })

    def test_status_explain_covers_operational_and_business_failure_boundaries(self):
        loaded = {"ai.anicca.example": {"last_exit": "0"}}
        installed = {"ai.anicca.example": "b" * 40}

        def reason(*, event=None, runtime=loaded, disabled=None, release=installed,
                   fenced=None):
            return status_rows(
                REGISTRY,
                loaded=runtime,
                disabled=disabled or {},
                events={} if event is None else {"example": event},
                installed_releases=release,
                admission_effect_unknown=fenced,
                explain=True,
            )[0]["explain"]

        cases = [
            (reason(event=runtime_event(), disabled={"ai.anicca.example": True}),
             "disabled", "inspect_disabled_state"),
            (reason(event=runtime_event(), runtime={}),
             "unloaded", "apply_immutable_release"),
            (reason(event=runtime_event(release_sha="c" * 40)),
             "stale_release_event", "reconcile_loaded_release"),
            (reason(event=runtime_event(
                status="blocked", effect_status="unknown",
                blocker="host_admission_deferred:resource_effect_unknown"),
                fenced={"example"}),
             "effect_unknown_fence", "obtain_official_readback"),
            (reason(event=runtime_event(status="fail", effect_status="failed",
                                        blocker="entrypoint_exit_1")),
             "runtime_blocker", "inspect_evidence"),
            (reason(event=runtime_event(effect_status="unknown"), fenced=set()),
             "effect_unverified", "obtain_official_readback"),
        ]
        for explanation, code, action in cases:
            self.assertEqual((explanation["reason_code"], explanation["next_action"]),
                             (code, action))
            self.assertEqual(explanation["event_id"], "a" * 24)
            self.assertEqual(explanation["phase"], "report")
            self.assertEqual(explanation["evidence_refs"],
                             ["lm-loop://example/run-example/summary.json"])

        no_event = reason()
        self.assertEqual((no_event["reason_code"], no_event["next_action"]),
                         ("insufficient_evidence", "await_next_scheduled_wake"))
        self.assertEqual(no_event["evidence_refs"], [])
        self.assertIsNone(no_event["event_id"])
        invalid = reason(event={"status": "pass", "evidence_refs": ["forged"]})
        self.assertEqual(invalid["reason_code"], "insufficient_evidence")
        self.assertEqual(invalid["evidence_refs"], [])

    def test_status_explain_cli_accepts_one_target_and_rejects_unknown_flags(self):
        root = Path(__file__).resolve().parents[3]
        explained = subprocess.run(
            [str(root / "bin/lm-loop"), "status", "fundraiser", "--explain"],
            cwd="/tmp", capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(explained.returncode, 0, explained.stderr)
        row = json.loads(explained.stdout)[0]
        self.assertEqual(row["loop_id"], "fundraiser")
        self.assertEqual(set(row["explain"]), {
            "reason_code", "next_action", "event_id", "run_id", "phase", "evidence_refs",
        })
        rejected = subprocess.run(
            [str(root / "bin/lm-loop"), "status", "fundraiser", "--guess"],
            cwd="/tmp", capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(rejected.returncode, 2)


if __name__ == "__main__":
    unittest.main()
