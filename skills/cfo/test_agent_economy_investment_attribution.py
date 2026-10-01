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
SILENT_ROUND_AMOUNT = "123456789012345678901234567890.123456789012345678"
OVERSIZED_ATOMIC = "123456789012345678901234567890123"
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


def source_coverage(rows: list[dict], loop_id: str, source_id: str, projection: str) -> dict:
    return next(
        row for row in rows
        if row.get("record_type") == "coverage"
        and row["product_loop_id"] == loop_id
        and row["source_id"] == source_id
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

    def test_taskmarket_award_gross_and_rank_mismatch_fails_closed(self):
        base = fixture("agent-economy-finalized.json")
        for field, value in (("grossAmount", "999999"), ("rank", 2)):
            payload = copy.deepcopy(base)
            payload["taskmarket"][0]["task"]["awards"][0][field] = value
            rows = self.adapt_agent(payload)
            self.assertFalse(any(
                row.get("record_type") == "receipt" and row.get("provider") == "taskmarket"
                for row in rows
            ))
            self.assertEqual(
                coverage(rows, "agent-economy", "trailing")["reason"],
                "unverified_receipt",
            )

    def test_taskmarket_award_and_settlement_receipt_tx_must_match(self):
        payload = fixture("agent-economy-finalized.json")
        payload["taskmarket"][0]["receipt"]["tx_hash"] = (
            "0xdddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
        )
        rows = self.adapt_agent(payload)
        self.assertFalse(any(
            row.get("record_type") == "receipt" and row.get("provider") == "taskmarket"
            for row in rows
        ))
        self.assertEqual(
            coverage(rows, "agent-economy", "trailing")["reason"],
            "unverified_receipt",
        )

        normalized = fixture("agent-economy-finalized.json")
        normalized["taskmarket"][0]["receipt"]["tx_hash"] = (
            "0xCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
        )
        rows = self.adapt_agent(normalized)
        self.assertTrue(any(
            row.get("record_type") == "receipt" and row.get("provider") == "taskmarket"
            for row in rows
        ))

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

        self.assertEqual(total(contract.REVENUE), contract.Decimal("5.18"))
        self.assertEqual(total("provider_fee"), contract.Decimal("0.25"))
        self.assertEqual(total("other_measured_cost"), contract.Decimal("1.55"))
        loss = next(row for row in investment_receipts if row["receipt_id"].endswith("sell-002:pnl"))
        self.assertEqual(loss["components"], [{"category": "other_measured_cost", "amount": "1.49"}])
        gain_rows = [row for row in investment_receipts if "sell-001:" in row["receipt_id"]]
        gain_components = {
            component["category"]: contract.Decimal(component["amount"])
            for row in gain_rows for component in row["components"]
        }
        self.assertEqual(
            gain_components[contract.REVENUE]
            - gain_components["provider_fee"]
            - gain_components["other_measured_cost"],
            contract.Decimal("5"),
        )
        loss_cost = sum(
            contract.Decimal(component["amount"])
            for row in investment_receipts if "sell-002:" in row["receipt_id"]
            for component in row["components"]
        )
        self.assertEqual(-loss_cost, contract.Decimal("-1.50"))
        balance = next(row for row in rows if row["record_type"] == "liquid_balance")
        self.assertEqual(balance["amount"], "104.57")
        self.assertEqual(balance["verification_state"], "verified")
        self.assertEqual(coverage(rows, "investment", "as_of")["coverage_state"], "complete")

    def test_oversized_amounts_fail_closed_without_silent_rounding(self):
        for field in (
            "realized_pnl_usd", "fee_usd", "slippage_usd", "unrealized_pnl_usd",
        ):
            with self.subTest(source="investment", field=field):
                payload = fixture("investment-realized.json")
                payload["outcomes"][1][field] = SILENT_ROUND_AMOUNT
                rows = self.adapt_investment(payload)
                self.assertFalse(receipts(rows, "investment"))
                order_coverage = source_coverage(rows, "investment", "alpaca-orders", "trailing")
                self.assertEqual(
                    (order_coverage["coverage_state"], order_coverage["reason"]),
                    ("gap", "unverified_receipt"),
                )

        with self.subTest(source="investment", field="balance"):
            payload = fixture("investment-realized.json")
            payload["balance"]["amount"] = SILENT_ROUND_AMOUNT
            rows = self.adapt_investment(payload)
            self.assertFalse(any(row["record_type"] == "liquid_balance" for row in rows))
            self.assertEqual(
                (coverage(rows, "investment", "as_of")["coverage_state"],
                 coverage(rows, "investment", "as_of")["reason"]),
                ("gap", "unverified_receipt"),
            )

        with self.subTest(source="x402", field="amount"):
            payload = fixture("agent-economy-finalized.json")
            payload["x402"][0]["gross_decimal"] = SILENT_ROUND_AMOUNT
            rows = self.adapt_agent(payload)
            self.assertFalse(any(
                row.get("record_type") == "receipt" and row.get("provider") == "x402"
                for row in rows
            ))
            x402_coverage = source_coverage(rows, "agent-economy", "x402-readback", "trailing")
            self.assertEqual(
                (x402_coverage["coverage_state"], x402_coverage["reason"]),
                ("gap", "unverified_receipt"),
            )

        with self.subTest(source="taskmarket", field="amount"):
            payload = fixture("agent-economy-finalized.json")
            payload["taskmarket"][0]["award"]["grossAmount"] = OVERSIZED_ATOMIC
            rows = self.adapt_agent(payload)
            self.assertFalse(any(
                row.get("record_type") == "receipt" and row.get("provider") == "taskmarket"
                for row in rows
            ))
            taskmarket_coverage = source_coverage(
                rows, "agent-economy", "taskmarket-readback", "trailing",
            )
            self.assertEqual(
                (taskmarket_coverage["coverage_state"], taskmarket_coverage["reason"]),
                ("gap", "unverified_receipt"),
            )

    def test_missing_or_unknown_investment_pnl_basis_fails_closed(self):
        base = fixture("investment-realized.json")
        for basis in (None, "mystery_basis"):
            payload = copy.deepcopy(base)
            if basis is None:
                payload["outcomes"][1].pop("pnl_basis")
            else:
                payload["outcomes"][1]["pnl_basis"] = basis
            rows = self.adapt_investment(payload)
            self.assertFalse(receipts(rows, "investment"))
            self.assertEqual(
                next(
                    row for row in rows
                    if row.get("record_type") == "coverage"
                    and row["source_id"] == "alpaca-orders"
                    and row["projection"] == "trailing"
                )["reason"],
                "unverified_receipt",
            )

    def test_negative_unrealized_is_excluded_without_dropping_realized_records(self):
        payload = fixture("investment-realized.json")
        payload["outcomes"][1]["unrealized_pnl_usd"] = "-2.25"
        rows = self.adapt_investment(payload)
        realized = next(
            row for row in receipts(rows, "investment")
            if row["receipt_id"].endswith("sell-001:pnl")
        )
        unrealized = next(
            row for row in receipts(rows, "investment")
            if row["receipt_id"].endswith("sell-001:unrealized")
        )
        self.assertEqual(realized["components"], [
            {"category": "settled_external_revenue", "amount": "5.18"},
        ])
        self.assertEqual(unrealized["components"], [
            {"category": "unrealized_investment_pnl", "amount": "2.25"},
        ])

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

    def test_agent_bundle_root_reorg_fails_closed(self):
        payload = fixture("agent-economy-finalized.json")
        payload["reorg_detected"] = True
        rows = self.adapt_agent(payload)
        self.assertFalse(receipts(rows, "agent-economy"))
        for source_id in ("x402-readback", "taskmarket-readback"):
            for projection in ("historical", "trailing"):
                row = next(
                    row for row in rows
                    if row.get("record_type") == "coverage"
                    and row["source_id"] == source_id
                    and row["projection"] == projection
                )
                self.assertEqual((row["coverage_state"], row["reason"]), ("gap", "unverified_receipt"))

    def test_investment_bundle_root_reorg_fails_closed(self):
        payload = fixture("investment-realized.json")
        payload["reorg_detected"] = True
        rows = self.adapt_investment(payload)
        self.assertFalse(receipts(rows, "investment"))
        self.assertFalse(any(row["record_type"] == "liquid_balance" for row in rows))
        self.assertEqual(
            coverage(rows, "investment", "trailing")["reason"],
            "unverified_receipt",
        )
        account = next(
            row for row in rows
            if row.get("record_type") == "coverage"
            and row["source_id"] == "alpaca-account"
            and row["projection"] == "as_of"
        )
        self.assertEqual((account["coverage_state"], account["reason"]), ("gap", "unverified_receipt"))

    def test_agent_strict_boolean_integer_types_and_alias_conflicts_fail_closed(self):
        cases = (
            (
                "x402 finalized string",
                lambda payload: payload["x402"][0].update(finalized="false"),
                "x402-readback",
                "x402",
            ),
            (
                "x402 finalized alias conflict",
                lambda payload: payload["x402"][0].update(receipt={"finalized": False}),
                "x402-readback",
                "x402",
            ),
            (
                "taskmarket selfAward string",
                lambda payload: payload["taskmarket"][0]["task"].update(selfAward="true"),
                "taskmarket-readback",
                "taskmarket",
            ),
            (
                "taskmarket self_award string",
                lambda payload: payload["taskmarket"][0]["task"].update(self_award="true"),
                "taskmarket-readback",
                "taskmarket",
            ),
            (
                "taskmarket self-award alias conflict",
                lambda payload: payload["taskmarket"][0]["task"].update(
                    selfAward=True, self_award=False,
                ),
                "taskmarket-readback",
                "taskmarket",
            ),
            (
                "taskmarket awardCount bool",
                lambda payload: payload["taskmarket"][0]["task"].update(awardCount=True),
                "taskmarket-readback",
                "taskmarket",
            ),
            (
                "taskmarket award_count bool",
                lambda payload: payload["taskmarket"][0]["task"].update(award_count=False),
                "taskmarket-readback",
                "taskmarket",
            ),
            (
                "taskmarket award-count alias conflict",
                lambda payload: payload["taskmarket"][0]["task"].update(
                    awardCount=1, award_count=2,
                ),
                "taskmarket-readback",
                "taskmarket",
            ),
            (
                "taskmarket transfer_count bool",
                lambda payload: payload["taskmarket"][0]["receipt"].update(transfer_count=True),
                "taskmarket-readback",
                "taskmarket",
            ),
            (
                "taskmarket transfer-count list conflict",
                lambda payload: payload["taskmarket"][0]["receipt"].update(
                    transfer_count=1, transfers=[{}, {}],
                ),
                "taskmarket-readback",
                "taskmarket",
            ),
            (
                "x402 reorg string",
                lambda payload: payload["x402"][0].update(reorg_detected="true"),
                "x402-readback",
                "x402",
            ),
            (
                "taskmarket reorg string",
                lambda payload: payload["taskmarket"][0]["receipt"].update(reorg_detected="false"),
                "taskmarket-readback",
                "taskmarket",
            ),
        )
        for label, mutate, source_id, provider in cases:
            with self.subTest(case=label):
                payload = fixture("agent-economy-finalized.json")
                mutate(payload)
                rows = self.adapt_agent(payload)
                self.assertFalse(any(
                    row.get("record_type") == "receipt" and row.get("provider") == provider
                    for row in rows
                ))
                trailing = source_coverage(
                    rows, "agent-economy", source_id, "trailing",
                )
                self.assertEqual(
                    (trailing["coverage_state"], trailing["reason"]),
                    ("gap", "unverified_receipt"),
                )

    def test_root_reorg_boolean_type_and_alias_conflict_fail_closed(self):
        cases = (
            ("root reorg string", lambda payload: payload.update(reorg_detected="true")),
            (
                "root reorg alias conflict",
                lambda payload: payload.update(
                    reorg_detected=False, readback={"reorg_detected": True},
                ),
            ),
        )
        for label, mutate in cases:
            with self.subTest(case=label):
                payload = fixture("agent-economy-finalized.json")
                mutate(payload)
                rows = self.adapt_agent(payload)
                self.assertFalse(receipts(rows, "agent-economy"))
                for source_id in ("x402-readback", "taskmarket-readback"):
                    trailing = source_coverage(
                        rows, "agent-economy", source_id, "trailing",
                    )
                    self.assertEqual(
                        (trailing["coverage_state"], trailing["reason"]),
                        ("gap", "unverified_receipt"),
                    )

    def test_investment_boolean_types_fail_closed_on_balance_cash_flow_and_nested_paths(self):
        cases = (
            (
                "cash flow finalized string",
                lambda payload: payload["cash_flows"][0].update(
                    finalized="false", verification_state="verified",
                ),
                "alpaca-orders",
            ),
            (
                "cash flow reorg string",
                lambda payload: payload["cash_flows"][0].update(reorg_detected="false"),
                "alpaca-orders",
            ),
            (
                "outcome broker finalized string",
                lambda payload: payload["outcomes"][0]["broker"].update(finalized="false"),
                "alpaca-orders",
            ),
            (
                "outcome broker reorg string",
                lambda payload: payload["outcomes"][0]["broker"].update(reorg_detected="false"),
                "alpaca-orders",
            ),
            (
                "balance reorg string",
                lambda payload: payload["balance"].update(reorg_detected="false"),
                "alpaca-account",
            ),
        )
        for label, mutate, source_id in cases:
            with self.subTest(case=label):
                payload = fixture("investment-realized.json")
                mutate(payload)
                rows = self.adapt_investment(payload)
                if source_id == "alpaca-account":
                    self.assertFalse(any(row["record_type"] == "liquid_balance" for row in rows))
                else:
                    self.assertFalse(receipts(rows, "investment"))
                self.assertEqual(
                    source_coverage(
                        rows, "investment", source_id,
                        "as_of" if source_id == "alpaca-account" else "trailing",
                    )["reason"],
                    "unverified_receipt",
                )

        for field in ("finalized", "reorg_detected"):
            with self.subTest(source="x402-pending", field=field):
                payload = fixture("agent-economy-excluded.json")
                payload["x402"][3][field] = "false"
                rows = self.adapt_agent(payload)
                self.assertFalse(any(
                    row.get("record_type") == "receipt" and row.get("provider") == "x402"
                    for row in rows
                ))
                self.assertEqual(
                    source_coverage(
                        rows, "agent-economy", "x402-readback", "trailing",
                    )["reason"],
                    "unverified_receipt",
                )

    def test_datetime_boundary_errors_become_readback_gaps(self):
        boundary_values = (
            "0001-01-01T00:00:00+14:00",
            "9999-12-31T23:59:59-14:00",
        )
        for boundary in boundary_values:
            with self.subTest(source="agent-root", boundary=boundary):
                payload = fixture("agent-economy-finalized.json")
                payload["observed_at"] = boundary
                rows = self.adapt_agent(payload)
                self.assertFalse(receipts(rows, "agent-economy"))
                self.assertEqual(
                    {
                        row["reason"] for row in rows
                        if row.get("record_type") == "coverage"
                        and row["product_loop_id"] == "agent-economy"
                    },
                    {"read_failed"},
                )

            with self.subTest(source="investment-root", boundary=boundary):
                payload = fixture("investment-realized.json")
                payload["observed_at"] = boundary
                rows = self.adapt_investment(payload)
                self.assertFalse(receipts(rows, "investment"))
                self.assertEqual(
                    {
                        row["reason"] for row in rows
                        if row.get("record_type") == "coverage"
                        and row["product_loop_id"] == "investment"
                    },
                    {"read_failed"},
                )

        agent_rows = (
            (
                "x402 occurred underflow",
                lambda payload: payload["x402"][0].update(
                    occurred_at="0001-01-01T00:00:00+14:00",
                ),
            ),
            (
                "x402 settled overflow",
                lambda payload: payload["x402"][0].update(
                    settled_at="9999-12-31T23:59:59-14:00",
                ),
            ),
        )
        for label, mutate in agent_rows:
            with self.subTest(source="agent-row", case=label):
                payload = fixture("agent-economy-finalized.json")
                mutate(payload)
                rows = self.adapt_agent(payload)
                self.assertFalse(any(
                    row.get("record_type") == "receipt" and row.get("provider") == "x402"
                    for row in rows
                ))
                self.assertEqual(
                    source_coverage(
                        rows, "agent-economy", "x402-readback", "trailing",
                    )["reason"],
                    "unverified_receipt",
                )

        investment_rows = (
            (
                "outcome occurred underflow",
                lambda payload: payload["outcomes"][0].update(
                    occurred_at="0001-01-01T00:00:00+14:00",
                ),
            ),
            (
                "outcome settled overflow",
                lambda payload: payload["outcomes"][0].update(
                    settled_at="9999-12-31T23:59:59-14:00",
                ),
            ),
        )
        for label, mutate in investment_rows:
            with self.subTest(source="investment-row", case=label):
                payload = fixture("investment-realized.json")
                mutate(payload)
                rows = self.adapt_investment(payload)
                self.assertFalse(receipts(rows, "investment"))
                self.assertEqual(
                    source_coverage(
                        rows, "investment", "alpaca-orders", "trailing",
                    )["reason"],
                    "unverified_receipt",
                )

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
