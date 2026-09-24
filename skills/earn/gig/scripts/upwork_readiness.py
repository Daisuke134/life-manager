#!/usr/bin/env python3
"""Fail-closed Upwork Paid-owner registration gate.

The existing Upwork proposal/message/offer/delivery/finance modules own the
provider-specific work. This small boundary only decides whether one lifecycle
owner may be registered: every action must have a current approved receipt and
the authenticated inventory must contain a source-complete funded milestone.
It never opens CDP, sends a proposal/message, accepts an offer, or delivers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
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
REQUIRED_ACTIONS = frozenset({
    "search", "inspect", "propose", "message", "accept_offer",
    "deliver_milestone", "read_payments", "read_payouts",
})
INVENTORY_READ_ACTIONS = frozenset({"inspect", "read_payments", "read_payouts"})
_CONTRACT_STATES = frozenset({"pending", "funded", "active", "completed", "closed"})


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


def _official_url(value: Any, identity: str) -> str:
    value = _text(value, "contract_url_invalid")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or parsed.netloc != "www.upwork.com"
        or identity not in parsed.path
    ):
        raise ReadinessError("contract_url_invalid")
    return value


@dataclass(frozen=True)
class UpworkContract:
    contract_id: str
    state: str
    funded_milestone_minor: int
    source_url: str
    source_hash: str
    observed_at: str


@dataclass(frozen=True)
class UpworkInventory:
    account_id: str
    source_complete: bool
    observed_at: str
    source_hash: str
    contracts: tuple[UpworkContract, ...]


@dataclass(frozen=True)
class RegistrationReport:
    account_id: str
    ready: bool
    reasons: tuple[str, ...]
    missing_actions: tuple[str, ...]
    funded_contract_ids: tuple[str, ...]


def snapshot_from_browser_state(
    state: Any, *, account_id: str,
    contract_details: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert one official Upwork browser state into the canonical inventory."""
    account_id = _text(account_id, "account_id_invalid")
    if not isinstance(state, dict) or state.get("version") != 1:
        raise ReadinessError("browser_state_invalid")
    if state.get("provider") != "upwork":
        raise ReadinessError("browser_state_provider_invalid")
    observed_at = _time(state.get("observed_at"), "browser_state_observed_at_invalid")
    evidence = state.get("evidence_sha256")
    if not isinstance(evidence, dict):
        raise ReadinessError("browser_state_evidence_invalid")
    source_hash = _hash(evidence.get("contracts"), "inventory_source_hash_invalid")
    rows = state.get("active_contracts")
    if not isinstance(rows, list):
        raise ReadinessError("browser_state_contracts_invalid")
    details = contract_details if contract_details is not None else {}
    if not isinstance(details, dict):
        raise ReadinessError("contract_details_invalid")

    contracts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ReadinessError("browser_state_contract_invalid")
        contract_id = _text(row.get("id"), "contract_id_invalid")
        if contract_id in seen:
            raise ReadinessError("duplicate_contract_id")
        seen.add(contract_id)
        href = _official_url(row.get("href"), contract_id)
        detail = details.get(contract_id)
        if detail is None:
            raise ReadinessError("contract_detail_required")
        if not isinstance(detail, dict) or detail.get("contract_id", contract_id) != contract_id:
            raise ReadinessError("contract_detail_invalid")
        detail_url = detail.get("source_url", href)
        contracts.append({
            "contract_id": contract_id,
            "state": detail.get("state"),
            "funded_milestone_minor": detail.get("funded_milestone_minor"),
            "source_url": detail_url,
            "source_hash": detail.get("source_hash"),
            "observed_at": detail.get("observed_at"),
        })
    if set(details) - seen:
        raise ReadinessError("orphan_contract_detail")
    snapshot = {
        "version": 1,
        "provider": "upwork",
        "account_id": account_id,
        "source_complete": True,
        "observed_at": observed_at,
        "source_hash": source_hash,
        "contracts": contracts,
    }
    parse_inventory(snapshot)
    return snapshot


