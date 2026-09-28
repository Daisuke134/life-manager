"""Read-only normalization of venue receipt rows into the canonical snapshot."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable

from portfolio_receipts import VenueSnapshot


_MONEY_FIELDS = (
    "equity_usd",
    "free_cash_usd",
    "gross_pnl_usd",
    "trading_fees_usd",
    "funding_or_borrow_usd",
    "slippage_usd",
    "gas_usd",
    "model_cost_usd",
)
_COST_FIELDS = _MONEY_FIELDS[3:]


def _unknown(reason: str) -> dict[str, str]:
    return {"status": "unknown", "reason": reason}


def _receipt_id(row: dict[str, Any]) -> Any:
    return row.get("receipt_id", row.get("source_receipt_id", row.get("id")))


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("snapshot_time_invalid")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_receipts(venue: str, rows: Iterable[dict[str, Any]]) -> VenueSnapshot | dict[str, str]:
    if not isinstance(venue, str) or not venue:
        return _unknown("venue_unknown")
    try:
        items = list(rows)
    except TypeError:
        return _unknown("receipts_invalid")
    if not items:
        return _unknown("receipts_missing")

    seen: set[str] = set()
    totals = {field_name: Decimal("0") for field_name in _MONEY_FIELDS}
    latest = None
    latest_row = None
    cost_evidence: dict[str, list[str]] = defaultdict(list)
    source_ids: list[str] = []
    try:
        for row in items:
            if not isinstance(row, dict):
                return _unknown("receipt_invalid")
            if row.get("status") == "effect_unknown":
                return _unknown("effect_unknown")
            receipt_id = _receipt_id(row)
            if not isinstance(receipt_id, str) or not receipt_id:
                return _unknown("source_receipt_invalid")
            if receipt_id in seen:
                return _unknown("source_receipt_duplicate")
            seen.add(receipt_id)
            source_ids.append(receipt_id)
            observed = _parse_time(row.get("observed_at"))
            if latest is None or observed > latest:
                latest = observed
                latest_row = row
            for field_name in _MONEY_FIELDS:
                value = row.get(field_name)
                if value is None or value == "unknown":
                    if field_name in _COST_FIELDS:
                        return _unknown("cost_unknown")
                    return _unknown("snapshot_number_unknown")
                if isinstance(value, bool):
                    return _unknown("snapshot_number_invalid")
                amount = Decimal(str(value))
                if not amount.is_finite():
                    return _unknown("snapshot_number_invalid")
                if field_name in _COST_FIELDS and amount < 0:
                    return _unknown("cost_invalid")
                totals[field_name] += amount
                if field_name in _COST_FIELDS:
                    cost_evidence[field_name].append(receipt_id)
    except (ArithmeticError, TypeError, ValueError):
        return _unknown("snapshot_number_invalid")

    assert latest_row is not None
    payload = {
        "venue": venue,
        "observed_at": latest_row["observed_at"],
        "equity_usd": latest_row["equity_usd"],
        "free_cash_usd": latest_row["free_cash_usd"],
        "gross_pnl_usd": totals["gross_pnl_usd"],
        "trading_fees_usd": totals["trading_fees_usd"],
        "funding_or_borrow_usd": totals["funding_or_borrow_usd"],
        "slippage_usd": totals["slippage_usd"],
        "gas_usd": totals["gas_usd"],
        "model_cost_usd": totals["model_cost_usd"],
        "source_receipt_ids": source_ids,
        "risk": latest_row.get("risk"),
        "measurement_status": "measured",
        "cost_evidence": {key: tuple(value) for key, value in cost_evidence.items()},
    }
    try:
        snapshot = VenueSnapshot.from_mapping(payload)
    except ValueError as error:
        return _unknown(str(error))
    reason = snapshot.validation_reason()
    if reason is not None:
        return _unknown(reason)
    return snapshot
