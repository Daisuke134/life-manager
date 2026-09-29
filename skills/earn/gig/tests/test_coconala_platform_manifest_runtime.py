from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = _load(
    SCRIPTS / "coconala_platform_manifest_runtime.py",
    "coconala_platform_manifest_runtime_test",
)


STATES = (
    "preflight", "authenticated", "email_verified", "sms_verified",
    "seller_information", "identity_approved", "bank_registered",
    "launchd_readback", "storefront_listing_readback",
)


def _onboarding() -> dict[str, object]:
    return {
        "version": 2,
        "platform": "coconala",
        "states": {
            state: {
                "status": "complete" if state == "authenticated" else "pending",
                "evidence_sha256": "b" * 64 if state == "authenticated" else None,
            }
            for state in STATES
        },
    }


def _live_collector_snapshot() -> dict[str, object]:
    return {
        "version": 1,
        "pass_id": "coconala-pass-1",
        "lease_fence": {"task": "coconala", "token": "token", "generation": 1},
        "observed_at": "2026-09-30T12:00:00Z",
        "objective": {
            "target_applications": 1,
            "max_applications": 1,
            "required_search_source_ids": ["single:new"],
        },
        "search_sources": [{
            "source_id": "single:new",
            "url": "https://coconala.com/requests?recruiting=true",
            "page_index": 1,
            "card_request_ids": ["123"],
            "has_next": False,
            "exhausted": True,
            "screenshot_sha256": "a" * 64,
            "dom_sha256": "b" * 64,
        }],
        # Opportunity data must be projected out before the platform manifest.
        "request_details": [{"request_id": "123", "visible_text": "client brief"}],
        "already_applied_ids": [],
        "snapshot_sha256": "c" * 64,
    }


def test_live_coconala_wake_reads_onboarding_and_persists_partial_cycle(tmp_path):
    onboarding_path = tmp_path / "coconala-onboarding.json"
    onboarding_path.write_text(
        json.dumps(_onboarding(), ensure_ascii=False), encoding="utf-8",
    )

    result = runtime.run_coconala_platform_manifest_wake(
        onboarding_path=onboarding_path,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="coconala-natural-1",
        observed_at="2026-09-30T12:00:00Z",
    )

    assert result["status"] == "partial"
    assert result["sources"] == 4
    assert result["inspected"] == 1
    assert result["held"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "lancers", "crowdworks", "mercor",
    }
    assert result["next_actions"][0]["next_action"] == "collect_missing_gates"


def test_live_coconala_wake_missing_onboarding_is_typed_partial_without_creating_source(
    tmp_path,
):
    result = runtime.run_coconala_platform_manifest_wake(
        onboarding_path=tmp_path / "does-not-exist.json",
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="coconala-natural-missing-1",
        observed_at="2026-09-30T12:01:00Z",
    )

    assert result["status"] == "partial"
    assert result["inspected"] == 0
    assert {row["source"] for row in result["source_errors"]} == {
        "coconala", "lancers", "crowdworks", "mercor",
    }
    assert not (tmp_path / "does-not-exist.json").exists()


def test_live_coconala_wake_uses_collector_snapshot_without_onboarding_receipt(tmp_path):
    result = runtime.run_coconala_platform_manifest_wake(
        onboarding_path=tmp_path / "does-not-exist.json",
        live_snapshot=_live_collector_snapshot(),
        authenticated_state={
            "authenticated": True,
            "profile_readback": True,
            "account_id_sha256": "d" * 64,
        },
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="coconala-natural-live-1",
        observed_at="2026-09-30T12:02:00Z",
    )

    assert result["status"] == "partial"
    assert result["inspected"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "lancers", "crowdworks", "mercor",
    }


