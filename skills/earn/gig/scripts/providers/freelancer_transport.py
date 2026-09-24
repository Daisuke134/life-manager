#!/usr/bin/env python3
"""Authorization-bound Freelancer transport and official inventory route plan.

This module selects an already-authorized official API or private browser
transport. It never logs in, refreshes credentials, sends a marketplace
effect, or registers an owner. The route plan is deliberately read-only and
is consumed by the provider-owned adapter before its response is passed to
``freelancer_readiness.read_authenticated_inventory``.
"""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from provider_authorization import (
    AuthorizationDecision,
    AuthorizationState,
    authorize,
)


DEFAULT_OAUTH_PATH = Path.home() / ".config" / "anicca" / "gig" / "freelancer-oauth2.json"
DEFAULT_PROFILES_ROOT = Path.home() / ".cloak" / "profiles"
DEFAULT_BROWSER_PROFILE = DEFAULT_PROFILES_ROOT / "gig-freelancer"
DEFAULT_MATRIX_PATH = Path(__file__).resolve().parents[2] / "config" / "freelancer-actions.public.json"
_OAUTH_KEYS = {
    "version", "access_token", "refresh_token", "token_type", "scopes", "expires_at",
}
_MAX_CREDENTIAL_BYTES = 32_768


class TransportConfigurationError(ValueError):
    """A local credential, action matrix, or official route is unsafe."""


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
    """Load the canonical mode-600 OAuth record without exposing its secret."""
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
    if not isinstance(raw, dict) or raw.get("provider") != "freelancer":
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
class FreelancerTransport:
    account: str
    now: datetime
    oauth_path: Path = DEFAULT_OAUTH_PATH
    profiles_root: Path = DEFAULT_PROFILES_ROOT
    browser_profile: Path = DEFAULT_BROWSER_PROFILE
    matrix_path: Path = DEFAULT_MATRIX_PATH

    def for_action(self, action: str) -> TransportSelection | None:
        if action not in _listed_actions(self.matrix_path):
            return None
        api_auth = authorize("freelancer", self.account, action, "official_api", self.now)
        if api_auth.state is AuthorizationState.APPROVED_API:
            token = load_oauth2_token(self.oauth_path, self.now)
            if token is not None:
                return TransportSelection("official_api", self.oauth_path, api_auth)
        browser_auth = authorize("freelancer", self.account, action, "cloak_browser", self.now)
        if browser_auth.state is AuthorizationState.APPROVED_BROWSER:
            profile = _private_profile(self.browser_profile, self.profiles_root)
            if profile is not None:
                return TransportSelection("cloak_browser", profile, browser_auth)
        return None

    def inventory_route_plan(self, *, project_ids: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
        """Return the exact read-only official routes needed for one inventory.

        The response parser remains provider-owned and strict. This method only
        enumerates documented routes; it does not issue HTTP requests.
        """
        if len(set(project_ids)) != len(project_ids):
            raise TransportConfigurationError("duplicate_project_id")
        for project_id in project_ids:
            if not isinstance(project_id, str) or not project_id.isdigit() or not project_id:
                raise TransportConfigurationError("project_id_invalid")
        routes: list[tuple[str, str]] = [
            ("identity", "/users/0.1/users/"),
            ("projects", "/projects/0.1/self/"),
        ]
        routes.extend(
            (f"milestones:{project_id}", f"/projects/0.1/projects/{project_id}/milestones/")
            for project_id in project_ids
        )
        routes.append(("hourly_contracts", "/projects/0.1/hourly_contracts/"))
        routes.extend(
            (f"ip_contract:{project_id}", f"/projects/0.1/projects/{project_id}/ip_contracts/")
            for project_id in project_ids
        )
        return tuple(routes)

    def read_inventory(
        self,
        receipts: Iterable[Any],
        *,
        account_id: str,
        project_ids: tuple[str, ...],
        fetch: Callable[[TransportSelection, tuple[tuple[str, str], ...]], Any],
    ) -> Any:
        """Attach the route plan to the strict readiness readback boundary.

        ``fetch`` is the provider-owned HTTP/CDP implementation. It receives
        only after ``read_authenticated_inventory`` has proved all three
        account-bound read receipts; its return value must be the canonical
        inventory object accepted by ``freelancer_readiness.parse_inventory``.
        """
        if not callable(fetch):
            raise TransportConfigurationError("inventory_fetch_not_callable")
        plan = self.inventory_route_plan(project_ids=project_ids)
        from freelancer_readiness import read_authenticated_inventory

        def readback(_approved: dict[str, Any]) -> Any:
            selection = self.for_action("inspect")
            if selection is None:
                raise TransportConfigurationError("inventory_transport_unavailable")
            return fetch(selection, plan)

        return read_authenticated_inventory(
            receipts,
            account_id=account_id,
            now=self.now,
            readback=readback,
        )

    def effect_intent(self, selection: TransportSelection, *, resource_id: str, payload_hash: str):
        """Keep effect identity account-bound; provider effects remain elsewhere."""
        from application_effect_fence import authorized_provider_intent

        action = self._approved_action(selection.authorization)
        return authorized_provider_intent(
            provider="freelancer", account_key=self.account,
            resource_id=resource_id, action=action, payload_hash=payload_hash,
            authorization=selection.authorization,
        )

    def _approved_action(self, authorization: AuthorizationDecision) -> str:
        transport = "official_api" if authorization.state is AuthorizationState.APPROVED_API else "cloak_browser"
        for action in _listed_actions(self.matrix_path):
            decision = authorize("freelancer", self.account, action, transport, self.now)
            if decision.receipt_hash == authorization.receipt_hash:
                return action
        raise TransportConfigurationError("authorization_scope_unresolved")
