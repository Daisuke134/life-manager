#!/usr/bin/env python3
"""Tests for the pure dashboard-text parser in readback.py (no browser)."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import readback  # noqa: E402
from readback import parse_dashboard_cards, status_for_title  # noqa: E402

# Captured verbatim from https://promptbase.com/account?view=prompts on the
# real seller account, 2026-09-28 (innerText of the Prompts list body).
REAL_DASHBOARD_TEXT = """PromptBase
Create
Jobs
Sell
4
Upgrade
Dashboard
Profile
Prompts
Skills
Apps
Sales
Referrals
Payouts
Boosts
Promotions
Trends
Subscribers
Insights
Tools
Downloads
Uses
Applications
Contracts
Favorites
Perks
Settings
Prompts
Export Data
Status
Approved
Pending
Scheduled
Draft
Declined
Archived
Disputed
Newest
Most Popular
Trending
\U0001f300 Claude
Draft
Reels Hook Lab — Win the Cover Frame
\U0001f300 Claude
Draft
Reels Hook Lab Win The Cover Frame
\U0001f300 Claude
Approved
Hook Lab Win The First 3 Seconds
1"""


class ParseDashboardCardsTest(unittest.TestCase):
    def test_finds_all_real_cards(self):
        cards = parse_dashboard_cards(REAL_DASHBOARD_TEXT)
        self.assertIn(("Approved", "Hook Lab Win The First 3 Seconds"), cards)
        self.assertIn(("Draft", "Reels Hook Lab Win The Cover Frame"), cards)
        self.assertIn(("Draft", "Reels Hook Lab — Win the Cover Frame"), cards)
        # the filter/status option list above the cards must not be
        # misread as cards themselves
        self.assertNotIn(("Approved", "Pending"), cards)

    def test_status_for_title_maps_to_ledger_vocabulary(self):
        self.assertEqual(
            status_for_title(REAL_DASHBOARD_TEXT, "Hook Lab Win The First 3 Seconds"),
            "live",
        )
        self.assertEqual(
            status_for_title(REAL_DASHBOARD_TEXT, "Reels Hook Lab Win The Cover Frame"),
            "draft",
        )

    def test_status_for_unknown_title_is_none(self):
        self.assertIsNone(status_for_title(REAL_DASHBOARD_TEXT, "Nonexistent Listing"))

    def test_empty_text_yields_no_cards(self):
        self.assertEqual(parse_dashboard_cards(""), [])


class ParseSalesTest(unittest.TestCase):
    def test_unrecognized_login_page_is_not_zero_sales(self):
        with self.assertRaisesRegex(ValueError, "sales_readback_unrecognized"):
            readback.parse_sales("PromptBase\nLogin\nEmail\nPassword")

    def test_no_sales_phrase_without_sales_page_structure_is_not_zero(self):
        with self.assertRaisesRegex(ValueError, "sales_readback_unrecognized"):
            readback.parse_sales("Security verification\nNo sales yet")

    def test_explicit_no_sales_message_remains_zero(self):
        self.assertEqual(
            readback.parse_sales("Dashboard\nSales\nNo sales yet"),
            {"sales_count": 0, "net_usd": 0.0, "by_item": {}},
        )

    def test_sale_row_still_parses_amount_and_net(self):
        self.assertEqual(
            readback.parse_sales("Dashboard\nSales\n$4.99\t$3.49\tPaid\tHook Lab"),
            {"sales_count": 1, "net_usd": 3.49,
             "by_item": {"Hook Lab": {"sales": 1, "net_usd": 3.49}}},
        )


@pytest.mark.parametrize(
    ("sales_url", "sales_text", "should_succeed"),
    [
        ("https://promptbase.com/login?view=login", "PromptBase\nLogin\nNo sales yet", False),
        (readback.SALES_URL,
         "PromptBase\nDashboard\nSales\nSecurity verification\nNo sales yet", False),
        (readback.SALES_URL, "PromptBase\nDashboard\nSales\nNo sales yet", True),
    ],
)
@pytest.mark.parametrize(
    "ledger_rows",
    [
        {"hook-lab": {"title": "Hook Lab", "status": "live", "sales_usd": 0.0}},
        {},
    ],
    ids=["tracked-listing", "empty-ledger"],
)
def test_run_does_not_write_zero_for_unverified_sales_page(
    tmp_path, monkeypatch, sales_url, sales_text, should_succeed, ledger_rows,
):

    class FakeResponse:
        status = 200

    class FakePage:
        url = "about:blank"
        body = ""
        visited = []

        def goto(self, url, **kwargs):
            self.visited.append(url)
            if url == readback.PROMPTS_URL:
                self.url = url
                self.body = REAL_DASHBOARD_TEXT
            else:
                self.url = sales_url
                self.body = sales_text
            return FakeResponse()

        def wait_for_timeout(self, _milliseconds):
            pass

        def inner_text(self, _selector):
            return self.body

        def close(self):
            pass

    page = FakePage()
    browser = SimpleNamespace(contexts=[SimpleNamespace(new_page=lambda: page)])
    fake_playwright = SimpleNamespace(
        chromium=SimpleNamespace(connect_over_cdp=lambda _endpoint: browser),
    )

    class FakeManager:
        def __enter__(self):
            return fake_playwright

        def __exit__(self, *_args):
            return False

    import playwright.sync_api
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: FakeManager())
    monkeypatch.setattr(readback.ledger_mod, "latest_by_slug", lambda: ledger_rows)
    summary = tmp_path / "promptbase-sales.json"
    monkeypatch.setattr(readback, "SUMMARY_PATH", summary)

    if should_succeed:
        result = readback.run("http://127.0.0.1:9222")
        assert result["ok"] is True
        assert result["checked"] == len(ledger_rows)
        assert result["sales"]["sales_count"] == 0
        assert page.visited == [readback.PROMPTS_URL, readback.SALES_URL]
        assert summary.exists()
    else:
        with pytest.raises(RuntimeError, match="promptbase_sales_readback_unverified"):
            readback.run("http://127.0.0.1:9222")
        assert not summary.exists()


if __name__ == "__main__":
    unittest.main()
