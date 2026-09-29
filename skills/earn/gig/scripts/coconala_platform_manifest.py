#!/usr/bin/env python3
"""Build a platform-level Coconala Meta Loop manifest from read-only state.

The input is the secret-free onboarding observation, not the Coconala request
snapshot.  Missing policy, funded-work, canary, or economics evidence remains
``unknown`` so the shared enrollment gate records a hold instead of inventing
promotion evidence.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping
from urllib.parse import urlsplit


try:
    from platform_manifest_source import manifest_to_discovery_item
except ModuleNotFoundError:  # pragma: no cover - direct module loading fallback
    _platform_spec = importlib.util.spec_from_file_location(
        "coconala_platform_manifest_source",
        Path(__file__).resolve().parents[3]
        / "_shared" / "marketplace-core" / "scripts" / "platform_manifest_source.py",
    )
    if _platform_spec is None or _platform_spec.loader is None:
        raise
    _platform_module = importlib.util.module_from_spec(_platform_spec)
    sys.modules[_platform_spec.name] = _platform_module
    _platform_spec.loader.exec_module(_platform_module)
    manifest_to_discovery_item = _platform_module.manifest_to_discovery_item


_HASH = re.compile(r"^[0-9a-f]{64}$")
_STATES = (
    "preflight", "authenticated", "email_verified", "sms_verified",
    "seller_information", "identity_approved", "bank_registered",
    "launchd_readback", "storefront_listing_readback",
)
_SNAPSHOT_FIELDS = frozenset({
    "version", "platform", "observed_at", "source_url", "adapter_source_sha256",
    "evidence_refs", "onboarding",
})
_STATE_FIELDS = frozenset({"status", "evidence_sha256"})
_OPPORTUNITY_KEYS = frozenset({
    "opportunities", "request_details", "listings", "jobs", "requests",
})
_REQUIRED_ACTIONS = [
    "discover", "inspect", "propose", "message", "accept_offer", "deliver",
    "read_payments", "read_payouts",
]


class CoconalaPlatformManifestError(ValueError):
    """The Coconala platform observation is malformed or the wrong source kind."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise CoconalaPlatformManifestError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise CoconalaPlatformManifestError(reason)
    return text


