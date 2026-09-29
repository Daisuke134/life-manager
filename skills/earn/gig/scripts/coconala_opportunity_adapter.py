#!/usr/bin/env python3
"""Pure Coconala application-snapshot adapter for the shared opportunity contract.

The browser collector and any provider transport stay outside this module.  Given a
validated application snapshot, it exposes only open, not-yet-applied opportunities
and an identity-bound read-only inspect operation.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
from typing import Any

try:
    from provider_adapter import Opportunity, OpportunityDetail
except ModuleNotFoundError:  # pragma: no cover - direct module loading fallback
    _provider_spec = importlib.util.spec_from_file_location(
        "coconala_provider_adapter", Path(__file__).with_name("provider_adapter.py")
    )
    if _provider_spec is None or _provider_spec.loader is None:
        raise
    _provider_module = importlib.util.module_from_spec(_provider_spec)
    sys.modules[_provider_spec.name] = _provider_module
    _provider_spec.loader.exec_module(_provider_module)
    Opportunity = _provider_module.Opportunity
    OpportunityDetail = _provider_module.OpportunityDetail

try:
    from application_snapshot import validate_snapshot
except ModuleNotFoundError:  # pragma: no cover - direct module loading fallback
    _snapshot_spec = importlib.util.spec_from_file_location(
        "coconala_application_snapshot", Path(__file__).with_name("application_snapshot.py")
    )
    if _snapshot_spec is None or _snapshot_spec.loader is None:
        raise
    _snapshot_module = importlib.util.module_from_spec(_snapshot_spec)
    sys.modules[_snapshot_spec.name] = _snapshot_module
    _snapshot_spec.loader.exec_module(_snapshot_module)
    validate_snapshot = _snapshot_module.validate_snapshot


_REQUEST_ID = re.compile(r"^(?:[0-9]+|[0-7][0-9A-HJKMNP-TV-Z]{25})$")
_OPPORTUNITY_ID = re.compile(r"^request:(?P<request_id>[0-9]+|[0-7][0-9A-HJKMNP-TV-Z]{25})$")


class CoconalaDiscoveryError(ValueError):
    """The snapshot cannot safely produce a shared opportunity record."""


def _validated_snapshot(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise CoconalaDiscoveryError("snapshot_invalid")
    errors = validate_snapshot(snapshot)
    if errors:
        raise CoconalaDiscoveryError("snapshot_invalid:" + ",".join(errors[:4]))
    return snapshot


def _request_id(value: Any) -> str:
    text = str(value or "").strip()
    if _REQUEST_ID.fullmatch(text) is None:
        raise CoconalaDiscoveryError("request_id_invalid")
    return text


def _opportunity_id(request_id: str) -> str:
    return f"request:{request_id}"


def _request_id_from_opportunity(value: Any) -> str:
    match = _OPPORTUNITY_ID.fullmatch(str(value or "").strip())
    if match is None:
        raise CoconalaDiscoveryError("opportunity_id_invalid")
    return match.group("request_id")


def _opportunity(detail: dict[str, Any]) -> Opportunity:
    request_id = _request_id(detail.get("request_id"))
    return Opportunity(
        provider="coconala",
        opportunity_id=_opportunity_id(request_id),
        source_url=str(detail["canonical_url"]),
        title=str(detail["title"]),
        currency="JPY",
        source_hash=str(detail["content_sha256"]),
        observed_at=str(detail["observed_at"]),
    )


def opportunities_from_snapshot(
    snapshot: dict[str, Any],
    *,
    include_closed: bool = False,
    include_applied: bool = False,
    max_items: int = 40,
) -> list[Opportunity]:
    """Convert a validated Coconala snapshot into bounded shared opportunities."""

    if type(max_items) is not int or not 1 <= max_items <= 40:
        raise CoconalaDiscoveryError("discovery_bound_invalid")
    envelope = _validated_snapshot(snapshot)
    applied = set(envelope["already_applied_ids"])
    found: list[Opportunity] = []
    for raw in envelope["request_details"]:
        detail = dict(raw)
        request_id = _request_id(detail["request_id"])
        if not include_closed and detail["accepting_applications"] is not True:
            continue
        if not include_applied and request_id in applied:
            continue
        if len(found) >= max_items:
            raise CoconalaDiscoveryError("discovery_bound_exceeded")
        found.append(_opportunity(detail))
    return found


def inspect_from_snapshot(
    snapshot: dict[str, Any], opportunity_id: str,
) -> OpportunityDetail:
    """Read one opportunity's stable scope and content hash from the same snapshot."""

    envelope = _validated_snapshot(snapshot)
    request_id = _request_id_from_opportunity(opportunity_id)
    for raw in envelope["request_details"]:
        if _request_id(raw.get("request_id")) != request_id:
            continue
        detail = dict(raw)
        opportunity = _opportunity(detail)
        return OpportunityDetail(
            opportunity=opportunity,
            scope=str(detail["visible_text"]),
            source_hash=str(detail["content_sha256"]),
        )
    raise CoconalaDiscoveryError("opportunity_not_found")


class CoconalaSnapshotAdapter:
    """Read-only adapter over one already captured Coconala snapshot."""

    def __init__(self, snapshot: dict[str, Any], *, max_items: int = 40):
        self._snapshot = snapshot
        self._max_items = max_items

    def discover(self) -> list[Opportunity]:
        return opportunities_from_snapshot(self._snapshot, max_items=self._max_items)

    def inspect(self, opportunity_id: str) -> OpportunityDetail:
        return inspect_from_snapshot(self._snapshot, opportunity_id)


class CoconalaSnapshotSource:
    """Read-only bridge from the existing authenticated collector to the shared runner.

    ``snapshot_loader`` is deliberately injected: the existing browser collector owns
    CDP/session lifecycle, while this source owns one immutable snapshot per wake.  A
    failed collector is converted to a typed discovery error and cannot fall through to
    an empty candidate list or any provider mutation.
    """

    def __init__(self, snapshot_loader: Any, *, max_items: int = 40):
        if not callable(snapshot_loader):
            raise CoconalaDiscoveryError("snapshot_loader_invalid")
        if type(max_items) is not int or not 1 <= max_items <= 40:
            raise CoconalaDiscoveryError("discovery_bound_invalid")
        self._snapshot_loader = snapshot_loader
        self._max_items = max_items
        self._adapter: CoconalaSnapshotAdapter | None = None

    def _loaded(self) -> CoconalaSnapshotAdapter:
        if self._adapter is not None:
            return self._adapter
        try:
            snapshot = self._snapshot_loader()
        except CoconalaDiscoveryError:
            raise
        except Exception as error:  # noqa: BLE001 - typed at the read-only boundary
            raise CoconalaDiscoveryError("snapshot_collect_failed") from error
        self._adapter = CoconalaSnapshotAdapter(snapshot, max_items=self._max_items)
        return self._adapter

    def discover(self) -> list[Opportunity]:
        return self._loaded().discover()

    def inspect(self, opportunity_id: str) -> OpportunityDetail:
        return self._loaded().inspect(opportunity_id)


__all__ = [
    "CoconalaDiscoveryError",
    "CoconalaSnapshotAdapter",
    "CoconalaSnapshotSource",
    "inspect_from_snapshot",
    "opportunities_from_snapshot",
]
