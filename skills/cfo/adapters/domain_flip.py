"""Fail-closed B0 attribution for verified .si domain sales and measured costs."""

from __future__ import annotations

import importlib.util
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from skills.cfo import economic_attribution as contract


CORE_PATH = Path(__file__).resolve().parents[2] / "domain-flip" / "core.py"
CORE_SPEC = importlib.util.spec_from_file_location("domain_flip_cfo_core", CORE_PATH)
if CORE_SPEC is None or CORE_SPEC.loader is None:
    raise ImportError("domain_flip_core_unavailable")
domain_flip_core = importlib.util.module_from_spec(CORE_SPEC)
CORE_SPEC.loader.exec_module(domain_flip_core)

_COST_CATEGORIES = {
    "refund": contract.REFUND,
    "registration": "other_measured_cost",
    "renewal": "other_measured_cost",
    "transfer": "other_measured_cost",
    "tax": "other_measured_cost",
    "other_measured_cost": "other_measured_cost",
    "marketplace_fee": "provider_fee",
    "provider_fee": "provider_fee",
    "payment_fee": "payment_fee",
    "payout_fee": "payment_fee",
    "fx_fee": "payment_fee",
    "model_cost": "model_cost",
    "tool_cost": "tool_cost",
    "browser_cost": "browser_cost",
    "infra_cost": "infra_cost",
}
_PAYOUT_DEDUCTION_CATEGORIES = {"marketplace_fee", "provider_fee", "payout_fee", "payment_fee"}
_SALE_PROVIDERS = {
    "buyer_settlement": {"sedo"},
    "holder_transfer": {"register-si", "openprovider"},
    "seller_payout": {"sedo"},
    "receiving_account_credit": {"bank"},
}
_DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.si$")


def _instant(value: Any) -> str:
    if not isinstance(value, str) or not contract.RFC3339.fullmatch(value):
        raise ValueError("read_failed")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("read_failed")
        return instant.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
    except (ValueError, OverflowError) as error:
        raise ValueError("read_failed") from error


def _amount(value: Any) -> tuple[Decimal, str]:
    if isinstance(value, bool):
        raise ValueError("unverified_receipt")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("unverified_receipt") from error
    if not amount.is_finite() or amount <= 0:
        raise ValueError("unverified_receipt")
    text = format(amount.normalize(), "f")
    if not contract.AMOUNT.fullmatch(text):
        raise ValueError("unverified_receipt")
    return amount, text


def _refs(value: Any) -> list[str]:
    if (not isinstance(value, list) or not value
            or not all(isinstance(ref, str) and contract.EVIDENCE.fullmatch(ref) for ref in value)):
        raise ValueError("unverified_receipt")
    return sorted(set(value))


def _domain(value: Any) -> str:
    if not isinstance(value, str) or not _DOMAIN.fullmatch(value):
        raise ValueError("unverified_receipt")
    return value


def _unique_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("unverified_receipt")
        provider, receipt_id = row.get("provider"), row.get("receipt_id")
        if (not isinstance(provider, str) or not contract.NAME.fullmatch(provider)
                or not isinstance(receipt_id, str) or not contract.IDENTITY.fullmatch(receipt_id)):
            raise ValueError("unverified_receipt")
        key = (provider, receipt_id)
        if key in unique and unique[key] != row:
            raise ValueError("unverified_receipt")
        unique[key] = row
    return list(unique.values())


