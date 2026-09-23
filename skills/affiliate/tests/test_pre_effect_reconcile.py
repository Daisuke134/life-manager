from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "pre_effect_reconcile.py"
SPEC = importlib.util.spec_from_file_location("affiliate_pre_effect_reconcile", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)


def write_private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    path.chmod(0o600)


class AffiliatePreEffectReconcileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SPEC.loader.exec_module(MODULE)

    def unknown(self, occurrence: str) -> list[dict]:
        return [{
            "occurrence_id": occurrence,
            "owner_id": "affiliate-loop",
            "queued_at": 100.0,
            "sequence": 7,
            "state": "claimed",
            "effect_unknown": 1,
            "older_open_count": 0,
        }]

    def scratch(self, loop_state: Path, run_id: str, marker: dict) -> Path:
        scratch = loop_state / "loop-tmp" / "affiliate-loop" / run_id
        scratch.mkdir(parents=True)
        write_private(scratch / "host-admission.json", {
            "effect": 0,
            "reason": "resource_slot_acquired",
            "resource_class": "deterministic",
            "status": "pass",
        })
        write_private(scratch / "entrypoint-result.json", marker)
        write_private(scratch / ".owner.json", {
            "effect_class": "publish", "pid": 999999,
            "process_start": "not-running",
        })
        write_private(scratch / ".terminal-unrecorded", {"protected": True})
        return scratch

    def runtime_events(self, loop_state: Path, run_id: str, *, blocked: bool = True) -> None:
        rows = [{
            "version": 1, "event_id": "1" * 24, "loop_id": "affiliate-loop",
            "domain": "growth", "provider": "deterministic", "profile_alias": None,
            "phase": "execute", "status": "running", "effect_status": "started",
            "effect_class": "publish", "blocker": None,
            "evidence_refs": [f"lm-loop://affiliate-loop/{run_id}/summary.json"],
            "run_id": run_id, "release_sha": "a" * 40,
            "timestamp": "2026-09-23T11:20:20+00:00",
        }]
        if blocked:
            rows.extend((
                {
                    "version": 1, "event_id": "2" * 24, "loop_id": "affiliate-loop",
                    "domain": "growth", "provider": "deterministic", "profile_alias": None,
                    "phase": "execute", "status": "running", "effect_status": "started",
                    "effect_class": "publish", "blocker": None,
                    "evidence_refs": ["lm-loop://affiliate-loop/next-run/summary.json"],
                    "run_id": "next-run", "release_sha": "a" * 40,
                    "timestamp": "2026-09-23T11:30:53+00:00",
                },
                {
                    "version": 1, "event_id": "3" * 24, "loop_id": "affiliate-loop",
                    "domain": "growth", "provider": "deterministic", "profile_alias": None,
                    "phase": "report", "status": "blocked", "effect_status": "unknown",
                    "effect_class": "publish",
                    "blocker": "host_admission_deferred:resource_effect_unknown",
                    "evidence_refs": ["agent-runner://affiliate-loop/next-run/summary.json"],
                    "run_id": "next-run", "release_sha": "a" * 40,
                    "timestamp": "2026-09-23T11:30:54+00:00",
                },
            ))
        path = loop_state / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        path.chmod(0o600)

    def empty_job_journal(self, affiliate_state: Path) -> None:
        path = affiliate_state / "job-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        path.chmod(0o600)

    def test_exact_marker_reconciles_only_matching_occurrence(self):
        occurrence = "affiliate-loop:old"
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = "unrecorded-run"
            self.scratch(loop_state, run_id, {
                "schema_version": 1,
                "kind": "life_manager_pre_effect_result",
                "status": "pre_effect_failure",
                "effect": 0,
                "owner_id": "affiliate-loop",
                "occurrence_id": occurrence,
                "runtime_run_id": run_id,
            })
            self.runtime_events(loop_state, run_id, blocked=False)
            resolver = Mock(return_value=True)
            coalescer = Mock(return_value=3)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
                coalescer=coalescer,
                current_occurrence_id="affiliate-loop:current",
            )

            self.assertEqual(result["state"], "RECONCILED")
            self.assertEqual(result["occurrence_id"], occurrence)
            self.assertEqual(result["cancelled_occurrences"], 3)
            coalescer.assert_called_once_with("affiliate-loop", "affiliate-loop:current")
            proof = resolver.call_args.kwargs["pre_effect_readback"]()
            self.assertEqual(proof["proof_type"], "pre_effect")
            self.assertEqual(proof["occurrence_id"], occurrence)
            receipt = Path(result["receipt_path"])
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(str(Path.home()), receipt.read_text(encoding="utf-8"))

    def test_unique_legacy_marker_requires_adjacent_fence_and_zero_job_events(self):
        occurrence = MODULE.LEGACY_MIGRATION_OCCURRENCE_ID
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = MODULE.LEGACY_MIGRATION_RUN_ID
            scratch = self.scratch(loop_state, run_id, {
                "status": "pre_effect_failure", "effect": 0,
            })
            self.runtime_events(loop_state, run_id)
            self.empty_job_journal(affiliate_state)
            # Put the marker between the execute and blocked timestamps.
            os.utime(scratch / "entrypoint-result.json", (1790162421, 1790162421))
            resolver = Mock(return_value=True)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
            )

            self.assertEqual(result["state"], "RECONCILED")
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            self.assertEqual(receipt["evidence"]["marker_contract"], "legacy_unique")
            self.assertEqual(receipt["evidence"]["new_job_events"], 0)

    def test_legacy_marker_holds_when_a_job_event_exists_in_window(self):
        occurrence = MODULE.LEGACY_MIGRATION_OCCURRENCE_ID
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = MODULE.LEGACY_MIGRATION_RUN_ID
            scratch = self.scratch(loop_state, run_id, {
                "status": "pre_effect_failure", "effect": 0,
            })
            self.runtime_events(loop_state, run_id)
            os.utime(scratch / "entrypoint-result.json", (1790162421, 1790162421))
            write_private(affiliate_state / "job-events.jsonl", {
                "job_id": "effect-1", "kind": "X_POST_PUBLISH",
                "state": "EFFECT_STARTED", "updated_at": 1790162500,
            })
            resolver = Mock(return_value=True)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
            )

            self.assertEqual(result["state"], "HELD")
            self.assertEqual(result["reason"], "legacy_effect_window_nonempty")
            resolver.assert_not_called()

    def test_legacy_marker_cannot_reconcile_a_different_occurrence(self):
        occurrence = "affiliate-loop:not-the-historical-target"
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = MODULE.LEGACY_MIGRATION_RUN_ID
            scratch = self.scratch(loop_state, run_id, {
                "status": "pre_effect_failure", "effect": 0,
            })
            self.runtime_events(loop_state, run_id)
            os.utime(scratch / "entrypoint-result.json", (1790162421, 1790162421))
            resolver = Mock(return_value=True)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
            )

            self.assertEqual(result["state"], "HELD")
            resolver.assert_not_called()

    def test_legacy_marker_requires_the_immediate_next_execute_report_pair(self):
        occurrence = MODULE.LEGACY_MIGRATION_OCCURRENCE_ID
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = MODULE.LEGACY_MIGRATION_RUN_ID
            scratch = self.scratch(loop_state, run_id, {
                "status": "pre_effect_failure", "effect": 0,
            })
            self.runtime_events(loop_state, run_id)
            event_path = loop_state / "events.jsonl"
            rows = [json.loads(line) for line in event_path.read_text().splitlines()]
            rows.insert(2, {
                "version": 1, "event_id": "4" * 24, "loop_id": "affiliate-loop",
                "domain": "growth", "provider": "deterministic", "profile_alias": None,
                "phase": "execute", "status": "running", "effect_status": "started",
                "effect_class": "publish", "blocker": None,
                "evidence_refs": ["lm-loop://affiliate-loop/intervening-run/summary.json"],
                "run_id": "intervening-run", "release_sha": "a" * 40,
                "timestamp": "2026-09-23T11:30:53.500000+00:00",
            })
            event_path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8",
            )
            os.utime(scratch / "entrypoint-result.json", (1790162421, 1790162421))
            resolver = Mock(return_value=True)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
            )

            self.assertEqual(result["state"], "HELD")
            resolver.assert_not_called()

    def test_legacy_marker_holds_when_job_journal_is_malformed(self):
        occurrence = MODULE.LEGACY_MIGRATION_OCCURRENCE_ID
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = MODULE.LEGACY_MIGRATION_RUN_ID
            scratch = self.scratch(loop_state, run_id, {
                "status": "pre_effect_failure", "effect": 0,
            })
            self.runtime_events(loop_state, run_id)
            os.utime(scratch / "entrypoint-result.json", (1790162421, 1790162421))
            journal = affiliate_state / "job-events.jsonl"
            journal.parent.mkdir(parents=True)
            journal.write_text("{broken\n", encoding="utf-8")
            journal.chmod(0o600)
            resolver = Mock(return_value=True)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
            )

            self.assertEqual(result["state"], "HELD")
            resolver.assert_not_called()

    def test_legacy_marker_holds_when_runtime_event_journal_is_malformed(self):
        occurrence = MODULE.LEGACY_MIGRATION_OCCURRENCE_ID
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = MODULE.LEGACY_MIGRATION_RUN_ID
            scratch = self.scratch(loop_state, run_id, {
                "status": "pre_effect_failure", "effect": 0,
            })
            self.runtime_events(loop_state, run_id)
            event_path = loop_state / "events.jsonl"
            rows = event_path.read_text(encoding="utf-8").splitlines(keepends=True)
            event_path.write_text(rows[0] + "{broken\n" + "".join(rows[1:]), encoding="utf-8")
            self.empty_job_journal(affiliate_state)
            os.utime(scratch / "entrypoint-result.json", (1790162421, 1790162421))
            resolver = Mock(return_value=True)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
            )

            self.assertEqual(result["state"], "HELD")
            resolver.assert_not_called()

    def test_legacy_marker_holds_when_runtime_event_schema_is_invalid(self):
        occurrence = MODULE.LEGACY_MIGRATION_OCCURRENCE_ID
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = MODULE.LEGACY_MIGRATION_RUN_ID
            scratch = self.scratch(loop_state, run_id, {
                "status": "pre_effect_failure", "effect": 0,
            })
            self.runtime_events(loop_state, run_id)
            event_path = loop_state / "events.jsonl"
            rows = event_path.read_text(encoding="utf-8").splitlines(keepends=True)
            event_path.write_text(rows[0] + "{}\n" + "".join(rows[1:]), encoding="utf-8")
            self.empty_job_journal(affiliate_state)
            os.utime(scratch / "entrypoint-result.json", (1790162421, 1790162421))
            resolver = Mock(return_value=True)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
            )

            self.assertEqual(result["state"], "HELD")
            resolver.assert_not_called()

    def test_legacy_marker_holds_when_runtime_event_journal_is_not_private(self):
        occurrence = MODULE.LEGACY_MIGRATION_OCCURRENCE_ID
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = MODULE.LEGACY_MIGRATION_RUN_ID
            scratch = self.scratch(loop_state, run_id, {
                "status": "pre_effect_failure", "effect": 0,
            })
            self.runtime_events(loop_state, run_id)
            (loop_state / "events.jsonl").chmod(0o644)
            self.empty_job_journal(affiliate_state)
            os.utime(scratch / "entrypoint-result.json", (1790162421, 1790162421))
            resolver = Mock(return_value=True)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
            )

            self.assertEqual(result["state"], "HELD")
            resolver.assert_not_called()

    def test_legacy_marker_holds_when_runtime_event_journal_is_a_symlink(self):
        occurrence = MODULE.LEGACY_MIGRATION_OCCURRENCE_ID
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = MODULE.LEGACY_MIGRATION_RUN_ID
            scratch = self.scratch(loop_state, run_id, {
                "status": "pre_effect_failure", "effect": 0,
            })
            self.runtime_events(loop_state, run_id)
            event_path = loop_state / "events.jsonl"
            target = root / "events-target.jsonl"
            event_path.replace(target)
            event_path.symlink_to(target)
            self.empty_job_journal(affiliate_state)
            os.utime(scratch / "entrypoint-result.json", (1790162421, 1790162421))
            resolver = Mock(return_value=True)

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver,
            )

            self.assertEqual(result["state"], "HELD")
            resolver.assert_not_called()

    def test_multiple_unknown_occurrences_hold_without_guessing(self):
        with tempfile.TemporaryDirectory() as root:
            result = MODULE.reconcile_before_effect(
                Path(root) / "affiliate", Path(root) / "loop",
                unknown_reader=lambda _owner: [
                    *self.unknown("affiliate-loop:one"),
                    *self.unknown("affiliate-loop:two"),
                ],
                resolver=Mock(side_effect=AssertionError("must not resolve")),
            )
        self.assertEqual(result, {
            "state": "HELD", "reason": "unknown_occurrence_count", "count": 2,
        })

    def test_dry_run_returns_proof_without_receipt_or_resolution(self):
        occurrence = "affiliate-loop:old"
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            loop_state, affiliate_state = root / "loop", root / "affiliate"
            run_id = "unrecorded-run"
            self.scratch(loop_state, run_id, {
                "schema_version": 1,
                "kind": "life_manager_pre_effect_result",
                "status": "pre_effect_failure",
                "effect": 0,
                "owner_id": "affiliate-loop",
                "occurrence_id": occurrence,
                "runtime_run_id": run_id,
            })
            self.runtime_events(loop_state, run_id, blocked=False)
            resolver = Mock(side_effect=AssertionError("dry run must not resolve"))

            result = MODULE.reconcile_before_effect(
                affiliate_state, loop_state,
                unknown_reader=lambda _owner: self.unknown(occurrence),
                resolver=resolver, dry_run=True,
            )

            self.assertEqual(result["state"], "PROOF_READY")
            resolver.assert_not_called()
            self.assertFalse((affiliate_state / "reconciliation").exists())


if __name__ == "__main__":
    unittest.main()
