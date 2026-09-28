from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest

from etf_momentum import (
    build_validation_report,
    screen_grid,
    simulate,
    strategy_card,
)
from strategy_cards import validate_strategy_card
from strategy_validation import select_strategy


UNIVERSE = ("A", "B", "C")


def _bars(values: list[tuple[float, float]]) -> list[dict[str, str]]:
    start = date(2026, 1, 1)
    return [
        {
            "t": (start + timedelta(days=index)).isoformat() + "T00:00:00Z",
            "o": str(open_price),
            "c": str(close),
        }
        for index, (open_price, close) in enumerate(values)
    ]


def _fixture() -> dict[str, list[dict[str, str]]]:
    return {
        "A": _bars([(100, 100), (100, 100), (100, 120), (50, 55), (55, 60), (60, 60)]),
        "B": _bars([(100, 100), (100, 101), (100, 101), (100, 101), (100, 101), (100, 101)]),
        "C": _bars([(100, 100), (100, 100), (100, 100), (100, 100), (100, 100), (100, 100)]),
    }


def _costs() -> dict[str, Decimal]:
    return {
        "entry_fee_bps": Decimal("0"),
        "exit_fee_bps": Decimal("0"),
        "entry_slippage_bps": Decimal("10"),
        "exit_slippage_bps": Decimal("10"),
    }


def _measured_result() -> dict[str, object]:
    summary = {
        "trades": 40,
        "gross_pnl_usd": "3.00",
        "cost_usd": "0.80",
        "net_pnl_usd": "2.20",
        "max_drawdown_usd": "2.72",
    }
    return {
        "status": "measured",
        "decision": "measured",
        "reason": None,
        "data_quality": {"common_sessions": 1551},
        "trades": [{"net_pnl_usd": "0.10"}],
        "train": summary,
        "validation": {**summary, "trades": 13, "net_pnl_usd": "2.21"},
        "holdout": {
            **summary,
            "trades": 14,
            "net_pnl_usd": "1.62",
            "max_drawdown_usd": "1.25",
        },
    }


def _passing_grid() -> dict[str, object]:
    return {
        "gate": True,
        "positive_count": 9,
        "median_holdout_net_pnl_usd": "1.62",
        "grid": [],
    }


class EtfMomentumTests(unittest.TestCase):
    def test_signal_waits_for_full_lookback_and_enters_next_open(self):
        result = simulate(
            _fixture(), universe=UNIVERSE, lookback_days=2, hold_days=2,
            notional_usd=Decimal("10"), **_costs(),
        )

        first = result["trades"][0]
        self.assertEqual(first["decision_date"], "2026-01-03")
        self.assertEqual(first["symbol"], "A")
        self.assertEqual(first["entry_price"], "50.00")
        self.assertEqual(first["exit_price"], "60.00")
        self.assertEqual(first["gross_pnl_usd"], "2.00")

    def test_declared_costs_are_subtracted_from_net(self):
        result = simulate(
            _fixture(), universe=UNIVERSE, lookback_days=2, hold_days=2,
            notional_usd=Decimal("10"), entry_fee_bps=Decimal("10"),
            exit_fee_bps=Decimal("10"), entry_slippage_bps=Decimal("10"),
            exit_slippage_bps=Decimal("10"),
        )

        first = result["trades"][0]
        self.assertEqual(first["cost_usd"], "0.04")
        self.assertEqual(first["net_pnl_usd"], "1.96")

    def test_duplicate_session_is_rejected(self):
        bars = _fixture()
        bars["A"][1]["t"] = bars["A"][0]["t"]

        with self.assertRaisesRegex(ValueError, "^duplicate_session$"):
            simulate(
                bars, universe=UNIVERSE, lookback_days=2, hold_days=2,
                notional_usd=Decimal("10"), **_costs(),
            )

    def test_missing_symbol_is_rejected(self):
        bars = _fixture()
        del bars["C"]

        with self.assertRaisesRegex(ValueError, "^symbol_missing:C$"):
            simulate(
                bars, universe=UNIVERSE, lookback_days=2, hold_days=2,
                notional_usd=Decimal("10"), **_costs(),
            )

    def test_empty_holdout_is_rejected_not_zero_profit(self):
        result = simulate(
            _fixture(), universe=UNIVERSE, lookback_days=2, hold_days=2,
            notional_usd=Decimal("10"), **_costs(),
        )

        self.assertEqual(result["decision"], "rejected")
        self.assertEqual(result["reason"], "insufficient_trades")
        self.assertEqual(result["holdout"]["trades"], 0)

    def test_grid_is_fixed_and_reports_all_nine_neighbors(self):
        values = [(100 + index, 100 + index) for index in range(240)]
        bars = {symbol: _bars(values) for symbol in UNIVERSE}

        result = screen_grid(
            bars, universe=UNIVERSE, lookbacks=(84, 126, 168),
            hold_days=(15, 21, 30), notional_usd=Decimal("10"), **_costs(),
        )

        self.assertEqual(len(result["grid"]), 9)
        self.assertLess(result["positive_count"], 9)
        self.assertEqual(result["gate"], False)

    def test_unknown_cost_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "^cost_invalid$"):
            simulate(
                _fixture(), universe=UNIVERSE, lookback_days=2, hold_days=2,
                notional_usd=Decimal("10"), entry_fee_bps="unknown",
                exit_fee_bps=Decimal("0"), entry_slippage_bps=Decimal("10"),
                exit_slippage_bps=Decimal("10"),
            )

    def test_research_card_declares_universe_window_and_costs(self):
        card = strategy_card()

        self.assertEqual(validate_strategy_card(card), ())
        self.assertEqual(card.strategy_id, "alpaca-etf-126d-momentum-v1")
        self.assertEqual(tuple(card.instruments), (
            "SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "GLD",
        ))
        self.assertEqual(card.timeframe, "1d")
        self.assertEqual(card.status, "research")

    def test_validation_report_can_enter_deterministic_selection(self):
        report = build_validation_report(
            strategy_card(), _measured_result(), _passing_grid(),
            release_sha="a" * 40,
            report_id="alpaca-etf-126d-momentum-v1-20260929",
            evidence_ids=["alpaca-paper://etf/20260929/83d5"],
            observed_at="2026-09-28T16:15:54Z",
        )

        self.assertEqual(report["decision"], "paper")
        selected = select_strategy([report])
        self.assertEqual(selected["strategy_id"], "alpaca-etf-126d-momentum-v1")

    def test_validation_report_rejects_incomplete_neighbor_gate(self):
        grid = {**_passing_grid(), "gate": False, "positive_count": 4}

        report = build_validation_report(
            strategy_card(), _measured_result(), grid,
            release_sha="a" * 40,
            report_id="alpaca-etf-126d-momentum-v1-rejected",
            evidence_ids=["alpaca-paper://etf/20260929/rejected"],
            observed_at="2026-09-28T16:15:54Z",
        )

        self.assertEqual(report["decision"], "rejected")
        self.assertIn("parameter_sensitivity", report["failed_gates"])


if __name__ == "__main__":
    unittest.main()
