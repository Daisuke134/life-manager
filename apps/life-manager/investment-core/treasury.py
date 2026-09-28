"""Read-only treasury separation for customer cash, investment P&L, and reserves."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Iterable


_MONEY = Decimal("0.01")
_CATEGORIES = {"customer_revenue", "investment_net_pnl", "owner_cash_flow", "model_cost"}


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.quantize(_MONEY, rounding=ROUND_HALF_EVEN))


def _empty(period: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "period": period,
        "customer_revenue_usd": None,
        "investment_net_pnl_usd": None,
        "owner_cash_flow_usd": None,
        "model_cost_usd": None,
        "tax_reserve_usd": None,
        "investable_surplus_usd": None,
        "investment_net_pnl_target_usd": "10000.00",
        "investment_net_pnl_target_gap_usd": None,
        "treasury_surplus_target_usd": None,
        "treasury_surplus_target_gap_usd": None,
        "evidence_status": status,
        "reason": reason,
        "source_receipt_ids": [],
    }


def treasury_snapshot(period: str, receipts: Iterable[dict[str, Any]], reserve_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(period, str) or not period:
        return _empty(str(period), "blocked", "period_invalid")
    if not isinstance(reserve_policy, dict):
        return _empty(period, "partial", "reserve_policy_missing")
    tax_rate = _decimal(reserve_policy.get("tax_rate"))
    cash_reserve = _decimal(reserve_policy.get("cash_reserve_usd"))
    if tax_rate is None or tax_rate < 0 or tax_rate > 1 or cash_reserve is None or cash_reserve < 0:
        return _empty(period, "blocked", "reserve_policy_invalid")
    try:
        rows = list(receipts)
    except TypeError:
        return _empty(period, "blocked", "receipts_invalid")
    if not rows:
        return _empty(period, "partial", "receipts_missing")

    seen: set[str] = set()
    totals = {category: Decimal("0") for category in _CATEGORIES}
    categories_seen: set[str] = set()
    source_ids: list[str] = []
    deductible_model_cost = Decimal("0")
    partial_reason = None
    for row in rows:
        if not isinstance(row, dict):
            return _empty(period, "blocked", "receipt_invalid")
        receipt_id = row.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id:
            return _empty(period, "blocked", "receipt_id_invalid")
        if receipt_id in seen:
            return _empty(period, "blocked", "duplicate_receipt_id")
        seen.add(receipt_id)
        source_ids.append(receipt_id)
        if row.get("status") != "verified":
            partial_reason = partial_reason or "receipt_unverified"
            continue
        category = row.get("category")
        if category not in _CATEGORIES:
            return _empty(period, "blocked", "category_invalid")
        amount = _decimal(row.get("amount_usd"))
        if amount is None:
            return _empty(period, "blocked", "amount_invalid")
        if category in {"customer_revenue", "model_cost"} and amount < 0:
            return _empty(period, "blocked", "amount_invalid")
        categories_seen.add(category)
        totals[category] += amount
        if category == "model_cost":
            included = row.get("included_in_investment_net")
            if not isinstance(included, bool):
                partial_reason = partial_reason or "model_cost_scope_unknown"
            elif not included:
                deductible_model_cost += amount

    required = {"customer_revenue", "investment_net_pnl", "owner_cash_flow", "model_cost"}
    if not required.issubset(categories_seen):
        partial_reason = partial_reason or "receipt_category_missing"
    if partial_reason:
        result = _empty(period, "partial", partial_reason)
        result["source_receipt_ids"] = source_ids
        return result

    taxable_base = max(Decimal("0"), totals["customer_revenue"] + max(Decimal("0"), totals["investment_net_pnl"]) - deductible_model_cost)
    tax_reserve = taxable_base * tax_rate
    investable = totals["customer_revenue"] + totals["investment_net_pnl"] - deductible_model_cost - tax_reserve - cash_reserve
    treasury_target = _decimal(reserve_policy.get("treasury_surplus_target_usd"))
    if treasury_target is not None and treasury_target < 0:
        return _empty(period, "blocked", "treasury_target_invalid")
    return {
        "period": period,
        "customer_revenue_usd": _money(totals["customer_revenue"]),
        "investment_net_pnl_usd": _money(totals["investment_net_pnl"]),
        "owner_cash_flow_usd": _money(totals["owner_cash_flow"]),
        "model_cost_usd": _money(totals["model_cost"]),
        "tax_reserve_usd": _money(tax_reserve),
        "investable_surplus_usd": _money(investable),
        "investment_net_pnl_target_usd": "10000.00",
        "investment_net_pnl_target_gap_usd": _money(max(Decimal("0"), Decimal("10000") - totals["investment_net_pnl"])),
        "treasury_surplus_target_usd": _money(treasury_target),
        "treasury_surplus_target_gap_usd": (
            _money(max(Decimal("0"), treasury_target - investable)) if treasury_target is not None else None
        ),
        "evidence_status": "measured",
        "reason": "measured_receipts",
        "source_receipt_ids": source_ids,
        "model_cost_deducted_usd": _money(deductible_model_cost),
        "taxable_base_usd": _money(taxable_base),
    }
