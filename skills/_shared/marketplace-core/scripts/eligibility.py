"""Provider-neutral pre-application eligibility policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
from typing import Any, Mapping


def _load_deadline_module():
    name = "anicca_marketplace_contract_deadline_for_eligibility"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).with_name("contract_deadline.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("marketplace_contract_deadline_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_deadline = _load_deadline_module()


class EligibilityValidationError(ValueError):
    """Raised when eligibility evidence cannot be trusted."""


@dataclass(frozen=True)
class EligibilityDecision:
    status: str
    reason: str
    matched_project_id: str | None = None
    matched_buyer_id: str | None = None
    eligible_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EligibilityValidationError(f"{field}_invalid")
    return value.strip()


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise EligibilityValidationError("now_timezone_required")
    return current.astimezone(timezone.utc)


def _unknown(reason: str = "eligibility_unknown") -> EligibilityDecision:
    return EligibilityDecision(status="unknown", reason=reason)


def evaluate_reapplication(
    opportunity: Mapping[str, Any],
    history: list[Mapping[str, Any]],
    *,
    history_complete: bool,
    cooldown_days: int = 183,
    now: datetime | None = None,
) -> EligibilityDecision:
    """Fail closed unless official history proves this application is eligible.

    History rows use only provider-neutral fields: ``external_id``,
    ``buyer_external_id`` and strict RFC3339 ``submitted_at``.  This function
    never submits, mutates, or chooses a provider-specific application route.
    """

    if not isinstance(opportunity, Mapping):
        raise EligibilityValidationError("opportunity_invalid")
    project_id = _text(opportunity.get("external_id"), "project_id")
    buyer_id = opportunity.get("buyer_external_id")
    if buyer_id is None or not isinstance(buyer_id, str) or not buyer_id.strip():
        return _unknown("buyer_identity_missing")
    buyer_id = buyer_id.strip()
    if not isinstance(history, list):
        raise EligibilityValidationError("history_invalid")
    if not isinstance(history_complete, bool):
        raise EligibilityValidationError("history_complete_invalid")
    if isinstance(cooldown_days, bool) or not isinstance(cooldown_days, int) or cooldown_days < 0:
        raise EligibilityValidationError("cooldown_days_invalid")
    current = _now(now)
    if not history_complete:
        return _unknown()

    cooldown = timedelta(days=cooldown_days)
    for row in history:
        if not isinstance(row, Mapping):
            raise EligibilityValidationError("history_row_invalid")
        prior_project = _text(row.get("external_id"), "history_project_id")
        prior_buyer = _text(row.get("buyer_external_id"), "history_buyer_id")
        raw_submitted = row.get("submitted_at")
        try:
            submitted_at = _deadline.normalize_timestamp(raw_submitted, field="submitted_at")
        except _deadline.ContractDeadlineValidationError as error:
            raise EligibilityValidationError(str(error)) from None
        if submitted_at is None:
            raise EligibilityValidationError("submitted_at_invalid")
        submitted = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
        if submitted > current:
            raise EligibilityValidationError("submitted_at_future")
        if prior_project == project_id:
            return EligibilityDecision(
                status="ineligible", reason="duplicate_project",
                matched_project_id=prior_project, matched_buyer_id=prior_buyer,
            )
        if prior_buyer != buyer_id:
            continue
        eligible_at = submitted + cooldown
        if eligible_at > current:
            return EligibilityDecision(
                status="ineligible", reason="provider_reapply_cooldown",
                matched_project_id=prior_project, matched_buyer_id=prior_buyer,
                eligible_at=eligible_at.isoformat().replace("+00:00", "Z"),
            )
    return EligibilityDecision(status="eligible", reason="eligible")


__all__ = [
    "EligibilityDecision",
    "EligibilityValidationError",
    "evaluate_reapplication",
]
