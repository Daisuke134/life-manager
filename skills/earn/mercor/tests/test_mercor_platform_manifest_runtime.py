from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills" / "earn" / "mercor" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = _load(
    SCRIPTS / "mercor_platform_manifest_runtime.py",
    "mercor_platform_manifest_runtime_test",
)


def _reply_snapshot() -> dict[str, object]:
    return {
        "applications": [],
        "notifications": [],
        "assessments": [],
        "contracts": [],
        "interviews": [],
        "gmail": [{"threadId": "thread-1", "messages": []}],
        "source_health": {"gmail": {"status": "fresh", "observed_at": "2026-09-30T05:00:00Z"}},
        # These opportunity fields must never cross into the platform manifest.
        "inspected_listings": [{"listing_id": "list-1"}],
        "submitted": [{"listing_id": "list-1"}],
    }


def test_build_live_snapshot_contains_only_account_source_health():
    snapshot = runtime.build_live_snapshot(
        reply_snapshot=_reply_snapshot(),
        account_id="owner@example.com",
        auth_readback={"status": "authenticated", "url": "https://work.mercor.com/home"},
        observed_at="2026-09-30T05:01:00Z",
    )

    assert set(snapshot) == {
        "version", "platform", "observed_at", "source_url", "adapter_source_sha256",
        "account_id", "source_complete", "gmail_status", "contract_readback", "evidence_refs",
    }
    assert snapshot["source_complete"] is True
    assert snapshot["contract_readback"] is True
    assert snapshot["gmail_status"] == "fresh"
    assert "inspected_listings" not in snapshot
    assert "submitted" not in snapshot


def test_build_live_snapshot_marks_stale_or_incomplete_sources_false():
    reply = _reply_snapshot()
    reply["source_health"] = {"gmail": {"status": "stale", "observed_at": "2026-09-29T05:00:00Z"}}
    reply.pop("contracts")

    snapshot = runtime.build_live_snapshot(
        reply_snapshot=reply,
        account_id="owner@example.com",
        auth_readback={"status": "authenticated"},
        observed_at="2026-09-30T05:01:00Z",
    )

    assert snapshot["source_complete"] is False
    assert snapshot["contract_readback"] is False
    assert snapshot["gmail_status"] == "stale"


def test_run_wake_persists_mercor_hold_and_typed_missing_sources(tmp_path):
    snapshot = runtime.build_live_snapshot(
        reply_snapshot=_reply_snapshot(),
        account_id="owner@example.com",
        auth_readback={"status": "authenticated"},
        observed_at="2026-09-30T05:01:00Z",
    )

    result = runtime.run_mercor_platform_manifest_wake(
        snapshot=snapshot,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="mercor-natural-test",
        observed_at="2026-09-30T05:01:00Z",
    )

    assert result["status"] == "partial"
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert result["source_errors"]
    assert any(error["source"] == "coconala" for error in result["source_errors"])


def test_reply_owner_invokes_manifest_before_reply_kernel():
    source = (SCRIPTS / "reply-owner").read_text(encoding="utf-8")

    assert "--platform-manifest-evidence-dir" in source
    assert "--auth-readback" in source
    assert source.index("--platform-manifest-evidence-dir") < source.index("reply_kernel.py")


def test_mercor_candidate_lifecycle_uses_account_bound_registry(tmp_path):
    cycle = runtime._CYCLE or runtime._modules()[1]
    candidates_module = runtime._CANDIDATE_STORE or runtime._modules()[2]
    candidate_store = candidates_module.CandidateStateStore(tmp_path / "candidates")
    candidate_store.record({
        "schema_version": 1,
        "provider": "mercor",
        "candidate_id": "platform:mercor",
        "observed_at": "2026-09-30T15:30:00Z",
        "source_url": "https://work.mercor.com",
        "snapshot_sha256": "e" * 64,
        "decision": "promote",
        "gates": {
            "policy": "pass", "adapter": "pass", "funded_work": "pass",
            "canary": "pass", "unit_economics": "pass",
        },
        "reasons": [],
        "evidence_refs": ["mercor://candidate/observed"],
        "next_action": "provision_owner_after_release_readback",
        "idempotency_key": "marketplace-candidate:v1:mercor:platform:mercor:" + "e" * 64,
    })

    calls = []

    class Adapter:
        def provision_owner(self, candidate):
            calls.append("provision")
            return {
                "status": "provisioned", "owner_id": "owner-1",
                "receipt_ref": "provider-receipt://mercor/owner-1",
                "observed_at": "2026-09-30T15:30:01Z",
            }

        def canary_readback(self, candidate, owner):
            calls.append("canary")
            return {
                "status": "verified", "receipt_ref": "provider-receipt://mercor/canary-1",
                "replay_zero": True, "observed_at": "2026-09-30T15:30:02Z",
            }

        def rollback_owner(self, candidate, owner, reason):
            calls.append("rollback")
            return {
                "status": "rolled_back", "receipt_ref": "provider-receipt://mercor/rollback-1",
                "observed_at": "2026-09-30T15:30:03Z",
            }

        def settle(self, candidate, owner, canary):
            calls.append("settle")
            return {
                "status": "settled", "receipt_ref": "provider-receipt://mercor/settlement-1",
                "net_amount_minor": 1000, "currency": "USD",
                "observed_at": "2026-09-30T15:30:04Z",
            }

    registry = cycle.PlatformLifecycleAdapterRegistry({"mercor": lambda context: Adapter()})
    result = runtime.run_mercor_candidate_lifecycle(
        candidate_root=tmp_path / "candidates",
        lifecycle_root=tmp_path / "lifecycle",
        registry=registry,
        account_context={
            "account_id": "mercor-owner-1",
            "authorization_receipt_ref": "auth://mercor/receipt-1",
        },
        candidate_id="platform:mercor",
        run_id="mercor-lifecycle-1",
        observed_at="2026-09-30T15:30:00Z",
    )

    assert result["status"] == "settled"
    assert calls == ["provision", "canary", "settle"]
