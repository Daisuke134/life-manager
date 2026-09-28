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


def test_cli_fixture_run_also_writes_skill_analytics_next_to_receipt(tmp_path: Path) -> None:
    module = load_module()
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    payloads = live_payloads()
    for name, payload in payloads.items():
        (fixture_dir / f"{name}.json").write_text(json.dumps(payload))
    output = tmp_path / "state" / "capafy-hourly-reconcile.json"

    rc = module.main(
        ["--fixture-dir", str(fixture_dir), "--output", str(output), "--observed-at", "2026-08-22T10:00:00Z"]
    )

    assert rc == 0
    analytics_path = output.parent / "capafy-skill-analytics.json"
    assert analytics_path.exists()
    analytics = json.loads(analytics_path.read_text())
    assert analytics["kind"] == "capafy_skill_analytics"
    assert analytics["observed_at"] == "2026-08-22T10:00:00Z"


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
    assert not (output.parent / "capafy-skill-analytics.json").exists()
    assert shown["gross_sales_usd"] == "9.99"
    assert shown["window_start"] == "2026-09-01"
    assert shown["window_kind"] == "calendar_month_to_date_utc"
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
    monkeypatch.setattr(module, "_usage_requests", lambda *_args: {"rows": []})
    monkeypatch.setattr(module, "_openrouter_data", lambda *_args: {})

    module._live_payloads(Path("/tmp"), observed)

    assert {path for path, _ in calls} == {
        "/app/sales/clickhouse/trend",
        "/app/sales/clickhouse/ranking",
        "/app/realtime-revenue/clickhouse/trend",
        "/app/realtime-revenue/clickhouse/comparison",
        "/app/unit-sales/clickhouse/trend",
        "/app/unit-sales/clickhouse/ranking",
    }
    # The since-launch period calls (one per endpoint above, minus the two fixed 30d/7d
    # ranking calls added below) all carry sinceLaunch=True.
    since_launch_calls = [body for _, body in calls if "sinceLaunch" in body]
    assert len(since_launch_calls) == 5
    assert all(body.get("sinceLaunch") is True for body in since_launch_calls)
    # Fixed 30d/7d windows for per-agent GROSS revenue and paid-order rankings.
    windowed_calls = [(path, body) for path, body in calls if "startDate" in body]
    assert {path for path, _ in windowed_calls} == {
        "/app/sales/clickhouse/ranking", "/app/unit-sales/clickhouse/ranking",
    }
    assert len(windowed_calls) == 4
    windows = {(body["startDate"], body["endDate"]) for _, body in windowed_calls}
    assert windows == {("2026-08-19", "2026-09-17"), ("2026-09-11", "2026-09-17")}


