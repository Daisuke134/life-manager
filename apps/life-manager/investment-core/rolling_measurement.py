"""Fail-closed rolling net-P&L measurement over daily investment receipts."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1
WINDOW_DAYS = 30
TARGET_NET_PNL_USD = Decimal("10000.00")
_MONEY = Decimal("0.01")


def _number(value: Any) -> Decimal | None:
    if value is None or value == "unknown" or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _money(value: Decimal) -> str:
    return str(value.quantize(_MONEY, rounding=ROUND_HALF_EVEN))


def _canonical_day(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _base(period_start: date | None, period_end: date | None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "window_days": WINDOW_DAYS,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "days_observed": 0,
        "measurement_status": "blocked",
        "capital_expansion_allowed": False,
        "net_pnl_usd": None,
        "owner_cash_flow_usd": None,
        "target_usd": _money(TARGET_NET_PNL_USD),
        "target_gap_usd": None,
        "source_receipt_ids": [],
    }


def _failure(base: Mapping[str, Any], status: str, reason: str, **extra: Any) -> dict[str, Any]:
    result = dict(base)
    result.update({"measurement_status": status, "reason": reason})
    result.update(extra)
    return result


def rolling_30d(receipts: Iterable[Mapping[str, Any]], end_day: str) -> dict[str, Any]:
    """Calculate a complete UTC 30-day net-P&L window.

    ``receipts`` are already persisted daily report receipts. A day is eligible
    only when the report delivery is confirmed and its aggregate is measured.
    Owner cash flow is returned separately and is never added to net P&L.
    No numeric rolling result is returned for an incomplete or ambiguous window.
    """

    parsed_end = _canonical_day(end_day)
    if parsed_end is None:
        return _failure(_base(None, None), "blocked", "period_end_invalid")
    parsed_start = parsed_end - timedelta(days=WINDOW_DAYS - 1)
    result_base = _base(parsed_start, parsed_end)
    expected_days = [parsed_start + timedelta(days=offset) for offset in range(WINDOW_DAYS)]
    expected = set(expected_days)

    if isinstance(receipts, (str, bytes, Mapping)):
        return _failure(result_base, "blocked", "daily_receipts_invalid")
    try:
        rows = list(receipts)
    except (TypeError, ValueError):
        return _failure(result_base, "blocked", "daily_receipts_invalid")

    by_day: dict[date, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            return _failure(result_base, "blocked", "daily_receipt_invalid")
        day = _canonical_day(row.get("day"))
        if day is None:
            return _failure(result_base, "blocked", "daily_day_invalid")
        if day not in expected:
            continue
        if day in by_day:
            return _failure(result_base, "blocked", "daily_receipt_duplicate", duplicate_day=day.isoformat())
        by_day[day] = row

    missing = [day.isoformat() for day in expected_days if day not in by_day]
    if missing:
        return _failure(
            result_base,
            "unknown",
            "daily_receipt_missing",
            missing_days=missing,
            days_observed=len(by_day),
        )

    net_total = Decimal("0")
    owner_flow_total = Decimal("0")
    source_receipt_ids: list[str] = []
    seen_source_ids: set[str] = set()

    for day in expected_days:
        row = by_day[day]
        if row.get("_load_error"):
            return _failure(
                result_base,
                "blocked",
                str(row.get("_load_error")),
                affected_days=[day.isoformat()],
                days_observed=WINDOW_DAYS,
            )
        if row.get("status") != "delivered":
            return _failure(
                result_base,
                "unknown",
                "daily_receipt_not_delivered",
                affected_days=[day.isoformat()],
                days_observed=WINDOW_DAYS,
            )

        aggregate = row.get("aggregate")
        if not isinstance(aggregate, Mapping):
            return _failure(result_base, "blocked", "daily_aggregate_missing", affected_days=[day.isoformat()])
        if aggregate.get("measurement_status") != "measured":
            return _failure(
                result_base,
                "unknown",
                "daily_measurement_incomplete",
                affected_days=[day.isoformat()],
                days_observed=WINDOW_DAYS,
            )

        net = _number(aggregate.get("net_pnl_usd"))
        if net is None:
            return _failure(result_base, "blocked", "daily_net_pnl_invalid", affected_days=[day.isoformat()])
        owner_flow = _number(aggregate.get("owner_cash_flow_usd"))
        if owner_flow is None:
            return _failure(result_base, "blocked", "daily_owner_cash_flow_invalid", affected_days=[day.isoformat()])

        raw_ids = aggregate.get("source_receipt_ids")
        if not isinstance(raw_ids, (list, tuple)) or not raw_ids:
            return _failure(result_base, "blocked", "source_receipt_missing", affected_days=[day.isoformat()])
        if any(not isinstance(receipt_id, str) or not receipt_id for receipt_id in raw_ids):
            return _failure(result_base, "blocked", "source_receipt_invalid", affected_days=[day.isoformat()])
        if len(set(raw_ids)) != len(raw_ids):
            return _failure(result_base, "blocked", "source_receipt_duplicate", affected_days=[day.isoformat()])
        if any(receipt_id in seen_source_ids for receipt_id in raw_ids):
            return _failure(result_base, "blocked", "source_receipt_duplicate", affected_days=[day.isoformat()])

        net_total += net
        owner_flow_total += owner_flow
        source_receipt_ids.extend(raw_ids)
        seen_source_ids.update(raw_ids)

    target_gap = max(Decimal("0"), TARGET_NET_PNL_USD - net_total)
    return {
        **result_base,
        "measurement_status": "measured",
        "reason": "rolling_measurement_complete",
        "days_observed": WINDOW_DAYS,
        "net_pnl_usd": _money(net_total),
        "owner_cash_flow_usd": _money(owner_flow_total),
        "target_gap_usd": _money(target_gap),
        "source_receipt_ids": source_receipt_ids,
    }


__all__ = ["rolling_30d"]
