"""Small, source-labeled learning contracts for the Mercor funnel."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit


SOURCE_KINDS = frozenset({
    "official_guidance",
    "first_person",
    "marketing",
    "code",
    "official_receipt",
})
_POSITIVE_STAGES = frozenset({
    "offer",
    "trial",
    "contract",
    "paid",
    "settled",
    "payout_received",
    "received",
})


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def build_learning_candidate(
    *,
    source_url: str,
    source_kind: str,
    observation: str,
    hypothesis: str,
    target_stage: str,
    one_variable: str,
    strategy_version: str,
    baseline_cohort: Mapping[str, Any],
    proposed_change: Mapping[str, Any],
) -> dict[str, Any]:
    """Create one bounded hypothesis without promoting it to a provider fact."""
    url = _text(source_url, "source_url")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("source_url must be an https URL")
    kind = _text(source_kind, "source_kind")
    if kind not in SOURCE_KINDS:
        raise ValueError("unsupported source_kind")
    if not isinstance(baseline_cohort, Mapping):
        raise ValueError("baseline_cohort must be an object")
    resolved = baseline_cohort.get("resolved")
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 0:
        raise ValueError("baseline_cohort.resolved must be a nonnegative integer")
    if not isinstance(proposed_change, Mapping) or len(proposed_change) != 1:
        raise ValueError("proposed_change must contain exactly one variable")
    variable = _text(one_variable, "one_variable")
    if variable not in proposed_change:
        raise ValueError("proposed_change must match one_variable")
    return {
        "version": 1,
        "source_url": url,
        "source_kind": kind,
        "observation": _text(observation, "observation"),
        "hypothesis": _text(hypothesis, "hypothesis"),
        "target_stage": _text(target_stage, "target_stage"),
        "one_variable": variable,
        "strategy_version": _text(strategy_version, "strategy_version"),
        "baseline_cohort": dict(baseline_cohort),
        "proposed_change": dict(proposed_change),
    }


def evaluate_source_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    """Return zero income unless an official provider receipt proves the amount."""
    if not isinstance(claim, Mapping):
        raise ValueError("claim must be an object")
    source_kind = str(claim.get("source_kind") or "")
    claimed = claim.get("claimed_income_usd", 0)
    if isinstance(claimed, bool) or not isinstance(claimed, (int, float)):
        claimed = 0
    if not math.isfinite(float(claimed)) or float(claimed) < 0:
        claimed = 0
    official = (
        source_kind == "official_receipt"
        and claim.get("verified") is True
        and isinstance(claim.get("provider_receipt_id"), str)
        and bool(claim["provider_receipt_id"].strip())
        and isinstance(claim.get("evidence_ref"), str)
        and bool(claim["evidence_ref"].strip())
    )
    return {
        "verified_income_usd": float(claimed) if official else 0,
        "evidence_grade": "official_receipt" if official else "hypothesis_only",
    }


def _resolved_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        row for row in rows
        if isinstance(row, Mapping)
        and (
            row.get("resolved") is True
            or str(row.get("stage") or "") in _POSITIVE_STAGES
            or str(row.get("status") or "") in _POSITIVE_STAGES
        )
    ]


def _positive_rate(rows: Sequence[Mapping[str, Any]]) -> float:
    resolved = _resolved_rows(rows)
    if not resolved:
        return 0.0
    positive = sum(
        str(row.get("stage") or row.get("status") or "") in _POSITIVE_STAGES
        for row in resolved
    )
    return positive / len(resolved)


def decide_change(
    *,
    before: Sequence[Mapping[str, Any]],
    after: Sequence[Mapping[str, Any]],
    min_resolved: int = 5,
) -> dict[str, Any]:
    """Compare later official funnel outcomes, or remain inconclusive."""
    if not isinstance(min_resolved, int) or isinstance(min_resolved, bool) or min_resolved < 1:
        raise ValueError("min_resolved must be a positive integer")
    before_rows = _resolved_rows(before)
    after_rows = _resolved_rows(after)
    if len(before_rows) < min_resolved or len(after_rows) < min_resolved:
        return {
            "decision": "insufficient_evidence",
            "before_resolved": len(before_rows),
            "after_resolved": len(after_rows),
        }
    before_rate = _positive_rate(before)
    after_rate = _positive_rate(after)
    if after_rate > before_rate:
        decision = "keep"
    elif after_rate < before_rate:
        decision = "revert"
    else:
        decision = "pause"
    return {
        "decision": decision,
        "before_resolved": len(before_rows),
        "after_resolved": len(after_rows),
        "before_positive_rate": before_rate,
        "after_positive_rate": after_rate,
    }


__all__ = [
    "build_learning_candidate",
    "decide_change",
    "evaluate_source_claim",
]
