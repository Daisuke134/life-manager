#!/usr/bin/env python3
"""Resolve one provider action from exact, private authorization receipts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


DEFAULT_RECEIPT_PATH = Path.home() / ".config" / "anicca" / "gig" / "authorizations.json"
_STORE_KEYS = {"version", "receipts"}
_RECEIPT_KEYS = {
    "provider", "account", "action", "transport", "state", "jurisdiction",
    "terms_version", "evidence_hash", "issued_at", "expires_at",
}
_APPROVED_TRANSPORTS = {
    "approved_api": "official_api",
    "approved_browser": "cloak_browser",
    "approved_assisted": "human_ceremony",
}


class AuthorizationError(ValueError):
    """The private receipt store is malformed or insufficiently protected."""


class AuthorizationState(StrEnum):
    APPROVED_API = "approved_api"
    APPROVED_BROWSER = "approved_browser"
    APPROVED_ASSISTED = "approved_assisted"
    DENIED = "denied"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AuthorizationReceipt:
    provider: str
    account: str
    action: str
    transport: str
    state: AuthorizationState
    jurisdiction: str
    terms_version: str
    evidence_hash: str
    issued_at: datetime
    expires_at: datetime
    receipt_hash: str


@dataclass(frozen=True)
class AuthorizationDecision:
    state: AuthorizationState
    reason: str
    evidence_hash: str | None = None
    receipt_hash: str | None = None
    terms_version: str | None = None


def _reject_constant(value: str) -> None:
    raise AuthorizationError(f"invalid_json_constant:{value}")


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise AuthorizationError(f"{label}_keys_mismatch")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthorizationError(f"invalid_{label}")
    return value.strip()


def _timestamp(value: Any, label: str) -> datetime:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorizationError(f"invalid_{label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthorizationError(f"invalid_{label}")
    return parsed


def _parse_receipt(raw: Any) -> AuthorizationReceipt:
    if not isinstance(raw, dict):
        raise AuthorizationError("receipt_not_object")
    _exact_keys(raw, _RECEIPT_KEYS, "receipt")
    issued_at = _timestamp(raw["issued_at"], "issued_at")
    expires_at = _timestamp(raw["expires_at"], "expires_at")
    if expires_at <= issued_at:
        raise AuthorizationError("invalid_receipt_window")
    evidence_hash = _text(raw["evidence_hash"], "evidence_hash")
    if len(evidence_hash) != 64 or any(c not in "0123456789abcdef" for c in evidence_hash):
        raise AuthorizationError("invalid_evidence_hash")
    try:
        state_value = AuthorizationState(_text(raw["state"], "state"))
    except ValueError as exc:
        raise AuthorizationError("invalid_state") from exc
    transport = _text(raw["transport"], "transport")
    expected_transport = _APPROVED_TRANSPORTS.get(state_value.value)
    if expected_transport is not None and transport != expected_transport:
        raise AuthorizationError("state_transport_mismatch")
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return AuthorizationReceipt(
        provider=_text(raw["provider"], "provider"),
        account=_text(raw["account"], "account"),
        action=_text(raw["action"], "action"),
        transport=transport,
        state=state_value,
        jurisdiction=_text(raw["jurisdiction"], "jurisdiction"),
        terms_version=_text(raw["terms_version"], "terms_version"),
        evidence_hash=evidence_hash,
        issued_at=issued_at,
        expires_at=expires_at,
        receipt_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def load_receipts(path: Path) -> tuple[AuthorizationReceipt, ...]:
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise AuthorizationError("private_receipt_store_requires_mode_600")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizationError("invalid_receipt_store") from exc
    if not isinstance(value, dict):
        raise AuthorizationError("receipt_store_not_object")
    _exact_keys(value, _STORE_KEYS, "store")
    if type(value["version"]) is not int or value["version"] != 1:
        raise AuthorizationError("unsupported_store_version")
    if not isinstance(value["receipts"], list):
        raise AuthorizationError("receipts_not_array")
    return tuple(_parse_receipt(raw) for raw in value["receipts"])


def authorize(
    provider: str,
    account: str,
    action: str,
    transport: str,
    now: datetime,
) -> AuthorizationDecision:
    if now.tzinfo is None or now.utcoffset() is None:
        raise AuthorizationError("now_requires_timezone")
    path = Path(os.environ.get("GIG_AUTHORIZATION_PATH") or DEFAULT_RECEIPT_PATH).expanduser()
    if not path.is_file():
        return AuthorizationDecision(AuthorizationState.UNKNOWN, "receipt_store_missing")
    try:
        receipts = load_receipts(path)
    except AuthorizationError:
        return AuthorizationDecision(AuthorizationState.UNKNOWN, "invalid_receipt_store")
    scoped = [
        receipt for receipt in receipts
        if (receipt.provider, receipt.account, receipt.action, receipt.transport)
        == (provider, account, action, transport)
    ]
    if not scoped:
        return AuthorizationDecision(AuthorizationState.UNKNOWN, "no_matching_receipt")
    active = [receipt for receipt in scoped if receipt.issued_at <= now < receipt.expires_at]
    if not active:
        reason = "matching_receipt_expired" if all(now >= r.expires_at for r in scoped) else "matching_receipt_not_yet_valid"
        return AuthorizationDecision(AuthorizationState.UNKNOWN, reason)
    if len(active) != 1:
        return AuthorizationDecision(AuthorizationState.UNKNOWN, "ambiguous_matching_receipts")
    receipt = active[0]
    return AuthorizationDecision(
        receipt.state,
        "matching_receipt",
        evidence_hash=receipt.evidence_hash,
        receipt_hash=receipt.receipt_hash,
        terms_version=receipt.terms_version,
    )