def test_monthly_money_reads_use_calendar_month_start(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    observed = module.dt.datetime(2026, 9, 17, tzinfo=module.dt.timezone.utc)
    calls = []
    monkeypatch.setattr(module, "_token", lambda _root: "seller-token")
    monkeypatch.setattr(module, "_web_token", lambda: "web-token")
    monkeypatch.setattr(module, "_get", lambda path, _token: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_post", lambda path, _token, body: calls.append(body) or {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_usage_requests", lambda *_args: {"rows": []})
    monkeypatch.setattr(module, "_openrouter_data", lambda *_args: {})

    module._live_payloads(Path("/tmp"), observed, seller_start_date=observed.date().replace(day=1))

    # Month-to-date calls (sinceLaunch replaced with an explicit month start).
    month_to_date_calls = [body for body in calls if body.get("startDate") == "2026-09-01"]
    assert len(month_to_date_calls) == 5
    assert all(body.get("endDate") == "2026-09-17" for body in month_to_date_calls)
    # The fixed 30d/7d gross-window ranking calls are independent of the month-to-date period.
    assert all(body.get("endDate") == "2026-09-17" for body in calls)


def skill_analytics_payloads() -> dict:
    return {
        "account": {"code": 0, "data": {"email": "owner@example.com"}},
        "inventory": {"code": 0, "data": {"list": [
            # Real /agent/agents list items key the display name "name", not "agentTitle"
            # (that key only appears in the ranking/earnings payloads below).
            {"agentId": "111", "name": "Hook Lab", "agentStatus": "online",
             "agentRuntime": "openclaw", "rating": 0, "reviewCount": 0},
            {"agentId": "222", "name": "Zero Sales Skill", "agentStatus": "online",
             "agentRuntime": "claude", "rating": 0, "reviewCount": 0},
        ]}},
        "seller_sales": {"code": 0, "data": {"totalRevenue": 34.88, "data": [
            {"date": "2026-06-25", "orders": 1, "revenue": 19.9, "refundAmount": 0.0},
            {"date": "2026-09-20", "orders": 1, "revenue": 9.99, "refundAmount": 0.0},
            {"date": "2026-09-26", "orders": 1, "revenue": 4.99, "refundAmount": 0.0},
        ]}},
        "seller_ranking": {"code": 0, "data": {"agents": [
            {"agentId": "111", "agentTitle": "Hook Lab", "totalSalesAmount": 34.88,
             "skus": [{"skuName": "Daily Subscription", "skuType": "subscription_day",
                       "salesAmount": 19.9, "previousSalesAmount": 0.0, "changePercent": 0.0},
                      {"skuName": "Weekly Subscription", "skuType": "subscription_week",
                       "salesAmount": 4.99, "previousSalesAmount": 0.0, "changePercent": 0.0}]},
        ]}},
        "earnings_ranking": {"code": 0, "data": {"agents": [
            {"agentId": "111", "skus": [{"skuType": "subscription_day", "revenue": 15.4},
                                        {"skuType": "subscription_week", "revenue": 3.6}]},
        ]}},
        "unit_sales": {"code": 0, "data": {"totalSalesVolume": 3, "totalFreeTrialCount": 1, "data": []}},
        "payout": {"code": 0, "data": {"balancePending": 15.4, "balanceConfirmed": 35.36,
                                       "balancePayout": 14.4, "totalPayout": 0.0,
                                       "payoutMethod": "wire_transfer", "accountNumberMasked": "****1900"}},
        "refunds": {"code": 0, "data": {"list": []}},
        "statements": {"code": 0, "data": {"list": [
            {"settlementMonth": "2026-08", "endingSettlementBalance": 14.4, "payableAmount": 0.0}]}},
        # Windowed per-agent GROSS rankings: this is what actually reconciles against real sales.
        # 222 is absent from all four (a real zero, not a source failure).
        "seller_ranking_30d": {"code": 0, "data": {"agents": [
            {"agentId": "111", "agentTitle": "Hook Lab", "totalSalesAmount": 24.89},
        ]}},
        "seller_ranking_7d": {"code": 0, "data": {"agents": [
            {"agentId": "111", "agentTitle": "Hook Lab", "totalSalesAmount": 5.98},
        ]}},
        "unit_ranking_30d": {"code": 0, "data": {"agents": [
            {"agentId": "111", "agentTitle": "Hook Lab", "totalSalesVolume": 61, "freeTrialCount": 50},
        ]}},
        "unit_ranking_7d": {"code": 0, "data": {"agents": [
            {"agentId": "111", "agentTitle": "Hook Lab", "totalSalesVolume": 12, "freeTrialCount": 9},
        ]}},
    }


def skill_agent_stats() -> dict:
    # Real GET /agent/agent/{agentId}/stats shape: a flat object with sales/revenue/daily,
    # not a nested "data" list.
    return {
        "111": {
            "d30": {"code": 0, "data": {"agentId": "111", "sales": 2, "revenue": 6.4, "daily": []}},
            "d7": {"code": 0, "data": {"agentId": "111", "sales": 0, "revenue": 0.0, "daily": []}},
            "detail": {"code": 0, "data": {"agentId": "111", "model": "Claude Sonnet 4.6 (detail)"}},
        },
        "222": {
            "d30": {"code": 0, "data": {"agentId": "222", "sales": 0, "revenue": 0.0, "daily": []}},
            "d7": {"code": 0, "data": {"agentId": "222", "sales": 0, "revenue": 0.0, "daily": []}},
            "detail": {"_error": "HTTP 503"},
        },
    }


def test_build_skill_analytics_account_totals_and_per_skill_rows() -> None:
    module = load_module()
    analytics = module.build_skill_analytics(
        skill_analytics_payloads(), skill_agent_stats(), {"111": "Claude Sonnet 4.6"},
        "2026-09-27T00:00:00Z",
    )

    assert analytics["kind"] == "capafy_skill_analytics"
    assert analytics["account_totals"]["all_time"]["gross_usd"] == "34.88"
    assert analytics["account_totals"]["all_time"]["units"] == 3
    assert analytics["account_totals"]["all_time"]["trials"] == 1
    assert analytics["account_totals"]["last_30d"]["gross_usd"] == "14.98"
    assert analytics["account_totals"]["last_30d"]["orders"] == 2
    assert analytics["account_totals"]["last_7d"]["gross_usd"] == "4.99"
    assert analytics["balances"]["balance_payout_usd"] == "14.40"
    assert analytics["balances"]["payout_method"] == "wire_transfer"

    rows = {row["agent_id"]: row for row in analytics["per_skill_rows"]}
    assert rows["111"]["name"] == "Hook Lab"
    assert rows["222"]["name"] == "Zero Sales Skill"
    assert rows["111"]["model"] == "Claude Sonnet 4.6"
    assert rows["111"]["since_launch_gross_usd"] == "34.88"
    assert rows["111"]["since_launch_creator_earnings_usd"] == "19.00"
    # GROSS 30d/7d (per-agent clickhouse ranking window): reflects actual sales.
    assert rows["111"]["stats_30d_revenue_usd"] == "24.89"
    assert rows["111"]["stats_30d_orders"] == 11  # 61 total - 50 free trial
    assert rows["111"]["stats_7d_revenue_usd"] == "5.98"
    assert rows["111"]["stats_7d_orders"] == 3  # 12 total - 9 free trial
    # SETTLED 30d/7d (/agent/agent/{id}/stats): kept as a separate, known-lagging figure.
    assert rows["111"]["stats_30d_settled_orders"] == 2
    assert rows["111"]["stats_30d_settled_revenue_usd"] == "6.40"
    assert rows["222"]["model"] == "claude"
    assert rows["222"]["since_launch_gross_usd"] == "0.00"
    # 222 is absent from the windowed rankings: a real zero, not unavailable.
    assert rows["222"]["stats_30d_revenue_usd"] == "0.00"
    assert rows["222"]["stats_30d_orders"] == 0

    assert analytics["rankings"]["top_by_earnings"][0]["agent_id"] == "111"
    assert analytics["rankings"]["top_by_units_30d"][0] == {
        "agent_id": "111", "name": "Hook Lab", "orders_30d": 11,
    }
    zero_sales_ids = {row["agent_id"] for row in analytics["rankings"]["zero_sales"]}
    assert zero_sales_ids == {"222"}

    assert [row["date"] for row in analytics["daily_revenue_trend_last_30d"]] == [
        "2026-09-20", "2026-09-26"]

    assert analytics["subscription_proxy"]["label"] == "proxy_not_mrr"
    assert "not" in analytics["subscription_proxy"]["note"].lower()
    # Gross, not the lagging settled figure (6.40) that used to make this proxy read near-zero.
    assert analytics["subscription_proxy"]["last_30d_net_usd"] == "24.89"

    assert any("active" in gap.lower() and "subscription" in gap.lower() for gap in analytics["data_gaps"])
    assert isinstance(analytics["telegram_summary"], str) and "34.88" in analytics["telegram_summary"]
    assert analytics["verdict"] == "success"


def test_gross_window_fails_closed_to_none_when_its_ranking_source_fails() -> None:
    """A failed windowed-ranking source must not be confused with a real zero-sales skill."""
    module = load_module()
    payloads = skill_analytics_payloads()
    payloads["seller_ranking_30d"] = {"_error": "HTTP 503"}
    payloads["unit_ranking_7d"] = {"_error": "HTTP 503"}

    analytics = module.build_skill_analytics(
        payloads, skill_agent_stats(), {"111": "Claude Sonnet 4.6"}, "2026-09-27T00:00:00Z",
    )

    rows = {row["agent_id"]: row for row in analytics["per_skill_rows"]}
    assert rows["111"]["stats_30d_revenue_usd"] is None  # its source (seller_ranking_30d) failed
    assert rows["111"]["stats_7d_orders"] is None  # its source (unit_ranking_7d) failed
    # Windows whose own source is still healthy are unaffected by the other two failing.
    assert rows["111"]["stats_30d_orders"] == 11
    assert rows["111"]["stats_7d_revenue_usd"] == "5.98"
    assert rows["111"]["stats_30d_settled_revenue_usd"] == "6.40"
    # top_by_units_30d still ranks by the healthy stats_30d_orders field.
    assert analytics["rankings"]["top_by_units_30d"][0]["agent_id"] == "111"


def test_build_skill_analytics_isolates_stale_section_on_source_failure() -> None:
    module = load_module()
    payloads = skill_analytics_payloads()
    payloads["payout"] = {"_error": "HTTP 503"}

    analytics = module.build_skill_analytics(
        payloads, skill_agent_stats(), {}, "2026-09-27T00:00:00Z",
    )

    assert analytics["balances"]["_status"] == "stale"
    assert analytics["balances"]["balance_payout_usd"] is None
    assert analytics["verdict"] == "degraded"
    # Other sections still compute despite the payout failure.
    assert analytics["account_totals"]["_status"] == "fresh"
    assert len(analytics["per_skill_rows"]) == 2


def test_build_skill_analytics_isolates_stale_per_skill_rows_on_inventory_failure() -> None:
    module = load_module()
    payloads = skill_analytics_payloads()
    payloads["inventory"] = {"_error": "timeout"}

    analytics = module.build_skill_analytics(
        payloads, {}, {}, "2026-09-27T00:00:00Z",
    )

    assert analytics["per_skill_rows"] == []
    assert analytics["per_skill_rows_status"] == "stale"
    assert analytics["account_totals"]["_status"] == "fresh"
    assert analytics["verdict"] == "degraded"


def test_catalog_models_reads_primary_model_and_agent_id_from_listing(tmp_path: Path) -> None:
    module = load_module()
    catalog = tmp_path / "skills" / "capafy" / "catalog" / "youtube-script-writer"
    catalog.mkdir(parents=True)
    (catalog / "LISTING.md").write_text(
        "Primary Model: Claude Sonnet 4.6 · category: マーケティング · tags: x\n\n"
        "demand evidence    : This is the existing Capafy Agent `7686597754`; revision.\n"
    )

    models = module._catalog_models(tmp_path)

    assert models == {"7686597754": "Claude Sonnet 4.6"}


def test_agent_stats_windows_bounded_sequential_with_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    calls: list[str] = []
    sleeps: list[float] = []
    monkeypatch.setattr(module, "_get", lambda path, _token: calls.append(path) or {"code": 0, "data": {}})

    result = module._fetch_agent_stats_windows(
        "tok", ["a", "b", "c"], module.dt.date(2026, 9, 27), cap=2, delay=0.01, sleep=sleeps.append,
    )

    assert list(result.keys()) == ["a", "b"]
    assert len(calls) == 6  # 2 agents x (d30, d7, detail)
    assert calls[2] == "/agent/agents/a"
    assert sleeps == [0.01] * 6


def test_stats_orders_revenue_reads_the_flat_sales_and_revenue_fields() -> None:
    module = load_module()
    assert module._stats_orders_revenue(
        {"code": 0, "data": {"sales": 3, "revenue": 12.5, "daily": []}},
    ) == (3, "12.50")
    assert module._stats_orders_revenue({"_error": "HTTP 503"}) == (None, None)
    assert module._stats_orders_revenue({"code": 0, "data": {}}) == (0, "0.00")


def test_agent_detail_model_reads_the_model_field_not_runtime() -> None:
    module = load_module()
    assert module._agent_detail_model(
        {"code": 0, "data": {"agentRuntime": "openclaw", "model": "Claude Sonnet 4.6"}},
    ) == "Claude Sonnet 4.6"
    assert module._agent_detail_model({"_error": "timeout"}) is None
    assert module._agent_detail_model({"code": 0, "data": {"model": None}}) is None


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


def test_normal_mode_fetches_usage_over_the_trailing_30_days_not_since_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cost visibility must not require --money: usage is fetched every normal run too,
    over the same fixed 30d window as stats_30d, independent of the sinceLaunch range."""
    module = load_module()
    observed = module.dt.datetime(2026, 9, 17, tzinfo=module.dt.timezone.utc)
    usage_calls = []
    monkeypatch.setattr(module, "_token", lambda _root: "seller-token")
    monkeypatch.setattr(module, "_web_token", lambda: "web-token")
    monkeypatch.setattr(module, "_get", lambda path, _token: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_post", lambda path, _token, body: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_usage_requests",
                        lambda _web_token, start, end: usage_calls.append((start, end)) or {"rows": []})
    monkeypatch.setattr(module, "_openrouter_data", lambda *_args: {})

    payloads = module._live_payloads(Path("/tmp"), observed)  # seller_start_date defaults to None

    assert usage_calls == [("2026-08-19", "2026-09-17")]
    assert payloads["usage_requests"] == {"rows": []}


def test_per_skill_profit_from_net_revenue_minus_estimated_cost() -> None:
    module = load_module()
    payloads = skill_analytics_payloads()
    payloads["usage_requests"] = {"rows": [{
        "requestId": "r1", "agentId": "111", "agentTitle": "Hook Lab",
        "inputUncached": 1_000_000, "cacheRead": 0, "cacheWrite": 0, "output": 0,
    }]}
    payloads["agent_models"] = {"111": "anthropic/claude-sonnet-4.6"}
    payloads["model_prices"] = {"anthropic/claude-sonnet-4.6": {"prompt": "0.00002", "completion": "0.000015"}}

    analytics = module.build_skill_analytics(
        payloads, skill_agent_stats(), {"111": "Claude Sonnet 4.6"}, "2026-09-27T00:00:00Z",
    )

    rows = {row["agent_id"]: row for row in analytics["per_skill_rows"]}
    # stats_30d_revenue_usd is "24.89"; net = 24.89 * 0.80 = 19.912 -> "19.91"; cost = "20.00".
    assert rows["111"]["cost_30d_usd"] == "20.00"
    assert rows["111"]["net_revenue_30d_usd"] == "19.91"
    assert rows["111"]["profit_30d_usd"] == "-0.09"
    # 222 has no usage rows: cost/net/profit stay unknown/null, never fabricated.
    assert rows["222"]["cost_30d_usd"] is None
    assert rows["222"]["profit_30d_usd"] is None

    assert "Hook Lab" in analytics["telegram_summary"]
    assert "profit $-0.09" in analytics["telegram_summary"]
    assert any("cost_30d_usd is an estimate" in gap for gap in analytics["data_gaps"])


def activity_fixture_rows() -> list[dict]:
    return [
        {"date": "2026-09-01", "model": "anthropic/claude-sonnet-4.6", "usage": 20.0,
         "requests": 400, "prompt_tokens": 1_000_000, "completion_tokens": 200_000},
        {"date": "2026-09-15", "model": "anthropic/claude-sonnet-4.6", "usage": 22.87,
         "requests": 417, "prompt_tokens": 1_100_000, "completion_tokens": 210_000},
        {"date": "2026-09-15", "model": "openai/gpt-4o-mini", "usage": 0.49,
         "requests": 30, "prompt_tokens": 50_000, "completion_tokens": 5_000},
    ]


def test_openrouter_actual_summarizes_activity_rows_by_model_and_day() -> None:
    module = load_module()

    actual = module._openrouter_actual({"data": activity_fixture_rows()})

    assert actual["status"] == "fresh"
    assert actual["total_usd"] == "43.36"
    assert actual["by_model"] == {"anthropic/claude-sonnet-4.6": "42.87", "openai/gpt-4o-mini": "0.49"}
    assert actual["by_day"] == {"2026-09-01": "20.00", "2026-09-15": "23.36"}
    assert actual["window_start"] == "2026-09-01"
    assert actual["window_end"] == "2026-09-15"


def test_openrouter_actual_reports_unavailable_reason_without_key_or_on_error() -> None:
    module = load_module()

    assert module._openrouter_actual({"_error": "key_unavailable"})["status"] == "unavailable:key_unavailable"
    assert module._openrouter_actual({"_error": "HTTPError: 403"})["status"] == "unavailable:HTTPError: 403"
    assert module._openrouter_actual({"code": 0, "data": "not-a-list"})["status"] == "unavailable:unrecognized_shape"


def test_allocate_actual_cost_splits_by_estimated_share_within_a_model() -> None:
    module = load_module()
    usage_agents = [
        {"agent_id": "111", "model": "anthropic/claude-sonnet-4.6", "estimated_model_cost_usd": "6.00"},
        {"agent_id": "222", "model": "anthropic/claude-sonnet-4.6", "estimated_model_cost_usd": "2.00"},
        {"agent_id": "333", "model": "openai/gpt-4o-mini", "estimated_model_cost_usd": None},
    ]
    openrouter_actual = {"status": "fresh", "by_model": {"anthropic/claude-sonnet-4.6": "40.00"}}

    result = module._allocate_actual_cost_by_agent(usage_agents, openrouter_actual)

    # 111 has 3x the estimated cost of 222 within the same model -> 3x the allocated actual spend.
    assert result["111"] == "30.00"
    assert result["222"] == "10.00"
    # No actual figure for gpt-4o-mini, and no estimate for 333: stays unknown, not fabricated.
    assert result["333"] is None


def test_allocate_actual_cost_empty_when_actual_unavailable() -> None:
    module = load_module()
    usage_agents = [{"agent_id": "111", "model": "anthropic/claude-sonnet-4.6", "estimated_model_cost_usd": "6.00"}]

    assert module._allocate_actual_cost_by_agent(usage_agents, {"status": "unavailable:key_unavailable"}) == {}


def test_per_skill_and_account_actual_cost_profit_use_real_openrouter_spend() -> None:
    module = load_module()
    payloads = skill_analytics_payloads()
    payloads["usage_requests"] = {"rows": [{
        "requestId": "r1", "agentId": "111", "agentTitle": "Hook Lab",
        "inputUncached": 1_000_000, "cacheRead": 0, "cacheWrite": 0, "output": 0,
    }]}
    payloads["agent_models"] = {"111": "anthropic/claude-sonnet-4.6"}
    payloads["model_prices"] = {"anthropic/claude-sonnet-4.6": {"prompt": "0.00002", "completion": "0.000015"}}
    payloads["openrouter_activity"] = {"data": [
        {"date": "2026-09-01", "model": "anthropic/claude-sonnet-4.6", "usage": 42.87, "requests": 817},
    ]}

    analytics = module.build_skill_analytics(
        payloads, skill_agent_stats(), {"111": "Claude Sonnet 4.6"}, "2026-09-27T00:00:00Z",
    )

    rows = {row["agent_id"]: row for row in analytics["per_skill_rows"]}
    # 111 is the only agent with an estimated cost for this model, so it absorbs the full
    # real spend even though its estimate ("20.00") was lower than the actual bill.
    assert rows["111"]["cost_30d_actual_usd"] == "42.87"
    assert rows["111"]["profit_30d_usd"] == "-0.09"  # unchanged estimate-based figure
    assert rows["111"]["profit_30d_actual_usd"] == "-22.96"  # 19.91 net - 42.87 actual
    assert rows["222"]["cost_30d_actual_usd"] is None

    assert analytics["account_totals"]["net30_usd"] is not None
    assert analytics["account_totals"]["cost30_actual_usd"] == "42.87"
    assert analytics["account_totals"]["profit30_actual_usd"] == module._money(
        module.Decimal(analytics["account_totals"]["net30_usd"]) - module.Decimal("42.87"))
    assert "cost30(actual) $42.87" in analytics["telegram_summary"]
    assert "profit $-22.96" in analytics["telegram_summary"]
    assert any("api/v1/activity" in gap for gap in analytics["data_gaps"])


def test_account_actual_falls_back_to_estimate_label_when_activity_unavailable() -> None:
    module = load_module()
    payloads = skill_analytics_payloads()  # no openrouter_activity fixture -> key_unavailable

    analytics = module.build_skill_analytics(
        payloads, skill_agent_stats(), {"111": "Claude Sonnet 4.6"}, "2026-09-27T00:00:00Z",
    )

    assert analytics["account_totals"]["cost30_actual_usd"] is None
    assert analytics["account_totals"]["profit30_actual_usd"] is None
    assert analytics["openrouter_actual"]["status"].startswith("unavailable:")
    assert "cost30(est)" in analytics["telegram_summary"]


def test_live_payloads_fetches_activity_with_management_key(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module()
    observed = module.dt.datetime(2026, 9, 17, tzinfo=module.dt.timezone.utc)
    calls = []
    monkeypatch.setattr(module, "_token", lambda _root: "seller-token")
    monkeypatch.setattr(module, "_web_token", lambda: "web-token")
    monkeypatch.setattr(module, "_get", lambda path, _token: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_post", lambda path, _token, body: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_usage_requests", lambda *_args: {"rows": []})
    monkeypatch.setattr(module, "_openrouter_data", lambda path, token="": calls.append((path, token)) or {"data": []})
    monkeypatch.setenv("CAPAFY_OPENROUTER_MANAGEMENT_KEY", "mgmt-key")
    monkeypatch.delenv("CAPAFY_HOST_OPENROUTER_KEY", raising=False)

    payloads = module._live_payloads(Path("/tmp"), observed)

    assert ("/activity", "mgmt-key") in calls
    assert payloads["openrouter_activity"] == {"data": []}


def test_live_payloads_skips_activity_without_management_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    observed = module.dt.datetime(2026, 9, 17, tzinfo=module.dt.timezone.utc)
    monkeypatch.setattr(module, "_token", lambda _root: "seller-token")
    monkeypatch.setattr(module, "_web_token", lambda: "web-token")
    monkeypatch.setattr(module, "_get", lambda path, _token: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_post", lambda path, _token, body: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_usage_requests", lambda *_args: {"rows": []})
    monkeypatch.setattr(module, "_openrouter_data", lambda *_args: {"data": {}})
    monkeypatch.setenv("LIFE_MANAGER_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("CAPAFY_OPENROUTER_MANAGEMENT_KEY", raising=False)

    payloads = module._live_payloads(Path("/tmp"), observed)

    assert payloads["openrouter_activity"] == {"_error": "key_unavailable"}


def test_live_payloads_reads_management_key_from_life_manager_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    observed = module.dt.datetime(2026, 9, 17, tzinfo=module.dt.timezone.utc)
    calls = []
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CAPAFY_OPENROUTER_MANAGEMENT_KEY=mgmt-from-file\n"
        "CAPAFY_HOST_OPENROUTER_KEY=host-from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIFE_MANAGER_ENV_FILE", str(env_file))
    monkeypatch.delenv("CAPAFY_OPENROUTER_MANAGEMENT_KEY", raising=False)
    monkeypatch.delenv("CAPAFY_HOST_OPENROUTER_KEY", raising=False)
    monkeypatch.setattr(module, "_token", lambda _root: "seller-token")
    monkeypatch.setattr(module, "_web_token", lambda: "web-token")
    monkeypatch.setattr(module, "_get", lambda path, _token: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_post", lambda path, _token, body: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_usage_requests", lambda *_args: {"rows": []})
    monkeypatch.setattr(
        module,
        "_openrouter_data",
        lambda path, token="": calls.append((path, token)) or {"data": []},
    )

    module._live_payloads(Path("/tmp"), observed)

    assert ("/activity", "mgmt-from-file") in calls
    assert ("/key", "host-from-file") in calls


def test_live_payloads_prefers_process_management_key_over_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    observed = module.dt.datetime(2026, 9, 17, tzinfo=module.dt.timezone.utc)
    calls = []
    env_file = tmp_path / ".env"
    env_file.write_text("CAPAFY_OPENROUTER_MANAGEMENT_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("LIFE_MANAGER_ENV_FILE", str(env_file))
    monkeypatch.setenv("CAPAFY_OPENROUTER_MANAGEMENT_KEY", "process-key")
    monkeypatch.setattr(module, "_token", lambda _root: "seller-token")
    monkeypatch.setattr(module, "_web_token", lambda: "web-token")
    monkeypatch.setattr(module, "_get", lambda path, _token: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_post", lambda path, _token, body: {"code": 0, "data": {}})
    monkeypatch.setattr(module, "_usage_requests", lambda *_args: {"rows": []})
    monkeypatch.setattr(
        module,
        "_openrouter_data",
        lambda path, token="": calls.append((path, token)) or {"data": []},
    )

    module._live_payloads(Path("/tmp"), observed)

    assert ("/activity", "process-key") in calls


def test_token_reads_the_publisher_runtime_config(tmp_path, monkeypatch):
    # The live publisher keeps its REST session in runtime/capafy-publisher/config.json;
    # without it the per-skill stats were access_token_unavailable in production.
    module = load_module()
    monkeypatch.delenv("CAPAFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CAPAFY_TOKEN", raising=False)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))
    runtime = tmp_path / ".local/state/life-manager/runtime/capafy-publisher"
    runtime.mkdir(parents=True)
    (runtime / "config.json").write_text(json.dumps({"access_token": "runtime-token"}))
    assert module._token(tmp_path / "repo") == "runtime-token"
