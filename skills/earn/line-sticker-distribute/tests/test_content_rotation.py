#!/usr/bin/env python3
"""Focused tests for the per-slot content-type rotation (SSOT L17 gap #1):
the model decides content_type + beat_texts (caption_compose.validate_content_plan),
render_video.render overlays per-beat text instead of the repeated title when given one,
and line_sticker_distribute.resolve_link_in_caption makes link_in_caption date-based.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import caption_compose  # noqa: E402
import line_sticker_distribute as distribute  # noqa: E402
import line_sticker_distribute_ledger as ledger  # noqa: E402
import render_video  # noqa: E402


class ValidateContentPlanTest(unittest.TestCase):
    def test_showcase_needs_no_beat_texts(self):
        plan = caption_compose.validate_content_plan(
            {"hook": "h", "content_type": "showcase", "beat_texts": []}, clip_count=4,
        )
        self.assertEqual(plan, {"hook": "h", "content_type": "showcase", "beat_texts": []})

    def test_daily_life_requires_beat_texts(self):
        with self.assertRaises(RuntimeError):
            caption_compose.validate_content_plan(
                {"hook": "h", "content_type": "daily_life", "beat_texts": []}, clip_count=4,
            )

    def test_beat_texts_trimmed_to_clip_count(self):
        plan = caption_compose.validate_content_plan(
            {"hook": "h", "content_type": "daily_life", "beat_texts": ["a", "b", "c", "d", "e"]},
            clip_count=3,
        )
        self.assertEqual(plan["beat_texts"], ["a", "b", "c"])

    def test_beat_texts_padded_when_short(self):
        plan = caption_compose.validate_content_plan(
            {"hook": "h", "content_type": "reaction_pick", "beat_texts": ["a", "b"]}, clip_count=4,
        )
        self.assertEqual(plan["beat_texts"], ["a", "b", "a", "b"])

    def test_unknown_content_type_rejected(self):
        with self.assertRaises(RuntimeError):
            caption_compose.validate_content_plan(
                {"hook": "h", "content_type": "not_a_real_type", "beat_texts": []}, clip_count=1,
            )

    def test_empty_hook_rejected(self):
        with self.assertRaises(RuntimeError):
            caption_compose.validate_content_plan(
                {"hook": "   ", "content_type": "showcase", "beat_texts": []}, clip_count=1,
            )


class RenderBeatTextsValidationTest(unittest.TestCase):
    def test_beat_texts_length_must_match_clip_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                render_video.render(
                    [Path(tmp) / "a.mp4", Path(tmp) / "b.mp4"], "title", "https://store.line.me/x",
                    Path(tmp) / "out.mp4", beat_texts=["only-one"],
                )


class RecentContentTypesTest(unittest.TestCase):
    def test_most_recent_first_and_limited(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.json"
            ledger.record(ledger_path, "lane-a-2026-10-05T08:00:00Z", {
                "status": "published", "content_type": "showcase",
            })
            ledger.record(ledger_path, "lane-a-2026-10-06T08:00:00Z", {
                "status": "published", "content_type": "daily_life",
            })
            ledger.record(ledger_path, "lane-a-2026-10-07T08:00:00Z", {
                "status": "published", "content_type": "seasonal_hook",
            })
            # a different lane must not leak in
            ledger.record(ledger_path, "lane-b-2026-10-08T08:00:00Z", {
                "status": "published", "content_type": "reaction_pick",
            })
            recent = ledger.recent_content_types(ledger_path, "lane-a", limit=2)
            self.assertEqual(recent, ["seasonal_hook", "daily_life"])

    def test_no_history_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.json"
            self.assertEqual(ledger.recent_content_types(ledger_path, "lane-a"), [])


class ResolveLinkInCaptionTest(unittest.TestCase):
    def test_static_true_when_no_date_field(self):
        account = {"link_in_caption": True, "timezone": "Asia/Tokyo"}
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertTrue(distribute.resolve_link_in_caption(account, now))

    def test_date_based_false_before_the_date(self):
        account = {
            "link_in_caption": True, "link_in_caption_from": "2026-10-10", "timezone": "Asia/Tokyo",
        }
        now = datetime(2026, 10, 8, 23, 0, tzinfo=timezone.utc)  # 2026-10-09 08:00 JST -- still before
        self.assertFalse(distribute.resolve_link_in_caption(account, now))

    def test_date_based_true_on_or_after_the_date(self):
        account = {
            "link_in_caption": False, "link_in_caption_from": "2026-10-10", "timezone": "Asia/Tokyo",
        }
        now = datetime(2026, 10, 9, 15, 1, tzinfo=timezone.utc)  # 2026-10-10 00:01 JST
        self.assertTrue(distribute.resolve_link_in_caption(account, now))


if __name__ == "__main__":
    unittest.main()
