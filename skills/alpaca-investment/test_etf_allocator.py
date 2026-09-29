from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CORE = ROOT.parents[1] / "apps" / "life-manager" / "investment-core"
while str(CORE) in sys.path:
    sys.path.remove(str(CORE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import allocator
from strategy_policy import candidate_cards
from test_etf_policy import _snapshot as policy_snapshot


NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
ETF_ID = "alpaca-etf-126d-momentum-v1"


def _risk() -> dict[str, object]:
    return {
        "allocated_capital_usd": "0",
        "cash_flow_ny_day_usd": "0",
        "equity_pnl_ny_day_usd": "0",
        "official_pnl_ny_day_usd": "0",
        "risk_day_ready": True,
        "unrealized_pnl_usd": "0",
        "observed_at": NOW,
        "ny_day": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
    }


def _snapshot(mode: str = "paper") -> dict[str, object]:
    value = policy_snapshot()
    value.update({
        "mode": mode,
        "account": {"cash": "100", "equity": "100"},
        "available_cash_usd": "100",
        "clock": {"timestamp": NOW, "is_open": True},
        "positions": 0,
        "open_orders": 0,
        "unresolved_intents": 0,
        "risk": _risk(),
    })
    return value


def _selected_state(path: Path) -> None:
    card = candidate_cards()[ETF_ID].to_mapping()
    path.mkdir(parents=True, exist_ok=True)
    (path / "selected-strategy.json").write_text(json.dumps({
        "selection": "selected",
        "report_id": "alpaca-etf-126d-momentum-v1-20260929",
        "release_sha": "c" * 40,
        "strategy_id": ETF_ID,
        "card": card,
        "expires_at": "2099-01-01T00:00:00Z",
    }))


def _candidate(symbol: str = "QQQ") -> dict[str, object]:
    return {
        "asset_class": "us_equity",
        "candidate_ref": f"equity://{symbol}",
        "max_loss_usd": 10.0,
        "quote_age_seconds": 0,
        "spread_fraction": 0,
        "symbol": symbol,
    }


class EtfAllocatorTests(unittest.TestCase):
    def test_build_candidates_exposes_fixed_etf_universe_when_daily_bars_exist(self):
        snapshot = _snapshot()
        snapshot.update({
            "crypto": [],
            "qqq_asset": {"tradable": False, "status": "inactive"},
            "qqq_quote": {"bid": "1", "ask": "1", "quote_at": NOW},
            "option_quotes": [],
        })

        candidates = allocator.build_candidates(snapshot)

        self.assertEqual(
            [row["symbol"] for row in candidates if row["asset_class"] == "us_equity"],
            ["SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "GLD"],
        )

    def test_paper_etf_selection_dispatches_and_approves_only_us_equity_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            _selected_state(state)
            result = allocator.choose(
                _snapshot("paper"), [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertEqual(result["action"], "ENTER")
        self.assertEqual(result["strategy_id"], ETF_ID)
        self.assertEqual(result["candidate"]["asset_class"], "us_equity")
        self.assertTrue(result["approved"])
        self.assertEqual(result["gate"], "approved")

    def test_paper_etf_entry_is_rejected_outside_regular_session(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            _selected_state(state)
            snapshot = _snapshot("paper")
            snapshot["clock"] = {"timestamp": NOW, "is_open": False}
            result = allocator.choose(
                snapshot, [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertFalse(result["approved"])
        self.assertFalse(result["checks"]["regular_session"])
        self.assertEqual(result["gate"], "risk_rejected")

    def test_paper_etf_exit_is_rejected_outside_regular_session(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper"},
        ), patch.object(allocator, "evaluate", return_value={
            "action": "EXIT",
            "strategy_id": ETF_ID,
            "symbol": "QQQ",
            "decision_session": "2026-09-29",
            "entry_after_session": None,
            "signal_inputs": {"held_symbol": "QQQ"},
            "reason": "hold_sessions_elapsed",
            "expected_cost_usd": "0.02",
        }):
            state = Path(directory) / "state"
            _selected_state(state)
            snapshot = _snapshot("paper")
            snapshot.update({
                "clock": {"timestamp": NOW, "is_open": False},
                "positions": 1,
                "position": {
                    "owner_id": "alpaca-investment-paper",
                    "strategy_id": ETF_ID,
                    "symbol": "QQQ",
                    "qty": "0.025",
                    "entry_session": "2026-09-01",
                },
            })
            result = allocator.choose(
                snapshot, [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertFalse(result["approved"])
        self.assertFalse(result["checks"]["regular_session"])
        self.assertEqual(result["gate"], "exit_rejected")

    def test_paper_owner_identity_is_not_live_owner(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper"},
        ):
            state = Path(directory) / "state"
            _selected_state(state)
            result = allocator.choose(
                _snapshot("paper"), [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertTrue(result["approved"])
        self.assertEqual(result["owner_id"], "alpaca-investment-paper")

    def test_paper_etf_exit_is_approved_and_emits_sell_quantity(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper"},
        ), patch.object(allocator, "evaluate", return_value={
            "action": "EXIT",
            "strategy_id": ETF_ID,
            "symbol": "QQQ",
            "decision_session": "2026-09-29",
            "entry_after_session": None,
            "signal_inputs": {"held_symbol": "QQQ"},
            "reason": "hold_sessions_elapsed",
            "expected_cost_usd": "0.02",
        }):
            state = Path(directory) / "state"
            _selected_state(state)
            snapshot = _snapshot("paper")
            snapshot.update({
                "positions": 1,
                "position": {
                    "owner_id": "alpaca-investment-paper",
                    "strategy_id": ETF_ID,
                    "symbol": "QQQ",
                    "qty": "0.025",
                    "entry_session": "2026-09-01",
                },
            })
            result = allocator.choose(
                snapshot, [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )
            order = allocator.order_for(result)

        self.assertEqual(result["action"], "EXIT")
        self.assertTrue(result["approved"])
        self.assertEqual(result["gate"], "approved_exit")
        self.assertEqual(order, {
            "asset_class": "us_equity",
            "qty": "0.025",
            "side": "sell",
            "symbol": "QQQ",
            "time_in_force": "day",
            "type": "market",
        })

    def test_live_etf_selection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            _selected_state(state)
            result = allocator.choose(
                _snapshot("live"), [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertFalse(result["approved"])
        self.assertEqual(result["gate"], "live_etf_rejected")

    def test_etf_order_shape_is_paper_stock_day_market_not_crypto_gtc(self):
        order = allocator.order_for({"candidate": _candidate("QQQ")})

        self.assertEqual(order, {
            "asset_class": "us_equity",
            "notional_usd": "10.00",
            "side": "buy",
            "symbol": "QQQ",
            "time_in_force": "day",
            "type": "market",
        })


if __name__ == "__main__":
    unittest.main()
