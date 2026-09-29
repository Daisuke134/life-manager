from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from paper_performance import build_paper_performance, write_paper_performance


OWNER = "alpaca-investment-paper"
STRATEGY = "alpaca-etf-126d-momentum-v1"


def _strategy_receipt(provider_order_id: str, observed_at: str, positions: list[dict]) -> dict:
    return {
        "account_readback": {
            "account": {"cash": "100000", "equity": "100000"},
            "clock": {"observed_at": observed_at},
            "positions": positions,
        },
        "receipt": {
            "owner_id": OWNER,
            "provider_order_id": provider_order_id,
        },
    }


def _rows() -> list[dict]:
    return [
        {
            "receipt_type": "effect_intent",
            "effect_id": "entry-effect",
            "status": "planned",
            "mode": "paper",
            "paper": True,
            "owner_id": OWNER,
            "strategy_id": STRATEGY,
            "client_order_id": "lm-ai-" + "a" * 24,
            "source_receipt_ids": ["alpaca://bars/entry"],
            "order": {
                "asset_class": "us_equity", "side": "buy", "symbol": "QQQ",
            },
        },
        {
            "receipt_type": "outcome",
            "effect_id": "entry-effect",
            "outcome": "broker_reconciled",
            "mode": "paper",
            "paper": True,
            "recorded_at": "2026-09-29T14:31:05Z",
            "broker": {
                "id": "paper-entry",
                "client_order_id": "lm-ai-" + "a" * 24,
                "status": "filled",
                "symbol": "QQQ",
                "side": "buy",
                "filled_qty": "0.025",
                "filled_avg_price": "400",
            },
            "strategy_receipt": _strategy_receipt(
                "paper-entry", "2026-09-29T14:31:05Z",
                [{"symbol": "QQQ", "qty": "0.025"}],
            ),
        },
        {
            "receipt_type": "effect_intent",
            "effect_id": "exit-effect",
            "status": "planned",
            "mode": "paper",
            "paper": True,
            "owner_id": OWNER,
            "strategy_id": STRATEGY,
            "client_order_id": "lm-ai-" + "b" * 24,
            "source_receipt_ids": ["alpaca://bars/exit"],
            "order": {
                "asset_class": "us_equity", "side": "sell", "symbol": "QQQ",
            },
        },
        {
            "receipt_type": "outcome",
            "effect_id": "exit-effect",
            "outcome": "broker_reconciled",
            "mode": "paper",
            "paper": True,
            "recorded_at": "2026-10-20T14:31:05Z",
            "broker": {
                "id": "paper-exit",
                "client_order_id": "lm-ai-" + "b" * 24,
                "status": "filled",
                "symbol": "QQQ",
                "side": "sell",
                "filled_qty": "0.025",
                "filled_avg_price": "410",
            },
            "strategy_receipt": _strategy_receipt(
                "paper-exit", "2026-10-20T14:31:05Z", [],
            ),
        },
    ]


def _cost_rows() -> list[dict]:
    rows = _rows()
    rows[0]["decision_id"] = "entry-decision"
    rows[2]["decision_id"] = "exit-decision"
    return [
        {
            "receipt_type": "decision", "decision_id": "entry-decision",
            "decision": {
                "execution_quote": {"bid": "399", "ask": "399", "quote_at": "2026-09-29T14:31:00Z"},
                "model_cost_usd": "0.01",
                "model_cost_source": "deterministic_etf_policy",
            },
        },
        {
            "receipt_type": "decision", "decision_id": "exit-decision",
            "decision": {
                "execution_quote": {"bid": "411", "ask": "411", "quote_at": "2026-10-20T14:31:00Z"},
                "model_cost_usd": "0.01",
                "model_cost_source": "deterministic_etf_policy",
            },
        },
        *rows,
    ]


OBSERVATION = {
    "mode": "paper",
    "paper": True,
    "account": {"cash": "100000.25", "equity": "100000.25"},
    "clock": {"observed_at": "2026-10-20T14:31:10Z"},
    "positions": [],
}
RISK = {"drawdown_usd": "0.00"}


