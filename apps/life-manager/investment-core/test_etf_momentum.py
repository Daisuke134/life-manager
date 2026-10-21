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


def _benchmark_fixture(count: int = 25) -> dict[str, list[dict[str, str]]]:
    return {
        "SPY": _bars([(100, 100 + index) for index in range(count)]),
        "QQQ": _bars([(100, 100 + 2 * index) for index in range(count)]),
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
        "benchmark": {
            "symbol": "SPY",
            "method": "buy_and_hold",
            "measurement_kind": "modeled_reference_pnl",
            "status": "measured",
            "holdout": {
                "status": "measured",
                "net_pnl_usd": "0.50",
                "strategy_net_pnl_usd": "1.62",
                "excess_net_pnl_usd": "1.12",
            },
        },
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
    def test_benchmark_uses_holdout_boundaries_and_one_round_trip_cost(self):
        for notional, cost, net, excess in (
            ("10", "0.02", "2.28", "10.26"),
            ("20", "0.04", "4.56", "20.52"),
        ):
            with self.subTest(notional=notional):
                result = simulate(
                    _benchmark_fixture(), universe=("SPY", "QQQ"),
                    lookback_days=1, hold_days=2,
                    notional_usd=Decimal(notional), **_costs(),
                )

                self.assertIn("benchmark", result)
                benchmark = result["benchmark"]
                self.assertEqual(benchmark["status"], "measured")
                self.assertEqual(benchmark["measurement_kind"], "modeled_reference_pnl")
                holdout = benchmark["holdout"]
                self.assertEqual(holdout["start_date"], "2026-01-19")
                self.assertEqual(holdout["end_date"], "2026-01-24")
                self.assertEqual(holdout["cost_usd"], cost)
                self.assertEqual(holdout["net_pnl_usd"], net)
                self.assertEqual(holdout["excess_net_pnl_usd"], excess)
                self.assertEqual(holdout["outcome"], "outperformed")

    def test_benchmark_exposes_underperformance_with_positive_strategy_net(self):
        bars = {
            "SPY": _bars([(100 + index, 100 + index) for index in range(25)]),
            "QQQ": _bars([(100, 100)] * 25),
        }
        result = simulate(
            bars, universe=("SPY", "QQQ"), lookback_days=1, hold_days=2,
            notional_usd=Decimal("10"), **_costs(),
        )

        self.assertEqual(result["holdout"]["net_pnl_usd"], "0.18")
        self.assertIn("benchmark", result)
        holdout = result["benchmark"]["holdout"]
        self.assertEqual(holdout["net_pnl_usd"], "0.40")
        self.assertEqual(holdout["excess_net_pnl_usd"], "-0.22")
        self.assertEqual(holdout["outcome"], "underperformed")

    def test_missing_benchmark_symbol_is_unknown_not_zero(self):
        result = simulate(
            _fixture(), universe=UNIVERSE, lookback_days=2, hold_days=2,
            notional_usd=Decimal("10"), **_costs(),
        )

        self.assertIn("benchmark", result)
        self.assertEqual(result["benchmark"]["status"], "unknown")
        holdout = result["benchmark"]["holdout"]
        self.assertEqual(holdout["reason"], "benchmark_symbol_missing")
        self.assertIsNone(holdout["net_pnl_usd"])
        self.assertIsNone(holdout["excess_net_pnl_usd"])
        self.assertIsNone(holdout["outcome"])

    def test_measured_zero_benchmark_comparison_is_matched(self):
        bars = {symbol: _bars([(100, 100)] * 25) for symbol in ("SPY", "QQQ")}
        result = simulate(
            bars, universe=("SPY", "QQQ"), lookback_days=1, hold_days=2,
            notional_usd=Decimal("10"),
            **dict.fromkeys(_costs(), Decimal("0")),
        )

        self.assertIn("benchmark", result)
        holdout = result["benchmark"]["holdout"]
        self.assertEqual(holdout["status"], "measured")
        self.assertEqual(holdout["excess_net_pnl_usd"], "0.00")
        self.assertEqual(holdout["outcome"], "matched")

    def test_empty_benchmark_holdout_is_unknown_not_zero(self):
        for count in (3, 6):
            with self.subTest(count=count):
                result = simulate(
                    _benchmark_fixture(count), universe=("SPY", "QQQ"),
                    lookback_days=2, hold_days=2,
                    notional_usd=Decimal("10"), **_costs(),
                )

                self.assertIn("benchmark", result)
                holdout = result["benchmark"]["holdout"]
                self.assertEqual(holdout["status"], "unknown")
                self.assertEqual(holdout["reason"], "insufficient_trades")
                self.assertIsNone(holdout["net_pnl_usd"])
                self.assertIsNone(holdout["excess_net_pnl_usd"])

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
