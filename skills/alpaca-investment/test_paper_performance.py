from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import paper_performance
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
            "recorded_at": "2026-09-29T14:30:00Z",
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
            "recorded_at": "2026-10-20T14:31:00Z",
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


def _prior_rows() -> list[dict]:
    replacements = {
        "entry-effect": "prior-entry-effect",
        "exit-effect": "prior-exit-effect",
        "paper-entry": "prior-paper-entry",
        "paper-exit": "prior-paper-exit",
        "lm-ai-" + "a" * 24: "lm-ai-" + "c" * 24,
        "lm-ai-" + "b" * 24: "lm-ai-" + "d" * 24,
        "alpaca://bars/entry": "alpaca://bars/prior-entry",
        "alpaca://bars/exit": "alpaca://bars/prior-exit",
        "2026-09-29": "2026-09-20",
        "2026-10-20": "2026-09-22",
    }

    def replace(value):
        if isinstance(value, str):
            for old, new in replacements.items():
                value = value.replace(old, new)
            return value
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        return value

    return replace(_rows())


OBSERVATION = {
    "mode": "paper",
    "paper": True,
    "account": {"cash": "100000.25", "equity": "100000.25"},
    "clock": {"observed_at": "2026-10-20T14:31:10Z"},
    "positions": [],
}
RISK = {"drawdown_usd": "0.00"}


