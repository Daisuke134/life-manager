#!/usr/bin/env python3
"""Pure read-only adapter for the bounded Mercor pass result."""

from __future__ import annotations

from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import parse_qs, urlsplit


_PROVIDER_PATH = Path(__file__).resolve().parents[2] / "gig" / "scripts" / "provider_adapter.py"
_provider_spec = importlib.util.spec_from_file_location("mercor_provider_adapter", _PROVIDER_PATH)
if _provider_spec is None or _provider_spec.loader is None:
    raise RuntimeError("provider_adapter_unavailable")
_provider_module = importlib.util.module_from_spec(_provider_spec)
sys.modules[_provider_spec.name] = _provider_module
_provider_spec.loader.exec_module(_provider_module)
Opportunity = _provider_module.Opportunity
OpportunityDetail = _provider_module.OpportunityDetail


_LISTING_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$")
_JOB_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{0,255}$")
_OPPORTUNITY_ID = re.compile(r"^listing:(?P<listing_id>[A-Za-z0-9][A-Za-z0-9_-]{0,255})$")


class MercorDiscoveryError(ValueError):
    """The bounded Mercor pass result cannot safely produce a shared record."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError) as error:
        raise MercorDiscoveryError("listing_snapshot_unserializable") from error


def _text(value: Any, reason: str, *, max_length: int = 200_000) -> str:
    if not isinstance(value, str):
        raise MercorDiscoveryError(reason)
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text:
        raise MercorDiscoveryError(reason)
    return text


def _listing_id(value: Any) -> str:
    text = _text(value, "listing_id_invalid", max_length=256)
    if _LISTING_ID.fullmatch(text) is None:
        raise MercorDiscoveryError("listing_id_invalid")
    return text


def _canonical_url(value: Any, listing_id: str) -> str:
    raw = _text(value, "listing_url_invalid", max_length=2048)
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "work.mercor.com"
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise MercorDiscoveryError("listing_url_invalid")
    query = parse_qs(parsed.query, keep_blank_values=True)
    query_ids = query.get("listingId", [])
    if parsed.path == "/explore" and query_ids == [listing_id] and set(query) == {"listingId"}:
        return f"https://work.mercor.com/explore?listingId={listing_id}"
    if parsed.path == f"/jobs/{listing_id}" and not parsed.query:
        return f"https://work.mercor.com/jobs/{listing_id}"
    path_segments = parsed.path.split("/")
    if (
        not parsed.query
        and len(path_segments) >= 4
        and path_segments[1] == "jobs"
        and path_segments[2] == listing_id
        and all(_JOB_PATH_SEGMENT.fullmatch(segment) for segment in path_segments[3:])
    ):
        return f"https://work.mercor.com{parsed.path}"
    raise MercorDiscoveryError("listing_url_invalid")


def _observed_at(value: Any) -> str:
    text = _text(value, "observed_at_invalid", max_length=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as error:
        raise MercorDiscoveryError("observed_at_invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MercorDiscoveryError("observed_at_invalid")
    return text


def _evidence_text(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 64:
        raise MercorDiscoveryError("listing_evidence_invalid")
    result = []
    for item in value:
        result.append(_text(item, "listing_evidence_invalid", max_length=2048))
    return result


def _description(record: dict[str, Any], title: str) -> str:
    direct = record.get("description")
    if isinstance(direct, str) and direct.strip():
        return _text(direct, "listing_description_invalid")
    evidence = _evidence_text(record.get("ranking_evidence", []))
    requirements = record.get("requirement_evidence", [])
    if not isinstance(requirements, list) or len(requirements) > 64:
        raise MercorDiscoveryError("listing_requirements_invalid")
    requirement_lines = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise MercorDiscoveryError("listing_requirements_invalid")
        requirement_lines.append(_text(requirement.get("requirement"), "listing_requirements_invalid", max_length=2048))
        requirement_lines.append(_text(requirement.get("disposition"), "listing_requirements_invalid", max_length=2048))
    return _text("\n".join([title, *evidence, *requirement_lines]), "listing_description_invalid")


def _record(record: Any, *, default_currency: str, default_observed_at: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise MercorDiscoveryError("listing_record_invalid")
    listing_id = _listing_id(record.get("listing_id"))
    title = _text(record.get("title"), "listing_title_invalid", max_length=512)
    description = _description(record, title)
    url = _canonical_url(record.get("url"), listing_id)
    observed_at = _observed_at(record.get("observed_at") or default_observed_at)
    application_state = _text(record.get("application_state"), "listing_application_state_invalid", max_length=64)
    decision = _text(record.get("decision"), "listing_decision_invalid", max_length=128)
    provider_fit_status = _text(record.get("provider_fit_status"), "listing_fit_status_invalid", max_length=32)
    ranking_band = _text(record.get("ranking_band"), "listing_ranking_band_invalid", max_length=16)
    currency = record.get("currency") or default_currency
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isupper() or not currency.isalpha():
        raise MercorDiscoveryError("listing_currency_invalid")
    normalized = {
        "external_id": listing_id,
        "title": title,
        "description": description,
        "category": "mercor",
        "url": url,
        "observed_at": observed_at,
        "budget_type": "unknown",
        "currency": currency,
        "application_state": application_state,
        "decision": decision,
        "provider_fit_status": provider_fit_status,
        "ranking_band": ranking_band,
    }
    normalized["source_hash"] = hashlib.sha256(_canonical_bytes(normalized)).hexdigest()
    return normalized


def _opportunity(record: dict[str, Any]) -> Any:
    return Opportunity(
        provider="mercor",
        opportunity_id=f"listing:{record['external_id']}",
        source_url=record["url"],
        title=record["title"],
        currency=record["currency"],
        source_hash=record["source_hash"],
        observed_at=record["observed_at"],
    )


def _scope(record: dict[str, Any]) -> str:
    return "\n".join((
        f"案件名: {record['title']}",
        f"状態: {record['application_state']}",
        f"判断: {record['decision']}",
        f"適合: {record['provider_fit_status']}",
        f"優先度: {record['ranking_band']}",
        f"観測本文: {record['description']}",
    ))


def _validated_snapshot(snapshot: Any) -> tuple[list[dict[str, Any]], set[str]]:
    if not isinstance(snapshot, dict):
        raise MercorDiscoveryError("snapshot_invalid")
    if snapshot.get("ok") is not True or snapshot.get("platform") != "mercor":
        error = str(snapshot.get("error") or "snapshot_unavailable")
        raise MercorDiscoveryError(f"snapshot_unavailable:{error[:80]}")
    raw_records = snapshot.get("inspected_listings")
    if not isinstance(raw_records, list):
        raise MercorDiscoveryError("inspected_listings_invalid")
    observed_at = _observed_at(snapshot.get("observed_at"))
    raw_submitted = snapshot.get("submitted_listing_ids", [])
    if not isinstance(raw_submitted, list):
        raise MercorDiscoveryError("submitted_listing_ids_invalid")
    submitted = {_listing_id(value) for value in raw_submitted}
    default_currency = snapshot.get("currency") or "USD"
    if not isinstance(default_currency, str):
        raise MercorDiscoveryError("snapshot_currency_invalid")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_records:
        record = _record(raw, default_currency=default_currency, default_observed_at=observed_at)
        listing_id = record["external_id"]
        if listing_id in seen:
            raise MercorDiscoveryError("duplicate_listing_id")
        seen.add(listing_id)
        records.append(record)
        if record["application_state"] in {"submitted", "submitted_pending_review", "submitted_pending_review_observed"}:
            submitted.add(listing_id)
    return records, submitted


class MercorSnapshotAdapter:
    """Read-only adapter over one Mercor pass result."""

    def __init__(self, snapshot: dict[str, Any], *, max_items: int = 40):
        if type(max_items) is not int or not 1 <= max_items <= 100:
            raise MercorDiscoveryError("discovery_bound_invalid")
        self._snapshot = snapshot
        self._max_items = max_items

    def _records(self) -> tuple[list[dict[str, Any]], set[str]]:
        records, submitted = _validated_snapshot(self._snapshot)
        if len(records) > self._max_items:
            raise MercorDiscoveryError("discovery_bound_exceeded")
        return records, submitted

    def discover(self) -> list[Any]:
        records, submitted = self._records()
        return [_opportunity(record) for record in records if record["external_id"] not in submitted]

    def inspect(self, opportunity_id: str) -> Any:
        match = _OPPORTUNITY_ID.fullmatch(str(opportunity_id or "").strip())
        if match is None:
            raise MercorDiscoveryError("opportunity_id_invalid")
        listing_id = match.group("listing_id")
        records, submitted = self._records()
        if listing_id in submitted:
            raise MercorDiscoveryError("opportunity_already_applied")
        for record in records:
            if record["external_id"] == listing_id:
                opportunity = _opportunity(record)
                return OpportunityDetail(
                    opportunity=opportunity,
                    scope=_scope(record),
                    source_hash=record["source_hash"],
                )
        raise MercorDiscoveryError("opportunity_not_found")


class MercorSnapshotSource:
    """Inject one bounded Mercor pass result per natural wake."""

    def __init__(self, snapshot_loader: Any, *, max_items: int = 40):
        if not callable(snapshot_loader):
            raise MercorDiscoveryError("snapshot_loader_invalid")
        self._snapshot_loader = snapshot_loader
        self._max_items = max_items
        self._adapter: MercorSnapshotAdapter | None = None

    def _loaded(self) -> MercorSnapshotAdapter:
        if self._adapter is None:
            try:
                snapshot = self._snapshot_loader()
            except MercorDiscoveryError:
                raise
            except Exception as error:  # noqa: BLE001 - typed read-only boundary
                raise MercorDiscoveryError("snapshot_collect_failed") from error
            self._adapter = MercorSnapshotAdapter(snapshot, max_items=self._max_items)
        return self._adapter

    def discover(self) -> list[Any]:
        return self._loaded().discover()

    def inspect(self, opportunity_id: str) -> Any:
        return self._loaded().inspect(opportunity_id)


__all__ = ["MercorDiscoveryError", "MercorSnapshotAdapter", "MercorSnapshotSource"]
