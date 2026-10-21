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
from test_etf_policy import SESSIONS, _snapshot as policy_snapshot


ETF_ID = "alpaca-etf-126d-momentum-v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _risk(observed_at: str) -> dict[str, object]:
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    return {
        "allocated_capital_usd": "0",
        "cash_flow_ny_day_usd": "0",
        "equity_pnl_ny_day_usd": "0",
        "official_pnl_ny_day_usd": "0",
        "risk_day_ready": True,
        "unrealized_pnl_usd": "0",
        "observed_at": observed_at,
        "ny_day": observed.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
    }


def _snapshot(mode: str = "paper") -> dict[str, object]:
    value = policy_snapshot()
    observed_at = _now()
    value.update({
        "mode": mode,
        "account": {"cash": "100", "equity": "100"},
        "available_cash_usd": "100",
        "clock": {"timestamp": observed_at, "is_open": True},
        "positions": 0,
        "open_orders": 0,
        "unresolved_intents": 0,
        "risk": _risk(observed_at),
    })
    return value


def _selected_state(path: Path, *, include_benchmark: bool = True) -> None:
    card = candidate_cards()[ETF_ID].to_mapping()
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "selection": "selected",
        "report_id": "alpaca-etf-126d-momentum-v1-20260929",
        "release_sha": "c" * 40,
        "strategy_id": ETF_ID,
        "card": card,
        "holdout": {"net_pnl_usd": "1.62"},
        "expires_at": "2099-01-01T00:00:00Z",
    }
    if include_benchmark:
        payload["benchmark"] = {
            "symbol": "SPY", "method": "buy_and_hold",
            "measurement_kind": "modeled_reference_pnl", "status": "measured",
            "holdout": {"status": "measured", "net_pnl_usd": "0.50", "strategy_net_pnl_usd": "1.62",
                        "excess_net_pnl_usd": "1.12"},
        }
    (path / "selected-strategy.json").write_text(json.dumps(payload))


def _expired_selected_state(path: Path) -> None:
    _selected_state(path)
    selection_path = path / "selected-strategy.json"
    selection = json.loads(selection_path.read_text())
    selection["expires_at"] = "2020-01-01T00:00:00Z"
    selection_path.write_text(json.dumps(selection))


def _candidate(symbol: str = "QQQ") -> dict[str, object]:
    return {
        "asset_class": "us_equity",
        "candidate_ref": f"equity://{symbol}",
        "max_loss_usd": 10.0,
        "quote_age_seconds": 0,
        "spread_fraction": 0,
        "symbol": symbol,
    }


class LegacyCryptoEntryRetirementTests(unittest.TestCase):
    def test_old_btc_policy_cannot_reenter_while_new_policy_uses_the_same_risk_gates(self):
        candidate={**_candidate("BTC/USDC"),"asset_class":"crypto","candidate_ref":"crypto://BTC/USDC"}
        base={"action":"ENTER","mode":"paper","candidate_ref":candidate["candidate_ref"],"symbol":"BTC/USDC",
              "expected_cost_usd":"0.02","owner_id":"alpaca-investment-paper"}
        for strategy in ("alpaca-btc-5m-trend-v1","alpaca-btc-5m-reversion-v1"):
            with self.subTest(strategy=strategy):
                result=allocator.gate(_snapshot("paper"),[candidate],{**base,"strategy_id":strategy})
                self.assertFalse(result["approved"])
                self.assertEqual(result["gate"],"legacy_btc_entry_retired")
        result=allocator.gate(_snapshot("paper"),[candidate],{**base,"strategy_id":"alpaca-btc-5m-trend-400-v2"})
        self.assertTrue(result["approved"],result)


