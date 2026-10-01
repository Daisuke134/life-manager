import importlib.util
import json
from pathlib import Path
import sys
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[4]
MODULE = Path(__file__).resolve().parents[1] / "scripts/financial_record.py"
SPEC = importlib.util.spec_from_file_location("marketplace_financial_record_test", MODULE)
financial = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = financial
SPEC.loader.exec_module(financial)
SCHEMA = json.loads((ROOT / "runtime/contracts/common-record.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def _validate(record):
    errors = list(VALIDATOR.iter_errors(record))
    assert not errors, errors[0].message if errors else ""


def payment():
    return {
        "schema_version": 1, "record_type": "payment_receipt", "platform": "mercor",
        "work_external_id": "work-1", "payment_external_id": "payment-1", "receipt_id": "receipt-1",
        "gross_amount_minor": 10000, "fee_amount_minor": 1000, "cost_amount_minor": 500,
        "net_amount_minor": 8500, "currency": "USD", "status": "settled",
        "occurred_at": "2026-09-07T01:00:00Z", "observed_at": "2026-09-07T01:01:00Z",
    }


def test_payment_projects_gross_fee_and_cost_without_net_double_counting():
    records = financial.payment_to_financial_records(payment(), subject_id="tenant-1")
    assert [(row["kind"], row["amount_minor"]) for row in records] == [
        ("business_revenue", 10000), ("fee", 1000), ("business_cost", 500),
    ]
    assert records == financial.payment_to_financial_records(payment(), subject_id="tenant-1")
    assert records[0]["record_id"] != financial.payment_to_financial_records(payment(), subject_id="tenant-2")[0]["record_id"]
    for record in records:
        _validate(record)


def test_matched_payout_projects_separately_from_revenue():
    value = {
        "schema_version": 1, "record_type": "payout_match_receipt", "platform": "mercor",
        "payment_external_id": "payment-1", "payout_external_id": "payout-1",
        "bank_transaction_external_id": "bank-1", "status": "matched", "amount_minor": 8500,
        "currency": "USD", "observed_at": "2026-09-07T01:02:00Z",
    }
    record = financial.payout_to_financial_record(value, subject_id="tenant-1")
    assert (record["kind"], record["amount_minor"]) == ("payout", 8500)
    _validate(record)
    sibling = financial.payout_to_financial_record(
        {**value, "payment_external_id": "payment-2"}, subject_id="tenant-1",
    )
    assert sibling["record_id"] != record["record_id"]


def test_platform_with_underscore_uses_fixed_evidence_scheme():
    value = {**payment(), "platform": "crowd_works"}
    [record, *_] = financial.payment_to_financial_records(value, subject_id="tenant-1")
    assert record["verification"]["evidence_refs"][0].startswith("marketplace://crowd_works/")
    _validate(record)


def _chain():
    return json.loads(
        (Path(__file__).parent / "fixtures" / "mercor-full-chain.json").read_text()
    )


def test_complete_positive_chain_projects_one_shared_chain_evidence():
    records = financial.project_receipt_chain(_chain(), subject_id="tenant-1")
    assert records == financial.project_receipts(_chain(), subject_id="tenant-1")

    assert [record["kind"] for record in records] == [
        "business_revenue", "fee", "business_cost", "payout",
    ]
    chain_refs = [
        [ref for ref in record["verification"]["evidence_refs"] if "/chain/" in ref]
        for record in records
    ]
    assert len({refs[0] for refs in chain_refs}) == 1
    for record in records:
        _validate(record)


def test_non_positive_chain_is_not_projected():
    value = _chain()
    value[5]["fee_amount_minor"] = 9500
    value[5]["net_amount_minor"] = 0
    value[6]["amount_minor"] = 0

    with pytest.raises(ValueError, match="net amount must be positive"):
        financial.project_receipt_chain(value, subject_id="tenant-1")


def test_partial_canonical_chain_cannot_bypass_chain_validation():
    value = _chain()[:-1]

    with pytest.raises(ValueError, match="incomplete_or_out_of_order_receipt_chain"):
        financial.project_receipts(value, subject_id="tenant-1")


def test_multiple_complete_chains_project_without_cross_chain_double_counting():
    first = _chain()
    second = deepcopy(first)
    for row in second:
        for key, value in list(row.items()):
            if isinstance(value, str) and value.endswith("-1"):
                row[key] = f"{value[:-2]}-2"

    records = financial.project_receipts(first + second, subject_id="tenant-1")

    assert len(records) == 8
    assert len({
        ref
        for record in records
        for ref in record["verification"]["evidence_refs"]
        if "/chain/" in ref
    }) == 2


def test_mixed_complete_and_partial_chains_fail_closed():
    with pytest.raises(ValueError, match="incomplete_or_out_of_order_receipt_chain"):
        financial.project_receipts(_chain() + _chain()[:-1], subject_id="tenant-1")


def test_payment_and_payout_only_journal_keeps_legacy_projection_path():
    value = _chain()
    records = financial.project_receipts(value[5:7], subject_id="tenant-1")

    assert [record["kind"] for record in records] == [
        "business_revenue", "fee", "business_cost", "payout",
    ]
