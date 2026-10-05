"""Regression coverage for CP1's `prices` command: the read-only gate that catches
a saved plan card before it is confirmed (no edit URL exists after confirmation).

Measured 2026-10-05 on YouTube Script Writer (agent 7686597754): CP1 switched plan
cards to week/month/year and saved month price=$9.99 (target $19.99) and year
cap=8640 (target 720) -- verify_pricing.py (run right before CP3, card already
confirmed) could only warn. These tests cover the PURE comparison logic
(compare_price_cards / prices_result) with no browser involved, per CP1_AGENTIC.md's
requirement that the DOM read and the comparison stay separately testable.
"""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("cp1_agent_prices_under_test", SCRIPTS / "cp1_agent.py")
cp1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cp1)

SPEC_VP = importlib.util.spec_from_file_location("verify_pricing_under_test", SCRIPTS / "verify_pricing.py")
verify_pricing = importlib.util.module_from_spec(SPEC_VP)
sys.modules["verify_pricing"] = verify_pricing
SPEC_VP.loader.exec_module(verify_pricing)


def _card(period, price, cap, trial=None):
    return {"period": period, "price": price, "cap": cap, "trial": trial}


def _plan(cycle, price, cap, trial=None):
    return {"cycle": cycle, "price": price, "cap": str(cap), "trial": trial}


def test_matching_cards_report_no_mismatches():
    plans = [
        _plan("week", "9.99", 30),
        _plan("month", "19.99", 80),
        _plan("year", "99.99", 720),
    ]
    cards = [
        _card("Weekly", "9.99", "30"),
        _card("Monthly", "19.99", "80"),
        _card("Yearly", "99.99", "720"),
    ]
    assert cp1.compare_price_cards(plans, cards) == []


def test_youtube_script_writer_mismatch_names_month_price_and_year_cap():
    # Exact measured case (2026-10-05, agent 7686597754): month price saved
    # as 9.99 instead of 19.99, year cap saved as 8640 instead of 720.
    plans = [
        _plan("week", "9.99", 30),
        _plan("month", "19.99", 80),
        _plan("year", "99.99", 720),
    ]
    cards = [
        _card("Weekly", "9.99", "30"),
        _card("Monthly", "9.99", "80"),
        _card("Yearly", "99.99", "8640"),
    ]
    mismatches = cp1.compare_price_cards(plans, cards)
    assert "month: price target=$19.99 actual=9.99" in mismatches
    assert "year: cap target=720 actual=8640" in mismatches
    assert len(mismatches) == 2


def test_resorted_card_order_still_matches_by_period_label_not_position():
    # Capafy re-sorts plan cards when a period changes (CP1_AGENTIC.md). A caller
    # that matched by list position instead of Period label would compare the
    # wrong plan to the wrong card here (cards are listed year, week, month --
    # the opposite of plans' week, month, year order -- yet every value matches).
    plans = [
        _plan("week", "9.99", 30),
        _plan("month", "19.99", 80),
        _plan("year", "99.99", 720),
    ]
    cards = [
        _card("Yearly", "99.99", "720"),
        _card("Weekly", "9.99", "30"),
        _card("Monthly", "19.99", "80"),
    ]
    assert cp1.compare_price_cards(plans, cards) == []


def test_missing_card_for_a_listing_cycle_is_reported():
    plans = [_plan("year", "99.99", 720)]
    cards = [_card("Weekly", "9.99", "30")]
    mismatches = cp1.compare_price_cards(plans, cards)
    assert mismatches == ["year: missing (target price=$99.99)"]


def test_trial_mismatch_enabled_card_target_no_trial():
    plans = [_plan("week", "9.99", 30, trial=None)]
    cards = [_card("Weekly", "9.99", "30", trial={"hours": "24", "requests": "5"})]
    mismatches = cp1.compare_price_cards(plans, cards)
    assert len(mismatches) == 1
    assert mismatches[0].startswith("week: trial target=None")


def test_trial_matches_when_hours_and_requests_agree():
    plans = [_plan("week", "9.99", 30, trial={"hours": 24, "requests": 5})]
    cards = [_card("Weekly", "9.99", "30", trial={"hours": "24", "requests": "5"})]
    assert cp1.compare_price_cards(plans, cards) == []


def test_prices_result_match_message_and_exit_code():
    plans = [_plan("week", "9.99", 30)]
    cards = [_card("Weekly", "9.99", "30")]
    message, code = cp1.prices_result(plans, cards)
    assert message == "PRICES_MATCH 1"
    assert code == 0


def test_prices_result_mismatch_message_and_exit_code():
    plans = [_plan("month", "19.99", 80)]
    cards = [_card("Monthly", "9.99", "80")]
    message, code = cp1.prices_result(plans, cards)
    assert message == "PRICES_MISMATCH month: price target=$19.99 actual=9.99"
    assert code == 1


def test_prices_result_download_listing_is_unknown_not_mismatch():
    message, code = cp1.prices_result(None, [])
    assert message == "PRICES_UNKNOWN listing-has-no-subscription-plans"
    assert code == 0


def test_price_cards_js_anchors_on_period_dropdown_and_trial_text():
    # Guards the DOM-extraction JS against silent drift: the per-card anchor and
    # input ordering are load-bearing (see scripts/drive_cp1.py GOTCHA 12).
    assert "pricingConfigDropdownButton" in cp1.PRICE_CARDS_JS
    assert "無料トライアル" in cp1.PRICE_CARDS_JS


def test_real_listing_plans_feed_into_compare_price_cards(tmp_path):
    listing = tmp_path / "LISTING.md"
    listing.write_text(
        "Primary Model: DeepSeek V4.1 Flash · category: マーケティング · tags: a\n\n"
        "## Pricing\n"
        "| cycle | price | cap | trial |\n"
        "|---|---|---|---|\n"
        "| week | $9.99 | 30 | No Free Trial |\n"
        "| month | $19.99 | 80 | No Free Trial |\n"
        "| year | $99.99 | 720 | No Free Trial |\n",
        encoding="utf-8",
    )
    plans = verify_pricing.listing_plans(str(listing))
    cards = [
        _card("Weekly", "9.99", "30"),
        _card("Monthly", "9.99", "80"),
        _card("Yearly", "99.99", "8640"),
    ]
    mismatches = cp1.compare_price_cards(plans, cards)
    assert "month: price target=$19.99 actual=9.99" in mismatches
    assert "year: cap target=720 actual=8640" in mismatches
