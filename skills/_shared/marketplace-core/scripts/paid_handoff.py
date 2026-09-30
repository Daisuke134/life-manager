"""Small shared builder for provider-specific funded Paid handoffs.

Provider adapters still own official observation and field extraction.  This
module owns only the provider-independent shape checks so a new platform does
not invent a second receipt format.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping


_HASH = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class PaidHandoffMappingError(ValueError):
    """Provider facts cannot be mapped to the shared funded boundary."""


def _text(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaidHandoffMappingError(reason)
    return value.strip()


def _hash(value: Any, reason: str) -> str:
    value = _text(value, reason)
    if not _HASH.fullmatch(value):
        raise PaidHandoffMappingError(reason)
    return value


def _observed_at(value: Any) -> str:
    value = _text(value, "observed_at_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PaidHandoffMappingError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PaidHandoffMappingError("observed_at_invalid")
    return value


def build_paid_handoff(
    *,
    platform: str,
    application_external_id: str,
    work_external_id: str,
    contract_external_id: str,
    funding_external_id: str,
    thread_external_id: str,
    terms_sha256: str,
    scope_sha256: str,
    artifact_requirement_sha256: str,
    price_minor: int,
    currency: str,
    observed_at: str,
) -> dict[str, dict[str, Any]]:
    """Build the one canonical accepted-contract/funded-handoff pair."""
    platform = _text(platform, "platform_invalid")
    application_external_id = _text(application_external_id, "application_external_id_invalid")
    work_external_id = _text(work_external_id, "work_external_id_invalid")
    contract_external_id = _text(contract_external_id, "contract_external_id_invalid")
    funding_external_id = _text(funding_external_id, "funding_external_id_invalid")
    thread_external_id = _text(thread_external_id, "thread_external_id_invalid")
    terms_sha256 = _hash(terms_sha256, "terms_sha256_invalid")
    scope_sha256 = _hash(scope_sha256, "scope_sha256_invalid")
    artifact_requirement_sha256 = _hash(
        artifact_requirement_sha256, "artifact_requirement_sha256_invalid",
    )
    if type(price_minor) is not int or price_minor < 1:
        raise PaidHandoffMappingError("price_minor_invalid")
    currency = _text(currency, "currency_invalid")
    if not _CURRENCY.fullmatch(currency):
        raise PaidHandoffMappingError("currency_invalid")
    observed_at = _observed_at(observed_at)
    return {
        "contract": {
            "schema_version": 1,
            "record_type": "contract_receipt",
            "platform": platform,
            "application_external_id": application_external_id,
            "work_external_id": work_external_id,
            "contract_external_id": contract_external_id,
            "status": "accepted",
            "terms_sha256": terms_sha256,
            "observed_at": observed_at,
        },
        "handoff": {
            "schema_version": 1,
            "record_type": "paid_handoff_receipt",
            "platform": platform,
            "thread_external_id": thread_external_id,
            "contract_external_id": contract_external_id,
            "funding_external_id": funding_external_id,
            "scope_sha256": scope_sha256,
            "artifact_requirement_sha256": artifact_requirement_sha256,
            "price_minor": price_minor,
            "currency": currency,
            "status": "funded",
            "observed_at": observed_at,
        },
    }


__all__ = ["PaidHandoffMappingError", "build_paid_handoff"]
