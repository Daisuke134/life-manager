"""Read-only conversion of Alpaca owner state into a canonical venue snapshot."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping


_COST_FIELDS = (
    "trading_fees_usd",
    "funding_or_borrow_usd",
    "slippage_usd",
    "gas_usd",
    "model_cost_usd",
)


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _measurement_status(snapshot: Mapping[str, Any], performance: Mapping[str, Any]) -> str:
    if performance.get("measurement_status") != "measured":
        return "partial"
    if any(snapshot.get(field) is None for field in (
        "observed_at", "equity_usd", "free_cash_usd", "gross_pnl_usd",
        *_COST_FIELDS, "source_receipt_ids",
    )):
        return "partial"
    if not snapshot.get("risk"):
        return "partial"
    return "measured"


def build_alpaca_snapshot(
    performance: Mapping[str, Any],
    observation: Mapping[str, Any],
    risk: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a provider-neutral snapshot without filling unknown costs."""
    if not isinstance(performance, Mapping) or not isinstance(observation, Mapping):
        raise ValueError("alpaca_snapshot_input_invalid")
    account = _mapping(observation.get("account")) or {}
    snapshot_risk = dict(risk) if isinstance(risk, Mapping) else {}
    if "round_trips" not in snapshot_risk:
        round_trips = performance.get(
            "completed_round_trips_total",
            performance.get("completed_round_trips"),
        )
        if isinstance(round_trips, int) and not isinstance(round_trips, bool):
            snapshot_risk["round_trips"] = round_trips
    if "drawdown_usd" not in snapshot_risk:
        drawdown = performance.get("observed_endpoint_drawdown_usd")
        if drawdown is not None:
            snapshot_risk["drawdown_usd"] = drawdown
    if "capital_at_risk_usd" not in snapshot_risk:
        exposure = performance.get("gross_exposure_usd")
        if exposure is not None:
            snapshot_risk["capital_at_risk_usd"] = exposure

    source_ids = performance.get("source_receipt_ids")
    if not isinstance(source_ids, list):
        source_ids = []
    snapshot = {
        "venue": "alpaca",
        "observed_at": performance.get("observed_at"),
        "equity_usd": account.get("equity"),
        "free_cash_usd": account.get("cash"),
        "gross_pnl_usd": performance.get("gross_strategy_pnl_usd"),
        "trading_fees_usd": performance.get("fees_usd"),
        "funding_or_borrow_usd": performance.get("funding_or_borrow_usd"),
        "slippage_usd": performance.get("slippage_usd"),
        "gas_usd": performance.get("gas_usd"),
        "model_cost_usd": performance.get("model_cost_usd"),
        "source_receipt_ids": list(source_ids),
        "risk": snapshot_risk,
        "measurement_status": "partial",
        "cost_evidence": {},
    }
    raw_cost_evidence = performance.get("cost_evidence")
    if isinstance(raw_cost_evidence, Mapping):
        snapshot["cost_evidence"] = {
            field: list(evidence_ids)
            for field, evidence_ids in raw_cost_evidence.items()
            if field in _COST_FIELDS
            and isinstance(evidence_ids, (list, tuple))
            and all(isinstance(item, str) and item for item in evidence_ids)
        }
    snapshot["measurement_status"] = _measurement_status(snapshot, performance)
    return snapshot


def _read_mapping(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _read_performance(
    root: Path,
    performance_day: str | None,
) -> tuple[Mapping[str, Any] | None, str | None]:
    if performance_day is None:
        path = root / "performance-latest.json"
        return _read_mapping(path), None
    if not isinstance(performance_day, str):
        return None, "alpaca_performance_day_invalid"
    try:
        parsed = date.fromisoformat(performance_day)
    except ValueError:
        return None, "alpaca_performance_day_invalid"
    if parsed.isoformat() != performance_day:
        return None, "alpaca_performance_day_invalid"
    path = root / f"performance-daily-{performance_day}.json"
    if not path.is_file():
        return None, "alpaca_daily_performance_missing"
    performance = _read_mapping(path)
    if performance is None:
        return None, "alpaca_daily_performance_invalid"
    if performance.get("performance_day") != performance_day:
        return None, "alpaca_daily_performance_day_mismatch"
    return performance, None


def read_alpaca_snapshot(
    state_dir: str | Path,
    *,
    performance_day: str | None = None,
) -> dict[str, Any]:
    """Read durable owner files for a snapshot, optionally pinned to a UTC day."""
    root = Path(state_dir).expanduser()
    performance, performance_error = _read_performance(root, performance_day)
    observation = _read_mapping(root / "observation-latest.json")
    risk = _read_mapping(root / "risk-latest.json")
    if performance_error is not None:
        return {"status": "unknown", "reason": performance_error}
    if performance is None or observation is None or risk is None:
        return {"status": "unknown", "reason": "alpaca_state_missing"}
    performance_for_snapshot: Mapping[str, Any] = performance
    if performance_day is not None:
        clock = observation.get("clock")
        observed_at = clock.get("observed_at") if isinstance(clock, Mapping) else None
        if not isinstance(observed_at, str) or not observed_at:
            return {"status": "unknown", "reason": "alpaca_observation_clock_missing"}
        performance_for_snapshot = {**performance, "observed_at": observed_at}
    try:
        return build_alpaca_snapshot(performance_for_snapshot, observation, risk)
    except (TypeError, ValueError):
        return {"status": "unknown", "reason": "alpaca_state_invalid"}


__all__ = ["build_alpaca_snapshot", "read_alpaca_snapshot"]
