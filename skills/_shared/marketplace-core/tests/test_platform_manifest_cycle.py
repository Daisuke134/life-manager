from __future__ import annotations

from copy import deepcopy
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


cycle = _load(SCRIPTS / "platform_manifest_cycle.py", "platform_manifest_cycle_test")
enrollment = _load(SCRIPTS / "platform_enrollment.py", "platform_cycle_enrollment_test")
candidate_store_module = _load(
    SCRIPTS / "platform_candidate_store.py", "platform_cycle_candidate_store_test"
)
run_store_module = _load(
    SCRIPTS / "meta_loop_run_store.py", "platform_cycle_run_store_test"
)
lifecycle_store_module = _load(
    SCRIPTS / "meta_loop_lifecycle.py", "platform_cycle_lifecycle_store_test"
)


PROVIDERS = ("coconala", "lancers", "crowdworks", "mercor")


def _item(provider: str) -> dict[str, object]:
    return {
        "source_kind": "platform",
        "candidate": {
            "version": 1,
            "provider": provider,
            "policy": {
                "status": "unknown",
                "source_url": "https://example.test/policy",
                "observed_at": "2026-09-30T06:00:00Z",
            },
            "adapter": {
                "contract": "marketplace-core-v1",
                "actions": [
                    "discover", "inspect", "propose", "message", "accept_offer",
                    "deliver", "read_payments", "read_payouts",
                ],
                "source_sha256": "a" * 64,
            },
            "funded_work": {
                "status": "unknown",
                "receipt_ref": f"provider-receipt://{provider}/unverified",
                "observed_at": "2026-09-30T06:00:00Z",
            },
            "canary": {
                "status": "unknown",
                "official_receipt_ref": None,
                "replay_zero": False,
                "observed_at": "2026-09-30T06:00:00Z",
            },
            "unit_economics": {
                "status": "unknown",
                "net_amount_minor": 0,
                "currency": "USD",
                "evidence_refs": [f"platform://{provider}/observed"],
            },
        },
        "candidate_id": f"platform:{provider}",
        "observed_at": "2026-09-30T06:00:00Z",
        "source_url": "https://example.test/platform",
        "snapshot_sha256": "b" * 64,
        "evidence_refs": [f"platform://{provider}/observed"],
    }


def test_platform_manifest_cycle_runs_all_four_sources_once_and_persists_summary(tmp_path):
    calls = {provider: 0 for provider in PROVIDERS}

    def discover(provider: str):
        def _discover():
            calls[provider] += 1
            return [_item(provider)]
        return _discover

    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")
    result = cycle.run_platform_manifest_wake(
        {provider: discover(provider) for provider in PROVIDERS},
        candidates,
        runs,
        run_id="all-platforms-1",
        observed_at="2026-09-30T06:01:00Z",
    )

    assert result["status"] == "ok"
    assert result["sources"] == 4
    assert result["inspected"] == 4
    assert result["held"] == 4
    assert calls == {provider: 1 for provider in PROVIDERS}
    assert runs.latest("all-platforms-1")["held"] == 4


def test_platform_manifest_cycle_records_missing_source_as_partial(tmp_path):
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")
    result = cycle.run_platform_manifest_wake(
        {"coconala": lambda: [_item("coconala")]},
        candidates,
        runs,
        run_id="missing-lancers-1",
        observed_at="2026-09-30T06:02:00Z",
    )

    assert result["status"] == "partial"
    assert result["sources"] == 4
    assert result["inspected"] == 1
    assert {row["source"] for row in result["source_errors"]} == {
        "crowdworks", "lancers", "mercor",
    }
    assert runs.latest("missing-lancers-1")["status"] == "partial"


def test_platform_manifest_cycle_rejects_unknown_source_before_discovery(tmp_path):
    called = False

    def discover():
        nonlocal called
        called = True
        return []

    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")
    try:
        cycle.run_platform_manifest_wake(
            {"unknown": discover},
            candidates,
            runs,
            run_id="unknown-source-1",
            observed_at="2026-09-30T06:03:00Z",
        )
    except cycle.PlatformManifestCycleError as error:
        assert str(error) == "source_provider_invalid"
    else:  # pragma: no cover - assertion keeps the failure explicit
        raise AssertionError("unknown source must fail closed")
    assert called is False


