"""Focused contract tests for the reviewed D003 aggregate packet connection."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import unittest

from manager_core.models.source import Source

PACKET_PATH = Path(__file__).parents[1] / "docs/research/GIVEDIRECTLY_D003_SOURCE_20261023.json"
SOURCE_ID = "givedirectly-d003-aggregate-20261023"
SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/Daisuke134/life-manager/"
    "71c42c559ba416a85e60f10ba510298b4ceea44c/"
    "products/manager/docs/research/GIVEDIRECTLY_D003_SOURCE_20261023.json"
)
SNAPSHOT_SHA256 = "b76f8bbfb6e5a51094e35a3639a40bd0d4638c789fa1d2769a939cd88d2d6989"
RETRIEVED_AT = datetime.fromisoformat("2026-10-23T09:43:56.632492+00:00")


def reviewed_packet() -> bytes:
    return PACKET_PATH.read_bytes()


def packet_source(payload: bytes | None = None, *, source_id=SOURCE_ID, url=SNAPSHOT_URL) -> Source:
    payload = reviewed_packet() if payload is None else payload
    return Source(source_id, url, "minimal-aggregate-facts-and-source-links",
                  "allowed_with_conditions", hashlib.sha256(payload).hexdigest(),
                  RETRIEVED_AT, "public_nonpersonal")


class PublicProgramDisbursementTests(unittest.TestCase):
    def connector(self):
        try:
            module = importlib.import_module("manager_core.public_program_disbursement")
        except ModuleNotFoundError as error:
            if error.name != "manager_core.public_program_disbursement":
                raise
            self.fail("connect_published_program callable is unavailable")
        connect = getattr(module, "connect_published_program", None)
        self.assertTrue(callable(connect), "connect_published_program callable is unavailable")
        return connect

    def test_reviewed_packet_separates_disbursements_and_report(self):
        output = self.connector()(reviewed_packet(), packet_source())

        self.assertEqual(output["program_id"], "US-EIN-27-1661997-Ug-refugees-pilot")
        disbursements = output["disbursements"]
        self.assertEqual(disbursements["published_disbursement_total_minor"], 290390000)
        self.assertEqual(disbursements["currency"], "USD")
        self.assertEqual(len(disbursements["rows"]), 3)
        self.assertEqual([row["date_precision"] for row in disbursements["rows"]], ["day"] * 3)
        self.assertEqual([row["transaction_date"] for row in disbursements["rows"]],
                         ["2017-12-31", "2018-03-31", "2018-06-30"])

        aggregate = output["beneficiary_aggregate"]
        self.assertEqual((aggregate["value"], aggregate["denominator"]), (87, 484))
        self.assertIsNone(aggregate["item_specific_valid_response_count"])
        self.assertIsNone(aggregate["exact_positive_count"])
        self.assertIsNone(aggregate["followup_window"])
        relation = output["source_relation"]
        self.assertEqual(relation["connection"]["scope"], "same_program_only")
        self.assertEqual(relation["activity_report_document_link"]["url"],
                         "https://aidstream.s3.us-west-2.amazonaws.com/documents/"
                         "CashTransfersToRefugeeCommunitiesWhitePaper-20180917030903.pdf")
        raw_sources = relation["raw_sources"]
        self.assertEqual(len({item["sha256"] for item in raw_sources.values()}), 3)
        self.assertEqual(aggregate["report_date_precision"], "month")
        self.assertFalse(aggregate["third_party_evaluation"])
        self.assertEqual(output["limited_rights"]["iati_publisher"]["license_version_status"], "UNKNOWN")
        self.assertEqual(output["limited_rights"]["implementer_report"]["raw_redistribution_permission"],
                         "NOT_VERIFIED")

        self.assertEqual(output["proof_level"], "P0")
        self.assertEqual(output["action"], "NO_ACTION")
        self.assertEqual(output["human_welfare_status"], "NOT_MEASURED")
        self.assertEqual(output["measurement_authentication"], "NOT_VERIFIED")
        self.assertIsNone(output["verified_income_increase_minor"])
        self.assertIsNone(output["verified_net_benefit_minor"])
        self.assertIsNone(output["unresolved_accounting"]["costs_minor"])
        self.assertIsNone(output["unresolved_accounting"]["refunds_minor"])
        self.assertIsNone(output["unresolved_accounting"]["displacement_minor"])

    def test_source_hash_mismatch_rejects_altered_bytes(self):
        payload = reviewed_packet().replace(b"290390000", b"290390001")
        with self.assertRaises(ValueError):
            self.connector()(payload, packet_source())

    def test_reviewed_pin_rejects_caller_rehashed_amount_change(self):
        self.assert_rehashed_tamper_rejected(lambda packet: packet["disbursements"]["rows"][0].__setitem__(
            "amount_minor", packet["disbursements"]["rows"][0]["amount_minor"] + 1))

    def test_reviewed_pin_rejects_caller_rehashed_foreign_activity(self):
        self.assert_rehashed_tamper_rejected(lambda packet: packet.__setitem__("activity_id", "foreign-activity"))

    def test_reviewed_pin_rejects_caller_rehashed_contact_or_raw_body(self):
        def add_unreviewed_data(packet):
            packet["unreviewed_contact"] = "person@example.invalid"
            packet["raw_document_body"] = "unreviewed narrative"
        self.assert_rehashed_tamper_rejected(add_unreviewed_data)

    def assert_rehashed_tamper_rejected(self, mutate):
        packet = json.loads(reviewed_packet())
        mutate(packet)
        payload = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self.assertRaises(ValueError):
            self.connector()(payload, packet_source(payload))

    def test_raw_report_url_cannot_be_used_as_packet_source_url(self):
        with self.assertRaises(ValueError):
            self.connector()(reviewed_packet(), packet_source(
                url="https://aidstream.s3.us-west-2.amazonaws.com/documents/"
                     "CashTransfersToRefugeeCommunitiesWhitePaper-20180917030903.pdf"))

    def test_wrong_source_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            self.connector()(reviewed_packet(), packet_source(source_id="another-source"))

    def test_wrong_source_type_is_rejected(self):
        with self.assertRaises(ValueError):
            self.connector()(reviewed_packet(), object())

    def test_oversized_and_non_bytes_input_are_rejected(self):
        connect = self.connector()
        source = packet_source()
        with self.assertRaises(ValueError):
            connect(b"x" * 32769, source)
        with self.assertRaises(ValueError):
            connect("not bytes", source)


if __name__ == "__main__":
    unittest.main()
