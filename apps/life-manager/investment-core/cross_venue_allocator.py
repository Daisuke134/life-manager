"""Pure, read-only ranking of measured cross-venue net-P&L candidates."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Iterable

from net_pnl import venue_net


_MONEY = Decimal("0.01")


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _money(value: Decimal) -> str:
    return str(value.quantize(_MONEY, rounding=ROUND_HALF_EVEN))


def _invalid_candidate(venue: Any, reason: str) -> dict[str, Any]:
    return {"venue": venue, "candidate_ref": f"venue://{venue}" if venue else None, "reason": reason}


def build_candidates(snapshots: Iterable[Any], aggregate: dict[str, Any], caps: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(aggregate, dict) or aggregate.get("measurement_status") != "measured":
        return []
    try:
        rows = list(snapshots)
    except TypeError:
        return []
    candidates: list[dict[str, Any]] = []
    for snapshot in rows:
        row = venue_net(snapshot)
        if row.get("measurement_status") != "measured":
            continue
        net = _decimal(row.get("net_pnl_usd"))
        risk = dict(row.get("risk") or {})
        capital_at_risk = _decimal(risk.get("capital_at_risk_usd"))
        if capital_at_risk is None or capital_at_risk <= 0:
            capital_at_risk = _decimal(caps.get("current_cap_usd"))
        if net is None or capital_at_risk is None or capital_at_risk <= 0:
            continue
        candidates.append({
            "candidate_ref": f"venue://{row['venue']}",
            "venue": row["venue"],
            "verified": True,
            "measurement_status": "measured",
            "net_pnl_usd": row["net_pnl_usd"],
            "gross_pnl_usd": row["gross_pnl_usd"],
            "trading_fees_usd": row["trading_fees_usd"],
            "funding_or_borrow_usd": row["funding_or_borrow_usd"],
            "slippage_usd": row["slippage_usd"],
            "gas_usd": row["gas_usd"],
            "model_cost_usd": row["model_cost_usd"],
            "source_receipt_ids": list(row["source_receipt_ids"]),
            "observed_at": row["observed_at"],
            "risk": risk,
            "capital_at_risk_usd": _money(capital_at_risk),
            "net_return_per_dollar": str(net / capital_at_risk),
        })
    return candidates


def rank(candidates: Iterable[dict[str, Any]], available_capital: Any, caps: dict[str, Any]) -> dict[str, Any]:
    available = _decimal(available_capital)
    reserve = _decimal(caps.get("cash_reserve_usd"))
    max_allocation = _decimal(caps.get("max_allocation_usd"))
    current_cap = _decimal(caps.get("current_cap_usd"))
    max_drawdown = _decimal(caps.get("max_drawdown_fraction"))
    min_round_trips = caps.get("min_round_trips")
    result = {
        "action": "hold",
        "ranked": [],
        "excluded": [],
        "allocation_usd": "0.00",
        "capital_expansion_allowed": False,
        "reason": "no_eligible_candidate",
    }
    if available is None or available < 0 or reserve is None or max_allocation is None or current_cap is None or max_drawdown is None:
        result.update(action="halt", reason="allocator_caps_invalid")
        return result
    if not isinstance(min_round_trips, int) or isinstance(min_round_trips, bool) or min_round_trips < 0:
        result.update(action="halt", reason="allocator_caps_invalid")
        return result
    if available <= reserve:
        result["reason"] = "cash_reserve"
        return result
    try:
        rows = list(candidates)
    except TypeError:
        result.update(action="halt", reason="candidates_invalid")
        return result

    eligible: list[dict[str, Any]] = []
    for candidate in rows:
        if not isinstance(candidate, dict):
            result["excluded"].append(_invalid_candidate(None, "candidate_invalid"))
            continue
        venue = candidate.get("venue")
        if candidate.get("verified") is not True or candidate.get("measurement_status") != "measured":
            result["excluded"].append(_invalid_candidate(venue, "measurement_unknown"))
            continue
        if candidate.get("stale") is True:
            result["excluded"].append(_invalid_candidate(venue, "stale_snapshot"))
            continue
        risk = candidate.get("risk") if isinstance(candidate.get("risk"), dict) else {}
        drawdown = _decimal(risk.get("drawdown_fraction"))
        if drawdown is None:
            result["excluded"].append(_invalid_candidate(venue, "drawdown_unknown"))
            continue
        if drawdown > max_drawdown:
            result.update(action="halt", reason="drawdown_breach", allocation_usd="0.00")
            result["excluded"].append(_invalid_candidate(venue, "drawdown_breach"))
            return result
        round_trips = risk.get("round_trips")
        if not isinstance(round_trips, int) or isinstance(round_trips, bool) or round_trips < min_round_trips:
            result["excluded"].append(_invalid_candidate(venue, "sample_below_threshold"))
            continue
        net = _decimal(candidate.get("net_pnl_usd"))
        if net is None or net <= 0:
            result["excluded"].append(_invalid_candidate(venue, "non_positive_net"))
            continue
        requested_cap = _decimal(candidate.get("requested_cap_usd", current_cap))
        if requested_cap is None or requested_cap <= 0:
            result["excluded"].append(_invalid_candidate(venue, "requested_cap_invalid"))
            continue
        if requested_cap > current_cap:
            result["excluded"].append(_invalid_candidate(venue, "capital_expansion_denied"))
            continue
        score = _decimal(candidate.get("net_return_per_dollar"))
        if score is None:
            result["excluded"].append(_invalid_candidate(venue, "return_unknown"))
            continue
        eligible.append({**candidate, "_score": score, "_net": net})

    eligible.sort(key=lambda row: (-row["_score"], -row["_net"], str(row.get("venue") or "")))
    if not eligible:
        return result
    allocation = min(available - reserve, max_allocation, current_cap)
    if allocation <= 0:
        result["reason"] = "cash_reserve"
        return result
    ranked = []
    for row in eligible:
        clean = {key: value for key, value in row.items() if not key.startswith("_")}
        clean["allocation_usd"] = _money(allocation)
        ranked.append(clean)
    result.update(action="allocate", reason="verified_net_candidate", ranked=ranked, allocation_usd=_money(allocation))
    return result

