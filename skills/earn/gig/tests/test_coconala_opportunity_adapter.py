from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
MODULE_PATH = SCRIPTS / "coconala_opportunity_adapter.py"
SNAPSHOT_PATH = SCRIPTS / "application_snapshot.py"
STORE_PATH = Path(__file__).resolve().parents[3] / "_shared" / "marketplace-core" / "scripts" / "opportunity_observation_store.py"
RUNNER_PATH = Path(__file__).resolve().parents[3] / "_shared" / "marketplace-core" / "scripts" / "opportunity_discovery.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load(MODULE_PATH, "coconala_opportunity_adapter_test")
snapshot = _load(SNAPSHOT_PATH, "coconala_application_snapshot_for_adapter_test")
observation_store = _load(STORE_PATH, "coconala_observation_store_for_adapter_test")
discovery_runner = _load(RUNNER_PATH, "coconala_discovery_runner_for_adapter_test")
ULID = "01KYPJ0M0ACF4DBAFSJVFN9K24"


def _source(source_id: str, url: str, card_request_ids: list[str]):
    return {
        "source_id": source_id,
        "url": url,
        "page_index": 1,
        "card_request_ids": card_request_ids,
        "has_next": False,
        "exhausted": True,
        "screenshot_sha256": "a" * 64,
        "dom_sha256": "b" * 64,
    }


def _detail(request_id: str, canonical_url: str, *, accepting=True):
    return {
        "request_id": request_id,
        "canonical_url": canonical_url,
        "title": f"案件 {request_id}",
        "category": "記事作成",
        "visible_text": "募集内容\n本文",
        "accepting_applications": accepting,
        "budget_min_jpy": 1000,
        "budget_max_jpy": 5000,
        "applicants_count": 0,
        "contracted_count": 0,
        "applicants": [],
        "application_questions": [],
        "observed_at": "2026-09-14T10:00:00Z",
    }


def _snapshot():
    collector = {
        "pass_id": "pass-1",
        "lease_fence": {"task": "gig", "token": "a" * 32, "generation": 1},
        "observed_at": "2026-09-14T10:00:00Z",
        "objective": {
            "target_applications": 1,
            "max_applications": 2,
            "required_search_source_ids": ["single:new"],
        },
        "search_sources": [_source(
            "single:new", "https://www.coconala.com/requests?sort=new", ["2", ULID]
        )],
        "request_details": [
            _detail("2", "https://coconala.com/requests/2"),
            _detail(
                ULID,
                f"https://coconala.com/job_matching/outsources/{ULID}",
                accepting=False,
            ),
        ],
        "already_applied_ids": [ULID],
    }
    return snapshot.build_envelope(collector)


def test_coconala_snapshot_discovery_returns_only_open_unapplied_opportunities():
    found = adapter.opportunities_from_snapshot(_snapshot())

    assert len(found) == 1
    opportunity = found[0]
    assert opportunity.provider == "coconala"
    assert opportunity.opportunity_id == "request:2"
    assert opportunity.source_url == "https://coconala.com/requests/2"
    assert opportunity.currency == "JPY"
    assert opportunity.title == "案件 2"


def test_coconala_snapshot_inspect_binds_scope_and_content_hash():
    document = _snapshot()
    detail = adapter.inspect_from_snapshot(document, "request:2")

    assert detail.opportunity.opportunity_id == "request:2"
    assert detail.scope == "募集内容\n本文"
    assert detail.source_hash == document["request_details"][0]["content_sha256"]


def test_snapshot_adapter_exposes_read_only_discover_and_inspect_methods():
    read_only = adapter.CoconalaSnapshotAdapter(_snapshot())

    [opportunity] = read_only.discover()
    inspected = read_only.inspect(opportunity.opportunity_id)

    assert inspected.opportunity == opportunity


def test_invalid_snapshot_or_unknown_opportunity_fails_closed():
    with pytest.raises(adapter.CoconalaDiscoveryError, match="snapshot_invalid"):
        adapter.opportunities_from_snapshot({})
    with pytest.raises(adapter.CoconalaDiscoveryError, match="opportunity_not_found"):
        adapter.inspect_from_snapshot(_snapshot(), "request:999")


def test_coconala_adapter_feeds_the_shared_read_only_runner(tmp_path):
    read_only = adapter.CoconalaSnapshotSource(lambda: _snapshot())
    store = observation_store.OpportunityObservationStore(tmp_path / "observations")

    result = discovery_runner.run_opportunity_discovery(
        read_only,
        lambda _opportunity, _detail: {
            "decision": "hold",
            "reasons": ["workflow_not_evaluated"],
            "evidence_refs": ["snapshot://coconala/pass-1"],
            "next_action": "evaluate_workflow",
        },
        store,
    )

    assert result["inspected"] == 1
    assert result["held"] == 1
    assert store.latest("coconala", "request:2")["next_action"] == "evaluate_workflow"


def test_snapshot_source_loads_the_authenticated_snapshot_once_per_wake():
    calls = 0

    def load_snapshot():
        nonlocal calls
        calls += 1
        return _snapshot()

    source = adapter.CoconalaSnapshotSource(load_snapshot)

    [opportunity] = source.discover()
    inspected = source.inspect(opportunity.opportunity_id)

    assert inspected.opportunity == opportunity
    assert calls == 1


def test_snapshot_source_maps_collector_failure_to_read_only_error():
    def load_snapshot():
        raise RuntimeError("browser session unavailable")

    source = adapter.CoconalaSnapshotSource(load_snapshot)

    with pytest.raises(adapter.CoconalaDiscoveryError, match="snapshot_collect_failed"):
        source.discover()
