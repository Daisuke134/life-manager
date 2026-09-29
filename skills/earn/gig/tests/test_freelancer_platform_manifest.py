from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills" / "earn" / "gig" / "scripts"
CORE = ROOT / "skills" / "_shared" / "marketplace-core" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load(SCRIPTS / "freelancer_platform_manifest.py", "freelancer_manifest_test")
enrollment = _load(CORE / "platform_enrollment.py", "freelancer_manifest_enrollment_test")
candidate_store_module = _load(
    CORE / "platform_candidate_store.py", "freelancer_manifest_candidate_store_test"
)


def _observation() -> dict[str, object]:
    return {
        "version": 1,
        "platform": "freelancer",
        "observed_at": "2026-09-30T05:00:00Z",
        "source_url": "https://www.freelancer.com/dashboard",
        "adapter_source_sha256": "a" * 64,
        "authenticated": True,
        "source_complete": False,
        "profile_readback": True,
        "account_id_sha256": "b" * 64,
        "evidence_refs": ["freelancer://run/read-only-1"],
        "inventory_evidence_sha256": {
            "identity": "c" * 64,
            "projects": "d" * 64,
            "payments": "e" * 64,
            "payouts": "f" * 64,
        },
    }


def test_freelancer_platform_source_maps_account_state_and_holds_policy():
    source = module.FreelancerPlatformManifestSource(_observation)

    [item] = source.discover()

    assert item["source_kind"] == "platform"
    assert item["candidate_id"] == "platform:freelancer"
    assert item["candidate"]["provider"] == "freelancer"
    assert item["candidate"]["policy"]["status"] == "unknown"
    assert item["candidate"]["funded_work"]["status"] == "unknown"
    assert "account_id_sha256" not in item


def test_freelancer_platform_source_enters_meta_loop_as_hold(tmp_path):
    source = module.FreelancerPlatformManifestSource(_observation)
    store = candidate_store_module.CandidateStateStore(tmp_path / "candidates")

    summary = enrollment.run_discovery_cycle(
        {"freelancer-platform": source.discover}, store,
    )

    assert summary["status"] == "ok"
    assert summary["inspected"] == 1
    assert summary["promoted"] == 0
    assert summary["held"] == 1
    assert store.latest("freelancer", "platform:freelancer")["decision"] == "hold"


def test_freelancer_platform_source_rejects_project_payload():
    source = module.FreelancerPlatformManifestSource(
        lambda: {**_observation(), "projects": []}
    )

    with pytest.raises(module.FreelancerPlatformManifestError, match="opportunity_snapshot_rejected"):
        source.discover()


def test_freelancer_live_builder_projects_hashes_only():
    state = {
        "version": 1,
        "provider": "freelancer",
        "observed_at": "2026-09-30T05:01:00Z",
        "evidence_sha256": {
            "identity": "c" * 64,
            "projects": "d" * 64,
            "payments": "e" * 64,
            "payouts": "f" * 64,
            "profile": "1" * 64,
        },
        "contracts": [{"id": "private-contract-body"}],
    }

    snapshot = module.build_live_snapshot(
        state,
        account_id="private-account-id",
        adapter_source_sha256="a" * 64,
    )

    assert snapshot["profile_readback"] is True
    assert snapshot["account_id_sha256"] != "private-account-id"
    assert "private-account-id" not in repr(snapshot)
    assert "private-contract-body" not in repr(snapshot)
