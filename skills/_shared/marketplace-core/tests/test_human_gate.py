"""Provider-neutral, resumable human-gate contract tests."""

import importlib.util
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest


MODULE = Path(__file__).parents[1] / "scripts" / "human_gate.py"
SPEC = importlib.util.spec_from_file_location("marketplace_human_gate", MODULE)
human_gate = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(human_gate)


HASH = "a" * 64
NOW = "2026-09-15T00:00:00.000Z"
DEADLINE = "2026-09-16T00:00:00.000Z"


def request(**overrides):
    value = {
        "tenant_id": "tenant-1",
        "owner_id": "mercor-owner",
        "product_loop_id": "gig-mercor",
        "job_id": "mercor-application",
        "wake_id": "wake-1",
        "effect_key": "mercor-application:v1:abc",
        "capability": "mercor.interview",
        "action_kind": "interview",
        "action": "Complete the provider interview in the existing session.",
        "evidence_ref": "evidence://mercor/interview-state",
        "deadline": DEADLINE,
        "created_at": NOW,
    }
    value.update(overrides)
    return value


def test_build_gate_is_stable_and_contains_the_required_owner_and_outbox_identity():
    first = human_gate.build_human_gate(**request())
    second = human_gate.build_human_gate(**request())

    assert first == second
    assert first["schema_version"] == 1
    assert first["record_type"] == "human_gate"
    assert first["status"] == "pending"
    assert first["human_gate_id"]
    assert first["notification_event_id"] == f"human-gate:{first['human_gate_id']}"
    assert first["outbox_id"] is None
    assert first["answer_ref"] is None
    assert len(first["action_sha256"]) == 64
    assert human_gate.validate_human_gate(first) == first


def test_only_explicit_human_actions_are_allowed_and_secrets_are_rejected():
    for action_kind in ("interview", "kyc", "identity_recording", "approval"):
        assert human_gate.build_human_gate(**request(action_kind=action_kind))["action_kind"] == action_kind
    with pytest.raises(human_gate.HumanGateError):
        human_gate.build_human_gate(**request(action_kind="browser_navigation"))
    with pytest.raises(human_gate.HumanGateError):
        human_gate.build_human_gate(**request(action="Use the password from the vault."))
    with pytest.raises(human_gate.HumanGateError):
        human_gate.build_human_gate(**request(evidence_ref="https://user:pass@example.com/gate"))
    with pytest.raises(human_gate.HumanGateError):
        human_gate.validate_human_gate({**human_gate.build_human_gate(**request()), "unexpected": True})


def test_store_is_append_only_and_create_is_idempotent(tmp_path):
    path = tmp_path / "state" / "human-gates.jsonl"
    store = human_gate.HumanGateStore(path)
    record = human_gate.build_human_gate(**request())

    first = store.create(record)
    duplicate = store.create(record)

    assert first == duplicate
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert store.pending() == [record]
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert json.loads(path.read_text(encoding="utf-8"))["human_gate_id"] == record["human_gate_id"]


def test_same_gate_id_with_different_payload_is_a_conflict(tmp_path):
    store = human_gate.HumanGateStore(tmp_path / "human-gates.jsonl")
    record = human_gate.build_human_gate(**request())
    store.create(record)
    with pytest.raises(human_gate.HumanGateError, match="conflict"):
        store.create({**record, "outbox_id": "telegram:other"})


def test_concurrent_creates_still_append_one_gate(tmp_path):
    path = tmp_path / "human-gates.jsonl"
    record = human_gate.build_human_gate(**request())

    def create_once(_):
        return human_gate.HumanGateStore(path).create(record)

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(create_once, range(16)))
    assert all(row == record for row in rows)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_resolution_is_append_only_idempotent_and_keeps_the_same_effect_namespace(tmp_path):
    path = tmp_path / "human-gates.jsonl"
    store = human_gate.HumanGateStore(path)
    record = human_gate.build_human_gate(**request())
    store.create(record)

    resolved = store.resolve(
        record["human_gate_id"],
        owner_id=record["owner_id"],
        effect_key=record["effect_key"],
        answer_ref="answer://mercor/interview-complete",
        observed_at="2026-09-15T01:00:00.000Z",
        outbox_id="telegram:human-gate:1",
    )
    replay = store.resolve(
        record["human_gate_id"],
        owner_id=record["owner_id"],
        effect_key=record["effect_key"],
        answer_ref="answer://mercor/interview-complete",
        observed_at="2026-09-15T01:00:00.000Z",
        outbox_id="telegram:human-gate:1",
    )

    assert resolved == replay
    assert resolved["status"] == "resolved"
    assert resolved["owner_id"] == record["owner_id"]
    assert resolved["effect_key"] == record["effect_key"]
    assert resolved["notification_event_id"] == record["notification_event_id"]
    assert store.pending() == []
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    binding = human_gate.resume_binding(resolved, resume_wake_id="wake-2")
    assert binding == {
        "human_gate_id": record["human_gate_id"],
        "tenant_id": record["tenant_id"],
        "owner_id": record["owner_id"],
        "product_loop_id": record["product_loop_id"],
        "job_id": record["job_id"],
        "wake_id": "wake-2",
        "effect_key": record["effect_key"],
    }


def test_resolution_rejects_wrong_owner_effect_stale_answer_and_conflicting_replay(tmp_path):
    store = human_gate.HumanGateStore(tmp_path / "human-gates.jsonl")
    record = human_gate.build_human_gate(**request())
    store.create(record)
    kwargs = {
        "owner_id": record["owner_id"],
        "effect_key": record["effect_key"],
        "answer_ref": "answer://mercor/interview-complete",
        "observed_at": "2026-09-15T01:00:00.000Z",
    }
    for change in ({"owner_id": "another-owner"}, {"effect_key": "other-effect"}, {"observed_at": NOW}):
        with pytest.raises(human_gate.HumanGateError):
            store.resolve(record["human_gate_id"], **{**kwargs, **change})
    store.resolve(record["human_gate_id"], **kwargs)
    with pytest.raises(human_gate.HumanGateError, match="conflict"):
        store.resolve(record["human_gate_id"], **{**kwargs, "answer_ref": "answer://mercor/different"})