def _broker_cost_evidence() -> dict:
    return {
        "broker_costs_status": "partial",
        "broker_costs_reason": "paper_regulatory_fees_not_simulated",
        "broker_fees_status": "not_simulated",
        "broker_fees_usd": None,
        "broker_slippage_status": "complete",
        "broker_gross_pnl_usd": "0.250",
        "broker_slippage_usd": "-0.005",
        "owner_id": OWNER,
        "mode": "paper",
        "paper": True,
        "observed_at": "2026-10-20T14:31:15Z",
        "order_ids": ["paper-entry", "paper-exit"],
        "period_start": "2026-09-29T14:30:00Z",
        "provider": "alpaca",
        "provider_readback": {
            "fills": [
                {"id": "fill-entry", "activity_type": "FILL", "order_id": "paper-entry",
                 "symbol": "QQQ", "side": "buy", "qty": "0.025", "price": "400",
                 "transaction_time": "2026-09-29T14:31:05Z"},
                {"id": "fill-exit", "activity_type": "FILL", "order_id": "paper-exit",
                 "symbol": "QQQ", "side": "sell", "qty": "0.025", "price": "410",
                 "transaction_time": "2026-10-20T14:31:05Z"},
            ],
            "quotes_by_fill_id": {
                "fill-entry": {"t": "2026-09-29T14:31:05Z", "bp": "400", "ap": "400"},
                "fill-exit": {"t": "2026-10-20T14:31:04Z", "bp": "409.79", "ap": "409.81"},
            },
        },
        "source_receipt_ids": [
            "fill-entry", "fill-exit",
            "alpaca-quote:fill-entry:2026-09-29T14:31:05Z",
            "alpaca-quote:fill-exit:2026-10-20T14:31:04Z",
        ],
    }


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

    def test_legacy_orderless_lifecycle_rows_reuse_the_planned_order(self):
        rows = _rows()
        client_order_id = "lm-ai-" + "a" * 24
        rows[0]["decision_id"] = "entry-decision"
        lifecycle = [
            {
                "client_order_id": client_order_id,
                "decision_id": "entry-decision",
                "effect_id": "entry-effect",
                "mode": "paper",
                "paper": True,
                "receipt_type": "effect_intent",
                "recorded_at": "2026-09-29T14:30:10Z",
                "schema_version": 1,
                "status": "started",
            },
            {
                "client_order_id": client_order_id,
                "effect_id": "entry-effect",
                "mode": "paper",
                "paper": True,
                "receipt_type": "effect_intent",
                "recorded_at": "2026-09-29T14:30:11Z",
                "schema_version": 1,
                "status": "applied",
            },
            {
                "broker_status": "accepted",
                "client_order_id": client_order_id,
                "effect_id": "entry-effect",
                "mode": "paper",
                "paper": True,
                "receipt_type": "effect_intent",
                "recorded_at": "2026-09-29T14:30:12Z",
                "schema_version": 1,
                "status": "reconciliation_pending",
            },
        ]
        rows[1:1] = lifecycle

        result = build_paper_performance(rows, OBSERVATION, RISK)

        self.assertEqual(result.get("measurement_status"), "partial")
        self.assertEqual(result["completed_round_trips"], 1)
        self.assertEqual(result["gross_strategy_pnl_usd"], "0.250")

    def test_same_filled_order_readback_can_add_its_strategy_receipt(self):
        rows = _rows()
        accepted = copy.deepcopy(rows[1])
        accepted["broker"] = {
            **accepted["broker"], "status": "accepted", "filled_qty": "0",
        }
        accepted.pop("strategy_receipt")
        legacy_fill = copy.deepcopy(rows[1])
        legacy_fill.pop("strategy_receipt")
        legacy_fill["broker_status"] = "filled"
        legacy_fill["broker_receipt_id"] = "paper-entry-activity"
        rows = [rows[0], accepted, legacy_fill, rows[1], *rows[2:]]

        result = build_paper_performance(rows, OBSERVATION, RISK)

        self.assertEqual(result.get("measurement_status"), "partial")
        self.assertEqual(result["completed_round_trips"], 1)
        self.assertEqual(result["gross_strategy_pnl_usd"], "0.250")

    def test_orderless_lifecycle_without_a_planned_intent_stays_invalid(self):
        orphan = {
            "effect_id": "orphan-effect",
            "mode": "paper",
            "paper": True,
            "receipt_type": "effect_intent",
            "status": "started",
        }

        result = build_paper_performance([orphan], OBSERVATION, RISK)

        self.assertEqual(result, {
            "status": "unknown",
            "reason": "paper_intent_invalid",
        })

    def test_duplicate_outcome_for_same_effect_fails_closed(self):
        rows = _rows()
        conflicting = copy.deepcopy(rows[1])
        conflicting["broker"]["filled_avg_price"] = "401"
        rows.insert(2, conflicting)

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
        self.assertIsNone(result["model_cost_usd"])
        self.assertIsNone(result["system_cost_usd"])
        self.assertIsNone(result["net_realized_pnl_usd"])
        self.assertEqual(result["unknown_cost_categories"], [
            "fees", "slippage", "model", "system",
        ])
        self.assertEqual(result["source_receipt_ids"], [
            "alpaca://bars/entry", "alpaca-order:paper-entry",
            "alpaca://bars/exit", "alpaca-order:paper-exit",
        ])

    def test_execution_evidence_keeps_unsimulated_and_unallocated_costs_unknown(self):
        result = build_paper_performance(
            _rows(), OBSERVATION, RISK, broker_cost_evidence=[_broker_cost_evidence()],
        )

        self.assertIsNone(result["fees_usd"])
        self.assertEqual(result["slippage_usd"], "-0.005")
        self.assertEqual(result["broker_costs_status"], "partial")
        self.assertEqual(result["costs_status"], "partial")
        self.assertTrue(result["slippage_included_in_gross_pnl"])
        self.assertIsNone(result["model_cost_usd"])
        self.assertIsNone(result["system_cost_usd"])
        self.assertIsNone(result["net_realized_pnl_usd"])
        self.assertEqual(result["unknown_cost_categories"], ["fees", "model", "system"])
        self.assertIn("fill-entry", result["source_receipt_ids"])

    def test_broker_cost_receipt_for_another_order_pair_is_not_joined(self):
        evidence = _broker_cost_evidence()
        evidence["order_ids"] = ["buy-other", "sell-other"]

        result = build_paper_performance(
            _rows(), OBSERVATION, RISK, broker_cost_evidence=[evidence],
        )

        self.assertIsNone(result["fees_usd"])
        self.assertIsNone(result["slippage_usd"])
        self.assertEqual(result["broker_costs_status"], "unknown")
        self.assertEqual(result["unknown_cost_categories"], [
            "fees", "slippage", "model", "system",
        ])

    def test_broker_cost_receipt_from_another_owner_or_mode_is_not_joined(self):
        evidence = _broker_cost_evidence()
        evidence.update({"owner_id": "alpaca-investment-live", "mode": "live", "paper": False})

        result = build_paper_performance(
            _rows(), OBSERVATION, RISK, broker_cost_evidence=[evidence],
        )

        self.assertEqual(result["broker_costs_status"], "unknown")
        self.assertIsNone(result["fees_usd"])
        self.assertIsNone(result["slippage_usd"])

    def test_execution_evidence_must_not_claim_paper_regulatory_fees(self):
        evidence = _broker_cost_evidence()
        evidence["broker_fees_usd"] = "0.02"

        result = build_paper_performance(
            _rows(), OBSERVATION, RISK, broker_cost_evidence=[evidence],
        )

        self.assertEqual(result["broker_costs_status"], "unknown")
        self.assertEqual(result["broker_costs_reason"], "paper_cost_receipt_mismatch")
        self.assertIsNone(result["fees_usd"])

    def test_broker_slippage_total_must_match_official_fill_and_quote_rows(self):
        evidence = _broker_cost_evidence()
        evidence["broker_slippage_usd"] = "-0.006"

        result = build_paper_performance(
            _rows(), OBSERVATION, RISK, broker_cost_evidence=[evidence],
        )

        self.assertEqual(result["broker_costs_status"], "unknown")
        self.assertEqual(result["broker_costs_reason"], "paper_cost_receipt_mismatch")
        self.assertIsNone(result["slippage_usd"])

    def test_broker_cost_receipt_from_a_different_period_is_not_joined(self):
        evidence = _broker_cost_evidence()
        evidence["period_start"] = "2026-10-01T14:31:05Z"

        result = build_paper_performance(
            _rows(), OBSERVATION, RISK, broker_cost_evidence=[evidence],
        )

        self.assertIsNone(result["fees_usd"])
        self.assertIsNone(result["slippage_usd"])
        self.assertEqual(result["broker_costs_status"], "unknown")

    def test_broker_fill_prices_must_match_the_owner_order_ledger(self):
        evidence = _broker_cost_evidence()
        readback = evidence["provider_readback"]
        readback["fills"][0]["price"] = "500"
        readback["fills"][1]["price"] = "510"
        readback["quotes_by_fill_id"]["fill-entry"].update({"bp": "500", "ap": "500"})
        readback["quotes_by_fill_id"]["fill-exit"].update({"bp": "509.79", "ap": "509.81"})

        result = build_paper_performance(
            _rows(), OBSERVATION, RISK, broker_cost_evidence=[evidence],
        )

        self.assertEqual(result["broker_costs_status"], "unknown")
        self.assertEqual(result["broker_costs_reason"], "paper_cost_receipt_mismatch")
        self.assertIsNone(result["fees_usd"])
        self.assertIsNone(result["slippage_usd"])

    def test_writer_reuses_validated_execution_readback_for_the_same_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "receipts.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in _rows()), encoding="utf-8",
            )
            from unittest.mock import Mock
            reader_receipt = _broker_cost_evidence()
            reader_receipt.pop("owner_id")
            reader_receipt.pop("mode")
            reader_receipt.pop("paper")
            reader = Mock(return_value=reader_receipt)

            first = write_paper_performance(
                state, OBSERVATION, RISK, broker_cost_reader=reader,
            )
            second = write_paper_performance(
                state, OBSERVATION, RISK, broker_cost_reader=reader,
            )
            saved = json.loads(next(state.glob("performance-cost-*.json")).read_text(encoding="utf-8"))

        self.assertEqual(reader.call_count, 1)
        self.assertIsNone(first["fees_usd"])
        self.assertIsNone(second["fees_usd"])
        self.assertEqual(saved["owner_id"], OWNER)
        self.assertEqual(saved["mode"], "paper")
        self.assertIs(saved["paper"], True)

    def test_writer_refreshes_saved_cost_receipt_with_wrong_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "receipts.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in _rows()), encoding="utf-8",
            )
            digest = hashlib.sha256(
                "\0".join(sorted(["paper-entry", "paper-exit"])).encode("utf-8")
            ).hexdigest()[:20]
            stale = _broker_cost_evidence()
            stale.update({"owner_id": "alpaca-investment-live", "mode": "live", "paper": False})
            (state / f"performance-cost-{digest}.json").write_text(
                json.dumps(stale), encoding="utf-8",
            )
            reader_receipt = _broker_cost_evidence()
            reader_receipt.pop("owner_id")
            reader_receipt.pop("mode")
            reader_receipt.pop("paper")
            from unittest.mock import Mock
            reader = Mock(return_value=reader_receipt)

            result = write_paper_performance(
                state, OBSERVATION, RISK, broker_cost_reader=reader,
            )
            saved = json.loads(
                (state / f"performance-cost-{digest}.json").read_text(encoding="utf-8"),
            )

        self.assertEqual(reader.call_count, 1)
        self.assertEqual(result["broker_costs_status"], "partial")
        self.assertIsNone(result["fees_usd"])
        self.assertEqual(saved["owner_id"], OWNER)
        self.assertEqual(saved["mode"], "paper")
        self.assertIs(saved["paper"], True)

    def test_invalid_cached_receipt_gets_one_same_day_refresh_past_old_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "receipts.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in _rows()), encoding="utf-8",
            )
            digest = hashlib.sha256(
                "\0".join(sorted(["paper-entry", "paper-exit"])).encode("utf-8")
            ).hexdigest()[:20]
            stale = _broker_cost_evidence()
            stale.update({"owner_id": "alpaca-investment-live", "mode": "live", "paper": False})
            (state / f"performance-cost-{digest}.json").write_text(
                json.dumps(stale), encoding="utf-8",
            )
            attempt_path = state / f"performance-cost-attempt-{digest}.json"
            attempt_path.write_text(json.dumps({
                "attempted_at": "2026-10-20T13:00:00Z",
                "attempted_day": "2026-10-20",
                "order_ids": ["paper-entry", "paper-exit"],
                "owner_id": OWNER,
                "status": "unknown",
            }), encoding="utf-8")
            from unittest.mock import Mock
            reader = Mock(side_effect=ValueError("paper_cost_receipt_invalid"))

            first = write_paper_performance(
                state, OBSERVATION, RISK, broker_cost_reader=reader,
            )
            second = write_paper_performance(
                state, OBSERVATION, RISK, broker_cost_reader=reader,
            )
            attempt = json.loads(attempt_path.read_text(encoding="utf-8"))

        self.assertEqual(reader.call_count, 1)
        self.assertEqual(first["broker_costs_status"], "unknown")
        self.assertEqual(second["broker_costs_status"], "unknown")
        self.assertTrue(attempt["invalid_cached_receipt_refresh_attempted"])

    def test_daily_writer_joins_only_cost_receipts_for_trips_closed_that_day(self):
        def reader(*, orders, period_start):
            tag = "prior" if orders[0]["id"] == "prior-paper-entry" else "current"
            trip = next(
                item for item in paper_performance._closed_round_trips([*_prior_rows(), *_rows()])[0]
                if item["order_ids"] == [order["id"] for order in orders]
            )
            evidence = _broker_cost_evidence()
            buy_fill, sell_fill = f"{tag}-buy-fill", f"{tag}-sell-fill"
            readback = evidence["provider_readback"]
            entry_day = "2026-09-20" if tag == "prior" else "2026-09-29"
            exit_day = "2026-09-22" if tag == "prior" else "2026-10-20"
            entry_time = f"{entry_day}T14:31:05Z"
            exit_time = f"{exit_day}T14:31:05Z"
            readback["fills"] = [
                {"id": buy_fill, "activity_type": "FILL", "order_id": orders[0]["id"],
                 "symbol": "QQQ", "side": "buy", "qty": "0.025", "price": "400",
                 "transaction_time": entry_time},
                {"id": sell_fill, "activity_type": "FILL", "order_id": orders[1]["id"],
                 "symbol": "QQQ", "side": "sell", "qty": "0.025", "price": "410",
                 "transaction_time": exit_time},
            ]
            readback["quotes_by_fill_id"] = {
                buy_fill: {"t": entry_time, "bp": "400", "ap": "400"},
                sell_fill: {
                    "t": exit_time.replace("14:31:05", "14:31:04"),
                    "bp": "409.79", "ap": "409.81",
                },
            }
            evidence.update({
                "broker_gross_pnl_usd": str(trip["gross_pnl_usd"]),
                "observed_at": "2026-09-23T14:31:15Z" if tag == "prior"
                else "2026-10-20T14:31:15Z",
                "order_ids": [order["id"] for order in orders],
                "period_start": period_start,
                "source_receipt_ids": [
                    buy_fill, sell_fill,
                    f"alpaca-quote:{buy_fill}:{entry_time}",
                    f"alpaca-quote:{sell_fill}:{exit_time.replace('14:31:05', '14:31:04')}",
                ],
            })
            return evidence

        rows = [*_prior_rows(), *_rows()]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "receipts.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8",
            )
            result = write_paper_performance(
                state, OBSERVATION, RISK, broker_cost_reader=reader,
            )

        self.assertEqual(result["completed_round_trips_total"], 2)
        self.assertEqual(result["completed_round_trips"], 1)
        self.assertEqual(result["broker_costs_status"], "partial")
        self.assertIsNone(result["fees_usd"])
        self.assertEqual(result["broker_cost_source_receipt_ids"][0], "current-buy-fill")
        self.assertNotIn("prior-buy-fill", result["broker_cost_source_receipt_ids"])

    def test_writer_retries_failed_broker_readback_only_on_a_later_et_day(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "receipts.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in _rows()), encoding="utf-8",
            )
            from unittest.mock import Mock
            reader = Mock(side_effect=ValueError("paper_cost_quote_invalid"))

            first = write_paper_performance(
                state, OBSERVATION, RISK, broker_cost_reader=reader,
            )
            second = write_paper_performance(
                state, OBSERVATION, RISK, broker_cost_reader=reader,
            )
            next_day = copy.deepcopy(OBSERVATION)
            next_day["clock"]["observed_at"] = "2026-10-21T14:31:10Z"
            write_paper_performance(state, next_day, RISK, broker_cost_reader=reader)

        self.assertEqual(reader.call_count, 2)
        self.assertEqual(first["broker_costs_reason"], "paper_cost_quote_invalid")
        self.assertEqual(second["broker_costs_errors"][0]["next_action"], "retry_after_next_et_day")

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
