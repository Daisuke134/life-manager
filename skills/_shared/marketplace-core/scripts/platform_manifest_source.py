"""Read-only bridge for platform-level Meta Loop candidate manifests.

This module accepts one platform manifest per source wake.  It intentionally
does not accept opportunity/listing snapshots: those belong to the shared
Opportunity runner and are not evidence that a new platform is qualified.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any, Mapping


_HASH = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
_PLATFORM_ID = re.compile(r"^platform:(?P<provider>[a-z][a-z0-9_-]{1,31})$")
_CANDIDATE_FIELDS = frozenset({
    "version", "provider", "policy", "adapter", "funded_work", "canary",
    "unit_economics",
})
_MANIFEST_FIELDS = frozenset({
    "schema_version", "source_kind", "provider", "candidate_id", "candidate",
    "observed_at", "source_url", "snapshot_sha256", "evidence_refs",
})
_OPPORTUNITY_KEYS = frozenset({
    "opportunities", "request_details", "listings", "jobs", "requests",
})


class PlatformManifestError(ValueError):
    """A platform-level manifest is malformed or is the wrong source kind."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise PlatformManifestError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise PlatformManifestError(reason)
    return text


def _timestamp(value: Any) -> str:
    text = _text(value, "observed_at_invalid", max_length=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise PlatformManifestError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PlatformManifestError("observed_at_invalid")
    return text


def _hash(value: Any) -> str:
    text = _text(value, "snapshot_sha256_invalid", max_length=64)
    if _HASH.fullmatch(text) is None:
        raise PlatformManifestError("snapshot_sha256_invalid")
    return text


def _evidence_refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise PlatformManifestError("evidence_refs_invalid")
    refs: list[str] = []
    for item in value:
        refs.append(_text(item, "evidence_refs_invalid", max_length=1024))
    return refs


def _candidate(raw: Any, provider: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _CANDIDATE_FIELDS:
        raise PlatformManifestError("candidate_invalid")
    if raw.get("version") != 1 or raw.get("provider") != provider:
        raise PlatformManifestError("provider_mismatch")
    return dict(raw)


def manifest_to_discovery_item(raw: Any) -> dict[str, Any]:
    """Validate one platform manifest and return the discovery-cycle item."""

    if not isinstance(raw, Mapping):
        raise PlatformManifestError("platform_manifest_invalid")
    if _OPPORTUNITY_KEYS.intersection(raw):
        raise PlatformManifestError("opportunity_snapshot_rejected")
    if set(raw) != _MANIFEST_FIELDS or raw.get("schema_version") != 1:
        raise PlatformManifestError("platform_manifest_invalid")
    if raw.get("source_kind") != "platform":
        raise PlatformManifestError("source_kind_invalid")
    provider = _text(raw.get("provider"), "provider_invalid", max_length=32)
    if _PROVIDER.fullmatch(provider) is None:
        raise PlatformManifestError("provider_invalid")
    candidate_id = _text(raw.get("candidate_id"), "candidate_id_invalid", max_length=128)
    candidate_match = _PLATFORM_ID.fullmatch(candidate_id)
    if candidate_match is None or candidate_match.group("provider") != provider:
        raise PlatformManifestError("candidate_id_invalid")
    candidate = _candidate(raw.get("candidate"), provider)
    source_url = _text(raw.get("source_url"), "source_url_invalid", max_length=2048)
    if not source_url.startswith("https://"):
        raise PlatformManifestError("source_url_invalid")
    return {
        "source_kind": "platform",
        "candidate": candidate,
        "candidate_id": candidate_id,
        "observed_at": _timestamp(raw.get("observed_at")),
        "source_url": source_url,
        "snapshot_sha256": _hash(raw.get("snapshot_sha256")),
        "evidence_refs": _evidence_refs(raw.get("evidence_refs")),
    }


class PlatformManifestSource:
    """Inject one immutable, read-only platform manifest per wake."""

    def __init__(self, snapshot_loader: Any):
        if not callable(snapshot_loader):
            raise PlatformManifestError("snapshot_loader_invalid")
        self._snapshot_loader = snapshot_loader
        self._item: dict[str, Any] | None = None

    def _loaded(self) -> dict[str, Any]:
        if self._item is not None:
            return self._item
        try:
            raw = self._snapshot_loader()
        except PlatformManifestError:
            raise
        except Exception as error:  # noqa: BLE001 - typed at the read-only boundary
            raise PlatformManifestError("snapshot_collect_failed") from error
        self._item = manifest_to_discovery_item(raw)
        return self._item

    def discover(self) -> list[dict[str, Any]]:
        """Return one platform candidate item without contacting a provider."""

        return [deepcopy(self._loaded())]


__all__ = [
    "PlatformManifestError",
    "PlatformManifestSource",
    "manifest_to_discovery_item",
]
