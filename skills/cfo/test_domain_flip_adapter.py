"""Receipt-bound tests for the domain-flip B0 adapter."""

from __future__ import annotations

import pytest

from skills.cfo import economic_attribution as contract
from skills.cfo.adapters import domain_flip as adapter


SNAPSHOT = "2026-10-07T14:00:00Z"
TRAILING_START = "2026-09-07T14:00:00Z"


def complete_sale_receipts():
    return [
        {
            "type": "buyer_settlement", "sale_id": "sale-1", "provider": "sedo",
            "receipt_id": "buyer-1", "domain": "novara.si", "amount_eur": "500.00",
            "currency": "EUR", "verified": True,
            "occurred_at": "2026-10-05T10:00:00Z", "settled_at": "2026-10-05T10:05:00Z",
            "evidence_refs": ["sedo://sales/sale-1/buyer-1"],
        },
        {
            "type": "holder_transfer", "sale_id": "sale-1", "provider": "register-si",
            "receipt_id": "transfer-1", "domain": "novara.si", "new_holder_verified": True,
            "currency": "EUR", "verified": True,
            "occurred_at": "2026-10-05T10:10:00Z", "settled_at": "2026-10-05T10:15:00Z",
            "evidence_refs": ["register-si://transfers/transfer-1"],
        },
        {
            "type": "seller_payout", "sale_id": "sale-1", "provider": "sedo",
            "receipt_id": "payout-1", "amount_eur": "425.00", "currency": "EUR",
            "verified": True,
            "occurred_at": "2026-10-05T10:20:00Z", "settled_at": "2026-10-05T10:25:00Z",
            "evidence_refs": ["sedo://payouts/payout-1"],
        },
        {
            "type": "receiving_account_credit", "sale_id": "sale-1", "provider": "bank",
            "receipt_id": "credit-1", "amount_eur": "425.00", "currency": "EUR",
            "verified": True,
            "occurred_at": "2026-10-05T10:30:00Z", "settled_at": "2026-10-05T10:35:00Z",
            "evidence_refs": ["bank://credits/credit-1"],
        },
    ]


def complete_costs():
    return {
        "coverage_state": "complete",
        "covered_categories": list(contract.COUNTED_CATEGORIES),
        "evidence_refs": ["domain-flip://cost-readback/sale-1"],
        "items": [
            {
                "provider": "openprovider", "receipt_id": "reg-1", "category": "registration",
                "domain": "novara.si",
                "amount_eur": "10.00", "currency": "EUR", "verified": True,
                "occurred_at": "2026-10-01T00:00:00Z", "settled_at": "2026-10-01T00:00:00Z",
                "evidence_refs": ["openprovider://receipts/reg-1"],
            },
            {
                "provider": "openprovider", "receipt_id": "renewal-1", "category": "renewal",
                "domain": "novara.si",
                "amount_eur": "10.00", "currency": "EUR", "verified": True,
                "occurred_at": "2026-10-01T00:00:00Z", "settled_at": "2026-10-01T00:00:00Z",
                "evidence_refs": ["openprovider://receipts/renewal-1"],
            },
            {
                "provider": "sedo", "receipt_id": "fee-1", "category": "marketplace_fee",
                "domain": "novara.si",
                "sale_id": "sale-1",
                "amount_eur": "75.00", "currency": "EUR", "verified": True,
                "occurred_at": "2026-10-05T10:05:00Z", "settled_at": "2026-10-05T10:05:00Z",
                "evidence_refs": ["sedo://fees/fee-1"],
            },
            {
                "provider": "agent-runner", "receipt_id": "model-1", "category": "model_cost",
                "domain": "novara.si",
                "amount_eur": "1.00", "currency": "EUR", "verified": True,
                "occurred_at": "2026-10-05T10:00:00Z", "settled_at": "2026-10-05T10:00:00Z",
                "evidence_refs": ["agent-runner://costs/model-1"],
            },
        ],
    }


