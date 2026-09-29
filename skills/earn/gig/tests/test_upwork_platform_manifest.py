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


module = _load(SCRIPTS / "upwork_platform_manifest.py", "upwork_manifest_test")
enrollment = _load(CORE / "platform_enrollment.py", "upwork_manifest_enrollment_test")
candidate_store_module = _load(
    CORE / "platform_candidate_store.py", "upwork_manifest_candidate_store_test"
)


def _observation() -> dict[str, object]:
    return {
        "version": 1,
        "platform": "upwork",
        "observed_at": "2026-09-30T04:00:00Z",
        "source_url": "https://www.upwork.com/nx/wm/freelancer/home",
        "adapter_source_sha256": "a" * 64,
        "authenticated": True,
        "source_complete": True,
        "profile_readback": True,
        "account_id_sha256": "b" * 64,
        "evidence_refs": ["upwork://run/read-only-1"],
        "inventory_evidence_sha256": {
            "contracts": "c" * 64,
            "transactions": "d" * 64,
            "withdrawals": "e" * 64,
        },
    }


def test_upwork_platform_source_maps_account_state_and_holds_gates():
    source = module.UpworkPlatformManifestSource(_observation)

    [item] = source.discover()

    assert item["source_kind"] == "platform"
    assert item["candidate_id"] == "platform:upwork"
    assert item["candidate"]["provider"] == "upwork"
    assert item["candidate"]["funded_work"]["status"] == "unknown"
    assert item["candidate"]["canary"]["official_receipt_ref"] is None
    assert "account_id_sha256" not in item
    assert "inventory_evidence_sha256" not in item


def test_upwork_platform_source_enters_meta_loop_as_hold(tmp_path):
    source = module.UpworkPlatformManifestSource(_observation)
    store = candidate_store_module.CandidateStateStore(tmp_path / "candidates")

    summary = enrollment.run_discovery_cycle({"upwork-platform": source.discover}, store)

    assert summary["status"] == "ok"
    assert summary["inspected"] == 1
    assert summary["promoted"] == 0
    assert summary["held"] == 1
    assert store.latest("upwork", "platform:upwork")["decision"] == "hold"


def test_upwork_platform_source_rejects_contract_or_job_payloads():
    source = module.UpworkPlatformManifestSource(
        lambda: {**_observation(), "jobs": []}
    )

    with pytest.raises(module.UpworkPlatformManifestError, match="opportunity_snapshot_rejected"):
        source.discover()


def test_upwork_live_builder_projects_only_hashes():
    state = {
        "version": 1,
        "provider": "upwork",
        "observed_at": "2026-09-30T04:01:00Z",
        "evidence_sha256": {
            "contracts": "c" * 64,
            "transactions": "d" * 64,
            "withdrawals": "e" * 64,
            "working-style": "f" * 64,
        },
        "active_contracts": [{"id": "contract-secret-body"}],
    }

    snapshot = module.build_live_snapshot(
        state,
        account_id="account-secret",
        adapter_source_sha256="a" * 64,
    )

    assert snapshot["source_complete"] is True
    assert snapshot["profile_readback"] is True
    assert snapshot["account_id_sha256"] != "account-secret"
    assert "account-secret" not in repr(snapshot)
    assert "contract-secret-body" not in repr(snapshot)


def test_upwork_live_builder_rejects_missing_inventory_hash():
    state = {
        "version": 1,
        "provider": "upwork",
        "observed_at": "2026-09-30T04:01:00Z",
        "evidence_sha256": {"contracts": "c" * 64},
    }

    with pytest.raises(module.UpworkPlatformManifestError, match="inventory_evidence_invalid"):
        module.build_live_snapshot(
            state,
            account_id="account-secret",
            adapter_source_sha256="a" * 64,
        )
