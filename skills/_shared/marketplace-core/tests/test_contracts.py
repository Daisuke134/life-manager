import copy
import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import contracts as marketplace_contracts  # noqa: E402
from contracts import (  # noqa: E402
    AuthorizationReceipt,
    ApplicationHistoryReceipt,
    ContractValidationError,
    ContractReceipt,
    DeliveryReceipt,
    PaymentReceipt,
    PayoutMatchReceipt,
    QAReceipt,
    parse_contract,
    validate_receipt_chain,
)
from ledger import normalize_event  # noqa: E402


class ContractReceiptTests(unittest.TestCase):
    def _mercor_chain(self):
        path = Path(__file__).parent / "fixtures" / "mercor-full-chain.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_parses_provider_observed_accepted_contract(self):
        receipt = parse_contract(
            {
                "schema_version": 1,
                "record_type": "contract_receipt",
                "platform": "mercor",
                "application_external_id": "application-123",
                "work_external_id": "work-123",
                "contract_external_id": "contract-456",
                "status": "accepted",
                "terms_sha256": "a" * 64,
                "observed_at": "2026-08-26T07:00:00Z",
            }
        )

        self.assertIsInstance(receipt, ContractReceipt)
        self.assertEqual(receipt.contract_external_id, "contract-456")

    def test_parses_history_without_fabricating_submission_content(self):
        receipt = parse_contract(
            {
                "schema_version": 1,
                "record_type": "application_history_receipt",
                "platform": "crowdworks",
                "opportunity_external_id": "job-123",
                "application_external_id": "proposal-456",
                "buyer_external_id": "buyer-789",
                "status": "submitted",
                "submitted_at": "2026-09-27T15:55:00+09:00",
                "observed_at": "2026-10-01T00:00:00Z",
            }
        )

        self.assertIsInstance(receipt, ApplicationHistoryReceipt)
        self.assertEqual(receipt.application_external_id, "proposal-456")

    def test_parses_explicit_work_authorization(self):
        receipt = parse_contract(
            {
                "schema_version": 1,
                "record_type": "authorization_receipt",
                "platform": "mercor",
                "contract_external_id": "contract-456",
                "authorization_external_id": "authorization-789",
                "status": "authorized",
                "scope_sha256": "b" * 64,
                "observed_at": "2026-08-26T07:05:00Z",
            }
        )

        self.assertIsInstance(receipt, AuthorizationReceipt)
        self.assertEqual(receipt.status, "authorized")

    def test_parses_artifact_bound_qa_receipt(self):
        receipt = parse_contract(
            {
                "schema_version": 1,
                "record_type": "qa_receipt",
                "platform": "mercor",
                "work_external_id": "work-123",
                "qa_external_id": "qa-012",
                "status": "passed",
                "artifact_sha256": "c" * 64,
                "report_sha256": "d" * 64,
                "observed_at": "2026-08-26T07:10:00Z",
            }
        )

        self.assertIsInstance(receipt, QAReceipt)
        self.assertEqual(receipt.status, "passed")

    def test_delivery_receipt_is_bound_to_qa(self):
        receipt = parse_contract(
            {
                "schema_version": 1,
                "record_type": "delivery_receipt",
                "platform": "mercor",
                "work_external_id": "work-123",
                "delivery_external_id": "delivery-345",
                "qa_external_id": "qa-012",
                "status": "verified",
                "artifact_sha256": "c" * 64,
                "idempotency_key": "mercor:delivery-345",
                "observed_at": "2026-08-26T07:15:00Z",
            }
        )

        self.assertIsInstance(receipt, DeliveryReceipt)
        self.assertEqual(receipt.qa_external_id, "qa-012")

    def test_payment_receipt_records_verified_net(self):
        value = {
            "schema_version": 1,
            "record_type": "payment_receipt",
            "platform": "mercor",
            "work_external_id": "work-123",
            "payment_external_id": "payment-678",
            "receipt_id": "receipt-901",
            "gross_amount_minor": 10000,
            "fee_amount_minor": 1000,
            "cost_amount_minor": 500,
            "net_amount_minor": 8500,
            "currency": "USD",
            "status": "settled",
            "occurred_at": "2026-08-26T07:20:00Z",
            "observed_at": "2026-08-26T07:21:00Z",
        }

        receipt = parse_contract(value)
        self.assertIsInstance(receipt, PaymentReceipt)
        self.assertEqual(receipt.net_amount_minor, 8500)
        self.assertEqual(normalize_event(value).amount_minor, 8500)

        value["net_amount_minor"] = 9000
        with self.assertRaisesRegex(ContractValidationError, "net_amount_minor"):
            parse_contract(value)

    def test_parses_official_payout_bank_match(self):
        receipt = parse_contract(
            {
                "schema_version": 1,
                "record_type": "payout_match_receipt",
                "platform": "mercor",
                "payment_external_id": "payment-678",
                "payout_external_id": "payout-234",
                "bank_transaction_external_id": "bank-567",
                "status": "matched",
                "amount_minor": 8500,
                "currency": "USD",
                "observed_at": "2026-08-26T07:25:00Z",
            }
        )

        self.assertIsInstance(receipt, PayoutMatchReceipt)
        self.assertEqual(receipt.bank_transaction_external_id, "bank-567")

    def test_validates_linked_mercor_full_chain(self):
        records = validate_receipt_chain(self._mercor_chain())

        self.assertEqual(records[-1].bank_transaction_external_id, "bank-1")

    def test_rejects_mismatched_bank_amount(self):
        chain = copy.deepcopy(self._mercor_chain())
        chain[-1]["amount_minor"] = 8499

        with self.assertRaisesRegex(ContractValidationError, "payout amount"):
            validate_receipt_chain(chain)

    def test_paid_handoff_requires_funded_contract_identity(self):
        contract = {
            "schema_version": 1,
            "record_type": "contract_receipt",
            "platform": "coconala",
            "application_external_id": "application-123",
            "work_external_id": "work-123",
            "contract_external_id": "contract-456",
            "status": "accepted",
            "terms_sha256": "a" * 64,
            "observed_at": "2026-08-26T07:00:00Z",
        }
        handoff = {
            "schema_version": 1,
            "record_type": "paid_handoff_receipt",
            "platform": "coconala",
            "thread_external_id": "thread-789",
            "contract_external_id": "contract-456",
            "funding_external_id": "milestone-001",
            "scope_sha256": "b" * 64,
            "artifact_requirement_sha256": "c" * 64,
            "price_minor": 50000,
            "currency": "JPY",
            "status": "funded",
            "observed_at": "2026-08-26T07:05:00Z",
        }

        parsed = marketplace_contracts.validate_paid_handoff(handoff, contract)

        self.assertEqual(type(parsed).__name__, "PaidHandoffReceipt")
        self.assertEqual(parsed.thread_external_id, "thread-789")

        missing_funding = copy.deepcopy(handoff)
        del missing_funding["funding_external_id"]
        with self.assertRaisesRegex(ContractValidationError, "funding_external_id"):
            marketplace_contracts.parse_paid_handoff_receipt(missing_funding)

        invalid_status = copy.deepcopy(handoff)
        invalid_status["status"] = "negotiating"
        with self.assertRaisesRegex(ContractValidationError, r"status: const_mismatch"):
            marketplace_contracts.parse_paid_handoff_receipt(invalid_status)

    def test_paid_handoff_rejects_contract_identity_mismatch(self):
        contract = {
            "schema_version": 1,
            "record_type": "contract_receipt",
            "platform": "lancers",
            "application_external_id": "application-123",
            "work_external_id": "work-123",
            "contract_external_id": "contract-456",
            "status": "accepted",
            "terms_sha256": "a" * 64,
            "observed_at": "2026-08-26T07:00:00Z",
        }
        handoff = {
            "schema_version": 1,
            "record_type": "paid_handoff_receipt",
            "platform": "coconala",
            "thread_external_id": "thread-789",
            "contract_external_id": "contract-456",
            "funding_external_id": "milestone-001",
            "scope_sha256": "b" * 64,
            "artifact_requirement_sha256": "c" * 64,
            "price_minor": 50000,
            "currency": "JPY",
            "status": "funded",
            "observed_at": "2026-08-26T07:05:00Z",
        }

        with self.assertRaisesRegex(ContractValidationError, "platform"):
            marketplace_contracts.validate_paid_handoff(handoff, contract)

    def test_paid_handoff_rejects_contract_without_accepted_status(self):
        contract = {
            "schema_version": 1,
            "record_type": "contract_receipt",
            "platform": "coconala",
            "application_external_id": "application-123",
            "work_external_id": "work-123",
            "contract_external_id": "contract-456",
            "status": "offered",
            "terms_sha256": "a" * 64,
            "observed_at": "2026-08-26T07:00:00Z",
        }
        handoff = {
            "schema_version": 1,
            "record_type": "paid_handoff_receipt",
            "platform": "coconala",
            "thread_external_id": "thread-789",
            "contract_external_id": "contract-456",
            "funding_external_id": "milestone-001",
            "scope_sha256": "b" * 64,
            "artifact_requirement_sha256": "c" * 64,
            "price_minor": 50000,
            "currency": "JPY",
            "status": "funded",
            "observed_at": "2026-08-26T07:05:00Z",
        }

        with self.assertRaisesRegex(ContractValidationError, "contract_not_accepted"):
            marketplace_contracts.validate_paid_handoff(handoff, contract)


if __name__ == "__main__":
    unittest.main()
