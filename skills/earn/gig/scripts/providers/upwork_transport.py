#!/usr/bin/env python3
"""Authorization-bound transport selection for the Upwork adapter."""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from application_effect_fence import authorized_provider_intent
from provider_authorization import (
    AuthorizationDecision,
    AuthorizationState,
    authorize,
)


DEFAULT_OAUTH_PATH = Path.home() / ".config" / "anicca" / "gig" / "upwork-oauth2.json"
DEFAULT_PROFILES_ROOT = Path.home() / ".cloak" / "profiles"
DEFAULT_BROWSER_PROFILE = DEFAULT_PROFILES_ROOT / "gig-upwork"
DEFAULT_MATRIX_PATH = Path(__file__).resolve().parents[2] / "config" / "upwork-actions.public.json"
_OAUTH_KEYS = {
    "version", "access_token", "refresh_token", "token_type", "scopes", "expires_at",
}
_MAX_CREDENTIAL_BYTES = 32_768
INVENTORY_ROUTES = (
    ("contracts", "https://www.upwork.com/nx/wm/freelancer/home"),
    ("transactions", "https://www.upwork.com/nx/payments/reports/transaction-history"),
    ("withdrawals", "https://www.upwork.com/nx/payments/disbursement-methods"),
)


class TransportConfigurationError(ValueError):
    """A local transport credential or public action matrix is unsafe."""


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TransportConfigurationError("oauth_expires_at_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TransportConfigurationError("oauth_expires_at_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TransportConfigurationError("oauth_expires_at_invalid")
    return parsed


def _secret(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 16_384:
        raise TransportConfigurationError(f"oauth_{label}_invalid")
    return value


@dataclass(frozen=True)
class OAuth2Token:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    scopes: tuple[str, ...]
    expires_at: datetime
    token_type: str = "Bearer"


def load_oauth2_token(path: Path, now: datetime) -> OAuth2Token | None:
    """Load a small mode-600 OAuth record without ever formatting its secrets."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise TransportConfigurationError("now_requires_timezone")
    path = path.expanduser()
    if not path.is_file():
        return None
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise TransportConfigurationError("oauth_requires_mode_600")
    if path.stat().st_size > _MAX_CREDENTIAL_BYTES:
        raise TransportConfigurationError("oauth_too_large")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransportConfigurationError("oauth_invalid_json") from exc
    if not isinstance(raw, dict) or set(raw) != _OAUTH_KEYS:
        raise TransportConfigurationError("oauth_keys_mismatch")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise TransportConfigurationError("oauth_version_unsupported")
    if raw["token_type"] != "Bearer":
        raise TransportConfigurationError("oauth_token_type_invalid")
    scopes = raw["scopes"]
    if (
        not isinstance(scopes, list)
        or not scopes
        or len(scopes) > 64
        or any(not isinstance(scope, str) or not scope or len(scope) > 128 for scope in scopes)
    ):
        raise TransportConfigurationError("oauth_scopes_invalid")
    expires_at = _timestamp(raw["expires_at"])
    if now >= expires_at:
        return None
    return OAuth2Token(
        access_token=_secret(raw["access_token"], "access_token"),  # type: ignore[arg-type]
        refresh_token=_secret(raw["refresh_token"], "refresh_token", optional=True),
        scopes=tuple(scopes),
        expires_at=expires_at,
    )


@dataclass(frozen=True)
class TransportSelection:
    mode: str
    credential_path: Path
    authorization: AuthorizationDecision = field(repr=False)


def _listed_actions(path: Path) -> frozenset[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransportConfigurationError("action_matrix_invalid") from exc
    if not isinstance(raw, dict) or raw.get("provider") != "upwork":
        raise TransportConfigurationError("action_matrix_invalid")
    actions = raw.get("actions")
    if not isinstance(actions, dict) or any(not isinstance(key, str) for key in actions):
        raise TransportConfigurationError("action_matrix_invalid")
    return frozenset(actions)


def _private_profile(path: Path, root: Path) -> Path | None:
    path = path.expanduser()
    root = root.expanduser()
    if path.is_symlink() or root.is_symlink() or not path.is_dir() or not root.is_dir():
        return None
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return None
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        return None
    return resolved


@dataclass(frozen=True)
class UpworkTransport:
    account: str
    now: datetime
    oauth_path: Path = DEFAULT_OAUTH_PATH
    profiles_root: Path = DEFAULT_PROFILES_ROOT
    browser_profile: Path = DEFAULT_BROWSER_PROFILE
    matrix_path: Path = DEFAULT_MATRIX_PATH

    def for_action(self, action: str) -> TransportSelection | None:
        if action not in _listed_actions(self.matrix_path):
            return None
        api_auth = authorize("upwork", self.account, action, "official_api", self.now)
        if api_auth.state is AuthorizationState.APPROVED_API:
            token = load_oauth2_token(self.oauth_path, self.now)
            if token is not None:
                return TransportSelection("official_api", self.oauth_path, api_auth)
        browser_auth = authorize("upwork", self.account, action, "cloak_browser", self.now)
        if browser_auth.state is AuthorizationState.APPROVED_BROWSER:
            profile = _private_profile(self.browser_profile, self.profiles_root)
            if profile is not None:
                return TransportSelection("cloak_browser", profile, browser_auth)
        return None

    def read_inventory(
        self,
        receipts: Iterable[Any],
        *,
        fetch: Callable[[TransportSelection, tuple[tuple[str, str], ...]], Any],
    ) -> Any:
        """Attach official contract/payment pages to the strict readiness gate.

        ``fetch`` is provider-owned and must return the canonical inventory
        accepted by ``upwork_readiness.parse_inventory``. It is not called
        until the three account-bound inventory receipts have been validated.
        """
        if not callable(fetch):
            raise TransportConfigurationError("inventory_fetch_not_callable")
        from upwork_readiness import read_authenticated_inventory

        def readback(_approved: dict[str, Any]) -> Any:
            selection = self.for_action("inspect")
            if selection is None:
                raise TransportConfigurationError("inventory_transport_unavailable")
            payload = fetch(selection, INVENTORY_ROUTES)
            if (
                isinstance(payload, dict)
                and payload.get("version") == 1
                and payload.get("provider") == "upwork"
            ):
                return payload
            if isinstance(payload, dict) and set(payload) == {
                "browser_state", "contract_details",
            }:
                from upwork_readiness import snapshot_from_browser_state

                try:
                    return snapshot_from_browser_state(
                        payload["browser_state"], account_id=self.account,
                        contract_details=payload["contract_details"],
                        required_evidence=("contracts", "transactions", "withdrawals"),
                    )
                except ValueError as exc:
                    raise TransportConfigurationError("inventory_state_bundle_invalid") from exc
            raise TransportConfigurationError("inventory_state_bundle_invalid")

        return read_authenticated_inventory(
            receipts,
            account_id=self.account,
            now=self.now,
            readback=readback,
        )

    def effect_intent(
        self,
        selection: TransportSelection,
        *,
        resource_id: str,
        payload_hash: str,
    ):
        return authorized_provider_intent(
            provider="upwork",
            account_key=self.account,
            resource_id=resource_id,
            action=self._approved_action(selection.authorization),
            payload_hash=payload_hash,
            authorization=selection.authorization,
        )

    def _approved_action(self, authorization: AuthorizationDecision) -> str:
        # A receipt decision intentionally omits its scope. Recover the one action
        # whose exact transport receipt produced this immutable receipt hash.
        for action in _listed_actions(self.matrix_path):
            decision = authorize("upwork", self.account, action, self._transport(authorization), self.now)
            if decision.receipt_hash == authorization.receipt_hash:
                return action
        raise TransportConfigurationError("authorization_scope_unresolved")

    @staticmethod
    def _transport(authorization: AuthorizationDecision) -> str:
        if authorization.state is AuthorizationState.APPROVED_API:
            return "official_api"
        if authorization.state is AuthorizationState.APPROVED_BROWSER:
            return "cloak_browser"
        raise TransportConfigurationError("authorization_not_autonomous")
