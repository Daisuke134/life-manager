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


OWNER_ID = "alpaca-investment-paper"
STRATEGY_ID = "alpaca-etf-126d-momentum-v1"
INVESTMENT_PRODUCT_LOOP_ID = "investment"
MODEL_SYSTEM_COST_CATEGORIES = frozenset({
    "model_cost", "tool_cost", "browser_cost", "infra_cost",
})
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
                "period_start": (intent.get("recorded_at")
                                 if isinstance(intent.get("recorded_at"), str) else None),
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
    """Accept only broker receipts matching every closed owner order pair."""
    unknown = {
        "broker_costs_status": "unknown",
        "broker_costs_reason": "paper_cost_receipt_missing",
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
                    or row.get("broker_costs_status") != "complete"
                    or not isinstance(raw_ids, list) or len(raw_ids) != 2
                    or any(not isinstance(item, str) or not item for item in raw_ids)):
                raise ValueError
            key = tuple(sorted(raw_ids))
            if key in by_orders:
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
            provider_readback = row.get("provider_readback")
            if not isinstance(provider_readback, Mapping):
                raise ValueError
            fill_rows = provider_readback.get("fills")
            fee_rows = provider_readback.get("fees")
            quote_rows = provider_readback.get("quotes_by_fill_id")
            account_scope = provider_readback.get("account_fill_order_ids_by_symbol_date")
            if (not isinstance(fill_rows, list) or not fill_rows
                    or not isinstance(fee_rows, list) or not fee_rows
                    or not isinstance(quote_rows, Mapping)
                    or not isinstance(account_scope, list) or not account_scope):
                raise ValueError
            fill_ids = set()
            for fill in fill_rows:
                if (not isinstance(fill, Mapping) or fill.get("activity_type") != "FILL"
                        or not isinstance(fill.get("id"), str)
                        or fill.get("order_id") not in raw_ids):
                    raise ValueError
                fill_ids.add(fill["id"])
            if fill_ids != set(quote_rows):
                raise ValueError
            fee_ids = set()
            for fee in fee_rows:
                if (not isinstance(fee, Mapping) or fee.get("activity_type") != "FEE"
                        or not isinstance(fee.get("id"), str)):
                    raise ValueError
                fee_ids.add(fee["id"])
            for scope in account_scope:
                scope_ids = scope.get("order_ids") if isinstance(scope, Mapping) else None
                if (not isinstance(scope_ids, list) or not scope_ids
                        or not set(scope_ids) <= set(raw_ids)):
                    raise ValueError
            quote_receipt_ids = {
                f"alpaca-quote:{fill_id}:{quote.get('t')}"
                for fill_id, quote in quote_rows.items() if isinstance(quote, Mapping)
            }
            if not (fill_ids | fee_ids | quote_receipt_ids) <= set(receipts):
                raise ValueError
            gross = _number(row.get("broker_gross_pnl_usd"))
            fees = _number(row.get("broker_fees_usd"))
            slippage = _number(row.get("broker_slippage_usd"))
            if fees < 0:
                raise ValueError
            by_orders[key] = {
                **dict(row),
                "_gross": gross,
                "_fees": fees,
                "_slippage": slippage,
                "_receipts": receipts,
            }
        expected_keys = []
        for trip in completed:
            order_ids = trip.get("order_ids")
            period_start = trip.get("period_start")
            if (not isinstance(order_ids, list) or len(order_ids) != 2
                    or any(not isinstance(item, str) or not item for item in order_ids)
                    or not isinstance(period_start, str)):
                raise ValueError
            key = tuple(sorted(order_ids))
            row = by_orders.get(key)
            if row is None:
                raise ValueError
            observed_at = _timestamp(row.get("observed_at"))
            closed_at = _timestamp(trip.get("closed_at"))
            if (observed_at < closed_at
                    or _timestamp(row.get("period_start"))
                    != _timestamp(trip.get("period_start"))):
                raise ValueError
            if abs(row["_gross"] - _number(trip.get("gross_pnl_usd"))) > Decimal("0.000001"):
                raise ValueError
            expected_keys.append(key)
        if set(expected_keys) != set(by_orders):
            raise ValueError
        receipt_ids = [receipt_id for row in by_orders.values()
                       for receipt_id in row["_receipts"]]
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError
        fees_total = sum((row["_fees"] for row in by_orders.values()), Decimal("0"))
        slippage_total = sum((row["_slippage"] for row in by_orders.values()), Decimal("0"))
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return {**unknown, "broker_costs_reason": "paper_cost_receipt_mismatch"}
    return {
        "broker_costs_status": "complete",
        "broker_costs_reason": None,
        "fees_usd": str(fees_total),
        "slippage_usd": str(slippage_total),
        "broker_cost_source_receipt_ids": receipt_ids,
    }


