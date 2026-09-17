#!/usr/bin/env python3
"""Read-only Capafy company reconcile with an atomic, truthful receipt."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


API = "https://api.capafy.ai"
OPENROUTER_API = "https://openrouter.ai/api/v1"
SOURCE_NAMES = (
    "account", "inventory", "sales", "payout", "refunds",
    "seller_sales", "seller_ranking", "creator_earnings", "earnings_ranking",
    "unit_sales", "statements",
)
CAPAFY_ACTIVE_SUBMISSION_CAP = 5


def _money(value: Any) -> str | None:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return f"{amount:.2f}" if amount.is_finite() else None


def _ok(payload: Any) -> bool:
    return isinstance(payload, dict) and "_error" not in payload and payload.get("code", 0) == 0


def _data(payload: Any) -> Any:
    return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload


def _sales_money(payload: dict) -> tuple[str | None, str | None, int | None]:
    if not _ok(payload):
        return None, None, None
    data = _data(payload)
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None, None, None
    gross = Decimal("0")
    refunds = Decimal("0")
    orders = 0
    try:
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError
            gross += Decimal(str(row.get("revenue", 0) or 0))
            refunds += Decimal(str(row.get("refundAmount", 0) or 0))
            raw_orders = row.get("orders", 0) or 0
            if isinstance(raw_orders, bool):
                raise ValueError
            orders += int(raw_orders)
    except (InvalidOperation, TypeError, ValueError):
        return None, None, None
    return _money(gross), _money(refunds), orders


def _payout_money(payload: dict) -> tuple[str | None, str | None]:
    if not _ok(payload):
        return None, None
    data = _data(payload)
    if not isinstance(data, dict):
        return None, None
    return _money(data.get("balancePayout")), _money(data.get("totalPayout"))


def _payout_balances(payload: dict) -> dict[str, str | None]:
    data = _data(payload) if _ok(payload) else None
    if not isinstance(data, dict):
        return {name: None for name in (
            "balance_pending_usd", "balance_confirmed_usd", "balance_payout_usd", "paid_out_usd")}
    return {
        "balance_pending_usd": _money(data.get("balancePending")),
        "balance_confirmed_usd": _money(data.get("balanceConfirmed")),
        "balance_payout_usd": _money(data.get("balancePayout")),
        "paid_out_usd": _money(data.get("totalPayout")),
    }


def _refund_count(payload: dict) -> int | None:
    if not _ok(payload):
        return None
    data = _data(payload)
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("list", "refunds", "records"):
            if isinstance(data.get(key), list):
                return len(data[key])
    return None


def _creator_earnings(payload: dict) -> str | None:
    data = _data(payload) if _ok(payload) else None
    return _money(data.get("totalRevenue")) if isinstance(data, dict) else None


def _unit_counts(payload: dict) -> tuple[int | None, int | None, int | None]:
    data = _data(payload) if _ok(payload) else None
    if not isinstance(data, dict):
        return None, None, None
    total, trial = data.get("totalSalesVolume"), data.get("totalFreeTrialCount")
    if (type(total) is not int or type(trial) is not int or trial < 0
            or total < trial):
        return None, None, None
    return total, trial, total - trial


def _subscription_earnings(payload: dict) -> str | None:
    data = _data(payload) if _ok(payload) else None
    agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, list):
        return None
    try:
        amount = sum(
            Decimal(str(sku.get("revenue", 0) or 0))
            for agent in agents for sku in (agent.get("skus") or [])
            if str(sku.get("skuType") or "").startswith("subscription_")
        )
    except (AttributeError, InvalidOperation, TypeError, ValueError):
        return None
    return _money(amount)


def _seller_money(sales_payload: dict, ranking_payload: dict, statements_payload: dict) -> dict:
    empty = {"gross": None, "orders": None, "refunds": None, "one_time": None,
             "mrr": None, "ending_balance": None, "payable": None, "winner": None}
    if not all(_ok(value) for value in (sales_payload, ranking_payload, statements_payload)):
        return empty
    sales = _data(sales_payload)
    ranking = _data(ranking_payload)
    statements = _data(statements_payload)
    if not isinstance(sales, dict) or not isinstance(ranking, dict) or not isinstance(statements, dict):
        return empty
    rows = sales.get("data")
    agents = ranking.get("agents")
    statement_rows = statements.get("list")
    if not isinstance(rows, list) or not isinstance(agents, list) or not isinstance(statement_rows, list):
        return empty
    try:
        gross = Decimal(str(sales.get("totalRevenue", 0) or 0))
        orders = sum(
            int(row.get("orders", 0) or 0)
            for row in rows
            if Decimal(str(row.get("revenue", 0) or 0)) > 0
        )
        refunds = sum(Decimal(str(row.get("refundAmount", 0) or 0)) for row in rows)
        subscription_sales = sum(
            Decimal(str(sku.get("salesAmount", 0) or 0))
            for agent in agents for sku in (agent.get("skus") or [])
            if str(sku.get("skuType") or "").startswith("subscription_")
        )
        winner_row = max(agents, key=lambda agent: Decimal(str(agent.get("totalSalesAmount", 0) or 0)), default={})
        winner_sales = Decimal(str(winner_row.get("totalSalesAmount", 0) or 0))
        winner_sku = max(
            winner_row.get("skus") or [],
            key=lambda sku: Decimal(str(sku.get("salesAmount", 0) or 0)),
            default={},
        )
        latest = max(statement_rows, key=lambda row: str(row.get("settlementMonth") or ""), default={})
    except (InvalidOperation, TypeError, ValueError):
        return empty
    # Sales do not reveal which subscriptions remain active or canceled.
    mrr = None
    sku_type = str(winner_sku.get("skuType") or "")
    winner = None
    if winner_sales > 0 and winner_row.get("agentId") and winner_row.get("agentTitle"):
        winner = {
            "agent_id": str(winner_row["agentId"]),
            "name": str(winner_row["agentTitle"]),
            "sales_usd": _money(winner_sales),
            "sku_type": sku_type,
            "revenue_kind": "subscription" if sku_type.startswith("subscription_") else "one_time",
            "source": "official_publisher_console",
        }
    return {
        "gross": _money(gross), "orders": orders, "refunds": _money(refunds),
        "one_time": _money(gross - subscription_sales), "mrr": mrr,
        "ending_balance": _money(latest.get("endingSettlementBalance")) if latest else None,
        "payable": _money(latest.get("payableAmount")) if latest else None,
        "winner": winner,
    }


def _inventory(payload: dict) -> dict:
    result = {"status": "unknown_unrecognized_shape", "observed_agents": None, "occupied": None, "free": None}
    if not _ok(payload):
        result["status"] = "unknown_source_error"
        return result
    data = _data(payload)
    rows = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("list", "agents"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    if rows is None:
        return result

    counts = {"listed": 0, "occupied": 0, "retry": 0, "blocked": 0}
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("agentId") or "").strip():
            result.update(status="unknown_invalid_agent", observed_agents=len(rows))
            return result
        status = row.get("agentStatus")
        if status in {"online", "approved"}:
            counts["listed"] += 1
        elif status in {"draft", "under_review"}:
            counts["occupied"] += 1
        elif status == "review_rejected":
            counts["retry"] += 1
        elif status == "banned":
            counts["blocked"] += 1
        else:
            result.update(status="unknown_unrecognized_status", observed_agents=len(rows))
            return result
    result.update(
        status="normalized",
        observed_agents=len(rows),
        listed=counts["listed"],
        occupied=counts["occupied"],
        free=max(0, CAPAFY_ACTIVE_SUBMISSION_CAP - counts["occupied"]),
        retry=counts["retry"],
        blocked=counts["blocked"],
    )
    return result


def build_receipt(payloads: dict[str, dict], observed_at: str) -> dict:
    sources = {
        name: {
            "freshness": "fresh" if _ok(payloads.get(name)) else "unknown",
            "error": payloads.get(name, {}).get("_error") if isinstance(payloads.get(name), dict) else "missing",
        }
        for name in SOURCE_NAMES
    }
    legacy_gross, legacy_refunds, legacy_orders = _sales_money(payloads.get("sales", {}))
    seller = _seller_money(
        payloads.get("seller_sales", {}), payloads.get("seller_ranking", {}), payloads.get("statements", {})
    )
    gross, refunds, orders = seller["gross"], seller["refunds"], seller["orders"]
    earnings = _creator_earnings(payloads.get("creator_earnings", {}))
    units, trials, non_trials = _unit_counts(payloads.get("unit_sales", {}))
    subscription_earnings = _subscription_earnings(payloads.get("earnings_ranking", {}))
    pending, realized = _payout_money(payloads.get("payout", {}))
    payout_balances = _payout_balances(payloads.get("payout", {}))
    inventory = _inventory(payloads.get("inventory", {}))
    required_fresh = (
        all(sources[name]["freshness"] == "fresh" for name in SOURCE_NAMES)
        and inventory["status"] == "normalized"
    )
    return {
        "schema_version": 1,
        "kind": "capafy_hourly_reconcile",
        "observed_at": observed_at,
        "verdict": "success" if required_fresh else "degraded",
        "account": {"authenticated": True if _ok(payloads.get("account")) else None},
        "inventory": inventory,
        "orders": orders,
        "seller_winner": seller["winner"],
        "legacy_agent_api": {"orders": legacy_orders, "gross_usd": legacy_gross, "refunds_usd": legacy_refunds},
        "refunds": {"tickets": _refund_count(payloads.get("refunds", {}))},
        "money": {
            "gross_usd": gross,
            "creator_earnings_usd": earnings,
            "unit_sales_total": units,
            "free_trial_units": trials,
            "non_trial_units": non_trials,
            "observed_subscription_earnings_usd": subscription_earnings,
            **payout_balances,
            "one_time_revenue_usd": seller["one_time"],
            "pending_usd": pending,
            "realized_usd": realized,
            "refunds_usd": refunds,
            "settled_mrr_usd": seller["mrr"],
            "net_mrr_usd": seller["mrr"],
            "statement_ending_balance_usd": seller["ending_balance"],
            "statement_payable_usd": seller["payable"],
        },
        "money_status": {
            "gross_usd": "fresh" if gross is not None else "unknown",
            "creator_earnings_usd": "fresh" if earnings is not None else "unknown",
            "unit_sales_total": "fresh" if units is not None else "unknown",
            "observed_subscription_earnings_usd": "fresh_not_mrr" if subscription_earnings is not None else "unknown",
            "one_time_revenue_usd": "fresh_official_seller_console" if seller["one_time"] is not None else "unknown",
            "pending_usd": "fresh" if pending is not None else "unknown",
            "realized_usd": "fresh" if realized is not None else "unknown",
            "refunds_usd": "fresh" if refunds is not None else "unknown",
            "settled_mrr_usd": "unknown_active_subscription_status",
            "net_mrr_usd": "unknown_active_subscription_status",
        },
        "sources": sources,
        "usage": _usage_summary(payloads.get("usage_requests", {}),
                                payloads.get("agent_models", {}),
                                payloads.get("model_prices", {})),
        "openrouter": payloads.get("openrouter_usage", {"_error": "not_observed"}),
    }


def _token(repo_root: Path) -> str:
    for key in ("CAPAFY_ACCESS_TOKEN", "CAPAFY_TOKEN"):
        if os.environ.get(key):
            return str(os.environ[key])
    candidates = (
        Path.home() / ".local/state/life-manager/credentials/capafy-publisher.json",
        repo_root / "skills/capafy-autopublish/vendor/capafy-publisher/config.json",
    )
    for path in candidates:
        try:
            token = json.loads(path.read_text()).get("access_token")
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        if token:
            return str(token)
    return ""


def _web_token() -> str:
    try:
        credentials = json.loads((Path.home() / ".local/share/anicca/credentials.json").read_text())["credentials"]
        matches = [row for row in credentials if row.get("service") == "capafy-publisher"]
        return str(matches[0].get("web_token") or "") if len(matches) == 1 else ""
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return ""


def _get(path: str, token: str) -> dict:
    request = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            value = json.loads(response.read().decode("utf-8"))
            return value if isinstance(value, dict) else {"_error": "response_not_object"}
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def _post(path: str, token: str, body: dict) -> dict:
    request = urllib.request.Request(
        API + path, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            value = json.loads(response.read().decode("utf-8"))
            return value if isinstance(value, dict) else {"_error": "response_not_object"}
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def _usage_requests(web_token: str, start: str, end: str) -> dict:
    rows: list[dict] = []
    seen: set[str] = set()
    cursor: dict = {}
    expected: int | None = None
    while True:
        payload = _post("/app/usage/requests", web_token, {
            "startDate": start, "endDate": end, "pageSize": 50, **cursor,
        })
        data = _data(payload) if _ok(payload) else None
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return {"_error": "usage_request_source_invalid"}
        if expected is None:
            expected = data.get("total") if type(data.get("total")) is int else None
        for row in data["items"]:
            request_id = row.get("requestId") if isinstance(row, dict) else None
            if not request_id or request_id in seen:
                return {"_error": "usage_request_duplicate_or_missing_id"}
            seen.add(request_id)
            rows.append(row)
        if not data.get("hasMore"):
            break
        next_cursor = {"cursorTime": data.get("nextCursorTime"),
                       "cursorRequestId": data.get("nextCursorRequestId")}
        if not all(next_cursor.values()) or next_cursor == cursor or not data["items"]:
            return {"_error": "usage_request_cursor_stalled"}
        cursor = next_cursor
        if expected is not None and len(rows) > expected:
            return {"_error": "usage_request_total_exceeded"}
    if expected is not None and len(rows) != expected:
        return {"_error": "usage_request_total_mismatch"}
    return {"rows": rows, "total": len(rows)}


def _openrouter_data(path: str, token: str = "") -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(OPENROUTER_API + path, headers=headers),
                                    timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def _usage_summary(payload: dict, models: dict[str, str], prices: dict) -> dict:
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {"status": "unknown_usage_source", "agents": [], "requests": None,
                "zero_token_requests": None, "estimated_model_cost_usd": None}
    agents: dict[str, dict] = {}
    for row in rows:
        aid = str(row.get("agentId") or "")
        if not aid:
            return {"status": "unknown_agent_id", "agents": [], "requests": None,
                    "zero_token_requests": None, "estimated_model_cost_usd": None}
        agent = agents.setdefault(aid, {"agent_id": aid, "name": row.get("agentTitle"),
                                        "model": models.get(aid), "requests": 0,
                                        "zero_token_requests": 0,
                                        "input_uncached": 0, "cache_read": 0,
                                        "cache_write": 0, "output": 0})
        agent["requests"] += 1
        for source, target in (("inputUncached", "input_uncached"), ("cacheRead", "cache_read"),
                               ("cacheWrite", "cache_write"), ("output", "output")):
            value = row.get(source)
            if type(value) is not int or value < 0:
                return {"status": "unknown_token_shape", "agents": [], "requests": None,
                        "zero_token_requests": None, "estimated_model_cost_usd": None}
            agent[target] += value
        if all(row[key] == 0 for key in ("inputUncached", "cacheRead", "cacheWrite", "output")):
            agent["zero_token_requests"] += 1
    total_cost = Decimal("0")
    all_priced = True
    for agent in agents.values():
        price = prices.get(agent["model"]) if agent["model"] else None
        if not isinstance(price, dict):
            agent["estimated_model_cost_usd"] = None
            all_priced = False
            continue
        try:
            cost = sum(Decimal(str(price.get(rate, "0"))) * agent[count] for count, rate in (
                ("input_uncached", "prompt"), ("cache_read", "input_cache_read"),
                ("cache_write", "input_cache_write"), ("output", "completion")))
        except (InvalidOperation, TypeError):
            agent["estimated_model_cost_usd"] = None
            all_priced = False
            continue
        agent["estimated_model_cost_usd"] = _money(cost)
        total_cost += cost
    return {"status": "estimated" if all_priced else "partial_missing_model_or_price",
            "agents": sorted(agents.values(), key=lambda agent: agent["requests"], reverse=True),
            "requests": len(rows),
            "zero_token_requests": sum(agent["zero_token_requests"] for agent in agents.values()),
            "estimated_model_cost_usd": _money(total_cost) if all_priced else None}


def _live_payloads(repo_root: Path, observed: dt.datetime,
                   *, seller_start_date: dt.date | None = None) -> dict[str, dict]:
    token = _token(repo_root)
    web_token = _web_token()
    if not token:
        return {name: {"_error": "access_token_unavailable"} for name in SOURCE_NAMES}
    start = (observed.date() - dt.timedelta(days=89)).isoformat()
    end = observed.date().isoformat()
    paths = {
        "account": "/agent/account",
        "inventory": "/agent/agents",
        "sales": f"/agent/sales/trend?startDate={start}&endDate={end}",
        "payout": "/agent/developer/payout-info",
        "refunds": "/agent/refund/developer/list",
    }
    payloads = {name: _get(path, token) for name, path in paths.items()}
    if not web_token:
        payloads.update({name: {"_error": "web_token_unavailable"} for name in (
            "seller_sales", "seller_ranking", "creator_earnings", "earnings_ranking",
            "unit_sales", "statements",
        )})
        return payloads
    seller_range = (
        {"sinceLaunch": True} if seller_start_date is None
        else {"startDate": seller_start_date.isoformat(),
              "endDate": end}
    )
    period = {**seller_range, "granularity": "daily"}
    payloads.update({
        "seller_sales": _post("/app/sales/clickhouse/trend", web_token, period),
        "seller_ranking": _post("/app/sales/clickhouse/ranking", web_token,
                                {**period, "languageCode": "en"}),
        "creator_earnings": _post("/app/realtime-revenue/clickhouse/trend", web_token,
                                  {**period, "dimension": "all"}),
        "earnings_ranking": _post("/app/realtime-revenue/clickhouse/comparison", web_token,
                                  {**period, "languageCode": "en"}),
        "unit_sales": _post("/app/unit-sales/clickhouse/trend", web_token, period),
        "statements": _get("/app/developer/settlement-statement/list?page=1&size=20", web_token),
    })
    if seller_start_date is not None:
        usage = _usage_requests(web_token, seller_range["startDate"], end)
        payloads["usage_requests"] = usage
        agent_ids = {str(row.get("agentId")) for row in usage.get("rows", []) if row.get("agentId")}
        details = {aid: _data(_get(f"/agent/agents/{aid}", token)) for aid in agent_ids}
        display_models = {aid: detail.get("model") if isinstance(detail, dict) else None
                          for aid, detail in details.items()}
        model_ids = {"Claude Sonnet 4.6": "anthropic/claude-sonnet-4.6",
                     "DeepSeek V4.1 Flash": "deepseek/deepseek-v4.1-flash"}
        payloads["agent_models"] = {aid: model_ids.get(display) for aid, display in display_models.items()}
        catalog = _openrouter_data("/models")
        model_rows = catalog.get("data") if isinstance(catalog, dict) else None
        payloads["model_prices"] = (
            {row["id"]: row.get("pricing", {}) for row in model_rows if isinstance(row, dict) and row.get("id")}
            if isinstance(model_rows, list) else {})
        key = os.environ.get("CAPAFY_HOST_OPENROUTER_KEY", "")
        key_result = _openrouter_data("/key", key) if key else {"_error": "key_unavailable"}
        key_data = _data(key_result) if _ok(key_result) else None
        payloads["openrouter_usage"] = (
            {"data": {"usage_monthly": key_data.get("usage_monthly")}}
            if isinstance(key_data, dict) else {"_error": "key_usage_unavailable"})
    return payloads


def _atomic_write(path: Path, receipt: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _money_snapshot(receipt: dict, observed: dt.datetime) -> dict:
    money = receipt["money"]
    openrouter = _data(receipt["openrouter"]) if _ok(receipt["openrouter"]) else None
    return {
        "kind": "capafy_money_readback",
        "observed_at": receipt["observed_at"],
        "window_start": observed.date().replace(day=1).isoformat(),
        "window_end": observed.date().isoformat(),
        "window_kind": "calendar_month_to_date_utc",
        "gross_sales_usd": money["gross_usd"],
        "creator_earnings_usd": money["creator_earnings_usd"],
        "unit_sales_total": money["unit_sales_total"],
        "free_trial_units": money["free_trial_units"],
        "non_trial_units": money["non_trial_units"],
        "observed_subscription_earnings_usd": money["observed_subscription_earnings_usd"],
        "payout": {key: money[key] for key in (
            "balance_pending_usd", "balance_confirmed_usd", "balance_payout_usd", "paid_out_usd")},
        "active_mrr_usd": None,
        "active_mrr_status": "missing_seller_active_subscription_source",
        "usage": receipt["usage"],
        "openrouter_host_key_calendar_month_usage_usd": (
            _money(openrouter.get("usage_monthly")) if isinstance(openrouter, dict) else None),
        "openrouter_host_key_usage_status": (
            "fresh" if isinstance(openrouter, dict) and _money(openrouter.get("usage_monthly")) is not None
            else "unknown"),
        "source_status": {key: receipt["sources"][key]["freshness"] for key in (
            "seller_sales", "creator_earnings", "earnings_ranking", "unit_sales", "payout")},
    }


def _money_complete(snapshot: dict) -> bool:
    return (all(value == "fresh" for value in snapshot["source_status"].values())
            and snapshot["gross_sales_usd"] is not None
            and snapshot["creator_earnings_usd"] is not None
            and snapshot["unit_sales_total"] is not None
            and snapshot["free_trial_units"] is not None
            and snapshot["usage"]["status"] == "estimated"
            and snapshot["openrouter_host_key_usage_status"] == "fresh"
            and all(value is not None for value in snapshot["payout"].values()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--money", action="store_true", help="read live money without writing state")
    parser.add_argument("--json", action="store_true", help="machine-readable money output")
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path.home() / ".local/state/life-manager/state/capafy-hourly-reconcile.json")
    parser.add_argument("--observed-at")
    args = parser.parse_args(argv)
    observed = dt.datetime.now(dt.timezone.utc)
    if args.observed_at:
        observed = dt.datetime.fromisoformat(args.observed_at.replace("Z", "+00:00"))
    observed_at = observed.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    repo_root = Path(__file__).resolve().parents[4]
    if args.fixture_dir:
        payloads = {name: json.loads((args.fixture_dir / f"{name}.json").read_text()) for name in SOURCE_NAMES}
        for name in ("usage_requests", "agent_models", "model_prices", "openrouter_usage"):
            path = args.fixture_dir / f"{name}.json"
            if path.exists():
                payloads[name] = json.loads(path.read_text())
    else:
        payloads = _live_payloads(repo_root, observed,
                                  seller_start_date=observed.date().replace(day=1) if args.money else None)
    receipt = build_receipt(payloads, observed_at)
    if args.money:
        snapshot = _money_snapshot(receipt, observed)
        if args.json:
            print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
        else:
            print(f"Capafy money {snapshot['window_start']}..{snapshot['window_end']}")
            print(f"Gross sales: ${snapshot['gross_sales_usd']}  Creator earnings: ${snapshot['creator_earnings_usd']}")
            print(f"Units: {snapshot['unit_sales_total']}  Free trials: {snapshot['free_trial_units']}  Other units: {snapshot['non_trial_units']}")
            print(f"Observed subscription earnings: ${snapshot['observed_subscription_earnings_usd']} (cash flow, not MRR)")
            print(f"Payout: {snapshot['payout']}")
            print(f"Requests: {snapshot['usage']['requests']}  Zero-token: {snapshot['usage']['zero_token_requests']}")
            print(f"Estimated model cost (same window): ${snapshot['usage']['estimated_model_cost_usd']}")
            print(f"OpenRouter host key usage (calendar month): ${snapshot['openrouter_host_key_calendar_month_usage_usd']}")
            print("Active MRR: unavailable (seller active-subscription source missing)")
        return 0 if _money_complete(snapshot) else 1
    _atomic_write(args.output, receipt)
    print(json.dumps(receipt, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0 if receipt["verdict"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
