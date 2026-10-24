"""D011 receipt portfolio: synthetic, no bank accounts, no payment API."""
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import unittest

from manager_core.models.source import Source
from manager_core.opportunity_outcomes import (
    OpportunityRecord, OpportunityStage, SettlementClaim,
)
from manager_core.opportunity_receipt_portfolio import preflight_receipt_portfolio


NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)


def source(label):
    return Source(label, "https://example.org/" + label, "CC0-1.0",
                  "allowed_with_conditions", sha256(label.encode()).hexdigest(),
                  NOW, "public_nonpersonal")


def record(job, receipt_label, *, state="settled", amount=2000):
    receipt_source = source(receipt_label)
    receipt = SettlementClaim(job, "synthetic_public_group", "a" * 64,
                              "USD", amount, state, receipt_source)
    return OpportunityRecord(
        job, "synthetic_public_group", "USD", 5000,
        OpportunityStage("posting", "public", source(job + "_posting")),
        OpportunityStage("delivery", "public", source(job + "_delivery")),
        OpportunityStage("approval", "public", source(job + "_approval")),
        OpportunityStage("settlement", "public", receipt_source),
        "a" * 64, "a" * 64, receipt,
    )


def change_receipt_source(item, new_source):
    return replace(
        item,
        settlement=OpportunityStage("settlement", "public", new_source),
        receipt=replace(item.receipt, source=new_source),
    )


class ReceiptPortfolioTests(unittest.TestCase):
    def test_distinct_claims_only_pass_preliminary_screen(self):
        result = preflight_receipt_portfolio([
            record("job_a", "receipt_a"), record("job_b", "receipt_b")])
        self.assertEqual(result["status"], "PRELIMINARY_ONLY")
        self.assertEqual(result["reason_codes"], [])
        self.assertFalse(result["independent_payment_verified"])
        self.assertFalse(result["can_count_declared_receipts_as_income"])
        self.assertIsNone(result["verified_income_minor"])
        self.assertEqual(result["beneficiary_effect"], "NOT_MEASURED")

    def test_same_receipt_across_two_different_jobs_is_not_countable(self):
        result = preflight_receipt_portfolio([
            record("job_a", "receipt_shared"), record("job_b", "receipt_shared")])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        for reason in ("RECEIPT_SOURCE_ID_REUSED", "RECEIPT_URL_REUSED",
                       "RECEIPT_CONTENT_SHA256_REUSED"):
            self.assertIn(reason, result["reason_codes"])

    def test_source_id_only_collision_detected(self):
        first = record("job_a", "receipt_a")
        second = record("job_b", "receipt_b")
        altered = replace(second.receipt.source, source_id=first.receipt.source.source_id)
        result = preflight_receipt_portfolio([first, change_receipt_source(second, altered)])
        self.assertEqual(result["reason_codes"], ["RECEIPT_SOURCE_ID_REUSED"])

    def test_url_only_collision_detected(self):
        first = record("job_a", "receipt_a")
        second = record("job_b", "receipt_b")
        altered = replace(second.receipt.source, url=first.receipt.source.url)
        result = preflight_receipt_portfolio([first, change_receipt_source(second, altered)])
        self.assertEqual(result["reason_codes"], ["RECEIPT_URL_REUSED"])

    def test_content_hash_only_collision_detected(self):
        first = record("job_a", "receipt_a")
        second = record("job_b", "receipt_b")
        altered = replace(second.receipt.source, content_sha256=first.receipt.source.content_sha256)
        result = preflight_receipt_portfolio([first, change_receipt_source(second, altered)])
        self.assertEqual(result["reason_codes"], ["RECEIPT_CONTENT_SHA256_REUSED"])

    def test_same_job_and_group_twice_is_not_two_independent_jobs(self):
        result = preflight_receipt_portfolio([
            record("job_a", "receipt_a"), record("job_a", "receipt_b")])
        self.assertIn("OPPORTUNITY_SCOPE_REUSED", result["reason_codes"])
        self.assertFalse(result["can_count_declared_receipts_as_income"])

    def test_missing_pending_reversed_disputed_and_unbound_are_not_clean(self):
        first = record("job_a", "receipt_a")
        missing = replace(first, receipt=None)
        self.assertIn("RECEIPT_MISSING",
                      preflight_receipt_portfolio([missing])["reason_codes"])
        for state in ("pending", "reversed", "disputed"):
            with self.subTest(state=state):
                result = preflight_receipt_portfolio([record("job_a", "receipt_a", state=state)])
                self.assertIn("RECEIPT_NOT_SETTLED", result["reason_codes"])
        unbound = replace(first, settlement=OpportunityStage(
            "settlement", "public", source("mismatched_receipt")))
        self.assertIn("SETTLEMENT_SOURCE_NOT_BOUND",
                      preflight_receipt_portfolio([unbound])["reason_codes"])

    def test_same_amount_different_sources_is_not_automatically_reuse(self):
        result = preflight_receipt_portfolio([
            record("job_a", "receipt_a", amount=1200),
            record("job_b", "receipt_b", amount=1200)])
        self.assertEqual(result["reason_codes"], [])

    def test_only_source_collision_is_checked_not_provider_identity(self):
        first = record("job_a", "receipt_a")
        second = record("job_b", "receipt_b")
        second = replace(second, posting=first.posting)
        result = preflight_receipt_portfolio([first, second])
        self.assertEqual(result["status"], "PRELIMINARY_ONLY")
        self.assertFalse(result["provider_transaction_identity_verified"])

    def test_bad_shape_or_type_rejected_without_echo(self):
        for value in ([], (), "not a portfolio", [{}],
                      [record("job_a", "receipt_a")] * 129):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(ValueError):
                    preflight_receipt_portfolio(value)
        self.assertEqual(preflight_receipt_portfolio(
            (record("job_a", "receipt_a"),))["status"], "PRELIMINARY_ONLY")

    def test_no_amount_source_or_person_text_leaks_into_report(self):
        first = record("job_secret_alpha", "receipt_secret")
        second = record("job_secret_beta", "receipt_secret")
        result = preflight_receipt_portfolio([first, second])
        rendered = json.dumps(result)
        for secret in ("job_secret_alpha", "job_secret_beta", "receipt_secret",
                       "example.org", "2000", "synthetic_public_group"):
            self.assertNotIn(secret, rendered)
        for key in ("can_count_declared_receipts_as_income", "can_publish",
                    "can_execute", "source_bytes_verified",
                    "independent_payment_verified"):
            self.assertFalse(result[key], key)
        self.assertEqual(result["income_status"], "NOT_VERIFIED")
        self.assertEqual(result["next_action"], "NO_ACTION")


if __name__ == "__main__":
    unittest.main()