def test_platform_manifest_cycle_accepts_explicit_upwork_freelancer_registry(tmp_path):
    calls = []

    def discover(provider):
        def _discover():
            calls.append(provider)
            return [_item(provider)]
        return _discover

    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")
    result = cycle.run_platform_manifest_wake(
        {"upwork": discover("upwork"), "freelancer": discover("freelancer")},
        candidates,
        runs,
        providers=("upwork", "freelancer"),
        run_id="new-platforms-1",
        observed_at="2026-09-30T06:04:00Z",
    )

    assert result["status"] == "ok"
    assert result["sources"] == 2
    assert result["inspected"] == 2
    assert result["held"] == 2
    assert calls == ["freelancer", "upwork"]


def test_platform_manifest_cycle_rejects_provider_outside_supported_registry(tmp_path):
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")

    try:
        cycle.run_platform_manifest_wake(
            {}, candidates, runs, providers=("not-a-platform",),
            run_id="bad-provider-1", observed_at="2026-09-30T06:05:00Z",
        )
    except cycle.PlatformManifestCycleError as error:
        assert str(error) == "provider_registry_invalid"
    else:  # pragma: no cover
        raise AssertionError("unsupported provider must fail closed")


class _LifecycleAdapter:
    def __init__(self):
        self.calls = []

    def provision_owner(self, candidate):
        self.calls.append("provision")
        return {
            "status": "provisioned", "owner_id": "owner-1",
            "receipt_ref": "provider-receipt://coconala/owner-1",
            "observed_at": "2026-09-30T06:06:00Z",
        }

    def canary_readback(self, candidate, owner):
        self.calls.append("canary")
        return {
            "status": "verified", "receipt_ref": "provider-receipt://coconala/canary-1",
            "replay_zero": True, "observed_at": "2026-09-30T06:07:00Z",
        }

    def rollback_owner(self, candidate, owner, reason):
        self.calls.append("rollback")
        return {
            "status": "rolled_back", "receipt_ref": "provider-receipt://coconala/rollback-1",
            "observed_at": "2026-09-30T06:08:00Z",
        }

    def settle(self, candidate, owner, canary):
        self.calls.append("settle")
        return {
            "status": "settled", "receipt_ref": "provider-receipt://coconala/settlement-1",
            "net_amount_minor": 100, "currency": "USD",
            "observed_at": "2026-09-30T06:09:00Z",
        }


def _promoted_candidate():
    item = _item("coconala")
    candidate = deepcopy(item["candidate"])
    candidate["policy"] = {
        "status": "allowed", "source_url": "https://example.test/policy",
        "observed_at": "2026-09-30T06:00:00Z",
    }
    candidate["funded_work"] = {
        "status": "funded", "receipt_ref": "provider-receipt://coconala/funding-1",
        "observed_at": "2026-09-30T06:01:00Z",
    }
    candidate["canary"] = {
        "status": "verified", "official_receipt_ref": "provider-receipt://coconala/canary-0",
        "replay_zero": True, "observed_at": "2026-09-30T06:02:00Z",
    }
    candidate["unit_economics"] = {
        "status": "measured", "net_amount_minor": 100, "currency": "USD",
        "evidence_refs": ["ledger://coconala/canary-0"],
    }
    return candidate


def test_platform_candidate_lifecycle_holds_manifest_candidate_without_adapter_effect(tmp_path):
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    runs = run_store_module.MetaLoopRunStore(tmp_path / "runs")
    lifecycle_store = lifecycle_store_module.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    cycle.run_platform_manifest_wake(
        {"coconala": lambda: [_item("coconala")]}, candidates, runs,
        providers=("coconala",), run_id="manifest-hold-1",
        observed_at="2026-09-30T06:06:00Z",
    )
    adapter = _LifecycleAdapter()

    result = cycle.run_platform_candidate_lifecycle(
        candidates, lifecycle_store, adapter,
        provider="coconala", candidate_id="platform:coconala",
        run_id="lifecycle-hold-1", observed_at="2026-09-30T06:06:30Z",
    )

    assert result["status"] == "held"
    assert adapter.calls == []


