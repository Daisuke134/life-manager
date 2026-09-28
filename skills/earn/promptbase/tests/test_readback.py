#!/usr/bin/env python3
"""Tests for the pure dashboard-text parser in readback.py (no browser)."""
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
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


if __name__ == "__main__":
    unittest.main()
