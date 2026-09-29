from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "platform_enrollment.py"
STORE_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "platform_candidate_store.py"


def _module():
    spec = importlib.util.spec_from_file_location("marketplace_platform_enrollment_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _store_module():
    spec = importlib.util.spec_from_file_location("marketplace_platform_candidate_store_test", STORE_MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate(**overrides):
    value = {
        "version": 1,
        "provider": "example-market",
        "policy": {
            "status": "allowed",
            "source_url": "https://example.test/automation-policy",
            "observed_at": "2026-09-29T00:00:00Z",
        },
        "adapter": {
            "contract": "marketplace-core-v1",
            "actions": [
                "discover",
                "inspect",
                "propose",
                "message",
                "accept_offer",
                "deliver",
                "read_payments",
                "read_payouts",
            ],
            "source_sha256": "a" * 64,
        },
        "funded_work": {
            "status": "funded",
            "receipt_ref": "provider-receipt://example-market/funding-1",
            "observed_at": "2026-09-29T00:01:00Z",
        },
        "canary": {
            "status": "verified",
            "official_receipt_ref": "provider-receipt://example-market/canary-1",
            "replay_zero": True,
            "observed_at": "2026-09-29T00:02:00Z",
        },
        "unit_economics": {
            "status": "measured",
            "net_amount_minor": 100,
            "currency": "USD",
            "evidence_refs": ["ledger://example-market/canary-1"],
        },
    }
    for key, value_override in overrides.items():
        value[key] = value_override
    return value


def test_fully_evidenced_candidate_is_promotable():
    result = _module().evaluate_platform_candidate(_candidate())

    assert result["decision"] == "promote"
    assert result["owner_registration_allowed"] is True
    assert result["reasons"] == []
    assert all(status == "pass" for status in result["gates"].values())


def test_unknown_policy_holds_even_when_every_other_gate_is_ready():
    result = _module().evaluate_platform_candidate(_candidate(
        policy={
            "status": "unknown",
            "source_url": "https://example.test/automation-policy",
            "observed_at": "2026-09-29T00:00:00Z",
        },
    ))

    assert result["decision"] == "hold"
    assert result["owner_registration_allowed"] is False
    assert result["reasons"] == ["policy_not_allowed"]
    assert result["gates"]["policy"] == "fail"


def test_missing_canary_readback_and_non_positive_net_hold_promotion():
    result = _module().evaluate_platform_candidate(_candidate(
        canary={
            "status": "verified",
            "official_receipt_ref": None,
            "replay_zero": False,
            "observed_at": "2026-09-29T00:02:00Z",
        },
        unit_economics={
            "status": "measured",
            "net_amount_minor": 0,
            "currency": "USD",
            "evidence_refs": ["ledger://example-market/canary-1"],
        },
    ))

    assert result["decision"] == "hold"
    assert result["owner_registration_allowed"] is False
    assert result["reasons"] == [
        "canary_receipt_missing",
        "replay_not_zero",
        "net_not_positive",
    ]


def test_malformed_candidate_fails_closed():
    module = _module()
    with pytest.raises(module.EnrollmentError, match="candidate_fields_invalid"):
        module.evaluate_platform_candidate({"version": 1, "provider": "example-market"})


def test_receipts_must_be_bound_to_the_candidate_provider():
    module = _module()
    with pytest.raises(module.EnrollmentError, match="receipt_provider_mismatch"):
        module.evaluate_platform_candidate(_candidate(
            funded_work={
                "status": "funded",
                "receipt_ref": "provider-receipt://other-market/funding-1",
                "observed_at": "2026-09-29T00:01:00Z",
            },
        ))


class _RecordingStore:
    def __init__(self):
        self.records = []

    def record(self, value):
        self.records.append(value)
        return {"status": "appended", "record": value}


def test_evaluation_can_be_persisted_without_opening_a_provider_transport():
    module = _module()
    store = _RecordingStore()

    result = module.evaluate_and_record_candidate(
        _candidate(),
        store,
        candidate_id="listing-123",
        observed_at="2026-09-29T00:03:00Z",
        source_url="https://example.test/listing-123",
        snapshot_sha256="b" * 64,
        evidence_refs=["provider-receipt://example-market/canary-1"],
    )

    assert result["evaluation"]["decision"] == "promote"
    assert result["persistence"]["status"] == "appended"
    assert store.records[0]["provider"] == "example-market"
    assert store.records[0]["decision"] == "promote"
    assert store.records[0]["gates"] == {
        "policy": "pass",
        "adapter": "pass",
        "funded_work": "pass",
        "canary": "pass",
        "unit_economics": "pass",
    }
    assert store.records[0]["reasons"] == []


def test_held_evaluation_is_persisted_with_a_next_action_and_no_owner_permission():
    module = _module()
    store = _RecordingStore()

    result = module.evaluate_and_record_candidate(
        _candidate(policy={
            "status": "unknown",
            "source_url": "https://example.test/automation-policy",
            "observed_at": "2026-09-29T00:00:00Z",
        }),
        store,
        candidate_id="listing-124",
        observed_at="2026-09-29T00:03:00Z",
        source_url="https://example.test/listing-124",
        snapshot_sha256="c" * 64,
    )

    assert result["evaluation"]["owner_registration_allowed"] is False
    assert store.records[0]["decision"] == "hold"
    assert store.records[0]["next_action"] == "collect_missing_gates"
    assert store.records[0]["reasons"] == ["policy_not_allowed"]


def test_invalid_candidate_is_not_persisted():
    module = _module()
    store = _RecordingStore()

    with pytest.raises(module.EnrollmentError):
        module.evaluate_and_record_candidate(
            {"version": 1, "provider": "example-market"},
            store,
            candidate_id="listing-125",
            observed_at="2026-09-29T00:03:00Z",
            source_url="https://example.test/listing-125",
            snapshot_sha256="d" * 64,
        )
    assert store.records == []


def test_evaluation_writes_the_real_durable_store(tmp_path):
    module = _module()
    store = _store_module().CandidateStateStore(tmp_path / "candidate-state")

    module.evaluate_and_record_candidate(
        _candidate(),
        store,
        candidate_id="listing-126",
        observed_at="2026-09-29T00:03:00Z",
        source_url="https://example.test/listing-126",
        snapshot_sha256="e" * 64,
    )

    persisted = store.latest("example-market", "listing-126")
    assert persisted is not None
    assert persisted["decision"] == "promote"


def test_discovery_cycle_persists_each_candidate_and_reports_next_actions(tmp_path):
    module = _module()
    store = _store_module().CandidateStateStore(tmp_path / "candidate-state")

    def discover():
        return [
            {
                "candidate": _candidate(),
                "candidate_id": "listing-127",
                "observed_at": "2026-09-29T00:04:00Z",
                "source_url": "https://example.test/listing-127",
                "snapshot_sha256": "f" * 64,
                "evidence_refs": ["provider-receipt://example-market/canary-1"],
            },
            {
                "candidate": _candidate(policy={
                    "status": "unknown",
                    "source_url": "https://example.test/automation-policy",
                    "observed_at": "2026-09-29T00:00:00Z",
                }),
                "candidate_id": "listing-128",
                "observed_at": "2026-09-29T00:04:00Z",
                "source_url": "https://example.test/listing-128",
                "snapshot_sha256": "1" * 64,
            },
        ]

    result = module.run_discovery_cycle({"example-source": discover}, store)

    assert result["status"] == "ok"
    assert result["inspected"] == 2
    assert result["persisted"] == 2
    assert result["duplicates"] == 0
    assert result["promoted"] == 1
    assert result["held"] == 1
    assert [item["next_action"] for item in result["next_actions"]] == [
        "provision_owner_after_release_readback",
        "collect_missing_gates",
    ]


def test_discovery_cycle_is_idempotent_on_replay(tmp_path):
    module = _module()
    store = _store_module().CandidateStateStore(tmp_path / "candidate-state")
    item = {
        "candidate": _candidate(),
        "candidate_id": "listing-129",
        "observed_at": "2026-09-29T00:04:00Z",
        "source_url": "https://example.test/listing-129",
        "snapshot_sha256": "2" * 64,
    }

    first = module.run_discovery_cycle({"example-source": lambda: [item]}, store)
    second = module.run_discovery_cycle({"example-source": lambda: [item]}, store)

    assert first["persisted"] == 1
    assert second["persisted"] == 0
    assert second["duplicates"] == 1
    assert len(store.read_all()) == 1


def test_discovery_cycle_reports_source_failure_without_mutating_other_sources(tmp_path):
    module = _module()
    store = _store_module().CandidateStateStore(tmp_path / "candidate-state")

    def failing_source():
        raise RuntimeError("transport is unavailable")

    result = module.run_discovery_cycle(
        {
            "a-failing-source": failing_source,
            "b-good-source": lambda: [{
                "candidate": _candidate(),
                "candidate_id": "listing-130",
                "observed_at": "2026-09-29T00:04:00Z",
                "source_url": "https://example.test/listing-130",
                "snapshot_sha256": "3" * 64,
            }],
        },
        store,
    )

    assert result["status"] == "partial"
    assert result["persisted"] == 1
    assert result["source_errors"] == [{
        "source": "a-failing-source",
        "error_class": "RuntimeError",
        "next_action": "retry_source_read_only",
    }]
    assert store.latest("example-market", "listing-130") is not None


def test_discovery_cycle_marks_no_candidate_wake_as_empty_not_success(tmp_path):
    module = _module()
    store = _store_module().CandidateStateStore(tmp_path / "candidate-state")

    result = module.run_discovery_cycle(
        {"empty-source": lambda: []},
        store,
    )

    assert result["status"] == "empty"
    assert result["inspected"] == 0
    assert result["persisted"] == 0
    assert result["held"] == 0
    assert result["next_actions"] == []
