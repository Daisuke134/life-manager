"""Contract tests for the frozen public D011 opportunity snapshot."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import unittest

from manager_core.models.source import Source

try:
    from manager_core.public_opportunity_payment import (
        MAX_PACKET_BYTES,
        SNAPSHOT_SHA256,
        SNAPSHOT_URL,
        SOURCE_ID,
        connect_published_opportunity,
    )
except ImportError:
    # Keep collection successful on RED so the assertion names the missing API.
    MAX_PACKET_BYTES = 32768
    SNAPSHOT_SHA256 = "0" * 64
    SNAPSHOT_URL = "https://raw.githubusercontent.com/Daisuke134/life-manager/"
    SOURCE_ID = "jhipster-d011-aggregate-20261023"
    connect_published_opportunity = None


PACKET_PATH = (
    Path(__file__).parents[1]
    / "docs/research/JHIPSTER_D011_SOURCE_20261023.json"
)


class PublicOpportunityPaymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet_bytes = PACKET_PATH.read_bytes()
        cls.packet = json.loads(cls.packet_bytes)

    def source(self, body=None, *, source_id=SOURCE_ID, url=SNAPSHOT_URL):
        body = self.packet_bytes if body is None else body
        return Source(
            source_id=source_id,
            url=url,
            license_id="caller-controlled-license-must-not-be-projected",
            rights="allowed_with_conditions",
            content_sha256=sha256(body).hexdigest(),
            retrieved_at=datetime(2026, 10, 23, 10, 6, 19, 233694, tzinfo=timezone.utc),
            privacy_class="public_nonpersonal",
        )

    def connect(self, body=None, source=None):
        self.assertTrue(
            callable(connect_published_opportunity),
            "connect_published_opportunity(packet_bytes, packet_source) must be callable",
        )
        body = self.packet_bytes if body is None else body
        return connect_published_opportunity(body, source or self.source(body))

    def test_projects_exact_public_artifact_payment_links_and_conservative_claims(self):
        result = self.connect()

        artifact = result["public_artifact"]
        metadata = artifact["pr_metadata"]
        diff = artifact["diff_snapshot"]
        self.assertEqual(metadata["pr_url"], "https://github.com/jhipster/generator-jhipster/pull/34939")
        self.assertEqual(metadata["pr_number"], 34939)
        self.assertTrue(metadata["merged"])
        self.assertEqual(metadata["merged_at"], "2026-09-13T20:14:31Z")
        self.assertEqual(metadata["head_commit_git_sha1"], "3dc3a668b18f11ff8e72c1bf485ad3664132dc12")
        self.assertEqual(metadata["merge_commit_git_sha1"], "89bf4156f9c1a64a8ac6282908f1fb11cc3a0536")
        self.assertEqual(diff["diff_snapshot_sha256"], "367e082928145cd09777330dfebaf08357c992d95f8e14c510dd480ca80affda")
        self.assertNotEqual(diff["diff_snapshot_sha256"], metadata["head_commit_git_sha1"])
        self.assertNotEqual(diff["diff_snapshot_sha256"], metadata["merge_commit_git_sha1"])
        self.assertEqual(artifact["diff_hash_binding"], "ADAPTER_DERIVED_SNAPSHOT_NOT_PAYMENT_PROVIDER_ATTESTATION")

        payment = result["platform_payment"]
        self.assertEqual(payment["expense_id"], 346205)
        self.assertEqual(payment["expense_status"], "PAID")
        self.assertEqual(payment["currency"], "USD")
        self.assertEqual(payment["expense_amount_minor"], 10000)
        self.assertEqual(payment["paid_activity_type"], "COLLECTIVE_EXPENSE_PAID")
        self.assertEqual(payment["paid_at"], "2026-09-15T17:00:57.283Z")
        self.assertEqual(payment["platform_paid_debit_minor"], -10000)
        self.assertEqual(payment["bank_or_processor_settlement"], "NOT_VERIFIED")
        self.assertEqual(result["public_paid_amount_minor"], 10000)
        self.assertEqual(result["crosslinks"]["pr_url"], metadata["pr_url"])
        self.assertEqual(result["crosslinks"]["linked_expense_url"], payment["expense_url"])
        self.assertEqual(payment["invoice_item_pr_url"], metadata["pr_url"])
        self.assertEqual(payment["expense_description_pr_url"], metadata["pr_url"])

        self.assertEqual(result["prior_posting"]["prior_posting_status"], "UNKNOWN")
        self.assertIsNone(result["prior_posting"]["nominal_award_minor"])
        self.assertFalse(result["prior_posting"]["labels_precede_merge"])
        self.assertEqual(result["subject_scope"], "EXTERNAL_HISTORICAL_PUBLIC_WORK_NOT_MANAGER_INCOME")
        self.assertEqual(result["proof_level"], "P0")
        self.assertEqual(result["action"], "NO_ACTION")
        self.assertEqual(result["income_status"], "NOT_VERIFIED")
        self.assertEqual(result["human_welfare_status"], "NOT_MEASURED")
        self.assertEqual(result["chain_completeness"], "INCOMPLETE_PRIOR_POSTING_UNKNOWN")
        self.assertIsNone(result["verified_income_increase_minor"])
        self.assertIsNone(result["verified_net_benefit_minor"])
        self.assertTrue(all(value is None for value in result["unknown_costs"]["expenses_minor"].values()))
        self.assertIsNone(result["unknown_costs"]["labor_minutes"])
        self.assertIsNone(result["unknown_costs"]["opportunity_cost_minor"])
        self.assertIsNone(result["unknown_costs"]["opportunities_considered"])
        self.assertNotIn("license_id", result["packet_source"])
        self.assertNotIn("rights", result["packet_source"])

    def test_rehashed_replacements_cannot_change_frozen_facts_or_add_private_fields(self):
        mutations = (
            ("/platform_payment/expense_amount_minor", 1),
            ("/platform_payment/expense_id", 1),
            ("/crosslinks/linked_expense_url", "https://example.com/other-expense"),
            ("/platform_payment/expense_status", "PENDING"),
            ("/private_key", "must never be projected"),
        )
        for path, value in mutations:
            with self.subTest(path=path):
                changed = json.loads(self.packet_bytes)
                target = changed
                segments = path.strip("/").split("/")
                for segment in segments[:-1]:
                    target = target.setdefault(segment, {})
                target[segments[-1]] = value
                body = json.dumps(changed, separators=(",", ":")).encode()
                with self.assertRaisesRegex(ValueError, "reviewed snapshot"):
                    self.connect(body)

    def test_rejects_wrong_provenance_identity_and_packet_types_or_size(self):
        self.assertGreater(len(self.packet_bytes), 0)
        self.assertLessEqual(len(self.packet_bytes), MAX_PACKET_BYTES)
        with self.assertRaises(ValueError):
            self.connect(source=self.source(source_id="another-source"))
        with self.assertRaises(ValueError):
            self.connect(source=self.source(url="https://raw.githubusercontent.com/other/repo/"))

        self.assertTrue(callable(connect_published_opportunity), "adapter callable required")
        with self.assertRaises(ValueError):
            connect_published_opportunity(bytearray(self.packet_bytes), self.source())
        with self.assertRaises(ValueError):
            connect_published_opportunity("not bytes", self.source())
        with self.assertRaises(ValueError):
            connect_published_opportunity(b" " * (MAX_PACKET_BYTES + 1), self.source())
        with self.assertRaises(ValueError):
            connect_published_opportunity(self.packet_bytes, object())

    def test_source_hash_is_checked_before_independent_frozen_packet_pin(self):
        changed = self.packet_bytes + b" "
        with self.assertRaisesRegex(ValueError, "provenance hash"):
            self.connect(changed, self.source())


if __name__ == "__main__":
    unittest.main()
