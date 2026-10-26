"""D011: metadata-only guard for duplicate and unbound payment declarations.

This is a *necessary* preflight before any future cross-opportunity sum, not
provider settlement verification. It checks each declared evidence chain as
well as cross-opportunity reuse, never fetches data or returns receipt IDs,
amounts, beneficiary names or source URLs.
"""
from __future__ import annotations

from .opportunity_outcomes import OpportunityRecord, _resource_url

SCHEMA = "manager.opportunity-receipt-portfolio-preflight.v1"
MAX_RECORDS = 128


def preflight_receipt_portfolio(records: list | tuple) -> dict:
    """Detect declared duplicate payment evidence across independent records.

    Repeated source IDs, URL resources (even with different fragments), or
    content digests trigger a conservative
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

    earlier_stage_sources = []
    receipt_sources = []
    for record_index, record in enumerate(records):
        if type(record) is not OpportunityRecord:
            raise ValueError("typed public opportunity record required")
        scope = (record.opportunity_id, record.beneficiary_group)
        if scope in scopes:
            reasons.add("OPPORTUNITY_SCOPE_REUSED")
        scopes.add(scope)

        for name in ("posting", "delivery", "approval"):
            stage = getattr(record, name)
            if stage.source is not None:
                earlier_stage_sources.append((record_index, stage.source))

        # A portfolio must not call a claim "preliminary" when its own
        # posting -> delivery -> approval -> settlement chain is broken.
        # This is declaration consistency only, NOT external verification.
        if any(getattr(record, name).visibility != "public"
               for name in ("posting", "delivery", "approval")):
            reasons.add("PUBLIC_EVIDENCE_CHAIN_INCOMPLETE")

        receipt = record.receipt
        if receipt is None:
            reasons.add("RECEIPT_MISSING")
            continue
        if receipt.state != "settled":
            reasons.add("RECEIPT_NOT_SETTLED")
        if record.settlement.visibility != "public" or record.settlement.source != receipt.source:
            reasons.add("SETTLEMENT_SOURCE_NOT_BOUND")
        if (receipt.opportunity_id != record.opportunity_id
                or receipt.beneficiary_group != record.beneficiary_group):
            reasons.add("RECEIPT_SCOPE_NOT_BOUND")
        if receipt.currency != record.currency:
            reasons.add("RECEIPT_CURRENCY_NOT_BOUND")
        if (record.delivered_artifact_sha256 is None
                or record.approved_artifact_sha256 is None
                or record.delivered_artifact_sha256 != record.approved_artifact_sha256
                or receipt.artifact_sha256 != record.approved_artifact_sha256):
            reasons.add("RECEIPT_ARTIFACT_NOT_BOUND")

        # Merely relabeling a posting, approval or delivery page as a
        # settlement receipt cannot provide independent payment evidence.
        if any(
            stage.source is not None and (
                stage.source.source_id == receipt.source.source_id
                or _resource_url(stage.source.url) == _resource_url(receipt.source.url)
                or stage.source.content_sha256.lower() == receipt.source.content_sha256.lower()
            )
            for stage in (record.posting, record.delivery, record.approval)
        ):
            reasons.add("RECEIPT_REUSES_EARLIER_STAGE_EVIDENCE")
        source = receipt.source
        receipt_sources.append((record_index, source))
        for field, reason in reason_by_field.items():
            value = getattr(source, field)
            if field == "content_sha256":
                value = value.lower()
            elif field == "url":
                value = _resource_url(value)
            if value in seen[field]:
                reasons.add(reason)
            seen[field].add(value)

    # A receipt for opportunity B cannot be treated as independent merely
    # because it differs from B's own posting/delivery/approval materials:
    # B's claimed receipt might be opportunity A's earlier-stage document.
    # Source metadata is only a conservative screen, never payment proof.
    for receipt_index, receipt_source in receipt_sources:
        for earlier_index, earlier_source in earlier_stage_sources:
            if receipt_index == earlier_index:
                continue  # handled by the existing within-opportunity check
            if (receipt_source.source_id == earlier_source.source_id
                    or _resource_url(receipt_source.url) == _resource_url(earlier_source.url)
                    or receipt_source.content_sha256.lower() == earlier_source.content_sha256.lower()):
                reasons.add("RECEIPT_REUSES_OTHER_OPPORTUNITY_STAGE_EVIDENCE")
                break

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
