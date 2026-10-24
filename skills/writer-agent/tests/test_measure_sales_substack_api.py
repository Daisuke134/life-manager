"""Substack renders 0 and null alike as "-" (bundle formatter: ``null==e || 0===e && !showZero``),
so a dashboard dash proves nothing.  The numbers come from the JSON the same dashboard renders."""
from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure-sales.py"
SPEC = importlib.util.spec_from_file_location("writer_measure_sales_substack_api", SCRIPT)
measure = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(measure)

HOME = "https://aniccabuddha.substack.com/publish/home"
EARNINGS = "https://aniccabuddha.substack.com/publish/stats/earnings"
DASH_HOME = "有料登録者\n-\n0から"
DASH_EARNINGS = "累計収益\n-\n支払いを受け取るようになると、収益がここに表示されます"
ZERO_API = {
    "summary": {"subscribers": 0, "subscribersLast30Days": 0, "totalEmail": 1},
    "payouts": {"currency": "usd", "payouts": [], "totalAmount": 0, "hasMore": False},
    "payout_totals": {"currency": "usd", "payouts": [], "totalEarnings": 0},
}


def metrics(home=DASH_HOME, earnings=DASH_EARNINGS, api=None):
    payload = {"home_url": HOME, "home_body": home, "earnings_url": EARNINGS, "earnings_body": earnings}
    if api is not None:
        payload["api"] = api
    return {name: (value, ok, reason) for name, value, ok, reason, _url in measure.parse_substack_metrics(payload)}


def test_dash_with_explicit_zero_dashboard_json_is_a_measured_zero():
    result = metrics(api=ZERO_API)
    assert result["paid_subscribers"] == (0, True, None)
    assert result["revenue"] == (0.0, True, None)
    assert result["mrr"] == (0.0, True, None)  # no paid subscriber -> no recurring revenue


def test_lifetime_earnings_is_the_dashboard_sum_in_minor_units():
    api = json.loads(json.dumps(ZERO_API))
    api["payouts"]["totalAmount"] = 1234
    api["payout_totals"]["totalEarnings"] = 66
    result = metrics(earnings="累計収益\n$13.00\n", api=api)
    assert result["revenue"] == (13.0, True, None)


def test_dash_without_dashboard_json_stays_unknown():
    result = metrics()
    assert all(ok is False and value is None for value, ok, _ in result.values())


def test_missing_dashboard_cards_keep_json_values_unknown():
    # Review 2026-10-18: a relabelled or moved card must not let the unproven JSON field
    # become a measured money value on its own.
    api = json.loads(json.dumps(ZERO_API))
    api["summary"]["subscribers"] = 7
    result = metrics(home="no paid card here", earnings="no earnings card here", api=api)
    assert result["paid_subscribers"][:2] == (None, False)
    assert result["revenue"][:2] == (None, False)
    assert result["mrr"][:2] == (None, False)


def test_dash_contradicting_a_positive_json_count_stays_unknown():
    api = json.loads(json.dumps(ZERO_API))
    api["summary"]["subscribers"] = 3
    api["payouts"]["totalAmount"] = 500
    result = metrics(api=api)
    assert result["paid_subscribers"][:2] == (None, False)
    assert result["revenue"][:2] == (None, False)
    assert result["mrr"][:2] == (None, False)


def test_non_usd_or_failed_payout_reads_stay_unknown():
    api = json.loads(json.dumps(ZERO_API))
    api["payout_totals"] = {"error": "HTTP 500"}
    assert metrics(api=api)["revenue"][:2] == (None, False)
    api = json.loads(json.dumps(ZERO_API))
    api["payouts"]["currency"] = api["payout_totals"]["currency"] = "eur"
    assert metrics(api=api)["revenue"][:2] == (None, False)


def test_driver_reads_the_dashboard_json_inside_the_leased_page(monkeypatch):
    captured = {}

    def fake(script: str, timeout: int = 90, **kwargs):
        captured["script"] = script
        payload = {"home_url": HOME, "home_body": DASH_HOME, "earnings_url": EARNINGS,
                   "earnings_body": DASH_EARNINGS, "api": ZERO_API}
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        return subprocess.CompletedProcess([], 0, stdout=f"PAYLOAD_B64:{encoded}\n", stderr="")

    monkeypatch.setenv("SUBSTACK_PUBLICATION_JA", "aniccabuddha.substack.com")
    monkeypatch.setattr(measure, "run_browser_script", fake)
    assert measure.measure_substack_pages()["payload"]["api"] == ZERO_API
    for path in ("/api/v1/publish-dashboard/summary", "/api/v1/user_pub_stats/payouts?pubId=",
                 "/api/v1/payouts?currency="):
        assert path in captured["script"]
    assert 'credentials: "same-origin"' in captured["script"]


def test_renamed_paid_subscriber_card_is_still_measured():
    # 2026-10-24 Substack renamed the home card 有料登録者 -> 有料購読者; every reading went unknown.
    result = metrics(home="収益（年率換算）\n-\n$0から\n有料購読者\n-\n0から\n購読者数 合計\n1", api=ZERO_API)
    assert result["paid_subscribers"] == (0, True, None)
    assert result["mrr"] == (0.0, True, None)