def _timestamp(value: Any) -> str:
    text = _text(value, "observed_at_invalid", max_length=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise CoconalaPlatformManifestError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CoconalaPlatformManifestError("observed_at_invalid")
    return text


def _hash(value: Any, reason: str) -> str:
    text = _text(value, reason, max_length=64)
    if _HASH.fullmatch(text) is None:
        raise CoconalaPlatformManifestError(reason)
    return text


def _refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise CoconalaPlatformManifestError("evidence_refs_invalid")
    return [_text(item, "evidence_refs_invalid", max_length=1024) for item in value]


def _onboarding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CoconalaPlatformManifestError("onboarding_invalid")
    if set(value) != {"version", "platform", "states"}:
        raise CoconalaPlatformManifestError("onboarding_invalid")
    if value.get("version") != 2 or value.get("platform") != "coconala":
        raise CoconalaPlatformManifestError("onboarding_invalid")
    states = value.get("states")
    if not isinstance(states, Mapping) or set(states) != set(_STATES):
        raise CoconalaPlatformManifestError("onboarding_states_invalid")
    normalized_states: dict[str, dict[str, str | None]] = {}
    for state in _STATES:
        row = states[state]
        if not isinstance(row, Mapping) or set(row) != _STATE_FIELDS:
            raise CoconalaPlatformManifestError("onboarding_state_invalid")
        status = row.get("status")
        evidence = row.get("evidence_sha256")
        if status not in {"pending", "complete"}:
            raise CoconalaPlatformManifestError("onboarding_state_invalid")
        if status == "pending" and evidence is not None:
            raise CoconalaPlatformManifestError("onboarding_pending_evidence_invalid")
        if status == "complete":
            evidence = _hash(evidence, "onboarding_evidence_invalid")
        normalized_states[state] = {"status": status, "evidence_sha256": evidence}
    return {"version": 2, "platform": "coconala", "states": normalized_states}


def _source_url(value: Any) -> str:
    text = _text(value, "source_url_invalid", max_length=2048)
    parsed = urlsplit(text)
    if parsed.scheme != "https" or parsed.hostname != "coconala.com" or parsed.query or parsed.fragment:
        raise CoconalaPlatformManifestError("source_url_invalid")
    return f"https://coconala.com{parsed.path.rstrip('/') or '/'}"


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manifest_from_observation(raw: Any) -> dict[str, Any]:
    """Normalize one onboarding observation into a generic platform manifest."""

    if not isinstance(raw, Mapping):
        raise CoconalaPlatformManifestError("snapshot_invalid")
    if _OPPORTUNITY_KEYS.intersection(raw):
        raise CoconalaPlatformManifestError("opportunity_snapshot_rejected")
    if set(raw) != _SNAPSHOT_FIELDS or raw.get("version") != 2 or raw.get("platform") != "coconala":
        raise CoconalaPlatformManifestError("snapshot_invalid")
    observed_at = _timestamp(raw.get("observed_at"))
    source_url = _source_url(raw.get("source_url"))
    adapter_source_sha256 = _hash(raw.get("adapter_source_sha256"), "adapter_source_sha256_invalid")
    refs = _refs(raw.get("evidence_refs"))
    onboarding = _onboarding(raw.get("onboarding"))
    onboarding_refs = [
        f"coconala://onboarding/{state}/{row['evidence_sha256']}"
        for state, row in onboarding["states"].items()
        if row["status"] == "complete"
    ]
    evidence_refs = refs + onboarding_refs
    if not evidence_refs:
        evidence_refs = ["coconala://onboarding/observation"]
    candidate = {
        "version": 1,
        "provider": "coconala",
        "policy": {
            "status": "unknown",
            "source_url": "https://coconala.com/terms",
            "observed_at": observed_at,
        },
        "adapter": {
            "contract": "marketplace-core-v1",
            "actions": list(_REQUIRED_ACTIONS),
            "source_sha256": adapter_source_sha256,
        },
        "funded_work": {
            "status": "unknown",
            "receipt_ref": "provider-receipt://coconala/unverified",
            "observed_at": observed_at,
        },
        "canary": {
            "status": "unknown",
            "official_receipt_ref": None,
            "replay_zero": False,
            "observed_at": observed_at,
        },
        "unit_economics": {
            "status": "unknown",
            "net_amount_minor": 0,
            "currency": "JPY",
            "evidence_refs": evidence_refs,
        },
    }
    return {
        "schema_version": 1,
        "source_kind": "platform",
        "provider": "coconala",
        "candidate_id": "platform:coconala",
        "candidate": candidate,
        "observed_at": observed_at,
        "source_url": source_url,
        "snapshot_sha256": _canonical_hash(raw),
        "evidence_refs": evidence_refs,
    }


class CoconalaPlatformManifestSource:
    """Inject one Coconala onboarding observation per wake, read-only."""

    def __init__(self, snapshot_loader: Any):
        if not callable(snapshot_loader):
            raise CoconalaPlatformManifestError("snapshot_loader_invalid")
        self._snapshot_loader = snapshot_loader
        self._item: dict[str, Any] | None = None

    def _loaded(self) -> dict[str, Any]:
        if self._item is not None:
            return self._item
        try:
            manifest = manifest_from_observation(self._snapshot_loader())
            self._item = manifest_to_discovery_item(manifest)
        except CoconalaPlatformManifestError:
            raise
        except Exception as error:  # noqa: BLE001 - typed at the read-only boundary
            raise CoconalaPlatformManifestError("snapshot_collect_failed") from error
        return self._item

    def discover(self) -> list[dict[str, Any]]:
        return [deepcopy(self._loaded())]


__all__ = [
    "CoconalaPlatformManifestError",
    "CoconalaPlatformManifestSource",
    "manifest_from_observation",
]
