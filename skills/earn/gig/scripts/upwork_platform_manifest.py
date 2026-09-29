#!/usr/bin/env python3
"""Build a read-only Upwork platform manifest for the shared Meta Loop.

The Upwork browser owner observes contracts, payments, and account pages before
it plans any provider mutation.  This adapter projects only account identity
hashes and source-artifact hashes into the platform candidate.  Contract rows,
job briefs, message bodies, and proposal decisions stay in the provider lane.
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
        "upwork_platform_manifest_source",
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
_SNAPSHOT_FIELDS = frozenset({
    "version", "platform", "observed_at", "source_url", "adapter_source_sha256",
    "authenticated", "source_complete", "profile_readback", "account_id_sha256",
    "evidence_refs", "inventory_evidence_sha256",
})
_INVENTORY_FIELDS = frozenset({"contracts", "transactions", "withdrawals"})
_OPPORTUNITY_KEYS = frozenset({
    "applications", "contracts", "jobs", "listings", "messages", "proposals",
    "requests", "request_details",
})
_REQUIRED_ACTIONS = [
    "discover", "inspect", "propose", "message", "accept_offer", "deliver",
    "read_payments", "read_payouts",
]


class UpworkPlatformManifestError(ValueError):
    """The Upwork account observation is malformed or not platform-only."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise UpworkPlatformManifestError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise UpworkPlatformManifestError(reason)
    return text


def _timestamp(value: Any) -> str:
    text = _text(value, "observed_at_invalid", max_length=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise UpworkPlatformManifestError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise UpworkPlatformManifestError("observed_at_invalid")
    return text


def _hash(value: Any, reason: str) -> str:
    text = _text(value, reason, max_length=64)
    if _HASH.fullmatch(text) is None:
        raise UpworkPlatformManifestError(reason)
    return text


def _refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise UpworkPlatformManifestError("evidence_refs_invalid")
    return [_text(item, "evidence_refs_invalid", max_length=1024) for item in value]


def _source_url(value: Any) -> str:
    text = _text(value, "source_url_invalid", max_length=2048)
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"upwork.com", "www.upwork.com"}
        or parsed.query
        or parsed.fragment
    ):
        raise UpworkPlatformManifestError("source_url_invalid")
    return f"https://www.upwork.com{parsed.path.rstrip('/') or '/'}"


