#!/usr/bin/env python3
"""Build a platform-level Mercor Meta Loop manifest from source health.

Mercor reply/pass snapshots contain applications and listings.  This adapter
accepts only account/source-health facts and never treats a listing or an
application as platform qualification evidence.
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
        "mercor_platform_manifest_source",
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
    "account_id", "source_complete", "gmail_status", "contract_readback", "evidence_refs",
})
_OPPORTUNITY_KEYS = frozenset({
    "applications", "inspected_listings", "listings", "jobs", "requests", "contracts",
})
_REQUIRED_ACTIONS = [
    "discover", "inspect", "propose", "message", "accept_offer", "deliver",
    "read_payments", "read_payouts",
]


class MercorPlatformManifestError(ValueError):
    """The Mercor source-health observation is malformed or the wrong source kind."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise MercorPlatformManifestError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise MercorPlatformManifestError(reason)
    return text


def _timestamp(value: Any) -> str:
    text = _text(value, "observed_at_invalid", max_length=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise MercorPlatformManifestError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MercorPlatformManifestError("observed_at_invalid")
    return text


def _hash(value: Any, reason: str) -> str:
    text = _text(value, reason, max_length=64)
    if _HASH.fullmatch(text) is None:
        raise MercorPlatformManifestError(reason)
    return text


def _refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise MercorPlatformManifestError("evidence_refs_invalid")
    return [_text(item, "evidence_refs_invalid", max_length=1024) for item in value]


def _source_url(value: Any) -> str:
    text = _text(value, "source_url_invalid", max_length=2048)
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "work.mercor.com"
        or parsed.query
        or parsed.fragment
    ):
        raise MercorPlatformManifestError("source_url_invalid")
    return f"https://work.mercor.com{parsed.path.rstrip('/') or '/'}"


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manifest_from_observation(raw: Any) -> dict[str, Any]:
    """Normalize one Mercor source-health observation into a generic manifest."""

    if not isinstance(raw, Mapping):
        raise MercorPlatformManifestError("snapshot_invalid")
    if _OPPORTUNITY_KEYS.intersection(raw):
        raise MercorPlatformManifestError("opportunity_snapshot_rejected")
    if set(raw) != _SNAPSHOT_FIELDS or raw.get("version") != 1 or raw.get("platform") != "mercor":
        raise MercorPlatformManifestError("snapshot_invalid")
    observed_at = _timestamp(raw.get("observed_at"))
    source_url = _source_url(raw.get("source_url"))
    adapter_source_sha256 = _hash(raw.get("adapter_source_sha256"), "adapter_source_sha256_invalid")
    account_id = _text(raw.get("account_id"), "account_id_invalid", max_length=256)
    source_complete = raw.get("source_complete")
    contract_readback = raw.get("contract_readback")
    gmail_status = raw.get("gmail_status")
    if type(source_complete) is not bool or type(contract_readback) is not bool:
        raise MercorPlatformManifestError("account_state_invalid")
    if gmail_status not in {"fresh", "stale"}:
        raise MercorPlatformManifestError("gmail_status_invalid")
    refs = _refs(raw.get("evidence_refs")) + [
        f"mercor://account/id-sha256/{hashlib.sha256(account_id.encode()).hexdigest()}",
        f"mercor://source-complete/{str(source_complete).lower()}",
        f"mercor://gmail/{gmail_status}",
        f"mercor://contract-readback/{str(contract_readback).lower()}",
    ]
    candidate = {
        "version": 1,
        "provider": "mercor",
        "policy": {
            "status": "unknown",
            "source_url": "https://work.mercor.com/terms",
            "observed_at": observed_at,
        },
        "adapter": {
            "contract": "marketplace-core-v1",
            "actions": list(_REQUIRED_ACTIONS),
            "source_sha256": adapter_source_sha256,
        },
        "funded_work": {
            "status": "unknown",
            "receipt_ref": "provider-receipt://mercor/unverified",
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
            "evidence_refs": refs or ["mercor://account/observation"],
        },
    }
    return {
        "schema_version": 1,
        "source_kind": "platform",
        "provider": "mercor",
        "candidate_id": "platform:mercor",
        "candidate": candidate,
        "observed_at": observed_at,
        "source_url": source_url,
        "snapshot_sha256": _canonical_hash(raw),
        "evidence_refs": refs or ["mercor://account/observation"],
    }


class MercorPlatformManifestSource:
    """Inject one Mercor source-health observation per wake, read-only."""

    def __init__(self, snapshot_loader: Any):
        if not callable(snapshot_loader):
            raise MercorPlatformManifestError("snapshot_loader_invalid")
        self._snapshot_loader = snapshot_loader
        self._item: dict[str, Any] | None = None

    def _loaded(self) -> dict[str, Any]:
        if self._item is not None:
            return self._item
        try:
            manifest = manifest_from_observation(self._snapshot_loader())
            self._item = manifest_to_discovery_item(manifest)
        except MercorPlatformManifestError:
            raise
        except Exception as error:  # noqa: BLE001 - typed at the read-only boundary
            raise MercorPlatformManifestError("snapshot_collect_failed") from error
        return self._item

    def discover(self) -> list[dict[str, Any]]:
        return [deepcopy(self._loaded())]


__all__ = [
    "MercorPlatformManifestError",
    "MercorPlatformManifestSource",
    "manifest_from_observation",
]
