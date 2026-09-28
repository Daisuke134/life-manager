"""Pure, receipt-backed capital promotion recommendations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Mapping, Optional

from risk_policy import CAPITAL_LADDER_USD, LADDER_MIN_ROUND_TRIPS


MONEY = Decimal("0.01")


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _money(value: Decimal) -> str:
    return str(value.quantize(MONEY, rounding=ROUND_HALF_EVEN))


def _evidence_ids(evidence: Mapping[str, Any]) -> list[str]:
    values = evidence.get("source_receipt_ids")
    if not isinstance(values, (list, tuple)):
        return []
    return [value for value in values if isinstance(value, str) and value]


def _result(status: str, current: Decimal, next_cap: Decimal,
            reasons: list[str], evidence_ids: list[str]) -> dict[str, Any]:
    return {
        "capital_expansion_allowed": False,
        "current_cap_usd": _money(current),
        "evidence_ids": evidence_ids,
        "next_cap_usd": _money(next_cap),
        "owner_authorization_required": True,
        "reasons": reasons,
        "status": status,
    }


def _requested_cap_reason(requested: Optional[Decimal], current: Decimal,
                          next_cap: Optional[Decimal]) -> list[str]:
    if requested is None:
        return ["requested_cap_required"]
    if requested not in CAPITAL_LADDER_USD:
        return ["requested_cap_not_discrete"]
    if requested < current:
        return ["requested_cap_below_current"]
    if requested == current:
        return []
    if next_cap is None:
        return ["maximum_cap_reached"]
    if requested != next_cap:
        return ["next_discrete_cap_required"]
    return []


def _evidence_reasons(evidence: Any) -> tuple[list[str], list[str]]:
    if not isinstance(evidence, Mapping):
        return ["evidence_invalid"], []
    reasons: list[str] = []
    ids = _evidence_ids(evidence)
    raw_ids = evidence.get("source_receipt_ids")
    if (not ids or not isinstance(raw_ids, (list, tuple))
            or len(ids) != len(raw_ids) or len(set(ids)) != len(ids)):
        reasons.append("source_receipt_invalid")

    if evidence.get("paper") is True or evidence.get("measurement_mode") == "paper":
        reasons.append("paper_evidence")
    if evidence.get("measurement_status") != "measured":
        reasons.append("measurement_not_measured")
    if evidence.get("measurement_mode") != "live":
        reasons.append("live_evidence_required")

    net = _decimal(evidence.get("net_pnl_usd"))
    if net is None:
        reasons.append("net_unknown")
    elif net <= 0:
        reasons.append("net_non_positive")

    trips = evidence.get("completed_round_trips")
    if isinstance(trips, bool) or not isinstance(trips, int) or trips < LADDER_MIN_ROUND_TRIPS:
        reasons.append("sample_insufficient")

    unknown_costs = evidence.get("unknown_costs")
    if (evidence.get("costs_complete") is not True
            or not isinstance(unknown_costs, (list, tuple)) or unknown_costs):
        reasons.append("cost_unknown")

    drawdown = _decimal(evidence.get("drawdown_usd"))
    drawdown_limit = _decimal(evidence.get("drawdown_limit_usd"))
    if drawdown is None or drawdown_limit is None:
        reasons.append("drawdown_unknown")
    elif drawdown < 0 or drawdown > drawdown_limit:
        reasons.append("risk_breach")
    if evidence.get("risk_breach") is True:
        reasons.append("risk_breach")
    if evidence.get("venue_health") != "healthy":
        reasons.append("venue_unhealthy")
    return list(dict.fromkeys(reasons)), ids


def recommend_next_cap(evidence: Any, current_cap: Any, requested_cap: Any) -> dict[str, Any]:
    """Recommend one discrete next cap without changing runtime state or placing orders."""
    current = _decimal(current_cap)
    if current is None or current not in CAPITAL_LADDER_USD:
        fallback = current if current is not None and current > 0 else CAPITAL_LADDER_USD[0]
        return _result("reject", fallback, fallback, ["current_cap_invalid"], _evidence_ids(evidence) if isinstance(evidence, Mapping) else [])

    index = CAPITAL_LADDER_USD.index(current)
    next_cap = CAPITAL_LADDER_USD[index + 1] if index + 1 < len(CAPITAL_LADDER_USD) else None
    requested = _decimal(requested_cap)
    cap_reasons = _requested_cap_reason(requested, current, next_cap)
    evidence_reasons, ids = _evidence_reasons(evidence)
    reasons = list(dict.fromkeys(cap_reasons + evidence_reasons))
    output_next = requested if requested in CAPITAL_LADDER_USD and requested > current else (next_cap or current)

    if requested == current and not cap_reasons:
        return _result("hold", current, current, ["current_cap_unchanged"], ids)
    if reasons:
        return _result("reject", current, output_next, reasons, ids)
    return _result("recommend", current, output_next, [], ids)
