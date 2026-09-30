"""Convert subject-scoped canonical FinancialRecords into treasury receipts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import re
from typing import Any


_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CURRENCY = re.compile(r"^[A-Z][A-Z0-9]{2,9}$")
_SUPPORTED_CURRENCY = "USD"
_MAPPED_KINDS = {"business_revenue", "fee"}
_IGNORED_NON_BUSINESS_KINDS = {
    "asset_balance", "liability_balance", "personal_income", "personal_expense",
}
_STATUSES = {"verified", "unverified", "stale"}


def _empty(period: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "period": period,
        "receipts": [],
        "evidence_status": status,
        "reason": reason,
        "missing_sources": [],
        "excluded_currencies": [],
        "unclassified_records": [],
        "ignored_non_business_records": [],
        "zero_observations": [],
        "source_record_ids": [],
    }


def _amount_text(amount_minor: int) -> str:
    value = (Decimal(amount_minor) / Decimal(100)).quantize(Decimal("0.01"))
    return format(value, "f")


def _record_error(row: Any) -> str | None:
    if not isinstance(row, dict):
        return "record_invalid"
    for key in ("record_id", "subject_id", "kind", "currency", "occurred_at", "source", "verification"):
        if not isinstance(row.get(key), str if key in {"record_id", "subject_id", "kind", "currency", "occurred_at"} else dict):
            return f"{key}_invalid"
    if not row["record_id"] or not row["subject_id"] or not row["kind"]:
        return "record_identity_invalid"
    if not _CURRENCY.fullmatch(row["currency"]):
        return "currency_invalid"
    amount_minor = row.get("amount_minor")
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor < 0:
        return "amount_minor_invalid"
    try:
        parsed = datetime.fromisoformat(row["occurred_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "occurred_at_invalid"
    if parsed.tzinfo is None:
        return "occurred_at_timezone_missing"
    provider = row["source"].get("provider")
    if not isinstance(provider, str) or not provider:
        return "source_provider_invalid"
    status = row["verification"].get("status")
    if status not in _STATUSES:
        return "verification_status_invalid"
    return None


def _receipt(row: dict[str, Any]) -> dict[str, Any]:
    kind = row["kind"]
    value: dict[str, Any] = {
        "receipt_id": f"financial-record:{row['record_id']}",
        "category": "customer_revenue" if kind == "business_revenue" else "operating_cost",
        "amount_usd": _amount_text(row["amount_minor"]),
        "status": "verified",
        "source_record_id": row["record_id"],
        "source_provider": row["source"]["provider"],
        "source_kind": kind,
        "currency": row["currency"],
        "source_receipt_ids": [row["record_id"]],
    }
    if kind == "fee":
        value["included_in_investment_net"] = False
    return value


def financial_records_to_treasury_receipts(
    records: Any, subject_id: str, period: str,
) -> dict[str, Any]:
    """Map only verified, subject-scoped USD FinancialRecords.

    The canonical JS store remains the source of truth. This function receives
    its already-read rows so it cannot accidentally select another subject or
    perform provider I/O. It intentionally leaves ambiguous business costs,
    payouts, transfers, taxes, and non-USD assets outside the USD treasury.
    """
    if not isinstance(subject_id, str) or not subject_id:
        return _empty(str(period), "blocked", "subject_id_invalid")
    if not isinstance(period, str) or not _PERIOD.fullmatch(period):
        return _empty(str(period), "blocked", "period_invalid")
    if not isinstance(records, list):
        return _empty(period, "blocked", "records_invalid")

    rows = sorted(records, key=lambda row: row.get("record_id", "") if isinstance(row, dict) else "")
    seen: set[str] = set()
    for row in rows:
        error = _record_error(row)
        if error:
            return _empty(period, "blocked", error)
        record_id = row["record_id"]
        if record_id in seen:
            return _empty(period, "blocked", "duplicate_record_id")
        seen.add(record_id)
        if row["subject_id"] != subject_id:
            return _empty(period, "blocked", "subject_mismatch")

    result = _empty(period, "partial", "receipts_missing")
    in_period = 0
    accepted: list[dict[str, Any]] = []
    accepted_ids: list[str] = []
    for row in rows:
        if row["occurred_at"][:7] != period:
            continue
        in_period += 1
        if row["kind"] in _IGNORED_NON_BUSINESS_KINDS:
            result["ignored_non_business_records"].append(row["record_id"])
            continue
        status = row["verification"]["status"]
        if status != "verified":
            result["missing_sources"].append({
                "record_id": row["record_id"],
                "reason": f"verification_{status}",
            })
            continue
        if row["amount_minor"] == 0:
            result["zero_observations"].append(row["record_id"])
            continue

        kind = row["kind"]
        if kind not in _MAPPED_KINDS:
            result["unclassified_records"].append({
                "record_id": row["record_id"],
                "kind": kind,
                "reason": "treasury_category_not_explicit",
            })
            continue
        if row["currency"] != _SUPPORTED_CURRENCY:
            result["excluded_currencies"].append({
                "record_id": row["record_id"],
                "kind": kind,
                "currency": row["currency"],
                "amount_minor": row["amount_minor"],
                "reason": "currency_not_usd_no_fx",
            })
            continue
        accepted.append(_receipt(row))
        accepted_ids.append(row["record_id"])

    result["receipts"] = accepted
    result["source_record_ids"] = accepted_ids
    if result["missing_sources"] or result["excluded_currencies"] or result["unclassified_records"]:
        result["evidence_status"] = "partial"
        result["reason"] = "financial_record_evidence_incomplete"
    elif accepted:
        result["evidence_status"] = "measured"
        result["reason"] = "measured_financial_records"
    elif in_period:
        result["reason"] = "no_usd_treasury_receipts"
    return result


__all__ = ["financial_records_to_treasury_receipts"]
