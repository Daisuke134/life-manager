from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load(
    SCRIPTS / "crowdworks_platform_manifest_runtime.py",
    "crowdworks_platform_manifest_runtime_test",
)
application_owner = _load(
    SCRIPTS / "application_owner.py",
    "crowdworks_application_owner_manifest_runtime_test",
)


def _snapshot() -> dict[str, object]:
    return {
        "version": 1,
        "platform": "crowdworks",
        "observed_at": "2026-09-30T14:00:00Z",
        "source_url": "https://crowdworks.jp/dashboard",
        "adapter_source_sha256": "a" * 64,
        "authenticated": True,
        "source_complete": True,
        "profile_readback": True,
        "evidence_refs": ["crowdworks://account/live", "crowdworks://profile/readback/true"],
    }


def test_live_snapshot_contains_only_account_profile_state():
    snapshot = runtime.build_live_snapshot(
        authenticated=True,
        profile_readback=True,
        observed_at="2026-09-30T14:00:00Z",
    )

    assert snapshot["source_complete"] is True
    assert snapshot["profile_readback"] is True
    assert "jobs" not in snapshot
    assert "opportunities" not in snapshot


def test_crowdworks_natural_wake_persists_account_profile_only(tmp_path):
    result = runtime.run_crowdworks_platform_manifest_wake(
        snapshot=_snapshot(),
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="crowdworks-natural-1",
        observed_at="2026-09-30T14:01:00Z",
    )

    assert result["status"] == "partial"
    assert result["sources"] == 4
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "coconala", "lancers", "mercor",
    }


def test_crowdworks_application_owner_bridge_writes_read_only_summary(tmp_path):
    payload = application_owner.record_live_crowdworks_platform_manifest_wake(
        snapshot=_snapshot(),
        evidence_dir=tmp_path / "evidence",
        pass_id="crowdworks-pass-1",
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        observed_at="2026-09-30T14:02:00Z",
    )

    assert payload["status"] == "partial"
    assert payload["read_only"] is True
    assert (tmp_path / "evidence" / "platform-manifest-wake.json").is_file()


def test_crowdworks_candidate_lifecycle_uses_account_bound_registry(tmp_path):
    cycle = runtime._CYCLE or runtime._modules()[1]
    candidates_module = runtime._CANDIDATE_STORE or runtime._modules()[2]
    candidate_store = candidates_module.CandidateStateStore(tmp_path / "candidates")
    candidate_store.record({
        "schema_version": 1,
        "provider": "crowdworks",
        "candidate_id": "platform:crowdworks",
        "observed_at": "2026-09-30T15:20:00Z",
        "source_url": "https://crowdworks.jp",
        "snapshot_sha256": "d" * 64,
        "decision": "promote",
        "gates": {
            "policy": "pass", "adapter": "pass", "funded_work": "pass",
            "canary": "pass", "unit_economics": "pass",
        },
        "reasons": [],
        "evidence_refs": ["crowdworks://candidate/observed"],
        "next_action": "provision_owner_after_release_readback",
        "idempotency_key": "marketplace-candidate:v1:crowdworks:platform:crowdworks:" + "d" * 64,
    })

    calls = []

    class Adapter:
        def provision_owner(self, candidate):
            calls.append("provision")
            return {
                "status": "provisioned", "owner_id": "owner-1",
                "receipt_ref": "provider-receipt://crowdworks/owner-1",
                "observed_at": "2026-09-30T15:20:01Z",
            }

        def canary_readback(self, candidate, owner):
            calls.append("canary")
            return {
                "status": "verified", "receipt_ref": "provider-receipt://crowdworks/canary-1",
                "replay_zero": True, "observed_at": "2026-09-30T15:20:02Z",
            }

        def rollback_owner(self, candidate, owner, reason):
            calls.append("rollback")
            return {
                "status": "rolled_back", "receipt_ref": "provider-receipt://crowdworks/rollback-1",
                "observed_at": "2026-09-30T15:20:03Z",
            }

        def settle(self, candidate, owner, canary):
            calls.append("settle")
            return {
                "status": "settled", "receipt_ref": "provider-receipt://crowdworks/settlement-1",
                "net_amount_minor": 1000, "currency": "JPY",
                "observed_at": "2026-09-30T15:20:04Z",
            }

    registry = cycle.PlatformLifecycleAdapterRegistry({"crowdworks": lambda context: Adapter()})
    result = runtime.run_crowdworks_candidate_lifecycle(
        candidate_root=tmp_path / "candidates",
        lifecycle_root=tmp_path / "lifecycle",
        registry=registry,
        account_context={
            "account_id": "crowdworks-owner-1",
            "authorization_receipt_ref": "authorization-receipt://sha256/" + "a" * 64,
        },
        authorization=SimpleNamespace(state="approved_browser", receipt_hash="a" * 64),
        candidate_id="platform:crowdworks",
        run_id="crowdworks-lifecycle-1",
        observed_at="2026-09-30T15:20:00Z",
    )

    assert result["status"] == "settled"
    assert calls == ["provision", "canary", "settle"]