def adapt(receipts=None, costs=None, *, monkeypatch):
    loop_ids = contract.PRODUCT_LOOP_IDS
    if "domain-flip" not in loop_ids:
        monkeypatch.setattr(contract, "PRODUCT_LOOP_IDS", (*loop_ids, "domain-flip"))
    return adapter.adapt_sale(
        complete_sale_receipts() if receipts is None else receipts,
        complete_costs() if costs is None else costs,
        snapshot_at=SNAPSHOT,
        trailing_start=TRAILING_START,
    )


def receipt_rows(records):
    return [record for record in records if record.get("record_type") == "receipt"]


def categories(record):
    return {component["category"] for component in record["components"]}


def complete_other_loop_coverage():
    rows = []
    for loop_id in contract.PRODUCT_LOOP_IDS:
        if loop_id == "domain-flip":
            continue
        for projection in ("historical", "trailing", "as_of"):
            rows.append(contract.validate_record({
                "schema_version": contract.SCHEMA_VERSION,
                "record_type": "coverage",
                "product_loop_id": loop_id,
                "source_id": f"fixture-{loop_id}",
                "projection": projection,
                "window_start": TRAILING_START if projection == "trailing" else None,
                "window_end": SNAPSHOT,
                "coverage_state": "complete",
                "reason": None,
                "covered_categories": list(
                    contract.AS_OF_CATEGORIES if projection == "as_of"
                    else contract.COUNTED_CATEGORIES
                ),
                "observed_at": SNAPSHOT,
                "evidence_refs": [f"fixture://coverage/{loop_id}/{projection}"],
            }))
    return rows


def test_only_settled_paid_transferred_sales_become_revenue(monkeypatch):
    records = adapt(monkeypatch=monkeypatch)

    revenue = [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]

    assert len(revenue) == 1
    assert revenue[0]["receipt_id"] == "buyer-1"
    assert revenue[0]["provider"] == "sedo"
    assert revenue[0]["components"] == [
        {"category": contract.REVENUE, "amount": "500"},
    ]


def test_registration_and_renewal_are_costs_not_revenue(monkeypatch):
    records = adapt(monkeypatch=monkeypatch)
    rows = {row["receipt_id"]: row for row in receipt_rows(records)}

    assert categories(rows["reg-1"]) == {"other_measured_cost"}
    assert categories(rows["renewal-1"]) == {"other_measured_cost"}
    assert contract.REVENUE not in categories(rows["reg-1"])
    assert contract.REVENUE not in categories(rows["renewal-1"])


def test_pending_sale_or_listing_is_not_revenue(monkeypatch):
    pending_listing = [{
        "type": "listing", "sale_id": "sale-1", "provider": "sedo",
        "receipt_id": "listing-1", "domain": "novara.si", "currency": "EUR",
        "verified": True, "occurred_at": "2026-10-05T09:00:00Z",
        "settled_at": "2026-10-05T09:00:00Z",
        "evidence_refs": ["sedo://listings/listing-1"],
    }]

    records = adapt(pending_listing, complete_costs(), monkeypatch=monkeypatch)

    assert not [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]


def test_duplicate_sale_receipt_is_deduplicated(monkeypatch):
    receipts = complete_sale_receipts()
    receipts.append(dict(receipts[0]))

    records = adapt(receipts, complete_costs(), monkeypatch=monkeypatch)
    revenue = [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]

    assert len(revenue) == 1
    assert revenue[0]["receipt_id"] == "buyer-1"
    assert revenue[0]["components"] == [
        {"category": contract.REVENUE, "amount": "500"},
    ]


