#!/usr/bin/env python3
"""Build a read-only Freelancer platform manifest for Meta Loop."""

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
except ModuleNotFoundError:  # pragma: no cover
    spec = importlib.util.spec_from_file_location(
        "freelancer_platform_manifest_source",
        Path(__file__).resolve().parents[3] / "_shared" / "marketplace-core" / "scripts"
        / "platform_manifest_source.py",
    )
    if spec is None or spec.loader is None:
        raise
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    manifest_to_discovery_item = module.manifest_to_discovery_item


_HASH = re.compile(r"^[0-9a-f]{64}$")
_SNAPSHOT_FIELDS = frozenset({
    "version", "platform", "observed_at", "source_url", "adapter_source_sha256",
    "authenticated", "source_complete", "profile_readback", "account_id_sha256",
    "evidence_refs", "inventory_evidence_sha256",
})
_INVENTORY_FIELDS = frozenset({"identity", "projects", "payments", "payouts"})
_OPPORTUNITY_KEYS = frozenset({
    "bids", "contracts", "jobs", "listings", "messages", "projects", "proposals",
    "requests", "request_details",
})
_REQUIRED_ACTIONS = [
    "discover", "inspect", "propose", "message", "accept_offer", "deliver",
    "read_payments", "read_payouts",
]


