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

    def test_d011_other_opportunity_stage_must_not_be_relabelled_as_payment(self):
        # A payment source can pass within-opportunity checks while copying an
        # unrelated job's posting, delivery or approval evidence.
        first = record("job_a", "receipt_a")
        second = record("job_b", "receipt_b")
        for stage_name in ("posting", "delivery", "approval"):
            earlier = getattr(first, stage_name).source
            aliases = (
                ("id", replace(second.receipt.source, source_id=earlier.source_id)),
                ("url_fragment", replace(second.receipt.source,
                                         url=earlier.url + "#looks-like-payment")),
                ("hash", replace(second.receipt.source,
                                 content_sha256=earlier.content_sha256)),
            )
            for alias_type, fake in aliases:
                altered = change_receipt_source(second, fake)
                for order in ([first, altered], [altered, first]):
                    with self.subTest(stage=stage_name, alias=alias_type,
                                      order=order[0].opportunity_id):
                        report = preflight_receipt_portfolio(order)
                        self.assertEqual(report["status"], "REVIEW_REQUIRED")
                        self.assertEqual(report["reason_codes"], [
                            "RECEIPT_REUSES_OTHER_OPPORTUNITY_STAGE_EVIDENCE"
                        ])
                        self.assertFalse(report["independent_payment_verified"])
                        self.assertFalse(report["can_count_declared_receipts_as_income"])
                        self.assertIsNone(report["verified_income_minor"])
                        self.assertNotIn("looks-like-payment", json.dumps(report))

    def test_d011_cross_job_stage_reuse_checks_unknown_receipt_records_too(self):
        # A source of an unclaimed-payment opportunity still cannot be
        # counted as an independent receipt for another opportunity.
        first = replace(record("job_a", "receipt_a"), receipt=None)
        second = record("job_b", "receipt_b")
        altered = change_receipt_source(second, first.delivery.source)
        report = preflight_receipt_portfolio([altered, first])
        self.assertIn("RECEIPT_MISSING", report["reason_codes"])
        self.assertIn("RECEIPT_REUSES_OTHER_OPPORTUNITY_STAGE_EVIDENCE",
                      report["reason_codes"])
        self.assertIsNone(report["verified_income_minor"])

    def test_only_source_collision_is_checked_not_provider_identity(self):
        first = record("job_a", "receipt_a")
        second = record("job_b", "receipt_b")
        second = replace(second, posting=first.posting)
        result = preflight_receipt_portfolio([first, second])
        self.assertEqual(result["status"], "PRELIMINARY_ONLY")
        self.assertFalse(result["provider_transaction_identity_verified"])

    def test_receipt_must_bind_to_its_own_opportunity_and_beneficiary_group(self):
        item = record("job_a", "receipt_a")
        for field, mismatch in (
            ("opportunity_id", "job_b"),
            ("beneficiary_group", "different_public_group"),
        ):
            with self.subTest(field=field):
                changed = replace(item, receipt=replace(item.receipt, **{field: mismatch}))
                result = preflight_receipt_portfolio([changed])
                self.assertEqual(result["status"], "REVIEW_REQUIRED")
                self.assertIn("RECEIPT_SCOPE_NOT_BOUND", result["reason_codes"])
                self.assertIsNone(result["verified_income_minor"])

    def test_receipt_currency_must_match_record(self):
        item = record("job_a", "receipt_a")
        changed = replace(item, receipt=replace(item.receipt, currency="JPY"))
        result = preflight_receipt_portfolio([changed])
        self.assertIn("RECEIPT_CURRENCY_NOT_BOUND", result["reason_codes"])
        self.assertFalse(result["can_count_declared_receipts_as_income"])

    def test_receipt_artifact_must_bind_to_delivery_and_approval(self):
        item = record("job_a", "receipt_a")
        candidates = (
            replace(item, delivered_artifact_sha256=None),
            replace(item, approved_artifact_sha256=None),
            replace(item, approved_artifact_sha256="b" * 64),
            replace(item, receipt=replace(item.receipt, artifact_sha256="c" * 64)),
        )
        for altered in candidates:
            with self.subTest(delivered=altered.delivered_artifact_sha256,
                              approved=altered.approved_artifact_sha256):
                result = preflight_receipt_portfolio([altered])
                self.assertEqual(result["status"], "REVIEW_REQUIRED")
                self.assertIn("RECEIPT_ARTIFACT_NOT_BOUND", result["reason_codes"])

    def test_posting_delivery_and_approval_must_be_public_for_chain_review(self):
        item = record("job_a", "receipt_a")
        for stage_name in ("posting", "delivery", "approval"):
            with self.subTest(stage=stage_name):
                changed = replace(
                    item, **{stage_name: OpportunityStage(stage_name, "unknown")}
                )
                result = preflight_receipt_portfolio([changed])
                self.assertIn("PUBLIC_EVIDENCE_CHAIN_INCOMPLETE", result["reason_codes"])
                self.assertFalse(result["can_execute"])

    def test_receipt_cannot_reuse_posting_delivery_or_approval_evidence(self):
        item = record("job_a", "receipt_a")
        for stage_name in ("posting", "delivery", "approval"):
            with self.subTest(stage=stage_name):
                changed = change_receipt_source(item, getattr(item, stage_name).source)
                result = preflight_receipt_portfolio([changed])
                self.assertIn(
                    "RECEIPT_REUSES_EARLIER_STAGE_EVIDENCE", result["reason_codes"]
                )
                self.assertFalse(result["independent_payment_verified"])

    def test_distinct_evidence_remains_preliminary_only_and_never_income(self):
        result = preflight_receipt_portfolio([record("job_a", "receipt_a")])
        self.assertEqual(result["reason_codes"], [])
        self.assertEqual(result["status"], "PRELIMINARY_ONLY")
        self.assertIsNone(result["verified_income_minor"])
        self.assertFalse(result["can_publish"])
        self.assertFalse(result["independent_payment_verified"])

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


    def test_fragment_only_receipt_url_alias_across_jobs_requires_review(self):
        first = record("job_a", "receipt_a")
        second = record("job_b", "receipt_b")
        # Different source IDs, digests and fragments; same primary URI.
        a = replace(
            first.receipt.source,
            url="https://example.org/ledger?tx=shared#receipt-a",
            content_sha256="1" * 64,
        )
        b = replace(
            second.receipt.source,
            url="https://example.org/ledger?tx=shared#receipt-b",
            content_sha256="2" * 64,
        )
        first = change_receipt_source(first, a)
        second = change_receipt_source(second, b)
        for pair in ([first, second], [second, first]):
            with self.subTest(order=pair[0].opportunity_id):
                result = preflight_receipt_portfolio(pair)
                self.assertEqual(result["status"], "REVIEW_REQUIRED")
                self.assertEqual(result["reason_codes"], ["RECEIPT_URL_REUSED"])
                self.assertFalse(result["can_count_declared_receipts_as_income"])
                self.assertIsNone(result["verified_income_minor"])
                self.assertNotIn("tx=shared", json.dumps(result))

    def test_fragment_only_earlier_stage_alias_requires_review(self):
        item = record("job_a", "receipt_a")
        previous = item.approval.source
        alias = replace(
            item.receipt.source,
            source_id="a_new_source_id",
            url=previous.url + "#relabelled-as-payment",
            content_sha256="f" * 64,
        )
        result = preflight_receipt_portfolio(
            [change_receipt_source(item, alias)]
        )
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertIn(
            "RECEIPT_REUSES_EARLIER_STAGE_EVIDENCE", result["reason_codes"]
        )
        self.assertFalse(result["independent_payment_verified"])

    def test_distinct_query_identifiers_are_not_erased_as_fragments(self):
        first = record("job_a", "receipt_a")
        second = record("job_b", "receipt_b")
        a = replace(first.receipt.source, url="https://example.org/ledger?tx=one#details")
        b = replace(second.receipt.source, url="https://example.org/ledger?tx=two#details")
        result = preflight_receipt_portfolio([
            change_receipt_source(first, a),
            change_receipt_source(second, b),
        ])
        # Different query parameters MAY describe different transactions.
        # They do not prove independence, but this narrow screen must not
        # collapse them just because they share a host/path.
        self.assertEqual(result["status"], "PRELIMINARY_ONLY")
        self.assertEqual(result["reason_codes"], [])
        self.assertFalse(result["independent_payment_verified"])



    def test_d011_https_authority_alias_across_jobs_requires_review(self):
        first, second = record("job_a", "receipt_a"), record("job_b", "receipt_b")
        a = replace(first.receipt.source, url="https://PAY.EXAMPLE.org:443/transfers?tx=a#one",
                    content_sha256="1" * 64)
        b = replace(second.receipt.source, url="https://pay.example.ORG/transfers?tx=a#two",
                    content_sha256="2" * 64)
        result = preflight_receipt_portfolio([
            change_receipt_source(first, a), change_receipt_source(second, b)])
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["reason_codes"], ["RECEIPT_URL_REUSED"])
        self.assertIsNone(result["verified_income_minor"])

    def test_d011_host_alias_of_another_job_posting_requires_review(self):
        first, second = record("job_a", "receipt_a"), record("job_b", "receipt_b")
        alias = replace(second.receipt.source,
                        url="https://EXAMPLE.ORG:443/job_a_posting#payment",
                        content_sha256="e" * 64)
        result = preflight_receipt_portfolio([
            first, change_receipt_source(second, alias)])
        self.assertEqual(result["reason_codes"],
                         ["RECEIPT_REUSES_OTHER_OPPORTUNITY_STAGE_EVIDENCE"])
        self.assertFalse(result["independent_payment_verified"])

    def test_d011_query_path_and_nondefault_ports_remain_distinct(self):
        cases = (
            ("https://example.org/r/Receipt?tx=a", "https://example.org/r/receipt?tx=a"),
            ("https://example.org/r?tx=A", "https://example.org/r?tx=a"),
            ("https://example.org/r?tx=a", "https://example.org:8443/r?tx=a"),
        )
        for left, right in cases:
            with self.subTest(left=left, right=right):
                first, second = record("job_a", "receipt_a"), record("job_b", "receipt_b")
                a = replace(first.receipt.source, url=left)
                b = replace(second.receipt.source, url=right)
                result = preflight_receipt_portfolio([
                    change_receipt_source(first, a), change_receipt_source(second, b)])
                self.assertEqual(result["status"], "PRELIMINARY_ONLY")
                self.assertEqual(result["reason_codes"], [])
                self.assertFalse(result["independent_payment_verified"])

    def test_d011_empty_root_path_alias_is_not_distinct_payment(self):
        first, second = record("job_a", "receipt_a"), record("job_b", "receipt_b")
        a = replace(first.receipt.source, url="https://example.org")
        b = replace(second.receipt.source, url="https://EXAMPLE.ORG:443/#details")
        result = preflight_receipt_portfolio([
            change_receipt_source(first, a), change_receipt_source(second, b)])
        self.assertEqual(result["reason_codes"], ["RECEIPT_URL_REUSED"])

    def test_d011_bad_port_cannot_hide_behind_matching_source_id(self):
        item = record("job_a", "receipt_a")
        for port in ("abc", "0", "65536"):
            with self.subTest(port=port):
                alias = replace(item.receipt.source,
                                source_id=item.posting.source.source_id,
                                url=f"https://example.org:{port}/ledger")
                with self.assertRaisesRegex(ValueError,
                                            "invalid public opportunity source port"):
                    preflight_receipt_portfolio([change_receipt_source(item, alias)])


if __name__ == "__main__":
    unittest.main()
