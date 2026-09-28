"""Pure, fail-closed daily policy for the research ETF momentum card.

The policy consumes a completed-session snapshot and returns a JSON-safe
decision.  It does not read credentials, call a broker, write state, submit
orders, or infer missing market data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
import sys
from typing import Any


_CORE = Path(__file__).resolve().parents[2] / "apps" / "life-manager" / "investment-core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from etf_momentum import ETF_MOMENTUM_UNIVERSE, strategy_card  # noqa: E402
from strategy_cards import StrategyCard, validate_strategy_card  # noqa: E402


ACTION_ENTER = "ENTER"
ACTION_HOLD = "HOLD"
ACTION_EXIT = "EXIT"
ACTION_NO_TRADE = "NO_TRADE"
ALLOWED_ACTIONS = frozenset({ACTION_ENTER, ACTION_HOLD, ACTION_EXIT, ACTION_NO_TRADE})

LOOKBACK_SESSIONS = 126
HOLD_SESSIONS = 21
_MONEY = Decimal("0.01")
_BPS = Decimal("10000")
_CANONICAL_CARD = strategy_card().to_mapping()


def _decimal(value: Any, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("number_invalid")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("number_invalid") from error
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError("number_invalid")
    return number


def _session(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("session_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("session_invalid") from error
    return parsed.date().isoformat()


def _money(value: Decimal) -> str:
    return str(value.quantize(_MONEY, rounding=ROUND_HALF_EVEN))


def _result(
    action: str,
    *,
    symbol: str | None,
    decision_session: str | None,
    entry_after_session: str | None,
    signal_inputs: Mapping[str, Any],
    reason: str,
    expected_cost_usd: str | None,
    strategy_id: str = "alpaca-etf-126d-momentum-v1",
) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise ValueError("strategy_action_invalid")
    return {
        "action": action,
        "strategy_id": strategy_id,
        "symbol": symbol,
        "decision_session": decision_session,
        "entry_after_session": entry_after_session,
        "signal_inputs": {str(key): str(value) for key, value in signal_inputs.items()},
        "reason": reason,
        "expected_cost_usd": expected_cost_usd,
    }


def _no_trade(reason: str, *, detail: str | None = None,
              decision_session: str | None = None,
              strategy_id: str = "alpaca-etf-126d-momentum-v1") -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    if detail is not None:
        inputs["error"] = detail
    return _result(
        ACTION_NO_TRADE,
        symbol=None,
        decision_session=decision_session,
        entry_after_session=None,
        signal_inputs=inputs,
        reason=reason,
        expected_cost_usd=None,
        strategy_id=strategy_id,
    )


def _card_cost(card: StrategyCard) -> str | None:
    try:
        notional = _decimal(card.sizing_rule["notional_usd"], positive=True)
        bps = sum(
            (_decimal(card.cost_model[key]) for key in (
                "entry_fee_bps", "exit_fee_bps",
                "entry_slippage_bps", "exit_slippage_bps",
            )),
            Decimal("0"),
        )
        if bps < 0:
            return None
        return _money(notional * bps / _BPS)
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return None


def _valid_card(card: StrategyCard | None) -> bool:
    return (
        isinstance(card, StrategyCard)
        and not validate_strategy_card(card)
        and card.to_mapping() == _CANONICAL_CARD
    )


def _normalize_bars(rows: Any, completed_session: str) -> dict[str, dict[str, Decimal | str]]:
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence) or not rows:
        raise ValueError("bars_invalid")
    normalized: dict[str, dict[str, Decimal | str]] = {}
    previous: str | None = None
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("bar_invalid")
        session = _session(row.get("t", row.get("timestamp")))
        if session > completed_session:
            raise ValueError("bar_after_completed_boundary")
        if previous is not None:
            if session == previous:
                raise ValueError("duplicate_session")
            if session < previous:
                raise ValueError("sessions_not_sorted")
        opening = _decimal(row.get("o", row.get("open")), positive=True)
        closing = _decimal(row.get("c", row.get("close")), positive=True)
        normalized[session] = {
            "session": session,
            "open": opening,
            "close": closing,
        }
        previous = session
    return normalized


def _histories(snapshot: Mapping[str, Any]) -> tuple[
    dict[str, dict[str, dict[str, Decimal | str]]], list[str], str
]:
    completed_session = _session(snapshot["completed_through_session"])
    raw = snapshot["daily_bars"]
    if not isinstance(raw, Mapping):
        raise ValueError("daily_bars_invalid")
    normalized: dict[str, dict[str, dict[str, Decimal | str]]] = {}
    for symbol in ETF_MOMENTUM_UNIVERSE:
        if symbol not in raw:
            raise ValueError(f"missing_symbol:{symbol}")
        normalized[symbol] = _normalize_bars(raw[symbol], completed_session)
    common = set.intersection(*(set(rows) for rows in normalized.values()))
    sessions = sorted(common)
    if len(sessions) < LOOKBACK_SESSIONS + 1:
        raise ValueError("history_insufficient")
    if sessions[-1] != completed_session:
        raise ValueError("completed_session_missing")
    return normalized, sessions, completed_session


def _pending(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value > 0
    if isinstance(value, Decimal):
        return value > 0
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return bool(value)
    raise ValueError("effect_state_invalid")


def _position(value: Any, *, owner_id: str, strategy_id: str,
              sessions: Sequence[str]) -> tuple[dict[str, Any] | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, Mapping):
        raise ValueError("position_invalid")
    if value.get("owner_id") != owner_id or value.get("strategy_id") != strategy_id:
        return None, "position_not_owned"
    symbol = value.get("symbol")
    if symbol not in ETF_MOMENTUM_UNIVERSE:
        raise ValueError("position_symbol_invalid")
    _decimal(value.get("qty"), positive=True)
    entry_session = _session(value.get("entry_session"))
    if entry_session not in sessions:
        raise ValueError("position_history_missing")
    return {
        "symbol": symbol,
        "entry_session": entry_session,
    }, None


def evaluate(
    snapshot: Mapping[str, Any],
    card: StrategyCard | None = None,
    *,
    owner_id: str = "alpaca-investment-live",
) -> dict[str, Any]:
    """Evaluate one completed daily decision without producing an effect."""
    selected_card = strategy_card() if card is None else card
    strategy_id = getattr(selected_card, "strategy_id", "alpaca-etf-126d-momentum-v1")
    if not _valid_card(selected_card):
        return _no_trade("strategy_card_invalid", strategy_id=str(strategy_id))
    if not isinstance(snapshot, Mapping) or not isinstance(owner_id, str) or not owner_id:
        return _no_trade("snapshot_invalid")

    try:
        histories, sessions, completed_session = _histories(snapshot)
        expected_cost = _card_cost(selected_card)
        if expected_cost is None:
            return _no_trade("cost_unknown", decision_session=completed_session)
        for field in ("position", "open_orders", "unresolved_intents", "last_decision_session"):
            if field not in snapshot:
                return _no_trade("state_incomplete", decision_session=completed_session)
        if _pending(snapshot["open_orders"]) or _pending(snapshot["unresolved_intents"]):
            return _result(
                ACTION_NO_TRADE,
                symbol=None,
                decision_session=completed_session,
                entry_after_session=None,
                signal_inputs={"latest_session": completed_session},
                reason="effect_fence",
                expected_cost_usd=expected_cost,
                strategy_id=selected_card.strategy_id,
            )
        last_decision = snapshot["last_decision_session"]
        if last_decision is not None and _session(last_decision) == completed_session:
            return _result(
                ACTION_NO_TRADE,
                symbol=None,
                decision_session=completed_session,
                entry_after_session=None,
                signal_inputs={"latest_session": completed_session},
                reason="decision_session_consumed",
                expected_cost_usd=expected_cost,
                strategy_id=selected_card.strategy_id,
            )
        position, position_error = _position(
            snapshot["position"], owner_id=owner_id,
            strategy_id=selected_card.strategy_id, sessions=sessions,
        )
        if position_error:
            return _result(
                ACTION_NO_TRADE,
                symbol=None,
                decision_session=completed_session,
                entry_after_session=None,
                signal_inputs={},
                reason=position_error,
                expected_cost_usd=expected_cost,
                strategy_id=selected_card.strategy_id,
            )
        reference_session = sessions[-1 - LOOKBACK_SESSIONS]
        ranking: list[tuple[Decimal, str]] = []
        for symbol in ETF_MOMENTUM_UNIVERSE:
            reference = _decimal(histories[symbol][reference_session]["close"], positive=True)
            current = _decimal(histories[symbol][completed_session]["close"], positive=True)
            momentum = current / reference - Decimal("1")
            ranking.append((momentum, symbol))
        winner_momentum = max(row[0] for row in ranking)
        winner_symbol = min(row[1] for row in ranking if row[0] == winner_momentum)
        signal_inputs = {
            "latest_session": completed_session,
            "reference_session": reference_session,
            "lookback_days": LOOKBACK_SESSIONS,
            "momentum_rank": 1,
            "momentum_return": _money(winner_momentum),
        }
        if position is not None:
            held_symbol = str(position["symbol"])
            held_index = sessions.index(str(position["entry_session"]))
            held_sessions = len(sessions) - 1 - held_index
            signal_inputs["held_symbol"] = held_symbol
            signal_inputs["held_sessions"] = held_sessions
            if held_symbol != winner_symbol:
                return _result(
                    ACTION_EXIT,
                    symbol=held_symbol,
                    decision_session=completed_session,
                    entry_after_session=None,
                    signal_inputs=signal_inputs,
                    reason="ranked_symbol_changed",
                    expected_cost_usd=expected_cost,
                    strategy_id=selected_card.strategy_id,
                )
            if held_sessions >= HOLD_SESSIONS:
                return _result(
                    ACTION_EXIT,
                    symbol=held_symbol,
                    decision_session=completed_session,
                    entry_after_session=None,
                    signal_inputs=signal_inputs,
                    reason="hold_sessions_elapsed",
                    expected_cost_usd=expected_cost,
                    strategy_id=selected_card.strategy_id,
                )
            return _result(
                ACTION_HOLD,
                symbol=held_symbol,
                decision_session=completed_session,
                entry_after_session=None,
                signal_inputs=signal_inputs,
                reason="hold_period_not_elapsed",
                expected_cost_usd=expected_cost,
                strategy_id=selected_card.strategy_id,
            )
        return _result(
            ACTION_ENTER,
            symbol=winner_symbol,
            decision_session=completed_session,
            entry_after_session=completed_session,
            signal_inputs=signal_inputs,
            reason="top_momentum_next_session",
            expected_cost_usd=expected_cost,
            strategy_id=selected_card.strategy_id,
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return _no_trade("history_invalid")


__all__ = [
    "ACTION_ENTER", "ACTION_EXIT", "ACTION_HOLD", "ACTION_NO_TRADE",
    "ALLOWED_ACTIONS", "evaluate",
]
