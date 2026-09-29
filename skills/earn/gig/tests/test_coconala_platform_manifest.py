from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills" / "earn" / "gig" / "scripts"
CORE_SCRIPTS = ROOT / "skills" / "_shared" / "marketplace-core" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load(SCRIPTS / "coconala_platform_manifest.py", "coconala_platform_manifest_test")
enrollment = _load(CORE_SCRIPTS / "platform_enrollment.py", "coconala_manifest_enrollment_test")
candidate_store_module = _load(
    CORE_SCRIPTS / "platform_candidate_store.py", "coconala_manifest_candidate_store_test"
)
run_store_module = _load(
    CORE_SCRIPTS / "meta_loop_run_store.py", "coconala_manifest_run_store_test"
)


STATES = (
    "preflight", "authenticated", "email_verified", "sms_verified",
    "seller_information", "identity_approved", "bank_registered",
    "launchd_readback", "storefront_listing_readback",
)


def _snapshot() -> dict[str, object]:
    return {
        "version": 2,
        "platform": "coconala",
        "observed_at": "2026-09-30T02:00:00Z",
        "source_url": "https://coconala.com/mypage",
        "adapter_source_sha256": "a" * 64,
        "evidence_refs": ["coconala://onboarding/observed-1"],
        "onboarding": {
            "version": 2,
            "platform": "coconala",
            "states": {
                state: {
                    "status": "complete" if state == "authenticated" else "pending",
                    "evidence_sha256": "b" * 64 if state == "authenticated" else None,
                }
                for state in STATES
            },
        },
    }


def _live_snapshot() -> dict[str, object]:
    return {
        "version": 2,
        "platform": "coconala",
        "observed_at": "2026-09-30T03:00:00Z",
        "source_url": "https://coconala.com/mypage",
        "adapter_source_sha256": "a" * 64,
        "evidence_refs": ["coconala://live/snapshot/" + "c" * 64],
        "live_account": {
            "version": 1,
            "authenticated": True,
            "source_complete": True,
            "profile_readback": True,
            "account_id_sha256": "d" * 64,
        },
    }


def test_coconala_platform_source_maps_onboarding_without_promoting_gates():
    source = module.CoconalaPlatformManifestSource(_snapshot)

    [item] = source.discover()

    assert item["source_kind"] == "platform"
    assert item["candidate_id"] == "platform:coconala"
    assert item["candidate"]["provider"] == "coconala"
    assert item["candidate"]["policy"]["status"] == "unknown"
    assert item["candidate"]["funded_work"]["status"] == "unknown"
    assert item["candidate"]["canary"]["official_receipt_ref"] is None
    assert "opportunities" not in item


def test_coconala_platform_source_rejects_opportunity_snapshot():
    source = module.CoconalaPlatformManifestSource(
        lambda: {**_snapshot(), "request_details": []}
    )

    with pytest.raises(module.CoconalaPlatformManifestError, match="opportunity_snapshot_rejected"):
        source.discover()


def test_coconala_platform_source_enters_candidate_cycle_as_hold(tmp_path):
    source = module.CoconalaPlatformManifestSource(_snapshot)
    store = candidate_store_module.CandidateStateStore(tmp_path / "candidates")

    summary = enrollment.run_discovery_cycle(
        {"coconala-platform": source.discover},
        store,
    )

    assert summary["status"] == "ok"
    assert summary["inspected"] == 1
    assert summary["promoted"] == 0
    assert summary["held"] == 1
    record = store.latest("coconala", "platform:coconala")
    assert record["decision"] == "hold"
    assert record["next_action"] == "collect_missing_gates"


def test_coconala_platform_source_persists_meta_loop_wake_summary(tmp_path):
    source = module.CoconalaPlatformManifestSource(_snapshot)
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")

    result = enrollment.run_meta_loop_wake(
        {"coconala-platform": source.discover},
        candidates,
        runs,
        run_id="coconala-wake-1",
        observed_at="2026-09-30T02:01:00Z",
    )

    assert result["status"] == "ok"
    assert result["held"] == 1
    assert runs.latest("coconala-wake-1")["next_actions"][0]["next_action"] == "collect_missing_gates"


def test_coconala_platform_source_maps_live_account_state_without_opportunities():
    source = module.CoconalaPlatformManifestSource(_live_snapshot)

    [item] = source.discover()

    assert item["source_kind"] == "platform"
    assert item["candidate_id"] == "platform:coconala"
    assert "request_details" not in item
    assert "account_id_sha256" not in item
    assert "coconala://live/source-complete/true" in item["evidence_refs"]
