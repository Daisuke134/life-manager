"""Read-only conversion of Alpaca owner state into a canonical venue snapshot."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


_COST_FIELDS = (
    "trading_fees_usd",
    "funding_or_borrow_usd",
    "slippage_usd",
    "gas_usd",
    "model_cost_usd",
    "system_cost_usd",
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
    if (performance.get("report_scope") in ("owned_crypto_cycles", "owned_crypto_cycles_daily")
            and not _crypto_contract(performance, daily=performance.get("report_scope") == "owned_crypto_cycles_daily")):
        raise ValueError("alpaca_crypto_performance_invalid")
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
        "measurement_mode": performance.get("measurement_mode", performance.get("mode")),
        "paper": performance.get("paper"),
        "observed_at": performance.get("observed_at"),
        "equity_usd": account.get("equity"),
        "free_cash_usd": account.get("cash"),
        "gross_pnl_usd": performance.get("gross_strategy_pnl_usd"),
        "trading_fees_usd": performance.get("fees_usd"),
        "funding_or_borrow_usd": performance.get("funding_or_borrow_usd"),
        "slippage_usd": performance.get("slippage_usd"),
        "gas_usd": performance.get("gas_usd"),
        "model_cost_usd": performance.get("model_cost_usd"),
        "system_cost_usd": performance.get("system_cost_usd"),
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
    if performance.get("paper") is True or performance.get("mode") == "paper":
        if (performance.get("paper") is not True
                or performance.get("mode") not in (None, "paper")
                or performance.get("slippage_included_in_gross_pnl") is not True):
            return snapshot
        try:
            gross = Decimal(str(snapshot["gross_pnl_usd"]))
            slippage = Decimal(str(snapshot["slippage_usd"]))
            if not gross.is_finite() or not slippage.is_finite():
                return snapshot
            # Core subtracts signed slippage; fill gross already includes it.
            snapshot["gross_pnl_usd"] = str(gross + slippage)
        except (ArithmeticError, TypeError, ValueError):
            return snapshot
    mode = snapshot["measurement_mode"]
    if (mode not in ("paper", "live", "shadow")
            or type(snapshot["paper"]) is not bool
            or snapshot["paper"] != (mode == "paper")
            or performance.get("mode", mode) != mode):
        return snapshot
    snapshot["measurement_status"] = _measurement_status(snapshot, performance)
    return snapshot


def _read_mapping(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _utc_day(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).date().isoformat()


def _crypto_contract(value: Any, *, daily: bool = False) -> bool:
    """Scoped operating costs do not make BTC economics measured or settled."""
    if not isinstance(value, Mapping):
        return False
    mode = value.get("mode")
    return (isinstance(mode, str) and mode in {"paper", "live"}
            and type(value.get("schema_version")) is int and value["schema_version"] == 1
            and value.get("owner_id") == f"alpaca-investment-{mode}"
            and value.get("paper") is (mode == "paper")
            and value.get("report_scope") == ("owned_crypto_cycles_daily" if daily else "owned_crypto_cycles")
            and value.get("measurement_status") == "partial"
            and value.get("capital_expansion_allowed") is False
            and _crypto_operating_costs(value)
            and all(value.get(field) is None for field in (
                "gross_strategy_pnl_usd", "net_pnl_usd", "fees_usd", "funding_or_borrow_usd",
                "slippage_usd", "gas_usd")))


def _crypto_operating_costs(value: Mapping[str, Any]) -> bool:
    amounts=[value.get(field) for field in ("model_cost_usd", "system_cost_usd")]
    if all(amount is None for amount in amounts):
        return True
    coverage=value.get("operating_cost_coverage")
    if (value.get("operating_costs_status") != "complete" or not isinstance(coverage, Mapping)
            or coverage.get("coverage_state") != "complete"):
        return False
    try:
        return all(isinstance(amount, str) and bool(amount) and amount == amount.strip()
            and Decimal(amount).is_finite() and Decimal(amount) >= 0 for amount in amounts)
    except (ArithmeticError, ValueError):
        return False


def _read_performance(
    root: Path,
    performance_day: str | None,
) -> tuple[Mapping[str, Any] | None, str | None]:
    crypto = ((root / "performance-crypto-latest.json").exists()
              or any(root.glob("performance-crypto-daily-????-??-??.json")))
    prefix = "performance-crypto" if crypto else "performance"
    if performance_day is None:
        path = root / f"{prefix}-latest.json"
        value = _read_mapping(path)
        if crypto and not _crypto_contract(value):
            return None, "alpaca_crypto_performance_invalid"
        return value, None
    if not isinstance(performance_day, str):
        return None, "alpaca_performance_day_invalid"
    try:
        parsed = date.fromisoformat(performance_day)
    except ValueError:
        return None, "alpaca_performance_day_invalid"
    if parsed.isoformat() != performance_day:
        return None, "alpaca_performance_day_invalid"
    path = root / f"{prefix}-daily-{performance_day}.json"
    if not path.is_file():
        if crypto:
            return None, "alpaca_crypto_daily_performance_missing"
        # Keep a narrow migration path for an older live gate that only wrote
        # latest: it is acceptable only when its own observation is exactly
        # the requested completed day, never when latest is a new-day record.
        legacy = _read_mapping(root / "performance-latest.json")
        if (legacy is not None
                and legacy.get("performance_day") in (None, performance_day)
                and legacy.get("daily_receipt_reused") is not True
                and legacy.get("daily_receipt_written") is not False
                and _utc_day(legacy.get("observed_at")) == performance_day):
            return legacy, None
        return None, "alpaca_daily_performance_missing"
    performance = _read_mapping(path)
    if crypto and not _crypto_contract(performance, daily=True):
        return None, "alpaca_crypto_daily_performance_invalid"
    if performance is None:
        return None, "alpaca_daily_performance_invalid"
    if performance.get("performance_day") != performance_day:
        return None, "alpaca_daily_performance_day_mismatch"
    if _utc_day(performance.get("observed_at")) != performance_day:
        return None, "alpaca_daily_performance_timestamp_mismatch"
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
        readback_id = f"alpaca-account-readback:{observed_at}"
        source_ids = performance.get("source_receipt_ids")
        if not isinstance(source_ids, list):
            return {"status": "unknown", "reason": "alpaca_source_receipts_invalid"}
        if readback_id not in source_ids:
            source_ids = [*source_ids, readback_id]
        performance_for_snapshot = {
            **performance,
            "observed_at": observed_at,
            "source_receipt_ids": source_ids,
        }
    try:
        return build_alpaca_snapshot(performance_for_snapshot, observation, risk)
    except (TypeError, ValueError):
        return {"status": "unknown", "reason": "alpaca_state_invalid"}


__all__ = ["build_alpaca_snapshot", "read_alpaca_snapshot"]
