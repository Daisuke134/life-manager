#!/usr/bin/env python3
"""Pure read-only CrowdWorks public-job adapter for the shared opportunity contract."""

from __future__ import annotations

from datetime import datetime
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
    "crowdworks_provider_adapter", _PROVIDER_PATH,
)
if _provider_spec is None or _provider_spec.loader is None:
    raise RuntimeError("provider_adapter_unavailable")
_provider_module = importlib.util.module_from_spec(_provider_spec)
sys.modules[_provider_spec.name] = _provider_module
_provider_spec.loader.exec_module(_provider_module)
Opportunity = _provider_module.Opportunity
OpportunityDetail = _provider_module.OpportunityDetail


_JOB_ID = re.compile(r"^[1-9][0-9]{0,511}$")
_OPPORTUNITY_ID = re.compile(r"^job:(?P<job_id>[1-9][0-9]{0,511})$")


class CrowdWorksDiscoveryError(ValueError):
    """The read-only CrowdWorks snapshot cannot safely produce a shared record."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CrowdWorksDiscoveryError("job_snapshot_unserializable") from error


def _text(value: Any, reason: str, *, max_length: int = 200_000) -> str:
    if not isinstance(value, str):
        raise CrowdWorksDiscoveryError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise CrowdWorksDiscoveryError(reason)
    return text


def _job_id(value: Any) -> str:
    text = _text(value, "job_id_invalid", max_length=512)
    if _JOB_ID.fullmatch(text) is None:
        raise CrowdWorksDiscoveryError("job_id_invalid")
    return text


def _canonical_url(value: Any, job_id: str) -> str:
    raw = _text(value, "job_url_invalid", max_length=2048)
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"crowdworks.jp", "www.crowdworks.jp"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.path != f"/public/jobs/{job_id}"
    ):
        raise CrowdWorksDiscoveryError("job_url_invalid")
    return f"https://crowdworks.jp/public/jobs/{job_id}"


def _observed_at(value: Any) -> str:
    text = _text(value, "observed_at_invalid", max_length=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as error:
        raise CrowdWorksDiscoveryError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CrowdWorksDiscoveryError("observed_at_invalid")
    return text


def _record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise CrowdWorksDiscoveryError("job_record_invalid")
    job_id = _job_id(record.get("external_id"))
    title = _text(record.get("title"), "job_title_invalid", max_length=512)
    description = _text(record.get("description"), "job_description_invalid")
    category = _text(record.get("category"), "job_category_invalid", max_length=512)
    url = _canonical_url(record.get("url"), job_id)
    observed_at = _observed_at(record.get("observed_at"))
    budget_type = _text(record.get("budget_type"), "job_budget_type_invalid", max_length=32)
    currency = record.get("currency") or "JPY"
    if currency != "JPY":
        raise CrowdWorksDiscoveryError("job_currency_invalid")
    normalized = {
        "external_id": job_id,
        "title": title,
        "description": description,
        "category": category,
        "url": url,
        "observed_at": observed_at,
        "budget_type": budget_type,
        "currency": "JPY",
    }
    normalized["source_hash"] = hashlib.sha256(_canonical_bytes(normalized)).hexdigest()
    return normalized


def _opportunity(record: dict[str, Any]) -> Any:
    return Opportunity(
        provider="crowdworks",
        opportunity_id=f"job:{record['external_id']}",
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
        raise CrowdWorksDiscoveryError("snapshot_invalid")
    if snapshot.get("ok") is not True or snapshot.get("platform") != "crowdworks":
        error = str(snapshot.get("error") or "snapshot_unavailable")
        raise CrowdWorksDiscoveryError(f"snapshot_unavailable:{error[:80]}")
    raw_records = snapshot.get("opportunities")
    if not isinstance(raw_records, list):
        raise CrowdWorksDiscoveryError("opportunities_invalid")
    raw_applied = snapshot.get("already_applied_ids", [])
    if not isinstance(raw_applied, list):
        raise CrowdWorksDiscoveryError("already_applied_ids_invalid")
    applied = {_job_id(value) for value in raw_applied}
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_records:
        record = _record(raw)
        job_id = record["external_id"]
        if job_id in seen:
            raise CrowdWorksDiscoveryError("duplicate_job_id")
        seen.add(job_id)
        records.append(record)
    return records, applied


class CrowdWorksSnapshotAdapter:
    """Read-only adapter over one bounded application-owner snapshot."""

    def __init__(self, snapshot: dict[str, Any], *, max_items: int = 40):
        if type(max_items) is not int or not 1 <= max_items <= 100:
            raise CrowdWorksDiscoveryError("discovery_bound_invalid")
        self._snapshot = snapshot
        self._max_items = max_items

    def _records(self) -> tuple[list[dict[str, Any]], set[str]]:
        records, applied = _validated_snapshot(self._snapshot)
        if len(records) > self._max_items:
            raise CrowdWorksDiscoveryError("discovery_bound_exceeded")
        return records, applied

    def discover(self) -> list[Any]:
        records, applied = self._records()
        return [_opportunity(record) for record in records if record["external_id"] not in applied]

    def inspect(self, opportunity_id: str) -> Any:
        match = _OPPORTUNITY_ID.fullmatch(str(opportunity_id or "").strip())
        if match is None:
            raise CrowdWorksDiscoveryError("opportunity_id_invalid")
        job_id = match.group("job_id")
        records, applied = self._records()
        if job_id in applied:
            raise CrowdWorksDiscoveryError("opportunity_already_applied")
        for record in records:
            if record["external_id"] == job_id:
                opportunity = _opportunity(record)
                return OpportunityDetail(
                    opportunity=opportunity,
                    scope=_scope(record),
                    source_hash=record["source_hash"],
                )
        raise CrowdWorksDiscoveryError("opportunity_not_found")


class CrowdWorksSnapshotSource:
    """Inject one existing read-only CrowdWorks snapshot per natural wake."""

    def __init__(self, snapshot_loader: Any, *, max_items: int = 40):
        if not callable(snapshot_loader):
            raise CrowdWorksDiscoveryError("snapshot_loader_invalid")
        self._snapshot_loader = snapshot_loader
        self._max_items = max_items
        self._adapter: CrowdWorksSnapshotAdapter | None = None

    def _loaded(self) -> CrowdWorksSnapshotAdapter:
        if self._adapter is None:
            try:
                snapshot = self._snapshot_loader()
            except CrowdWorksDiscoveryError:
                raise
            except Exception as error:  # noqa: BLE001 - typed read-only boundary
                raise CrowdWorksDiscoveryError("snapshot_collect_failed") from error
            self._adapter = CrowdWorksSnapshotAdapter(snapshot, max_items=self._max_items)
        return self._adapter

    def discover(self) -> list[Any]:
        return self._loaded().discover()

    def inspect(self, opportunity_id: str) -> Any:
        return self._loaded().inspect(opportunity_id)


__all__ = [
    "CrowdWorksDiscoveryError",
    "CrowdWorksSnapshotAdapter",
    "CrowdWorksSnapshotSource",
]
