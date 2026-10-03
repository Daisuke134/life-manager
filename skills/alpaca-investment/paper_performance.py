"""Build a read-only paper ETF performance receipt from the effect ledger."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


OWNER_ID = "alpaca-investment-paper"
STRATEGY_ID = "alpaca-etf-126d-momentum-v1"
BROKER_TERMINAL_FAILURE_STATUSES = frozenset({
    "canceled", "done_for_day", "expired", "rejected", "stopped", "suspended",
})
BROKER_NONTERMINAL_STATUSES = frozenset({
    "accepted", "accepted_for_bidding", "new", "partially_filled",
    "pending_cancel", "pending_new", "pending_replace",
})


def _unknown(reason: str) -> dict[str, str]:
    return {"status": "unknown", "reason": reason}


def _number(value: Any, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("paper_number_invalid")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("paper_number_invalid") from error
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError("paper_number_invalid")
    return number


def _money(value: Decimal) -> str:
    if value == 0:
        return "0.00"
    return format(value.normalize(), "f")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("paper_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("paper_timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("paper_timestamp_invalid")
    return parsed


def _utc_day(value: Any) -> str:
    return _timestamp(value).astimezone(timezone.utc).date().isoformat()


def _source_ids(intent: Mapping[str, Any], broker: Mapping[str, Any]) -> list[str]:
    raw = intent.get("source_receipt_ids")
    if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
            or not raw or any(not isinstance(item, str) or not item for item in raw)):
        raise ValueError("paper_source_receipts_invalid")
    provider_id = broker.get("id")
    if not isinstance(provider_id, str) or not provider_id:
        raise ValueError("paper_provider_receipt_invalid")
    return [*raw, f"alpaca-order:{provider_id}"]


def _validate_strategy_receipt(
    strategy_receipt: Any,
    *,
    broker: Mapping[str, Any],
    side: Any,
    symbol: Any,
    qty: Decimal,
) -> None:
    if not isinstance(strategy_receipt, Mapping):
        raise ValueError("paper_strategy_receipt_missing")
    receipt = strategy_receipt.get("receipt")
    readback = strategy_receipt.get("account_readback")
    if not isinstance(receipt, Mapping) or not isinstance(readback, Mapping):
        raise ValueError("paper_strategy_receipt_missing")
    if receipt.get("owner_id") != OWNER_ID:
        raise ValueError("paper_owner_invalid")
    provider_id = receipt.get("provider_order_id", receipt.get("close_provider_order_id"))
    if provider_id != broker.get("id"):
        raise ValueError("paper_strategy_receipt_mismatch")
    account = readback.get("account")
    clock = readback.get("clock")
    positions = readback.get("positions")
    if not isinstance(account, Mapping) or not isinstance(clock, Mapping) \
            or not isinstance(positions, list):
        raise ValueError("paper_account_readback_invalid")
    _number(account.get("cash"))
    _number(account.get("equity"))
    _timestamp(clock.get("observed_at"))
    matching = [row for row in positions
                if isinstance(row, Mapping) and row.get("symbol") == symbol]
    if side == "buy":
        if len(matching) != 1 or _number(matching[0].get("qty"), positive=True) != qty:
            raise ValueError("paper_account_readback_invalid")
    elif side == "sell":
        if matching:
            raise ValueError("paper_account_readback_invalid")
    else:
        raise ValueError("paper_order_invalid")


def _ledger_rows(rows: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("paper_ledger_invalid")
    intents: dict[str, dict[str, Any]] = {}
    outcomes: dict[str, dict[str, Any]] = {}
    decisions: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("paper_ledger_invalid")
        if row.get("receipt_type") == "decision":
            decision_id = row.get("decision_id")
            decision = row.get("decision")
            if isinstance(decision_id, str) and isinstance(decision, Mapping):
                decisions[decision_id] = dict(decision)
        elif row.get("receipt_type") == "effect_intent":
            effect_id = row.get("effect_id")
            order = row.get("order")
            if not isinstance(effect_id, str) or not effect_id or not isinstance(order, Mapping):
                raise ValueError("paper_intent_invalid")
            if order.get("asset_class") != "us_equity":
                continue
            if (row.get("mode") != "paper" or row.get("paper") is not True
                    or row.get("owner_id") != OWNER_ID or row.get("strategy_id") != STRATEGY_ID):
                raise ValueError("paper_owner_invalid")
            if row.get("effect_id") in intents and row.get("status") == "planned":
                # A duplicate planned row is not an additional effect; the latest
                # status is authoritative for the append-only effect identity.
                continue
            intents[effect_id] = dict(row)
        elif row.get("receipt_type") == "outcome":
            effect_id = row.get("effect_id")
            if not isinstance(effect_id, str) or not effect_id:
                raise ValueError("paper_outcome_invalid")
            # A legacy non-terminal broker outcome can be followed by the
            # terminal official readback in the append-only ledger.  The latest
            # outcome for one effect is authoritative; duplicate provider IDs
            # across different effects remain invalid.
            previous = outcomes.get(effect_id)
            if previous is not None:
                previous_broker = previous.get("broker")
                current_broker = row.get("broker")
                previous_status = previous_broker.get("status") \
                    if isinstance(previous_broker, Mapping) else None
                current_status = current_broker.get("status") \
                    if isinstance(current_broker, Mapping) else None
                if (previous_status not in BROKER_NONTERMINAL_STATUSES
                        or current_status not in ({"filled"} | BROKER_TERMINAL_FAILURE_STATUSES)):
                    raise ValueError("paper_receipt_duplicate")
            outcomes[effect_id] = dict(row)
    provider_ids: set[str] = set()
    for row in outcomes.values():
        broker = row.get("broker")
        if not isinstance(broker, Mapping):
            continue
        provider_id = broker.get("id")
        if isinstance(provider_id, str) and provider_id:
            if provider_id in provider_ids:
                raise ValueError("paper_receipt_duplicate")
            provider_ids.add(provider_id)
    enriched = [
        {**intent, "decision": decisions.get(intent.get("decision_id"), {})}
        for intent in intents.values()
    ]
    return enriched, outcomes


def _execution_slippage(intent: Mapping[str, Any], broker: Mapping[str, Any]) -> Decimal | None:
    decision = intent.get("decision")
    quote = decision.get("execution_quote") if isinstance(decision, Mapping) else None
    if not isinstance(quote, Mapping):
        return None
    try:
        bid = _number(quote.get("bid"), positive=True)
        ask = _number(quote.get("ask"), positive=True)
        fill = _number(broker.get("filled_avg_price"), positive=True)
        qty = _number(broker.get("filled_qty"), positive=True)
    except ValueError:
        return None
    if ask < bid:
        return None
    side = intent.get("order", {}).get("side") if isinstance(intent.get("order"), Mapping) else None
    if side == "buy":
        return max(Decimal("0"), fill - ask) * qty
    if side == "sell":
        return max(Decimal("0"), bid - fill) * qty
    return None


def _model_cost(intent: Mapping[str, Any]) -> Decimal | None:
    decision = intent.get("decision")
    if not isinstance(decision, Mapping) or decision.get("model_cost_source") != "deterministic_etf_policy":
        return None
    try:
        value = _number(decision.get("model_cost_usd"))
    except ValueError:
        return None
    return value if value >= 0 else None


def _closed_round_trips(
    rows: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    intents, outcomes = _ledger_rows(rows)
    source_ids: list[str] = []
    seen_source_ids: set[str] = set()
    completed: list[dict[str, Any]] = []
    events: list[tuple[
        datetime, dict[str, Any], dict[str, Any], Mapping[str, Any], Mapping[str, Any], tuple[str, ...]
    ]] = []

    for intent in intents:
        effect_id = intent["effect_id"]
        outcome = outcomes.get(effect_id)
        if outcome is None:
            raise ValueError("paper_effect_unresolved")
        if outcome.get("mode") != "paper" or outcome.get("paper") is not True:
            raise ValueError("paper_outcome_invalid")
        broker = outcome.get("broker")
        if not isinstance(broker, Mapping):
            raise ValueError("paper_provider_receipt_invalid")
        if outcome.get("outcome") == "broker_terminal_failure":
            continue
        if outcome.get("outcome") != "broker_reconciled":
            raise ValueError("paper_outcome_invalid")
        if broker.get("status") != "filled":
            raise ValueError("paper_effect_unresolved")
        if (broker.get("status") != "filled"
                or broker.get("client_order_id") != intent.get("client_order_id")
                or broker.get("symbol") != intent.get("order", {}).get("symbol")
                or broker.get("side") != intent.get("order", {}).get("side")):
            raise ValueError("paper_fill_invalid")
        timestamp = _timestamp(outcome.get("recorded_at"))
        try:
            filled_qty = _number(broker.get("filled_qty"), positive=True)
        except ValueError as error:
            raise ValueError("paper_fill_invalid") from error
        _validate_strategy_receipt(
            outcome.get("strategy_receipt"), broker=broker,
            side=intent.get("order", {}).get("side"),
            symbol=intent.get("order", {}).get("symbol"), qty=filled_qty,
        )
        ids = _source_ids(intent, broker)
        for receipt_id in ids:
            if receipt_id in seen_source_ids:
                raise ValueError("paper_receipt_duplicate")
            seen_source_ids.add(receipt_id)
            source_ids.append(receipt_id)
        events.append((timestamp, intent, outcome, broker, outcome["strategy_receipt"], tuple(ids)))

    events.sort(key=lambda item: item[0])
    open_positions: dict[str, dict[str, Any]] = {}
    for _timestamp_value, intent, _outcome, broker, _strategy_receipt, event_source_ids in events:
        order = intent["order"]
        symbol = order.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("paper_order_invalid")
        try:
            qty = _number(broker.get("filled_qty"), positive=True)
            price = _number(broker.get("filled_avg_price"), positive=True)
        except ValueError as error:
            raise ValueError("paper_fill_invalid") from error
        side = order.get("side")
        if side == "buy":
            if symbol in open_positions:
                raise ValueError("paper_position_conflict")
            open_positions[symbol] = {
                "qty": qty,
                "price": price,
                "notional": qty * price,
                "intent": intent,
                "broker": broker,
                "source_receipt_ids": list(event_source_ids),
            }
        elif side == "sell":
            entry = open_positions.pop(symbol, None)
            if entry is None or qty != entry["qty"]:
                raise ValueError("paper_exit_without_entry")
            entry_slippage = _execution_slippage(entry["intent"], entry["broker"])
            exit_slippage = _execution_slippage(intent, broker)
            entry_model_cost = _model_cost(entry["intent"])
            exit_model_cost = _model_cost(intent)
            completed.append({
                "gross_pnl_usd": (price - entry["price"]) * qty,
                "exposure_usd": entry["notional"],
                "closed_at": _timestamp_value.isoformat(),
                "client_order_ids": [
                    entry["intent"]["client_order_id"], intent["client_order_id"],
                ],
                "slippage_usd": (entry_slippage + exit_slippage
                                  if entry_slippage is not None and exit_slippage is not None
                                  else None),
                "model_cost_usd": (entry_model_cost + exit_model_cost
                                    if entry_model_cost is not None and exit_model_cost is not None
                                    else None),
                "source_receipt_ids": [*entry["source_receipt_ids"], *event_source_ids],
            })
        else:
            raise ValueError("paper_order_invalid")
    if not completed:
        raise ValueError("paper_round_trip_missing")
    return completed, source_ids


def _cost_complete_metrics(
    completed: Sequence[Mapping[str, Any]], cost_readback: Mapping[str, Any] | None,
) -> dict[str, Decimal] | None:
    if not isinstance(cost_readback, Mapping) or cost_readback.get("status") != "complete":
        return None
    fees = cost_readback.get("fees_by_client_order_id")
    if not isinstance(fees, Mapping):
        return None
    fee_total = Decimal("0")
    slippage_total = Decimal("0")
    model_cost_total = Decimal("0")
    for item in completed:
        client_ids = item.get("client_order_ids")
        if (not isinstance(client_ids, Sequence) or isinstance(client_ids, (str, bytes))
                or len(client_ids) != 2):
            return None
        try:
            if any(client_id not in fees for client_id in client_ids):
                return None
            client_fees = [_number(fees[client_id]) for client_id in client_ids]
            if any(value < 0 for value in client_fees):
                return None
            fee_total += sum(client_fees, Decimal("0"))
        except (KeyError, TypeError, ValueError):
            return None
        slippage = item.get("slippage_usd")
        model_cost = item.get("model_cost_usd")
        if slippage is None or model_cost is None:
            return None
        try:
            slippage_total += _number(slippage)
            model_cost_total += _number(model_cost)
        except ValueError:
            return None
    return {
        "fees_usd": fee_total,
        "slippage_usd": slippage_total,
        "model_cost_usd": model_cost_total,
        "funding_or_borrow_usd": Decimal("0"),
        "gas_usd": Decimal("0"),
    }


def build_paper_performance(
    rows: Any,
    observation: Mapping[str, Any],
    risk: Mapping[str, Any],
    cost_readback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a partial receipt until every paper cost has official evidence."""
    try:
        if not isinstance(observation, Mapping) or not isinstance(risk, Mapping):
            raise ValueError("paper_observation_invalid")
        account = observation.get("account")
        clock = observation.get("clock")
        if not isinstance(account, Mapping) or not isinstance(clock, Mapping):
            raise ValueError("paper_observation_invalid")
        _number(account.get("cash"))
        _number(account.get("equity"))
        observed_at = clock.get("observed_at")
        _timestamp(observed_at)
        completed, source_ids = _closed_round_trips(rows)
        gross = sum((item["gross_pnl_usd"] for item in completed), Decimal("0"))
        exposure = max((item["exposure_usd"] for item in completed), default=Decimal("0"))
        costs = _cost_complete_metrics(completed, cost_readback)
        if costs is not None:
            cost_source_ids = cost_readback.get("source_receipt_ids", [])
            if (not isinstance(cost_source_ids, Sequence)
                    or isinstance(cost_source_ids, (str, bytes))
                    or any(not isinstance(item, str) or not item for item in cost_source_ids)):
                raise ValueError("paper_cost_receipts_invalid")
            net = gross - costs["fees_usd"] - costs["slippage_usd"] - costs["model_cost_usd"]
            return {
                "completed_round_trips": len(completed),
                "completed_round_trips_total": len(completed),
                "costs_status": "complete",
                "fees_usd": _money(costs["fees_usd"]),
                "funding_or_borrow_usd": "0.00",
                "gas_usd": "0.00",
                "gross_exposure_usd": str(exposure),
                "gross_strategy_pnl_usd": str(gross),
                "gross_strategy_pnl_total_usd": str(gross),
                "measurement_status": "measured",
                "mode": "paper",
                "model_cost_usd": _money(costs["model_cost_usd"]),
                "net_pnl_usd": _money(net),
                "observed_at": observed_at,
                "owner_cash_flow_usd": "0.00",
                "paper": True,
                "reason": "paper_cost_complete",
                "risk": dict(risk),
                "schema_version": 1,
                "slippage_usd": _money(costs["slippage_usd"]),
                "source_receipt_ids": [*source_ids, *cost_source_ids],
            }
        return {
            "completed_round_trips": len(completed),
            "completed_round_trips_total": len(completed),
            "costs_status": "unknown",
            "fees_usd": None,
            "funding_or_borrow_usd": None,
            "gas_usd": None,
            "gross_exposure_usd": str(exposure),
            "gross_strategy_pnl_usd": str(gross),
            "gross_strategy_pnl_total_usd": str(gross),
            "measurement_status": "partial",
            "mode": "paper",
            "model_cost_usd": None,
            "observed_at": observed_at,
            "owner_cash_flow_usd": "0.00",
            "paper": True,
            "reason": "paper_costs_unknown",
            "risk": dict(risk),
            "schema_version": 1,
            "slippage_usd": None,
            "source_receipt_ids": source_ids,
        }
    except (TypeError, ValueError, ArithmeticError) as error:
        return _unknown(str(error))


