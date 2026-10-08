#!/usr/bin/env python3
"""Focused tests for the date-gated, capped, idempotent engagement and bio-link steps
(SSOT L17 gaps #2/#4): no action before day 3 (ig-account-warmer ban-signal precedent),
no action before the configured date, and at most one attempt per idempotency key.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import bio_link_setup  # noqa: E402
import date_gate  # noqa: E402
import engagement_daily  # noqa: E402
import line_sticker_distribute_ledger as ledger  # noqa: E402


class DateGateTest(unittest.TestCase):
    def test_is_on_or_after_false_before(self):
        now = datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc)  # 2026-10-10 08:00 JST
        self.assertFalse(date_gate.is_on_or_after(now, "Asia/Tokyo", "2026-10-11"))

    def test_is_on_or_after_true_on_the_day(self):
        now = datetime(2026, 10, 9, 15, 1, tzinfo=timezone.utc)  # 2026-10-10 00:01 JST
        self.assertTrue(date_gate.is_on_or_after(now, "Asia/Tokyo", "2026-10-10"))

    def test_days_since(self):
        now = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(date_gate.days_since(now, "UTC", "2026-10-07"), 3)

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError):
            date_gate.is_on_or_after(datetime(2026, 1, 1), "UTC", "2026-01-01")


class EngagementDueTodayTest(unittest.TestCase):
    ACCOUNT = {
        "lane_id": "stardust-doubutsu-instagram", "timezone": "Asia/Tokyo",
        "created_at": "2026-10-07",
    }

    def test_not_due_before_day_3(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "engagement-ledger.json"
            # 2026-10-08 JST -- day 2, still inside the 72h ban-critical window
            now = datetime(2026, 10, 7, 20, 0, tzinfo=timezone.utc)
            due, key = engagement_daily.engagement_due_today(self.ACCOUNT, now, ledger_path)
            self.assertFalse(due)
            self.assertIsNone(key)

    def test_due_from_day_3(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "engagement-ledger.json"
            now = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)  # 2026-10-10 JST, day 3
            due, key = engagement_daily.engagement_due_today(self.ACCOUNT, now, ledger_path)
            self.assertTrue(due)
            self.assertEqual(key, "stardust-doubutsu-instagram-2026-10-10")

    def test_no_created_at_is_never_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "engagement-ledger.json"
            now = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
            due, key = engagement_daily.engagement_due_today(
                {"lane_id": "x", "timezone": "UTC"}, now, ledger_path,
            )
            self.assertFalse(due)

    def test_already_attempted_today_is_not_due_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "engagement-ledger.json"
            now = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
            ledger.record(ledger_path, "stardust-doubutsu-instagram-2026-10-10", {
                "status": "error", "likes_done": 0, "follows_done": 0,
            })
            due, key = engagement_daily.engagement_due_today(self.ACCOUNT, now, ledger_path)
            self.assertFalse(due)
            self.assertEqual(key, "stardust-doubutsu-instagram-2026-10-10")


class BioLinkDueTest(unittest.TestCase):
    ACCOUNT = {
        "lane_id": "stardust-doubutsu-instagram", "timezone": "Asia/Tokyo",
        "bio_link_from": "2026-10-10",
        "author_url": "https://store.line.me/stickershop/author/5796043/ja",
    }

    def test_not_due_before_the_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "engagement-ledger.json"
            now = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)
            due, key = bio_link_setup.bio_link_due(self.ACCOUNT, now, ledger_path)
            self.assertFalse(due)
            self.assertIsNone(key)

    def test_due_on_or_after_the_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "engagement-ledger.json"
            now = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)  # 2026-10-10 JST
            due, key = bio_link_setup.bio_link_due(self.ACCOUNT, now, ledger_path)
            self.assertTrue(due)
            self.assertEqual(key, "stardust-doubutsu-instagram-bio-link")

    def test_only_once_ever(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "engagement-ledger.json"
            now = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
            ledger.record(ledger_path, "stardust-doubutsu-instagram-bio-link", {"status": "ok"})
            due, key = bio_link_setup.bio_link_due(self.ACCOUNT, now, ledger_path)
            self.assertFalse(due)

    def test_missing_author_url_is_never_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "engagement-ledger.json"
            now = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)
            account = {"lane_id": "x", "timezone": "UTC", "bio_link_from": "2026-10-10"}
            due, key = bio_link_setup.bio_link_due(account, now, ledger_path)
            self.assertFalse(due)


if __name__ == "__main__":
    unittest.main()
