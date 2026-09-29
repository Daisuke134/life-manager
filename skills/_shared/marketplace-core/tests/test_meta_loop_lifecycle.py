from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lifecycle = _load(SCRIPTS / "meta_loop_lifecycle.py", "meta_loop_lifecycle_test")


def _candidate(*, decision: str = "promote") -> dict[str, object]:
    return {
        "schema_version": 1,
        "provider": "example-market",
        "candidate_id": "listing-1",
        "observed_at": "2026-09-30T06:00:00Z",
        "source_url": "https://example.test/listing-1",
        "snapshot_sha256": "a" * 64,
        "decision": decision,
        "gates": {
            "policy": "pass" if decision == "promote" else "fail",
            "adapter": "pass",
            "funded_work": "pass",
            "canary": "pass",
            "unit_economics": "pass",
        },
        "reasons": [] if decision == "promote" else ["policy_not_allowed"],
        "evidence_refs": ["provider-receipt://example-market/canary-1"],
        "next_action": "provision_owner_after_release_readback" if decision == "promote" else "collect_missing_gates",
        "idempotency_key": "marketplace-candidate:v1:example-market:listing-1:" + "a" * 64,
    }


class _Adapter:
    def __init__(self, *, canary_status: str = "verified", rollback_ok: bool = True):
        self.calls: list[str] = []
        self.canary_status = canary_status
        self.rollback_ok = rollback_ok

    def provision_owner(self, candidate):
        self.calls.append("provision")
        return {
            "status": "provisioned",
            "owner_id": "owner-1",
            "receipt_ref": "provider-receipt://example-market/owner-1",
            "observed_at": "2026-09-30T06:01:00Z",
        }

    def canary_readback(self, candidate, owner):
        self.calls.append("canary")
        return {
            "status": self.canary_status,
            "receipt_ref": "provider-receipt://example-market/canary-2" if self.canary_status == "verified" else None,
            "replay_zero": self.canary_status == "verified",
            "observed_at": "2026-09-30T06:02:00Z",
        }

    def rollback_owner(self, candidate, owner, reason):
        self.calls.append("rollback")
        if not self.rollback_ok:
            raise RuntimeError("rollback unavailable")
        return {
            "status": "rolled_back",
            "receipt_ref": "provider-receipt://example-market/rollback-1",
            "observed_at": "2026-09-30T06:03:00Z",
        }

    def settle(self, candidate, owner, canary):
        self.calls.append("settle")
        return {
            "status": "settled",
            "receipt_ref": "provider-receipt://example-market/settlement-1",
            "net_amount_minor": 100,
            "currency": "USD",
            "observed_at": "2026-09-30T06:04:00Z",
        }


def test_promoted_candidate_runs_owner_canary_settlement_once_and_persists_receipts(tmp_path):
    store = lifecycle.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    adapter = _Adapter()

    result = lifecycle.run_meta_loop_lifecycle(
        _candidate(), adapter, store,
        run_id="wake-1", observed_at="2026-09-30T06:00:30Z",
    )

    assert result["status"] == "settled"
    assert adapter.calls == ["provision", "canary", "settle"]
    latest = store.latest(result["lifecycle_key"])
    assert latest is not None
    assert latest["status"] == "settled"
    assert latest["owner_receipt_ref"] == "provider-receipt://example-market/owner-1"
    assert latest["canary_receipt_ref"] == "provider-receipt://example-market/canary-2"
    assert latest["settlement_receipt_ref"] == "provider-receipt://example-market/settlement-1"


def test_held_candidate_is_recorded_without_owner_effect(tmp_path):
    store = lifecycle.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    adapter = _Adapter()

    result = lifecycle.run_meta_loop_lifecycle(
        _candidate(decision="hold"), adapter, store,
        run_id="wake-hold", observed_at="2026-09-30T06:00:30Z",
    )

    assert result["status"] == "held"
    assert adapter.calls == []
    assert store.latest(result["lifecycle_key"])["next_action"] == "collect_missing_gates"


def test_unverified_canary_rolls_back_and_never_settles(tmp_path):
    store = lifecycle.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    adapter = _Adapter(canary_status="unverified")

    result = lifecycle.run_meta_loop_lifecycle(
        _candidate(), adapter, store,
        run_id="wake-canary-fail", observed_at="2026-09-30T06:00:30Z",
    )

    assert result["status"] == "rolled_back"
    assert adapter.calls == ["provision", "canary", "rollback"]
    latest = store.latest(result["lifecycle_key"])
    assert latest["rollback_receipt_ref"] == "provider-receipt://example-market/rollback-1"
    assert latest["settlement_receipt_ref"] is None


