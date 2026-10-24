"""D011: metadata-only guard against reusing one payment claim in a portfolio.

This is a *necessary* preflight before any future cross-opportunity sum, not
provider settlement verification. It reads typed public-source declarations
only, never fetches data or returns receipt identifiers, values or source URLs.
"""
from __future__ import annotations

from .opportunity_outcomes import OpportunityRecord

SCHEMA = "manager.opportunity-receipt-portfolio-preflight.v1"
MAX_RECORDS = 128


def preflight_receipt_portfolio(records: list | tuple) -> dict:
    """Detect declared duplicate payment evidence across independent records.

    Exact repeated source IDs, URLs or content digests trigger a conservative
    review. A common ledger page might legitimately contain several payments,
    so overlap is not proof of fraud; equally, distinct metadata cannot prove
    the underlying payment identities are different or funds were received.
    Never sum or authenticate declared amounts here.
    """
    if type(records) not in (list, tuple) or not 1 <= len(records) <= MAX_RECORDS:
        raise ValueError("a bounded portfolio of 1 to 128 typed records is required")

    reasons = set()
    scopes = set()
    seen = {"source_id": set(), "url": set(), "content_sha256": set()}
    reason_by_field = {
        "source_id": "RECEIPT_SOURCE_ID_REUSED",
        "url": "RECEIPT_URL_REUSED",
        "content_sha256": "RECEIPT_CONTENT_SHA256_REUSED",
    }

    for record in records:
        if type(record) is not OpportunityRecord:
            raise ValueError("typed public opportunity record required")
        scope = (record.opportunity_id, record.beneficiary_group)
        if scope in scopes:
            reasons.add("OPPORTUNITY_SCOPE_REUSED")
        scopes.add(scope)

        receipt = record.receipt
        if receipt is None:
            reasons.add("RECEIPT_MISSING")
            continue
        if receipt.state != "settled":
            reasons.add("RECEIPT_NOT_SETTLED")
        if record.settlement.visibility != "public" or record.settlement.source != receipt.source:
            reasons.add("SETTLEMENT_SOURCE_NOT_BOUND")
        source = receipt.source
        for field, reason in reason_by_field.items():
            value = getattr(source, field)
            if field == "content_sha256":
                value = value.lower()
            if value in seen[field]:
                reasons.add(reason)
            seen[field].add(value)

    return {
        "schema": SCHEMA,
        "status": "REVIEW_REQUIRED" if reasons else "PRELIMINARY_ONLY",
        "reason_codes": sorted(reasons),
        "provider_transaction_identity_verified": False,
        "source_bytes_verified": False,
        "independent_payment_verified": False,
        "can_count_declared_receipts_as_income": False,
        "can_publish": False,
        "can_execute": False,
        "income_status": "NOT_VERIFIED",
        "verified_income_minor": None,
        "beneficiary_effect": "NOT_MEASURED",
        "next_action": "NO_ACTION",
    }
