"""Pure cross-sectional ETF momentum research evaluator.

The module intentionally has no broker, credential, filesystem, or scheduler
side effects.  It consumes already-fetched daily bars and returns evidence that
can be reviewed before a strategy is represented as an executable card.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

from strategy_cards import StrategyCard


_MONEY = Decimal("0.01")
_BPS = Decimal("10000")
ETF_MOMENTUM_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA", "EFA", "EEM", "TLT", "GLD")


def strategy_card() -> StrategyCard:
    """Return the research-only card for the predeclared momentum hypothesis."""
    return StrategyCard.from_mapping({
        "strategy_id": "alpaca-etf-126d-momentum-v1",
        "venue": "alpaca",
        "instruments": list(ETF_MOMENTUM_UNIVERSE),
        "timeframe": "1d",
        "entry_rules": {"all": [
            {"field": "momentum_rank", "op": "eq", "value": "1"},
            {"field": "lookback_days", "op": "eq", "value": "126"},
        ]},
        "exit_rules": {"all": [
            {"field": "hold_sessions", "op": "gte", "value": "21"},
        ]},
        "sizing_rule": {"notional_usd": "10.00", "max_loss_usd": "10.00"},
        "cost_model": {
            "entry_fee_bps": "0",
            "exit_fee_bps": "0",
            "entry_slippage_bps": "10",
            "exit_slippage_bps": "10",
        },
        "risk_limits": {"trade_max_loss_usd": "10.00", "max_drawdown_usd": "20.00"},
        "kill_conditions": ["history_invalid", "missing_symbol", "cost_unknown", "effect_unknown"],
        "evidence_refs": [
            "https://doi.org/10.1111/j.1540-6261.1993.tb04702.x",
            "https://docs.alpaca.markets/us/reference/stockbars",
        ],
        "status": "research",
    })


def _number(value: Any, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("price_invalid")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("price_invalid") from error
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError("price_invalid")
    return number


def _cost(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("cost_invalid") from error
    if not number.is_finite() or number < 0:
        raise ValueError("cost_invalid")
    return number


def _session(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp_invalid") from error
    return parsed.date().isoformat()


def _normalize_symbol(symbol: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Decimal | str]]:
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        raise ValueError(f"bars_invalid:{symbol}")
    normalized: dict[str, dict[str, Decimal | str]] = {}
    previous: str | None = None
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"bars_invalid:{symbol}")
        session = _session(row.get("t", row.get("timestamp")))
        if previous is not None:
            if session == previous:
                raise ValueError("duplicate_session")
            if session < previous:
                raise ValueError("sessions_not_sorted")
        normalized[session] = {
            "session": session,
            "open": _number(row.get("o", row.get("open")), positive=True),
            "close": _number(row.get("c", row.get("close")), positive=True),
        }
        previous = session
    if not normalized:
        raise ValueError(f"bars_empty:{symbol}")
    return normalized


def _money(value: Decimal) -> str:
    return str(value.quantize(_MONEY, rounding=ROUND_HALF_EVEN))


def _summary(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gross = sum((Decimal(str(row["gross_pnl_usd"])) for row in trades), Decimal("0"))
    costs = sum((Decimal(str(row["cost_usd"])) for row in trades), Decimal("0"))
    net = sum((Decimal(str(row["net_pnl_usd"])) for row in trades), Decimal("0"))
    equity = Decimal("0")
    peak = Decimal("0")
    drawdown = Decimal("0")
    for row in trades:
        equity += Decimal(str(row["net_pnl_usd"]))
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "trades": len(trades),
        "gross_pnl_usd": _money(gross),
        "cost_usd": _money(costs),
        "net_pnl_usd": _money(net),
        "max_drawdown_usd": _money(drawdown),
    }


def _partitions(trades: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    count = len(trades)
    train_count = max(1, int(Decimal(count) * Decimal("0.60"))) if count else 0
    validation_count = max(1, int(Decimal(count) * Decimal("0.20"))) if count else 0
    if train_count + validation_count >= count:
        validation_count = max(0, count - train_count - 1)
    validation_end = train_count + validation_count
    result = {
        "train": trades[:train_count],
        "validation": trades[train_count:validation_end],
        "holdout": trades[validation_end:],
    }
    for period, rows in result.items():
        for row in rows:
            row["period"] = period
    return result


def _validated_inputs(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    universe: Sequence[str],
    lookback_days: int,
    hold_days: int,
    notional_usd: Any,
    entry_fee_bps: Any,
    exit_fee_bps: Any,
    entry_slippage_bps: Any,
    exit_slippage_bps: Any,
) -> tuple[tuple[str, ...], dict[str, dict[str, dict[str, Decimal | str]]], Decimal, Decimal, Decimal, Decimal, Decimal]:
    if isinstance(universe, (str, bytes)) or not isinstance(universe, Sequence):
        raise ValueError("universe_invalid")
    symbols = tuple(str(symbol) for symbol in universe)
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("universe_invalid")
    if not isinstance(bars_by_symbol, Mapping):
        raise ValueError("bars_invalid")
    normalized: dict[str, dict[str, dict[str, Decimal | str]]] = {}
    for symbol in symbols:
        if symbol not in bars_by_symbol:
            raise ValueError(f"symbol_missing:{symbol}")
        normalized[symbol] = _normalize_symbol(symbol, bars_by_symbol[symbol])
    if isinstance(lookback_days, bool) or not isinstance(lookback_days, int) or lookback_days < 1:
        raise ValueError("lookback_invalid")
    if isinstance(hold_days, bool) or not isinstance(hold_days, int) or hold_days < 1:
        raise ValueError("hold_invalid")
    notional = _number(notional_usd, positive=True)
    costs = tuple(_cost(value) for value in (
        entry_fee_bps, exit_fee_bps, entry_slippage_bps, exit_slippage_bps,
    ))
    return symbols, normalized, notional, *costs


def simulate(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    universe: Sequence[str],
    lookback_days: int,
    hold_days: int,
    notional_usd: Decimal,
    entry_fee_bps: Decimal,
    exit_fee_bps: Decimal,
    entry_slippage_bps: Decimal,
    exit_slippage_bps: Decimal,
) -> dict[str, Any]:
    """Simulate one fixed top-1 momentum hypothesis without side effects."""
    symbols, normalized, notional, entry_fee, exit_fee, entry_slippage, exit_slippage = _validated_inputs(
        bars_by_symbol, universe, lookback_days, hold_days, notional_usd,
        entry_fee_bps, exit_fee_bps, entry_slippage_bps, exit_slippage_bps,
    )
    common = sorted(set.intersection(*(set(normalized[symbol]) for symbol in symbols)))
    quality = {
        "rows_by_symbol": {symbol: len(normalized[symbol]) for symbol in symbols},
        "common_sessions": len(common),
        "dropped_sessions_by_symbol": {
            symbol: len(set(normalized[symbol]) - set(common)) for symbol in symbols
        },
        "first_session": common[0] if common else None,
        "last_session": common[-1] if common else None,
    }
    if len(common) <= lookback_days + hold_days:
        return {
            "status": "rejected", "decision": "rejected", "reason": "insufficient_sessions",
            "data_quality": quality, "trades": [],
            "train": _summary([]), "validation": _summary([]), "holdout": _summary([]),
        }

    rows = {symbol: [normalized[symbol][session] for session in common] for symbol in symbols}
    total_cost_bps = entry_fee + exit_fee + entry_slippage + exit_slippage
    fixed_cost = notional * total_cost_bps / _BPS
    trades: list[dict[str, Any]] = []
    decision_index = lookback_days
    while decision_index + hold_days < len(common):
        reference_index = decision_index - lookback_days
        ranking = []
        for symbol in symbols:
            reference = Decimal(str(rows[symbol][reference_index]["close"]))
            current = Decimal(str(rows[symbol][decision_index]["close"]))
            ranking.append((-(current / reference), symbol))
        _, symbol = min(ranking)
        entry_index = decision_index + 1
        exit_index = entry_index + hold_days - 1
        entry = Decimal(str(rows[symbol][entry_index]["open"]))
        exit_price = Decimal(str(rows[symbol][exit_index]["close"]))
        gross = (exit_price / entry - Decimal("1")) * notional
        trades.append({
            "decision_date": common[decision_index],
            "symbol": symbol,
            "entry_date": common[entry_index],
            "exit_date": common[exit_index],
            "entry_price": _money(entry),
            "exit_price": _money(exit_price),
            "gross_pnl_usd": _money(gross),
            "cost_usd": _money(fixed_cost),
            "net_pnl_usd": _money(gross - fixed_cost),
        })
        decision_index = exit_index

    partitions = _partitions(trades)
    summaries = {period: _summary(rows_for_period) for period, rows_for_period in partitions.items()}
    complete = all(summaries[period]["trades"] > 0 for period in ("train", "validation", "holdout"))
    return {
        "status": "measured" if complete else "rejected",
        "decision": "measured" if complete else "rejected",
        "reason": None if complete else "insufficient_trades",
        "data_quality": quality,
        "trades": trades,
        **summaries,
    }


def screen_grid(
    bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    universe: Sequence[str],
    lookbacks: Sequence[int],
    hold_days: Sequence[int],
    notional_usd: Decimal,
    entry_fee_bps: Decimal,
    exit_fee_bps: Decimal,
    entry_slippage_bps: Decimal,
    exit_slippage_bps: Decimal,
) -> dict[str, Any]:
    """Evaluate a predeclared neighboring grid without choosing parameters."""
    grid: list[dict[str, Any]] = []
    for lookback in lookbacks:
        for hold in hold_days:
            result = simulate(
                bars_by_symbol, universe=universe, lookback_days=lookback,
                hold_days=hold, notional_usd=notional_usd,
                entry_fee_bps=entry_fee_bps, exit_fee_bps=exit_fee_bps,
                entry_slippage_bps=entry_slippage_bps,
                exit_slippage_bps=exit_slippage_bps,
            )
            holdout = result["holdout"]
            grid.append({
                "lookback_days": lookback,
                "hold_days": hold,
                "decision": result["decision"],
                "holdout_trades": holdout["trades"],
                "holdout_net_pnl_usd": holdout["net_pnl_usd"],
            })
    nets = [Decimal(row["holdout_net_pnl_usd"]) for row in grid]
    positive_count = sum(1 for row in grid if row["decision"] == "measured" and Decimal(row["holdout_net_pnl_usd"]) > 0)
    ordered = sorted(nets)
    median = ordered[len(ordered) // 2] if ordered else None
    complete = all(row["decision"] == "measured" for row in grid)
    return {
        "grid": grid,
        "positive_count": positive_count,
        "median_holdout_net_pnl_usd": _money(median) if median is not None else None,
        "gate": bool(complete and positive_count >= 5 and median is not None and median > 0),
    }


__all__ = ["ETF_MOMENTUM_UNIVERSE", "screen_grid", "simulate", "strategy_card"]