def test_platform_candidate_lifecycle_delegates_promoted_record_to_shared_lifecycle(tmp_path):
    candidates = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    lifecycle_store = lifecycle_store_module.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    enrollment.evaluate_and_record_candidate(
        _promoted_candidate(), candidates,
        candidate_id="listing:promoted", observed_at="2026-09-30T06:05:00Z",
        source_url="https://example.test/listing:promoted", snapshot_sha256="d" * 64,
    )
    adapter = _LifecycleAdapter()

    result = cycle.run_platform_candidate_lifecycle(
        candidates, lifecycle_store, adapter,
        provider="coconala", candidate_id="listing:promoted",
        run_id="lifecycle-promote-1", observed_at="2026-09-30T06:06:30Z",
    )

    assert result["status"] == "settled"
    assert adapter.calls == ["provision", "canary", "settle"]


def test_platform_candidate_lifecycle_rejects_unknown_provider_before_readback(tmp_path):
    called = False

    class _CandidateStore:
        def latest(self, provider, candidate_id):
            nonlocal called
            called = True
            return None

    with pytest.raises(cycle.PlatformManifestCycleError, match="provider_invalid"):
        cycle.run_platform_candidate_lifecycle(
            _CandidateStore(), object(), _LifecycleAdapter(),
            provider="unknown", candidate_id="listing-1",
            run_id="lifecycle-invalid-1", observed_at="2026-09-30T06:06:30Z",
        )
    assert called is False


def test_registered_lifecycle_adapter_requires_account_bound_auth_context():
    registry = cycle.PlatformLifecycleAdapterRegistry(
        {"crowdworks": lambda context: _LifecycleAdapter()}
    )

    with pytest.raises(cycle.PlatformManifestCycleError, match="account_context_invalid"):
        registry.resolve("crowdworks", {})


def test_registered_lifecycle_adapter_rejects_missing_provider_without_effect():
    registry = cycle.PlatformLifecycleAdapterRegistry({})

    with pytest.raises(cycle.PlatformManifestCycleError, match="adapter_missing:coconala"):
        registry.resolve(
            "coconala",
            {"account_id": "coconala-owner", "authorization_receipt_ref": "auth://coconala/1"},
        )


def test_registered_lifecycle_adapter_delegates_only_valid_adapter(tmp_path):
    candidate_store = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    lifecycle_store = lifecycle_store_module.MetaLoopLifecycleStore(tmp_path / "lifecycle")
    enrollment.evaluate_and_record_candidate(
        _promoted_candidate(), candidate_store,
        candidate_id="listing:promoted", observed_at="2026-09-30T06:05:00Z",
        source_url="https://example.test/listing:promoted", snapshot_sha256="d" * 64,
    )
    calls = []

    def factory(context):
        calls.append(dict(context))
        return _LifecycleAdapter()

    registry = cycle.PlatformLifecycleAdapterRegistry({"coconala": factory})
    result = cycle.run_registered_platform_candidate_lifecycle(
        candidate_store,
        lifecycle_store,
        registry,
        provider="coconala",
        candidate_id="listing:promoted",
        account_context={
            "account_id": "coconala-owner",
            "authorization_receipt_ref": "auth://coconala/1",
        },
        run_id="wake-registered",
        observed_at="2026-09-30T06:00:00Z",
    )

    assert result["status"] == "settled"
    assert calls == [{
        "account_id": "coconala-owner",
        "authorization_receipt_ref": "auth://coconala/1",
    }]


def test_registered_lifecycle_adapter_rejects_incomplete_adapter_before_candidate_readback(tmp_path):
    class _Incomplete:
        def provision_owner(self, candidate):
            return {}

    registry = cycle.PlatformLifecycleAdapterRegistry(
        {"coconala": lambda context: _Incomplete()}
    )
    candidate_store = candidate_store_module.CandidateStateStore(tmp_path / "candidates")
    lifecycle_store = lifecycle_store_module.MetaLoopLifecycleStore(tmp_path / "lifecycle")

    with pytest.raises(cycle.PlatformManifestCycleError, match="adapter_invalid:canary_readback"):
        cycle.run_registered_platform_candidate_lifecycle(
            candidate_store,
            lifecycle_store,
            registry,
            provider="coconala",
            candidate_id="listing:promoted",
            account_context={
                "account_id": "coconala-owner",
                "authorization_receipt_ref": "auth://coconala/1",
            },
            run_id="wake-invalid-adapter",
            observed_at="2026-09-30T06:00:00Z",
        )
