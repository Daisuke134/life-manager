"""Read-only fee/model-cost-net P&L adapters for cross-venue allocation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Any, Iterable

from portfolio_performance import aggregate as aggregate_portfolio
from portfolio_receipts import VenueSnapshot
from risk_policy import parse_instant


_MONEY = Decimal("0.01")
_COST_FIELDS = (
    "trading_fees_usd",
    "funding_or_borrow_usd",
    "slippage_usd",
    "gas_usd",
    "model_cost_usd",
)


def _money(value: Decimal) -> str:
    return str(value.quantize(_MONEY, rounding=ROUND_HALF_EVEN))


def _snapshot(value: Any) -> VenueSnapshot:
    if isinstance(value, VenueSnapshot):
        return value
    if isinstance(value, dict):
        return VenueSnapshot.from_mapping(value)
    raise ValueError("snapshot_invalid")


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "capital_expansion_allowed": False,
        "measurement_status": "blocked",
        "reason": reason,
    }


def venue_net(snapshot: Any) -> dict[str, Any]:
    try:
        row = _snapshot(snapshot)
    except (TypeError, ValueError):
        return _blocked("snapshot_invalid")
    reason = row.validation_reason()
    if reason is not None:
        return _blocked(reason)
    net = row.gross_pnl_usd - sum((getattr(row, field) for field in _COST_FIELDS), Decimal("0"))
    return {
        "capital_expansion_allowed": False,
        "venue": row.venue,
        "observed_at": row.observed_at,
        "gross_pnl_usd": _money(row.gross_pnl_usd),
        "trading_fees_usd": _money(row.trading_fees_usd),
        "funding_or_borrow_usd": _money(row.funding_or_borrow_usd),
        "slippage_usd": _money(row.slippage_usd),
        "gas_usd": _money(row.gas_usd),
        "model_cost_usd": _money(row.model_cost_usd),
        "net_pnl_usd": _money(net),
        "source_receipt_ids": list(row.source_receipt_ids),
        "measurement_status": "measured",
        "risk": dict(row.risk),
    }


def aggregate(
    period_start: str,
    observed_at: str,
    snapshots: Iterable[Any],
    owner_cash_flow_usd: Any,
) -> dict[str, Any]:
    try:
        parse_instant(period_start)
        observed = parse_instant(observed_at)
        rows = [_snapshot(value) for value in snapshots]
    except (TypeError, ValueError):
        return _blocked("aggregate_input_invalid")
    if observed is None:
        return _blocked("observation_time_invalid")
    result = aggregate_portfolio(rows, owner_cash_flow_usd, now=observed)
    result = dict(result)
    result["period_start"] = period_start
    result["observed_at"] = observed_at
    if result.get("measurement_status") != "measured":
        return result
    result["venue_rows"] = [venue_net(row) for row in rows]
    return result

