from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
MODULE_PATH = SCRIPTS / "opportunity_adapter.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load(MODULE_PATH, "mercor_opportunity_adapter_test")


def _listing(listing_id: str = "list_123") -> dict[str, object]:
    return {
        "listing_id": listing_id,
        "url": f"https://work.mercor.com/explore?listingId={listing_id}",
        "title": "AI automation engineer",
        "application_state": "card_only",
        "submit_visible": False,
        "decision": "card_only_unverified",
        "ranking_band": "medium",
        "ranking_evidence": ["AI automation overlap"],
        "provider_fit_status": "allowed",
        "requirement_evidence": [],
        "strategy_version": "mercor-fit-evidence-v1",
    }


def _snapshot() -> dict[str, object]:
    return {
        "ok": True,
        "platform": "mercor",
        "observed_at": "2026-09-30T10:00:00Z",
        "inspected_listings": [_listing()],
        "submitted_listing_ids": [],
    }


def test_mercor_pass_snapshot_maps_listing_to_shared_opportunity():
    [opportunity] = adapter.MercorSnapshotAdapter(_snapshot()).discover()

    assert opportunity.provider == "mercor"
    assert opportunity.opportunity_id == "listing:list_123"
    assert opportunity.source_url == "https://work.mercor.com/explore?listingId=list_123"
    assert opportunity.currency == "USD"
    assert opportunity.title == "AI automation engineer"


def test_mercor_snapshot_inspect_binds_observed_scope_and_hash():
    source = adapter.MercorSnapshotAdapter(_snapshot())
    [opportunity] = source.discover()

    detail = source.inspect(opportunity.opportunity_id)

    assert detail.opportunity == opportunity
    assert "AI automation engineer" in detail.scope
    assert "AI automation overlap" in detail.scope
    assert detail.source_hash == opportunity.source_hash


def test_submitted_listing_is_excluded_and_cannot_be_inspected():
    snapshot = _snapshot()
    snapshot["submitted_listing_ids"] = ["list_123"]
    source = adapter.MercorSnapshotAdapter(snapshot)

    assert source.discover() == []
    with pytest.raises(adapter.MercorDiscoveryError, match="opportunity_already_applied"):
        source.inspect("listing:list_123")


def test_snapshot_source_loads_once_and_maps_failure():
    calls = 0

    def load_snapshot():
        nonlocal calls
        calls += 1
        return _snapshot()

    source = adapter.MercorSnapshotSource(load_snapshot)
    [opportunity] = source.discover()
    assert source.inspect(opportunity.opportunity_id).opportunity == opportunity
    assert calls == 1

    failing = adapter.MercorSnapshotSource(
        lambda: (_ for _ in ()).throw(RuntimeError("pass unavailable"))
    )
    with pytest.raises(adapter.MercorDiscoveryError, match="snapshot_collect_failed"):
        failing.discover()


def test_invalid_provider_url_fails_closed():
    snapshot = _snapshot()
    snapshot["inspected_listings"] = [{**_listing(), "url": "https://example.com/job/list_123"}]
    with pytest.raises(adapter.MercorDiscoveryError, match="listing_url_invalid"):
        adapter.MercorSnapshotAdapter(snapshot).discover()


def test_slugged_job_url_preserves_listing_identity():
    snapshot = _snapshot()
    snapshot["inspected_listings"] = [{
        **_listing(),
        "url": "https://work.mercor.com/jobs/list_123/software-evaluator",
    }]

    [opportunity] = adapter.MercorSnapshotAdapter(snapshot).discover()

    assert opportunity.source_url == "https://work.mercor.com/jobs/list_123/software-evaluator"
