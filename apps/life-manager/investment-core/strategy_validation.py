"""Finite, read-only validation for declarative investment strategy cards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import re
from typing import Any

from strategy_cards import StrategyCard, is_valid_release_sha, validate_strategy_card


_MONEY = Decimal("0.01")
_BPS = Decimal("10000")
_RULE_TEXT = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*"
    r"([A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?)\s*$"
)
_OPERATORS = {
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "eq": "==",
    "neq": "!=",
}
_NEIGHBOR_OFFSETS = (-4, -3, -2, -1, 0, 1, 2, 3, 4)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _text(value: Decimal) -> str:
    return format(value, "f")


def _money(value: Decimal) -> str:
    return str(value.quantize(_MONEY, rounding=ROUND_HALF_EVEN))


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo is not None else None


def _normalize_candles(candles: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        rows = list(candles)
    except TypeError:
        return [], "candles_invalid"
    if not rows:
        return [], "candles_empty"

    normalized: list[dict[str, Any]] = []
    previous: datetime | None = None
    for row in rows:
        if not isinstance(row, Mapping):
            return [], "candle_invalid"
        parsed = _timestamp(row.get("timestamp"))
        if parsed is None:
            return [], "candle_timestamp_invalid"
        if previous is not None:
            if parsed == previous:
                return [], "duplicate_candle_timestamp"
            if parsed < previous:
                return [], "candle_timestamps_not_sorted"
        copied = dict(row)
        copied["timestamp"] = parsed.isoformat()
        normalized.append(copied)
        previous = parsed
    return normalized, None


def _ratio(value: Any) -> Decimal | None:
    if isinstance(value, str) and value.strip().endswith("%"):
        number = _decimal(value.strip()[:-1])
        return number / Decimal("100") if number is not None else None
    number = _decimal(value)
    if number is None:
        return None
    return number / Decimal("100") if number > 1 else number


def _partition_candles(
    candles: list[dict[str, Any]], split: Mapping[str, str] | None,
) -> tuple[dict[str, list[dict[str, Any]]] | None, str | None]:
    split = split if isinstance(split, Mapping) else {}
    if "train_end" in split or "validation_end" in split:
        train_end = _timestamp(split.get("train_end"))
        validation_end = _timestamp(split.get("validation_end"))
        if train_end is None or validation_end is None or train_end >= validation_end:
            return None, "split_boundaries_invalid"
        partitions = {"train": [], "validation": [], "holdout": []}
        for candle in candles:
            timestamp = _timestamp(candle["timestamp"])
            assert timestamp is not None
            if timestamp <= train_end:
                partitions["train"].append(candle)
            elif timestamp <= validation_end:
                partitions["validation"].append(candle)
            else:
                partitions["holdout"].append(candle)
        if any(not rows for rows in partitions.values()):
            return None, "split_partition_empty"
        return partitions, None

    train_ratio = _ratio(split.get("train", "60%"))
    validation_ratio = _ratio(split.get("validation", "20%"))
    holdout_ratio = _ratio(split.get("holdout", "20%"))
    if (train_ratio is None or validation_ratio is None or holdout_ratio is None
            or min(train_ratio, validation_ratio, holdout_ratio) <= 0
            or train_ratio + validation_ratio + holdout_ratio != Decimal("1")):
        return None, "split_ratios_invalid"
    if len(candles) < 3:
        return None, "split_too_short"

    train_count = int(Decimal(len(candles)) * train_ratio)
    validation_count = int(Decimal(len(candles)) * validation_ratio)
    train_count = max(1, train_count)
    validation_count = max(1, validation_count)
    if train_count + validation_count >= len(candles):
        validation_count = len(candles) - train_count - 1
    if validation_count < 1:
        return None, "split_too_short"
    validation_end = train_count + validation_count
    partitions = {
        "train": candles[:train_count],
        "validation": candles[train_count:validation_end],
        "holdout": candles[validation_end:],
    }
    if any(not rows for rows in partitions.values()):
        return None, "split_partition_empty"
    return partitions, None


def _lookahead(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return (
            "future" in lowered
            or bool(re.search(r"\[\s*\+\s*\d+", value))
            or bool(re.search(r"\bt\s*\+\s*\d+\b", lowered))
        )
    if isinstance(value, Mapping):
        if value.get("lookahead") is True:
            return True
        offset = _decimal(value.get("offset"))
        if offset is not None and offset > 0:
            return True
        return any(_lookahead(key) or _lookahead(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_lookahead(item) for item in value)
    return False


def _compare(left: Decimal | str, right: Decimal | str, operator: str) -> bool | None:
    op = _OPERATORS.get(operator, operator)
    if isinstance(left, Decimal) and isinstance(right, Decimal):
        values = (left, right)
    elif op in {"==", "!="}:
        values = (str(left), str(right))
    else:
        return None
    if op == ">":
        return values[0] > values[1]
    if op == ">=":
        return values[0] >= values[1]
    if op == "<":
        return values[0] < values[1]
    if op == "<=":
        return values[0] <= values[1]
    if op == "==":
        return values[0] == values[1]
    if op == "!=":
        return values[0] != values[1]
    return None


def _operand(value: Any, candle: Mapping[str, Any]) -> Decimal | str | None:
    number = _decimal(value)
    if number is not None:
        return number
    if isinstance(value, str) and value in candle:
        raw = candle.get(value)
        parsed = _decimal(raw)
        return parsed if parsed is not None else raw if isinstance(raw, str) else None
    return value if isinstance(value, str) else None


def _condition(rule: Any, candle: Mapping[str, Any]) -> bool | None:
    if isinstance(rule, str):
        match = _RULE_TEXT.match(rule)
        if not match:
            return None
        field, operator, expected = match.groups()
        if _lookahead(field):
            return None
        actual = _operand(candle.get(field), candle)
        wanted = _operand(expected, candle)
        if actual is None or wanted is None:
            return None
        return _compare(actual, wanted, operator)

    if not isinstance(rule, Mapping):
        return None
    if "all" in rule:
        values = [_condition(item, candle) for item in rule.get("all", [])]
        if any(value is False for value in values):
            return False
        return True if values and all(value is True for value in values) else None
    if "any" in rule:
        values = [_condition(item, candle) for item in rule.get("any", [])]
        if any(value is True for value in values):
            return True
        return False if values and all(value is False for value in values) else None

    field = rule.get("field")
    if not isinstance(field, str) or _lookahead(field):
        return None
    actual = _operand(candle.get(field), candle)
    wanted = _operand(rule.get("value"), candle)
    if actual is None or wanted is None:
        return None
    return _compare(actual, wanted, str(rule.get("op", "eq")))


def _cost_parameters(costs: Mapping[str, str]) -> tuple[dict[str, Decimal] | None, str | None]:
    if not isinstance(costs, Mapping):
        return None, "cost_model_incomplete"
    values: dict[str, Decimal] = {}
    for name, aliases in {
        "entry_fee_bps": ("entry_fee_bps", "fee_bps"),
        "exit_fee_bps": ("exit_fee_bps", "fee_bps"),
        "entry_slippage_bps": ("entry_slippage_bps", "slippage_bps"),
        "exit_slippage_bps": ("exit_slippage_bps", "slippage_bps"),
    }.items():
        raw = next((costs[key] for key in aliases if key in costs), None)
        parsed = _decimal(raw)
        if parsed is None or parsed < 0:
            return None, "cost_model_incomplete"
        values[name] = parsed
    return values, None


def _notional(card: StrategyCard) -> Decimal | None:
    if not isinstance(card.sizing_rule, Mapping):
        return None
    for key in ("notional_usd", "notional"):
        value = _decimal(card.sizing_rule.get(key))
        if value is not None and value > 0:
            return value
    return None


def _empty_summary() -> dict[str, Any]:
    return {
        "trades": 0,
        "turnover": "0",
        "gross_pnl_usd": "0.00",
        "net_pnl_usd": "0.00",
        "fees_usd": "0.00",
        "slippage_usd": "0.00",
        "max_drawdown_usd": "0.00",
    }


def _summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    gross = sum((_decimal(row["gross_pnl_usd"]) or Decimal("0") for row in trades), Decimal("0"))
    fees = sum((_decimal(row["fees_usd"]) or Decimal("0") for row in trades), Decimal("0"))
    slippage = sum((_decimal(row["slippage_usd"]) or Decimal("0") for row in trades), Decimal("0"))
    net = sum((_decimal(row["net_pnl_usd"]) or Decimal("0") for row in trades), Decimal("0"))
    equity = Decimal("0")
    peak = Decimal("0")
    drawdown = Decimal("0")
    for row in trades:
        equity += _decimal(row["net_pnl_usd"]) or Decimal("0")
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "trades": len(trades),
        # The finite evaluator has no volume stream; completed round trips are
        # the explicit comparable turnover proxy carried into selection.
        "turnover": str(len(trades)),
        "gross_pnl_usd": _money(gross),
        "net_pnl_usd": _money(net),
        "fees_usd": _money(fees),
        "slippage_usd": _money(slippage),
        "max_drawdown_usd": _money(drawdown),
    }


def _evaluate_partitions(
    card: StrategyCard,
    partitions: Mapping[str, list[dict[str, Any]]],
    costs: Mapping[str, Decimal],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], bool]:
    notional = _notional(card)
    if notional is None:
        return {name: _empty_summary() for name in partitions}, [], True

    summaries: dict[str, dict[str, Any]] = {}
    all_trades: list[dict[str, Any]] = []
    unknown = False
    for period in ("train", "validation", "holdout"):
        rows = partitions[period]
        position: dict[str, Any] | None = None
        trades: list[dict[str, Any]] = []
        for candle in rows:
            if position is None:
                signal = _condition(card.entry_rules, candle)
                if signal is None:
                    unknown = True
                    continue
                if signal:
                    price = _decimal(candle.get("close"))
                    if price is None or price <= 0:
                        unknown = True
                        continue
                    position = {
                        "timestamp": candle["timestamp"],
                        "price": price,
                        "quantity": notional / price,
                    }
                continue

            signal = _condition(card.exit_rules, candle)
            if signal is None:
                unknown = True
                continue
            if not signal:
                continue
            exit_price = _decimal(candle.get("close"))
            if exit_price is None or exit_price <= 0:
                unknown = True
                continue
            entry_price = position["price"]
            quantity = position["quantity"]
            exit_notional = quantity * exit_price
            gross = (exit_price - entry_price) * quantity
            fees = (notional * costs["entry_fee_bps"] + exit_notional * costs["exit_fee_bps"]) / _BPS
            slippage = (
                notional * costs["entry_slippage_bps"]
                + exit_notional * costs["exit_slippage_bps"]
            ) / _BPS
            trades.append({
                "period": period,
                "entry_timestamp": position["timestamp"],
                "exit_timestamp": candle["timestamp"],
                "entry_price": _text(entry_price),
                "exit_price": _text(exit_price),
                "quantity": _text(quantity),
                "gross_pnl_usd": _money(gross),
                "fees_usd": _money(fees),
                "slippage_usd": _money(slippage),
                "net_pnl_usd": _money(gross - fees - slippage),
            })
            position = None
        summaries[period] = _summary(trades)
        all_trades.extend(trades)
    return summaries, all_trades, unknown


def _find_parameter(value: Any, path: tuple[Any, ...] = ()) -> tuple[tuple[Any, ...], Decimal] | None:
    if isinstance(value, Mapping):
        if "field" in value and "value" in value:
            number = _decimal(value.get("value"))
            if number is not None:
                step = _decimal(value.get("step")) or Decimal("1")
                return path + ("value",), step
        for key in sorted(value, key=str):
            found = _find_parameter(value[key], path + (key,))
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _find_parameter(item, path + (index,))
            if found is not None:
                return found
    return None


def _replace_path(value: Any, path: tuple[Any, ...], replacement: Any) -> Any:
    copied = deepcopy(value)
    target = copied
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    return copied


def _parameter_sensitivity(
    card: StrategyCard,
    partitions: Mapping[str, list[dict[str, Any]]],
    costs: Mapping[str, Decimal],
) -> dict[str, Any]:
    mapping = card.to_mapping()
    selected: tuple[str, tuple[Any, ...], Decimal] | None = None
    for rule_name in ("entry_rules", "exit_rules"):
        found = _find_parameter(mapping.get(rule_name))
        if found is not None:
            selected = (rule_name, found[0], found[1])
            break
    if selected is None:
        return {
            "status": "not_evaluated",
            "total": 0,
            "positive_count": 0,
            "median_net_pnl_usd": "unknown",
            "neighbor_net_pnl_usd": [],
        }

    rule_name, path, step = selected
    original = _decimal(mapping[rule_name][path[0]]) if len(path) == 1 else None
    if original is None:
        # The common card shape has a logical wrapper, so locate the value by
        # applying the path to a deep copy instead of assuming a fixed depth.
        target: Any = mapping[rule_name]
        for key in path:
            target = target[key]
        original = _decimal(target)
    if original is None:
        return {
            "status": "not_evaluated",
            "total": 0,
            "positive_count": 0,
            "median_net_pnl_usd": "unknown",
            "neighbor_net_pnl_usd": [],
        }

    values: list[Decimal | None] = []
    for offset in _NEIGHBOR_OFFSETS:
        candidate_mapping = deepcopy(mapping)
        candidate_mapping[rule_name] = _replace_path(
            candidate_mapping[rule_name], path, _text(original + step * offset)
        )
        candidate_card = StrategyCard.from_mapping(candidate_mapping)
        _, trades, unknown = _evaluate_partitions(candidate_card, partitions, costs)
        if unknown or not trades:
            values.append(None)
        else:
            values.append(sum((_decimal(trade["net_pnl_usd"]) or Decimal("0") for trade in trades), Decimal("0")))

    numeric = [value for value in values if value is not None]
    positive_count = sum(value > 0 for value in numeric)
    if len(numeric) == len(values):
        ordered = sorted(numeric)
        median = ordered[len(ordered) // 2]
        median_text = _money(median)
        status = "evaluated"
    else:
        median_text = "unknown"
        status = "incomplete"
    return {
        "status": status,
        "total": len(values),
        "positive_count": positive_count,
        "median_net_pnl_usd": median_text,
        "neighbor_net_pnl_usd": ["unknown" if value is None else _money(value) for value in values],
    }


def _empty_report(strategy_id: Any, status: str, reason: str, lookahead: bool = False) -> dict[str, Any]:
    return {
        "status": status,
        "strategy_id": strategy_id,
        "train": _empty_summary(),
        "validation": _empty_summary(),
        "holdout": _empty_summary(),
        "trades": [],
        "net_pnl_usd": "0.00",
        "turnover": "0",
        "fees_usd": "0.00",
        "slippage_usd": "0.00",
        "max_drawdown_usd": "0.00",
        "lookahead_detected": lookahead,
        "parameter_sensitivity": {
            "status": "not_evaluated",
            "total": 0,
            "positive_count": 0,
            "median_net_pnl_usd": "unknown",
            "neighbor_net_pnl_usd": [],
        },
        "decision": "rejected",
        "reason": reason,
    }


def validate_series(
    card: StrategyCard,
    candles: Sequence[Mapping[str, Any]],
    split: Mapping[str, str],
    costs: Mapping[str, str],
) -> dict[str, Any]:
    """Evaluate a card against chronological candles without side effects."""
    if not isinstance(card, StrategyCard):
        return _empty_report(None, "rejected", "card_invalid")
    card_errors = validate_strategy_card(card)
    if card_errors:
        report = _empty_report(card.strategy_id, "rejected", "card_invalid")
        report["validation_errors"] = list(card_errors)
        return report
    if _lookahead(card.entry_rules) or _lookahead(card.exit_rules):
        return _empty_report(card.strategy_id, "rejected", "lookahead_detected", True)

    normalized, candle_error = _normalize_candles(candles)
    if candle_error is not None:
        status = "rejected" if candle_error.startswith(("duplicate", "candle_timestamps")) else "unknown"
        return _empty_report(card.strategy_id, status, candle_error)
    partitions, split_error = _partition_candles(normalized, split)
    if split_error is not None or partitions is None:
        return _empty_report(card.strategy_id, "rejected", split_error or "split_invalid")
    cost_values, cost_error = _cost_parameters(costs)
    if cost_error is not None or cost_values is None:
        return _empty_report(card.strategy_id, "unknown", cost_error or "cost_model_incomplete")

    summaries, trades, unknown = _evaluate_partitions(card, partitions, cost_values)
    sensitivity = _parameter_sensitivity(card, partitions, cost_values)
    total = _summary(trades)
    if unknown:
        status = "unknown"
    elif not trades:
        status = "no_trade"
    else:
        status = "measured"

    failures: list[str] = []
    if status != "measured":
        failures.append("required_input_unknown" if unknown else "no_trades")
    holdout_net = _decimal(summaries["holdout"]["net_pnl_usd"])
    if holdout_net is None or holdout_net <= 0:
        failures.append("holdout_net_non_positive")
    max_drawdown_limit = _decimal(card.risk_limits.get("max_drawdown_usd")) \
        if isinstance(card.risk_limits, Mapping) else None
    if max_drawdown_limit is None or max_drawdown_limit < 0:
        failures.append("max_drawdown_limit_missing")
    elif (_decimal(total["max_drawdown_usd"]) or Decimal("0")) > max_drawdown_limit:
        failures.append("max_drawdown_exceeded")
    if sensitivity["status"] != "evaluated":
        failures.append("parameter_sensitivity_incomplete")
    elif sensitivity["positive_count"] < 5:
        failures.append("parameter_sensitivity_negative")
    elif _decimal(sensitivity["median_net_pnl_usd"]) is None or _decimal(sensitivity["median_net_pnl_usd"]) <= 0:
        failures.append("parameter_sensitivity_median_non_positive")

    result = {
        "status": status,
        "strategy_id": card.strategy_id,
        "train": summaries["train"],
        "validation": summaries["validation"],
        "holdout": summaries["holdout"],
        "trades": trades,
        "net_pnl_usd": total["net_pnl_usd"],
        "turnover": summaries["holdout"]["turnover"],
        "fees_usd": total["fees_usd"],
        "slippage_usd": total["slippage_usd"],
        "max_drawdown_usd": total["max_drawdown_usd"],
        "lookahead_detected": False,
        "parameter_sensitivity": sensitivity,
        "decision": "paper" if not failures else "rejected",
    }
    if failures:
        result["reason"] = failures[0]
        result["failed_gates"] = failures
    return result


def _selection_copy(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _selection_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_selection_copy(item) for item in value]
    return value


def _selection_cost_complete(value: Any) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    numeric = False
    for item in value.values():
        if isinstance(item, Mapping):
            if not _selection_cost_complete(item):
                return False
            numeric = True
            continue
        if isinstance(item, (list, tuple)):
            if not item or not all(_selection_cost_complete({"value": nested}) for nested in item):
                return False
            numeric = True
            continue
        if isinstance(item, str) and item.strip().lower() in {"", "unknown", "missing", "none", "null"}:
            return False
        parsed = _decimal(item)
        if parsed is None or parsed < 0:
            return False
        numeric = True
    return numeric


def _selection_detail(report: Mapping[str, Any], index: int) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    strategy_id = report.get("strategy_id")
    report_id = report.get("report_id")
    card_value = report.get("card")
    card: StrategyCard | None = None
    reasons: list[str] = []

    if not isinstance(report_id, str) or not report_id.strip():
        reasons.append("report_id_missing")
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        reasons.append("strategy_id_missing")
    if not is_valid_release_sha(report.get("release_sha")):
        reasons.append("release_sha_invalid")
    if not isinstance(card_value, Mapping):
        reasons.append("card_invalid")
    else:
        try:
            card = StrategyCard.from_mapping(card_value)
            if validate_strategy_card(card):
                reasons.append("card_invalid")
            elif card.strategy_id != strategy_id:
                reasons.append("strategy_id_mismatch")
        except (TypeError, ValueError):
            reasons.append("card_invalid")

    if report.get("status") != "measured":
        reasons.append("validation_not_measured")
    if report.get("decision") != "paper":
        reasons.append("validation_not_paper")
    if report.get("lookahead_detected") is True:
        reasons.append("lookahead_detected")
    if report.get("failed_gates"):
        reasons.append("validation_gate_failed")

    holdout = report.get("holdout")
    holdout_net: Decimal | None = None
    holdout_drawdown: Decimal | None = None
    if not isinstance(holdout, Mapping):
        reasons.append("holdout_metrics_missing")
    else:
        holdout_net = _decimal(holdout.get("net_pnl_usd"))
        if holdout_net is None:
            reasons.append("holdout_net_invalid")
        elif holdout_net <= 0:
            reasons.append("holdout_net_non_positive")
        trades = _decimal(holdout.get("trades"))
        if trades is None or trades <= 0 or trades != trades.to_integral_value():
            reasons.append("holdout_trades_missing")
        holdout_drawdown = _decimal(holdout.get("max_drawdown_usd"))
        if holdout_drawdown is None or holdout_drawdown < 0:
            reasons.append("holdout_drawdown_invalid")

    cost_model = report.get("cost_model")
    if not _selection_cost_complete(cost_model):
        reasons.append("cost_model_incomplete")

    turnover = _decimal(report.get("turnover", holdout.get("turnover") if isinstance(holdout, Mapping) else None))
    if turnover is None or turnover < 0:
        reasons.append("turnover_missing")

    if report.get("stale") is True or report.get("fresh") is False:
        reasons.append("report_stale")
    elif "expires_at" in report:
        expires_at = _timestamp(report.get("expires_at"))
        if expires_at is None or expires_at <= datetime.now(timezone.utc):
            reasons.append("report_stale")

    evidence_ids = report.get("evidence_ids")
    if not isinstance(evidence_ids, (list, tuple)) or not evidence_ids:
        reasons.append("evidence_ids_missing")
        evidence_ids = []
    elif any(not isinstance(value, str) or not value.strip() for value in evidence_ids):
        reasons.append("evidence_ids_invalid")

    detail = {
        "index": index,
        "report_id": report_id if isinstance(report_id, str) else None,
        "strategy_id": strategy_id if isinstance(strategy_id, str) else None,
        "venue": card.venue if card is not None else report.get("venue"),
        "release_sha": report.get("release_sha") if isinstance(report.get("release_sha"), str) else None,
        "card": card.to_mapping() if card is not None else None,
        "holdout": _selection_copy(holdout) if isinstance(holdout, Mapping) else None,
        "cost_model": _selection_copy(cost_model) if isinstance(cost_model, Mapping) else None,
        "turnover": str(turnover) if turnover is not None else None,
        "evidence_ids": list(evidence_ids),
        "accepted": False,
        "rejection_reasons": reasons,
    }
    rank = {
        "holdout_net": holdout_net,
        "holdout_drawdown": holdout_drawdown,
        "turnover": turnover,
    }
    return detail, reasons, rank


def select_strategy(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Select one release-pinned strategy from complete validation reports.

    The function is pure and deterministic. It ignores model-generated scores
    or explanations; only declared evidence fields participate in the gates and
    ranking. A missing or conflicting evidence boundary returns ``NO_STRATEGY``.
    """
    if isinstance(reports, (str, bytes)) or not isinstance(reports, Sequence):
        reports = []

    details: list[dict[str, Any]] = []
    ranks: list[dict[str, Decimal | None]] = []
    for index, report in enumerate(reports):
        if not isinstance(report, Mapping):
            details.append({
                "index": index,
                "report_id": None,
                "strategy_id": None,
                "venue": None,
                "release_sha": None,
                "card": None,
                "holdout": None,
                "cost_model": None,
                "turnover": None,
                "evidence_ids": [],
                "accepted": False,
                "rejection_reasons": ["report_invalid"],
            })
            ranks.append({"holdout_net": None, "holdout_drawdown": None, "turnover": None})
            continue
        detail, _reasons, rank = _selection_detail(report, index)
        details.append(detail)
        ranks.append(rank)

    report_id_indexes: dict[str, list[int]] = {}
    evidence_indexes: dict[str, list[int]] = {}
    for index, detail in enumerate(details):
        report_id = detail.get("report_id")
        if report_id:
            report_id_indexes.setdefault(report_id, []).append(index)
        for evidence_id in detail.get("evidence_ids", []):
            if isinstance(evidence_id, str) and evidence_id:
                evidence_indexes.setdefault(evidence_id, []).append(index)
    for indexes in report_id_indexes.values():
        if len(indexes) > 1:
            for index in indexes:
                details[index]["rejection_reasons"].append("duplicate_report_id")
    for indexes in evidence_indexes.values():
        if len(indexes) > 1:
            for index in indexes:
                details[index]["rejection_reasons"].append("duplicate_evidence_id")

    accepted: list[tuple[Decimal, Decimal, Decimal, str, int]] = []
    for index, detail in enumerate(details):
        reasons = detail["rejection_reasons"]
        detail["rejection_reasons"] = list(dict.fromkeys(reasons))
        detail["accepted"] = not detail["rejection_reasons"]
        if not detail["accepted"]:
            continue
        rank = ranks[index]
        if (detail.get("strategy_id") is None or rank["holdout_net"] is None
                or rank["holdout_drawdown"] is None or rank["turnover"] is None):
            detail["accepted"] = False
            detail["rejection_reasons"] = ["selection_rank_invalid"]
            continue
        accepted.append((
            -rank["holdout_net"],
            rank["holdout_drawdown"],
            rank["turnover"],
            str(detail["strategy_id"]),
            index,
        ))

    if not accepted:
        rejection_reasons = sorted({
            reason for detail in details for reason in detail["rejection_reasons"]
        })
        if not details:
            rejection_reasons = ["validation_reports_missing"]
        return {
            "strategy_id": "NO_STRATEGY",
            "venue": None,
            "report_id": None,
            "release_sha": None,
            "card": None,
            "holdout": None,
            "cost_model": None,
            "rejection_reasons": rejection_reasons,
            "reports": details,
            "selection": "no_strategy",
        }

    accepted.sort()
    selected = details[accepted[0][4]]
    return {
        "strategy_id": selected["strategy_id"],
        "venue": selected["venue"],
        "report_id": selected["report_id"],
        "release_sha": selected["release_sha"],
        "card": selected["card"],
        "holdout": selected["holdout"],
        "cost_model": selected["cost_model"],
        "rejection_reasons": [],
        "reports": details,
        "selection": "selected",
    }


__all__ = ["select_strategy", "validate_series"]
