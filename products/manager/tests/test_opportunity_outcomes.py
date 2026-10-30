"""Public OSS opportunity contracts; no fixtures represent real paid work."""
import importlib
import importlib.util
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

from manager_core.economic_scorecard import CostCoverage, COST_CATEGORIES
from manager_core.models.source import Source


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def module():
    assert importlib.util.find_spec("manager_core.opportunity_outcomes") is not None, "opportunity outcome implementation missing"
    return importlib.import_module("manager_core.opportunity_outcomes")


def source(name):
    return Source(name, "https://example.org/" + name, "CC0-1.0", "allowed_with_conditions",
                  sha256(name.encode()).hexdigest(), NOW, "public_nonpersonal")


def opportunity():
    m = module()
    receipt = m.SettlementClaim("oss-1", "public-cohort", "a" * 64, "USD", 2000, "settled", source("receipt"))
    return m.OpportunityRecord(
        "oss-1", "public-cohort", "USD", 5000,
        m.OpportunityStage("posting", "public", source("posting")),
        m.OpportunityStage("delivery", "public", source("delivery")),
        m.OpportunityStage("approval", "public", source("approval")),
        m.OpportunityStage("settlement", "public", source("receipt")),
        "a" * 64, "a" * 64, receipt,
    )


def costs(**changes):
    m = module()
    amounts = {category: 0 for category in COST_CATEGORIES}
    amounts["compute"] = 200
    data = dict(expenses=CostCoverage(amounts), labor_minutes=120, opportunity_cost_minor=100, opportunities_considered=2)
    data.update(changes)
    return m.OpportunityCosts(**data)


