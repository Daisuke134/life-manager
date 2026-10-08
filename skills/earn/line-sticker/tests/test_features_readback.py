"""Unit tests for the daily LINE Creators Market feature-campaign (特集) readback (no network, no
browser). Mirrors ``tests/test_sales_readback.py``'s structure.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import features_readback as MODULE  # noqa: E402


class ParseFeatureRadio(unittest.TestCase):
    def test_non_participation_option_is_dropped(self) -> None:
        self.assertIsNone(MODULE.parse_feature_radio("on", "参加しない", datetime.date(2026, 10, 8)))

    def test_non_feature_radios_on_the_create_page_are_dropped(self) -> None:
        self.assertIsNone(MODULE.parse_feature_radio("true", "「スタンプ」", datetime.date(2026, 10, 8)))

    def test_label_without_a_title_is_dropped(self) -> None:
        self.assertIsNone(MODULE.parse_feature_radio("799", "something unparseable", datetime.date(2026, 10, 8)))

    def test_single_end_date_period_parses_this_year(self) -> None:
        out = MODULE.parse_feature_radio("811", "「秋を感じるスタンプ」(受付 〜10/19)", datetime.date(2026, 10, 8))
        self.assertEqual(out, {"value": "811", "title": "秋を感じるスタンプ", "deadline": "2026-10-19"})

    def test_title_in_full_width_brackets_is_extracted(self) -> None:
        out = MODULE.parse_feature_radio("820", "「犬の日 スタンプ」(受付 〜11/16)", datetime.date(2026, 10, 8))
        self.assertEqual(out["title"], "犬の日 スタンプ")
        self.assertEqual(out["deadline"], "2026-11-16")

    def test_range_period_uses_the_last_date_as_the_deadline(self) -> None:
        out = MODULE.parse_feature_radio("835", "「冬を感じるスタンプ」(受付 10/2〜12/4)", datetime.date(2026, 10, 8))
        self.assertEqual(out["deadline"], "2026-12-04")

    def test_a_deadline_already_passed_this_year_rolls_to_next_year(self) -> None:
        # Measured-live-style label naming a January date, read in October: it means next January.
        out = MODULE.parse_feature_radio("901", "「お正月スタンプ」(受付 〜1/5)", datetime.date(2026, 10, 8))
        self.assertEqual(out["deadline"], "2027-01-05")

    def test_period_without_any_date_leaves_deadline_unknown(self) -> None:
        out = MODULE.parse_feature_radio("902", "「テスト」(受付 未定)", datetime.date(2026, 10, 8))
        self.assertIsNone(out["deadline"])


class MatchAnnounceLink(unittest.TestCase):
    def test_substring_match_finds_the_announce_href(self) -> None:
        links = [
            {"title": "「冬を感じるスタンプ」特集募集について", "href": "/my/x/announce/article?id=123"},
            {"title": "審査中のアイテムについて", "href": "/my/x/announce/article?id=456"},
        ]
        self.assertEqual(MODULE.match_announce_link("冬を感じるスタンプ", links), "/my/x/announce/article?id=123")

    def test_no_matching_title_returns_none(self) -> None:
        links = [{"title": "無関係なお知らせ", "href": "/my/x/announce/article?id=1"}]
        self.assertIsNone(MODULE.match_announce_link("冬を感じるスタンプ", links))


class ShouldRunToday(unittest.TestCase):
    def test_no_existing_ledger_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(MODULE.should_run_today(Path(tmp) / "features.json"))

    def test_already_observed_today_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "features.json"
            ledger.write_text(json.dumps({"observed_at": MODULE.now_utc().isoformat()}))
            self.assertFalse(MODULE.should_run_today(ledger))

    def test_observed_yesterday_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "features.json"
            yesterday = MODULE.now_utc() - datetime.timedelta(days=1, hours=1)
            ledger.write_text(json.dumps({"observed_at": yesterday.isoformat()}))
            self.assertTrue(MODULE.should_run_today(ledger))


class LiveCreatePageLabel(unittest.TestCase):
    def test_live_feature_block_text_parses_title_and_year_qualified_deadline(self) -> None:
        # Text of the radio-835 block on /sticker/create, 2026-10-08.
        label = ("タイトル： 「冬を感じるスタンプ」特集 審査受付期間： 2026年10月2日(金)11:00 〜 2026年12月4日(金)10:59"
                 " (日本時間) バナー掲載期間(予定)： 2026年11月11日(水)11:00 〜 2027年1月8日(金)10:59 (日本時間)")
        out = MODULE.parse_feature_radio("835", label, datetime.date(2026, 10, 8))
        self.assertEqual(out, {"value": "835", "title": "冬を感じるスタンプ", "deadline": "2026-12-04"})


if __name__ == "__main__":
    unittest.main()