def _complete_sale_proof(
    receipts: list[dict[str, Any]], snapshot: str,
) -> tuple[str, str, list[str], str]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in receipts:
        if row.get("verified") is True:
            receipt_type = row.get("type")
            if receipt_type in _SALE_PROVIDERS:
                by_type.setdefault(receipt_type, []).append(row)
    if any(not by_type.get(receipt_type) for receipt_type in _SALE_PROVIDERS):
        raise ValueError("missing_coverage")

    sale_ids: set[str] = set()
    domains: set[str] = set()
    proof_refs: set[str] = set()
    settled_at: list[str] = []
    for receipt_type, providers in _SALE_PROVIDERS.items():
        for row in by_type[receipt_type]:
            provider, receipt_id = row.get("provider"), row.get("receipt_id")
            sale_id = row.get("sale_id")
            if (provider not in providers or not isinstance(receipt_id, str)
                    or not contract.IDENTITY.fullmatch(receipt_id)
                    or not isinstance(sale_id, str) or not contract.IDENTITY.fullmatch(sale_id)
                    or row.get("currency", "EUR") != "EUR"):
                raise ValueError("unverified_receipt")
            sale_ids.add(sale_id)
            occurred, settled = _instant(row.get("occurred_at")), _instant(row.get("settled_at"))
            if settled < occurred or settled >= snapshot:
                raise ValueError("unverified_receipt")
            settled_at.append(settled)
            proof_refs.update(_refs(row.get("evidence_refs")))
            domain = row.get("domain")
            if domain is not None:
                domains.add(_domain(domain))
            if receipt_type in {"buyer_settlement", "seller_payout", "receiving_account_credit"}:
                _amount(row.get("amount_eur"))
            if receipt_type == "holder_transfer" and row.get("new_holder_verified") is not True:
                raise ValueError("unverified_receipt")

    if len(sale_ids) != 1 or len(domains) != 1:
        raise ValueError("unverified_receipt")
    sale_id = next(iter(sale_ids))
    domain = next(iter(domains))
    if any(row.get("domain") not in {None, domain}
           for rows in by_type.values() for row in rows):
        raise ValueError("unverified_receipt")
    # Recognize gross revenue only when the last required proof has settled.
    recognized_at = max(settled_at)
    return sale_id, domain, sorted(proof_refs), recognized_at


def _receipt(
    *, receipt_id: str, provider: str, amount: Decimal, category: str,
    occurred_at: str, settled_at: str, evidence_refs: list[str], revenue: bool = False,
) -> dict:
    _, amount_text = _amount(amount)
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "receipt",
        "receipt_id": receipt_id,
        "product_loop_id": "domain-flip",
        "provider": provider,
        "currency": "EUR",
        "occurred_at": occurred_at,
        "settled_at": settled_at,
        "verification_state": "verified",
        "revenue_class": "one_time" if revenue else None,
        "evidence_refs": evidence_refs,
        "components": [{
            "category": contract.REVENUE if revenue else category,
            "amount": amount_text,
        }],
    })


def _coverage(
    *, projection: str, start: str | None, end: str, state: str,
    reason: str | None, categories: list[str], evidence_refs: list[str],
) -> dict:
    return contract.validate_record({
        "schema_version": contract.SCHEMA_VERSION,
        "record_type": "coverage",
        "product_loop_id": "domain-flip",
        "source_id": "domain-flip-financial-record",
        "projection": projection,
        "window_start": start,
        "window_end": end,
        "coverage_state": state,
        "reason": reason,
        "covered_categories": sorted(set(categories)),
        "observed_at": end,
        "evidence_refs": evidence_refs,
    })


