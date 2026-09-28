#!/usr/bin/env python3
"""Tests for the JSONL ledger -- the idempotency guard the publisher relies on."""
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import ledger  # noqa: E402


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "promptbase-listings.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def _row(self, slug="reels-hook-lab", status="submitted_pending_review"):
        return {
            "slug": slug,
            "promptbase_id": "abc123",
            "url": "https://promptbase.com/prompt-edit/abc123",
            "status": status,
            "submitted_at": "2026-09-28T00:00:00Z",
        }

    def test_append_then_already_listed(self):
        self.assertIsNone(ledger.already_listed("reels-hook-lab", self.path))
        ledger.append(self._row(), self.path)
        found = ledger.already_listed("reels-hook-lab", self.path)
        self.assertIsNotNone(found)
        self.assertEqual(found["promptbase_id"], "abc123")

    def test_second_publish_attempt_is_blocked(self):
        ledger.append(self._row(), self.path)
        # A publisher must refuse to create a second listing for a slug that
        # already has a non-terminal row -- this is the exact check publish.py
        # runs before ever opening the /sell wizard.
        self.assertIsNotNone(ledger.already_listed("reels-hook-lab", self.path))

    def test_rejected_status_allows_retry(self):
        ledger.append(self._row(status="rejected"), self.path)
        self.assertIsNone(ledger.already_listed("reels-hook-lab", self.path))

    def test_append_requires_all_fields(self):
        with self.assertRaises(ValueError):
            ledger.append({"slug": "x"}, self.path)

    def test_update_status_appends_new_row_preserving_history(self):
        ledger.append(self._row(), self.path)
        ledger.update_status(
            "reels-hook-lab", status="live", sales=0.0, checked_at="2026-09-29T00:00:00Z",
            ledger_path=self.path,
        )
        rows = ledger.read_all(self.path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "submitted_pending_review")
        self.assertEqual(rows[1]["status"], "live")
        latest = ledger.latest_by_slug(self.path)
        self.assertEqual(latest["reels-hook-lab"]["status"], "live")

    def test_update_status_unknown_slug_raises(self):
        with self.assertRaises(ValueError):
            ledger.update_status("nope", status="live", ledger_path=self.path)

    def test_ledger_file_is_owner_only(self):
        ledger.append(self._row(), self.path)
        mode = self.path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