class EtfAllocatorTests(unittest.TestCase):
    def test_unbenchmarked_selection_cannot_open_a_new_etf_position(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            _selected_state(state, include_benchmark=False)

            result = allocator.choose(
                _snapshot("paper"), [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["gate"], "strategy_release_benchmark_invalid")
        self.assertFalse(result["approved"])

    def test_unbenchmarked_selection_allows_only_owned_etf_position_management(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper"},
        ):
            state = Path(directory) / "state"
            _selected_state(state, include_benchmark=False)
            snapshot = _snapshot("paper")
            snapshot.update({
                "positions": 1,
                "position": {
                    "owner_id": "alpaca-investment-paper",
                    "strategy_id": ETF_ID,
                    "symbol": "QQQ",
                    "qty": "0.025",
                    "entry_session": SESSIONS[-16].isoformat(),
                },
            })

            result = allocator.choose(
                snapshot, [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertEqual(result["action"], "HOLD")
        self.assertTrue(result["selection_management_only"])
        self.assertFalse(result["approved"])

    def test_build_candidates_exposes_fixed_etf_universe_when_daily_bars_exist(self):
        snapshot = _snapshot()
        snapshot.update({
            "crypto": [],
            "qqq_asset": {"tradable": False, "status": "inactive"},
            "qqq_quote": {"bid": "1", "ask": "1", "quote_at": snapshot["clock"]["timestamp"]},
            "option_quotes": [],
        })

        candidates = allocator.build_candidates(snapshot)

        self.assertEqual(
            [row["symbol"] for row in candidates if row["asset_class"] == "us_equity"],
            ["SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "GLD"],
        )

    def test_legacy_paper_etf_does_not_reenter_once_flat(self):
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
        self.assertFalse(result["approved"])
        self.assertFalse(result["checks"]["entry_policy_active"])
        self.assertEqual(result["gate"], "legacy_etf_entry_retired")

    def test_expired_selection_keeps_holding_an_exact_owned_etf_position(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper"},
        ):
            state = Path(directory) / "state"
            _expired_selected_state(state)
            snapshot = _snapshot("paper")
            snapshot.update({
                "positions": 1,
                "position": {
                    "owner_id": "alpaca-investment-paper",
                    "strategy_id": ETF_ID,
                    "symbol": "QQQ",
                    "qty": "0.025",
                    "entry_session": SESSIONS[-16].isoformat(),
                },
            })

            result = allocator.choose(
                snapshot, [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertEqual(result["action"], "HOLD")
        self.assertEqual(result["reason"], "hold_period_not_elapsed")
        self.assertTrue(result["selection_expired"])
        self.assertFalse(result["approved"])

    def test_expired_selection_still_allows_only_the_owned_etf_exit(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"LIFE_MANAGER_INVESTMENT_OWNER_ID": "alpaca-investment-paper"},
        ):
            state = Path(directory) / "state"
            _expired_selected_state(state)
            snapshot = _snapshot("paper")
            snapshot.update({
                "positions": 1,
                "position": {
                    "owner_id": "alpaca-investment-paper",
                    "strategy_id": ETF_ID,
                    "symbol": "QQQ",
                    "qty": "0.025",
                    "entry_session": SESSIONS[-22].isoformat(),
                },
            })

            result = allocator.choose(
                snapshot, [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "hold_sessions_elapsed")
        self.assertTrue(result["selection_expired"])
        self.assertTrue(result["approved"], result)
        self.assertEqual(allocator.order_for(result)["side"], "sell")

    def test_expired_selection_cannot_open_a_new_etf_position(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            _expired_selected_state(state)

            result = allocator.choose(
                _snapshot("paper"), [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["gate"], "strategy_release_expired")
        self.assertFalse(result["approved"])

    def test_expired_selection_does_not_manage_a_foreign_position(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            _expired_selected_state(state)
            snapshot = _snapshot("paper")
            snapshot.update({
                "positions": 1,
                "position": {
                    "owner_id": "another-investment-owner",
                    "strategy_id": ETF_ID,
                    "symbol": "QQQ",
                    "qty": "0.025",
                    "entry_session": SESSIONS[-22].isoformat(),
                },
            })

            result = allocator.choose(
                snapshot, [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["gate"], "strategy_release_expired")
        self.assertFalse(result["approved"])

    def test_paper_etf_entry_is_rejected_outside_regular_session(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            _selected_state(state)
            snapshot = _snapshot("paper")
            snapshot["clock"]["is_open"] = False
            result = allocator.choose(
                snapshot, [_candidate("QQQ")], state,
                Path("unused-runner"), Path(directory),
            )

        self.assertFalse(result["approved"])
        self.assertFalse(result["checks"]["regular_session"])
        self.assertEqual(result["gate"], "legacy_etf_entry_retired")

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
                "clock": {**snapshot["clock"], "is_open": False},
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

        self.assertFalse(result["approved"])
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
