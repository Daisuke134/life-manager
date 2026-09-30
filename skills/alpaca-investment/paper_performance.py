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
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("paper_ledger_invalid")
        if row.get("receipt_type") == "effect_intent":
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
    return list(intents.values()), outcomes


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
                "source_receipt_ids": list(event_source_ids),
            }
        elif side == "sell":
            entry = open_positions.pop(symbol, None)
            if entry is None or qty != entry["qty"]:
                raise ValueError("paper_exit_without_entry")
            completed.append({
                "gross_pnl_usd": (price - entry["price"]) * qty,
                "exposure_usd": entry["notional"],
                "closed_at": _timestamp_value.isoformat(),
                "source_receipt_ids": [*entry["source_receipt_ids"], *event_source_ids],
            })
        else:
            raise ValueError("paper_order_invalid")
    if not completed:
        raise ValueError("paper_round_trip_missing")
    return completed, source_ids


def build_paper_performance(
    rows: Any,
    observation: Mapping[str, Any],
    risk: Mapping[str, Any],
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
) -> dict[str, Any]:
    """Persist only a closed paper measurement; never turn missing costs into zero."""
    state = Path(state_dir)
    try:
        rows = _read_rows(state / "receipts.jsonl")
    except ValueError as error:
        return _unknown(str(error))
    result = build_paper_performance(rows, observation, risk)
    if result.get("measurement_status") == "partial":
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
        result = {
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
        _atomic_json(state / f"performance-daily-{observation_day}.json", result)
        _atomic_json(state / "performance-latest.json", result)
    return result


__all__ = ["build_paper_performance", "write_paper_performance"]
