"""Build a read-only paper ETF performance receipt from the effect ledger."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from effect_store import UNRESOLVED_INTENT_STATUSES
from crypto_ownership_proof import BROKER_TERMINAL_FAILURE_STATUSES
from paper_operating_costs import read_readback, select_components, summarize as summarize_operating_costs


OWNER_ID = "alpaca-investment-paper"
STRATEGY_ID = "alpaca-etf-126d-momentum-v1"
BROKER_NONTERMINAL_STATUSES = frozenset({
    "accepted", "accepted_for_bidding", "new", "partially_filled",
    "pending_cancel", "pending_new", "pending_replace", "done_for_day", "stopped", "suspended",
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
    ignored_intents: dict[str, dict[str, Any]] = {}
    outcomes: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("paper_ledger_invalid")
        if row.get("receipt_type") == "effect_intent":
            effect_id = row.get("effect_id")
            order = row.get("order")
            if not isinstance(effect_id, str) or not effect_id:
                raise ValueError("paper_intent_invalid")
            if not isinstance(order, Mapping):
                previous = intents.get(effect_id) or ignored_intents.get(effect_id)
                identity_fields = (
                    "client_order_id", "decision_id", "owner_id", "strategy_id",
                    "decision_session", "source_receipt_ids",
                )
                if (previous is None
                        or row.get("status") not in UNRESOLVED_INTENT_STATUSES
                        or row.get("mode") != previous.get("mode")
                        or row.get("paper") is not previous.get("paper")
                        or any(key in row and row.get(key) != previous.get(key)
                               for key in identity_fields)):
                    raise ValueError("paper_intent_invalid")
                continue
            if order.get("asset_class") != "us_equity":
                ignored_intents[effect_id] = dict(row)
                continue
            if (row.get("mode") != "paper" or row.get("paper") is not True
                    or row.get("owner_id") != OWNER_ID or row.get("strategy_id") != STRATEGY_ID):
                raise ValueError("paper_owner_invalid")
            if row.get("effect_id") in intents and row.get("status") == "planned":
                # A duplicate planned row is not an additional effect; the latest
                # status is authoritative for the append-only effect identity.
                continue
            previous = intents.get(effect_id)
            intents[effect_id] = {
                **dict(row),
                "intent_created_at": (previous.get("intent_created_at")
                                      if previous is not None else row.get("recorded_at")),
            }
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
                same_filled_order = (
                    previous_status == current_status == "filled"
                    and isinstance(previous_broker, Mapping)
                    and isinstance(current_broker, Mapping)
                    and isinstance(previous_broker.get("id"), str)
                    and bool(previous_broker.get("id"))
                    and previous_broker.get("id") == current_broker.get("id")
                    and isinstance(previous_broker.get("client_order_id"), str)
                    and bool(previous_broker.get("client_order_id"))
                    and previous_broker.get("client_order_id")
                    == current_broker.get("client_order_id")
                    and all(previous_broker.get(key) == current_broker.get(key)
                            and previous_broker.get(key) not in (None, "")
                            for key in ("symbol", "side", "filled_qty", "filled_avg_price"))
                )
                if (previous_status not in BROKER_NONTERMINAL_STATUSES
                        or current_status not in ({"filled"} | BROKER_TERMINAL_FAILURE_STATUSES)):
                    if not same_filled_order:
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
            try:
                zero_fill = _number(broker.get("filled_qty")) == 0
            except ValueError:
                zero_fill = False
            if broker.get("status") not in BROKER_TERMINAL_FAILURE_STATUSES or not zero_fill:
                raise ValueError("paper_effect_unresolved")
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
                "orders": [{
                    "id": broker["id"], "symbol": symbol, "side": side,
                    "filled_qty": str(qty), "filled_avg_price": str(price),
                }],
                "period_start": (intent.get("intent_created_at")
                                 if isinstance(intent.get("intent_created_at"), str) else None),
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
                "order_ids": [entry["orders"][0]["id"], broker["id"]],
                "orders": [*entry["orders"], {
                    "id": broker["id"], "symbol": symbol, "side": side,
                    "filled_qty": str(qty), "filled_avg_price": str(price),
                }],
                "period_start": entry["period_start"],
                "source_receipt_ids": [*entry["source_receipt_ids"], *event_source_ids],
            })
        else:
            raise ValueError("paper_order_invalid")
    if not completed:
        raise ValueError("paper_round_trip_missing")
    return completed, source_ids


def _broker_cost_summary(
    completed: Sequence[Mapping[str, Any]], evidence: Any,
) -> dict[str, Any]:
    """Validate paper execution evidence without inventing regulatory fees."""
    unknown = {
        "broker_costs_status": "unknown",
        "broker_costs_reason": "paper_cost_receipt_missing",
        "broker_fees_status": "not_simulated",
        "broker_slippage_status": "unknown",
        "broker_costs_observed_at": None,
        "fees_usd": None,
        "slippage_usd": None,
        "broker_cost_source_receipt_ids": [],
    }
    if (not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes))
            or not completed or len(evidence) != len(completed)):
        return unknown
    by_orders: dict[tuple[str, ...], Mapping[str, Any]] = {}
    try:
        for row in evidence:
            if not isinstance(row, Mapping):
                raise ValueError
            raw_ids = row.get("order_ids")
            if (row.get("provider") != "alpaca"
                    or row.get("broker_costs_status") != "partial"
                    or row.get("broker_slippage_status") != "complete"
                    or row.get("broker_fees_status") != "not_simulated"
                    or row.get("broker_fees_usd") is not None
                    or row.get("broker_costs_reason") != "paper_regulatory_fees_not_simulated"
                    or row.get("owner_id") != OWNER_ID
                    or row.get("mode") != "paper" or row.get("paper") is not True
                    or not isinstance(raw_ids, list) or len(raw_ids) != 2
                    or any(not isinstance(item, str) or not item for item in raw_ids)
                    or len(set(raw_ids)) != 2):
                raise ValueError
            order_key = tuple(sorted(raw_ids))
            if order_key in by_orders:
                raise ValueError
            observed_at = _timestamp(row.get("observed_at"))
            period_start = _timestamp(row.get("period_start"))
            if period_start > observed_at:
                raise ValueError
            receipts = row.get("source_receipt_ids")
            if (not isinstance(receipts, list) or not receipts
                    or any(not isinstance(item, str) or not item for item in receipts)
                    or len(set(receipts)) != len(receipts)):
                raise ValueError
            readback = row.get("provider_readback")
            if not isinstance(readback, Mapping):
                raise ValueError
            fill_rows = readback.get("fills")
            quote_rows = readback.get("quotes_by_fill_id")
            if (not isinstance(fill_rows, list) or not fill_rows
                    or not isinstance(quote_rows, Mapping)):
                raise ValueError
            fill_ids: set[str] = set()
            fills_by_order: dict[str, list[Mapping[str, Any]]] = {key: [] for key in raw_ids}
            readback_gross = Decimal("0")
            readback_slippage = Decimal("0")
            for fill in fill_rows:
                if (not isinstance(fill, Mapping) or fill.get("activity_type") != "FILL"
                        or not isinstance(fill.get("id"), str) or not fill.get("id")
                        or fill.get("order_id") not in fills_by_order
                        or not isinstance(fill.get("symbol"), str) or not fill.get("symbol")
                        or fill.get("side") not in {"buy", "sell"}):
                    raise ValueError
                fill_id = fill["id"]
                if fill_id in fill_ids:
                    raise ValueError
                fill_ids.add(fill_id)
                quantity = _number(fill.get("qty"), positive=True)
                price = _number(fill.get("price"), positive=True)
                filled_at = _timestamp(fill.get("transaction_time"))
                if filled_at < period_start or filled_at > observed_at:
                    raise ValueError
                quote = quote_rows.get(fill_id)
                if not isinstance(quote, Mapping):
                    raise ValueError
                quote_at = _timestamp(quote.get("t"))
                bid = _number(quote.get("bp"), positive=True)
                ask = _number(quote.get("ap"), positive=True)
                quote_age = (filled_at - quote_at).total_seconds()
                if quote_age < 0 or quote_age > 1 or ask < bid:
                    raise ValueError
                midpoint = (bid + ask) / 2
                direction = Decimal("1") if fill["side"] == "sell" else Decimal("-1")
                readback_gross += direction * quantity * price
                readback_slippage += direction * (midpoint - price) * quantity
                fills_by_order[fill["order_id"]].append(fill)
            if fill_ids != set(quote_rows) or any(not fills for fills in fills_by_order.values()):
                raise ValueError
            quote_receipt_ids = {
                f"alpaca-quote:{fill_id}:{quote.get('t')}"
                for fill_id, quote in quote_rows.items() if isinstance(quote, Mapping)
            }
            if set(receipts) != fill_ids | quote_receipt_ids:
                raise ValueError
            gross = _number(row.get("broker_gross_pnl_usd"))
            slippage = _number(row.get("broker_slippage_usd"))
            if (abs(gross - readback_gross) > Decimal("0.000001")
                    or abs(slippage - readback_slippage) > Decimal("0.000001")):
                raise ValueError
            by_orders[order_key] = {
                **dict(row), "_gross": gross, "_slippage": slippage,
                "_receipts": receipts, "_fills_by_order": fills_by_order,
            }
        expected_keys = []
        for trip in completed:
            order_ids = trip.get("order_ids")
            orders = trip.get("orders")
            period_start = trip.get("period_start")
            if (not isinstance(order_ids, list) or len(order_ids) != 2
                    or any(not isinstance(item, str) or not item for item in order_ids)
                    or not isinstance(orders, list) or len(orders) != 2
                    or not isinstance(period_start, str)):
                raise ValueError
            key = tuple(sorted(order_ids))
            row = by_orders.get(key)
            if row is None:
                raise ValueError
            if (len({order.get("id") for order in orders}) != 2
                    or {order.get("id") for order in orders} != set(key)):
                raise ValueError
            for order in orders:
                fills = row["_fills_by_order"][order["id"]]
                if any(fill["symbol"] != order.get("symbol")
                       or fill["side"] != order.get("side") for fill in fills):
                    raise ValueError
                quantity = sum((_number(fill["qty"], positive=True) for fill in fills), Decimal("0"))
                notional = sum((_number(fill["qty"]) * _number(fill["price"])
                                for fill in fills), Decimal("0"))
                if (quantity != _number(order.get("filled_qty"), positive=True)
                        or abs(notional / quantity - _number(order.get("filled_avg_price"), positive=True))
                        > Decimal("0.000001")):
                    raise ValueError
            if (_timestamp(row.get("observed_at")) < _timestamp(trip.get("closed_at"))
                    or _timestamp(row.get("period_start")) != _timestamp(period_start)
                    or abs(row["_gross"] - _number(trip.get("gross_pnl_usd"))) > Decimal("0.000001")):
                raise ValueError
            expected_keys.append(key)
        if set(expected_keys) != set(by_orders):
            raise ValueError
        receipt_ids = [receipt_id for row in by_orders.values() for receipt_id in row["_receipts"]]
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError
        slippage_total = sum((row["_slippage"] for row in by_orders.values()), Decimal("0"))
    except (AttributeError, KeyError, TypeError, ValueError, ArithmeticError):
        return {**unknown, "broker_costs_reason": "paper_cost_receipt_mismatch"}
    return {
        "broker_costs_status": "partial",
        "broker_costs_reason": "paper_regulatory_fees_not_simulated",
        "broker_fees_status": "not_simulated",
        "broker_slippage_status": "complete",
        "broker_costs_observed_at": max(
            by_orders.values(), key=lambda row: _timestamp(row["observed_at"]),
        )["observed_at"],
        "fees_usd": None,
        "slippage_usd": str(slippage_total),
        "broker_cost_source_receipt_ids": receipt_ids,
    }


def build_paper_performance(
    rows: Any,
    observation: Mapping[str, Any],
    risk: Mapping[str, Any],
    *,
    broker_cost_evidence: Any = None,
    operating_cost_readback: Any = None,
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
        broker_costs = _broker_cost_summary(completed, broker_cost_evidence)
        operating_costs = summarize_operating_costs(
            completed, operating_cost_readback, owner_id=OWNER_ID, observed_at=observed_at,
        )
        cost_source_ids = broker_costs["broker_cost_source_receipt_ids"]
        all_source_ids = [*source_ids, *cost_source_ids, *operating_costs["operating_cost_source_receipt_ids"]]
        if len(all_source_ids) != len(set(all_source_ids)):
            raise ValueError("paper_receipt_duplicate")
        unknown_costs = (["fees", "model", "system"] if broker_costs["broker_slippage_status"] == "complete"
                         else ["fees", "slippage", "model", "system"])
        return {
            **operating_costs,
            "completed_round_trips": len(completed),
            "completed_round_trips_total": len(completed),
            "broker_costs_status": broker_costs["broker_costs_status"],
            "broker_costs_reason": broker_costs["broker_costs_reason"],
            "broker_fees_status": broker_costs["broker_fees_status"],
            "broker_slippage_status": broker_costs["broker_slippage_status"],
            "broker_costs_observed_at": broker_costs["broker_costs_observed_at"],
            "broker_costs_errors": [],
            "broker_cost_source_receipt_ids": cost_source_ids,
            "costs_status": ("partial" if broker_costs["broker_slippage_status"] == "complete"
                             or operating_costs["operating_costs_status"] == "partial"
                             else "unknown"),
            "fees_usd": broker_costs["fees_usd"],
            "funding_or_borrow_usd": None,
            "gas_usd": None,
            "gross_exposure_usd": str(exposure),
            "gross_strategy_pnl_usd": str(gross),
            "gross_strategy_pnl_total_usd": str(gross),
            "measurement_status": "partial",
            "mode": "paper",
            "model_cost_usd": None,
            "net_realized_pnl_usd": None,
            "observed_at": observed_at,
            "owner_cash_flow_usd": "0.00",
            "paper": True,
            "reason": "paper_costs_unknown",
            "risk": dict(risk),
            "schema_version": 1,
            "slippage_usd": broker_costs["slippage_usd"],
            "slippage_included_in_gross_pnl": True,
            "source_receipt_ids": all_source_ids,
            "system_cost_usd": None,
            "unknown_cost_categories": unknown_costs,
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


def _broker_cost_cache(
    state: Path,
    completed: Sequence[Mapping[str, Any]],
    observed_at: Any,
    reader: Callable[..., Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(reader, Callable) or not isinstance(observed_at, str):
        return [], []
    try:
        observed = _timestamp(observed_at)
        attempted_day = observed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except ValueError:
        return [], []
    evidence: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for trip in completed:
        order_ids = trip.get("order_ids")
        orders = trip.get("orders")
        period_start = trip.get("period_start")
        if (not isinstance(order_ids, list) or len(order_ids) != 2
                or not isinstance(orders, list) or len(orders) != 2
                or not isinstance(period_start, str)):
            errors.append({
                "next_action": "refresh_owner_bound_period_receipt",
                "order_ids": sorted(order_ids) if isinstance(order_ids, list) else [],
                "reason": "paper_cost_order_period_missing",
            })
            continue
        digest = hashlib.sha256("\0".join(sorted(order_ids)).encode("utf-8")).hexdigest()[:20]
        receipt_path = state / f"performance-cost-{digest}.json"
        attempt_path = state / f"performance-cost-attempt-{digest}.json"
        invalid_cached_receipt = receipt_path.exists()
        try:
            cached = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (isinstance(cached, dict)
                    and sorted(cached.get("order_ids", [])) == sorted(order_ids)):
                cached_summary = _broker_cost_summary([trip], [cached])
                if cached_summary["broker_slippage_status"] == "complete":
                    evidence.append(cached)
                    continue
            invalid_cached_receipt = True
        except (OSError, ValueError, RecursionError, TypeError):
            invalid_cached_receipt = invalid_cached_receipt or receipt_path.exists()
        try:
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            attempt = {}
        attempted_today = (
            isinstance(attempt, Mapping) and attempt.get("attempted_day") == attempted_day
        )
        refresh_invalid_cache = (
            attempted_today
            and invalid_cached_receipt
            and attempt.get("invalid_cached_receipt_refresh_attempted") is not True
        )
        if attempted_today and not refresh_invalid_cache:
            errors.append({
                "next_action": "retry_after_next_et_day",
                "order_ids": sorted(order_ids),
                "reason": attempt.get("reason", "paper_cost_readback_attempted_today"),
            })
            continue
        try:
            _atomic_json(attempt_path, {
                "attempted_at": observed_at, "attempted_day": attempted_day,
                "invalid_cached_receipt_refresh_attempted": invalid_cached_receipt,
                "order_ids": sorted(order_ids), "owner_id": OWNER_ID, "status": "attempted",
            })
        except OSError:
            errors.append({
                "next_action": "defer_until_local_state_is_writable",
                "order_ids": sorted(order_ids),
                "reason": "paper_cost_attempt_receipt_write_failed",
            })
            continue
        try:
            receipt = reader(orders=orders, period_start=period_start)
            if (not isinstance(receipt, Mapping)
                    or sorted(receipt.get("order_ids", [])) != sorted(order_ids)
                    or receipt.get("broker_costs_status") != "partial"
                    or receipt.get("broker_slippage_status") != "complete"):
                raise ValueError("paper_cost_receipt_invalid")
            if (receipt.get("owner_id") not in (None, OWNER_ID)
                    or receipt.get("mode") not in (None, "paper")
                    or (receipt.get("paper") is not None and receipt.get("paper") is not True)):
                raise ValueError("paper_cost_receipt_identity_mismatch")
            normalized = {
                **dict(receipt), "owner_id": OWNER_ID, "mode": "paper", "paper": True,
            }
            if (_broker_cost_summary([trip], [normalized])["broker_slippage_status"]
                    != "complete"):
                raise ValueError("paper_cost_receipt_invalid")
            _atomic_json(receipt_path, normalized)
            evidence.append(normalized)
        except ValueError as error:
            reason = str(error)
            if (not reason.isascii() or not reason.replace("_", "").isalnum()):
                reason = "paper_cost_readback_failed"
            try:
                _atomic_json(attempt_path, {
                    "attempted_at": observed_at, "attempted_day": attempted_day,
                    "invalid_cached_receipt_refresh_attempted": invalid_cached_receipt,
                    "order_ids": sorted(order_ids), "owner_id": OWNER_ID,
                    "reason": reason, "status": "unknown",
                })
            except OSError:
                reason = "paper_cost_attempt_receipt_write_failed"
            errors.append({
                "next_action": "retry_after_next_et_day",
                "order_ids": sorted(order_ids), "reason": reason,
            })
        except OSError:
            errors.append({
                "next_action": "retry_after_next_et_day",
                "order_ids": sorted(order_ids),
                "reason": "paper_cost_receipt_persist_failed",
            })
        except Exception:
            errors.append({
                "next_action": "inspect_paper_cost_readback_adapter",
                "order_ids": sorted(order_ids),
                "reason": "paper_cost_readback_failed",
            })
    return evidence, errors


def _operating_charge_key(component: Mapping[str, Any]) -> tuple[str, ...]:
    key = component.get("charge_identity")
    if (not isinstance(key, list) or len(key) != 5
            or any(not isinstance(value, str) or not value for value in key)):
        raise ValueError("paper_operating_cost_binding_invalid")
    return tuple(key)


def _operating_identity_keys(component: Mapping[str, Any]) -> set[tuple[str, ...]]:
    receipt_id = component.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise ValueError("paper_operating_cost_binding_invalid")
    keys = {("charge", *_operating_charge_key(component)), ("receipt", receipt_id)}
    aliases = component.get("identity_aliases", [])
    if not isinstance(aliases, list):
        raise ValueError("paper_operating_cost_binding_invalid")
    for alias in aliases:
        if (not isinstance(alias, list) or any(not isinstance(value, str) or not value for value in alias)
                or not ((len(alias) == 6 and alias[0] == "charge")
                        or (len(alias) == 2 and alias[0] == "receipt"))):
            raise ValueError("paper_operating_cost_binding_invalid")
        keys.add(tuple(alias))
    return keys


def _bind_operating_costs(state: Path, completed, summary):
    """Keep one paid allocation bound to one trade across readback snapshots."""
    def binding(component):
        return (tuple(component["order_ids"]), _timestamp(component["period_start"]),
                _timestamp(component["period_end"]))

    expected = {binding({"order_ids": trip["order_ids"], "period_start": trip["period_start"],
                         "period_end": trip["closed_at"]}): trip
                for trip in completed if trip.get("period_start")}
    bindings = {}
    alias_sets = {}
    day_keys = {}
    try:
        for path in state.glob("performance-daily-????-??-??.json"):
            previous = json.loads(path.read_text(encoding="utf-8"))
            components = previous.get("operating_cost_components", [])
            if not isinstance(components, list):
                raise ValueError("paper_operating_cost_binding_invalid")
            if not components:
                continue
            day = path.stem.removeprefix("performance-daily-")
            ids = previous.get("source_receipt_ids")
            if (previous.get("mode") != "paper" or previous.get("paper") is not True
                    or previous.get("performance_day") != day
                    or previous.get("report_scope") != "daily_accumulation"
                    or _utc_day(previous.get("observed_at")) != day
                    or not isinstance(ids, list)):
                raise ValueError("paper_operating_cost_binding_invalid")
            for component in components:
                keys, trade = _operating_identity_keys(component), binding(component)
                keys |= {alias for key in keys for alias in alias_sets.get(key, set())}
                trip = expected.get(trade)
                if (trip is None or _utc_day(component["period_end"]) != day
                        or component.get("receipt_id") not in ids
                        or not set(trip["source_receipt_ids"]) <= set(ids)
                        or any(key in bindings and bindings[key] != trade for key in keys)):
                    raise ValueError("paper_operating_cost_binding_invalid")
                for key in keys:
                    bindings[key] = trade
                    alias_sets[key] = keys
                day_keys.setdefault(day, []).append(keys)
        components = summary["operating_cost_components"]
        eligible = []
        for row in components:
            keys = _operating_identity_keys(row)
            if any(key in bindings and bindings[key] != binding(row) for key in keys):
                continue
            keys |= {alias for key in keys for alias in alias_sets.get(key, set())}
            matching = [index for index, prior in enumerate(eligible)
                        if keys & _operating_identity_keys(prior)]
            if matching:
                prior = eligible[matching[0]]
                if (len(matching) != 1 or binding(prior) != binding(row)
                        or prior["category"] != row["category"]
                        or _number(prior["amount_usd"]) != _number(row["amount_usd"])):
                    return select_components({**summary, "operating_cost_components": [],
                        "operating_costs_reason": "operating_cost_identity_conflict"}, completed), day_keys
                keys |= _operating_identity_keys(prior)
                prior["identity_aliases"] = [list(key) for key in sorted(keys)]
            else:
                eligible.append({**row, "identity_aliases": [list(key) for key in sorted(keys)]})
        value = {**summary, "operating_cost_components": eligible}
        if len(eligible) != len(components):
            value["operating_costs_reason"] = "operating_cost_receipt_reassigned"
        return select_components(value, completed), day_keys
    except (OSError, KeyError, AttributeError, TypeError, ValueError, ArithmeticError, RecursionError) as error:
        raise ValueError("paper_operating_cost_binding_unavailable") from error


def _refresh_historical_costs(
    state: Path, completed: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]], current_day: str,
    operating_costs: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Attach late costs to the original day without backdating account observations."""
    results = []
    days = {_utc_day(trip["closed_at"]) for trip in completed}
    for day in sorted(day for day in days if day < current_day):
        trips = [trip for trip in completed if _utc_day(trip["closed_at"]) == day]
        pairs = {tuple(sorted(trip["order_ids"])) for trip in trips}
        day_evidence = [row for row in evidence if tuple(sorted(row["order_ids"])) in pairs]
        costs = _broker_cost_summary(trips, day_evidence)
        day_operating_costs = select_components(dict(operating_costs), trips)
        broker_available = costs["broker_slippage_status"] == "complete"
        operating_available = day_operating_costs["operating_costs_status"] == "partial"
        if not broker_available and not operating_available:
            continue
        path = state / f"performance-daily-{day}.json"
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
            ids = previous.get("source_receipt_ids") if isinstance(previous, Mapping) else None
            old_cost_ids = previous.get("broker_cost_source_receipt_ids", []) if isinstance(previous, Mapping) else None
            old_operating_ids = previous.get("operating_cost_source_receipt_ids", []) if isinstance(previous, Mapping) else None
            required_ids = {value for trip in trips for value in trip["source_receipt_ids"]}
            gross = sum((_number(trip["gross_pnl_usd"]) for trip in trips), Decimal("0"))
            if (not isinstance(previous, Mapping) or previous.get("mode") != "paper"
                    or previous.get("paper") is not True
                    or previous.get("schema_version") != 1
                    or previous.get("measurement_status") != "partial"
                    or not isinstance(previous.get("risk"), Mapping)
                    or previous.get("report_scope") != "daily_accumulation"
                    or previous.get("performance_day") != day
                    or _utc_day(previous.get("observed_at")) != day
                    or previous.get("completed_round_trips") != len(trips)
                    or _number(previous.get("gross_strategy_pnl_usd")) != gross
                    or not isinstance(ids, list) or any(not isinstance(value, str) for value in ids)
                    or not required_ids <= set(ids)
                    or f"alpaca-account-readback:{previous['observed_at']}" not in ids
                    or not isinstance(old_cost_ids, list)
                    or any(not isinstance(value, str) for value in old_cost_ids)
                    or not isinstance(old_operating_ids, list)
                    or any(not isinstance(value, str) for value in old_operating_ids)):
                raise ValueError("paper_historical_performance_mismatch")
            old_operating_keys = [_operating_identity_keys(row)
                                  for row in previous.get("operating_cost_components", [])]
            new_operating_keys = {key for row in day_operating_costs["operating_cost_components"]
                                  for key in _operating_identity_keys(row)}
            operating_available = operating_available and all(keys & new_operating_keys
                                                              for keys in old_operating_keys)
            replaced_ids = set((old_cost_ids if broker_available else [])
                               + (old_operating_ids if operating_available else []))
            updated = {
                **previous,
                **({**costs, "broker_costs_errors": [], "costs_status": "partial",
                    "unknown_cost_categories": ["fees", "model", "system"]} if broker_available else {}),
                **({**day_operating_costs, "costs_status": "partial"} if operating_available else {}),
                "net_realized_pnl_usd": None,
                "source_receipt_ids": list(dict.fromkeys([
                    *[value for value in ids if value not in replaced_ids],
                    *(costs["broker_cost_source_receipt_ids"] if broker_available else []),
                    *(day_operating_costs["operating_cost_source_receipt_ids"] if operating_available else []),
                ])),
            }
            if updated != previous:
                _atomic_json(path, updated)
            results.append({"performance_day": day, "status": "updated" if updated != previous else "unchanged"})
        except (OSError, ValueError, RecursionError, TypeError, ArithmeticError):
            results.append({
                "performance_day": day, "status": "unknown",
                "reason": "paper_historical_performance_unavailable",
                "next_action": "restore_same_day_account_readback",
            })
    return results