def _model_system_cost_summary(
    completed: Sequence[Mapping[str, Any]], evidence: Any, observed_at: Any,
    read_error: str | None = None,
) -> dict[str, Any]:
    """Join verified USD actual-cost receipts to the closed investment period."""
    unknown = {
        "model_system_costs_status": "unknown",
        "model_system_costs_reason": "actual_cost_receipt_missing",
        "model_cost_usd": None,
        "system_cost_usd": None,
        "model_system_cost_source_receipt_ids": [],
    }
    if read_error is not None:
        return {**unknown, "model_system_costs_reason": read_error}
    if (not completed or not isinstance(evidence, Sequence)
            or isinstance(evidence, (str, bytes))):
        return unknown
    try:
        period_start = min(_timestamp(item.get("period_start")) for item in completed)
        period_end = max(_timestamp(item.get("closed_at")) for item in completed)
        snapshot_at = _timestamp(observed_at)
        if period_start >= period_end or snapshot_at < period_end:
            raise ValueError("actual_cost_period_invalid")

        coverage = [
            row for row in evidence
            if isinstance(row, Mapping)
            and row.get("record_type") == "coverage"
            and row.get("product_loop_id") == INVESTMENT_PRODUCT_LOOP_ID
            and row.get("projection") == "trailing"
        ]
        if not coverage:
            raise ValueError("actual_cost_coverage_missing")
        covered_categories: set[str] = set()
        coverage_sources: set[str] = set()
        coverage_receipts: list[str] = []
        for row in coverage:
            source_id = row.get("source_id")
            categories = row.get("covered_categories")
            evidence_refs = row.get("evidence_refs")
            window_start = _timestamp(row.get("window_start"))
            window_end = _timestamp(row.get("window_end"))
            coverage_observed_at = _timestamp(row.get("observed_at"))
            if (row.get("coverage_state") != "complete"
                    or not isinstance(source_id, str)
                    or not source_id.startswith("actual-cost-")
                    or source_id in coverage_sources
                    or not isinstance(categories, list)
                    or any(not isinstance(item, str) for item in categories)
                    or not isinstance(evidence_refs, list) or not evidence_refs
                    or any(not isinstance(item, str) or not item for item in evidence_refs)
                    or window_start > period_start or window_end < period_end
                    or coverage_observed_at < period_end
                    or coverage_observed_at > snapshot_at):
                raise ValueError("actual_cost_coverage_incomplete")
            coverage_sources.add(source_id)
            covered_categories.update(categories)
            coverage_receipts.extend(evidence_refs)
        if not MODEL_SYSTEM_COST_CATEGORIES <= covered_categories:
            raise ValueError("actual_cost_categories_incomplete")

        model_total = Decimal("0")
        system_total = Decimal("0")
        receipt_ids: list[str] = []
        seen_receipt_ids: set[str] = set()
        for row in evidence:
            if not isinstance(row, Mapping) or row.get("product_loop_id") != INVESTMENT_PRODUCT_LOOP_ID:
                continue
            if row.get("record_type") != "receipt":
                continue
            receipt_id = row.get("receipt_id")
            occurred_at = _timestamp(row.get("occurred_at"))
            settled_at = _timestamp(row.get("settled_at"))
            components = row.get("components")
            evidence_refs = row.get("evidence_refs")
            if (not isinstance(receipt_id, str) or not receipt_id
                    or receipt_id in seen_receipt_ids
                    or row.get("verification_state") != "verified"
                    or row.get("currency") != "USD"
                    or settled_at < occurred_at or settled_at > snapshot_at
                    or not isinstance(components, list) or not components
                    or not isinstance(evidence_refs, list) or not evidence_refs
                    or any(not isinstance(item, str) or not item for item in evidence_refs)):
                raise ValueError("actual_cost_receipt_invalid")
            seen_receipt_ids.add(receipt_id)
            amounts: list[tuple[str, Decimal]] = []
            for component in components:
                if not isinstance(component, Mapping):
                    raise ValueError("actual_cost_receipt_invalid")
                category = component.get("category")
                amount = _number(component.get("amount"), positive=True)
                if category not in MODEL_SYSTEM_COST_CATEGORIES:
                    raise ValueError("actual_cost_receipt_invalid")
                amounts.append((category, amount))
            if period_start <= occurred_at <= period_end:
                for category, amount in amounts:
                    if category == "model_cost":
                        model_total += amount
                    else:
                        system_total += amount
                receipt_ids.extend([receipt_id, *evidence_refs])

        def money_text(amount: Decimal) -> str:
            value = format(amount, "f")
            return value.rstrip("0").rstrip(".") if "." in value else value

        source_ids = list(dict.fromkeys([*coverage_receipts, *receipt_ids]))
        if not source_ids:
            raise ValueError("actual_cost_evidence_missing")
        return {
            "model_system_costs_status": "complete",
            "model_system_costs_reason": None,
            "model_cost_usd": money_text(model_total),
            "system_cost_usd": money_text(system_total),
            "model_system_cost_source_receipt_ids": source_ids,
        }
    except (ArithmeticError, KeyError, TypeError, ValueError) as error:
        reason = str(error)
        if not reason.isascii() or not reason.replace("_", "").isalnum():
            reason = "actual_cost_receipt_invalid"
        return {**unknown, "model_system_costs_reason": reason}


