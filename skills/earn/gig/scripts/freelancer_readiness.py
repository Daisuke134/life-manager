#!/usr/bin/env python3
"""Fail-closed Freelancer onboarding and funded-contract gate.

This module deliberately does not contact Freelancer or register a launchd
owner. It validates provider receipts and an authenticated, source-complete
contract snapshot, then builds the same authorization-bound effect intent used
by the other Gig adapters. A funded contract is a prerequisite for every
effect-capable owner; a stale/empty public bid watch can never open the gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from application_effect_fence import authorized_provider_intent
from provider_adapter import EffectIntent
from provider_authorization import (
    AuthorizationDecision,
    AuthorizationReceipt,
    AuthorizationState,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_CURRENCIES = frozenset({"AUD", "CAD", "EUR", "GBP", "INR", "NZD", "SGD", "USD"})
_CONTRACT_STATES = frozenset({"pending", "active", "funded", "completed", "closed", "cancelled"})
_OFFICIAL_READBACK_KEYS = frozenset({
    "identity", "projects", "milestones", "hourly_contracts", "ip_contracts",
    "payments", "payouts",
})
_MILESTONE_FUNDED_STATES = frozenset({"pending", "requested_release", "frozen", "disputed"})
_MILESTONE_STATES = _MILESTONE_FUNDED_STATES | {"cleared", "canceled"}
REQUIRED_ACTIONS = frozenset({
    "search", "inspect", "propose", "message", "accept_offer", "deliver",
    "read_payments", "read_payouts",
})
INVENTORY_READ_ACTIONS = frozenset({"inspect", "read_payments", "read_payouts"})


class ReadinessError(ValueError):
    """A readiness snapshot, authorization, or effect request is unsafe."""


def _text(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadinessError(reason)
    return value.strip()


def _hash(value: Any, reason: str) -> str:
    value = _text(value, reason)
    if not _HASH.fullmatch(value):
        raise ReadinessError(reason)
    return value


def _time(value: Any, reason: str) -> str:
    value = _text(value, reason)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReadinessError(reason) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReadinessError(reason)
    return value


def _now(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReadinessError("now_requires_timezone")


def _official_url(value: Any, label: str, identity: str) -> str:
    value = _text(value, label)
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"freelancer.com", "www.freelancer.com"}
        or identity not in parsed.path
    ):
        raise ReadinessError(label)
    return value


@dataclass(frozen=True)
class FreelancerContract:
    project_id: str
    contract_id: str
    state: str
    currency: str
    amount_minor: int
    source_url: str
    source_hash: str
    observed_at: str


@dataclass(frozen=True)
class FreelancerInventory:
    account_id: str
    source_complete: bool
    observed_at: str
    source_hash: str
    contracts: tuple[FreelancerContract, ...]


@dataclass(frozen=True)
class RegistrationReport:
    account_id: str
    ready: bool
    reasons: tuple[str, ...]
    missing_actions: tuple[str, ...]
    funded_contract_ids: tuple[str, ...]


def _contract(raw: Any) -> FreelancerContract:
    required = {
        "project_id", "contract_id", "state", "currency", "amount_minor",
        "source_url", "source_hash", "observed_at",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise ReadinessError("contract_fields_invalid")
    project_id = _text(raw["project_id"], "project_id_invalid")
    contract_id = _text(raw["contract_id"], "contract_id_invalid")
    state = _text(raw["state"], "contract_state_invalid")
    if state not in _CONTRACT_STATES:
        raise ReadinessError("contract_state_invalid")
    currency = _text(raw["currency"], "contract_currency_invalid")
    if currency not in _CURRENCIES:
        raise ReadinessError("contract_currency_invalid")
    amount_minor = raw["amount_minor"]
    if type(amount_minor) is not int or amount_minor < 0 or (state == "funded" and amount_minor == 0):
        raise ReadinessError("contract_amount_invalid")
    return FreelancerContract(
        project_id=project_id,
        contract_id=contract_id,
        state=state,
        currency=currency,
        amount_minor=amount_minor,
        source_url=_official_url(raw["source_url"], "contract_url_invalid", project_id),
        source_hash=_hash(raw["source_hash"], "contract_source_hash_invalid"),
        observed_at=_time(raw["observed_at"], "contract_observed_at_invalid"),
    )


def parse_inventory(raw: Any) -> FreelancerInventory:
    """Parse one authenticated source-complete Freelancer inventory snapshot."""
    required = {
        "version", "provider", "account_id", "source_complete", "observed_at",
        "source_hash", "contracts",
    }
    if not isinstance(raw, dict) or set(raw) != required or raw["version"] != 1:
        raise ReadinessError("inventory_fields_invalid")
    if raw["provider"] != "freelancer":
        raise ReadinessError("inventory_provider_invalid")
    account_id = _text(raw["account_id"], "account_id_invalid")
    if type(raw["source_complete"]) is not bool:
        raise ReadinessError("inventory_source_complete_invalid")
    observed_at = _time(raw["observed_at"], "inventory_observed_at_invalid")
    source_hash = _hash(raw["source_hash"], "inventory_source_hash_invalid")
    contracts_raw = raw["contracts"]
    if not isinstance(contracts_raw, list):
        raise ReadinessError("contracts_invalid")
    contracts = tuple(_contract(item) for item in contracts_raw)
    ids = [item.contract_id for item in contracts]
    if len(set(ids)) != len(ids):
        raise ReadinessError("duplicate_contract_id")
    return FreelancerInventory(
        account_id=account_id,
        source_complete=raw["source_complete"],
        observed_at=observed_at,
        source_hash=source_hash,
        contracts=contracts,
    )


def _official_result(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("status") != "success":
        raise ReadinessError(f"official_{label}_envelope_invalid")
    result = raw.get("result")
    if not isinstance(result, dict):
        raise ReadinessError(f"official_{label}_result_invalid")
    return result


def _money_minor(value: Any, currency: str, currency_minor_units: dict[str, int]) -> int:
    scale = currency_minor_units.get(currency)
    if type(scale) is not int or scale < 0 or scale > 4:
        raise ReadinessError("currency_minor_units_missing")
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ReadinessError("milestone_amount_invalid")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ReadinessError("milestone_amount_invalid") from exc
    if not amount.is_finite() or amount < 0:
        raise ReadinessError("milestone_amount_invalid")
    minor = amount * (Decimal(10) ** scale)
    if minor != minor.to_integral_value():
        raise ReadinessError("milestone_amount_precision_invalid")
    return int(minor)


def snapshot_from_official_readbacks(
    readbacks: Any,
    *,
    account_id: str,
    observed_at: str,
    source_hash: str,
    currency_minor_units: dict[str, int],
) -> dict[str, Any]:
    """Normalize documented Freelancer API readbacks into one strict snapshot.

    The input is deliberately a complete bundle rather than a single endpoint
    response.  Every route is checked for the documented ``status=success`` /
    ``result`` envelope, the identity is bound to the account, and every
    awarded project has its milestone and IP readback.  Hourly/IP/payment data
    are validated for presence and shape even when they do not prove a funded
    fixed-price milestone.  Amount conversion is explicit: the caller must
    provide the currency minor-unit policy instead of silently assuming cents.
    """
    if not isinstance(readbacks, dict) or set(readbacks) != _OFFICIAL_READBACK_KEYS:
        raise ReadinessError("official_readbacks_fields_invalid")
    account_id = _text(account_id, "account_id_invalid")
    if not account_id.isdigit():
        raise ReadinessError("account_id_invalid")
    account_number = int(account_id)
    observed_at = _time(observed_at, "inventory_observed_at_invalid")
    source_hash = _hash(source_hash, "inventory_source_hash_invalid")
    if not isinstance(currency_minor_units, dict):
        raise ReadinessError("currency_minor_units_invalid")

    identity = _official_result(readbacks["identity"], "identity")
    users = identity.get("users")
    if not isinstance(users, dict):
        raise ReadinessError("official_identity_users_invalid")
    user = users.get(account_id)
    if not isinstance(user, dict) or type(user.get("id")) is not int:
        raise ReadinessError("official_identity_account_missing")
    if str(user["id"]) != account_id:
        raise ReadinessError("official_identity_account_mismatch")

    projects_result = _official_result(readbacks["projects"], "projects")
    projects_group = projects_result.get("projects")
    if not isinstance(projects_group, dict) or not isinstance(projects_group.get("projects"), list):
        raise ReadinessError("official_projects_invalid")
    project_ids: list[str] = []
    for project in projects_group["projects"]:
        if not isinstance(project, dict) or type(project.get("id")) is not int or project["id"] <= 0:
            raise ReadinessError("official_project_invalid")
        project_id = str(project["id"])
        if project_id in project_ids:
            raise ReadinessError("duplicate_project_id")
        project_ids.append(project_id)
    project_id_set = set(project_ids)

    milestones = readbacks["milestones"]
    ip_contracts = readbacks["ip_contracts"]
    if (
        not isinstance(milestones, dict) or set(milestones) != project_id_set
        or not isinstance(ip_contracts, dict) or set(ip_contracts) != project_id_set
    ):
        raise ReadinessError("official_project_readbacks_incomplete")

    _official_result(readbacks["hourly_contracts"], "hourly_contracts")
    _official_result(readbacks["payments"], "payments")
    _official_result(readbacks["payouts"], "payouts")

    hourly = _official_result(readbacks["hourly_contracts"], "hourly_contracts")
    hourly_rows = hourly.get("hourly_contracts")
    if not isinstance(hourly_rows, list):
        raise ReadinessError("official_hourly_contracts_invalid")
    hourly_ids: set[int] = set()
    for contract in hourly_rows:
        if (
            not isinstance(contract, dict)
            or type(contract.get("id")) is not int
            or type(contract.get("project_id")) is not int
            or contract["project_id"] <= 0
        ):
            raise ReadinessError("official_hourly_contract_invalid")
        if str(contract["project_id"]) not in project_id_set:
            raise ReadinessError("hourly_contract_project_unknown")
        if contract["id"] in hourly_ids:
            raise ReadinessError("duplicate_hourly_contract_id")
        hourly_ids.add(contract["id"])

    contracts: list[dict[str, Any]] = []
    for project_id in project_ids:
        ip_result = _official_result(ip_contracts[project_id], f"ip_contract:{project_id}")
        ip_rows = ip_result.get("contracts")
        if not isinstance(ip_rows, list):
            raise ReadinessError("official_ip_contracts_invalid")
        for ip_contract in ip_rows:
            if (
                not isinstance(ip_contract, dict)
                or type(ip_contract.get("project_id")) is not int
                or ip_contract["project_id"] != int(project_id)
                or type(ip_contract.get("user_id")) is not int
                or type(ip_contract.get("signed")) is not bool
            ):
                raise ReadinessError("official_ip_contract_invalid")
        milestone_result = _official_result(milestones[project_id], f"milestones:{project_id}")
        rows = milestone_result.get("milestones")
        if not isinstance(rows, dict):
            raise ReadinessError("official_milestones_invalid")
        for milestone_key, milestone in rows.items():
            if not isinstance(milestone_key, str) or not isinstance(milestone, dict):
                raise ReadinessError("official_milestone_invalid")
            transaction_id = milestone.get("transaction_id")
            if type(transaction_id) is not int or transaction_id <= 0:
                raise ReadinessError("official_milestone_invalid")
            if milestone.get("project_id") != int(project_id):
                raise ReadinessError("milestone_project_mismatch")
            if milestone.get("bidder_id") != account_number:
                raise ReadinessError("milestone_account_mismatch")
            status = milestone.get("status")
            if status not in _MILESTONE_STATES:
                raise ReadinessError("milestone_status_invalid")
            currency = milestone.get("currency")
            if not isinstance(currency, dict) or not isinstance(currency.get("code"), str):
                raise ReadinessError("milestone_currency_invalid")
            code = currency["code"]
            amount_minor = _money_minor(milestone.get("amount"), code, currency_minor_units)
            state = (
                "funded" if status in _MILESTONE_FUNDED_STATES
                else "completed" if status == "cleared" else "cancelled"
            )
            contracts.append({
                "project_id": project_id,
                "contract_id": f"project-{project_id}-milestone-{transaction_id}",
                "state": state,
                "currency": code,
                "amount_minor": amount_minor,
                "source_url": f"https://www.freelancer.com/projects/{project_id}",
                "source_hash": source_hash,
                "observed_at": observed_at,
            })

    snapshot = {
        "version": 1,
        "provider": "freelancer",
        "account_id": account_id,
        "source_complete": True,
        "observed_at": observed_at,
        "source_hash": source_hash,
        "contracts": contracts,
    }
    parse_inventory(snapshot)
    return snapshot


def read_authenticated_inventory(
    receipts: Iterable[AuthorizationReceipt],
    *,
    account_id: str,
    now: datetime,
    readback: Callable[[dict[str, AuthorizationReceipt]], Any],
) -> FreelancerInventory:
    """Read one canonical inventory only through an approved account-bound receipt.

    ``readback`` is the provider-owned browser/API adapter.  Keeping it injected
    makes this boundary testable without inventing a Freelancer endpoint and, more
    importantly, prevents a missing or denied receipt from opening the transport.
    The returned value is still parsed by the same strict inventory contract used by
    the owner gate.
    """
    account_id = _text(account_id, "account_id_invalid")
    if not callable(readback):
        raise ReadinessError("inventory_readback_not_callable")
    approved = _active_approved(receipts, account_id, now)
    missing = sorted(INVENTORY_READ_ACTIONS - set(approved))
    if missing:
        raise ReadinessError("inventory_authorization_missing:" + ",".join(missing))
    inventory = parse_inventory(readback(dict(approved)))
    if inventory.account_id != account_id:
        raise ReadinessError("inventory_account_mismatch")
    return inventory


def _active_approved(
    receipts: Iterable[AuthorizationReceipt], account_id: str, now: datetime,
) -> dict[str, AuthorizationReceipt]:
    _now(now)
    result: dict[str, AuthorizationReceipt] = {}
    for receipt in receipts:
        if (
            receipt.provider != "freelancer" or receipt.account != account_id
            or receipt.state not in {
                AuthorizationState.APPROVED_API, AuthorizationState.APPROVED_BROWSER,
            }
            or not receipt.issued_at <= now < receipt.expires_at
        ):
            continue
        if receipt.action in result:
            raise ReadinessError("ambiguous_authorization")
        result[receipt.action] = receipt
    return result


def evaluate_registration(
    receipts: Iterable[AuthorizationReceipt], inventory: FreelancerInventory,
    *, now: datetime,
) -> RegistrationReport:
    """Return whether one complete Freelancer lifecycle owner may be registered."""
    approved = _active_approved(receipts, inventory.account_id, now)
    missing = tuple(sorted(REQUIRED_ACTIONS - set(approved)))
    reasons: list[str] = []
    if missing:
        reasons.append("authorization_missing")
    if not inventory.source_complete:
        reasons.append("inventory_incomplete")
    funded_ids = tuple(
        contract.contract_id for contract in inventory.contracts if contract.state == "funded"
    )
    if not funded_ids:
        reasons.append("funded_contract_missing")
    return RegistrationReport(
        account_id=inventory.account_id,
        ready=not reasons,
        reasons=tuple(reasons),
        missing_actions=missing,
        funded_contract_ids=funded_ids,
    )


def _decision(receipt: AuthorizationReceipt) -> AuthorizationDecision:
    state = receipt.state
    if state not in {AuthorizationState.APPROVED_API, AuthorizationState.APPROVED_BROWSER}:
        raise ReadinessError("authorization_not_approved")
    return AuthorizationDecision(
        state=state,
        reason="matching_receipt",
        evidence_hash=receipt.evidence_hash,
        receipt_hash=receipt.receipt_hash,
    )


def plan_effect(
    report: RegistrationReport,
    receipts: Iterable[AuthorizationReceipt],
    *, contract_id: str, action: str, payload_hash: str, now: datetime,
) -> EffectIntent:
    """Build one fenced intent; no provider transport is invoked here."""
    if not report.ready:
        raise ReadinessError("registration_gate_not_ready")
    if contract_id not in report.funded_contract_ids:
        raise ReadinessError("contract_not_funded")
    if action not in REQUIRED_ACTIONS:
        raise ReadinessError("action_not_registered")
    approved = _active_approved(receipts, report.account_id, now)
    receipt = approved.get(action)
    if receipt is None:
        raise ReadinessError("authorization_not_approved")
    return authorized_provider_intent(
        provider="freelancer", account_key=report.account_id,
        resource_id=contract_id, action=action, payload_hash=payload_hash,
        authorization=_decision(receipt),
    )


def replay_zero(intents: Iterable[EffectIntent]) -> bool:
    """Return true only when one logical effect key appears at most once."""
    keys = [intent.effect_key for intent in intents]
    return len(keys) == len(set(keys))
