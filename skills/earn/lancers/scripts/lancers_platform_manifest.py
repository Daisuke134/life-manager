#!/usr/bin/env python3
"""Build a platform-level Lancers Meta Loop manifest from account state.

The source is deliberately separate from public project discovery.  It accepts
only read-only account/work-sync facts and leaves every promotion gate unknown
until an official provider receipt or canary supplies the missing evidence.
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
        "lancers_platform_manifest_source",
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
    "logged_in", "source_complete", "board_count", "required_reply_count",
    "unread_count", "evidence_refs",
})
_OPPORTUNITY_KEYS = frozenset({
    "opportunities", "projects", "listings", "jobs", "requests",
})
_REQUIRED_ACTIONS = [
    "discover", "inspect", "propose", "message", "accept_offer", "deliver",
    "read_payments", "read_payouts",
]


class LancersPlatformManifestError(ValueError):
    """The Lancers account observation is malformed or the wrong source kind."""


def _text(value: Any, reason: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise LancersPlatformManifestError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise LancersPlatformManifestError(reason)
    return text


def _timestamp(value: Any) -> str:
    text = _text(value, "observed_at_invalid", max_length=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise LancersPlatformManifestError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LancersPlatformManifestError("observed_at_invalid")
    return text


def _hash(value: Any, reason: str) -> str:
    text = _text(value, reason, max_length=64)
    if _HASH.fullmatch(text) is None:
        raise LancersPlatformManifestError(reason)
    return text


def _refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise LancersPlatformManifestError("evidence_refs_invalid")
    return [_text(item, "evidence_refs_invalid", max_length=1024) for item in value]


def _count(value: Any, reason: str) -> int:
    if type(value) is not int or value < 0:
        raise LancersPlatformManifestError(reason)
    return value


def _source_url(value: Any) -> str:
    text = _text(value, "source_url_invalid", max_length=2048)
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"www.lancers.jp", "lancers.jp"}
        or parsed.query
        or parsed.fragment
    ):
        raise LancersPlatformManifestError("source_url_invalid")
    return f"https://www.lancers.jp{parsed.path.rstrip('/') or '/'}"


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manifest_from_observation(raw: Any) -> dict[str, Any]:
    """Normalize one account/work-sync observation into a generic manifest."""

    if not isinstance(raw, Mapping):
        raise LancersPlatformManifestError("snapshot_invalid")
    if _OPPORTUNITY_KEYS.intersection(raw):
        raise LancersPlatformManifestError("opportunity_snapshot_rejected")
    if set(raw) != _SNAPSHOT_FIELDS or raw.get("version") != 1 or raw.get("platform") != "lancers":
        raise LancersPlatformManifestError("snapshot_invalid")
    observed_at = _timestamp(raw.get("observed_at"))
    source_url = _source_url(raw.get("source_url"))
    adapter_source_sha256 = _hash(raw.get("adapter_source_sha256"), "adapter_source_sha256_invalid")
    logged_in = raw.get("logged_in")
    source_complete = raw.get("source_complete")
    if type(logged_in) is not bool or type(source_complete) is not bool:
        raise LancersPlatformManifestError("account_state_invalid")
    _count(raw.get("board_count"), "board_count_invalid")
    _count(raw.get("required_reply_count"), "required_reply_count_invalid")
    _count(raw.get("unread_count"), "unread_count_invalid")
    refs = _refs(raw.get("evidence_refs"))
    refs = refs + [
        f"lancers://account/logged-in/{str(logged_in).lower()}",
        f"lancers://account/source-complete/{str(source_complete).lower()}",
    ]
    candidate = {
        "version": 1,
        "provider": "lancers",
        "policy": {
            "status": "unknown",
            "source_url": "https://www.lancers.jp/terms",
            "observed_at": observed_at,
        },
        "adapter": {
            "contract": "marketplace-core-v1",
            "actions": list(_REQUIRED_ACTIONS),
            "source_sha256": adapter_source_sha256,
        },
        "funded_work": {
            "status": "unknown",
            "receipt_ref": "provider-receipt://lancers/unverified",
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
            "evidence_refs": refs or ["lancers://account/observation"],
        },
    }
    return {
        "schema_version": 1,
        "source_kind": "platform",
        "provider": "lancers",
        "candidate_id": "platform:lancers",
        "candidate": candidate,
        "observed_at": observed_at,
        "source_url": source_url,
        "snapshot_sha256": _canonical_hash(raw),
        "evidence_refs": refs or ["lancers://account/observation"],
    }


def load_contracts_observation(
    path: str | Path,
    *,
    observed_at: str,
    adapter_source_sha256: str,
    source_url: str = "https://www.lancers.jp/mypage",
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Read the work-sync account state and discard opportunity/contract rows."""

    contracts_path = Path(path).expanduser()
    if contracts_path.is_symlink() or not contracts_path.is_file():
        raise LancersPlatformManifestError("work_sync_source_missing")
    try:
        raw = json.loads(contracts_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LancersPlatformManifestError("work_sync_source_invalid") from error
    if not isinstance(raw, Mapping):
        raise LancersPlatformManifestError("work_sync_source_invalid")
    fields = {
        "version": 1,
        "platform": "lancers",
        "observed_at": observed_at,
        "source_url": source_url,
        "adapter_source_sha256": adapter_source_sha256,
        "logged_in": raw.get("logged_in"),
        "source_complete": raw.get("source_complete"),
        "board_count": raw.get("board_count"),
        "required_reply_count": raw.get("required_reply_count"),
        "unread_count": raw.get("unread_count"),
        "evidence_refs": evidence_refs or ["private:lancers/contracts.json"],
    }
    manifest_from_observation(fields)
    return fields


class LancersPlatformManifestSource:
    """Inject one Lancers account observation per wake, read-only."""

    def __init__(self, snapshot_loader: Any):
        if not callable(snapshot_loader):
            raise LancersPlatformManifestError("snapshot_loader_invalid")
        self._snapshot_loader = snapshot_loader
        self._item: dict[str, Any] | None = None

    def _loaded(self) -> dict[str, Any]:
        if self._item is not None:
            return self._item
        try:
            manifest = manifest_from_observation(self._snapshot_loader())
            self._item = manifest_to_discovery_item(manifest)
        except LancersPlatformManifestError:
            raise
        except Exception as error:  # noqa: BLE001 - typed at the read-only boundary
            raise LancersPlatformManifestError("snapshot_collect_failed") from error
        return self._item

    def discover(self) -> list[dict[str, Any]]:
        return [deepcopy(self._loaded())]


__all__ = [
    "LancersPlatformManifestError",
    "LancersPlatformManifestSource",
    "load_contracts_observation",
    "manifest_from_observation",
]
