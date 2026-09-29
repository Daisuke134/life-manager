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


adapter = _load(MODULE_PATH, "crowdworks_opportunity_adapter_test")


def _record(external_id: str = "123") -> dict[str, object]:
    return {
        "external_id": external_id,
        "title": "業務自動化の案件",
        "description": "公開案件本文です。",
        "category": "システム開発",
        "url": f"https://crowdworks.jp/public/jobs/{external_id}",
        "observed_at": "2026-09-30T10:00:00Z",
        "budget_type": "fixed",
        "currency": "JPY",
    }


def _snapshot() -> dict[str, object]:
    return {
        "ok": True,
        "platform": "crowdworks",
        "observed_at": "2026-09-30T10:00:00Z",
        "opportunities": [_record()],
        "already_applied_ids": [],
    }


def test_crowdworks_snapshot_discovery_maps_public_job_to_shared_opportunity():
    [opportunity] = adapter.CrowdWorksSnapshotAdapter(_snapshot()).discover()

    assert opportunity.provider == "crowdworks"
    assert opportunity.opportunity_id == "job:123"
    assert opportunity.source_url == "https://crowdworks.jp/public/jobs/123"
    assert opportunity.currency == "JPY"
    assert opportunity.title == "業務自動化の案件"


def test_crowdworks_snapshot_inspect_binds_scope_and_source_hash():
    source = adapter.CrowdWorksSnapshotAdapter(_snapshot())

    [opportunity] = source.discover()
    detail = source.inspect(opportunity.opportunity_id)

    assert detail.opportunity == opportunity
    assert "公開案件本文です。" in detail.scope
    assert detail.source_hash == opportunity.source_hash


def test_already_applied_job_is_not_discoverable_or_inspectable():
    snapshot = _snapshot()
    snapshot["already_applied_ids"] = ["123"]
    source = adapter.CrowdWorksSnapshotAdapter(snapshot)

    assert source.discover() == []
    with pytest.raises(adapter.CrowdWorksDiscoveryError, match="opportunity_already_applied"):
        source.inspect("job:123")


def test_snapshot_source_loads_once_and_maps_collection_failure():
    calls = 0

    def load_snapshot():
        nonlocal calls
        calls += 1
        return _snapshot()

    source = adapter.CrowdWorksSnapshotSource(load_snapshot)
    [opportunity] = source.discover()
    assert source.inspect(opportunity.opportunity_id).opportunity == opportunity
    assert calls == 1

    failing = adapter.CrowdWorksSnapshotSource(
        lambda: (_ for _ in ()).throw(RuntimeError("browser unavailable"))
    )
    with pytest.raises(adapter.CrowdWorksDiscoveryError, match="snapshot_collect_failed"):
        failing.discover()


def test_invalid_snapshot_and_duplicate_job_fail_closed():
    with pytest.raises(adapter.CrowdWorksDiscoveryError, match="snapshot_invalid"):
        adapter.CrowdWorksSnapshotAdapter(None).discover()

    duplicate = _snapshot()
    duplicate["opportunities"] = [_record(), _record()]
    with pytest.raises(adapter.CrowdWorksDiscoveryError, match="duplicate_job_id"):
        adapter.CrowdWorksSnapshotAdapter(duplicate).discover()
