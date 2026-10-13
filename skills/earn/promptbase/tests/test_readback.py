#!/usr/bin/env python3
"""Tests for the pure dashboard-text parser in readback.py (no browser)."""
import json
import os
import stat
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

    def test_status_filters_and_sort_options_are_not_prompt_cards(self):
        filter_only = """Dashboard
Prompts
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
Trending"""

        self.assertEqual(parse_dashboard_cards(filter_only), [])
        self.assertFalse(readback.prompts_dashboard_is_official(readback.PROMPTS_URL, filter_only))

    def test_dashboard_must_contain_each_tracked_title(self):
        self.assertTrue(readback.prompts_dashboard_contains_titles(
            REAL_DASHBOARD_TEXT,
            ["Hook Lab Win The First 3 Seconds", "Reels Hook Lab — Win the Cover Frame"],
        ))
        self.assertFalse(readback.prompts_dashboard_contains_titles(
            REAL_DASHBOARD_TEXT,
            ["Hook Lab Win The First 3 Seconds", "New Listing Not Loaded Yet"],
        ))

    def test_waits_through_transient_login_shell_until_cards_render(self):
        class FakePage:
            url = readback.PROMPTS_URL
            bodies = ["Dashboard\nPrompts\nLogin", REAL_DASHBOARD_TEXT]
            waits = 0

            def inner_text(self, _selector):
                return self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]

            def wait_for_timeout(self, _milliseconds):
                self.waits += 1

        page = FakePage()
        result = readback.wait_for_prompt_dashboard(
            page, ["Hook Lab Win The First 3 Seconds"], timeout_ms=1000,
        )

        self.assertEqual(result, REAL_DASHBOARD_TEXT)
        self.assertEqual(page.waits, 1)


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
    ("sales_url", "sales_text"),
    [
        ("https://promptbase.com/login?view=login", "PromptBase\nLogin\nNo sales yet"),
        (readback.SALES_URL,
         "PromptBase\nDashboard\nSales\nSecurity verification\nNo sales yet"),
    ],
)
def test_run_does_not_write_zero_for_unverified_sales_page(
    tmp_path, monkeypatch, sales_url, sales_text,
):

    class FakeResponse:
        status = 200

    class FakePage:
        url = "about:blank"
        body = ""

        def goto(self, url, **kwargs):
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
    monkeypatch.setattr(readback.ledger_mod, "latest_by_slug", lambda: {
        "hook-lab": {"title": "Hook Lab Win The First 3 Seconds", "status": "live", "sales_usd": 0.0},
    })
    summary = tmp_path / "promptbase-sales.json"
    monkeypatch.setattr(readback, "SUMMARY_PATH", summary)

    with pytest.raises(RuntimeError, match="promptbase_sales_readback_unverified"):
        readback.run("http://127.0.0.1:9222")

    assert not summary.exists()


def test_run_rejects_a_partial_prompts_dashboard_before_writing_sales(tmp_path, monkeypatch):
    class FakeResponse:
        status = 200

    class FakePage:
        url = "about:blank"
        body = ""

        def goto(self, url, **kwargs):
            self.url = url
            if url == readback.PROMPTS_URL:
                self.body = """PromptBase
Dashboard
Prompts
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
\\U0001f300 Claude
Approved
Unrelated Listing"""
            else:
                self.body = "Dashboard\nSales\nNo sales yet"
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
    monkeypatch.setattr(readback, "PROMPTS_READY_TIMEOUT_MS", 0, raising=False)
    monkeypatch.setattr(readback.ledger_mod, "latest_by_slug", lambda: {
        "hook-lab": {"title": "Hook Lab Win The First 3 Seconds", "status": "live"},
        "new-listing": {"title": "New Listing Not Loaded Yet", "status": "pending_review"},
    })
    summary = tmp_path / "promptbase-sales.json"
    monkeypatch.setattr(readback, "SUMMARY_PATH", summary)

    with pytest.raises(RuntimeError, match="promptbase_prompts_readback_incomplete"):
        readback.run("http://127.0.0.1:9222")

    assert not summary.exists()


def test_sales_only_readback_does_not_depend_on_prompts_page(tmp_path, monkeypatch):
    class FakeResponse:
        status = 200

    class FakePage:
        url = "about:blank"
        visited = []

        def goto(self, url, **_kwargs):
            self.visited.append(url)
            self.url = url
            return FakeResponse()

        def wait_for_timeout(self, _milliseconds):
            pass

        def inner_text(self, _selector):
            return "Dashboard\nSales\nNo sales yet"

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
    summary = tmp_path / "promptbase-sales.json"
    monkeypatch.setattr(readback, "SUMMARY_PATH", summary)

    result = readback.run_sales_only("http://127.0.0.1:9222")

    assert result["sales"] == {"sales_count": 0, "net_usd": 0.0, "by_item": {}}
    assert page.visited == [readback.SALES_URL]
    assert json.loads(summary.read_text())["sales_count"] == 0


def test_sales_summary_preserves_previous_file_when_serialization_fails(tmp_path, monkeypatch):
    summary = tmp_path / "promptbase-sales.json"
    previous = '{"observed_at":"previous","sales_count":1}\n'
    summary.write_text(previous, encoding="utf-8")
    monkeypatch.setattr(readback, "SUMMARY_PATH", summary)

    def fail_after_partial_write(_value, handle, **_kwargs):
        handle.write('{"partial":')
        raise OSError("simulated no space left")

    monkeypatch.setattr(readback.json, "dump", fail_after_partial_write)
    with pytest.raises(OSError, match="simulated no space left"):
        readback._write_sales_summary(
            {"sales_count": 2, "net_usd": 4.25, "by_item": {}},
            "2026-10-12T12:00:00Z",
        )

    assert summary.read_text(encoding="utf-8") == previous
    assert list(tmp_path.iterdir()) == [summary]


def test_new_sales_summary_has_owner_only_permissions(tmp_path, monkeypatch):
    summary = tmp_path / "promptbase-sales.json"
    monkeypatch.setattr(readback, "SUMMARY_PATH", summary)
    previous_umask = os.umask(0)
    try:
        readback._write_sales_summary(
            {"sales_count": 0, "net_usd": 0.0, "by_item": {}},
            "2026-10-12T12:00:00Z",
        )
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(summary.stat().st_mode) == 0o600


if __name__ == "__main__":
    unittest.main()
