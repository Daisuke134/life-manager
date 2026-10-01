"""Focused tests for pure official actual-cost readback attribution."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import economic_attribution as contract  # noqa: E402
from adapters import actual_cost  # noqa: E402


SNAPSHOT = "2026-10-01T00:00:00Z"
TRAILING_START = "2026-09-24T00:00:00Z"
FIXTURES = Path(__file__).parent / "fixtures/economic_attribution"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def adapt(payload: dict) -> list[dict]:
    return actual_cost.adapt(
        payload,
        snapshot_at=SNAPSHOT,
        trailing_start=TRAILING_START,
    )


def receipts(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["record_type"] == "receipt"]


def coverage(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["record_type"] == "coverage"]


class ActualCostAttributionTest(unittest.TestCase):
    def assert_contract_rows(self, rows: list[dict]) -> None:
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(contract.validate_record(row), row)

    def test_official_paid_documents_emit_only_measured_costs(self):
        rows = adapt(fixture("actual-cost-official.json"))
        self.assert_contract_rows(rows)
        actual = receipts(rows)

        self.assertEqual(len(actual), 11)
        self.assertEqual(
            {(row["provider"], row["currency"], row["product_loop_id"])
             for row in actual},
            {
                ("openai", "USD", "self-build"),
                ("openai", "USD", "writer"),
                ("openai", "USD", "affiliate"),
                ("anthropic", "USD", "writer"),
                ("openrouter", "USD", "affiliate"),
                ("blockrun", "USD", "agent-economy"),
                ("apify", "USD", "job-hunter"),
                ("browserbase", "USD", "job-hunter"),
                ("digitalocean", "USD", "self-build"),
                ("aws", "USD", "cfo"),
                ("aws", "JPY", "capafy"),
            },
        )
        categories = {
            component["category"]
            for row in actual
            for component in row["components"]
        }
        self.assertEqual(categories, {"model_cost", "tool_cost", "browser_cost", "infra_cost"})
        self.assertFalse(any(row["currency"] == "USD_API_EQUIV" for row in actual))
        self.assertTrue(all(row["verification_state"] == "verified" for row in actual))

        blockrun = next(row for row in actual if row["provider"] == "blockrun")
        self.assertIn("br-receipt-1", blockrun["receipt_id"])
        self.assertEqual(blockrun["components"], [{"category": "model_cost", "amount": "0.8"}])

        self.assertTrue(all(row["coverage_state"] == "complete" for row in coverage(rows)))
        self.assertTrue({row["projection"] for row in coverage(rows)} >= {"historical", "trailing"})

    def test_product_loop_allocation_is_explicit_and_preserves_amount(self):
        rows = adapt(fixture("actual-cost-official.json"))
        split = [
            row for row in receipts(rows)
            if row["receipt_id"].startswith("openai:actual-cost:invoice:inv-openai-202609:line:openai-model-split")
        ]
        self.assertEqual(
            [(row["product_loop_id"], row["components"][0]["amount"]) for row in split],
            [("affiliate", "1"), ("writer", "1")],
        )

    def test_unpriced_estimate_quote_and_personal_subscription_are_not_costs(self):
        rows = adapt(fixture("actual-cost-invalid.json"))
        self.assert_contract_rows(rows)
        self.assertEqual(receipts(rows), [])
        self.assertTrue(any(
            row["coverage_state"] == "gap"
            and row["reason"] in {"unsupported_currency", "missing_coverage", "unverified_receipt"}
            for row in coverage(rows)
        ))

    def test_blockrun_requires_official_paid_receipt_and_job_join(self):
        payload = fixture("actual-cost-official.json")
        payload["job_joins"] = []
        rows = adapt(payload)
        self.assertFalse(any(row["provider"] == "blockrun" for row in receipts(rows)))
        blockrun_gaps = [
            row for row in coverage(rows)
            if row["source_id"] == "actual-cost-blockrun"
        ]
        self.assertTrue(blockrun_gaps)
        self.assertTrue(all(row["coverage_state"] == "gap" for row in blockrun_gaps))
        self.assertTrue(all(row["reason"] == "unverified_receipt" for row in blockrun_gaps))

    def test_missing_invoice_is_a_gap_and_never_zero(self):
        rows = adapt(fixture("actual-cost-missing-invoice.json"))
        self.assert_contract_rows(rows)
        self.assertEqual(receipts(rows), [])
        expected = {
            "actual-cost-digitalocean",
            "actual-cost-aws",
            "actual-cost-openai",
            "actual-cost-anthropic",
            "actual-cost-openrouter",
        }
        observed = {row["source_id"] for row in coverage(rows)}
        self.assertTrue(expected <= observed)
        self.assertTrue(all(row["coverage_state"] == "gap" for row in coverage(rows)))
        self.assertTrue(all(row["reason"] in {"credential_missing", "read_failed", "missing_coverage"}
                            for row in coverage(rows)))

    def test_duplicate_identical_line_is_idempotent_and_conflict_is_gap(self):
        payload = fixture("actual-cost-duplicate.json")
        once = adapt(payload)
        replay = adapt(copy.deepcopy(payload))
        self.assertEqual(once, replay)
        self.assertEqual(len(receipts(once)), 1)

        conflict = copy.deepcopy(payload)
        conflict["documents"][0]["line_items"][1]["amount"] = "9.99"
        conflicted = adapt(conflict)
        self.assertEqual(receipts(conflicted), [])
        self.assertTrue(any(
            row["source_id"] == "actual-cost-openai"
            and row["coverage_state"] == "gap"
            and row["reason"] == "unverified_receipt"
            for row in coverage(conflicted)
        ))

    def test_stale_readback_drops_receipts_and_marks_both_windows_stale(self):
        payload = fixture("actual-cost-official.json")
        payload["readback"]["observed_at"] = "2026-09-30T23:59:59Z"
        rows = adapt(payload)
        self.assertEqual(receipts(rows), [])
        stale = coverage(rows)
        self.assertTrue(stale)
        self.assertTrue(all(row["coverage_state"] == "gap" for row in stale))
        self.assertTrue(all(row["reason"] == "stale_readback" for row in stale))

    def test_malformed_nested_shape_fails_closed_with_contract_valid_gap(self):
        payload = fixture("actual-cost-missing-invoice.json")
        payload["sources"] = [{
            "provider": "openai",
            "status": {"not": "hashable"},
            "product_loop_ids": [{"not": "a-loop"}],
        }]
        rows = adapt(payload)
        self.assert_contract_rows(rows)
        self.assertEqual(receipts(rows), [])
        self.assertTrue(all(row["coverage_state"] == "gap" for row in coverage(rows)))

    def test_currency_is_kept_separate_and_evidence_is_replay_stable(self):
        first = adapt(fixture("actual-cost-official.json"))
        second = adapt(fixture("actual-cost-official.json"))
        self.assertEqual(first, second)
        jpy = [row for row in receipts(first) if row["currency"] == "JPY"]
        self.assertEqual(len(jpy), 1)
        self.assertEqual(jpy[0]["components"], [{"category": "infra_cost", "amount": "1000"}])
        self.assertTrue(all(ref.startswith("lm-actual-cost://")
                           for row in first for ref in row["evidence_refs"]))


if __name__ == "__main__":
    unittest.main()
