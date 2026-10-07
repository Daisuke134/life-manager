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
        "registration_cost_eur": "1.00",
        "renewal_cost_eur": "1.00",
    }
    funding = {
        "currency": "EUR",
        "lifetime_cap_eur": "4.53",
        "owner_funded_total_eur": "4.53",
        "remaining_eur": "4.53",
        "lifetime_cap_usd": "4.99",
        "funding_receipt_usd": "4.99",
        "funding_receipt_eur": "4.53",
        "fx_verified": True,
        "fx_basis_receipt_id": "funding-1",
        "fx_evidence_refs": ["domain-flip://funding/funding-1/fx"],
        "source_type": "business_dedicated",
        "source_owner_id": "domain-flip",
        "source_verified": True,
        "balance_readback_verified": True,
        "balance_provider_receipt_id": "balance-readback-1",
        "funding_receipt_id": "funding-1",
        "top_up_count": 1,
        "automatic_refill_enabled": False,
    }
    portfolio = {
        "active_holdings": 0,
        "acquisitions_this_pass": 0,
        "committed_loss_eur": "0.00",
        "committed_loss_usd": "0.00",
        "effect_unknown_domains": [],
    }
    evidence = {
        "registrant": {
            "legal_holder_verified": True,
            "holder_type": "natural_person",
            "whois_email_functional": True,
            "whois_email_receiving_verified": True,
            "whois_public_fields": ["email"],
            "whois_optional_fields_opted_in": [],
            "whois_policy_verified": True,
            "whois_policy_evidence_refs": ["https://www.register.si/splosni-pogoji/#pravila_whois"],
            "owner_handle_fingerprint": "a" * 64,
            "contact_fingerprint": "b" * 64,
            "whois_email_fingerprint": "c" * 64,
        },
        "registrant_readback": {
            "provider": "openprovider",
            "readback_verified": True,
            "holder_type": "natural_person",
            "owner_handle_fingerprint": "a" * 64,
            "contact_fingerprint": "b" * 64,
            "email_fingerprint": "c" * 64,
            "email_verified": True,
        },
        "rights": {
            "status": "clear",
            "sources": ["euipo"],
            "evidence_refs": [
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
            "readback_verified": True,
            "cost_readback_verified": True,
            "cost_evidence_refs": ["domain-flip://cost-readback/run-1"],
            "minimum_sale_price_eur": "20.00",
            "sedo_fee_rate": "0.20",
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
    assert decision["conditional_net_eur"] == Decimal("397.99")
    assert decision["maximum_loss_eur"] == Decimal("2.01")
    assert decision["maximum_loss_usd"] == Decimal("2.22")
    assert decision["autorenew"] == "off"
    assert "expected_profit_eur" not in decision

    args[2]["remaining_eur"] = "1.00"
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


def test_purchase_reserves_all_fixed_costs_against_the_cap():
    args = purchase_inputs()
    args[2]["remaining_eur"] = "4.00"
    args[4]["fees"].update(tax_eur="0.50", payout_fee_eur="0.50", fx_fee_eur="1.00")

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert decision["maximum_loss_eur"] == Decimal("4.01")
    assert "funding_insufficient" in decision["reason_codes"]


def test_purchase_reserves_cumulative_spend_under_strict_usd_cap():
    args = purchase_inputs()
    args[1].update(registration_cost_eur="1.00", renewal_cost_eur="1.00")
    args[2].update(
        lifetime_cap_eur="4.53",
        owner_funded_total_eur="4.53",
        remaining_eur="4.53",
        lifetime_cap_usd="4.99",
        funding_receipt_usd="4.99",
        funding_receipt_eur="4.53",
        fx_verified=True,
        fx_basis_receipt_id="funding-1",
        fx_evidence_refs=["domain-flip://funding/funding-1/fx"],
    )
    args[3]["committed_loss_usd"] = "0.00"

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is True
    assert decision["maximum_loss_usd"] == Decimal("2.22")
    args[2]["usd_per_eur"] = "0.01"
    assert core.evaluate_purchase(*args)["maximum_loss_usd"] == Decimal("2.22")

    args[2]["fx_verified"] = False
    missing_fx_attestation = core.evaluate_purchase(*args)
    assert missing_fx_attestation["eligible"] is False
    assert "funding_fx_unverified" in missing_fx_attestation["reason_codes"]

    args[2]["fx_verified"] = True
    args[2]["fx_basis_receipt_id"] = "other-funding"
    mismatched_fx = core.evaluate_purchase(*args)
    assert mismatched_fx["eligible"] is False
    assert "funding_fx_unverified" in mismatched_fx["reason_codes"]

    args[2]["fx_basis_receipt_id"] = "funding-1"
    args[3]["committed_loss_usd"] = "2.78"
    over_cap = core.evaluate_purchase(*args)
    assert over_cap["eligible"] is False
    assert "lifetime_cap_exceeded" in over_cap["reason_codes"]


def test_funding_cap_must_remain_strictly_below_five_usd():
    args = purchase_inputs()
    args[1].update(registration_cost_eur="1.00", renewal_cost_eur="1.00")
    args[2].update(
        lifetime_cap_eur="4.54",
        owner_funded_total_eur="4.54",
        remaining_eur="4.54",
        lifetime_cap_usd="5.00",
        funding_receipt_usd="5.00",
        funding_receipt_eur="4.54",
        fx_verified=True,
        fx_basis_receipt_id="funding-1",
        fx_evidence_refs=["domain-flip://funding/funding-1/fx"],
    )
    args[3]["committed_loss_usd"] = "0.00"

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert "lifetime_cap_exceeded" in decision["reason_codes"]


def test_purchase_requires_fresh_matching_provider_contact_readback():
    args = purchase_inputs()
    args[4]["registrant_readback"]["contact_fingerprint"] = "d" * 64

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert "registrant_contact_readback_mismatch" in decision["reason_codes"]


def test_purchase_requires_explicit_natural_person_whois_publication_scope():
    args = purchase_inputs()
    args[4]["registrant"].pop("whois_optional_fields_opted_in")

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert "whois_publication_unverified" in decision["reason_codes"]


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


def test_purchase_requires_verified_business_balance_readback():
    args = purchase_inputs()
    args[2].pop("balance_readback_verified")
    args[2].pop("balance_provider_receipt_id")

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert "business_balance_unverified" in decision["reason_codes"]


def test_purchase_respects_current_marketplace_minimum_sale_price():
    args = purchase_inputs()
    args[0]["minimum_accepted_price_eur"] = "15.00"

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert "minimum_sale_price_invalid" in decision["reason_codes"]


def test_prior_committed_loss_reserves_the_lifetime_cap():
    args = purchase_inputs()
    args[3]["committed_loss_eur"] = "90.00"

    decision = core.evaluate_purchase(*args)

    assert decision["eligible"] is False
    assert "lifetime_cap_exceeded" in decision["reason_codes"]


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
        final_charge_eur="0.50",
        renewal_cost_eur="0.50",
    )
    args[2]["funding_receipt_id"] = "funding-1"
    converted = core.evaluate_purchase(*args)

    assert converted["eligible"] is False
    assert "currency_mismatch" in converted["reason_codes"]


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