def adapt_sale(
    receipts: list[dict[str, Any]],
    costs: dict[str, Any],
    *,
    snapshot_at: str,
    trailing_start: str,
) -> list[dict]:
    """Emit validated B0 rows; incomplete sale evidence yields explicit gaps."""
    try:
        snapshot = _instant(snapshot_at)
        start = _instant(trailing_start)
        if start >= snapshot:
            raise ValueError("read_failed")
    except ValueError:
        return []

    evidence_refs: set[str] = set()
    failure = "missing_coverage"
    cost_records: list[dict] = []
    cost_categories: set[str] = set()
    unique_cost_rows: list[dict[str, Any]] = []
    costs_complete = (
        isinstance(costs, dict)
        and costs.get("coverage_state") == "complete"
        and isinstance(costs.get("items"), list)
        and bool(costs.get("items"))
    )
    covered_categories = costs.get("covered_categories") if isinstance(costs, dict) else None
    if (not isinstance(covered_categories, list)
            or len(set(covered_categories)) != len(covered_categories)
            or not set(contract.COUNTED_CATEGORIES).issubset(covered_categories)
            or any(category not in contract.COUNTED_CATEGORIES for category in covered_categories)):
        costs_complete = False
        failure = "missing_category"
    if isinstance(costs, dict):
        try:
            evidence_refs.update(_refs(costs.get("evidence_refs")))
        except ValueError:
            costs_complete = False
    if costs_complete:
        seen_costs: dict[tuple[str, str], dict] = {}
        for row in costs["items"]:
            if not isinstance(row, dict):
                costs_complete = False
                failure = "unverified_receipt"
                continue
            try:
                provider, receipt_id = row.get("provider"), row.get("receipt_id")
                if (not isinstance(provider, str) or not contract.NAME.fullmatch(provider)
                        or not isinstance(receipt_id, str) or not contract.IDENTITY.fullmatch(receipt_id)
                        or row.get("verified") is not True):
                    raise ValueError("unverified_receipt")
                domain = row.get("domain")
                _domain(domain)
                if row.get("currency", "EUR") != "EUR":
                    failure = "unsupported_currency"
                    costs_complete = False
                    continue
                category = _COST_CATEGORIES.get(row.get("category"))
                if category is None:
                    failure = "missing_category"
                    costs_complete = False
                    continue
                amount, _ = _amount(row.get("amount_eur"))
                occurred, settled = _instant(row.get("occurred_at")), _instant(row.get("settled_at"))
                if settled >= snapshot:
                    raise ValueError("unverified_receipt")
                refs = _refs(row.get("evidence_refs"))
                evidence_refs.update(refs)
                key = (provider, receipt_id)
                prior = seen_costs.get(key)
                if prior is not None:
                    if prior != row:
                        raise ValueError("unverified_receipt")
                    continue
                seen_costs[key] = row
                unique_cost_rows.append(row)
                record = _receipt(
                    receipt_id=receipt_id, provider=provider, amount=amount,
                    category=category, occurred_at=occurred, settled_at=settled,
                    evidence_refs=refs,
                )
                cost_records.append(record)
                cost_categories.add(category)
            except (ValueError, contract.ContractError):
                costs_complete = False
                failure = "unverified_receipt"

    try:
        unique_receipts = _unique_rows(receipts) if isinstance(receipts, list) else []
    except ValueError:
        unique_receipts = []
        failure = "unverified_receipt"
    sale_result = domain_flip_core.realized_sale(
        unique_receipts,
        costs if isinstance(costs, dict) else {},
    )
    revenue_record = None
    if sale_result.get("status") == "closed" and costs_complete:
        try:
            sale_id, domain, proof_refs, recognized_at = _complete_sale_proof(
                unique_receipts, snapshot
            )
            if any(row.get("domain") != domain for row in unique_cost_rows):
                raise ValueError("unverified_receipt")
            if not any(row.get("category") == "registration" for row in unique_cost_rows):
                raise ValueError("missing_coverage")
            buyer_rows = [row for row in unique_receipts
                          if row.get("type") == "buyer_settlement" and row.get("verified") is True]
            if len(buyer_rows) != 1:
                raise ValueError("unverified_receipt")
            payout_deductions = Decimal("0")
            for row in unique_cost_rows:
                if row.get("category") not in _PAYOUT_DEDUCTION_CATEGORIES:
                    continue
                if row.get("sale_id") != sale_id or row.get("domain") != domain:
                    raise ValueError("unverified_receipt")
                amount, _ = _amount(row.get("amount_eur"))
                payout_deductions += amount
            payout_difference = sale_result["revenue_eur"] - sale_result["payout_eur"]
            if payout_difference < 0 or payout_deductions != payout_difference:
                raise ValueError("unverified_receipt")
            revenue_record = _receipt(
                receipt_id=buyer_rows[0]["receipt_id"],
                provider="sedo",
                amount=sale_result["revenue_eur"],
                category=contract.REVENUE,
                occurred_at=recognized_at,
                settled_at=recognized_at,
                evidence_refs=proof_refs,
                revenue=True,
            )
        except (ValueError, KeyError, contract.ContractError):
            failure = "unverified_receipt"
            revenue_record = None
    elif sale_result.get("reason_codes"):
        reason = sale_result["reason_codes"][0]
        if "currency" in reason:
            failure = "unsupported_currency"
        elif "unverified" in reason or "invalid" in reason or "conflict" in reason:
            failure = "unverified_receipt"

    records = [*cost_records]
    categories = set(cost_categories)
    if revenue_record is not None:
        records.append(revenue_record)
        categories = set(covered_categories)
        categories.add(contract.REVENUE)
    coverage_state = "complete" if revenue_record is not None else "gap"
    coverage_reason = None if coverage_state == "complete" else failure
    coverage_refs = sorted(evidence_refs) or [f"domain-flip://cfo/coverage/{snapshot}"]
    records.extend([
        _coverage(
            projection="historical", start=None, end=snapshot,
            state=coverage_state, reason=coverage_reason,
            categories=sorted(categories), evidence_refs=coverage_refs,
        ),
        _coverage(
            projection="trailing", start=start, end=snapshot,
            state=coverage_state, reason=coverage_reason,
            categories=sorted(categories), evidence_refs=coverage_refs,
        ),
        _coverage(
            projection="as_of", start=None, end=snapshot,
            state="gap", reason="missing_coverage", categories=[],
            evidence_refs=coverage_refs,
        ),
    ])
    return records
