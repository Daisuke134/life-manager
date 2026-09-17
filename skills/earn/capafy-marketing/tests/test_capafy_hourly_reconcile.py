from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "capafy_hourly_reconcile.py"


def load_module():
    spec = importlib.util.spec_from_file_location("capafy_hourly_reconcile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def live_payloads() -> dict:
    return {
        "account": {"code": 0, "data": {"email": "owner@example.com"}},
        "inventory": {
            "code": 0,
            "data": {
                "list": [
                    {"agentId": "a1", "agentStatus": "online"},
                    {"agentId": "a2", "agentStatus": "draft"},
                    {"agentId": "a3", "agentStatus": "under_review"},
                    {"agentId": "a4", "agentStatus": "review_rejected"},
                ]
            },
        },
        "sales": {
            "code": 0,
            "data": {
                "data": [
                    {
                        "date": "2026-08-22",
                        "orders": 2,
                        "revenue": 19.98,
                        "netRevenue": 17.98,
                        "refundCount": 1,
                        "refundAmount": 2.00,
                    }
                ]
            },
        },
        "payout": {
            "code": 0,
            "data": {"balancePayout": 8, "totalPayout": 0, "balancePending": 3,
                     "balanceConfirmed": 4},
        },
        "refunds": {"code": 0, "data": {"list": [{"refundId": "r-1"}]}},
        "seller_sales": {"code": 0, "data": {"totalRevenue": 9.99, "data": [{"orders": 1, "refundAmount": 0}]}},
        "creator_earnings": {"code": 0, "data": {"totalRevenue": 8.0, "data": []}},
        "earnings_ranking": {"code": 0, "data": {"agents": [{
            "agentId": "6839055303", "skus": [{"skuType": "buyout", "revenue": 8.0}],
        }]}},
        "unit_sales": {"code": 0, "data": {"totalSalesVolume": 2, "totalFreeTrialCount": 1, "data": []}},
        "seller_ranking": {"code": 0, "data": {"agents": [{
            "agentId": "6839055303",
            "agentTitle": "Academic Humanizer — Human Voice, No AI Tells",
            "totalSalesAmount": 9.99,
            "previousSalesAmount": 0.0,
            "changePercent": 0.0,
            "skuCount": 1,
            "skus": [{"skuName": "Per Download", "skuType": "buyout", "salesAmount": 9.99,
                      "previousSalesAmount": 0.0, "changePercent": 0.0}],
        }]}},
        "statements": {"code": 0, "data": {"list": [{"settlementMonth": "2026-07", "endingSettlementBalance": 8, "payableAmount": 0}]}},
        "usage_requests": {"rows": [{"requestId": "r1", "agentId": "6839055303",
                                      "agentTitle": "Academic Humanizer", "inputUncached": 100,
                                      "cacheRead": 0, "cacheWrite": 0, "output": 20}]},
        "agent_models": {"6839055303": "anthropic/claude-sonnet-4.6"},
        "model_prices": {"anthropic/claude-sonnet-4.6": {
            "prompt": "0.000003", "completion": "0.000015"}},
        "openrouter_usage": {"data": {"usage_monthly": 2.5}},
    }


def test_receipt_separates_money_and_keeps_unobservable_mrr_unknown() -> None:
    module = load_module()
    receipt = module.build_receipt(live_payloads(), "2026-08-22T10:00:00Z")

    assert receipt["verdict"] == "success"
    assert receipt["money"] == {
        "gross_usd": "9.99",
        "creator_earnings_usd": "8.00",
        "unit_sales_total": 2,
        "free_trial_units": 1,
        "non_trial_units": 1,
        "observed_subscription_earnings_usd": "0.00",
        "balance_pending_usd": "3.00",
        "balance_confirmed_usd": "4.00",
        "balance_payout_usd": "8.00",
        "paid_out_usd": "0.00",
        "one_time_revenue_usd": "9.99",
        "pending_usd": "8.00",
        "realized_usd": "0.00",
        "refunds_usd": "0.00",
        "settled_mrr_usd": None,
        "net_mrr_usd": None,
        "statement_ending_balance_usd": "8.00",
        "statement_payable_usd": "0.00",
    }
    assert receipt["money_status"]["one_time_revenue_usd"] == "fresh_official_seller_console"
    assert receipt["money_status"]["settled_mrr_usd"] == "unknown_active_subscription_status"
    assert receipt["seller_winner"] == {
        "agent_id": "6839055303",
        "name": "Academic Humanizer — Human Voice, No AI Tells",
        "sales_usd": "9.99",
        "sku_type": "buyout",
        "revenue_kind": "one_time",
        "source": "official_publisher_console",
    }
    assert receipt["refunds"]["tickets"] == 1
    assert receipt["sources"]["sales"]["freshness"] == "fresh"


def test_failed_source_is_unknown_not_zero_and_receipt_is_degraded() -> None:
    module = load_module()
    payloads = live_payloads()
    payloads["payout"] = {"_error": "HTTP 503"}
    payloads["sales"] = {"_error": "timeout"}

    receipt = module.build_receipt(payloads, "2026-08-22T10:00:00Z")

    assert receipt["verdict"] == "degraded"
    assert receipt["money"]["gross_usd"] == "9.99"
    assert receipt["money"]["pending_usd"] is None
    assert receipt["money"]["realized_usd"] is None
    assert receipt["money"]["settled_mrr_usd"] is None
    assert receipt["sources"]["sales"]["freshness"] == "unknown"
    assert receipt["sources"]["payout"]["freshness"] == "unknown"


def test_inventory_shape_is_observed_without_claiming_normalized_slots() -> None:
    module = load_module()
    payloads = live_payloads()
    payloads["inventory"] = {"code": 0, "data": {"unexpected": [1, 2, 3]}}

    receipt = module.build_receipt(payloads, "2026-08-22T10:00:00Z")

    assert receipt["inventory"]["status"] == "unknown_unrecognized_shape"
    assert receipt["inventory"]["occupied"] is None
    assert receipt["inventory"]["free"] is None
    assert receipt["sources"]["inventory"]["freshness"] == "fresh"
    assert receipt["verdict"] == "degraded"


def test_inventory_normalizes_five_slot_lifecycle() -> None:
    module = load_module()

    receipt = module.build_receipt(live_payloads(), "2026-08-22T10:00:00Z")

    assert receipt["inventory"] == {
        "status": "normalized",
        "observed_agents": 4,
        "listed": 1,
        "occupied": 2,
        "free": 3,
        "retry": 1,
        "blocked": 0,
    }


def test_cli_fixture_run_writes_atomic_receipt(tmp_path: Path) -> None:
    module = load_module()
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    for name, payload in live_payloads().items():
        (fixture_dir / f"{name}.json").write_text(json.dumps(payload))
    output = tmp_path / "state" / "receipt.json"

    rc = module.main(
        ["--fixture-dir", str(fixture_dir), "--output", str(output), "--observed-at", "2026-08-22T10:00:00Z"]
    )

    assert rc == 0
    assert json.loads(output.read_text())["observed_at"] == "2026-08-22T10:00:00Z"
    assert not output.with_suffix(".json.tmp").exists()


def test_money_mode_is_read_only_and_keeps_subscription_mrr_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_module()
    payloads = live_payloads()
    payloads["seller_ranking"]["data"]["agents"][0]["skus"] = [
        {"skuName": "Weekly Subscription", "skuType": "subscription_week", "salesAmount": 9.99}
    ]
    payloads["earnings_ranking"]["data"]["agents"][0]["skus"] = [
        {"skuType": "subscription_week", "revenue": 8.0}
    ]
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    for name, payload in payloads.items():
        (fixture_dir / f"{name}.json").write_text(json.dumps(payload))
    output = tmp_path / "must-not-write.json"

    rc = module.main([
        "--money", "--json", "--fixture-dir", str(fixture_dir),
        "--output", str(output), "--observed-at", "2026-09-17T00:00:00Z",
    ])

    shown = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert not output.exists()
    assert shown["gross_sales_usd"] == "9.99"
    assert shown["creator_earnings_usd"] == "8.00"
    assert shown["free_trial_units"] == 1
    assert shown["observed_subscription_earnings_usd"] == "8.00"
    assert shown["active_mrr_usd"] is None
    assert shown["active_mrr_status"] == "missing_seller_active_subscription_source"
    assert shown["usage"]["requests"] == 1
    assert shown["usage"]["estimated_model_cost_usd"] == "0.00"
    assert shown["openrouter_host_key_calendar_month_usage_usd"] == "2.50"


def test_live_seller_reads_use_current_clickhouse_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    observed = module.dt.datetime(2026, 9, 17, tzinfo=module.dt.timezone.utc)
    calls = []
    monkeypatch.setattr(module, "_token", lambda _root: "seller-token")
    monkeypatch.setattr(module, "_web_token", lambda: "web-token")
    monkeypatch.setattr(module, "_get", lambda path, _token: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_post", lambda path, _token, body: calls.append((path, body)) or {"code": 0, "data": {}})

    module._live_payloads(Path("/tmp"), observed)

    assert {path for path, _ in calls} == {
        "/app/sales/clickhouse/trend",
        "/app/sales/clickhouse/ranking",
        "/app/realtime-revenue/clickhouse/trend",
        "/app/realtime-revenue/clickhouse/comparison",
        "/app/unit-sales/clickhouse/trend",
    }
    assert all(body.get("sinceLaunch") is True for _, body in calls)


def test_usage_requests_follow_cursor_without_duplicate_count(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    bodies = []
    def fake_post(_path, _token, body):
        bodies.append(body)
        if len(bodies) == 1:
            return {"code": 0, "data": {"total": 2, "items": [
                {"requestId": "a", "agentId": "one"}], "hasMore": True,
                "nextCursorTime": 123, "nextCursorRequestId": "a"}}
        return {"code": 0, "data": {"total": 2, "items": [
            {"requestId": "b", "agentId": "one"}], "hasMore": False}}
    monkeypatch.setattr(module, "_post", fake_post)

    result = module._usage_requests("web", "2026-09-01", "2026-09-16")

    assert result["total"] == 2
    assert bodies[1]["cursorTime"] == 123
    assert bodies[1]["cursorRequestId"] == "a"
