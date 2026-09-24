import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from job_search_loop.evidence_retention import classify_run, reclaim_evidence


class EvidenceRetentionTests(unittest.TestCase):
    def _write_json(self, path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def _old(self, path: Path) -> None:
        old = time.time() - (8 * 24 * 60 * 60)
        for item in [path, *path.rglob("*")]:
            os.utime(item, (old, old), follow_symlinks=False)

    def test_reclaims_only_explicit_no_work_and_keeps_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "job-search" / "evidence"
            no_work = root / "inbox-20260901-000000-1"
            self._write_json(
                no_work / "inbox-terminal.json",
                {
                    "outcome": "no_work",
                    "reason": "no_new_messages_or_preparation",
                },
            )
            self._write_json(no_work / "summary.json", {"status": "no_new_recruiting_email"})
            self._old(no_work)

            current = root / "inbox-20260925-000000-2"
            self._write_json(
                current / "inbox-terminal.json",
                {"outcome": "no_work", "reason": "no_new_messages_or_preparation"},
            )

            result = reclaim_evidence(
                root,
                current_run=current,
                min_age_seconds=7 * 24 * 60 * 60,
                min_free_bytes=0,
                max_evidence_bytes=0,
                force=True,
            )

            self.assertEqual(result["reclaimed_runs"], 1)
            self.assertFalse(no_work.exists())
            self.assertTrue(current.exists())

    def test_effect_unknown_submitted_and_unmarked_runs_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "job-search" / "evidence"
            submitted = root / "mercor-20260901-000000-1"
            self._write_json(
                submitted / "mercor-pass-terminal.json",
                {"status": "submitted", "submitted": [{"listing_id": "job-1"}]},
            )
            unknown = root / "daily-20260901-000000"
            self._write_json(
                unknown / "wake-report.json",
                {"outcome": "failed", "reason": "delivery_unknown"},
            )
            unmarked = root / "daily-20260901-000001"
            self._write_json(unmarked / "summary.json", {"status": "success"})
            for run in (submitted, unknown, unmarked):
                self._old(run)

            result = reclaim_evidence(
                root,
                min_age_seconds=0,
                min_free_bytes=0,
                max_evidence_bytes=0,
                force=True,
            )

            self.assertEqual(result["reclaimed_runs"], 0)
            self.assertTrue(submitted.exists())
            self.assertTrue(unknown.exists())
            self.assertTrue(unmarked.exists())
            self.assertEqual(classify_run(submitted)["eligible"], False)
            self.assertEqual(classify_run(unmarked)["reason"], "no_explicit_no_effect")

    def test_active_marker_and_symlink_are_never_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "job-search" / "evidence"
            active = root / "inbox-20260901-000000-1"
            self._write_json(
                active / "inbox-terminal.json",
                {"outcome": "no_work", "reason": "no_new_messages_or_preparation"},
            )
            (active / "scratch").mkdir()
            (active / "scratch" / "command.lock").write_text("live", encoding="utf-8")
            self._old(active)

            outside = Path(directory) / "outside"
            outside.mkdir()
            link = root / "inbox-20260901-000001-1"
            root.mkdir(parents=True, exist_ok=True)
            link.symlink_to(outside, target_is_directory=True)

            result = reclaim_evidence(
                root,
                min_age_seconds=0,
                min_free_bytes=0,
                max_evidence_bytes=0,
                force=True,
            )

            self.assertEqual(result["reclaimed_runs"], 0)
            self.assertTrue(active.exists())
            self.assertTrue(link.is_symlink())


if __name__ == "__main__":
    unittest.main()