def _read_rows(path: Path) -> list[dict[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("paper_ledger_invalid") from error
    if not all(isinstance(value, dict) for value in values):
        raise ValueError("paper_ledger_invalid")
    return values


def paper_round_trip_client_order_ids(state_dir: str | Path) -> list[str]:
    """Return the client order IDs for completed paper round trips only."""
    rows = _read_rows(Path(state_dir) / "receipts.jsonl")
    try:
        completed, _source_ids = _closed_round_trips(rows)
    except ValueError as error:
        if str(error) in {"paper_effect_unresolved", "paper_round_trip_missing"}:
            return []
        raise
    result: list[str] = []
    for item in completed:
        client_order_ids = item.get("client_order_ids")
        if (not isinstance(client_order_ids, Sequence)
                or isinstance(client_order_ids, (str, bytes))
                or len(client_order_ids) != 2
                or any(not isinstance(value, str) or not value for value in client_order_ids)):
            raise ValueError("paper_client_order_ids_invalid")
        for client_order_id in client_order_ids:
            if client_order_id not in result:
                result.append(client_order_id)
    return result


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def write_paper_performance(
    state_dir: str | Path,
    observation: Mapping[str, Any],
    risk: Mapping[str, Any],
    cost_readback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist only a closed paper measurement; never turn missing costs into zero."""
    state = Path(state_dir)
    try:
        rows = _read_rows(state / "receipts.jsonl")
    except ValueError as error:
        return _unknown(str(error))
    result = build_paper_performance(rows, observation, risk, cost_readback=cost_readback)
    if result.get("measurement_status") in {"partial", "measured"}:
        completed, _source_ids = _closed_round_trips(rows)
        observed_at = result.get("observed_at")
        observation_day = _utc_day(observed_at)
        daily_rounds = [
            item for item in completed
            if _utc_day(item.get("closed_at")) == observation_day
        ]
        daily_gross = sum((item["gross_pnl_usd"] for item in daily_rounds), Decimal("0"))
        daily_exposure = max((item["exposure_usd"] for item in daily_rounds), default=Decimal("0"))
        cumulative_order_ids: list[str] = []
        for item in completed:
            for receipt_id in item.get("source_receipt_ids", []):
                if receipt_id not in cumulative_order_ids:
                    cumulative_order_ids.append(receipt_id)
        account_receipt_id = f"alpaca-account-readback:{observed_at}"
        daily_source_ids = [
            *[receipt_id for item in daily_rounds for receipt_id in item.get("source_receipt_ids", [])],
            account_receipt_id,
        ]
        daily_result = {
            **result,
            "completed_round_trips": len(daily_rounds),
            "completed_round_trips_total": len(completed),
            "gross_exposure_usd": str(daily_exposure),
            "gross_strategy_pnl_usd": str(daily_gross),
            "gross_strategy_pnl_total_usd": result.get("gross_strategy_pnl_usd"),
            "reported_order_receipt_ids": cumulative_order_ids,
            "report_scope": "daily_accumulation",
            "performance_day": observation_day,
            "source_receipt_ids": daily_source_ids,
        }
        if result.get("measurement_status") == "measured":
            daily_costs = _cost_complete_metrics(daily_rounds, cost_readback)
            if daily_costs is None:
                return _unknown("paper_daily_costs_incomplete")
            daily_net = (daily_gross - daily_costs["fees_usd"]
                         - daily_costs["slippage_usd"] - daily_costs["model_cost_usd"])
            daily_result.update({
                "fees_usd": _money(daily_costs["fees_usd"]),
                "funding_or_borrow_usd": "0.00",
                "gas_usd": "0.00",
                "model_cost_usd": _money(daily_costs["model_cost_usd"]),
                "net_pnl_usd": _money(daily_net),
                "slippage_usd": _money(daily_costs["slippage_usd"]),
            })
        result = daily_result
        _atomic_json(state / f"performance-daily-{observation_day}.json", result)
        _atomic_json(state / "performance-latest.json", result)
    return result


__all__ = [
    "build_paper_performance", "paper_round_trip_client_order_ids", "write_paper_performance",
]
