"""Read-only adapter for finalized external x402 USDC inflow evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import re
from typing import Any


_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_TX = re.compile(r"^0x[0-9a-fA-F]{64}$")
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_USDC = Decimal("0.000001")


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _empty(period: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "period": period,
        "cash_receipts": [],
        "revenue_usdc": None,
        "outside_period_count": 0,
        "source_receipt_ids": [],
        "evidence_status": status,
        "reason": reason,
    }


def _amount_text(value: Decimal) -> str:
    return format(value.quantize(_USDC, rounding=ROUND_HALF_EVEN), "f")


def _observed_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def x402_inflows_to_cash_receipts(rows: Any, period: str) -> dict[str, Any]:
    """Map verified external inflows to a separate USDC cash ledger.

    The result deliberately has ``amount_usdc`` rather than ``amount_usd`` and
    is not an input to the USD-only treasury rollup. No FX rate is inferred.
    """

    if not isinstance(period, str) or not _PERIOD.fullmatch(period):
        return _empty(str(period), "blocked", "period_invalid")
    if not isinstance(rows, list):
        return _empty(period, "blocked", "rows_invalid")

    parsed: list[tuple[dict[str, Any], Decimal, datetime, str, str]] = []
    seen_txs: set[str] = set()
    seen_sales: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return _empty(period, "blocked", "row_invalid")
        source = row.get("source")
        source_sale_id = row.get("source_sale_id")
        tx = row.get("tx")
        pay_to = row.get("payTo")
        destination = row.get("to")
        sender = row.get("from")
        if not isinstance(source, str) or not source:
            return _empty(period, "blocked", "source_invalid")
        if not isinstance(source_sale_id, str) or not _ID.fullmatch(source_sale_id):
            return _empty(period, "blocked", "source_sale_id_invalid")
        if not isinstance(tx, str) or not _TX.fullmatch(tx):
            return _empty(period, "blocked", "transaction_invalid")
        tx = tx.lower()
        if tx in seen_txs:
            return _empty(period, "blocked", "duplicate_transaction")
        seen_txs.add(tx)
        if source_sale_id in seen_sales:
            return _empty(period, "blocked", "duplicate_source_sale")
        seen_sales.add(source_sale_id)
        if not isinstance(pay_to, str) or not _ADDRESS.fullmatch(pay_to):
            return _empty(period, "blocked", "pay_to_invalid")
        if not isinstance(destination, str) or not _ADDRESS.fullmatch(destination):
            return _empty(period, "blocked", "destination_invalid")
        if destination.lower() != pay_to.lower():
            return _empty(period, "blocked", "pay_to_mismatch")
        if not isinstance(sender, str) or not _ADDRESS.fullmatch(sender):
            return _empty(period, "blocked", "sender_invalid")
        if row.get("finalized") is not True:
            return _empty(period, "blocked", "inflow_not_finalized")
        if row.get("status") != "success":
            return _empty(period, "blocked", "inflow_not_successful")
        if row.get("external") is not True:
            return _empty(period, "blocked", "inflow_not_external")
        amount = _decimal(row.get("usdc"))
        if amount is None or amount <= 0 or amount.quantize(_USDC) != amount:
            return _empty(period, "blocked", "amount_invalid")
        observed = _observed_at(row.get("observed_at"))
        if observed is None:
            return _empty(period, "blocked", "observed_at_invalid")
        parsed.append((row, amount, observed, tx, source_sale_id))

    selected = [item for item in parsed if item[2].strftime("%Y-%m") == period]
    result = _empty(period, "partial", "no_usdc_receipts")
    result["outside_period_count"] = len(parsed) - len(selected)
    if not selected:
        return result

    selected.sort(key=lambda item: (item[2], item[4]))
    receipts = []
    total = Decimal("0")
    source_ids = []
    for row, amount, observed, tx, source_sale_id in selected:
        total += amount
        source_ids.append(tx)
        receipts.append({
            "receipt_id": f"x402-inflow:{source_sale_id}",
            "source_receipt_id": tx,
            "source_sale_id": source_sale_id,
            "source_provider": row["source"],
            "offer_id": row.get("offer_id"),
            "currency": "USDC",
            "amount_usdc": _amount_text(amount),
            "status": "verified",
            "finality": "finalized",
            "external": True,
            "occurred_at": observed.isoformat().replace("+00:00", "Z"),
        })
    result.update({
        "cash_receipts": receipts,
        "revenue_usdc": _amount_text(total),
        "source_receipt_ids": source_ids,
        "evidence_status": "measured",
        "reason": "verified_external_inflows",
    })
    return result


__all__ = ["x402_inflows_to_cash_receipts"]
