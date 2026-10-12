"""Unit tests for the daily LINE Creators Market sales/分配 readback (no network, no browser).

Fixtures under tests/fixtures/ are real page inner_text captured 2026-10-07 from the
creator.line.me 売上・統計情報 (stats/sticker) and 送金申請 (payment_request) pages, with the
seller's display name replaced by a placeholder.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

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

    def test_parses_official_product_ids_from_detail_links(self) -> None:
        rows = MODULE.parse_sticker_table_rows([
            {
                "href": "https://creator.line.me/my/account/stats/sticker/48077815",
                "text": "毎日使えるカワウソスタンプ\t2026/10/6\t￥0",
            },
            {
                "href": "https://creator.line.me/my/account/stats/sticker/42100028",
                "text": "いりや\t2025/12/1\t￥189",
            },
        ])
        self.assertEqual(rows, [
            {"product_id": "48077815", "title_ja": "毎日使えるカワウソスタンプ", "sale_start_date": "2026/10/6", "sales_jpy": 0},
            {"product_id": "42100028", "title_ja": "いりや", "sale_start_date": "2025/12/1", "sales_jpy": 189},
        ])


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
        rows = MODULE.parse_sticker_table_rows([
            {
                "href": "https://creator.line.me/my/account/stats/sticker/48077815",
                "text": "毎日使えるカワウソスタンプ\t2026/10/6\t￥0",
            },
            {
                "href": "https://creator.line.me/my/account/stats/sticker/42100028",
                "text": "いりや\t2025/12/1\t￥189",
            },
        ])
        tracked = [{"product_id": "48077815", "title_ja": "毎日使えるカワウソスタンプ"}]
        products = MODULE.match_products(tracked, rows)
        self.assertEqual(products, [{
            "product_id": "48077815", "title_ja": "毎日使えるカワウソスタンプ",
            "sale_start_date": "2026/10/6", "sales_jpy": 0,
        }])

    def test_tracked_product_with_no_matching_row_stays_unknown(self) -> None:
        tracked = [{"product_id": "48128258", "title_ja": "動く！テストくまの敬語返事"}]
        rows = MODULE.parse_sticker_table_rows([
            {
                "href": "https://creator.line.me/my/account/stats/sticker/48077815",
                "text": "動く！テストくまの敬語返事\t2026/10/6\t￥189",
            },
        ])
        products = MODULE.match_products(tracked, rows)
        self.assertEqual(products, [{
            "product_id": "48128258", "title_ja": "動く！テストくまの敬語返事",
            "sale_start_date": None, "sales_jpy": None,
        }])

    def test_same_title_does_not_copy_sales_between_distinct_product_ids(self) -> None:
        tracked = [
            {"product_id": "set-a", "title_ja": "重複タイトル"},
            {"product_id": "set-b", "title_ja": "重複タイトル"},
        ]
        rows = [{
            "product_id": "set-a", "title_ja": "重複タイトル",
            "sale_start_date": "2026/10/12", "sales_jpy": 189,
        }]
        self.assertEqual(MODULE.match_products(tracked, rows), [
            {"product_id": "set-a", "title_ja": "重複タイトル", "sale_start_date": "2026/10/12", "sales_jpy": 189},
            {"product_id": "set-b", "title_ja": "重複タイトル", "sale_start_date": None, "sales_jpy": None},
        ])

    def test_duplicate_official_management_id_stays_unknown(self) -> None:
        tracked = [{"product_id": "set-a", "title_ja": "公式タイトル"}]
        rows = [
            {"product_id": "set-a", "title_ja": "公式タイトル", "sale_start_date": "2026/10/12", "sales_jpy": 189},
            {"product_id": "set-a", "title_ja": "公式タイトル", "sale_start_date": "2026/10/12", "sales_jpy": 0},
        ]
        self.assertEqual(MODULE.match_products(tracked, rows), [
            {"product_id": "set-a", "title_ja": "公式タイトル", "sale_start_date": None, "sales_jpy": None},
        ])

    def test_duplicate_tracked_management_id_does_not_copy_one_row_twice(self) -> None:
        tracked = [
            {"product_id": "set-a", "title_ja": "商品A"},
            {"product_id": "set-a", "title_ja": "商品B"},
        ]
        rows = [{
            "product_id": "set-a", "title_ja": "商品A",
            "sale_start_date": "2026/10/12", "sales_jpy": 189,
        }]
        self.assertEqual(MODULE.match_products(tracked, rows), [
            {"product_id": "set-a", "title_ja": "商品A", "sale_start_date": None, "sales_jpy": None},
            {"product_id": "set-a", "title_ja": "商品B", "sale_start_date": None, "sales_jpy": None},
        ])


class FetchTableCompleteness(unittest.TestCase):
    def test_partial_dom_rows_are_not_a_successful_stats_readback(self) -> None:
        row = {
            "href": "https://creator.line.me/my/account/stats/sticker/48077815",
            "text": "毎日使えるカワウソスタンプ\t2026/10/6\t￥0",
        }
        snapshot = {
            "ready_state": "complete",
            "table_count": 1,
            "rows": [row],
            "body_row_count": 15,
            "page_numbers": [1],
            "current_page": 1,
            "has_next_page": False,
            "busy": False,
        }

        class FakePage:
            url = "https://creator.line.me/my/account/stats/sticker"

            async def goto(self, url: str, **_kwargs: object) -> None:
                self.url = url

            async def wait_for_timeout(self, _milliseconds: int) -> None:
                return None

            async def wait_for_load_state(self, *_args: object, **_kwargs: object) -> None:
                return None

            async def evaluate(self, _script: str) -> dict:
                return snapshot

            def locator(self, _selector: str):
                class FakeLocator:
                    async def evaluate_all(self, _script: str) -> list[dict]:
                        return [row]

                return FakeLocator()

            async def inner_text(self, _selector: str) -> str:
                return PAYMENT_TEXT

            async def close(self) -> None:
                return None

        class FakeContext:
            async def new_page(self) -> FakePage:
                return FakePage()

        class FakeBrowser:
            contexts = [FakeContext()]

        class FakeChromium:
            async def connect_over_cdp(self, _cdp: str) -> FakeBrowser:
                return FakeBrowser()

        class FakePlaywright:
            chromium = FakeChromium()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args: object) -> None:
                return None

        package = types.ModuleType("playwright")
        async_api = types.ModuleType("playwright.async_api")
        async_api.async_playwright = FakePlaywright
        package.async_api = async_api
        with patch.dict(sys.modules, {"playwright": package, "playwright.async_api": async_api}):
            result = asyncio.run(MODULE._fetch("http://127.0.0.1:9222"))
        self.assertEqual(result["status"], "incomplete_stats_table")


class TrackedProducts(unittest.TestCase):
    def test_uses_submitted_title_in_creators_item_not_planned_listing_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            set_dir = Path(tmp) / "set-001"
            set_dir.mkdir()
            (set_dir / "creators-item.json").write_text(json.dumps({
                "product_id": "48077815", "title_ja": "公式に提出したタイトル",
            }))
            (set_dir / "listing.json").write_text(json.dumps({
                "title": {"ja": "制作計画の旧タイトル"},
            }))
            self.assertEqual(MODULE._tracked_products(Path(tmp)), [
                {"product_id": "48077815", "title_ja": "公式に提出したタイトル"},
            ])


class ShouldRunToday(unittest.TestCase):
    def test_no_existing_ledger_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(MODULE.should_run_today(Path(tmp) / "sales.json"))

    def test_already_observed_today_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "sales.json"
            ledger.write_text(json.dumps({
                "schema_version": 2,
                "observed_at": MODULE.now_utc().isoformat(),
            }))
            self.assertFalse(MODULE.should_run_today(ledger))

    def test_same_day_and_same_tracked_id_set_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "sales.json"
            ledger.write_text(json.dumps({
                "schema_version": 2,
                "observed_at": MODULE.now_utc().isoformat(),
                "products": [{"product_id": "48100000", "sales_jpy": 0}],
            }))
            tracked = [{"product_id": "48100000", "title_ja": "same product"}]
            self.assertFalse(MODULE.should_run_today(ledger, tracked))

    def test_same_day_legacy_snapshot_runs_after_schema_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "sales.json"
            ledger.write_text(json.dumps({"observed_at": MODULE.now_utc().isoformat()}))
            self.assertTrue(MODULE.should_run_today(ledger))

    def test_observed_yesterday_runs(self) -> None:
        import datetime
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "sales.json"
            yesterday = MODULE.now_utc() - datetime.timedelta(days=1, hours=1)
            ledger.write_text(json.dumps({"observed_at": yesterday.isoformat()}))
            self.assertTrue(MODULE.should_run_today(ledger))

    def test_main_refreshes_same_day_snapshot_when_a_tracked_id_is_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            set_dir = state / "set-037"
            set_dir.mkdir()
            (set_dir / "creators-item.json").write_text(json.dumps({
                "product_id": "48279443", "title_ja": "新商品",
            }))
            ledger = state / "sales.json"
            ledger.write_text(json.dumps({
                "schema_version": 2,
                "observed_at": MODULE.now_utc().isoformat(),
                "products": [{"product_id": "48100000", "sales_jpy": None}],
            }))

            async def fetch(_cdp: str) -> dict:
                return {
                    "status": "ok",
                    "stats_rows": [{
                        "href": "https://creator.line.me/my/account/stats/sticker/48279443",
                        "text": "新商品\t2026/10/13\t￥0",
                    }],
                    "payment_text": (
                        "送金可能額¥0\n対象期間\t2025.12.01-2025.12.31\n"
                        "分配額\t¥0\n源泉所得税\t¥0"
                    ),
                }

            completed = types.SimpleNamespace(
                returncode=0, stdout="http://127.0.0.1:9231\n", stderr="",
            )
            output = io.StringIO()
            with (
                patch.object(MODULE, "_fetch", fetch),
                patch.object(MODULE.subprocess, "run", return_value=completed),
                patch.object(sys, "argv", ["sales_readback.py", "--state-root", str(state)]),
                contextlib.redirect_stdout(output),
            ):
                MODULE.main()

            self.assertEqual(json.loads(output.getvalue()), {"status": "ok", "products": 1})
            refreshed = json.loads(ledger.read_text())
            self.assertEqual(refreshed["products"], [{
                "product_id": "48279443", "title_ja": "新商品",
                "sale_start_date": "2026/10/13", "sales_jpy": 0,
            }])


class ReadbackEntrypoint(unittest.TestCase):
    def _run_with_busy_script(self, busy_script: str, item_count: int) -> tuple[int, list[str], str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state" / "line-sticker"
            for number in range(1, item_count + 1):
                set_dir = state / f"set-{number:03d}"
                set_dir.mkdir(parents=True)
                (set_dir / "creators-item.json").write_text(json.dumps({"product_id": str(number)}))
            calls = root / "calls.txt"
            fake_python = root / "python"
            fake_python.write_text(
                "#!/bin/sh\n"
                "name=\"${1##*/}\"\n"
                "printf '%s\\n' \"$name\" >> \"$CALL_LOG\"\n"
                "[ \"$name\" != \"$BUSY_SCRIPT\" ] || exit 75\n"
                "exit 0\n"
            )
            fake_python.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "BUSY_SCRIPT": busy_script,
                "CALL_LOG": str(calls),
                "LIFE_MANAGER_PYTHON": str(fake_python),
                "LIFE_MANAGER_REPO": str(MODULE_ROOT.parents[2]),
                "LIFE_MANAGER_STATE_HOME": str(root / "state"),
            })

            result = subprocess.run(
                ["bash", str(MODULE_ROOT / "line-sticker-readback.sh")],
                capture_output=True, text=True, env=env, check=False,
            )
            return result.returncode, calls.read_text().splitlines(), result.stdout + result.stderr

    def test_sales_browser_busy_skips_items_and_features_but_keeps_public_market_sweep(self) -> None:
        code, calls, output = self._run_with_busy_script("sales_readback.py", item_count=2)
        self.assertEqual(code, 75, output)
        self.assertEqual(calls, ["sales_readback.py", "market.py"])

    def test_first_item_browser_busy_skips_remaining_items_and_features(self) -> None:
        code, calls, output = self._run_with_busy_script("creators_readback.py", item_count=2)
        self.assertEqual(code, 75, output)
        self.assertEqual(calls, ["sales_readback.py", "creators_readback.py", "market.py"])


if __name__ == "__main__":
    unittest.main()