def write_paper_performance(
    state_dir: str | Path,
    observation: Mapping[str, Any],
    risk: Mapping[str, Any],
    *,
    broker_cost_reader: Callable[..., Mapping[str, Any]] | None = None,
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
        cost_evidence, cost_errors = _broker_cost_cache(
            state, completed, observed_at, broker_cost_reader,
        )
        result = build_paper_performance(
            rows, observation, risk, broker_cost_evidence=cost_evidence,
            operating_cost_readback=read_readback(
                os.environ.get("LM_CFO_ACTUAL_COST_READBACK") or os.environ.get("LM_CFO_ACTUAL_COST"),
            ),
        )
        try:
            operating_costs, previous_cost_keys = _bind_operating_costs(state, completed, result)
        except ValueError as error:
            return _unknown(str(error))
        result.update(operating_costs)
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
        daily_order_ids = {tuple(sorted(item.get("order_ids", []))) for item in daily_rounds}
        daily_cost_evidence = [
            row for row in cost_evidence
            if (isinstance(row, Mapping)
                and isinstance(row.get("order_ids"), list)
                and len(row["order_ids"]) == 2
                and all(isinstance(order_id, str) and order_id
                        for order_id in row["order_ids"])
                and tuple(sorted(row["order_ids"])) in daily_order_ids)
        ]
        daily_broker_costs = _broker_cost_summary(daily_rounds, daily_cost_evidence)
        daily_operating_costs = select_components(result, daily_rounds)
        incoming_keys = {key for row in daily_operating_costs["operating_cost_components"]
                         for key in _operating_identity_keys(row)}
        if any(not keys & incoming_keys for keys in previous_cost_keys.get(observation_day, [])):
            return _unknown("paper_operating_cost_readback_incomplete")
        daily_cost_source_ids = daily_broker_costs["broker_cost_source_receipt_ids"]
        daily_cost_errors = [
            row for row in cost_errors if tuple(sorted(row.get("order_ids", []))) in daily_order_ids
        ]
        daily_source_ids = [
            *[receipt_id for item in daily_rounds for receipt_id in item.get("source_receipt_ids", [])],
            account_receipt_id,
            *daily_cost_source_ids,
            *daily_operating_costs["operating_cost_source_receipt_ids"],
        ]
        unknown_costs = (["fees", "model", "system"]
                         if daily_broker_costs["broker_slippage_status"] == "complete"
                         else ["fees", "slippage", "model", "system"])
        result = {
            **result,
            **daily_operating_costs,
            "broker_costs_status": daily_broker_costs["broker_costs_status"],
            "broker_fees_status": daily_broker_costs["broker_fees_status"],
            "broker_slippage_status": daily_broker_costs["broker_slippage_status"],
            "broker_costs_observed_at": daily_broker_costs["broker_costs_observed_at"],
            "broker_costs_reason": (
                daily_cost_errors[0]["reason"] if daily_cost_errors
                else daily_broker_costs["broker_costs_reason"]
            ),
            "broker_cost_source_receipt_ids": daily_cost_source_ids,
            "broker_costs_errors": daily_cost_errors,
            "completed_round_trips": len(daily_rounds),
            "completed_round_trips_total": len(completed),
            "costs_status": ("partial" if daily_broker_costs["broker_slippage_status"] == "complete"
                             or daily_operating_costs["operating_costs_status"] == "partial"
                             else "unknown"),
            "fees_usd": daily_broker_costs["fees_usd"],
            "gross_exposure_usd": str(daily_exposure),
            "gross_strategy_pnl_usd": str(daily_gross),
            "gross_strategy_pnl_total_usd": result.get("gross_strategy_pnl_usd"),
            "net_realized_pnl_usd": None,
            "reported_order_receipt_ids": cumulative_order_ids,
            "report_scope": "daily_accumulation",
            "performance_day": observation_day,
            "slippage_usd": daily_broker_costs["slippage_usd"],
            "source_receipt_ids": list(dict.fromkeys(daily_source_ids)),
            "unknown_cost_categories": unknown_costs,
            "historical_cost_reconciliations": _refresh_historical_costs(
                state, completed, cost_evidence, observation_day, result,
            ),
        }
        _atomic_json(state / f"performance-daily-{observation_day}.json", result)
        _atomic_json(state / "performance-latest.json", result)
    return result


__all__ = ["build_paper_performance", "write_paper_performance"]
