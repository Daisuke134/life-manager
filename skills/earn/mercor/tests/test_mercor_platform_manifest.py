from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills" / "earn" / "mercor" / "scripts"
CORE_SCRIPTS = ROOT / "skills" / "_shared" / "marketplace-core" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load(SCRIPTS / "mercor_platform_manifest.py", "mercor_platform_manifest_test")
enrollment = _load(CORE_SCRIPTS / "platform_enrollment.py", "mercor_manifest_enrollment_test")
candidate_store_module = _load(
    CORE_SCRIPTS / "platform_candidate_store.py", "mercor_manifest_candidate_store_test"
)
run_store_module = _load(
    CORE_SCRIPTS / "meta_loop_run_store.py", "mercor_manifest_run_store_test"
)


def _snapshot() -> dict[str, object]:
    return {
        "version": 1,
        "platform": "mercor",
        "observed_at": "2026-09-30T05:00:00Z",
        "source_url": "https://work.mercor.com/home",
        "adapter_source_sha256": "a" * 64,
        "account_id": "gmail-owner@example.com",
        "source_complete": True,
        "gmail_status": "fresh",
        "contract_readback": True,
        "evidence_refs": ["mercor://account/observed-1"],
    }


def test_mercor_platform_source_maps_source_health_only():
    source = module.MercorPlatformManifestSource(_snapshot)

    [item] = source.discover()

    assert item["source_kind"] == "platform"
    assert item["candidate_id"] == "platform:mercor"
    assert item["candidate"]["provider"] == "mercor"
    assert item["candidate"]["policy"]["status"] == "unknown"
    assert item["candidate"]["funded_work"]["status"] == "unknown"
    assert "applications" not in item


def test_mercor_platform_source_rejects_listing_snapshot():
    source = module.MercorPlatformManifestSource(
        lambda: {**_snapshot(), "inspected_listings": []}
    )

    with pytest.raises(module.MercorPlatformManifestError, match="opportunity_snapshot_rejected"):
        source.discover()


def test_mercor_platform_source_enters_candidate_cycle_as_hold(tmp_path):
    source = module.MercorPlatformManifestSource(_snapshot)
    store = candidate_store_module.CandidateStateStore(tmp_path / "candidates")

    summary = enrollment.run_discovery_cycle(
        {"mercor-platform": source.discover},
        store,
    )

    assert summary["status"] == "ok"
    assert summary["inspected"] == 1
    assert summary["promoted"] == 0
    assert summary["held"] == 1
    assert store.latest("mercor", "platform:mercor")["decision"] == "hold"


def test_mercor_platform_source_persists_meta_loop_wake_summary(tmp_path):
    source = module.MercorPlatformManifestSource(_snapshot)
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")

    result = enrollment.run_meta_loop_wake(
        {"mercor-platform": source.discover},
        candidates,
        runs,
        run_id="mercor-wake-1",
        observed_at="2026-09-30T05:01:00Z",
    )

    assert result["status"] == "ok"
    assert result["held"] == 1
    assert runs.latest("mercor-wake-1")["held"] == 1

