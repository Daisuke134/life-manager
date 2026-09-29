from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills" / "earn" / "lancers" / "scripts"
CORE_SCRIPTS = ROOT / "skills" / "_shared" / "marketplace-core" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load(SCRIPTS / "lancers_platform_manifest.py", "lancers_platform_manifest_test")
enrollment = _load(CORE_SCRIPTS / "platform_enrollment.py", "lancers_manifest_enrollment_test")
candidate_store_module = _load(
    CORE_SCRIPTS / "platform_candidate_store.py", "lancers_manifest_candidate_store_test"
)
run_store_module = _load(
    CORE_SCRIPTS / "meta_loop_run_store.py", "lancers_manifest_run_store_test"
)


def _snapshot() -> dict[str, object]:
    return {
        "version": 1,
        "platform": "lancers",
        "observed_at": "2026-09-30T03:00:00Z",
        "source_url": "https://www.lancers.jp/mypage",
        "adapter_source_sha256": "a" * 64,
        "logged_in": True,
        "source_complete": True,
        "board_count": 2,
        "required_reply_count": 0,
        "unread_count": 0,
        "evidence_refs": ["lancers://work-sync/observed-1"],
    }


def test_lancers_platform_source_maps_account_state_only():
    source = module.LancersPlatformManifestSource(_snapshot)

    [item] = source.discover()

    assert item["source_kind"] == "platform"
    assert item["candidate_id"] == "platform:lancers"
    assert item["candidate"]["provider"] == "lancers"
    assert item["candidate"]["policy"]["status"] == "unknown"
    assert item["candidate"]["funded_work"]["status"] == "unknown"
    assert "opportunities" not in item


def test_lancers_platform_source_rejects_public_opportunity_snapshot():
    source = module.LancersPlatformManifestSource(
        lambda: {**_snapshot(), "opportunities": []}
    )

    with pytest.raises(module.LancersPlatformManifestError, match="opportunity_snapshot_rejected"):
        source.discover()


def test_lancers_platform_source_enters_candidate_cycle_as_hold(tmp_path):
    source = module.LancersPlatformManifestSource(_snapshot)
    store = candidate_store_module.CandidateStateStore(tmp_path / "candidates")

    summary = enrollment.run_discovery_cycle(
        {"lancers-platform": source.discover},
        store,
    )

    assert summary["status"] == "ok"
    assert summary["inspected"] == 1
    assert summary["promoted"] == 0
    assert summary["held"] == 1
    assert store.latest("lancers", "platform:lancers")["decision"] == "hold"


def test_lancers_platform_source_persists_meta_loop_wake_summary(tmp_path):
    source = module.LancersPlatformManifestSource(_snapshot)
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")

    result = enrollment.run_meta_loop_wake(
        {"lancers-platform": source.discover},
        candidates,
        runs,
        run_id="lancers-wake-1",
        observed_at="2026-09-30T03:01:00Z",
    )

    assert result["status"] == "ok"
    assert result["held"] == 1
    assert runs.latest("lancers-wake-1")["held"] == 1

