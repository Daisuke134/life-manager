import gzip
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from runtime.loop import runtime_event

from runtime.loop.runtime_event import (
    append_runtime_event,
    build_install_event,
    build_runtime_event,
    rotate_jsonl_locked,
    validate_runtime_event,
)


BASE = {
    "version": 1, "event_id": "a" * 24, "timestamp": "2026-08-28T00:00:00+00:00",
    "loop_id": "example", "domain": "earn", "run_id": "run-1", "phase": "report",
    "status": "pass", "release_sha": "b" * 40, "provider": "openai",
    "profile_alias": "acct2", "effect_class": "application",
    "effect_status": "unknown", "blocker": None,
    "evidence_refs": ["agent-runner://example/run-1/summary.json"],
}


class RuntimeEventTest(unittest.TestCase):
    def test_exact_outer_terminal_ignores_inner_report_until_host_child_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            inner = {**BASE, "loop_id": "life-manager-connector-native",
                     "run_id": "outer-123", "provider": "codex", "event_id": "c" * 24,
                     "evidence_refs": ["agent-runner://life-manager-connector-native/outer-123/summary.json"]}
            outer = {**inner, "provider": "deterministic", "event_id": "d" * 24,
                     "profile_alias": None,
                     "evidence_refs": ["lm-loop://life-manager-connector-native/outer-123/summary.json"]}
            path.write_text(json.dumps(inner) + "\n", encoding="utf-8")
            find = getattr(runtime_event, "find_exact_outer_terminal", lambda *_: None)
            self.assertIsNone(find(path, "life-manager-connector-native", "outer-123", "b" * 40))
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(outer) + "\n")
            self.assertEqual(find(path, "life-manager-connector-native", "outer-123", "b" * 40), outer)

    def test_exact_outer_terminal_reads_rotated_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            outer = {**BASE, "loop_id": "life-manager-connector-native",
                     "run_id": "archived-123", "provider": "deterministic", "event_id": "e" * 24,
                     "profile_alias": None,
                     "evidence_refs": ["lm-loop://life-manager-connector-native/archived-123/summary.json"]}
            archive = path.with_name("events-20260916T010000Z.jsonl.gz")
            with gzip.open(archive, "wt", encoding="utf-8") as handle:
                handle.write(json.dumps(outer) + "\n")
            find = getattr(runtime_event, "find_exact_outer_terminal", lambda *_: None)
            self.assertEqual(find(path, "life-manager-connector-native", "archived-123", "b" * 40), outer)

    def test_exact_outer_terminal_rejects_wrong_sha_and_conflicting_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            outer = {**BASE, "loop_id": "life-manager-connector-native",
                     "run_id": "outer-456", "provider": "deterministic", "event_id": "f" * 24,
                     "profile_alias": None,
                     "evidence_refs": ["lm-loop://life-manager-connector-native/outer-456/summary.json"]}
            path.write_text(json.dumps(outer) + "\n", encoding="utf-8")
            find = getattr(runtime_event, "find_exact_outer_terminal", lambda *_: None)
            with self.assertRaises(ValueError):
                find(path, "life-manager-connector-native", "outer-456", "a" * 40)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({**outer, "event_id": "1" * 24, "status": "fail"}) + "\n")
            with self.assertRaises(ValueError):
                find(path, "life-manager-connector-native", "outer-456", "b" * 40)

    def test_exact_outer_terminal_rejects_report_still_marked_running(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            row = {**BASE, "loop_id": "life-manager-connector-native",
                   "run_id": "outer-running", "provider": "deterministic",
                   "profile_alias": None, "status": "running",
                   "evidence_refs": ["lm-loop://life-manager-connector-native/outer-running/summary.json"]}
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                runtime_event.find_exact_outer_terminal(
                    path, "life-manager-connector-native", "outer-running", "b" * 40)

    def test_valid_event_appends_one_private_jsonl_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            append_runtime_event(path, BASE)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_same_event_id_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            append_runtime_event(path, BASE)
            append_runtime_event(path, BASE)
            self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_duplicate_scan_parses_only_matching_candidate_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            for index in range(1000):
                append_runtime_event(path, {**BASE, "event_id": f"{index:024x}"})
            append_runtime_event(path, BASE)
            with mock.patch.object(
                runtime_event.json, "loads", wraps=runtime_event.json.loads
            ) as loads:
                append_runtime_event(path, BASE)
            self.assertEqual(loads.call_count, 1)
            self.assertEqual(len(path.read_text().splitlines()), 1001)

    def test_corrupt_partial_row_does_not_suppress_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_bytes(f'{{"event_id":"{BASE["event_id"]}"'.encode())
            append_runtime_event(path, BASE)
            lines = path.read_text().splitlines()
            self.assertEqual(json.loads(lines[-1]), BASE)

    def test_unicode_escaped_event_id_is_still_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            encoded = json.dumps(BASE).replace(BASE["event_id"], "\\u0061" * 24)
            path.write_text(encoded + "\n", encoding="utf-8")
            append_runtime_event(path, BASE)
            self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_spaced_valid_json_row_is_still_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(json.dumps(BASE) + "\n", encoding="utf-8")
            append_runtime_event(path, BASE)
            self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_rotation_preserves_all_rows_in_private_gzip_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            with mock.patch.dict(os.environ, {"LM_RUNTIME_EVENTS_MAX_BYTES": "1"}):
                append_runtime_event(path, BASE)
                append_runtime_event(path, {**BASE, "event_id": "b" * 24})
            archives = list(path.parent.glob("events-*.jsonl.gz"))
            self.assertEqual(len(archives), 1)
            with gzip.open(archives[0], "rt", encoding="utf-8") as handle:
                self.assertEqual(len(handle.readlines()) + len(path.read_text().splitlines()), 2)
            self.assertEqual(archives[0].stat().st_mode & 0o777, 0o600)

    def test_rotation_prunes_only_old_archives_when_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.jsonl"
            for index in range(4):
                path.write_text(f'{{"index":{index}}}\n', encoding="utf-8")
                with path.open("r+") as handle:
                    rotate_jsonl_locked(handle.fileno(), path, 1, keep_archives=3)
            archives = sorted(path.parent.glob("usage-*.jsonl.gz"))
            self.assertEqual(len(archives), 3)
            with gzip.open(archives[0], "rt", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), '{"index":1}\n')

    def test_unknown_and_secret_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            validate_runtime_event({**BASE, "model": "gpt"})
        with self.assertRaisesRegex(ValueError, "secret-like"):
            validate_runtime_event({**BASE, "blocker": "TOKEN=do-not-store"})
        with self.assertRaisesRegex(ValueError, "secret-like"):
            validate_runtime_event({**BASE, "evidence_refs": ["/" + "Users/operator/private.json"]})
        with self.assertRaisesRegex(ValueError, "secret-like"):
            validate_runtime_event({**BASE, "blocker": "sk-abcdefghijklmnopqrstuvwxyz012345"})

    def test_disk_cleanup_loop_id_is_not_mistaken_for_api_key(self):
        event = {
            **BASE,
            "loop_id": "life-manager-disk-cleanup",
            "evidence_refs": ["lm-loop://life-manager-disk-cleanup/install/summary.json"],
        }
        self.assertEqual(validate_runtime_event(event), event)

    def test_runner_success_does_not_claim_external_effect(self):
        event = build_runtime_event(
            loop_id="example", domain="earn", run_id="run-1", release_sha="b" * 40,
            provider="openai", profile_alias="acct2", effect_class="application",
            succeeded=True, blocker=None,
        )
        self.assertEqual(event["status"], "pass")
        self.assertEqual(event["effect_status"], "unknown")
        self.assertEqual(event["evidence_refs"], ["agent-runner://example/run-1/summary.json"])

    def test_no_effect_uses_not_applicable(self):
        event = build_runtime_event(
            loop_id="example", domain="system", run_id="run-1", release_sha="b" * 40,
            provider="deterministic", profile_alias=None, effect_class="none",
            succeeded=False, blocker="runner_failed",
        )
        self.assertEqual(event["effect_status"], "not_applicable")
        self.assertEqual(event["status"], "fail")

    def test_deferred_work_is_blocked_not_failed(self):
        event = build_runtime_event(
            loop_id="example", domain="earn", run_id="run-1", release_sha="b" * 40,
            provider="deterministic", profile_alias=None, effect_class="message",
            succeeded=False, deferred=True, blocker="memory_admission_deferred",
        )
        self.assertEqual(event["status"], "blocked")

    def test_install_event_is_plan_truth_not_external_effect_truth(self):
        event = build_install_event(
            loop_id="example", domain="earn", release_sha="b" * 40,
            provider="shared-agent-runner", effect_class="application")
        self.assertEqual((event["phase"], event["status"], event["effect_status"]),
                         ("plan", "pass", "unknown"))
        self.assertEqual(event["evidence_refs"], ["lm-loop://example/install/summary.json"])


if __name__ == "__main__":
    unittest.main()
