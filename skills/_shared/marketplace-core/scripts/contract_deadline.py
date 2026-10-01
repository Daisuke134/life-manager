"""Provider-neutral contract-termination deadline facts.

Adapters may read a provider's termination-request page and pass the observed
facts here.  This module deliberately does not choose ``agree`` or ``reject``
and does not contain browser or provider selectors; it only normalizes facts
and classifies urgency for the shared reply queue.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


class ContractDeadlineValidationError(ValueError):
    """Raised when a provider observation cannot be trusted as a deadline."""


@dataclass(frozen=True)
class ContractTermination:
    platform: str
    request_id: str
    contract_id: str
    requested_at: str | None
    due_at: str | None
    current_state: str
    agree_url: str
    reject_flow: str
    client_reason: str

    def to_dict(self) -> dict[str, Any]:
        """Return a detached wire-safe observation without a decision field."""

        return asdict(self)


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractDeadlineValidationError(f"{field}_invalid")
    return value.strip()


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field)


def _timestamp(value: Any, field: str) -> str | None:
    raw = _optional_text(value, field)
    if raw is None:
        return None
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError, OverflowError):
        raise ContractDeadlineValidationError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractDeadlineValidationError(f"{field}_timezone_required")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_contract_termination(value: Mapping[str, Any]) -> ContractTermination:
    """Normalize one provider observation while preserving unknown deadlines.

    ``due_at`` and ``requested_at`` may be absent when the provider does not
    expose them.  The resulting ``unknown`` classification is intentionally
    fail-closed; callers must not treat it as permission to mutate state.
    """

    if not isinstance(value, Mapping):
        raise ContractDeadlineValidationError("observation_invalid")
    return ContractTermination(
        platform=_required_text(value.get("platform"), "platform"),
        request_id=_required_text(value.get("request_id"), "request_id"),
        contract_id=_required_text(value.get("contract_id"), "contract_id"),
        requested_at=_timestamp(value.get("requested_at"), "requested_at"),
        due_at=_timestamp(value.get("due_at"), "due_at"),
        current_state=_required_text(value.get("current_state"), "current_state"),
        agree_url=_required_text(value.get("agree_url"), "agree_url"),
        reject_flow=_required_text(value.get("reject_flow"), "reject_flow"),
        client_reason=str(value.get("client_reason") or "").strip(),
    )


def classify_deadline(
    termination: ContractTermination,
    *,
    now: datetime | None = None,
    urgent_within: timedelta = timedelta(hours=24),
) -> str:
    """Return ``overdue``, ``urgent``, ``upcoming``, or ``unknown``.

    The function is pure and timezone-aware.  ``unknown`` is returned when the
    provider did not expose a deadline, so a missing date cannot silently pass
    a deadline gate.
    """

    if not isinstance(termination, ContractTermination):
        raise ContractDeadlineValidationError("termination_invalid")
    if termination.due_at is None:
        return "unknown"
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ContractDeadlineValidationError("now_timezone_required")
    if urgent_within < timedelta(0):
        raise ContractDeadlineValidationError("urgent_within_invalid")
    due = datetime.fromisoformat(termination.due_at.replace("Z", "+00:00"))
    remaining = due - current.astimezone(timezone.utc)
    if remaining <= timedelta(0):
        return "overdue"
    if remaining <= urgent_within:
        return "urgent"
    return "upcoming"


__all__ = [
    "ContractDeadlineValidationError",
    "ContractTermination",
    "classify_deadline",
    "normalize_contract_termination",
]
