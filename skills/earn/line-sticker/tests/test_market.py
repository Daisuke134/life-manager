"""Unit tests for the LINE STORE top-seller market sweep (no network, no model).

Fixtures under tests/fixtures/market_*.html are trimmed real page excerpts: a showcase ranking
block, a product page's schema.org JSON-LD + sticker-preview list, and an author page's product
links.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(MODULE_ROOT))
import market as MODULE  # noqa: E402

SHOWCASE_HTML = (FIXTURES / "market_showcase.html").read_text()
PRODUCT_HTML = (FIXTURES / "market_product.html").read_text()
AUTHOR_HTML = (FIXTURES / "market_author.html").read_text()


class ParseShowcaseProductIds(unittest.TestCase):
    def test_parses_product_ids_in_rank_order_deduped(self) -> None:
        self.assertEqual(
            MODULE.parse_showcase_product_ids(SHOWCASE_HTML),
            ["32411274", "21802595", "35452767"],
        )

    def test_no_products_returns_empty_list(self) -> None:
        self.assertEqual(MODULE.parse_showcase_product_ids("<html></html>"), [])


class ParseProductPage(unittest.TestCase):
    def test_parses_title_description_price_author_and_sticker_count(self) -> None:
        detail = MODULE.parse_product_page(PRODUCT_HTML)
        self.assertEqual(detail["title"], "ちいかわ(ハチワレ多)")
        self.assertIn("ハチワレ", detail["description"])
        self.assertEqual(detail["price_jpy"], 190)
        self.assertEqual(detail["author"], "ナガノ")
        self.assertEqual(detail["author_url"], "https://store.line.me/stickershop/author/153187/ja")
        self.assertEqual(detail["sticker_count"], 6)
        self.assertEqual(detail["format"], "static")

    def test_missing_ldjson_leaves_fields_none(self) -> None:
        detail = MODULE.parse_product_page("<html>no ld+json here</html>")
        self.assertIsNone(detail["title"])
        self.assertIsNone(detail["price_jpy"])
        self.assertIsNone(detail["sticker_count"])
        self.assertEqual(detail["format"], "unknown")

    def test_any_animation_sticker_makes_the_whole_set_animated(self) -> None:
        html = PRODUCT_HTML.replace("&quot;type&quot; : &quot;static&quot;", "&quot;type&quot; : &quot;animation&quot;", 1)
        self.assertEqual(MODULE.parse_product_page(html)["format"], "animated")


class ParseAuthorSetCount(unittest.TestCase):
    def test_counts_distinct_products_on_the_authors_page(self) -> None:
        self.assertEqual(MODULE.parse_author_set_count(AUTHOR_HTML), 3)

    def test_no_products_is_zero(self) -> None:
        self.assertEqual(MODULE.parse_author_set_count("<html></html>"), 0)


class SweepProductIds(unittest.TestCase):
    def test_dedups_across_multiple_showcase_pages_and_caps_the_limit(self) -> None:
        urls = list(MODULE.SHOWCASE_URLS)
        pages = {
            urls[0]: "<li><a href=\"/stickershop/product/1/ja\"></a></li>",
            urls[1]: "<li><a href=\"/stickershop/product/1/ja\"></a></li><li><a href=\"/stickershop/product/2/ja\"></a></li>",
            urls[2]: "<li><a href=\"/stickershop/product/3/ja\"></a></li>",
        }
        ids = MODULE.sweep_product_ids(fetch=lambda url: pages[url])
        self.assertEqual(ids, ["1", "2", "3"])

    def test_caps_to_the_limit(self) -> None:
        urls = list(MODULE.SHOWCASE_URLS)
        html = "".join(f'<li><a href="/stickershop/product/{n}/ja"></a></li>' for n in range(100))
        ids = MODULE.sweep_product_ids(fetch=lambda url: html if url == urls[0] else "", limit=5)
        self.assertEqual(len(ids), 5)


class BuildItems(unittest.TestCase):
    def test_builds_one_compact_item_per_product_and_reuses_author_lookups(self) -> None:
        author_fetches = []

        def fake_fetch(url):
            if "/product/" in url:
                return PRODUCT_HTML
            author_fetches.append(url)
            return AUTHOR_HTML

        items = MODULE.build_items(["29118925", "12499968"], fetch=fake_fetch)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["product_id"], "29118925")
        self.assertEqual(items[0]["author_sets"], 3)
        self.assertEqual(items[0]["product_url"], "https://store.line.me/stickershop/product/29118925/ja")
        self.assertIsNone(items[0]["text_or_no_text"])
        # same author on both products: author page fetched once, not twice.
        self.assertEqual(len(author_fetches), 1)

    def test_fetch_failure_for_one_product_skips_it_without_raising(self) -> None:
        items = MODULE.build_items(["1", "2"], fetch=lambda url: None)
        self.assertEqual(items, [])


class ShouldRunToday(unittest.TestCase):
    def test_no_existing_market_file_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(MODULE.should_run_today(Path(tmp) / "market.json"))

    def test_already_observed_today_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            market_file = Path(tmp) / "market.json"
            market_file.write_text(json.dumps({"observed_at": MODULE.now_utc().isoformat()}))
            self.assertFalse(MODULE.should_run_today(market_file))

    def test_observed_yesterday_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            market_file = Path(tmp) / "market.json"
            yesterday = MODULE.now_utc() - datetime.timedelta(days=1, hours=1)
            market_file.write_text(json.dumps({"observed_at": yesterday.isoformat()}))
            self.assertTrue(MODULE.should_run_today(market_file))


if __name__ == "__main__":
    unittest.main()