def test_rollback_failure_is_recorded_as_reconciliation_required(tmp_path):
    store = lifecycle.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    adapter = _Adapter(canary_status="unverified", rollback_ok=False)

    result = lifecycle.run_meta_loop_lifecycle(
        _candidate(), adapter, store,
        run_id="wake-rollback-fail", observed_at="2026-09-30T06:00:30Z",
    )

    assert result["status"] == "rollback_required"
    assert result["next_action"] == "official_readback_then_rollback"
    assert adapter.calls == ["provision", "canary", "rollback"]
    assert store.latest(result["lifecycle_key"])["owner_receipt_ref"] == "provider-receipt://example-market/owner-1"


def test_replay_of_terminal_lifecycle_does_not_call_provider_again(tmp_path):
    store = lifecycle.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    first_adapter = _Adapter()
    first = lifecycle.run_meta_loop_lifecycle(
        _candidate(), first_adapter, store,
        run_id="wake-1", observed_at="2026-09-30T06:00:30Z",
    )
    second_adapter = _Adapter()

    second = lifecycle.run_meta_loop_lifecycle(
        _candidate(), second_adapter, store,
        run_id="wake-2", observed_at="2026-09-30T06:05:30Z",
    )

    assert first["status"] == "settled"
    assert second["status"] == "duplicate"
    assert second["record"]["status"] == "settled"
    assert second_adapter.calls == []


def test_planned_lifecycle_requires_reconciliation_instead_of_replaying_owner(tmp_path):
    store = lifecycle.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    adapter = _Adapter()
    lifecycle_key = lifecycle.lifecycle_key(_candidate())
    store.record(lifecycle.planned_event(
        _candidate(), lifecycle_key,
        run_id="crashed-wake", observed_at="2026-09-30T06:00:30Z",
    ))

    result = lifecycle.run_meta_loop_lifecycle(
        _candidate(), adapter, store,
        run_id="retry-wake", observed_at="2026-09-30T06:05:30Z",
    )

    assert result["status"] == "reconcile_required"
    assert result["next_action"] == "official_readback_before_retry"
    assert adapter.calls == []


def test_invalid_provider_receipt_fails_closed_before_settlement(tmp_path):
    store = lifecycle.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    adapter = _Adapter()

    def invalid_settle(candidate, owner, canary):
        adapter.calls.append("settle")
        return {
            "status": "settled",
            "receipt_ref": "provider-receipt://other-market/settlement-1",
            "net_amount_minor": 100,
            "currency": "USD",
            "observed_at": "2026-09-30T06:04:00Z",
        }

    adapter.settle = invalid_settle
    result = lifecycle.run_meta_loop_lifecycle(
        _candidate(), adapter, store,
        run_id="wake-invalid-receipt", observed_at="2026-09-30T06:00:30Z",
    )

    assert result["status"] == "rolled_back"
    assert adapter.calls == ["provision", "canary", "settle", "rollback"]
    assert store.latest(result["lifecycle_key"])["next_action"] == "retry_after_provider_readback"


def test_store_rejects_lifecycle_key_conflict(tmp_path):
    store = lifecycle.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    candidate = _candidate()
    key = lifecycle.lifecycle_key(candidate)
    event = lifecycle.planned_event(candidate, key, run_id="wake-1", observed_at="2026-09-30T06:00:30Z")
    store.record(event)
    with pytest.raises(lifecycle.MetaLoopLifecycleStoreError, match="event_key_conflict"):
        store.record({**event, "run_id": "wake-2"})


def test_candidate_snapshot_must_end_in_a_sha256_digest(tmp_path):
    store = lifecycle.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    candidate = _candidate()
    candidate["idempotency_key"] = "marketplace-candidate:v1:example-market:listing-1:not-a-digest"
    with pytest.raises(lifecycle.MetaLoopLifecycleError, match="candidate_snapshot_key_invalid"):
        lifecycle.run_meta_loop_lifecycle(
            candidate, _Adapter(), store,
            run_id="wake-invalid-snapshot", observed_at="2026-09-30T06:00:30Z",
        )
