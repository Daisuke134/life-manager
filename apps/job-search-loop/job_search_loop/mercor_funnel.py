"""Project Mercor's selection and payment stages from receipt observations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


_STAGES = ("application", "reply", "offer", "trial", "contract", "work", "payment")
_SETTLED = frozenset({"paid", "settled", "paid_settled", "completed"})
_RECEIVED = frozenset({"received", "bank_matched", "payout_received"})


def _text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _time(row: Mapping[str, Any]) -> str:
    return _text(row, "observed_at", "occurred_at", "updated_at")


def _identifier(row: Mapping[str, Any], *keys: str) -> str:
    return _text(row, *keys)


def _stage(row: Mapping[str, Any], *, default_status: str = "unknown") -> dict[str, Any]:
    status = _text(row, "status", "state") or default_status
    result: dict[str, Any] = {"status": status}
    observed_at = _time(row)
    evidence_ref = _text(row, "evidence_ref", "evidence_url", "source_url")
    if observed_at:
        result["observed_at"] = observed_at
    if evidence_ref:
        result["evidence_ref"] = evidence_ref
    for field in (
        "application_id", "application_external_id", "listing_id", "work_id",
        "contract_id", "contract_external_id", "payment_id", "payment_external_id",
        "profile_version", "strategy_version",
    ):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            result[field] = value.strip()
    return result


def _aliases(row: Mapping[str, Any], *keys: str) -> list[str]:
    values = []
    for key in keys:
        value = _identifier(row, key)
        if value and value not in values:
            values.append(value)
    return values


def _amount(row: Mapping[str, Any]) -> Decimal:
    value = row.get("amount_usd")
    if value is None:
        minor = row.get("net_amount_minor", row.get("amount_minor"))
        if minor is None:
            return Decimal("0")
        try:
            return Decimal(str(minor)) / Decimal("100")
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return amount if amount.is_finite() and amount >= 0 else Decimal("0")


def _merge_project(
    projects: dict[str, dict[str, Any]], aliases: dict[str, str], values: Sequence[str]
) -> dict[str, Any]:
    identifiers = [value for value in values if value]
    existing = [aliases[value] for value in identifiers if value in aliases]
    key = existing[0] if existing else (identifiers[0] if identifiers else f"unknown-{len(projects)+1}")
    for old in dict.fromkeys(existing):
        if old == key:
            continue
        projects[key].update({stage: value for stage, value in projects[old].items()
                              if value.get("status") != "unknown"})
        projects.pop(old, None)
        for alias, mapped in list(aliases.items()):
            if mapped == old:
                aliases[alias] = key
    projects.setdefault(key, {stage: {"status": "unknown"} for stage in _STAGES})
    for identifier in identifiers:
        aliases[identifier] = key
    return projects[key]


def _latest(rows: Sequence[Mapping[str, Any]], *keys: str) -> list[Mapping[str, Any]]:
    selected: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        identity = _identifier(row, *keys)
        if not identity:
            continue
        previous = selected.get(identity)
        if previous is None or (_time(row), str(row)) >= (_time(previous), str(previous)):
            selected[identity] = row
    return list(selected.values())


def project_funnel(
    *,
    application_receipts: Sequence[Mapping[str, Any]],
    reply_receipts: Sequence[Mapping[str, Any]],
    work_receipts: Sequence[Mapping[str, Any]],
    payment_receipts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a deduplicated, receipt-backed funnel projection.

    Missing stages remain ``{"status": "unknown"}``; only explicit received
    payment states contribute to ``received_usd``.
    """
    projects: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    application_rows = _latest(
        application_receipts, "application_id", "application_external_id", "listing_id",
    )
    reply_rows = _latest(
        reply_receipts, "reply_id", "thread_id", "application_id", "listing_id", "contract_id",
    )
    work_rows = _latest(work_receipts, "work_id", "contract_id", "application_id")
    payment_rows = _latest(payment_receipts, "payment_id", "payment_external_id", "work_id", "contract_id")

    for row in application_rows:
        project = _merge_project(
            projects, aliases,
            _aliases(row, "application_id", "application_external_id", "listing_id"),
        )
        project["application"] = _stage(row, default_status="submitted")

    for row in reply_rows:
        project = _merge_project(
            projects, aliases,
            _aliases(row, "application_id", "application_external_id", "listing_id", "thread_id", "reply_id", "contract_id"),
        )
        reply = _stage(row)
        project["reply"] = reply
        status = str(reply["status"]).casefold()
        if status == "offer":
            project["offer"] = dict(reply)
        elif status in {"trial_invited", "paid_trial_invited", "work_trial"}:
            project["trial"] = dict(reply)
        if status in {"contracted", "contract", "accepted"} or _identifier(row, "contract_id", "contract_external_id"):
            project["contract"] = _stage(row, default_status="contracted")

    for row in work_rows:
        project = _merge_project(
            projects, aliases,
            _aliases(row, "work_id", "contract_id", "application_id", "listing_id"),
        )
        project["work"] = _stage(row)
        contract_id = _identifier(row, "contract_id", "contract_external_id")
        if contract_id:
            project["contract"] = _stage(row, default_status="contracted")

    settled_total = Decimal("0")
    received_total = Decimal("0")
    for row in payment_rows:
        project = _merge_project(
            projects, aliases,
            _aliases(row, "work_id", "contract_id", "application_id", "listing_id", "payment_id", "payment_external_id"),
        )
        payment = _stage(row)
        project["payment"] = payment
        status = str(payment["status"]).casefold()
        amount = _amount(row)
        if status in _SETTLED:
            settled_total += amount
        if status in _RECEIVED or row.get("received") is True:
            received_total += amount

    stage_counts = {stage: 0 for stage in _STAGES}
    for project in projects.values():
        for stage in _STAGES:
            if project[stage].get("status") != "unknown":
                stage_counts[stage] += 1
    return {
        "version": 1,
        "unique_applications": len(application_rows),
        "stage_counts": stage_counts,
        "settled_usd": float(settled_total),
        "received_usd": float(received_total),
        "projects": projects,
    }


__all__ = ["project_funnel"]
