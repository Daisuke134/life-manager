from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path


CORE_PATH = Path(__file__).with_name("core.py")
SPEC = importlib.util.spec_from_file_location("domain_flip_core", CORE_PATH)
assert SPEC is not None and SPEC.loader is not None
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


def purchase_inputs():
    candidate = {
        "domain": "novara.si",
        "minimum_accepted_price_eur": "500.00",
    }
    quote = {
        "available": True,
        "provider": "openprovider",
        "provider_receipt_id": None,
        "readback_verified": True,
        "evidence_refs": ["lm-domain-flip://readbacks/openprovider-price-quote-1"],
        "currency": "EUR",
        "registration_cost_eur": "10.00",
        "renewal_cost_eur": "10.00",
    }
    funding = {
        "currency": "EUR",
        "lifetime_cap_eur": "100.00",
        "owner_funded_total_eur": "100.00",
        "remaining_eur": "100.00",
        "source_type": "business_dedicated",
        "source_owner_id": "domain-flip",
        "source_verified": True,
        "top_up_count": 1,
        "automatic_refill_enabled": False,
    }
    portfolio = {
        "active_holdings": 0,
        "acquisitions_this_pass": 0,
        "effect_unknown_domains": [],
    }
    evidence = {
        "registrant": {
            "legal_holder_verified": True,
            "whois_email_functional": True,
            "whois_email_receiving_verified": True,
        },
        "rights": {
            "status": "clear",
            "sources": ["wipo", "euipo"],
            "evidence_refs": [
                "https://branddb.wipo.int/en/quicksearch",
                "https://api.euipo.europa.eu/trademark-search/trademarks",
            ],
        },
        "market": {
            "status": "reported",
            "evidence_refs": [
                "https://www.dynadot.com/blog/why-si-domains-are-gaining-attention",
            ],
        },
        "fees": {
            "sedo_fee_rate": "0.15",
            "tax_eur": "0.00",
            "payout_fee_eur": "0.00",
            "fx_fee_eur": "0.00",
            "measured_model_cost_eur": "0.01",
            "measured_infra_cost_eur": "0.00",
            "evidence_refs": ["https://sedo.com/us/what-we-offer/price-list/"],
        },
    }
    return candidate, quote, funding, portfolio, evidence


def complete_sale_receipts():
    return [
        {
            "type": "buyer_settlement",
            "sale_id": "sale-1",
            "provider": "sedo",
            "receipt_id": "buyer-1",
            "domain": "novara.si",
            "amount_eur": "500.00",
            "verified": True,
        },
        {
            "type": "holder_transfer",
            "sale_id": "sale-1",
            "provider": "register-si",
            "receipt_id": "transfer-1",
            "domain": "novara.si",
            "new_holder_verified": True,
            "verified": True,
        },
        {
            "type": "seller_payout",
            "sale_id": "sale-1",
            "provider": "sedo",
            "receipt_id": "payout-1",
            "amount_eur": "425.00",
            "verified": True,
        },
        {
            "type": "receiving_account_credit",
            "sale_id": "sale-1",
            "provider": "bank",
            "receipt_id": "credit-1",
            "amount_eur": "425.00",
            "verified": True,
        },
    ]


def complete_costs():
    return {
        "coverage_state": "complete",
        "evidence_refs": ["lm-domain-flip://cost-coverage/sale-1"],
        "items": [
            {"provider": "openprovider", "receipt_id": "reg-1", "category": "registration", "amount_eur": "10.00", "verified": True},
            {"provider": "openprovider", "receipt_id": "renewal-1", "category": "renewal", "amount_eur": "10.00", "verified": True},
            {"provider": "sedo", "receipt_id": "fee-1", "category": "marketplace_fee", "amount_eur": "75.00", "verified": True},
            {"provider": "agent-runner", "receipt_id": "model-1", "category": "model_cost", "amount_eur": "1.00", "verified": True},
        ],
    }


