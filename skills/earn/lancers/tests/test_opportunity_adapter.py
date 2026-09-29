from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
MODULE_PATH = SCRIPTS / "opportunity_adapter.py"
RUNNER_PATH = Path(__file__).resolve().parents[3] / "_shared" / "marketplace-core" / "scripts" / "opportunity_discovery.py"
STORE_PATH = Path(__file__).resolve().parents[3] / "_shared" / "marketplace-core" / "scripts" / "opportunity_observation_store.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load(MODULE_PATH, "lancers_opportunity_adapter_test")
runner = _load(RUNNER_PATH, "lancers_opportunity_runner_test")
store_module = _load(STORE_PATH, "lancers_opportunity_store_test")


def _record(external_id: str = "123"):
    return {
        "schema_version": 1,
        "record_type": "opportunity",
        "platform": "lancers",
        "external_id": external_id,
        "title": "業務自動化案件",
        "description": "業務フローを自動化する案件です。",
        "url": f"https://www.lancers.jp/work/detail/{external_id}",
        "category": "システム開発",
        "budget_type": "fixed",
        "budget_min_minor": 10000,
        "budget_max_minor": 50000,
        "currency": "JPY",
        "buyer_external_id": "client-1",
        "observed_at": "2026-09-30T12:00:00Z",
    }


def _snapshot(*, already_applied_ids=None):
    records = [_record()]
    return {
        "ok": True,
        "platform": "lancers",
        "source": "public_html",
        "provider_count": len(records),
        "normalized_count": len(records),
        "rejected_count": 0,
        "detail_enriched_count": len(records),
        "detail_failed_count": 0,
        "opportunities": records,
        "already_applied_ids": list(already_applied_ids or []),
    }


def test_lancers_snapshot_adapter_returns_open_unapplied_shared_opportunity():
    [opportunity] = adapter.LancersSnapshotAdapter(_snapshot()).discover()

    assert opportunity.provider == "lancers"
    assert opportunity.opportunity_id == "project:123"
    assert opportunity.source_url == "https://www.lancers.jp/work/detail/123"
    assert opportunity.currency == "JPY"
    assert opportunity.title == "業務自動化案件"


def test_lancers_snapshot_inspect_is_identity_and_hash_bound():
    document = _snapshot()
    read_only = adapter.LancersSnapshotAdapter(document)

    [opportunity] = read_only.discover()
    detail = read_only.inspect(opportunity.opportunity_id)

    assert detail.opportunity == opportunity
    assert "業務フロー" in detail.scope
    assert detail.source_hash == opportunity.source_hash


def test_lancers_snapshot_adapter_filters_already_applied_ids():
    assert adapter.LancersSnapshotAdapter(
        _snapshot(already_applied_ids=["123"])
    ).discover() == []


def test_lancers_snapshot_source_loads_once_and_maps_collector_failure():
    calls = 0

    def load_snapshot():
        nonlocal calls
        calls += 1
        return _snapshot()

    source = adapter.LancersSnapshotSource(load_snapshot)
    [opportunity] = source.discover()
    assert source.inspect(opportunity.opportunity_id).opportunity == opportunity
    assert calls == 1

    failing = adapter.LancersSnapshotSource(lambda: (_ for _ in ()).throw(RuntimeError("WAF")))
    with pytest.raises(adapter.LancersDiscoveryError, match="snapshot_collect_failed"):
        failing.discover()


def test_lancers_adapter_feeds_shared_runner(tmp_path):
    source = adapter.LancersSnapshotSource(lambda: _snapshot())
    store = store_module.OpportunityObservationStore(tmp_path / "observations")

    result = runner.run_opportunity_discovery(
        source,
        lambda _opportunity, _detail: {
            "decision": "hold",
            "reasons": ["workflow_not_evaluated"],
            "evidence_refs": ["snapshot://lancers/test"],
            "next_action": "evaluate_workflow",
        },
        store,
    )

    assert result["inspected"] == 1
    assert result["held"] == 1
    assert store.latest("lancers", "project:123")["decision"] == "hold"
