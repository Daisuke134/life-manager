from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
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
    SCRIPTS / "lancers_platform_manifest_runtime.py",
    "lancers_platform_manifest_runtime_test",
)
application_loop = _load(
    SCRIPTS / "application_loop.py",
    "lancers_application_loop_manifest_runtime_test",
)


def test_lancers_natural_wake_filters_contract_state_and_persists_partial_cycle(tmp_path):
    contracts_path = tmp_path / "contracts.json"
    contracts_path.write_text(json.dumps({
        "logged_in": True,
        "source_complete": True,
        "observed_at": "2026-09-30T13:00:00Z",
        "board_count": 3,
        "required_reply_count": 1,
        "unread_count": 2,
        # These fields are deliberately opportunity/contract data and must not
        # cross the platform-manifest boundary.
        "boards": [{"board_id": "secret-opportunity-data"}],
        "contract_candidates": [{"project_id": "123"}],
    }), encoding="utf-8")

    result = runtime.run_lancers_platform_manifest_wake(
        contracts_path=contracts_path,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="lancers-natural-1",
        observed_at="2026-09-30T13:01:00Z",
    )

    assert result["status"] == "partial"
    assert result["sources"] == 4
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "coconala", "crowdworks", "mercor",
    }


def test_lancers_natural_wake_missing_contract_state_is_typed_partial_without_creation(tmp_path):
    result = runtime.run_lancers_platform_manifest_wake(
        contracts_path=tmp_path / "missing-contracts.json",
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="lancers-natural-missing-1",
        observed_at="2026-09-30T13:02:00Z",
    )

    assert result["status"] == "partial"
    assert result["inspected"] == 0
    assert {row["source"] for row in result["source_errors"]} == {
        "coconala", "lancers", "crowdworks", "mercor",
    }
    assert not (tmp_path / "missing-contracts.json").exists()


def test_lancers_application_wake_bridge_writes_summary(tmp_path):
    contracts_path = tmp_path / "contracts.json"
    contracts_path.write_text(json.dumps({
        "logged_in": True,
        "source_complete": True,
        "board_count": 0,
        "required_reply_count": 0,
        "unread_count": 0,
    }), encoding="utf-8")

    payload = application_loop.record_live_lancers_platform_manifest_wake(
        evidence_dir=tmp_path / "evidence",
        pass_id="lancers-pass-1",
        contracts_path=contracts_path,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        observed_at="2026-09-30T13:03:00Z",
    )

    assert payload["status"] == "partial"
    assert payload["pass_id"] == "lancers-pass-1"
    assert (tmp_path / "evidence" / "platform-manifest-wake.json").is_file()


def test_lancers_natural_run_invokes_platform_bridge_before_default_discovery(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        application_loop,
        "record_live_lancers_platform_manifest_wake",
        lambda **kwargs: calls.append(kwargs) or {"status": "partial"},
    )
    monkeypatch.setattr(application_loop, "_capacity_reason", lambda *_args: None)
    monkeypatch.setattr(
        application_loop,
        "_run_default_discovery",
        lambda *_args: {"ok": True, "opportunities": [], "observed_count": 0, "already_decided_count": 0},
    )

    result = application_loop.run_loop(
        state_path=tmp_path / "application.json",
        evidence_root=tmp_path / "evidence",
        clock=lambda: datetime(2026, 9, 30, 13, 4, tzinfo=timezone.utc),
    )

    assert result["reason"] == "no_eligible_project"
    assert len(calls) == 1
    assert calls[0]["contracts_path"] == tmp_path / "contracts.json"


def test_lancers_candidate_lifecycle_uses_account_bound_registry(tmp_path):
    cycle = runtime._CYCLE or runtime._modules()[1]
    candidates_module = runtime._CANDIDATE_STORE or runtime._modules()[2]
    candidate_store = candidates_module.CandidateStateStore(tmp_path / "candidates")
    candidate_store.record({
        "schema_version": 1,
        "provider": "lancers",
        "candidate_id": "platform:lancers",
        "observed_at": "2026-09-30T15:10:00Z",
        "source_url": "https://www.lancers.jp",
        "snapshot_sha256": "c" * 64,
        "decision": "promote",
        "gates": {
            "policy": "pass", "adapter": "pass", "funded_work": "pass",
            "canary": "pass", "unit_economics": "pass",
        },
        "reasons": [],
        "evidence_refs": ["lancers://candidate/observed"],
        "next_action": "provision_owner_after_release_readback",
        "idempotency_key": "marketplace-candidate:v1:lancers:platform:lancers:" + "c" * 64,
    })

    calls = []

    class Adapter:
        def provision_owner(self, candidate):
            calls.append("provision")
            return {
                "status": "provisioned", "owner_id": "owner-1",
                "receipt_ref": "provider-receipt://lancers/owner-1",
                "observed_at": "2026-09-30T15:10:01Z",
            }

        def canary_readback(self, candidate, owner):
            calls.append("canary")
            return {
                "status": "verified", "receipt_ref": "provider-receipt://lancers/canary-1",
                "replay_zero": True, "observed_at": "2026-09-30T15:10:02Z",
            }

        def rollback_owner(self, candidate, owner, reason):
            calls.append("rollback")
            return {
                "status": "rolled_back", "receipt_ref": "provider-receipt://lancers/rollback-1",
                "observed_at": "2026-09-30T15:10:03Z",
            }

        def settle(self, candidate, owner, canary):
            calls.append("settle")
            return {
                "status": "settled", "receipt_ref": "provider-receipt://lancers/settlement-1",
                "net_amount_minor": 1000, "currency": "JPY",
                "observed_at": "2026-09-30T15:10:04Z",
            }

    registry = cycle.PlatformLifecycleAdapterRegistry({"lancers": lambda context: Adapter()})
    result = runtime.run_lancers_candidate_lifecycle(
        candidate_root=tmp_path / "candidates",
        lifecycle_root=tmp_path / "lifecycle",
        registry=registry,
        account_context={
            "account_id": "lancers-owner-1",
            "authorization_receipt_ref": "authorization-receipt://sha256/" + "a" * 64,
        },
        authorization=SimpleNamespace(state="approved_browser", receipt_hash="a" * 64),
        candidate_id="platform:lancers",
        run_id="lancers-lifecycle-1",
        observed_at="2026-09-30T15:10:00Z",
    )

    assert result["status"] == "settled"
    assert calls == ["provision", "canary", "settle"]