class OpportunityOutcomeTests(unittest.TestCase):
    def test_posting_delivery_approval_settlement_visibility_are_distinct(self):
        m = module()
        item = opportunity()
        item = replace(item, settlement=m.OpportunityStage("settlement", "unknown"), receipt=None)
        result = m.reconcile_opportunity(item, costs())
        self.assertEqual(result.stage_visibility, {"posting": "public", "delivery": "public", "approval": "public", "settlement": "unknown"})
        self.assertEqual(result.income_status, "NOT_VERIFIED")
        self.assertIsNone(result.verified_income_minor)
        self.assertIsNone(result.declared_received_minor)

    def test_complete_declared_settlement_produces_qualified_arithmetic_not_verified_income(self):
        result = module().reconcile_opportunity(opportunity(), costs())
        self.assertEqual(result.evidence_status, "DECLARED_SETTLEMENT_RECONCILED")
        self.assertEqual(result.declared_received_minor, 2000)
        self.assertEqual(result.nominal_award_minor, 5000)
        self.assertEqual(result.expenses_minor, 200)
        self.assertEqual(result.declared_cash_net_minor, 1800)
        self.assertEqual(result.declared_economic_net_minor, 1700)
        self.assertEqual(result.labor_minutes, 120)
        self.assertEqual(result.opportunity_cost_minor, 100)
        self.assertEqual(result.net_per_labor_hour_minor, 850)
        self.assertEqual(result.net_per_opportunity_minor, 850)
        self.assertEqual(result.income_status, "NOT_VERIFIED")
        self.assertIsNone(result.verified_income_minor)
        self.assertEqual(result.human_welfare_status, "NOT_MEASURED")

    def test_award_approval_without_settlement_is_not_received_income(self):
        m = module()
        item = replace(opportunity(), receipt=None)
        result = m.reconcile_opportunity(item, costs())
        self.assertEqual(result.evidence_status, "RECEIPT_MISSING")
        self.assertIsNone(result.declared_received_minor)
        self.assertIsNone(result.declared_economic_net_minor)

    def test_pending_reversed_and_disputed_receipts_are_never_income(self):
        m = module()
        item = opportunity()
        for state in ("pending", "reversed", "disputed"):
            result = m.reconcile_opportunity(replace(item, receipt=replace(item.receipt, state=state)), costs())
            self.assertEqual(result.evidence_status, "SETTLEMENT_INCOMPLETE")
            self.assertIsNone(result.declared_received_minor)
            self.assertEqual(result.income_status, "NOT_VERIFIED")

    def test_receipt_must_match_exact_opportunity_group_artifact_and_currency(self):
        m = module()
        item = opportunity()
        for field, value in (("opportunity_id", "different"), ("beneficiary_group", "different"),
                             ("artifact_sha256", "b" * 64), ("currency", "JPY")):
            result = m.reconcile_opportunity(replace(item, receipt=replace(item.receipt, **{field: value})), costs())
            self.assertEqual(result.evidence_status, "RECEIPT_BINDING_MISMATCH")
            self.assertIsNone(result.declared_received_minor)
        result = m.reconcile_opportunity(replace(item, approved_artifact_sha256="b" * 64), costs())
        self.assertEqual(result.evidence_status, "ARTIFACT_MISMATCH")

    def test_same_stage_source_is_not_independent_receipt_provenance(self):
        m = module()
        item = opportunity()
        item = replace(item, receipt=replace(item.receipt, source=source("approval")))
        result = m.reconcile_opportunity(item, costs())
        self.assertEqual(result.evidence_status, "RECEIPT_SOURCE_MISMATCH")
        self.assertIsNone(result.declared_received_minor)

    def test_d011_receipt_cannot_reuse_posting_delivery_or_approval_source(self):
        m = module()
        item = opportunity()
        for earlier in ("posting", "delivery", "approval"):
            same = getattr(item, earlier).source
            modified = replace(
                item,
                settlement=m.OpportunityStage("settlement", "public", same),
                receipt=replace(item.receipt, source=same),
            )
            with self.subTest(earlier=earlier):
                outcome = m.reconcile_opportunity(modified, costs())
                self.assertEqual(outcome.evidence_status, "RECEIPT_EVIDENCE_REUSED")
                self.assertIsNone(outcome.declared_received_minor)
                self.assertIsNone(outcome.declared_economic_net_minor)
                self.assertEqual(outcome.income_status, "NOT_VERIFIED")

    def test_d011_receipt_reuse_with_distinct_ids_or_urls_is_not_independent(self):
        m = module()
        item = opportunity()
        approved = item.approval.source
        original = item.receipt.source
        fakes = (
            replace(original, source_id="independent-label", url=approved.url),
            replace(original, source_id="independent-label", content_sha256=approved.content_sha256),
        )
        for fake in fakes:
            modified = replace(
                item,
                settlement=m.OpportunityStage("settlement", "public", fake),
                receipt=replace(item.receipt, source=fake),
            )
            with self.subTest(fake=fake.source_id + fake.url):
                outcome = m.reconcile_opportunity(modified, costs())
                self.assertEqual(outcome.evidence_status, "RECEIPT_EVIDENCE_REUSED")
                self.assertIsNone(outcome.declared_received_minor)
                self.assertIsNone(outcome.verified_income_minor)

    def test_d011_separate_docs_are_necessary_not_sufficient_for_income(self):
        outcome = module().reconcile_opportunity(opportunity(), costs())
        self.assertEqual(outcome.evidence_status, "DECLARED_SETTLEMENT_RECONCILED")
        self.assertEqual(outcome.declared_received_minor, 2000)
        self.assertEqual(outcome.income_status, "NOT_VERIFIED")
        self.assertIsNone(outcome.verified_income_minor)
        self.assertEqual(outcome.human_welfare_status, "NOT_MEASURED")

    def test_unknown_expenses_time_and_opportunity_cost_stay_unknown(self):
        m = module()
        amounts = {category: 0 for category in COST_CATEGORIES}
        amounts["compute"] = None
        result = m.reconcile_opportunity(opportunity(), costs(expenses=CostCoverage(amounts), labor_minutes=None,
                                                              opportunity_cost_minor=None, opportunities_considered=None))
        self.assertEqual(result.declared_received_minor, 2000)
        for value in (result.expenses_minor, result.labor_minutes, result.opportunity_cost_minor,
                      result.declared_cash_net_minor, result.declared_economic_net_minor,
                      result.net_per_labor_hour_minor, result.net_per_opportunity_minor):
            self.assertIsNone(value)
        self.assertIn("expenses.compute", result.missing_fields)
        self.assertIn("labor_minutes", result.missing_fields)

    def test_cash_net_known_when_opportunity_cost_unknown_is_not_total_net(self):
        result = module().reconcile_opportunity(opportunity(), costs(opportunity_cost_minor=None))
        self.assertEqual(result.declared_cash_net_minor, 1800)
        self.assertIsNone(result.declared_economic_net_minor)

    def test_negative_net_and_zero_time_are_not_hidden_or_divided_by_zero(self):
        amounts = {category: 0 for category in COST_CATEGORIES}
        amounts["compute"] = 2500
        result = module().reconcile_opportunity(opportunity(), costs(expenses=CostCoverage(amounts), labor_minutes=0))
        self.assertEqual(result.declared_cash_net_minor, -500)
        self.assertEqual(result.declared_economic_net_minor, -600)
        self.assertIsNone(result.net_per_labor_hour_minor)

    def test_public_stage_cannot_import_private_records_or_confuse_stage_names(self):
        m = module()
        with self.assertRaises(ValueError):
            m.OpportunityStage("approval", "not_public", source("private"))
        with self.assertRaises(ValueError):
            replace(opportunity(), posting=m.OpportunityStage("settlement", "unknown"))
        with self.assertRaises(ValueError):
            m.OpportunityStage("posting", "public")
        with self.assertRaises(ValueError):
            costs(opportunities_considered=0)
        with self.assertRaises(ValueError):
            replace(opportunity().receipt, amount_minor=True)

    def test_supplied_hash_verification_does_not_authenticate_payment(self):
        m = module()
        result = m.reconcile_opportunity(opportunity(), costs(), snapshots={"receipt": b"receipt"})
        self.assertEqual(result.income_status, "NOT_VERIFIED")
        with self.assertRaises(ValueError):
            m.reconcile_opportunity(opportunity(), costs(), snapshots={"receipt": b"different"})


    def test_d011_fragment_alias_of_earlier_stage_is_not_a_declared_receipt(self):
        # RFC 3986 §3.5: a fragment does not establish a separate payment
        # resource. This is a fail-closed synthetic screen, not authentication.
        m = module()
        item = opportunity()
        for stage_name in ("posting", "delivery", "approval"):
            with self.subTest(stage=stage_name):
                previous = getattr(item, stage_name).source
                alias = replace(
                    item.receipt.source,
                    source_id="receipt_fragment_" + stage_name,
                    url=previous.url + "#claimed-distinct-receipt",
                    content_sha256="e" * 64,
                )
                changed = replace(
                    item,
                    settlement=m.OpportunityStage("settlement", "public", alias),
                    receipt=replace(item.receipt, source=alias),
                )
                output = m.reconcile_opportunity(changed, costs())
                self.assertEqual(output.evidence_status, "RECEIPT_EVIDENCE_REUSED")
                self.assertIsNone(output.declared_received_minor)
                self.assertIsNone(output.declared_economic_net_minor)
                self.assertEqual(output.income_status, "NOT_VERIFIED")



    def test_d011_https_authority_alias_of_approval_is_not_payment(self):
        m = module()
        item = opportunity()
        alias = replace(item.receipt.source, source_id="other_label",
                        url="https://EXAMPLE.ORG:443/approval#receipt",
                        content_sha256="f" * 64)
        changed = replace(item,
                          settlement=m.OpportunityStage("settlement", "public", alias),
                          receipt=replace(item.receipt, source=alias))
        result = m.reconcile_opportunity(changed, costs())
        self.assertEqual(result.evidence_status, "RECEIPT_EVIDENCE_REUSED")
        self.assertIsNone(result.declared_received_minor)
        self.assertEqual(result.income_status, "NOT_VERIFIED")

    def test_d011_invalid_port_fails_even_with_pending_receipt(self):
        m = module()
        item = opportunity()
        for port in ("abc", "0", "65536"):
            with self.subTest(port=port):
                bad = replace(item.posting.source,
                              url=f"https://example.org:{port}/posting")
                changed = replace(item,
                                  posting=m.OpportunityStage("posting", "public", bad),
                                  receipt=replace(item.receipt, state="pending"))
                with self.assertRaisesRegex(ValueError,
                                            "invalid public opportunity source port"):
                    m.reconcile_opportunity(changed, costs())


    def test_d011_unreserved_percent_alias_cannot_relabel_approval_as_receipt(self):
        m = module()
        item = opportunity()
        alias = replace(item.receipt.source, source_id="new-label",
                        url="https://EXAMPLE.org:443/%61pproval#payment",
                        content_sha256="f" * 64)
        changed = replace(item,
                          settlement=m.OpportunityStage("settlement", "public", alias),
                          receipt=replace(item.receipt, source=alias))
        result = m.reconcile_opportunity(changed, costs())
        self.assertEqual(result.evidence_status, "RECEIPT_EVIDENCE_REUSED")
        self.assertIsNone(result.declared_received_minor)
        self.assertEqual(result.income_status, "NOT_VERIFIED")

    def test_d011_invalid_percent_rejected_even_with_pending_receipt(self):
        m = module()
        item = opportunity()
        for invalid in ("%", "%2", "%ZZ"):
            with self.subTest(invalid=invalid):
                bad = replace(item.posting.source,
                              url="https://example.org/post?x=" + invalid)
                changed = replace(item,
                                  posting=m.OpportunityStage("posting", "public", bad),
                                  receipt=replace(item.receipt, state="pending"))
                with self.assertRaisesRegex(ValueError, "invalid public opportunity percent encoding"):
                    m.reconcile_opportunity(changed, costs())



    def test_d011_complete_dot_segments_cannot_relabel_approval_as_receipt(self):
        # RFC 3986 5.2.4/6.2.2.3: aliases only flag review, not payment.
        m = module()
        item = opportunity()
        for alias_url in (
            "https://example.org/./approval",
            "https://example.org/stage/../approval",
            "https://example.org/stage/%2e%2E/approval",
            "https://EXAMPLE.org:443/stage/../%61pproval#receipt",
            "https://example.org/../../approval",
        ):
            with self.subTest(alias=alias_url):
                fake = replace(item.receipt.source, source_id="renamed_receipt",
                               url=alias_url, content_sha256="f" * 64)
                changed = replace(item,
                                  settlement=m.OpportunityStage("settlement", "public", fake),
                                  receipt=replace(item.receipt, source=fake))
                result = m.reconcile_opportunity(changed, costs())
                self.assertEqual(result.evidence_status, "RECEIPT_EVIDENCE_REUSED")
                self.assertIsNone(result.declared_received_minor)
                self.assertIsNone(result.verified_income_minor)

    def test_d011_dot_segment_alias_key_rfc_examples(self):
        m = module()
        for left, right in (
            ("/a/b/../receipt", "/a/receipt"),
            ("/a/./receipt", "/a/receipt"),
            ("/a/b/c/./../../g", "/a/g"),
            ("/a/b/.", "/a/b/"),
            ("/a/b/..", "/a/"),
            ("/a/%2E%2e/receipt", "/receipt"),
            ("/../../receipt", "/receipt"),
        ):
            with self.subTest(left=left):
                self.assertEqual(m._resource_url("https://example.org" + left),
                                 m._resource_url("https://example.org" + right))

    def test_d011_dot_segments_preserve_nonstructural_paths_and_query(self):
        m = module()
        for left, right in (
            ("/a//receipt", "/a/receipt"),
            ("/.well-known/receipt", "/receipt"),
            ("/a/..receipt", "/receipt"),
            ("/a/%2F/receipt", "/a//receipt"),
            ("/a/%252e%252e/receipt", "/receipt"),
            ("/receipt?path=/a/../b", "/receipt?path=/b"),
            ("/receipt?x=1&x=2", "/receipt?x=2&x=1"),
        ):
            with self.subTest(left=left):
                self.assertNotEqual(m._resource_url("https://example.org" + left),
                                    m._resource_url("https://example.org" + right))



if __name__ == "__main__":
    unittest.main()
