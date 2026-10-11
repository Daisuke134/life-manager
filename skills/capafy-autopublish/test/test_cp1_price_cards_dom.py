"""PRICE_CARDS_JS against a minimal plan-card DOM (2026-10-11).

The Daily plan card on Capafy's 価格設定 tab has no 無料トライアル section, so the old
anchor (dropdown button AND trial text) skipped it and `prices` reported
`PRICES_MISMATCH day: missing` even though the agent had set day $1.99/10. That blocked
CP1 for the Hook Lab, TikTok Script Pro and YouTube Script Writer price restores.
"""
import importlib.util
import os
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("cp1_agent_dom_under_test", SCRIPTS / "cp1_agent.py")
cp1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cp1)

CARD = """<div class="card"><div class="head"><button class="pricingConfigDropdownButton">{period}</button></div>
<div class="body"><input value="{price}"><input value="{cap}"></div>{trial}</div>"""
TRIAL = '<div class="trial">無料トライアル<span>Enable Free Trial</span></div>'
HTML = "<div id='plans'>" + "".join([
    CARD.format(period="Daily", price="1.99", cap="10", trial=""),
    CARD.format(period="Weekly", price="4.99", cap="30", trial=TRIAL),
    CARD.format(period="Monthly", price="9.99", cap="50", trial=TRIAL),
]) + "</div>"


def _cards():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=os.environ.get("CP1_TEST_CHROMIUM") or None)
        except Exception as exc:  # no bundled browser on this host
            pytest.skip(f"chromium unavailable: {exc}")
        page = browser.new_page()
        page.evaluate("(h) => { document.body.innerHTML = h; }", HTML)
        cards = page.evaluate(cp1.PRICE_CARDS_JS)
        browser.close()
        return cards


def test_daily_card_without_trial_section_is_read():
    by_period = {c["period"]: c for c in _cards()}
    assert set(by_period) == {"Daily", "Weekly", "Monthly"}
    assert (by_period["Daily"]["price"], by_period["Daily"]["cap"], by_period["Daily"]["trial"]) == ("1.99", "10", None)
    assert (by_period["Weekly"]["price"], by_period["Weekly"]["cap"]) == ("4.99", "30")
