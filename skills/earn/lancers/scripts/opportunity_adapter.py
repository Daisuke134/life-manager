#!/usr/bin/env python3
"""Pure Lancers public-discovery adapter for the shared opportunity contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit


_PROVIDER_PATH = Path(__file__).resolve().parents[2] / "gig" / "scripts" / "provider_adapter.py"
_provider_spec = importlib.util.spec_from_file_location(
    "lancers_provider_adapter", _PROVIDER_PATH,
)
if _provider_spec is None or _provider_spec.loader is None:
    raise RuntimeError("provider_adapter_unavailable")
_provider_module = importlib.util.module_from_spec(_provider_spec)
sys.modules[_provider_spec.name] = _provider_module
_provider_spec.loader.exec_module(_provider_module)
Opportunity = _provider_module.Opportunity
OpportunityDetail = _provider_module.OpportunityDetail


_PROJECT_ID = re.compile(r"^[1-9][0-9]{0,511}$")
_OPPORTUNITY_ID = re.compile(r"^project:(?P<project_id>[1-9][0-9]{0,511})$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


class LancersDiscoveryError(ValueError):
    """The read-only Lancers snapshot cannot safely produce a shared record."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise LancersDiscoveryError("project_snapshot_unserializable") from error


def _text(value: Any, reason: str, *, max_length: int = 200_000) -> str:
    if not isinstance(value, str):
        raise LancersDiscoveryError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise LancersDiscoveryError(reason)
    return text


def _project_id(value: Any) -> str:
    text = _text(value, "project_id_invalid", max_length=512)
    if _PROJECT_ID.fullmatch(text) is None:
        raise LancersDiscoveryError("project_id_invalid")
    return text


def _canonical_url(value: Any, project_id: str) -> str:
    raw = _text(value, "project_url_invalid", max_length=2048)
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"www.lancers.jp", "lancers.jp"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.path != f"/work/detail/{project_id}"
    ):
        raise LancersDiscoveryError("project_url_invalid")
    return f"https://www.lancers.jp/work/detail/{project_id}"


def _observed_at(value: Any) -> str:
    text = _text(value, "observed_at_invalid", max_length=80)
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as error:
        raise LancersDiscoveryError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LancersDiscoveryError("observed_at_invalid")
    return text


def _record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise LancersDiscoveryError("project_record_invalid")
    project_id = _project_id(record.get("external_id"))
    title = _text(record.get("title"), "project_title_invalid", max_length=512)
    description = _text(record.get("description"), "project_description_invalid")
    category = _text(record.get("category"), "project_category_invalid", max_length=512)
    url = _canonical_url(record.get("url"), project_id)
    observed_at = _observed_at(record.get("observed_at"))
    budget_type = _text(record.get("budget_type"), "project_budget_type_invalid", max_length=32)
    # Lancers is a JPY marketplace. A missing budget does not make the opportunity
    # disappear; it remains a valid identity with no budget claim in the scope.
    currency = record.get("currency") or "JPY"
    if currency != "JPY":
        raise LancersDiscoveryError("project_currency_invalid")
    return {
        "external_id": project_id,
        "title": title,
        "description": description,
        "category": category,
        "url": url,
        "observed_at": observed_at,
        "budget_type": budget_type,
        "currency": "JPY",
        "source_hash": hashlib.sha256(_canonical_bytes(record)).hexdigest(),
    }


def _opportunity(record: dict[str, Any]) -> Any:
    return Opportunity(
        provider="lancers",
        opportunity_id=f"project:{record['external_id']}",
        source_url=record["url"],
        title=record["title"],
        currency="JPY",
        source_hash=record["source_hash"],
        observed_at=record["observed_at"],
    )


def _scope(record: dict[str, Any]) -> str:
    return "\n".join((
        f"案件名: {record['title']}",
        f"カテゴリ: {record['category']}",
        f"形式: {record['budget_type']}",
        f"内容: {record['description']}",
    ))


def _validated_snapshot(snapshot: Any) -> tuple[list[dict[str, Any]], set[str]]:
    if not isinstance(snapshot, dict):
        raise LancersDiscoveryError("snapshot_invalid")
    if snapshot.get("ok") is not True or snapshot.get("platform") != "lancers":
        error = str(snapshot.get("error") or "snapshot_unavailable")
        raise LancersDiscoveryError(f"snapshot_unavailable:{error[:80]}")
    raw_records = snapshot.get("opportunities")
    if not isinstance(raw_records, list):
        raise LancersDiscoveryError("opportunities_invalid")
    raw_applied = snapshot.get("already_applied_ids", [])
    if not isinstance(raw_applied, list):
        raise LancersDiscoveryError("already_applied_ids_invalid")
    applied = {_project_id(value) for value in raw_applied}
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_records:
        record = _record(raw)
        project_id = record["external_id"]
        if project_id in seen:
            raise LancersDiscoveryError("duplicate_project_id")
        seen.add(project_id)
        records.append(record)
    return records, applied


class LancersSnapshotAdapter:
    """Read-only adapter over one status.run_discovery result."""

    def __init__(self, snapshot: dict[str, Any], *, max_items: int = 40):
        if type(max_items) is not int or not 1 <= max_items <= 100:
            raise LancersDiscoveryError("discovery_bound_invalid")
        self._snapshot = snapshot
        self._max_items = max_items

    def _records(self) -> tuple[list[dict[str, Any]], set[str]]:
        records, applied = _validated_snapshot(self._snapshot)
        if len(records) > self._max_items:
            raise LancersDiscoveryError("discovery_bound_exceeded")
        return records, applied

    def discover(self) -> list[Any]:
        records, applied = self._records()
        return [_opportunity(record) for record in records if record["external_id"] not in applied]

    def inspect(self, opportunity_id: str) -> Any:
        match = _OPPORTUNITY_ID.fullmatch(str(opportunity_id or "").strip())
        if match is None:
            raise LancersDiscoveryError("opportunity_id_invalid")
        project_id = match.group("project_id")
        records, applied = self._records()
        if project_id in applied:
            raise LancersDiscoveryError("opportunity_already_applied")
        for record in records:
            if record["external_id"] == project_id:
                opportunity = _opportunity(record)
                return OpportunityDetail(
                    opportunity=opportunity,
                    scope=_scope(record),
                    source_hash=record["source_hash"],
                )
        raise LancersDiscoveryError("opportunity_not_found")


class LancersSnapshotSource:
    """Inject one existing read-only status collector result per wake."""

    def __init__(self, snapshot_loader: Any, *, max_items: int = 40):
        if not callable(snapshot_loader):
            raise LancersDiscoveryError("snapshot_loader_invalid")
        self._snapshot_loader = snapshot_loader
        self._max_items = max_items
        self._adapter: LancersSnapshotAdapter | None = None

    def _loaded(self) -> LancersSnapshotAdapter:
        if self._adapter is None:
            try:
                snapshot = self._snapshot_loader()
            except LancersDiscoveryError:
                raise
            except Exception as error:  # noqa: BLE001 - typed read-only boundary
                raise LancersDiscoveryError("snapshot_collect_failed") from error
            self._adapter = LancersSnapshotAdapter(snapshot, max_items=self._max_items)
        return self._adapter

    def discover(self) -> list[Any]:
        return self._loaded().discover()

    def inspect(self, opportunity_id: str) -> Any:
        return self._loaded().inspect(opportunity_id)


__all__ = [
    "LancersDiscoveryError",
    "LancersSnapshotAdapter",
    "LancersSnapshotSource",
]