def test_purchase_obeys_total_cap_and_one_per_pass():
    args = purchase_inputs()
    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is True
    assert decision["conditional_net_eur"] == Decimal("404.99")
    assert decision["maximum_loss_eur"] == Decimal("20.01")
    assert decision["autorenew"] == "off"
    assert "expected_profit_eur" not in decision

    args[2]["remaining_eur"] = "20.00"
    capped = core.evaluate_purchase(*args)
    assert capped["eligible"] is False
    assert "funding_insufficient" in capped["reason_codes"]

    args = purchase_inputs()
    args[3]["acquisitions_this_pass"] = 1
    repeated = core.evaluate_purchase(*args)
    assert repeated["eligible"] is False
    assert "one_purchase_per_pass" in repeated["reason_codes"]

    args = purchase_inputs()
    args[3]["active_holdings"] = 4
    full = core.evaluate_purchase(*args)
    assert full["eligible"] is False
    assert "portfolio_limit" in full["reason_codes"]

    args = purchase_inputs()
    args[2]["owner_funded_total_eur"] = "100.01"
    over_cap = core.evaluate_purchase(*args)
    assert over_cap["eligible"] is False
    assert "lifetime_cap_exceeded" in over_cap["reason_codes"]

    args = purchase_inputs()
    args[2]["source_type"] = "personal"
    personal = core.evaluate_purchase(*args)
    assert personal["eligible"] is False
    assert "personal_funding_forbidden" in personal["reason_codes"]


def test_purchase_requires_known_public_registrant_and_rights_evidence():
    args = purchase_inputs()
    args[4]["registrant"]["whois_email_receiving_verified"] = False
    args[4]["rights"]["evidence_refs"] = []

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert "whois_email_unverified" in decision["reason_codes"]
    assert "rights_evidence_missing" in decision["reason_codes"]


def test_purchase_requires_quote_readback_evidence():
    args = purchase_inputs()
    args[1]["evidence_refs"] = []

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert "quote_unverified" in decision["reason_codes"]


def test_currency_mismatch_blocks_purchase():
    args = purchase_inputs()
    args[1]["currency"] = "USD"

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert "currency_mismatch" in decision["reason_codes"]

    args = purchase_inputs()
    args[1].update(
        currency="USD",
        fx_verified=True,
        fx_basis_receipt_id="funding-1",
        fx_evidence_refs=["lm-domain-flip://funding/funding-1/fx"],
        final_charge_eur="10.50",
        renewal_cost_eur="10.50",
    )
    args[2]["funding_receipt_id"] = "funding-1"
    converted = core.evaluate_purchase(*args)

    assert converted["eligible"] is True
    assert converted["maximum_loss_eur"] == Decimal("21.01")


def test_effect_unknown_fences_same_domain():
    args = purchase_inputs()
    args[3]["effect_unknown_domains"] = ["novara.si"]

    decision = core.evaluate_purchase(*args)
    phase = core.advance_phase("eligible", {"effect": "effect_unknown"})
    unresolved = core.advance_phase("effect_unknown", {})
    reconciled = core.advance_phase(
        "effect_unknown",
        {"readback": {
            "provider": "openprovider",
            "provider_receipt_id": "domain-1",
            "status": "active",
            "resolved_phase": "registered",
            "verified": True,
        }},
    )

    assert decision["eligible"] is False
    assert "effect_unknown" in decision["reason_codes"]
    assert phase == "effect_unknown"
    assert unresolved == "effect_unknown"
    assert reconciled == "registered"


def test_pending_offer_is_not_revenue():
    result = core.realized_sale(
        [{"type": "buyer_offer", "sale_id": "sale-1", "amount_eur": "500", "verified": True}],
        complete_costs(),
    )

    assert result["status"] == "pending"
    assert result["revenue_eur"] is None
    assert result["net_eur"] is None


def test_sale_requires_settlement_transfer_and_payout():
    receipts = complete_sale_receipts()
    receipts = [row for row in receipts if row["type"] != "receiving_account_credit"]

    result = core.realized_sale(receipts, complete_costs())

    assert result["status"] == "pending"
    assert result["revenue_eur"] is None
    assert "receiving_account_readback_missing" in result["reason_codes"]


def test_duplicate_sale_or_payout_receipt_is_counted_once():
    receipts = complete_sale_receipts()
    receipts.append(dict(receipts[2]))
    costs = complete_costs()
    costs["items"].append(dict(costs["items"][1]))

    result = core.realized_sale(receipts, costs)

    assert result["status"] == "closed"
    assert result["revenue_eur"] == Decimal("500.00")
    assert result["payout_eur"] == Decimal("425.00")
    assert result["cost_eur"] == Decimal("96.00")
    assert result["net_eur"] == Decimal("404.00")