def build_paper_performance(
    rows: Any,
    observation: Mapping[str, Any],
    risk: Mapping[str, Any],
    *,
    broker_cost_evidence: Any = None,
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
        cost_source_ids = broker_costs["broker_cost_source_receipt_ids"]
        all_source_ids = [*source_ids, *cost_source_ids]
        if len(all_source_ids) != len(set(all_source_ids)):
            raise ValueError("paper_receipt_duplicate")
        unknown_costs = (["model", "system"] if broker_costs["broker_costs_status"] == "complete"
                         else ["fees", "slippage", "model", "system"])
        return {
            "completed_round_trips": len(completed),
            "completed_round_trips_total": len(completed),
            "broker_costs_status": broker_costs["broker_costs_status"],
            "broker_costs_reason": broker_costs["broker_costs_reason"],
            "broker_costs_errors": [],
            "broker_cost_source_receipt_ids": cost_source_ids,
            "costs_status": ("partial" if broker_costs["broker_costs_status"] == "complete"
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
        try:
            cached = json.loads(receipt_path.read_text(encoding="utf-8"))
            if (isinstance(cached, dict)
                    and sorted(cached.get("order_ids", [])) == sorted(order_ids)):
                evidence.append(cached)
                continue
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        try:
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            attempt = {}
        if isinstance(attempt, Mapping) and attempt.get("attempted_day") == attempted_day:
            errors.append({
                "next_action": "retry_after_next_et_day",
                "order_ids": sorted(order_ids),
                "reason": attempt.get("reason", "paper_cost_readback_attempted_today"),
            })
            continue
        try:
            _atomic_json(attempt_path, {
                "attempted_at": observed_at, "attempted_day": attempted_day,
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
                    or receipt.get("broker_costs_status") != "complete"):
                raise ValueError("paper_cost_receipt_invalid")
            normalized = dict(receipt)
            _atomic_json(receipt_path, normalized)
            evidence.append(normalized)
        except ValueError as error:
            reason = str(error)
            if (not reason.isascii() or not reason.replace("_", "").isalnum()):
                reason = "paper_cost_readback_failed"
            try:
                _atomic_json(attempt_path, {
                    "attempted_at": observed_at, "attempted_day": attempted_day,
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


def write_paper_performance(
    state_dir: str | Path,
    observation: Mapping[str, Any],
    risk: Mapping[str, Any],
    *,
    broker_cost_reader: Callable[..., Mapping[str, Any]] | None = None,
    model_system_cost_reader: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
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
        )
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
        daily_cost_source_ids = daily_broker_costs["broker_cost_source_receipt_ids"]
        daily_period_start = min(
            (item["period_start"] for item in daily_rounds
             if isinstance(item.get("period_start"), str)),
            default=None,
        )
        daily_period_end = max(
            (item["closed_at"] for item in daily_rounds
             if isinstance(item.get("closed_at"), str)),
            default=None,
        )
        model_system_evidence = None
        model_system_read_error = None
        if isinstance(model_system_cost_reader, Callable) and daily_period_start and daily_period_end:
            try:
                model_system_evidence = model_system_cost_reader(
                    period_start=daily_period_start, period_end=daily_period_end,
                    observed_at=observed_at,
                )
            except ValueError as error:
                reason = str(error)
                model_system_read_error = (
                    reason if reason.isascii() and reason.replace("_", "").isalnum()
                    else "actual_cost_readback_failed"
                )
            except Exception:
                model_system_read_error = "actual_cost_readback_failed"
        elif not isinstance(model_system_cost_reader, Callable):
            model_system_read_error = "actual_cost_reader_unavailable"
        daily_model_system_costs = _model_system_cost_summary(
            daily_rounds, model_system_evidence, observed_at, model_system_read_error,
        )
        daily_model_system_source_ids = daily_model_system_costs[
            "model_system_cost_source_receipt_ids"
        ]
        daily_cost_errors = [
            row for row in cost_errors if tuple(sorted(row.get("order_ids", []))) in daily_order_ids
        ]
        daily_source_ids = [
            *[receipt_id for item in daily_rounds for receipt_id in item.get("source_receipt_ids", [])],
            account_receipt_id,
            *daily_cost_source_ids,
            *daily_model_system_source_ids,
        ]
        broker_costs_complete = daily_broker_costs["broker_costs_status"] == "complete"
        model_system_costs_complete = (
            daily_model_system_costs["model_system_costs_status"] == "complete"
        )
        unknown_costs = ([] if model_system_costs_complete else ["model", "system"])
        if not broker_costs_complete:
            unknown_costs = ["fees", "slippage", *unknown_costs]
        net_realized = None
        if broker_costs_complete and model_system_costs_complete:
            net_realized = str(
                daily_gross
                - Decimal(daily_broker_costs["fees_usd"])
                - Decimal(daily_model_system_costs["model_cost_usd"])
                - Decimal(daily_model_system_costs["system_cost_usd"])
            )
        costs_status = (
            "complete" if broker_costs_complete and model_system_costs_complete
            else "partial" if broker_costs_complete or model_system_costs_complete
            else "unknown"
        )
        measurement_status = (
            "complete" if broker_costs_complete and model_system_costs_complete else "partial"
        )
        result = {
            **result,
            "broker_costs_reason": (
                daily_cost_errors[0]["reason"] if daily_cost_errors
                else daily_broker_costs["broker_costs_reason"]
            ),
            "broker_cost_source_receipt_ids": daily_cost_source_ids,
            "broker_costs_errors": daily_cost_errors,
            "completed_round_trips": len(daily_rounds),
            "completed_round_trips_total": len(completed),
            "costs_status": costs_status,
            "fees_usd": daily_broker_costs["fees_usd"],
            "gross_exposure_usd": str(daily_exposure),
            "gross_strategy_pnl_usd": str(daily_gross),
            "gross_strategy_pnl_total_usd": result.get("gross_strategy_pnl_usd"),
            "measurement_status": measurement_status,
            "model_cost_usd": daily_model_system_costs["model_cost_usd"],
            "model_system_costs_reason": daily_model_system_costs["model_system_costs_reason"],
            "model_system_costs_status": daily_model_system_costs["model_system_costs_status"],
            "model_system_cost_source_receipt_ids": daily_model_system_source_ids,
            "net_realized_pnl_usd": net_realized,
            "reason": None if measurement_status == "complete" else "paper_costs_unknown",
            "reported_order_receipt_ids": cumulative_order_ids,
            "report_scope": "daily_accumulation",
            "performance_day": observation_day,
            "slippage_usd": daily_broker_costs["slippage_usd"],
            "source_receipt_ids": list(dict.fromkeys(daily_source_ids)),
            "system_cost_usd": daily_model_system_costs["system_cost_usd"],
            "unknown_cost_categories": unknown_costs,
        }
        _atomic_json(state / f"performance-daily-{observation_day}.json", result)
        _atomic_json(state / "performance-latest.json", result)
    return result


__all__ = ["build_paper_performance", "write_paper_performance"]
