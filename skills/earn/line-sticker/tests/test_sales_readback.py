"""Unit tests for the daily LINE Creators Market sales/分配 readback (no network, no browser).

Fixtures under tests/fixtures/ are real page inner_text captured 2026-10-07 from the
creator.line.me 売上・統計情報 (stats/sticker) and 送金申請 (payment_request) pages, with the
seller's display name replaced by a placeholder.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(MODULE_ROOT))
import sales_readback as MODULE  # noqa: E402

STATS_TEXT = (FIXTURES / "stats_sticker.txt").read_text()
PAYMENT_TEXT = (FIXTURES / "payment_request.txt").read_text()


class ParseStickerStats(unittest.TestCase):
    def test_parses_each_row_title_date_and_cumulative_sales(self) -> None:
        rows = MODULE.parse_sticker_stats(STATS_TEXT)
        self.assertEqual(rows, [
            {"title_ja": "毎日使えるカワウソスタンプ", "sale_start_date": "2026/10/6", "sales_jpy": 0},
            {"title_ja": "いりや", "sale_start_date": "2025/12/1", "sales_jpy": 189},
        ])

    def test_empty_table_returns_empty_list(self) -> None:
        self.assertEqual(MODULE.parse_sticker_stats("売上・統計情報：アイテム\nサムネイル\tタイトル\t販売開始日 \t売上（累計） \n"), [])


class ParsePaymentRequest(unittest.TestCase):
    def test_parses_payable_and_current_period(self) -> None:
        result = MODULE.parse_payment_request(PAYMENT_TEXT)
        self.assertEqual(result, {
            "payable_jpy": 0,
            "current_period": {"period": "2025.12.01-2025.12.31", "distributed_jpy": 0, "withholding_tax_jpy": 0},
        })

    def test_missing_fields_stay_unknown_not_zero(self) -> None:
        result = MODULE.parse_payment_request("送金申請\n\n送金の流れ\n")
        self.assertIsNone(result["payable_jpy"])
        self.assertIsNone(result["current_period"])


class BuildLedgerRow(unittest.TestCase):
    def test_matches_known_titles_to_tracked_product_ids_and_ignores_untracked(self) -> None:
        rows = MODULE.parse_sticker_stats(STATS_TEXT)
        tracked = [{"product_id": "48077815", "title_ja": "毎日使えるカワウソスタンプ"}]
        products = MODULE.match_products(tracked, rows)
        self.assertEqual(products, [{
            "product_id": "48077815", "title_ja": "毎日使えるカワウソスタンプ",
            "sale_start_date": "2026/10/6", "sales_jpy": 0,
        }])

    def test_tracked_product_with_no_matching_row_stays_unknown(self) -> None:
        tracked = [{"product_id": "48128258", "title_ja": "動く！テストくまの敬語返事"}]
        products = MODULE.match_products(tracked, MODULE.parse_sticker_stats(STATS_TEXT))
        self.assertEqual(products, [{
            "product_id": "48128258", "title_ja": "動く！テストくまの敬語返事",
            "sale_start_date": None, "sales_jpy": None,
        }])


class ShouldRunToday(unittest.TestCase):
    def test_no_existing_ledger_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(MODULE.should_run_today(Path(tmp) / "sales.json"))

    def test_already_observed_today_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "sales.json"
            ledger.write_text(json.dumps({"observed_at": MODULE.now_utc().isoformat()}))
            self.assertFalse(MODULE.should_run_today(ledger))

    def test_observed_yesterday_runs(self) -> None:
        import datetime
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "sales.json"
            yesterday = MODULE.now_utc() - datetime.timedelta(days=1, hours=1)
            ledger.write_text(json.dumps({"observed_at": yesterday.isoformat()}))
            self.assertTrue(MODULE.should_run_today(ledger))


if __name__ == "__main__":
    unittest.main()
