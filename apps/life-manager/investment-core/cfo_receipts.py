"""Convert the existing read-only CFO table into treasury receipt rows."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any


_KINDS = ("revenue", "refund", "cost")
_CATEGORIES = {
    "revenue": "customer_revenue",
    "refund": "customer_refund",
    "cost": "operating_cost",
}
_SUPPORTED_CURRENCY = "USD"


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _amount_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _empty(period: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "period": period,
        "receipts": [],
        "evidence_status": status,
        "reason": reason,
        "missing_sources": [],
        "excluded_currencies": [],
        "excluded_investment_rows": [],
        "zero_observations": [],
        "source_receipt_ids": [],
    }


def _cell_error(cell: Any) -> str | None:
    if not isinstance(cell, dict):
        return "cell_invalid"
    if cell.get("status") not in {"verified", "zero", "unverified"}:
        return "cell_status_invalid"
    amounts = cell.get("amounts")
    if not isinstance(amounts, dict):
        return "cell_amounts_invalid"
    receipts = cell.get("receipts")
    if not isinstance(receipts, list) or any(not isinstance(item, str) or not item for item in receipts):
        return "cell_receipts_invalid"
    if len(receipts) != len(set(receipts)):
        return "duplicate_source_receipt_id"
    incomplete = cell.get("incomplete", 0)
    if isinstance(incomplete, bool) or not isinstance(incomplete, int) or incomplete < 0:
        return "cell_incomplete_invalid"
    for currency, value in amounts.items():
        if not isinstance(currency, str) or not currency:
            return "currency_invalid"
        amount = _decimal(value)
        if amount is None or amount < 0:
            return "amount_invalid"
    return None


def _missing(loop_id: str, kind: str, reason: str) -> dict[str, str]:
    return {"loop_id": loop_id, "kind": kind, "reason": reason}


def _source_error(source: Any) -> dict[str, str] | None:
    if not isinstance(source, dict):
        return {"source": "unknown", "kind": "source", "reason": "source_invalid"}
    name = source.get("name")
    if not isinstance(name, str) or not name:
        return {"source": "unknown", "kind": "source", "reason": "source_name_invalid"}
    if source.get("ok") is False:
        error = source.get("error")
        return {"source": name, "kind": "source", "reason": str(error or "source_failed")}
    return None


def _aggregate_receipt(period: str, loop_id: str, kind: str, currency: str,
                       amount: Decimal, source_ids: list[str]) -> dict[str, Any]:
    seed = "\n".join([period, loop_id, kind, currency, *sorted(source_ids)])
    digest = sha256(seed.encode()).hexdigest()[:24]
    value: dict[str, Any] = {
        "receipt_id": f"cfo:{period}:{loop_id}:{kind}:{currency}:{digest}",
        "category": _CATEGORIES[kind],
        "amount_usd": _amount_text(amount),
        "status": "verified",
        "source_loop_id": loop_id,
        "source_kind": kind,
        "currency": currency,
        "source_receipt_ids": list(source_ids),
    }
    if kind == "cost":
        value["included_in_investment_net"] = False
    return value


def cfo_table_to_treasury_receipts(table: Any, period: str | None = None) -> dict[str, Any]:
    """Map receipt-backed USD cells from ``skills/cfo/loop_pnl.py``.

    The CFO table is an observation table, not a ledger. The adapter therefore
    emits one deterministic aggregate receipt per loop/kind/currency cell and
    preserves the provider receipt IDs inside that row. Investment P&L, owner
    cash flow, non-USD amounts, and API-price estimates stay outside this
    customer-cash boundary.
    """
    chosen_period = period if period is not None else table.get("reporting_date") if isinstance(table, dict) else ""
    if not isinstance(chosen_period, str) or not chosen_period:
        return _empty(str(chosen_period), "blocked", "period_invalid")
    if not isinstance(table, dict):
        return _empty(chosen_period, "blocked", "table_invalid")
    if not isinstance(table.get("reporting_date"), str) or not table["reporting_date"]:
        return _empty(chosen_period, "blocked", "reporting_date_invalid")
    if not isinstance(table.get("sources"), list):
        return _empty(chosen_period, "blocked", "sources_invalid")
    rows = table.get("rows")
    if not isinstance(rows, list):
        return _empty(chosen_period, "blocked", "rows_invalid")

    result = _empty(chosen_period, "measured", "mapped_cfo_table")
    for source in table["sources"]:
        error = _source_error(source)
        if error:
            result["missing_sources"].append(error)

    by_loop: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("loop_id"), str) or not row["loop_id"]:
            return _empty(chosen_period, "blocked", "row_invalid")
        loop_id = row["loop_id"]
        if loop_id in by_loop:
            return _empty(chosen_period, "blocked", "duplicate_loop_id")
        by_loop[loop_id] = row

    accepted_source_ids: list[str] = []
    for loop_id in sorted(by_loop):
        row = by_loop[loop_id]
        for kind in _KINDS:
            cell = row.get(kind)
            error = _cell_error(cell)
            if error:
                return _empty(chosen_period, "blocked", error)
            if loop_id == "investment":
                if cell["status"] != "zero" and (cell["amounts"] or cell["receipts"]):
                    result["excluded_investment_rows"].append(f"investment:{kind}")
                continue

            status = cell["status"]
            if status == "unverified":
                result["missing_sources"].append(
                    _missing(loop_id, kind, str(cell.get("reason") or "cell_unverified")))
                continue
            incomplete = cell.get("incomplete", 0)
            if incomplete:
                reason = "incomplete_cost_evidence" if kind == "cost" else "incomplete_cell_evidence"
                result["missing_sources"].append(
                    _missing(loop_id, kind, f"{reason}:{incomplete}"))
                continue
            if status == "zero":
                if cell["amounts"] or cell["receipts"]:
                    return _empty(chosen_period, "blocked", "zero_cell_has_amount_or_receipt")
                result["zero_observations"].append({
                    "loop_id": loop_id,
                    "kind": kind,
                    "sources": list(cell.get("sources") or []),
                })
                continue

            if not cell["receipts"] and any(_decimal(value) for value in cell["amounts"].values()):
                result["missing_sources"].append(_missing(loop_id, kind, "verified_without_receipt"))
                continue
            for currency, raw_amount in sorted(cell["amounts"].items()):
                amount = _decimal(raw_amount)
                assert amount is not None  # validated by _cell_error above
                if amount == 0:
                    continue
                if currency != _SUPPORTED_CURRENCY:
                    result["excluded_currencies"].append({
                        "loop_id": loop_id,
                        "source_kind": kind,
                        "currency": currency,
                        "amount": _amount_text(amount),
                        "reason": "currency_not_usd_no_fx",
                    })
                    continue
                if not cell["receipts"]:
                    result["missing_sources"].append(_missing(loop_id, kind, "usd_without_receipt"))
                    continue
                result["receipts"].append(
                    _aggregate_receipt(chosen_period, loop_id, kind, currency, amount, cell["receipts"])
                )
                for source_id in cell["receipts"]:
                    if source_id not in accepted_source_ids:
                        accepted_source_ids.append(source_id)

    result["excluded_investment_rows"] = sorted(set(result["excluded_investment_rows"]))
    result["source_receipt_ids"] = accepted_source_ids
    if result["missing_sources"] or result["excluded_currencies"]:
        result["evidence_status"] = "partial"
        result["reason"] = "source_evidence_incomplete"
    return result


__all__ = ["cfo_table_to_treasury_receipts"]
