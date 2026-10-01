"""Focused B5 tests for pure Agent Economy and Investment attribution."""

from __future__ import annotations

import copy
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from skills.cfo import economic_attribution as contract
from skills.cfo.adapters import agent_economy_investment as adapter


SNAPSHOT = "2026-10-01T00:00:00Z"
TRAILING_START = "2026-09-24T00:00:00Z"
FIXTURES = Path(__file__).parent / "fixtures/economic_attribution"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def receipts(rows: list[dict], loop_id: str | None = None) -> list[dict]:
    return [
        row for row in rows
        if row.get("record_type") == "receipt"
        and (loop_id is None or row["product_loop_id"] == loop_id)
    ]


def coverage(rows: list[dict], loop_id: str, projection: str) -> dict:
    return next(
        row for row in rows
        if row.get("record_type") == "coverage"
        and row["product_loop_id"] == loop_id
        and row["projection"] == projection
    )


class AgentEconomyInvestmentAttributionTest(unittest.TestCase):
    def adapt_agent(self, payload: dict) -> list[dict]:
        return adapter.adapt_agent_economy(
            payload, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )

    def adapt_investment(self, payload: dict) -> list[dict]:
        return adapter.adapt_investment(
            payload, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START,
        )

    def test_finalized_x402_and_taskmarket_are_recorded_once_with_refund_and_fee(self):
        rows = self.adapt_agent(fixture("agent-economy-finalized.json"))
        for row in rows:
            contract.validate_record(row)
        by_id = {row["receipt_id"]: row for row in receipts(rows, "agent-economy")}
        self.assertEqual(
            by_id[
                "x402:base:0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:4"
            ]["components"],
            [
                {"category": "provider_fee", "amount": "0.05"},
                {"category": "refund", "amount": "0.25"},
                {"category": "settled_external_revenue", "amount": "1.25"},
            ],
        )
        self.assertEqual(
            by_id[
                "taskmarket:base:0xcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc:9"
            ]["components"],
            [
                {"category": "provider_fee", "amount": "0.075"},
                {"category": "settled_external_revenue", "amount": "1"},
            ],
        )
        taskmarket = by_id[
            "taskmarket:base:0xcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc:9"
        ]
        taskmarket_revenue = contract.Decimal("1")
        taskmarket_fee = contract.Decimal("0.075")
        self.assertEqual(taskmarket_revenue - taskmarket_fee, contract.Decimal("0.925"))
        self.assertEqual(
            taskmarket["components"][1]["amount"],
            str(taskmarket_revenue),
        )
        revenue = sum(
            contract.Decimal(component["amount"])
            for row in by_id.values()
            for component in row["components"]
            if component["category"] == contract.REVENUE
        )
        self.assertEqual(revenue, contract.Decimal("2.25"))
        self.assertEqual(coverage(rows, "agent-economy", "historical")["coverage_state"], "complete")
        self.assertEqual(coverage(rows, "agent-economy", "trailing")["coverage_state"], "complete")

    def test_taskmarket_award_amount_mismatch_fails_closed(self):
        base = fixture("agent-economy-finalized.json")
        for field, value in (("workerPayment", "924999"), ("platformFee", "75001")):
            payload = copy.deepcopy(base)
            payload["taskmarket"][0]["task"]["awards"][0][field] = value
            rows = self.adapt_agent(payload)
            self.assertFalse(any(
                row.get("record_type") == "receipt" and row.get("provider") == "taskmarket"
                for row in rows
            ))
            taskmarket_trailing = next(
                row for row in rows
                if row.get("record_type") == "coverage"
                and row["source_id"] == "taskmarket-readback"
                and row["projection"] == "trailing"
            )
            self.assertEqual(
                (taskmarket_trailing["coverage_state"], taskmarket_trailing["reason"]),
                ("gap", "unverified_receipt"),
            )

    def test_owner_deposit_self_payment_internal_transfer_pending_and_blockrun_are_not_revenue(self):
        rows = self.adapt_agent(fixture("agent-economy-excluded.json"))
        for row in rows:
            contract.validate_record(row)
        excluded = receipts(rows, "agent-economy")
        categories = {
            component["category"]
            for row in excluded
            for component in row["components"]
        }
        self.assertEqual(
            categories,
            {"owner_deposit", "self_payment", "internal_transfer", "pending_revenue"},
        )
        self.assertFalse(any(
            component["category"] == contract.REVENUE
            for row in excluded for component in row["components"]
        ))
        pending = next(row for row in excluded if row["components"][0]["category"] == "pending_revenue")
        self.assertEqual((pending["verification_state"], pending["settled_at"]), ("pending", None))
        x402_trailing = next(
            row for row in rows
            if row.get("record_type") == "coverage"
            and row["source_id"] == "x402-readback"
            and row["projection"] == "trailing"
        )
        self.assertEqual(x402_trailing["coverage_state"], "gap")
        self.assertEqual(x402_trailing["reason"], "unverified_receipt")

    def test_investment_realized_pnl_fees_slippage_and_verified_balance_are_recomputable(self):
        rows = self.adapt_investment(fixture("investment-realized.json"))
        for row in rows:
            contract.validate_record(row)
        investment_receipts = receipts(rows, "investment")

        def total(category: str):
            return sum(
                contract.Decimal(component["amount"])
                for row in investment_receipts
                for component in row["components"]
                if component["category"] == category
            )

        self.assertEqual(total(contract.REVENUE), contract.Decimal("5"))
        self.assertEqual(total("provider_fee"), contract.Decimal("0.25"))
        self.assertEqual(total("other_measured_cost"), contract.Decimal("1.56"))
        loss = next(row for row in investment_receipts if row["receipt_id"].endswith("sell-002:pnl"))
        self.assertEqual(loss["components"], [{"category": "other_measured_cost", "amount": "1.5"}])
        balance = next(row for row in rows if row["record_type"] == "liquid_balance")
        self.assertEqual(balance["amount"], "104.57")
        self.assertEqual(balance["verification_state"], "verified")
        self.assertEqual(coverage(rows, "investment", "as_of")["coverage_state"], "complete")

    def test_paper_token_appreciation_unrealized_and_unverified_balance_are_excluded(self):
        rows = self.adapt_investment(fixture("investment-paper-unrealized.json"))
        for row in rows:
            contract.validate_record(row)
        investment_receipts = receipts(rows, "investment")
        self.assertFalse(any(
            component["category"] in contract.COUNTED_CATEGORIES
            for row in investment_receipts for component in row["components"]
        ))
        self.assertEqual(
            {component["category"] for row in investment_receipts for component in row["components"]},
            {"token_appreciation", "unrealized_investment_pnl"},
        )
        self.assertFalse(any(row["record_type"] == "liquid_balance" for row in rows))
        self.assertEqual(coverage(rows, "investment", "as_of")["reason"], "unverified_receipt")

    def test_exact_duplicate_replay_is_zero_and_conflicting_identity_fails_closed(self):
        payload = fixture("agent-economy-finalized.json")
        replay = copy.deepcopy(payload)
        replay["x402"].append(copy.deepcopy(replay["x402"][0]))
        once = self.adapt_agent(payload)
        twice = self.adapt_agent(replay)
        self.assertEqual(once, twice)

        conflict = copy.deepcopy(payload)
        changed = copy.deepcopy(conflict["x402"][0])
        changed["usdc_atomic"] = "1250001"
        conflict["x402"].append(changed)
        conflicted = self.adapt_agent(conflict)
        self.assertFalse(any(
            component["category"] == contract.REVENUE
            for row in receipts(conflicted, "agent-economy")
            for component in row["components"]
        ))
        self.assertEqual(coverage(conflicted, "agent-economy", "historical")["reason"], "unverified_receipt")

    def test_missing_finality_identity_reorg_and_stale_readback_fail_closed(self):
        base = fixture("agent-economy-finalized.json")
        for mutation in (
            lambda row: row.update(finalized=False),
            lambda row: row.pop("log_index"),
            lambda row: row.update(reorg_detected=True),
        ):
            payload = copy.deepcopy(base)
            mutation(payload["x402"][0])
            rows = self.adapt_agent(payload)
            self.assertFalse(any(
                component["category"] == contract.REVENUE
                for row in receipts(rows, "agent-economy")
                for component in row["components"]
            ))
            self.assertEqual(coverage(rows, "agent-economy", "trailing")["reason"], "unverified_receipt")

        stale = copy.deepcopy(base)
        stale["observed_at"] = "2026-09-30T00:00:00Z"
        rows = self.adapt_agent(stale)
        self.assertFalse(receipts(rows, "agent-economy"))
        self.assertEqual(coverage(rows, "agent-economy", "trailing")["reason"], "stale_readback")

    def test_combined_adapter_and_path_adapter_are_replay_deterministic(self):
        bundle = {
            "agent_economy": fixture("agent-economy-finalized.json"),
            "investment": fixture("investment-realized.json"),
        }
        first = adapter.adapt(bundle, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START)
        second = adapter.adapt(copy.deepcopy(bundle), snapshot_at=SNAPSHOT, trailing_start=TRAILING_START)
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readback.json"
            path.write_text(json.dumps(bundle), encoding="utf-8")
            self.assertEqual(
                first,
                adapter.adapt_path(path, snapshot_at=SNAPSHOT, trailing_start=TRAILING_START),
            )

    def test_adapter_has_no_network_or_wallet_boundary(self):
        source = inspect.getsource(adapter)
        for forbidden in ("urllib", "requests", "httpx", "subprocess", "socket", "web3", "fetch("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
