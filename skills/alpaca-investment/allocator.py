"""Declared-card allocation with a deterministic risk boundary."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from risk_policy import evaluate_entry
from etf_ownership import investment_owner_id
from strategy_policy import (ACTION_ENTER, ACTION_EXIT, ACTION_NO_TRADE, ALLOWED_ACTIONS,
                             BTC_SYMBOLS, CANONICAL_SYMBOL, ETF_STRATEGY_ID,
                             ETF_SYMBOLS, evaluate,
                             load_selected_card)


MAX_QUOTE_AGE_SECONDS = 30
MAX_SPREAD_FRACTION = .15
MIN_CASH_FRACTION = .30


def _read_selection(state: Path) -> dict[str, Any] | None:
    path = state / "selected-strategy.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("strategy_selection_invalid") from error
    if not isinstance(value, dict):
        raise ValueError("strategy_selection_invalid")
    return value


def _age_seconds(timestamp: str) -> float:
    normalized = timestamp.replace("Z", "+00:00")
    # Apple system Python 3.9 accepts at most six fractional-second digits;
    # Alpaca can return nanosecond timestamps. Keep the instant, normalize the
    # precision, and make the same candidate gate portable across host Pythons.
    match = re.fullmatch(r"(.*)\.(\d+)([+-]\d{2}:\d{2})", normalized)
    if match:
        normalized = f"{match.group(1)}.{match.group(2)[:6].ljust(6, '0')}{match.group(3)}"
    observed = datetime.fromisoformat(normalized)
    return (datetime.now(timezone.utc) - observed).total_seconds()


def _option_parts(symbol: str) -> tuple[str, int] | None:
    match = re.fullmatch(r"SPY(\d{6})C(\d{8})", symbol)
    return (match.group(1), int(match.group(2))) if match else None


def build_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    histories = snapshot.get("crypto_history", {})
    for quote in snapshot["crypto"]:
        bid, ask = float(quote["bid"]), float(quote["ask"])
        if bid > 0 and ask >= bid:
            candidates.append({
                "asset_class": "crypto", "ask": ask, "bid": bid,
                "candidate_ref": f"crypto://{quote['symbol']}",
                "max_loss_usd": 10.0, "quote_age_seconds": _age_seconds(quote["quote_at"]),
                "spread_fraction": (ask - bid) / ask, "symbol": quote["symbol"],
                "history_5min": histories.get(quote["symbol"], []),
            })
    asset, quote = snapshot["qqq_asset"], snapshot["qqq_quote"]
    if (asset.get("tradable") is True and asset.get("status") == "active"
            and asset.get("overnight_tradable") is True
            and asset.get("overnight_halted") is False):
        bid, ask = float(quote["bid"]), float(quote["ask"])
        candidates.append({
            "asset_class": "equity", "ask": ask, "bid": bid,
            "candidate_ref": "equity://QQQ", "max_loss_usd": 10.0,
            "quote_age_seconds": _age_seconds(quote["quote_at"]),
            "spread_fraction": (ask - bid) / ask, "symbol": "QQQ",
        })
    daily_bars = snapshot.get("daily_bars")
    if isinstance(daily_bars, dict) and all(symbol in daily_bars for symbol in ETF_SYMBOLS):
        for symbol in ETF_SYMBOLS:
            candidates.append({
                "asset_class": "us_equity", "candidate_ref": f"equity://{symbol}",
                "max_loss_usd": 10.0, "quote_age_seconds": 0,
                "spread_fraction": 0, "symbol": symbol,
            })
    if snapshot["clock"].get("is_open") is True:
        quotes = sorted(snapshot["option_quotes"], key=lambda row: row["symbol"])
        for left, right in zip(quotes, quotes[1:]):
            a, b = _option_parts(left["symbol"]), _option_parts(right["symbol"])
            if not a or not b or a[0] != b[0] or b[1] - a[1] != 1000:
                continue
            debit = float(left["ask"]) - float(right["bid"])
            if debit <= 0:
                continue
            candidates.append({
                "asset_class": "option_spread",
                "ask": float(left["ask"]), "bid": float(right["bid"]),
                "candidate_ref": f"option-spread://{left['symbol']}-{right['symbol']}",
                "long_symbol": left["symbol"], "short_symbol": right["symbol"],
                "max_loss_usd": round(debit * 100, 2),
                "max_profit_usd": round((1 - debit) * 100, 2),
                "quote_age_seconds": max(_age_seconds(left["quote_at"]), _age_seconds(right["quote_at"])),
                "spread_fraction": abs(float(left["ask"]) - float(left["bid"])) / float(left["ask"]),
            })
    return candidates


def choose(snapshot: dict[str, Any], candidates: list[dict[str, Any]], state: Path,
           runner: Path, workdir: Path) -> dict[str, Any]:
    """Evaluate the release-pinned card; runner/workdir remain for API compatibility."""
    del runner, workdir
    observed_at = snapshot.get("clock", {}).get("timestamp")
    try:
        selection = _read_selection(state)
    except ValueError as error:
        return {
            "action": ACTION_NO_TRADE,
            "strategy_id": None,
            "signal_inputs": {},
            "reason": str(error),
            "expected_cost_usd": None,
            "candidate_ref": "NO_TRADE",
            "approved": False,
            "gate": "strategy_selection_invalid",
            "observed_at": observed_at,
        }
    if selection is not None and selection.get("strategy_id") == "NO_STRATEGY":
        return {
            "action": ACTION_NO_TRADE,
            "strategy_id": None,
            "signal_inputs": {},
            "reason": "no_strategy_selected",
            "expected_cost_usd": None,
            "candidate_ref": "NO_TRADE",
            "approved": False,
            "gate": "strategy_selection_no_strategy",
            "observed_at": observed_at,
        }
    try:
        card, release_sha = load_selected_card(state)
    except ValueError as error:
        return {
            "action": ACTION_NO_TRADE,
            "strategy_id": None,
            "signal_inputs": {},
            "reason": str(error),
            "expected_cost_usd": None,
            "candidate_ref": "NO_TRADE",
            "approved": False,
            "gate": str(error),
            "observed_at": observed_at,
        }
    if selection is not None:
        if (selection.get("selection") != "selected"
                or not isinstance(selection.get("report_id"), str)
                or not selection["report_id"].strip()):
            return {
                "action": ACTION_NO_TRADE,
                "strategy_id": None,
                "signal_inputs": {},
                "reason": "strategy_selection_invalid",
                "expected_cost_usd": None,
                "candidate_ref": "NO_TRADE",
                "approved": False,
                "gate": "strategy_selection_invalid",
                "observed_at": observed_at,
            }
        if (selection.get("strategy_id") != card.strategy_id
                or selection.get("release_sha") != release_sha):
            return {
                "action": ACTION_NO_TRADE,
                "strategy_id": None,
                "signal_inputs": {},
                "reason": "strategy_selection_mismatch",
                "expected_cost_usd": None,
                "candidate_ref": "NO_TRADE",
                "approved": False,
                "gate": "strategy_selection_mismatch",
                "observed_at": observed_at,
            }
    policy = evaluate(snapshot, card, owner_id=investment_owner_id())
    if card.strategy_id == ETF_STRATEGY_ID:
        if policy.get("action") == ACTION_NO_TRADE:
            decision = {**policy, "candidate_ref": "NO_TRADE", "release_sha": release_sha}
            gated = gate(snapshot, candidates, decision)
            gated["observed_at"] = observed_at
            return gated
        offered = next((row for row in candidates
                        if row.get("asset_class") == "us_equity"
                        and row.get("symbol") == policy.get("symbol")), None)
    else:
        offered = next((row for row in candidates
                        if row.get("asset_class") == "crypto"
                        and row.get("symbol") in BTC_SYMBOLS), None)
    if offered is None:
        return {
            "action": ACTION_NO_TRADE,
            "strategy_id": card.strategy_id,
            "signal_inputs": policy.get("signal_inputs", {}),
            "reason": "candidate_not_offered",
            "expected_cost_usd": policy.get("expected_cost_usd"),
            "candidate_ref": "NO_TRADE",
            "release_sha": release_sha,
            "approved": False,
            "gate": "candidate_not_offered",
            "observed_at": observed_at,
        }
    decision = {**policy, "candidate_ref": offered["candidate_ref"], "release_sha": release_sha}
    if card.strategy_id == ETF_STRATEGY_ID:
        decision["owner_id"] = investment_owner_id()
        decision["position"] = snapshot.get("position")
    gated = gate(snapshot, candidates, decision)
    gated["observed_at"] = observed_at
    return gated


def gate(snapshot: dict[str, Any], candidates: list[dict[str, Any]], decision: dict[str, Any]) -> dict[str, Any]:
    offered = {row["candidate_ref"]: row for row in candidates}
    ref = decision.get("candidate_ref")
    if decision.get("action") in ALLOWED_ACTIONS:
        if decision.get("action") == ACTION_EXIT:
            candidate = offered.get(ref)
            position = snapshot.get("position")
            if candidate is None:
                return {**decision, "approved": False, "gate": "candidate_not_offered"}
            checks = {
                "paper_mode": candidate.get("asset_class") == "us_equity"
                and snapshot.get("mode") == "paper",
                "position_slot": snapshot.get("positions") == 1,
                "position_owned": isinstance(position, dict)
                and position.get("owner_id") == decision.get("owner_id")
                and position.get("strategy_id") == ETF_STRATEGY_ID
                and position.get("symbol") == candidate.get("symbol"),
                "position_quantity": isinstance(position, dict)
                and isinstance(position.get("qty"), str)
                and float(position["qty"]) > 0,
                "order_slot": snapshot.get("open_orders") == 0,
                "intent_slot": snapshot.get("unresolved_intents") == 0,
                "policy_cost_complete": decision.get("expected_cost_usd") is not None,
            }
            return {**decision, "approved": all(checks.values()),
                    "candidate": candidate, "checks": checks,
                    "gate": "approved_exit" if all(checks.values()) else "exit_rejected"}
        if decision.get("action") != ACTION_ENTER:
            return {**decision, "approved": False,
                    "gate": f"policy_{str(decision.get('action')).lower()}"}
        candidate = offered.get(ref)
        if candidate is None:
            return {**decision, "approved": False, "gate": "candidate_not_offered"}
        try:
            equity = float(snapshot["account"]["equity"])
            cash = float(snapshot.get("available_cash_usd", snapshot["account"]["cash"]))
            loss = float(candidate["max_loss_usd"])
        except (KeyError, TypeError, ValueError):
            return {**decision, "approved": False, "gate": "snapshot_invalid"}
        fixed_risk = evaluate_entry(snapshot.get("risk"), candidate["max_loss_usd"])
        is_equity = candidate.get("asset_class") == "us_equity"
        if is_equity and snapshot.get("mode") != "paper":
            return {**decision, "approved": False,
                    "gate": "live_etf_rejected" if snapshot.get("mode") == "live"
                    else "paper_mode_required", "candidate": candidate}
        checks = {
            "quote_fresh": 0 <= candidate.get("quote_age_seconds", -1) <= MAX_QUOTE_AGE_SECONDS,
            "spread": candidate.get("spread_fraction", MAX_SPREAD_FRACTION + 1) <= MAX_SPREAD_FRACTION,
            "policy_cost_complete": decision.get("expected_cost_usd") is not None,
            "fixed_risk": fixed_risk["approved"],
            "cash_reserve": cash - loss >= equity * MIN_CASH_FRACTION,
            "position_slot": snapshot.get("positions") == 0,
            "order_slot": snapshot.get("open_orders") == 0,
            "intent_slot": snapshot.get("unresolved_intents") == 0,
            "instrument_allowed": (
                candidate.get("symbol") in ETF_SYMBOLS if is_equity
                else candidate.get("symbol") == CANONICAL_SYMBOL
            ),
            "paper_mode": (not is_equity) or snapshot.get("mode") == "paper",
        }
        approved = all(checks.values()) and candidate.get("asset_class") in {
            "crypto", "us_equity",
        }
        return {**decision, "approved": approved, "candidate": candidate,
                "checks": checks, "fixed_risk": fixed_risk,
                "gate": "approved" if approved else "risk_rejected"}
    if ref == "NO_TRADE":
        return {**decision, "approved": False, "gate": "model_no_trade"}
    candidate = offered.get(ref)
    if candidate is None:
        return {**decision, "approved": False, "gate": "candidate_not_offered"}
    equity = float(snapshot["account"]["equity"])
    cash = float(snapshot.get("available_cash_usd", snapshot["account"]["cash"]))
    probability, gain = float(decision["probability_profit"]), float(decision["expected_gain_usd"])
    loss = float(candidate["max_loss_usd"])
    fixed_risk = evaluate_entry(snapshot.get("risk"), candidate["max_loss_usd"])
    checks = {
        "quote_fresh": 0 <= candidate["quote_age_seconds"] <= MAX_QUOTE_AGE_SECONDS,
        "spread": candidate["spread_fraction"] <= MAX_SPREAD_FRACTION,
        "expected_value": 0 <= probability <= 1 and gain > 0 and probability * gain - (1 - probability) * loss > 0,
        "fixed_risk": fixed_risk["approved"],
        "cash_reserve": cash - loss >= equity * MIN_CASH_FRACTION,
        "position_slot": snapshot["positions"] == 0,
        "order_slot": snapshot["open_orders"] == 0,
        "intent_slot": snapshot.get("unresolved_intents") == 0,
    }
    if candidate["asset_class"] == "option_spread":
        checks["bounded_upside"] = gain <= float(candidate["max_profit_usd"])
        checks["regular_session"] = snapshot["clock"].get("is_open") is True
    approved = all(checks.values()) and candidate["asset_class"] in {"crypto", "option_spread"}
    return {**decision, "approved": approved, "candidate": candidate,
            "checks": checks, "fixed_risk": fixed_risk,
            "gate": "approved" if approved else "risk_rejected"}


def order_for(decision: dict[str, Any]) -> dict[str, Any]:
    candidate = decision["candidate"]
    if candidate["asset_class"] == "crypto":
        return {"asset_class": "crypto", "notional_usd": f"{candidate['max_loss_usd']:.2f}",
                "side": "buy", "symbol": candidate["symbol"], "time_in_force": "gtc", "type": "market"}
    if candidate["asset_class"] == "us_equity":
        if decision.get("action") == ACTION_EXIT:
            position = decision.get("position")
            if not isinstance(position, dict) or not isinstance(position.get("qty"), str):
                raise ValueError("etf_exit_position_missing")
            return {"asset_class": "us_equity", "qty": position["qty"],
                    "side": "sell", "symbol": candidate["symbol"],
                    "time_in_force": "day", "type": "market"}
        return {"asset_class": "us_equity", "notional_usd": f"{candidate['max_loss_usd']:.2f}",
                "side": "buy", "symbol": candidate["symbol"],
                "time_in_force": "day", "type": "market"}
    return {"asset_class": "option_spread", "limit_price": f"{candidate['max_loss_usd'] / 100:.2f}",
            "long_symbol": candidate["long_symbol"], "short_symbol": candidate["short_symbol"],
            "time_in_force": "day", "type": "limit"}