class PaperPerformanceTests(unittest.TestCase):
    def test_pending_order_never_emits_numeric_pnl(self):
        rows = _rows()
        rows.pop(1)
        rows[0]["status"] = "reconciliation_pending"

        result = build_paper_performance(rows, OBSERVATION, RISK)

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "paper_effect_unresolved",
        })

    def test_legacy_accepted_outcome_is_superseded_by_later_filled_receipt(self):
        rows = _rows()
        accepted = copy.deepcopy(rows[1])
        accepted["broker"] = {
            **accepted["broker"], "status": "accepted", "filled_qty": "0",
        }
        accepted.pop("strategy_receipt")
        rows = [rows[0], accepted, rows[1], *rows[2:]]

        result = build_paper_performance(rows, OBSERVATION, RISK)

        self.assertEqual(result["completed_round_trips"], 1)
        self.assertEqual(result["gross_strategy_pnl_usd"], "0.250")

    def test_duplicate_outcome_for_same_effect_fails_closed(self):
        rows = _rows()
        rows.insert(2, copy.deepcopy(rows[1]))

        result = build_paper_performance(rows, OBSERVATION, RISK)

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "paper_receipt_duplicate",
        })

    def test_zero_fill_terminal_failure_is_not_a_pnl_event(self):
        failed_intent = {
            "receipt_type": "effect_intent",
            "effect_id": "failed-effect",
            "status": "applied",
            "mode": "paper",
            "paper": True,
            "owner_id": OWNER,
            "strategy_id": STRATEGY,
            "client_order_id": "lm-ai-" + "c" * 24,
            "source_receipt_ids": ["alpaca://bars/failed"],
            "order": {"asset_class": "us_equity", "side": "buy", "symbol": "SPY"},
        }
        failed_outcome = {
            "receipt_type": "outcome",
            "effect_id": "failed-effect",
            "outcome": "broker_terminal_failure",
            "mode": "paper",
            "paper": True,
            "recorded_at": "2026-09-29T14:00:00Z",
            "broker": {
                "id": "paper-failed", "client_order_id": "lm-ai-" + "c" * 24,
                "status": "canceled", "symbol": "SPY", "side": "buy",
                "filled_qty": "0",
            },
        }

        result = build_paper_performance(
            [failed_intent, failed_outcome, *_rows()], OBSERVATION, RISK
        )

        self.assertEqual(result["completed_round_trips"], 1)
        self.assertEqual(result["gross_strategy_pnl_usd"], "0.250")

    def test_closed_round_trip_emits_gross_but_keeps_costs_unknown(self):
        result = build_paper_performance(_rows(), OBSERVATION, RISK)

        self.assertEqual(result["measurement_status"], "partial")
        self.assertEqual(result["reason"], "paper_costs_unknown")
        self.assertEqual(result["completed_round_trips"], 1)
        self.assertEqual(result["gross_strategy_pnl_usd"], "0.250")
        self.assertIsNone(result["fees_usd"])
        self.assertIsNone(result["slippage_usd"])
        self.assertEqual(result["source_receipt_ids"], [
            "alpaca://bars/entry", "alpaca-order:paper-entry",
            "alpaca://bars/exit", "alpaca-order:paper-exit",
        ])

    def test_official_costs_and_execution_quotes_produce_cost_complete_net_pnl(self):
        result = build_paper_performance(
            _cost_rows(), OBSERVATION, RISK,
            cost_readback={
                "status": "complete",
                "fees_by_client_order_id": {
                    "lm-ai-" + "a" * 24: "0.01",
                    "lm-ai-" + "b" * 24: "0.02",
                },
                "source_receipt_ids": ["alpaca-fee:entry", "alpaca-fee:exit"],
            },
        )

        self.assertEqual(result["measurement_status"], "measured")
        self.assertEqual(result["costs_status"], "complete")
        self.assertEqual(result["fees_usd"], "0.03")
        self.assertEqual(result["slippage_usd"], "0.05")
        self.assertEqual(result["model_cost_usd"], "0.02")
        self.assertEqual(result["net_pnl_usd"], "0.15")

    def test_open_or_unresolved_round_trip_does_not_emit_numeric_pnl(self):
        rows = _rows()
        rows.pop()
        result = build_paper_performance(rows, OBSERVATION, RISK)

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "paper_effect_unresolved",
        })

    def test_duplicate_provider_receipt_fails_closed(self):
        rows = _rows()
        duplicate = copy.deepcopy(rows[1])
        duplicate["effect_id"] = "duplicate-entry-effect"
        rows.insert(2, duplicate)

        result = build_paper_performance(rows, OBSERVATION, RISK)

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "paper_receipt_duplicate",
        })

    def test_missing_official_account_readback_fails_closed(self):
        rows = _rows()
        rows[1].pop("strategy_receipt")

        result = build_paper_performance(rows, OBSERVATION, RISK)

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "paper_strategy_receipt_missing",
        })

    def test_write_only_writes_a_closed_paper_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "receipts.jsonl"
            ledger.write_text("".join(json.dumps(row) + "\n" for row in _rows()))

            result = write_paper_performance(state, OBSERVATION, RISK)

            self.assertEqual(result["completed_round_trips"], 1)
            path = state / "performance-latest.json"
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text())["gross_strategy_pnl_usd"], "0.250")

    def test_repeated_daily_observation_reports_delta_without_repeating_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "receipts.jsonl"
            ledger.write_text("".join(json.dumps(row) + "\n" for row in _rows()))

            first = write_paper_performance(state, OBSERVATION, RISK)
            later_observation = copy.deepcopy(OBSERVATION)
            later_observation["clock"]["observed_at"] = "2026-10-21T14:31:10Z"
            second = write_paper_performance(state, later_observation, RISK)

            self.assertEqual(first["gross_strategy_pnl_usd"], "0.250")
            self.assertEqual(second["gross_strategy_pnl_usd"], "0")
            self.assertEqual(second["completed_round_trips"], 0)
            self.assertEqual(second["completed_round_trips_total"], 1)
            self.assertNotEqual(first["source_receipt_ids"], second["source_receipt_ids"])

    def test_repeated_paper_wake_keeps_same_day_pnl_until_daily_consumer_reads_it(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            ledger = state / "receipts.jsonl"
            ledger.write_text("".join(json.dumps(row) + "\n" for row in _rows()))

            first = write_paper_performance(state, OBSERVATION, RISK)
            later_observation = copy.deepcopy(OBSERVATION)
            later_observation["clock"]["observed_at"] = "2026-10-20T14:31:20Z"
            second = write_paper_performance(state, later_observation, RISK)

            self.assertEqual(first["gross_strategy_pnl_usd"], "0.250")
            self.assertEqual(second["gross_strategy_pnl_usd"], "0.250")
            self.assertEqual(second["completed_round_trips"], 1)
            self.assertEqual(second["completed_round_trips_total"], 1)
            self.assertNotEqual(first["source_receipt_ids"], second["source_receipt_ids"])
            self.assertEqual(
                json.loads((state / "performance-daily-2026-10-20.json").read_text())["gross_strategy_pnl_usd"],
                "0.250",
            )


if __name__ == "__main__":
    unittest.main()