def test_live_profile_snapshot_hashes_identity_and_persists_hold(tmp_path):
    profile_url = "https://coconala.com/users/2564121"
    snapshot = runtime.build_live_profile_snapshot(
        profile_url=profile_url,
        account_id_sha256="f2fa9de414238160851ec65d2c1129ec5784d3c7e5e8a9acd1015a8ace2d315d",
        observed_at="2026-09-30T12:03:00Z",
    )

    assert snapshot["live_account"] == {
        "version": 1,
        "authenticated": True,
        "source_complete": False,
        "profile_readback": True,
        "account_id_sha256": (
            "f2fa9de414238160851ec65d2c1129ec5784d3c7e5e8a9acd1015a8ace2d315d"
        ),
    }
    profile_hash = hashlib.sha256(profile_url.encode("utf-8")).hexdigest()
    assert f"coconala://live/profile-url/sha256/{profile_hash}" in snapshot["evidence_refs"]
    assert profile_url not in json.dumps(snapshot, ensure_ascii=False)

    result = runtime.run_coconala_platform_manifest_wake(
        live_snapshot=snapshot,
        candidate_root=tmp_path / "candidates",
        run_root=tmp_path / "runs",
        run_id="coconala-profile-readback-1",
        observed_at="2026-09-30T12:03:00Z",
    )

    assert result["status"] == "partial"
    assert result["inspected"] == 1
    assert result["held"] == 1
    candidates = runtime._CANDIDATE_STORE or runtime._modules()[2]
    record = candidates.CandidateStateStore(tmp_path / "candidates").latest(
        "coconala", "platform:coconala",
    )
    assert record is not None
    assert record["decision"] == "hold"


def test_coconala_candidate_lifecycle_uses_account_bound_registry(tmp_path):
    cycle = runtime._CYCLE or runtime._modules()[1]
    candidates_module = runtime._CANDIDATE_STORE or runtime._modules()[2]
    candidate_store = candidates_module.CandidateStateStore(tmp_path / "candidates")
    candidate_store.record({
        "schema_version": 1,
        "provider": "coconala",
        "candidate_id": "platform:coconala",
        "observed_at": "2026-09-30T15:00:00Z",
        "source_url": "https://coconala.com",
        "snapshot_sha256": "b" * 64,
        "decision": "promote",
        "gates": {
            "policy": "pass", "adapter": "pass", "funded_work": "pass",
            "canary": "pass", "unit_economics": "pass",
        },
        "reasons": [],
        "evidence_refs": ["coconala://candidate/observed"],
        "next_action": "provision_owner_after_release_readback",
        "idempotency_key": "marketplace-candidate:v1:coconala:platform:coconala:" + "b" * 64,
    })

    calls = []

    class Adapter:
        def provision_owner(self, candidate):
            calls.append("provision")
            return {
                "status": "provisioned", "owner_id": "owner-1",
                "receipt_ref": "provider-receipt://coconala/owner-1",
                "observed_at": "2026-09-30T15:00:01Z",
            }

        def canary_readback(self, candidate, owner):
            calls.append("canary")
            return {
                "status": "verified", "receipt_ref": "provider-receipt://coconala/canary-1",
                "replay_zero": True,
                "observed_at": "2026-09-30T15:00:02Z",
            }

        def rollback_owner(self, candidate, owner, reason):
            calls.append("rollback")
            return {
                "status": "rolled_back", "receipt_ref": "provider-receipt://coconala/rollback-1",
                "observed_at": "2026-09-30T15:00:03Z",
            }

        def settle(self, candidate, owner, canary):
            calls.append("settle")
            return {
                "status": "settled", "receipt_ref": "provider-receipt://coconala/settlement-1",
                "net_amount_minor": 1000, "currency": "JPY",
                "observed_at": "2026-09-30T15:00:04Z",
            }

    registry = cycle.PlatformLifecycleAdapterRegistry({"coconala": lambda context: Adapter()})
    result = runtime.run_coconala_candidate_lifecycle(
        candidate_root=tmp_path / "candidates",
        lifecycle_root=tmp_path / "lifecycle",
        registry=registry,
        account_context={
            "account_id": "coconala-owner-1",
            "authorization_receipt_ref": "authorization-receipt://sha256/" + "a" * 64,
        },
        authorization=SimpleNamespace(state="approved_browser", receipt_hash="a" * 64),
        candidate_id="platform:coconala",
        run_id="coconala-lifecycle-1",
        observed_at="2026-09-30T15:00:00Z",
    )

    assert result["status"] == "settled"
    assert calls == ["provision", "canary", "settle"]
