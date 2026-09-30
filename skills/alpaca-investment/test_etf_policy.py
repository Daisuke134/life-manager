from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import unittest
from pathlib import Path
import sys


CORE = Path(__file__).resolve().parents[2] / "apps" / "life-manager" / "investment-core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from etf_momentum import ETF_MOMENTUM_UNIVERSE, strategy_card
from etf_policy import evaluate
from strategy_cards import StrategyCard


LOOKBACK = 126
SESSIONS = [date(2026, 1, 1) + timedelta(days=index) for index in range(LOOKBACK + 1)]
LATEST = SESSIONS[-1].isoformat()
STRATEGY_ID = "alpaca-etf-126d-momentum-v1"
OWNER_ID = "alpaca-investment-live"


def _bar(session: date, close: str, opening: str | None = None) -> dict[str, str]:
    opening = opening or close
    return {"t": f"{session.isoformat()}T00:00:00Z", "o": opening, "c": close}


def _bars(symbol: str, winner: str = "QQQ") -> list[dict[str, str]]:
    values = ["100"] * len(SESSIONS)
    if symbol == winner:
        values[-1] = "120"
    else:
        values[-1] = "110"
    return [_bar(session, close) for session, close in zip(SESSIONS, values)]


def _snapshot(*, winner: str = "QQQ", position: dict | None = None,
              open_orders: int = 0, unresolved_intents: int = 0,
              last_decision_session: str | None = None) -> dict:
    return {
        "daily_bars": {
            symbol: _bars(symbol, winner=winner)
            for symbol in ETF_MOMENTUM_UNIVERSE
        },
        "completed_through_session": LATEST,
        "position": position,
        "open_orders": open_orders,
        "unresolved_intents": unresolved_intents,
        "last_decision_session": last_decision_session,
    }


class EtfPolicyTests(unittest.TestCase):
    def test_selects_highest_momentum_with_stable_signal_boundary(self):
        result = evaluate(_snapshot(), strategy_card())

        self.assertEqual(result["action"], "ENTER")
        self.assertEqual(result["strategy_id"], STRATEGY_ID)
        self.assertEqual(result["symbol"], "QQQ")
        self.assertEqual(result["decision_session"], LATEST)
        self.assertEqual(result["entry_after_session"], LATEST)
        self.assertEqual(result["signal_inputs"]["lookback_days"], "126")
        self.assertEqual(result["expected_cost_usd"], "0.02")

    def test_future_bar_is_rejected_even_when_it_would_change_the_winner(self):
        snapshot = _snapshot()
        future_session = SESSIONS[-1] + timedelta(days=1)
        snapshot["daily_bars"]["SPY"].append(_bar(future_session, "999"))

        result = evaluate(snapshot, strategy_card())

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "history_invalid")

    def test_missing_symbol_is_fail_closed(self):
        snapshot = _snapshot()
        del snapshot["daily_bars"]["GLD"]

        result = evaluate(snapshot, strategy_card())

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "history_invalid")

    def test_duplicate_or_unsorted_sessions_are_fail_closed(self):
        for mutate in (
            lambda rows: rows.__setitem__(-1, {**rows[-1], "t": rows[-2]["t"]}),
            lambda rows: rows.__setitem__(-1, {**rows[-1], "t": rows[-2]["t"].replace("2026-05-06", "2025-01-01")}),
        ):
            snapshot = _snapshot()
            mutate(snapshot["daily_bars"]["QQQ"])

            result = evaluate(snapshot, strategy_card())

            self.assertEqual(result["action"], "NO_TRADE")
            self.assertEqual(result["reason"], "history_invalid")

    def test_current_session_cannot_be_consumed_twice(self):
        result = evaluate(
            _snapshot(last_decision_session=LATEST), strategy_card()
        )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "decision_session_consumed")

    def test_pending_effect_fence_blocks_new_entry(self):
        result = evaluate(_snapshot(open_orders=1), strategy_card())

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "effect_fence")

    def test_foreign_position_is_never_adopted(self):
        position = {
            "owner_id": "another-owner",
            "strategy_id": STRATEGY_ID,
            "symbol": "QQQ",
            "qty": "1",
            "entry_session": SESSIONS[-22].isoformat(),
        }

        result = evaluate(_snapshot(position=position), strategy_card())

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "position_not_owned")

    def test_owned_position_exits_after_21_completed_sessions(self):
        position = {
            "owner_id": OWNER_ID,
            "strategy_id": STRATEGY_ID,
            "symbol": "QQQ",
            "qty": "1",
            "entry_session": SESSIONS[-22].isoformat(),
        }

        result = evaluate(_snapshot(position=position), strategy_card())

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["symbol"], "QQQ")
        self.assertEqual(result["reason"], "hold_sessions_elapsed")

    def test_owned_position_exits_before_hold_period_when_ranked_symbol_changes(self):
        position = {
            "owner_id": OWNER_ID,
            "strategy_id": STRATEGY_ID,
            "symbol": "SPY",
            "qty": "1",
            "entry_session": SESSIONS[-2].isoformat(),
        }

        result = evaluate(_snapshot(position=position, winner="QQQ"), strategy_card())

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["symbol"], "SPY")
        self.assertEqual(result["reason"], "ranked_symbol_changed")

    def test_pending_effect_also_blocks_position_exit(self):
        position = {
            "owner_id": OWNER_ID,
            "strategy_id": STRATEGY_ID,
            "symbol": "QQQ",
            "qty": "1",
            "entry_session": SESSIONS[-2].isoformat(),
        }

        result = evaluate(
            _snapshot(position=position, open_orders=1), strategy_card()
        )

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "effect_fence")

    def test_mutated_card_is_rejected(self):
        payload = strategy_card().to_mapping()
        payload["sizing_rule"]["notional_usd"] = "11.00"

        result = evaluate(_snapshot(), StrategyCard.from_mapping(deepcopy(payload)))

        self.assertEqual(result["action"], "NO_TRADE")
        self.assertEqual(result["reason"], "strategy_card_invalid")


if __name__ == "__main__":
    unittest.main()