def _inventory_hashes(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _INVENTORY_FIELDS:
        raise UpworkPlatformManifestError("inventory_evidence_invalid")
    return {
        key: _hash(value[key], "inventory_evidence_invalid")
        for key in sorted(_INVENTORY_FIELDS)
    }


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manifest_from_observation(raw: Any) -> dict[str, Any]:
    """Normalize one secret-free account/source-health observation."""

    if not isinstance(raw, Mapping):
        raise UpworkPlatformManifestError("snapshot_invalid")
    if _OPPORTUNITY_KEYS.intersection(raw):
        raise UpworkPlatformManifestError("opportunity_snapshot_rejected")
    if set(raw) != _SNAPSHOT_FIELDS or raw.get("version") != 1 or raw.get("platform") != "upwork":
        raise UpworkPlatformManifestError("snapshot_invalid")
    observed_at = _timestamp(raw.get("observed_at"))
    source_url = _source_url(raw.get("source_url"))
    adapter_source_sha256 = _hash(
        raw.get("adapter_source_sha256"), "adapter_source_sha256_invalid",
    )
    authenticated = raw.get("authenticated")
    source_complete = raw.get("source_complete")
    profile_readback = raw.get("profile_readback")
    if (
        type(authenticated) is not bool
        or type(source_complete) is not bool
        or type(profile_readback) is not bool
    ):
        raise UpworkPlatformManifestError("account_state_invalid")
    account_hash = raw.get("account_id_sha256")
    if authenticated or profile_readback:
        account_hash = _hash(account_hash, "account_id_sha256_required")
    elif account_hash is not None:
        account_hash = _hash(account_hash, "account_id_sha256_invalid")
    inventory_hashes = _inventory_hashes(raw.get("inventory_evidence_sha256"))
    refs = _refs(raw.get("evidence_refs")) + [
        f"upwork://account/authenticated/{str(authenticated).lower()}",
        f"upwork://account/profile-readback/{str(profile_readback).lower()}",
        f"upwork://account/source-complete/{str(source_complete).lower()}",
    ]
    if account_hash is not None:
        refs.append(f"upwork://account/sha256/{account_hash}")
    refs.extend(f"upwork://inventory/{key}/{value}" for key, value in inventory_hashes.items())

    candidate = {
        "version": 1,
        "provider": "upwork",
        "policy": {
            "status": "unknown",
            "source_url": "https://www.upwork.com/legal#apimcpterms",
            "observed_at": observed_at,
        },
        "adapter": {
            "contract": "marketplace-core-v1",
            "actions": list(_REQUIRED_ACTIONS),
            "source_sha256": adapter_source_sha256,
        },
        "funded_work": {
            "status": "unknown",
            "receipt_ref": "provider-receipt://upwork/unverified",
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
            "currency": "USD",
            "evidence_refs": refs or ["upwork://account/observation"],
        },
    }
    return {
        "schema_version": 1,
        "source_kind": "platform",
        "provider": "upwork",
        "candidate_id": "platform:upwork",
        "candidate": candidate,
        "observed_at": observed_at,
        "source_url": source_url,
        "snapshot_sha256": _canonical_hash(raw),
        "evidence_refs": refs or ["upwork://account/observation"],
    }


def build_live_snapshot(
    state: Mapping[str, Any],
    *,
    account_id: str,
    adapter_source_sha256: str,
    source_url: str = "https://www.upwork.com/nx/wm/freelancer/home",
) -> dict[str, Any]:
    """Project one Upwork browser observation without retaining private rows."""

    if not isinstance(state, Mapping) or state.get("version") != 1 or state.get("provider") != "upwork":
        raise UpworkPlatformManifestError("live_state_invalid")
    account_id = _text(account_id, "account_id_invalid", max_length=256)
    evidence = state.get("evidence_sha256")
    required = {
        key: _hash(evidence.get(key), "inventory_evidence_invalid")
        if isinstance(evidence, Mapping) else None
        for key in sorted(_INVENTORY_FIELDS)
    }
    if any(value is None for value in required.values()):
        raise UpworkPlatformManifestError("inventory_evidence_invalid")
    observed_at = _timestamp(state.get("observed_at"))
    adapter_hash = _hash(adapter_source_sha256, "adapter_source_sha256_invalid")
    profile_readback = isinstance(evidence, Mapping) and isinstance(
        evidence.get("working-style"), str
    ) and _HASH.fullmatch(evidence["working-style"]) is not None
    snapshot = {
        "version": 1,
        "platform": "upwork",
        "observed_at": observed_at,
        "source_url": source_url,
        "adapter_source_sha256": adapter_hash,
        "authenticated": True,
        "source_complete": True,
        "profile_readback": profile_readback,
        "account_id_sha256": hashlib.sha256(account_id.encode("utf-8")).hexdigest(),
        "evidence_refs": [],
        "inventory_evidence_sha256": required,
    }
    return snapshot


class UpworkPlatformManifestSource:
    """Inject one Upwork account/source-health observation per wake."""

    def __init__(self, snapshot_loader: Any):
        if not callable(snapshot_loader):
            raise UpworkPlatformManifestError("snapshot_loader_invalid")
        self._snapshot_loader = snapshot_loader
        self._item: dict[str, Any] | None = None

    def _loaded(self) -> dict[str, Any]:
        if self._item is not None:
            return self._item
        try:
            manifest = manifest_from_observation(self._snapshot_loader())
            self._item = manifest_to_discovery_item(manifest)
        except UpworkPlatformManifestError:
            raise
        except Exception as error:  # noqa: BLE001 - typed at read-only boundary
            raise UpworkPlatformManifestError("snapshot_collect_failed") from error
        return self._item

    def discover(self) -> list[dict[str, Any]]:
        return [deepcopy(self._loaded())]


__all__ = [
    "UpworkPlatformManifestError",
    "UpworkPlatformManifestSource",
    "build_live_snapshot",
    "manifest_from_observation",
]
