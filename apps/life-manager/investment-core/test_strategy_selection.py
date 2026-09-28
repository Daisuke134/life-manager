from __future__ import annotations

import unittest

from strategy_validation import select_strategy


def _card(strategy_id: str) -> dict:
    return {
        "strategy_id": strategy_id,
        "venue": "alpaca",
        "instruments": ["BTC/USDC"],
        "timeframe": "5m",
        "entry_rules": {"all": ["close > 100"]},
        "exit_rules": {"any": ["close < 100"]},
        "sizing_rule": {"notional_usd": "100.00"},
        "cost_model": {
            "entry_fee_bps": "25.00",
            "exit_fee_bps": "25.00",
            "entry_slippage_bps": "5.00",
            "exit_slippage_bps": "5.00",
        },
        "risk_limits": {"max_drawdown_usd": "20.00"},
        "kill_conditions": ["stale_quote", "effect_unknown"],
        "evidence_refs": [f"https://example.test/{strategy_id}"],
        "status": "research",
    }


def _report(
    strategy_id: str,
    *,
    report_id: str | None = None,
    net: str = "12.00",
    drawdown: str = "2.00",
    turnover: str = "0.50",
    release_sha: str | None = None,
    evidence_ids: list[str] | None = None,
    **overrides,
) -> dict:
    card = _card(strategy_id)
    value = {
        "report_id": report_id or f"report-{strategy_id}",
        "strategy_id": strategy_id,
        "release_sha": release_sha or "a" * 40,
        "card": card,
        "status": "measured",
        "decision": "paper",
        "lookahead_detected": False,
        "holdout": {
            "trades": 3,
            "net_pnl_usd": net,
            "max_drawdown_usd": drawdown,
        },
        "cost_model": card["cost_model"],
        "turnover": turnover,
        "evidence_ids": evidence_ids or [f"evidence-{strategy_id}"],
        "model_score": 0,
    }
    value.update(overrides)
    return value


class StrategySelectionTests(unittest.TestCase):
    def test_selects_one_candidate_by_holdout_then_ignores_model_score(self):
        selected = select_strategy([
            _report("candidate-a", net="12.00", model_score=-999),
            _report("candidate-b", net="99.00", model_score=999, report_id="report-b"),
        ])

        self.assertEqual(selected["strategy_id"], "candidate-b")
        self.assertEqual(selected["report_id"], "report-b")
        self.assertEqual(selected["holdout"]["net_pnl_usd"], "99.00")
        self.assertEqual(selected["cost_model"]["entry_fee_bps"], "25.00")
        self.assertEqual(selected["rejection_reasons"], [])

    def test_one_positive_holdout_beats_a_rejected_candidate(self):
        selected = select_strategy([
            _report("candidate-pass", net="1.00"),
            _report("candidate-negative", net="-1.00", report_id="report-negative"),
        ])

        self.assertEqual(selected["strategy_id"], "candidate-pass")
        rejected = [row for row in selected["reports"] if row["report_id"] == "report-negative"][0]
        self.assertIn("holdout_net_non_positive", rejected["rejection_reasons"])

    def test_all_candidates_rejected_returns_no_strategy(self):
        selected = select_strategy([_report("candidate-a", net="0.00")])

        self.assertEqual(selected["strategy_id"], "NO_STRATEGY")
        self.assertIsNone(selected["report_id"])
        self.assertIn("holdout_net_non_positive", selected["rejection_reasons"])

    def test_stale_report_is_rejected(self):
        selected = select_strategy([_report("candidate-stale", stale=True)])

        self.assertEqual(selected["strategy_id"], "NO_STRATEGY")
        self.assertIn("report_stale", selected["rejection_reasons"])

    def test_cost_unknown_report_is_rejected(self):
        selected = select_strategy([_report("candidate-cost-unknown", cost_model=None)])

        self.assertEqual(selected["strategy_id"], "NO_STRATEGY")
        self.assertIn("cost_model_incomplete", selected["rejection_reasons"])

    def test_duplicate_evidence_ids_fail_closed(self):
        selected = select_strategy([
            _report("candidate-a", evidence_ids=["shared-evidence"]),
            _report("candidate-b", evidence_ids=["shared-evidence"]),
        ])

        self.assertEqual(selected["strategy_id"], "NO_STRATEGY")
        self.assertIn("duplicate_evidence_id", selected["rejection_reasons"])
        self.assertTrue(all("duplicate_evidence_id" in row["rejection_reasons"] for row in selected["reports"]))

    def test_ties_rank_by_drawdown_turnover_then_strategy_id(self):
        selected = select_strategy([
            _report("candidate-z", net="10.00", drawdown="3.00", turnover="0.10"),
            _report("candidate-a", net="10.00", drawdown="3.00", turnover="0.10"),
        ])

        self.assertEqual(selected["strategy_id"], "candidate-a")


if __name__ == "__main__":
    unittest.main()