def test_sale_identity_deduplicates_across_changed_sale_metadata(monkeypatch):
    receipts = complete_sale_receipts()
    costs = complete_costs()
    first = adapt(receipts, costs, monkeypatch=monkeypatch)
    for row in receipts:
        row["sale_id"] = "renamed-sale"
    next(row for row in costs["items"] if row["category"] == "marketplace_fee")["sale_id"] = "renamed-sale"
    second = adapt(receipts, costs, monkeypatch=monkeypatch)

    first_revenue = [row for row in receipt_rows(first) if contract.REVENUE in categories(row)]
    second_revenue = [row for row in receipt_rows(second) if contract.REVENUE in categories(row)]

    assert first_revenue[0]["receipt_id"] == second_revenue[0]["receipt_id"] == "buyer-1"
    projected = contract.project(
        [*first, *second, *complete_other_loop_coverage()],
        snapshot_at=SNAPSHOT,
        trailing_start=TRAILING_START,
    )
    domain_flip = projected["historical"]["loops"]["domain-flip"]
    assert domain_flip["currencies"]["EUR"]["settled_external_revenue"] == "500"
    assert domain_flip["currencies"]["EUR"]["net"] == "404"


def test_complete_sale_projects_verified_net_with_zero_cost_categories(monkeypatch):
    records = adapt(monkeypatch=monkeypatch)
    rows = [*records, *complete_other_loop_coverage()]

    projected = contract.project(rows, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START)
    domain_flip = projected["historical"]["loops"]["domain-flip"]

    assert domain_flip["status"] == "verified"
    assert domain_flip["currencies"]["EUR"]["net"] == "404"


def test_missing_zero_cost_category_coverage_blocks_complete_sale(monkeypatch):
    costs = complete_costs()
    costs["covered_categories"].remove("tool_cost")

    records = adapt(complete_sale_receipts(), costs, monkeypatch=monkeypatch)

    assert not [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]


def test_missing_payout_readback_is_a_coverage_gap(monkeypatch):
    receipts = [row for row in complete_sale_receipts() if row["type"] != "seller_payout"]

    records = adapt(receipts, complete_costs(), monkeypatch=monkeypatch)

    assert not [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]
    assert any(
        row.get("record_type") == "coverage"
        and row.get("product_loop_id") == "domain-flip"
        and row.get("coverage_state") == "gap"
        for row in records
    )


def test_payout_credit_and_transfer_need_settlement_timestamps(monkeypatch):
    receipts = complete_sale_receipts()
    receipts[1].pop("settled_at")

    records = adapt(receipts, complete_costs(), monkeypatch=monkeypatch)

    assert not [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]
    assert any(row.get("record_type") == "coverage" and row.get("coverage_state") == "gap"
               for row in records)


def test_missing_payout_deduction_receipt_blocks_gross_revenue(monkeypatch):
    costs = complete_costs()
    costs["items"] = [row for row in costs["items"] if row["category"] != "marketplace_fee"]

    records = adapt(complete_sale_receipts(), costs, monkeypatch=monkeypatch)

    assert not [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]
    assert any(row.get("record_type") == "coverage" and row.get("coverage_state") == "gap"
               for row in records)


def test_payout_deduction_amount_must_match_gross_to_net_difference(monkeypatch):
    costs = complete_costs()
    next(row for row in costs["items"] if row["category"] == "marketplace_fee")["amount_eur"] = "74.00"

    records = adapt(complete_sale_receipts(), costs, monkeypatch=monkeypatch)

    assert not [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]


def test_every_cost_receipt_must_match_the_sold_domain(monkeypatch):
    costs = complete_costs()
    costs["items"][0]["domain"] = "other.si"

    records = adapt(complete_sale_receipts(), costs, monkeypatch=monkeypatch)

    assert not [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]


def test_snapshot_boundary_cost_is_not_in_complete_window(monkeypatch):
    costs = complete_costs()
    next(row for row in costs["items"] if row["category"] == "marketplace_fee")["settled_at"] = (
        SNAPSHOT
    )

    records = adapt(complete_sale_receipts(), costs, monkeypatch=monkeypatch)

    assert not [row for row in receipt_rows(records) if contract.REVENUE in categories(row)]
    assert any(row.get("record_type") == "coverage" and row.get("coverage_state") == "gap"
               for row in records)