class FreelancerPlatformManifestError(ValueError):
    """The Freelancer account observation is malformed or not platform-only."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise FreelancerPlatformManifestError(reason)
    value = value.strip()
    if not value or len(value) > max_length or "\x00" in value:
        raise FreelancerPlatformManifestError(reason)
    return value


def _timestamp(value: Any) -> str:
    value = _text(value, "observed_at_invalid", max_length=80)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FreelancerPlatformManifestError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FreelancerPlatformManifestError("observed_at_invalid")
    return value


def _hash(value: Any, reason: str) -> str:
    value = _text(value, reason, max_length=64)
    if _HASH.fullmatch(value) is None:
        raise FreelancerPlatformManifestError(reason)
    return value


def _refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise FreelancerPlatformManifestError("evidence_refs_invalid")
    return [_text(item, "evidence_refs_invalid", max_length=1024) for item in value]


def _source_url(value: Any) -> str:
    value = _text(value, "source_url_invalid", max_length=2048)
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"freelancer.com", "www.freelancer.com"}
        or parsed.query or parsed.fragment
    ):
        raise FreelancerPlatformManifestError("source_url_invalid")
    return f"https://www.freelancer.com{parsed.path.rstrip('/') or '/'}"


def _inventory(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _INVENTORY_FIELDS:
        raise FreelancerPlatformManifestError("inventory_evidence_invalid")
    return {key: _hash(value[key], "inventory_evidence_invalid") for key in sorted(_INVENTORY_FIELDS)}


def _canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def manifest_from_observation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise FreelancerPlatformManifestError("snapshot_invalid")
    if _OPPORTUNITY_KEYS.intersection(raw):
        raise FreelancerPlatformManifestError("opportunity_snapshot_rejected")
    if set(raw) != _SNAPSHOT_FIELDS or raw.get("version") != 1 or raw.get("platform") != "freelancer":
        raise FreelancerPlatformManifestError("snapshot_invalid")
    observed_at = _timestamp(raw.get("observed_at"))
    source_url = _source_url(raw.get("source_url"))
    adapter_hash = _hash(raw.get("adapter_source_sha256"), "adapter_source_sha256_invalid")
    authenticated = raw.get("authenticated")
    source_complete = raw.get("source_complete")
    profile_readback = raw.get("profile_readback")
    if type(authenticated) is not bool or type(source_complete) is not bool or type(profile_readback) is not bool:
        raise FreelancerPlatformManifestError("account_state_invalid")
    account_hash = raw.get("account_id_sha256")
    if authenticated or profile_readback:
        account_hash = _hash(account_hash, "account_id_sha256_required")
    elif account_hash is not None:
        account_hash = _hash(account_hash, "account_id_sha256_invalid")
    inventory = _inventory(raw.get("inventory_evidence_sha256"))
    refs = _refs(raw.get("evidence_refs")) + [
        f"freelancer://account/authenticated/{str(authenticated).lower()}",
        f"freelancer://account/profile-readback/{str(profile_readback).lower()}",
        f"freelancer://account/source-complete/{str(source_complete).lower()}",
    ]
    if account_hash is not None:
        refs.append(f"freelancer://account/sha256/{account_hash}")
    refs.extend(f"freelancer://inventory/{key}/{value}" for key, value in inventory.items())
    candidate = {
        "version": 1,
        "provider": "freelancer",
        "policy": {
            "status": "unknown",
            "source_url": "https://developers.freelancer.com/docs/api-overview/types-of-integrations",
            "observed_at": observed_at,
        },
        "adapter": {
            "contract": "marketplace-core-v1", "actions": list(_REQUIRED_ACTIONS),
            "source_sha256": adapter_hash,
        },
        "funded_work": {
            "status": "unknown", "receipt_ref": "provider-receipt://freelancer/unverified",
            "observed_at": observed_at,
        },
        "canary": {
            "status": "unknown", "official_receipt_ref": None, "replay_zero": False,
            "observed_at": observed_at,
        },
        "unit_economics": {
            "status": "unknown", "net_amount_minor": 0, "currency": "USD",
            "evidence_refs": refs or ["freelancer://account/observation"],
        },
    }
    return {
        "schema_version": 1, "source_kind": "platform", "provider": "freelancer",
        "candidate_id": "platform:freelancer", "candidate": candidate,
        "observed_at": observed_at, "source_url": source_url,
        "snapshot_sha256": _canonical_hash(raw),
        "evidence_refs": refs or ["freelancer://account/observation"],
    }


def build_live_snapshot(
    state: Mapping[str, Any], *, account_id: str, adapter_source_sha256: str,
    source_url: str = "https://www.freelancer.com/dashboard",
) -> dict[str, Any]:
    """Project an authenticated inventory state without retaining contract rows."""
    if not isinstance(state, Mapping) or state.get("version") != 1 or state.get("provider") != "freelancer":
        raise FreelancerPlatformManifestError("live_state_invalid")
    account_id = _text(account_id, "account_id_invalid", max_length=256)
    evidence = state.get("evidence_sha256")
    if not isinstance(evidence, Mapping):
        raise FreelancerPlatformManifestError("inventory_evidence_invalid")
    inventory = {
        key: _hash(evidence.get(key), "inventory_evidence_invalid")
        for key in sorted(_INVENTORY_FIELDS)
    }
    observed_at = _timestamp(state.get("observed_at"))
    profile = evidence.get("profile")
    profile_readback = isinstance(profile, str) and _HASH.fullmatch(profile) is not None
    return {
        "version": 1, "platform": "freelancer", "observed_at": observed_at,
        "source_url": source_url,
        "adapter_source_sha256": _hash(adapter_source_sha256, "adapter_source_sha256_invalid"),
        "authenticated": True,
        "source_complete": bool(state.get("source_complete", False)),
        "profile_readback": profile_readback,
        "account_id_sha256": hashlib.sha256(account_id.encode("utf-8")).hexdigest(),
        "evidence_refs": [], "inventory_evidence_sha256": inventory,
    }


class FreelancerPlatformManifestSource:
    """Inject one Freelancer source-health observation per wake."""

    def __init__(self, snapshot_loader: Any):
        if not callable(snapshot_loader):
            raise FreelancerPlatformManifestError("snapshot_loader_invalid")
        self._snapshot_loader = snapshot_loader
        self._item: dict[str, Any] | None = None

    def _loaded(self) -> dict[str, Any]:
        if self._item is not None:
            return self._item
        try:
            self._item = manifest_to_discovery_item(
                manifest_from_observation(self._snapshot_loader())
            )
        except FreelancerPlatformManifestError:
            raise
        except Exception as error:  # noqa: BLE001 - typed at the read-only boundary
            raise FreelancerPlatformManifestError("snapshot_collect_failed") from error
        return self._item

    def discover(self) -> list[dict[str, Any]]:
        return [deepcopy(self._loaded())]


__all__ = [
    "FreelancerPlatformManifestError", "FreelancerPlatformManifestSource",
    "build_live_snapshot", "manifest_from_observation",
]
