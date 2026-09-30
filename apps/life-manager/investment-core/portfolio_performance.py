"""Pure aggregate net-P&L projection across receipt-verified venues."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Iterable, List, Optional

from portfolio_receipts import VenueSnapshot
from risk_policy import parse_instant


SCHEMA_VERSION = 1
DEFAULT_MAX_AGE_SECONDS = 300
MONEY = Decimal("0.01")


def _number(value: Any) -> Optional[Decimal]:
    if value is None or value == "unknown":
        return None
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _money(value: Decimal) -> str:
    return str(value.quantize(MONEY, rounding=ROUND_HALF_EVEN))


def _blocked(reason: str, *, excluded_venues: Optional[List[str]] = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "capital_expansion_allowed": False,
        "measurement_status": "blocked",
        "reason": reason,
        "schema_version": SCHEMA_VERSION,
    }
    if excluded_venues:
        result["excluded_venues"] = excluded_venues
    return result


def _as_snapshot(value: Any) -> VenueSnapshot:
    if isinstance(value, VenueSnapshot):
        return value
    if isinstance(value, dict):
        return VenueSnapshot.from_mapping(value)
    raise ValueError("snapshot_invalid")


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            return parse_instant(value)
        except (TypeError, ValueError):
            return None
    return None


def aggregate(
    snapshots: Iterable[Any],
    owner_cash_flow_usd: Any,
    *,
    now: Any = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Aggregate measured snapshots without treating deposits as P&L.

    This function only consumes already-read provider evidence. It never imports
    or invokes a venue submit/signing path. Any incomplete, stale, duplicate, or
    non-measured evidence fails closed without returning a numeric net P&L.
    """
    try:
        rows = [_as_snapshot(item) for item in snapshots]
    except (TypeError, ValueError):
        return _blocked("snapshot_invalid")
    if not rows:
        return _blocked("snapshot_missing")
    if not isinstance(max_age_seconds, int) or isinstance(max_age_seconds, bool) or max_age_seconds < 0:
        return _blocked("staleness_policy_invalid")

    owner_flow = _number(owner_cash_flow_usd)
    if owner_flow is None:
        return _blocked("owner_cash_flow_invalid")

    current = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    if current is None:
        return _blocked("observation_time_invalid")

    venues = set()
    seen_receipts = {}
    excluded_venues: List[str] = []
    for snapshot in rows:
        if snapshot.venue in venues:
            return _blocked("venue_duplicate")
        venues.add(snapshot.venue)

        if len(set(snapshot.source_receipt_ids)) != len(snapshot.source_receipt_ids):
            return _blocked("source_receipt_duplicate")
        for receipt_id in snapshot.source_receipt_ids:
            previous_venue = seen_receipts.get(receipt_id)
            if previous_venue is not None:
                return _blocked("source_receipt_cross_venue_duplicate")
            seen_receipts[receipt_id] = snapshot.venue

        reason = snapshot.validation_reason()
        if reason is not None:
            return _blocked(reason)
        observed = _as_utc(snapshot.observed_at)
        if observed is None:
            return _blocked("observation_time_invalid")
        age = (current - observed).total_seconds()
        if age < 0 or age > max_age_seconds:
            excluded_venues.append(snapshot.venue)

    if excluded_venues:
        return _blocked("stale_snapshot", excluded_venues=excluded_venues)

    totals = {
        "equity_usd": sum((snapshot.equity_usd for snapshot in rows), Decimal("0")),
        "free_cash_usd": sum((snapshot.free_cash_usd for snapshot in rows), Decimal("0")),
        "gross_pnl_usd": sum((snapshot.gross_pnl_usd for snapshot in rows), Decimal("0")),
        "trading_fees_usd": sum((snapshot.trading_fees_usd for snapshot in rows), Decimal("0")),
        "funding_or_borrow_usd": sum((snapshot.funding_or_borrow_usd for snapshot in rows), Decimal("0")),
        "slippage_usd": sum((snapshot.slippage_usd for snapshot in rows), Decimal("0")),
        "gas_usd": sum((snapshot.gas_usd for snapshot in rows), Decimal("0")),
        "model_cost_usd": sum((snapshot.model_cost_usd for snapshot in rows), Decimal("0")),
    }
    net = (
        totals["gross_pnl_usd"]
        - totals["trading_fees_usd"]
        - totals["funding_or_borrow_usd"]
        - totals["slippage_usd"]
        - totals["gas_usd"]
        - totals["model_cost_usd"]
    )
    source_receipts = [
        receipt_id
        for snapshot in rows
        for receipt_id in snapshot.source_receipt_ids
    ]
    observed_at = max(snapshot.observed_at for snapshot in rows)
    return {
        "capital_expansion_allowed": False,
        "equity_usd": _money(totals["equity_usd"]),
        "free_cash_usd": _money(totals["free_cash_usd"]),
        "gross_pnl_usd": _money(totals["gross_pnl_usd"]),
        "measurement_status": "measured",
        "model_cost_usd": _money(totals["model_cost_usd"]),
        "net_pnl_usd": _money(net),
        "observed_at": observed_at,
        "owner_cash_flow_usd": _money(owner_flow),
        "reason": "measurement_only",
        "schema_version": SCHEMA_VERSION,
        "source_receipt_ids": source_receipts,
        "trading_fees_usd": _money(totals["trading_fees_usd"]),
        "funding_or_borrow_usd": _money(totals["funding_or_borrow_usd"]),
        "slippage_usd": _money(totals["slippage_usd"]),
        "gas_usd": _money(totals["gas_usd"]),
        "venues": [snapshot.venue for snapshot in rows],
    }