def _contract(raw: Any) -> UpworkContract:
    required = {
        "contract_id", "state", "funded_milestone_minor", "source_url",
        "source_hash", "observed_at",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise ReadinessError("contract_fields_invalid")
    contract_id = _text(raw["contract_id"], "contract_id_invalid")
    state = _text(raw["state"], "contract_state_invalid")
    if state not in _CONTRACT_STATES:
        raise ReadinessError("contract_state_invalid")
    funded = raw["funded_milestone_minor"]
    if type(funded) is not int or funded < 0 or (state == "funded" and funded == 0):
        raise ReadinessError("funded_milestone_invalid")
    return UpworkContract(
        contract_id=contract_id,
        state=state,
        funded_milestone_minor=funded,
        source_url=_official_url(raw["source_url"], contract_id),
        source_hash=_hash(raw["source_hash"], "contract_source_hash_invalid"),
        observed_at=_time(raw["observed_at"], "contract_observed_at_invalid"),
    )


def parse_inventory(raw: Any) -> UpworkInventory:
    """Parse an authenticated, source-complete Upwork contract snapshot."""
    required = {
        "version", "provider", "account_id", "source_complete", "observed_at",
        "source_hash", "contracts",
    }
    if not isinstance(raw, dict) or set(raw) != required or raw["version"] != 1:
        raise ReadinessError("inventory_fields_invalid")
    if raw["provider"] != "upwork":
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
    return UpworkInventory(
        account_id=account_id,
        source_complete=raw["source_complete"],
        observed_at=observed_at,
        source_hash=source_hash,
        contracts=contracts,
    )


def read_authenticated_inventory(
    receipts: Iterable[AuthorizationReceipt],
    *,
    account_id: str,
    now: datetime,
    readback: Callable[[dict[str, AuthorizationReceipt]], Any],
) -> UpworkInventory:
    """Read one canonical contract inventory through approved Upwork evidence only.

    The provider-specific browser/API transport is injected at this seam.  No
    transport is called until the exact account has fresh approved receipts for
    contract inspection and payment/payout readback; the strict inventory parser
    then remains the single admission contract for the Paid owner.
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
            receipt.provider != "upwork" or receipt.account != account_id
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
    receipts: Iterable[AuthorizationReceipt], inventory: UpworkInventory,
    *, now: datetime,
) -> RegistrationReport:
    """Return whether one Upwork Paid owner may be registered."""
    approved = _active_approved(receipts, inventory.account_id, now)
    missing = tuple(sorted(REQUIRED_ACTIONS - set(approved)))
    reasons: list[str] = []
    if missing:
        reasons.append("authorization_missing")
    if not inventory.source_complete:
        reasons.append("inventory_incomplete")
    funded_ids = tuple(
        contract.contract_id
        for contract in inventory.contracts
        if contract.state == "funded" and contract.funded_milestone_minor > 0
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
    return AuthorizationDecision(
        state=receipt.state,
        reason="matching_receipt",
        evidence_hash=receipt.evidence_hash,
        receipt_hash=receipt.receipt_hash,
    )


def plan_effect(
    report: RegistrationReport,
    receipts: Iterable[AuthorizationReceipt],
    *, contract_id: str, action: str, payload_hash: str, now: datetime,
) -> EffectIntent:
    """Build one exact contract-bound intent; no Upwork transport is invoked."""
    if not report.ready:
        raise ReadinessError("registration_gate_not_ready")
    if contract_id not in report.funded_contract_ids:
        raise ReadinessError("contract_not_funded")
    if action not in REQUIRED_ACTIONS:
        raise ReadinessError("action_not_registered")
    receipt = _active_approved(receipts, report.account_id, now).get(action)
    if receipt is None:
        raise ReadinessError("authorization_not_approved")
    return authorized_provider_intent(
        provider="upwork", account_key=report.account_id,
        resource_id=contract_id, action=action, payload_hash=payload_hash,
        authorization=_decision(receipt),
    )


def replay_zero(intents: Iterable[EffectIntent]) -> bool:
    """Return true only when no logical effect key is duplicated."""
    keys = [intent.effect_key for intent in intents]
    return len(keys) == len(set(keys))
