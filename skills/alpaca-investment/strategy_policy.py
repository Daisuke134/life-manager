"""Pure, declared Alpaca strategy cards and signal evaluation.

This module has no broker, wallet, subprocess, or filesystem side effects during
signal evaluation.  A selected release is loaded separately by the effect owner
before it can turn an ``ENTER`` result into an order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
import json
from pathlib import Path
import re
import sys
from typing import Any


_CORE = Path(__file__).resolve().parents[2] / "apps" / "life-manager" / "investment-core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from etf_momentum import ETF_MOMENTUM_UNIVERSE, strategy_card as etf_strategy_card  # noqa: E402
from etf_policy import evaluate as evaluate_etf_policy  # noqa: E402
from strategy_cards import StrategyCard, validate_strategy_card  # noqa: E402


getcontext().prec = 28

ACTION_ENTER = "ENTER"
ACTION_HOLD = "HOLD"
ACTION_EXIT = "EXIT"
ACTION_NO_TRADE = "NO_TRADE"
ALLOWED_ACTIONS = frozenset({ACTION_ENTER, ACTION_HOLD, ACTION_EXIT, ACTION_NO_TRADE})

BTC_SYMBOLS = frozenset({"BTC/USDC", "BTC/USD", "BTCUSD", "BTCUSDC"})
CANONICAL_SYMBOL = "BTC/USDC"
ETF_STRATEGY_ID = "alpaca-etf-126d-momentum-v1"
ETF_SYMBOLS = tuple(ETF_MOMENTUM_UNIVERSE)
MAX_QUOTE_AGE_SECONDS = Decimal("30")
MAX_SPREAD_FRACTION = Decimal("0.15")
BAR_SECONDS = 300

_TWO_PLACES = Decimal("0.01")
_RELEASE_SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")


def _card_mapping(strategy_id: str, entry_rules: dict[str, Any],
                  exit_rules: dict[str, Any], evidence_ref: str) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "venue": "alpaca",
        "instruments": [CANONICAL_SYMBOL],
        "timeframe": "5m",
        "entry_rules": entry_rules,
        "exit_rules": exit_rules,
        "sizing_rule": {"notional_usd": "10.00", "max_loss_usd": "10.00"},
        "cost_model": {
            "entry_fee_bps": "25.00",
            "exit_fee_bps": "25.00",
            "entry_slippage_bps": "5.00",
            "exit_slippage_bps": "5.00",
        },
        "risk_limits": {"trade_max_loss_usd": "10.00", "max_drawdown_usd": "20.00"},
        "kill_conditions": ["quote_stale", "spread_too_wide", "history_invalid", "effect_unknown"],
        "evidence_refs": [evidence_ref],
        "status": "research",
    }


def candidate_cards() -> dict[str, StrategyCard]:
    """Return immutable Alpaca hypotheses, never a mutable registry."""
    cards = {
        "alpaca-btc-5m-reversion-v1": StrategyCard.from_mapping(_card_mapping(
            "alpaca-btc-5m-reversion-v1",
            {"all": ["rsi_14 <= 30", "tema_9 < bollinger_middle_20_2"]},
            {"any": [
                "rsi_14 >= 70",
                "close >= bollinger_upper_20_2",
                "close <= entry_price - 1.5 * atr_14",
                "age_bars >= 12",
            ]},
            "https://docs.freqtrade.io/en/stable/strategy-customization/",
        )),
        "alpaca-btc-5m-trend-v1": StrategyCard.from_mapping(_card_mapping(
            "alpaca-btc-5m-trend-v1",
            {"all": ["ema_20 > ema_50", "close > prior_20_high"]},
            {"any": [
                "close < ema_20",
                "close <= entry_price - 2 * atr_14",
                "age_bars >= 24",
            ]},
            "https://docs.freqtrade.io/en/stable/backtesting/",
        )),
    }
    cards[ETF_STRATEGY_ID] = etf_strategy_card()
    return cards


def _fmt(value: Decimal) -> str:
    return str(value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP))


def _decimal(value: Any) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite():
        raise InvalidOperation
    return number


def _instant(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp_invalid")
    normalized = value.replace("Z", "+00:00")
    observed = datetime.fromisoformat(normalized)
    if observed.tzinfo is None:
        raise ValueError("timestamp_timezone_missing")
    return observed.astimezone(timezone.utc)


def _result(card: StrategyCard, action: str, signal_inputs: Mapping[str, Any],
            reason: str, expected_cost_usd: str | None) -> dict[str, Any]:
    if action not in ALLOWED_ACTIONS:
        raise ValueError("strategy_action_invalid")
    return {
        "action": action,
        "strategy_id": card.strategy_id,
        "signal_inputs": {str(key): str(value) for key, value in signal_inputs.items()},
        "reason": reason,
        "expected_cost_usd": expected_cost_usd,
    }


def _cost_usd(card: StrategyCard) -> Decimal | None:
    try:
        sizing = card.sizing_rule
        model = card.cost_model
        notional = _decimal(sizing["notional_usd"])
        bps = sum((_decimal(model[key]) for key in (
            "entry_fee_bps", "exit_fee_bps", "entry_slippage_bps", "exit_slippage_bps",
        )), Decimal("0"))
        if notional <= 0 or bps < 0:
            raise InvalidOperation
        return notional * bps / Decimal("10000")
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return None


def _quote(snapshot: Mapping[str, Any]) -> tuple[dict[str, Any], Decimal, Decimal, Decimal] | None:
    quotes = snapshot.get("crypto")
    clock = snapshot.get("clock")
    if not isinstance(quotes, Sequence) or isinstance(quotes, (str, bytes)) \
            or not isinstance(clock, Mapping):
        return None
    selected = None
    for quote in quotes:
        if isinstance(quote, Mapping) and quote.get("symbol") in BTC_SYMBOLS:
            selected = dict(quote)
            break
    if selected is None:
        return None
    try:
        bid, ask = _decimal(selected["bid"]), _decimal(selected["ask"])
        age = (_instant(clock["timestamp"]) - _instant(selected["quote_at"])).total_seconds()
        age_decimal = _decimal(age)
        if bid <= 0 or ask <= 0 or ask < bid or age_decimal < 0:
            return None
        spread = (ask - bid) / ask
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return None
    return selected, bid, ask, age_decimal if spread >= 0 else Decimal("-1")


def _normalise_bars(snapshot: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    histories = snapshot.get("crypto_history")
    if not isinstance(histories, Mapping):
        return None
    raw = histories.get(CANONICAL_SYMBOL)
    if raw is None:
        raw = histories.get("BTC/USD")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    bars: list[dict[str, Any]] = []
    previous: datetime | None = None
    try:
        for row in raw:
            if not isinstance(row, Mapping):
                return None
            timestamp = _instant(row["t"])
            values = {key: _decimal(row[key]) for key in ("o", "h", "l", "c")}
            if any(value <= 0 for value in values.values()) \
                    or values["h"] < max(values["o"], values["l"], values["c"]) \
                    or values["l"] > min(values["o"], values["h"], values["c"]):
                return None
            if previous is not None and (timestamp <= previous
                    or (timestamp - previous).total_seconds() != BAR_SECONDS):
                return None
            bars.append({"timestamp": timestamp, **values})
            previous = timestamp
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return None
    return bars


def _normalise_contiguous_segments(raw_bars: Sequence[Mapping[str, Any]]) -> list[list[dict[str, Any]]]:
    """Validate official bars and split at missing five-minute intervals."""
    segments: list[list[dict[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    previous: datetime | None = None

    def flush() -> None:
        if not current:
            return
        normalized = _normalise_bars({"crypto_history": {CANONICAL_SYMBOL: current}})
        if normalized:
            segments.append(normalized)

    for raw_bar in raw_bars:
        single = _normalise_bars({"crypto_history": {CANONICAL_SYMBOL: [raw_bar]}})
        if single is None:
            flush()
            current = []
            previous = None
            continue
        timestamp = single[0]["timestamp"]
        if previous is not None and (timestamp - previous).total_seconds() != BAR_SECONDS:
            flush()
            current = []
        current.append(raw_bar)
        previous = timestamp
    flush()
    return segments


def _ema(values: Sequence[Decimal], period: int) -> list[Decimal]:
    if len(values) < period:
        return []
    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    result = [seed]
    multiplier = Decimal("2") / Decimal(period + 1)
    for value in values[period:]:
        result.append((value - result[-1]) * multiplier + result[-1])
    return result


def _tema(values: Sequence[Decimal], period: int) -> Decimal | None:
    first = _ema(values, period)
    second = _ema(first, period)
    third = _ema(second, period)
    if not third:
        return None
    # The three EMA series have different starting points.  The last values
    # are aligned to the same most recent candle, which is what the signal uses.
    return Decimal("3") * first[-1] - Decimal("3") * second[-1] + third[-1]


def _rsi(closes: Sequence[Decimal], period: int) -> Decimal | None:
    if len(closes) <= period:
        return None
    deltas = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    window = deltas[-period:]
    gains = sum((max(delta, Decimal("0")) for delta in window), Decimal("0"))
    losses = sum((max(-delta, Decimal("0")) for delta in window), Decimal("0"))
    if losses == 0:
        return Decimal("50") if gains == 0 else Decimal("100")
    return Decimal("100") - (Decimal("100") / (Decimal("1") + gains / losses))


def _bollinger(closes: Sequence[Decimal], period: int, deviations: int) -> tuple[Decimal, Decimal] | None:
    if len(closes) < period:
        return None
    window = list(closes[-period:])
    middle = sum(window, Decimal("0")) / Decimal(period)
    variance = sum(((value - middle) ** 2 for value in window), Decimal("0")) / Decimal(period)
    # Decimal.sqrt is deterministic and avoids a float round-trip in the gate.
    upper = middle + Decimal(deviations) * variance.sqrt()
    return middle, upper


def _atr(bars: Sequence[Mapping[str, Decimal]], period: int) -> Decimal | None:
    if len(bars) <= period:
        return None
    true_ranges: list[Decimal] = []
    for index in range(1, len(bars)):
        high, low = bars[index]["h"], bars[index]["l"]
        previous_close = bars[index - 1]["c"]
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    if len(true_ranges) < period:
        return None
    return sum(true_ranges[-period:], Decimal("0")) / Decimal(period)


def _indicators(bars: Sequence[Mapping[str, Any]], strategy_id: str) -> dict[str, Decimal] | None:
    closes = [row["c"] for row in bars]
    if strategy_id == "alpaca-btc-5m-reversion-v1":
        if len(bars) < 20:
            return None
        rsi = _rsi(closes, 14)
        tema = _tema(closes, 9)
        bollinger = _bollinger(closes, 20, 2)
        atr = _atr(bars, 14)
        if rsi is None or tema is None or bollinger is None or atr is None:
            return None
        middle, upper = bollinger
        return {"close": closes[-1], "rsi_14": rsi, "tema_9": tema,
                "bollinger_middle_20_2": middle, "bollinger_upper_20_2": upper,
                "atr_14": atr}
    if strategy_id == "alpaca-btc-5m-trend-v1":
        if len(bars) < 51:
            return None
        ema20, ema50 = _ema(closes, 20), _ema(closes, 50)
        atr = _atr(bars, 14)
        if not ema20 or not ema50 or atr is None:
            return None
        return {"close": closes[-1], "ema_20": ema20[-1], "ema_50": ema50[-1],
                "prior_20_high": max(row["h"] for row in bars[-21:-1]), "atr_14": atr}
    return None


def build_validation_candles(
    raw_bars: Sequence[Mapping[str, Any]], strategy_id: str,
) -> list[dict[str, str]]:
    """Build indicator candles without using any bar after the current one."""
    result: list[dict[str, str]] = []
    for bars in _normalise_contiguous_segments(raw_bars):
        for index, bar in enumerate(bars):
            indicators = _indicators(bars[:index + 1], strategy_id)
            if indicators is None:
                continue
            row = {
                "timestamp": bar["timestamp"].isoformat(),
                "open": str(bar["o"]),
                "high": str(bar["h"]),
                "low": str(bar["l"]),
                "close": str(bar["c"]),
            }
            row.update({key: str(value) for key, value in indicators.items()})
            result.append(row)
    return result


def _signal_inputs(indicators: Mapping[str, Decimal], age_bars: int | None = None,
                   quote_age: Decimal | None = None, spread: Decimal | None = None) -> dict[str, str]:
    values = {key: _fmt(value) for key, value in indicators.items()}
    if age_bars is not None:
        values["age_bars"] = str(age_bars)
    if quote_age is not None:
        values["quote_age_seconds"] = _fmt(quote_age)
    if spread is not None:
        values["spread_fraction"] = _fmt(spread)
    return values


def _age_bars(bars: Sequence[Mapping[str, Any]], entry_timestamp: Any) -> int | None:
    try:
        entry = _instant(entry_timestamp)
    except (TypeError, ValueError):
        return None
    return sum(1 for row in bars if row["timestamp"] > entry)


def _position(snapshot: Mapping[str, Any]) -> tuple[int, Mapping[str, Any] | None] | None:
    value = snapshot.get("positions")
    if isinstance(value, bool):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    if count < 0:
        return None
    position = snapshot.get("position")
    if position is not None and not isinstance(position, Mapping):
        return None
    return count, position


def _edge_usd(card: StrategyCard, ask: Decimal, indicators: Mapping[str, Decimal]) -> Decimal:
    entry = ask
    if card.strategy_id == "alpaca-btc-5m-reversion-v1":
        target = indicators["bollinger_upper_20_2"]
    else:
        target = indicators["close"] + Decimal("3") * indicators["atr_14"]
    notional = _decimal(card.sizing_rule["notional_usd"])
    if entry <= 0:
        return Decimal("0")
    return max((target - entry) / entry * notional, Decimal("0"))


def _allowed_card(card: StrategyCard) -> tuple[bool, str]:
    errors = validate_strategy_card(card)
    if errors:
        return False, "card_invalid"
    if card.status == "rejected":
        return False, "card_rejected"
    if card.strategy_id == ETF_STRATEGY_ID:
        if card.to_mapping() != etf_strategy_card().to_mapping():
            return False, "card_scope_invalid"
        return True, ""
    if card.venue != "alpaca" or card.timeframe != "5m":
        return False, "card_scope_invalid"
    instruments = tuple(card.instruments or ())
    if CANONICAL_SYMBOL not in instruments or any(symbol not in BTC_SYMBOLS for symbol in instruments):
        return False, "instrument_not_allowed"
    return True, ""


def evaluate(snapshot: Mapping[str, Any], card: StrategyCard) -> dict[str, Any]:
    """Evaluate one declared card against one official snapshot.

    The result is intentionally a small, JSON-safe decision record.  It never
    selects a card, creates an order, calls a model, or mutates state.
    """
    if not isinstance(snapshot, Mapping):
        raise TypeError("snapshot_mapping_required")
    if not isinstance(card, StrategyCard):
        raise TypeError("strategy_card_required")
    if card.strategy_id == ETF_STRATEGY_ID:
        return evaluate_etf_policy(snapshot, card)
    cost = _cost_usd(card)
    cost_text = _fmt(cost) if cost is not None else None
    valid, invalid_reason = _allowed_card(card)
    if not valid:
        return _result(card, ACTION_NO_TRADE, {}, invalid_reason, cost_text)

    position_state = _position(snapshot)
    if position_state is None:
        return _result(card, ACTION_NO_TRADE, {}, "snapshot_invalid", cost_text)
    positions, position = position_state
    quote = _quote(snapshot)
    if quote is None:
        return _result(card, ACTION_NO_TRADE, {}, "quote_invalid", cost_text)
    selected, bid, ask, quote_age = quote
    spread = (ask - bid) / ask
    quote_inputs = {"bid": bid, "ask": ask}
    if quote_age > MAX_QUOTE_AGE_SECONDS:
        return _result(card, ACTION_NO_TRADE, _signal_inputs(quote_inputs, quote_age=quote_age, spread=spread), "quote_stale", cost_text)
    if spread > MAX_SPREAD_FRACTION:
        return _result(card, ACTION_NO_TRADE, _signal_inputs(quote_inputs, quote_age=quote_age, spread=spread), "spread_too_wide", cost_text)

    bars = _normalise_bars(snapshot)
    if bars is None:
        return _result(card, ACTION_NO_TRADE, _signal_inputs(quote_inputs, quote_age=quote_age, spread=spread), "history_invalid", cost_text)
    indicators = _indicators(bars, str(card.strategy_id))
    if indicators is None:
        return _result(card, ACTION_NO_TRADE, _signal_inputs(quote_inputs, quote_age=quote_age, spread=spread), "history_insufficient", cost_text)

    is_reversion = card.strategy_id == "alpaca-btc-5m-reversion-v1"
    inputs = _signal_inputs(indicators, quote_age=quote_age, spread=spread)
    if positions == 0:
        if is_reversion:
            signal = indicators["rsi_14"] <= Decimal("30") and indicators["tema_9"] < indicators["bollinger_middle_20_2"]
        else:
            signal = indicators["ema_20"] > indicators["ema_50"] and indicators["close"] > indicators["prior_20_high"]
        if not signal:
            return _result(card, ACTION_NO_TRADE, inputs, "signal_false", cost_text)
        if cost is None:
            return _result(card, ACTION_NO_TRADE, inputs, "cost_model_incomplete", None)
        if _edge_usd(card, ask, indicators) <= cost:
            return _result(card, ACTION_NO_TRADE, inputs, "fee_threshold", cost_text)
        return _result(card, ACTION_ENTER, inputs, "signal_entry", cost_text)

    if positions != 1 or position is None:
        return _result(card, ACTION_NO_TRADE, inputs, "position_not_owned", cost_text)
    if position.get("symbol") not in BTC_SYMBOLS:
        return _result(card, ACTION_NO_TRADE, inputs, "position_not_owned", cost_text)
    try:
        entry_price = _decimal(position["entry_price"])
        if entry_price <= 0:
            raise InvalidOperation
    except (InvalidOperation, KeyError, TypeError):
        return _result(card, ACTION_NO_TRADE, inputs, "position_metadata_missing", cost_text)
    age_bars = _age_bars(bars, position.get("entry_timestamp"))
    if age_bars is None:
        return _result(card, ACTION_NO_TRADE, {**inputs, "age_bars": "unknown"}, "position_metadata_missing", cost_text)
    inputs["age_bars"] = str(age_bars)
    close = indicators["close"]
    if is_reversion:
        if indicators["rsi_14"] >= Decimal("70"):
            return _result(card, ACTION_EXIT, inputs, "rsi_exit", cost_text)
        if close >= indicators["bollinger_upper_20_2"]:
            return _result(card, ACTION_EXIT, inputs, "bollinger_exit", cost_text)
        if close <= entry_price - Decimal("1.5") * indicators["atr_14"]:
            return _result(card, ACTION_EXIT, inputs, "hard_stop", cost_text)
        if age_bars >= 12:
            return _result(card, ACTION_EXIT, inputs, "time_stop", cost_text)
    else:
        if close < indicators["ema_20"]:
            return _result(card, ACTION_EXIT, inputs, "ema_exit", cost_text)
        if close <= entry_price - Decimal("2") * indicators["atr_14"]:
            return _result(card, ACTION_EXIT, inputs, "hard_stop", cost_text)
        if age_bars >= 24:
            return _result(card, ACTION_EXIT, inputs, "time_stop", cost_text)
    return _result(card, ACTION_HOLD, inputs, "signal_hold", cost_text)


def load_selected_card(state: Path) -> tuple[StrategyCard, str]:
    """Load a release-pinned card, rejecting missing/stale selections.

    Task 7 will create the selection artifact.  Until then the live effect
    owner receives a typed no-trade rather than silently choosing a hypothesis.
    """
    try:
        payload = json.loads((state / "selected-strategy.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        raise ValueError("strategy_release_missing") from error
    if not isinstance(payload, Mapping):
        raise ValueError("strategy_release_invalid")
    release_sha = payload.get("release_sha")
    card_payload = payload.get("card")
    if not isinstance(release_sha, str) or not _RELEASE_SHA.fullmatch(release_sha):
        raise ValueError("strategy_release_invalid")
    if not isinstance(card_payload, Mapping):
        raise ValueError("strategy_release_invalid")
    card = StrategyCard.from_mapping(card_payload)
    if validate_strategy_card(card) or card.strategy_id not in candidate_cards():
        raise ValueError("strategy_release_invalid")
    canonical = candidate_cards()[str(card.strategy_id)]
    selected_mapping = card.to_mapping()
    canonical_mapping = canonical.to_mapping()
    # Validation may move a candidate from research to paper/shadow/live_candidate;
    # the rule, venue, cost, and risk fields must still be byte-for-byte canonical.
    selected_mapping["status"] = canonical_mapping["status"]
    if selected_mapping != canonical_mapping:
        raise ValueError("strategy_release_stale")
    expected = payload.get("strategy_id")
    if expected is not None and expected != card.strategy_id:
        raise ValueError("strategy_release_invalid")
    return card, release_sha


__all__ = [
    "ALLOWED_ACTIONS", "StrategyCard", "build_validation_candles", "candidate_cards",
    "ETF_STRATEGY_ID", "ETF_SYMBOLS", "evaluate", "load_selected_card",
]
