"""Pure policy and receipt arithmetic for the domain-flip owner."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


INITIAL_CAP_EUR = Decimal("100.00")
MAX_ACTIVE_HOLDINGS = 4
MAX_PURCHASES_PER_PASS = 1
AUTORENEW = "off"

_PHASES = {
    "discovered": "evidence-reviewed",
    "evidence-reviewed": "eligible",
    "eligible": "registered",
    "registered": "listing-pending",
    "listing-pending": "listed",
    "listed": "sale-pending",
    "sale-pending": "transferred",
    "transferred": "payout-confirmed",
    "payout-confirmed": "closed-net",
}
_TRANSITION_ACTIONS = {
    "discovered": "rights_review",
    "evidence-reviewed": "purchase_policy",
    "eligible": "registrar_readback",
    "registered": "sedo_listing_submission",
    "listing-pending": "sedo_listing_readback",
    "listed": "accepted_offer",
    "sale-pending": "holder_transfer_readback",
    "transferred": "payout_readback",
    "payout-confirmed": "cost_reconciliation",
}
_SALE_RECEIPT_TYPES = (
    "buyer_settlement",
    "holder_transfer",
    "seller_payout",
    "receiving_account_credit",
)


def _decimal(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() else None


def _refs(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(ref, str) and ref.strip() for ref in value)
    )


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def evaluate_purchase(
    candidate: dict[str, Any],
    quote: dict[str, Any],
    funding: dict[str, Any],
    portfolio: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Return a deterministic, EUR-denominated acquisition decision.

    `conditional_net_eur` is the margin if the minimum accepted sale completes.
    It deliberately contains no modeled sale probability or expected profit.
    """
    invalid_input = any(not isinstance(value, dict)
                        for value in (candidate, quote, funding, portfolio, evidence))
    candidate = candidate if isinstance(candidate, dict) else {}
    quote = quote if isinstance(quote, dict) else {}
    funding = funding if isinstance(funding, dict) else {}
    portfolio = portfolio if isinstance(portfolio, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    reasons: list[str] = []
    result: dict[str, Any] = {
        "eligible": False,
        "reason_codes": reasons,
        "conditional_net_eur": None,
        "maximum_loss_eur": None,
        "autorenew": AUTORENEW,
    }
    if invalid_input:
        _append_reason(reasons, "input_invalid")

    domain = candidate.get("domain") if isinstance(candidate, dict) else None
    if not isinstance(domain, str) or not domain.endswith(".si") or domain != domain.lower():
        _append_reason(reasons, "domain_invalid")

    if (quote.get("provider") != "openprovider"
            or quote.get("available") is not True
            or quote.get("readback_verified") is not True
            or not _refs(quote.get("evidence_refs"))):
        _append_reason(reasons, "quote_unverified")

    quote_currency = quote.get("currency")
    fx_valid = (
        quote.get("fx_verified") is True
        and bool(funding.get("funding_receipt_id"))
        and quote.get("fx_basis_receipt_id") == funding.get("funding_receipt_id")
        and _refs(quote.get("fx_evidence_refs"))
        and _decimal(quote.get("final_charge_eur")) is not None
    )
    if funding.get("currency") != "EUR" or (quote_currency != "EUR" and not fx_valid):
        _append_reason(reasons, "currency_mismatch")

    source_type = funding.get("source_type")
    if source_type in {"personal", "personal_wallet", "personal_bank", "personal_card", "credit"}:
        _append_reason(reasons, "personal_funding_forbidden")
    elif (source_type != "business_dedicated"
          or funding.get("source_owner_id") != "domain-flip"
          or funding.get("source_verified") is not True):
        _append_reason(reasons, "business_funding_unverified")

    cap = _decimal(funding.get("lifetime_cap_eur"))
    owner_funded = _decimal(funding.get("owner_funded_total_eur"))
    remaining = _decimal(funding.get("remaining_eur"))
    if (cap is None or owner_funded is None or remaining is None
            or cap < 0 or owner_funded < 0 or remaining < 0):
        _append_reason(reasons, "funding_invalid")
    elif (cap > INITIAL_CAP_EUR or owner_funded > INITIAL_CAP_EUR
          or owner_funded > cap):
        _append_reason(reasons, "lifetime_cap_exceeded")

    if funding.get("automatic_refill_enabled") is not False:
        _append_reason(reasons, "automatic_refill_enabled")
    top_up_count = funding.get("top_up_count")
    if type(top_up_count) is not int or top_up_count > 1:
        _append_reason(reasons, "repeat_funding_forbidden")

    active_holdings = portfolio.get("active_holdings")
    acquisitions = portfolio.get("acquisitions_this_pass")
    if type(active_holdings) is not int or active_holdings < 0:
        _append_reason(reasons, "portfolio_invalid")
    elif active_holdings >= MAX_ACTIVE_HOLDINGS:
        _append_reason(reasons, "portfolio_limit")
    if type(acquisitions) is not int or acquisitions < 0:
        _append_reason(reasons, "pass_count_invalid")
    elif acquisitions >= MAX_PURCHASES_PER_PASS:
        _append_reason(reasons, "one_purchase_per_pass")

    unknown_domains = portfolio.get("effect_unknown_domains", [])
    if not isinstance(unknown_domains, list):
        _append_reason(reasons, "effect_fence_state_invalid")
    elif isinstance(domain, str) and domain in unknown_domains:
        _append_reason(reasons, "effect_unknown")

    registrant = evidence.get("registrant", {})
    if not isinstance(registrant, dict) or registrant.get("legal_holder_verified") is not True:
        _append_reason(reasons, "legal_registrant_unverified")
    if (not isinstance(registrant, dict)
            or registrant.get("whois_email_functional") is not True
            or registrant.get("whois_email_receiving_verified") is not True):
        _append_reason(reasons, "whois_email_unverified")

    rights = evidence.get("rights", {})
    raw_rights_sources = rights.get("sources") if isinstance(rights, dict) else None
    rights_sources = (
        {source for source in raw_rights_sources if isinstance(source, str)}
        if isinstance(raw_rights_sources, list) else set()
    )
    if (not isinstance(rights, dict)
            or rights.get("status") != "clear"
            or not {"wipo", "euipo"}.issubset(rights_sources)
            or not _refs(rights.get("evidence_refs"))):
        _append_reason(reasons, "rights_evidence_missing")

    market = evidence.get("market", {})
    if (not isinstance(market, dict)
            or market.get("status") != "reported"
            or not _refs(market.get("evidence_refs"))):
        _append_reason(reasons, "market_evidence_missing")

    fees = evidence.get("fees", {})
    if not isinstance(fees, dict) or not _refs(fees.get("evidence_refs")):
        _append_reason(reasons, "fee_evidence_missing")
        fees = {}

    amount_fields = {
        "minimum_sale": _decimal(candidate.get("minimum_accepted_price_eur")),
        "registration": _decimal(
            quote.get("final_charge_eur") if quote_currency != "EUR" and fx_valid
            else quote.get("registration_cost_eur")
        ),
        "renewal": _decimal(quote.get("renewal_cost_eur")),
        "seller_fee_rate": _decimal(fees.get("sedo_fee_rate")),
        "tax": _decimal(fees.get("tax_eur")),
        "payout_fee": _decimal(fees.get("payout_fee_eur")),
        "fx_fee": _decimal(fees.get("fx_fee_eur")),
        "model_cost": _decimal(fees.get("measured_model_cost_eur")),
        "infra_cost": _decimal(fees.get("measured_infra_cost_eur")),
    }
    if any(value is None for value in amount_fields.values()):
        _append_reason(reasons, "cost_or_price_missing")
    elif any(value < 0 for value in amount_fields.values() if value is not None):
        _append_reason(reasons, "cost_or_price_invalid")
    elif amount_fields["seller_fee_rate"] > 1:
        _append_reason(reasons, "seller_fee_rate_invalid")

    values = amount_fields
    if all(value is not None for value in values.values()):
        minimum_sale = values["minimum_sale"]
        registration = values["registration"]
        renewal = values["renewal"]
        fee_rate = values["seller_fee_rate"]
        tax = values["tax"]
        payout_fee = values["payout_fee"]
        fx_fee = values["fx_fee"]
        model_cost = values["model_cost"]
        infra_cost = values["infra_cost"]
        maximum_loss = registration + renewal + model_cost + infra_cost
        conditional_net = (
            minimum_sale - (minimum_sale * fee_rate) - tax - payout_fee - fx_fee
            - registration - renewal - model_cost - infra_cost
        )
        result["maximum_loss_eur"] = maximum_loss
        result["conditional_net_eur"] = conditional_net
        if minimum_sale <= 0:
            _append_reason(reasons, "minimum_sale_price_invalid")
        if conditional_net <= 0:
            _append_reason(reasons, "conditional_net_not_positive")
        if remaining is not None and maximum_loss > remaining:
            _append_reason(reasons, "funding_insufficient")

    result["eligible"] = not reasons
    return result


def advance_phase(current: str, event: dict[str, Any]) -> str:
    """Advance only from an allowed event; hold uncertain effects for readback."""
    if not isinstance(event, dict):
        return current
    if event.get("effect") == "effect_unknown":
        return "effect_unknown"
    if current == "effect_unknown":
        readback = event.get("readback")
        if (not isinstance(readback, dict)
                or readback.get("verified") is not True
                or not readback.get("provider_receipt_id")
                or readback.get("provider") not in {"openprovider", "sedo", "register-si"}):
            return "effect_unknown"
        resolved = readback.get("resolved_phase")
        if isinstance(resolved, str) and resolved in {*_PHASES, "reconciled_no_effect"}:
            return resolved
        return "effect_unknown"

    next_phase = _PHASES.get(current)
    if next_phase is None or event.get("action") != _TRANSITION_ACTIONS[current]:
        return current
    if current == "discovered":
        valid = event.get("verified") is True and _refs(event.get("evidence_refs"))
    elif current == "evidence-reviewed":
        valid = event.get("eligible") is True and _refs(event.get("evidence_refs"))
    elif current == "eligible":
        readback = event.get("readback", {})
        valid = (
            isinstance(readback, dict)
            and readback.get("provider") == "openprovider"
            and readback.get("verified") is True
            and bool(readback.get("provider_receipt_id"))
            and readback.get("status") in {"active", "registered"}
        )
    elif current == "registered":
        valid = (
            event.get("provider") == "sedo"
            and event.get("verified") is True
            and bool(event.get("provider_receipt_id"))
        )
    elif current == "listing-pending":
        readback = event.get("readback", {})
        valid = (
            isinstance(readback, dict)
            and readback.get("provider") == "sedo"
            and readback.get("verified") is True
            and bool(readback.get("provider_receipt_id"))
            and readback.get("for_sale") is True
        )
    elif current == "listed":
        valid = (
            event.get("provider") == "sedo"
            and event.get("accepted") is True
            and event.get("verified") is True
            and bool(event.get("provider_receipt_id"))
        )
    elif current == "sale-pending":
        readback = event.get("readback", {})
        valid = (
            isinstance(readback, dict)
            and readback.get("provider") == "register-si"
            and readback.get("verified") is True
            and bool(readback.get("provider_receipt_id"))
            and readback.get("transferred_to_buyer") is True
        )
    elif current == "transferred":
        readback = event.get("readback", {})
        valid = (
            isinstance(readback, dict)
            and readback.get("seller_payout_verified") is True
            and readback.get("receiving_account_credit_verified") is True
            and bool(readback.get("provider_receipt_id"))
        )
    else:
        net = _decimal(event.get("net_eur"))
        valid = (
            event.get("cost_coverage_state") == "complete"
            and _refs(event.get("evidence_refs"))
            and net is not None
        )
    if valid:
        return next_phase
    return current


def _deduplicate(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            return [], False
        provider = row.get("provider")
        receipt_id = row.get("receipt_id")
        if not isinstance(provider, str) or not provider or not isinstance(receipt_id, str) or not receipt_id:
            return [], False
        key = (provider, receipt_id)
        prior = unique.get(key)
        if prior is not None and prior != row:
            return [], False
        unique[key] = row
    return list(unique.values()), True


def _pending(reason_codes: list[str]) -> dict[str, Any]:
    return {
        "status": "pending",
        "reason_codes": reason_codes,
        "revenue_eur": None,
        "payout_eur": None,
        "cost_eur": None,
        "net_eur": None,
    }


def realized_sale(receipts: list[dict[str, Any]], costs: dict[str, Any]) -> dict[str, Any]:
    """Compute one sale only after buyer, holder, payout, bank, and cost proof."""
    if not isinstance(receipts, list):
        return _pending(["sale_receipts_invalid"])
    unique, valid = _deduplicate(receipts)
    if not valid:
        return _pending(["sale_receipt_conflict"])

    if any(not isinstance(row.get("sale_id"), str) or not row.get("sale_id") for row in unique):
        return _pending(["sale_identity_incomplete"])
    sale_ids = {row["sale_id"] for row in unique}
    raw_domains = [row.get("domain") for row in unique if row.get("domain") is not None]
    if any(not isinstance(domain, str) or not domain for domain in raw_domains):
        return _pending(["sale_identity_incomplete"])
    domains = set(raw_domains)
    if len(sale_ids) != 1 or len(domains) != 1:
        return _pending(["sale_identity_incomplete"])

    reasons: list[str] = []
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in unique:
        if row.get("verified") is True:
            by_type.setdefault(str(row.get("type", "")), []).append(row)
    for receipt_type in _SALE_RECEIPT_TYPES:
        if not by_type.get(receipt_type):
            reason = {
                "buyer_settlement": "buyer_settlement_missing",
                "holder_transfer": "holder_transfer_missing",
                "seller_payout": "seller_payout_missing",
                "receiving_account_credit": "receiving_account_readback_missing",
            }[receipt_type]
            _append_reason(reasons, reason)
    if reasons:
        return _pending(reasons)

    for row in unique:
        if row.get("sale_id") not in sale_ids:
            _append_reason(reasons, "sale_id_mismatch")
        if row.get("currency", "EUR") != "EUR":
            _append_reason(reasons, "sale_currency_unverified")
    transfers = by_type["holder_transfer"]
    if not all(row.get("new_holder_verified") is True for row in transfers):
        _append_reason(reasons, "holder_transfer_unverified")

    def total_amount(rows: list[dict[str, Any]]) -> Decimal | None:
        amounts = [_decimal(row.get("amount_eur")) for row in rows]
        if any(amount is None or amount < 0 for amount in amounts):
            return None
        return sum((amount for amount in amounts if amount is not None), Decimal("0"))

    revenue = total_amount(by_type["buyer_settlement"])
    payout = total_amount(by_type["seller_payout"])
    bank_credit = total_amount(by_type["receiving_account_credit"])
    if revenue is None or revenue <= 0:
        _append_reason(reasons, "buyer_settlement_amount_invalid")
    if payout is None or payout <= 0:
        _append_reason(reasons, "seller_payout_amount_invalid")
    if bank_credit is None or bank_credit <= 0 or payout != bank_credit:
        _append_reason(reasons, "receiving_account_amount_mismatch")

    if (not isinstance(costs, dict)
            or costs.get("coverage_state") != "complete"
            or not _refs(costs.get("evidence_refs"))
            or not isinstance(costs.get("items"), list)):
        _append_reason(reasons, "cost_coverage_missing")
        cost_total = None
    else:
        unique_costs, costs_valid = _deduplicate(costs["items"])
        if not costs_valid:
            _append_reason(reasons, "cost_receipt_conflict")
            cost_total = None
        else:
            amounts = [_decimal(row.get("amount_eur")) for row in unique_costs]
            if (any(row.get("verified") is not True for row in unique_costs)
                    or any(row.get("currency", "EUR") != "EUR" for row in unique_costs)
                    or any(amount is None or amount < 0 for amount in amounts)):
                _append_reason(reasons, "cost_receipt_unverified")
                cost_total = None
            else:
                cost_total = sum((amount for amount in amounts if amount is not None), Decimal("0"))

    if reasons or revenue is None or payout is None or cost_total is None:
        return _pending(reasons or ["sale_record_incomplete"])

    return {
        "status": "closed",
        "reason_codes": [],
        "revenue_eur": revenue,
        "payout_eur": payout,
        "cost_eur": cost_total,
        "net_eur": revenue - cost_total,
        "receipt_count": len(unique),
        "cost_receipt_count": len(unique_costs),
    }
