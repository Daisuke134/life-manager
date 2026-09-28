#!/usr/bin/env python3
"""Tests for select_next.py's pure selection logic -- no network/browser."""
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import ledger  # noqa: E402
import select_next  # noqa: E402


def _agent(name, status="online"):
    return {"agent_id": "1", "name": name, "agent_status": status}


class SelectNextTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.catalog_dir = Path(self._tmp.name) / "catalog"
        self.ledger_path = Path(self._tmp.name) / "ledger.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def _make_skill(self, slug, title, demand_rank=None):
        d = self.catalog_dir / slug
        d.mkdir(parents=True)
        rank_line = f"\nDemand rank: {demand_rank}\n" if demand_rank is not None else ""
        (d / "LISTING.md").write_text(
            f"## Title\n{title}\n{rank_line}\n## shortDescription\nx\n", encoding="utf-8"
        )

    def test_picks_online_unshipped_slug(self):
        self._make_skill("hook-lab", "Hook Lab")
        result = select_next.select_next(
            self.catalog_dir, [_agent("Hook Lab")], self.ledger_path
        )
        self.assertEqual(result["slug"], "hook-lab")

    def test_skips_slug_not_online_on_capafy(self):
        self._make_skill("hook-lab", "Hook Lab")
        result = select_next.select_next(
            self.catalog_dir, [_agent("Hook Lab", status="under_review")], self.ledger_path
        )
        self.assertIsNone(result["slug"])
        self.assertEqual(result["reason"], "no_online_unshipped_catalog_item")

    def test_skips_slug_already_in_ledger(self):
        self._make_skill("hook-lab", "Hook Lab")
        ledger.append(
            {"slug": "hook-lab", "promptbase_id": "1", "url": "u", "status": "submitted_pending_review",
             "submitted_at": "2026-09-01T00:00:00Z"},
            self.ledger_path,
        )
        result = select_next.select_next(
            self.catalog_dir, [_agent("Hook Lab")], self.ledger_path
        )
        self.assertIsNone(result["slug"])

    def test_captcha_deferred_slug_is_retried(self):
        self._make_skill("hook-lab", "Hook Lab")
        ledger.record_captcha_deferred("hook-lab", ledger_path=self.ledger_path)
        result = select_next.select_next(
            self.catalog_dir, [_agent("Hook Lab")], self.ledger_path
        )
        self.assertEqual(result["slug"], "hook-lab")

    def test_reels_hook_lab_preferred_over_lower_demand_rank(self):
        # reels-hook-lab is the named winner-family slug and must win even
        # against a numerically lower demand rank on another candidate.
        self._make_skill("ad-hook-lab", "Ad Hook Lab", demand_rank=1)
        self._make_skill("reels-hook-lab", "Reels Hook Lab", demand_rank=3)
        result = select_next.select_next(
            self.catalog_dir,
            [_agent("Ad Hook Lab"), _agent("Reels Hook Lab")],
            self.ledger_path,
        )
        self.assertEqual(result["slug"], "reels-hook-lab")

    def test_demand_rank_breaks_tie_among_non_preferred_slugs(self):
        self._make_skill("ad-hook-lab", "Ad Hook Lab", demand_rank=3)
        self._make_skill("shorts-hook-lab", "Shorts Hook Lab", demand_rank=2)
        result = select_next.select_next(
            self.catalog_dir,
            [_agent("Ad Hook Lab"), _agent("Shorts Hook Lab")],
            self.ledger_path,
        )
        self.assertEqual(result["slug"], "shorts-hook-lab")

    def test_no_catalog_items(self):
        result = select_next.select_next(self.catalog_dir, [], self.ledger_path)
        self.assertEqual(result["reason"], "no_catalog_items_found")


if __name__ == "__main__":
    unittest.main()
