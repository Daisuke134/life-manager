import datetime as dt
import hashlib
import json
from pathlib import Path

import fundraiser_fence_reconcile as reconciler
from fundraiser_fence_reconcile import pre_effect_proof, reconcile
from runtime.host import resource_admission


def _write_events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _write_marker(root: Path, occurrence_id: str, phase: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    run_id = occurrence_id.split(":", 1)[1]
    marker = {
        "schema_version": 1,
        "owner_id": "fundraiser",
        "occurrence_id": occurrence_id,
        "phase": phase,
        "effect": 0 if phase in {"pre_effect", "human_required"} else 1,
    }
    path = root / f"{run_id}.json"
    path.write_text(json.dumps(marker) + "\n", encoding="utf-8")
    path.chmod(0o600)


def test_submitted_verified_receipt_proves_post_effect_occurrence(tmp_path, monkeypatch):
    run_id = "20261008T090100Z-12345"
    occurrence_id = f"fundraiser:{run_id}"
    receipt_identity_hash = "b" * 64
    target_identity_hash = "a" * 64
    application_digest = "c" * 64
    applications_dir = tmp_path / "applications"
    applications_dir.mkdir(mode=0o700)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir(mode=0o700)
    run_evidence = evidence_root / run_id
    run_evidence.mkdir(mode=0o700)
    completion_png = run_evidence / "completion.png"
    completion_png.write_bytes(b"\x89PNG\r\n\x1a\ncompletion proof")
    completion_png.chmod(0o600)

    provider_readback = "Fresh FoundersEdge completion page displayed Application Submitted!"
    evidence = {
        "provider_readback": provider_readback,
        "completion_png": str(completion_png),
        "telegram_photo_message_id": 105320,
    }
    application_record = {
        "schema_version": 1,
        "run_id": run_id,
        "occurrence_id": occurrence_id,
        "receipt_identity_hash": receipt_identity_hash,
        "target_identity_hash": target_identity_hash,
        "application_digest": application_digest,
        "official_url": "https://apply.foundersedge.com/pitch",
        "evidence": evidence,
    }
    application_record_path = applications_dir / f"{receipt_identity_hash}.json"
    application_record_path.write_text(json.dumps(application_record) + "\n", encoding="utf-8")
    application_record_path.chmod(0o600)
    application_record_sha256 = hashlib.sha256(application_record_path.read_bytes()).hexdigest()

    receipts_path = tmp_path / "application-receipts.jsonl"
    receipts_path.write_text(json.dumps({
        "run_id": run_id,
        "occurrence_id": occurrence_id,
        "receipt_identity_hash": receipt_identity_hash,
        "target_identity_hash": target_identity_hash,
        "application_digest": application_digest,
        "status": "submitted_verified",
        "official_url": "https://apply.foundersedge.com/pitch",
        "provider_readback": provider_readback,
        "completion_png": str(completion_png),
        "telegram_photo_message_id": 105320,
        "application_record_path": str(application_record_path),
        "application_record_sha256": application_record_sha256,
    }) + "\n", encoding="utf-8")
    receipts_path.chmod(0o600)

    target_intents_path = tmp_path / "target-intents.jsonl"
    target_intents_path.write_text("\n".join((
        json.dumps({
            "occurrence_id": occurrence_id,
            "target_identity_hash": target_identity_hash,
            "receipt_identity_hash": receipt_identity_hash,
            "application_digest": application_digest,
            "status": "submitted_verified",
            "effect": 1,
        }),
        json.dumps({
            "occurrence_id": occurrence_id,
            "target_identity_hash": "d" * 64,
            "receipt_identity_hash": "e" * 64,
            "application_digest": "f" * 64,
            "status": "verified_pre_effect_failure",
            "effect": 0,
            "evidence_ref": "pre-effect-proof.json",
        }),
    )) + "\n", encoding="utf-8")
    target_intents_path.chmod(0o600)

    monkeypatch.setattr(reconciler, "RECEIPTS_PATH", receipts_path)
    monkeypatch.setattr(reconciler, "APPLICATIONS_ROOT", applications_dir, raising=False)
    monkeypatch.setattr(reconciler, "TARGET_INTENTS_PATH", target_intents_path, raising=False)
    markers_root = tmp_path / "effect-markers"
    _write_marker(markers_root, occurrence_id, "post_effect_verified")
    resolver_calls = []

    def fake_resolve(owner_id, resolved_occurrence, *, official_readback, expected_state):
        resolver_calls.append((owner_id, resolved_occurrence, official_readback(), expected_state))
        return True

    monkeypatch.setattr(resource_admission, "resolve_unknown_occurrence", fake_resolve)

    proof = reconcile(
        occurrence_id,
        events_path=tmp_path / "events.jsonl",
        evidence_root=evidence_root,
        markers_root=markers_root,
        fenced_row_fn=lambda _owner, _occurrence: (
            "claimed", dt.datetime(2026, 10, 8, 9, 1, tzinfo=dt.timezone.utc),
        ),
        resolve=True,
    )

    assert proof["verified"] is True
    assert proof["proof_type"] == "official_readback"
    assert proof["provider_receipt_id"] == "telegram-photo:105320"
    assert proof["official_readback_ref"].startswith("lm-fundraiser://")
    assert proof["receipt_identity_hashes"] == [receipt_identity_hash]
    assert proof["closed"] is True
    assert resolver_calls[0][0:2] == ("fundraiser", occurrence_id)
    assert resolver_calls[0][3] == "claimed"

    receipt = json.loads(receipts_path.read_text(encoding="utf-8"))
    receipt["application_record_sha256"] = "0" * 64
    receipts_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    receipts_path.chmod(0o600)
    tampered = reconcile(
        occurrence_id,
        events_path=tmp_path / "events.jsonl",
        evidence_root=evidence_root,
        markers_root=markers_root,
        fenced_row_fn=lambda _owner, _occurrence: (
            "claimed", dt.datetime(2026, 10, 8, 9, 1, tzinfo=dt.timezone.utc),
        ),
        resolve=True,
    )
    assert tampered["verified"] is False
    assert len(resolver_calls) == 1

    receipt["application_record_sha256"] = application_record_sha256
    receipts_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    receipts_path.chmod(0o600)
    with target_intents_path.open("a", encoding="utf-8") as target_intents:
        target_intents.write(json.dumps({
            "occurrence_id": occurrence_id,
            "target_identity_hash": "9" * 64,
            "receipt_identity_hash": "8" * 64,
            "application_digest": "7" * 64,
            "status": "submit_unknown",
            "effect": 1,
        }) + "\n")
    unsettled = reconcile(
        occurrence_id,
        events_path=tmp_path / "events.jsonl",
        evidence_root=evidence_root,
        markers_root=markers_root,
        fenced_row_fn=lambda _owner, _occurrence: (
            "claimed", dt.datetime(2026, 10, 8, 9, 1, tzinfo=dt.timezone.utc),
        ),
        resolve=True,
    )
    assert unsettled["verified"] is False
    assert unsettled["reason"] == "target_intents_unsettled"
    assert len(resolver_calls) == 1


def test_entrypoint_preflight_death_with_no_evidence_dir_is_verified_pre_effect(tmp_path):
    occurrence_id = "fundraiser:18d93c1c4f16c148-65964"
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {"occurrence_id": occurrence_id, "status": "running", "timestamp": "2026-09-27T17:00:19.142865+00:00"},
        {
            "occurrence_id": occurrence_id, "status": "fail", "failure_layer": "entrypoint",
            "effect_identity_status": "not_written", "exit_code": 75,
            "timestamp": "2026-09-27T17:00:51.304825+00:00",
        },
    ])
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()

    proof = pre_effect_proof("fundraiser", occurrence_id, events_path=events_path, evidence_root=evidence_root)
    assert proof["verified"] is True
    assert proof["proof_type"] == "pre_effect"
    assert "no_evidence_dir_in_window" in proof["evidence_ref"]


def test_an_evidence_directory_in_the_window_holds_the_fence(tmp_path):
    occurrence_id = "fundraiser:some-run"
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {"occurrence_id": occurrence_id, "status": "running", "timestamp": "2026-09-27T17:00:19.000000+00:00"},
        {
            "occurrence_id": occurrence_id, "status": "fail", "failure_layer": "entrypoint",
            "effect_identity_status": "not_written", "exit_code": 75,
            "timestamp": "2026-09-27T17:00:51.000000+00:00",
        },
    ])
    evidence_root = tmp_path / "evidence"
    # A real evidence directory landed inside the plausible window -- the
    # entrypoint did get far enough to hand off to the agent, so this must
    # stay held, not be guessed closed.
    (evidence_root / "20260927T170025Z-9999").mkdir(parents=True)

    proof = pre_effect_proof("fundraiser", occurrence_id, events_path=events_path, evidence_root=evidence_root)
    assert proof["verified"] is False
    assert proof["reason"] == "evidence_directory_exists_in_window"


def test_a_non_entrypoint_failure_never_qualifies_as_pre_effect(tmp_path):
    occurrence_id = "fundraiser:agent-ran"
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {"occurrence_id": occurrence_id, "status": "running", "timestamp": "2026-09-27T17:00:19.000000+00:00"},
        {
            "occurrence_id": occurrence_id, "status": "fail", "failure_layer": "agent",
            "effect_identity_status": "written", "exit_code": 1,
            "timestamp": "2026-09-27T17:05:00.000000+00:00",
        },
    ])
    proof = pre_effect_proof("fundraiser", occurrence_id, events_path=events_path, evidence_root=tmp_path / "evidence")
    assert proof["verified"] is False
    assert proof["reason"] == "no_entrypoint_preflight_signature"


def test_reconcile_calls_resolve_only_when_proof_verified_and_resolve_requested(tmp_path):
    occurrence_id = "fundraiser:18d93c1c4f16c148-65964"
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {"occurrence_id": occurrence_id, "status": "running", "timestamp": "2026-09-27T17:00:19.142865+00:00"},
        {
            "occurrence_id": occurrence_id, "status": "fail", "failure_layer": "entrypoint",
            "effect_identity_status": "not_written", "exit_code": 75,
            "timestamp": "2026-09-27T17:00:51.304825+00:00",
        },
    ])
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()

    calls = []

    def fake_resolve(owner_id, occ_id, *, pre_effect_readback, expected_state):
        calls.append((owner_id, occ_id, expected_state, pre_effect_readback()))
        return True

    result = reconcile(
        occurrence_id,
        events_path=events_path,
        evidence_root=evidence_root,
        fenced_row_fn=lambda owner, occ: ("claimed", dt.datetime(2026, 9, 27, 17, 0, 19, tzinfo=dt.timezone.utc)),
        resolve_fn=fake_resolve,
        resolve=True,
    )
    assert result["closed"] is True
    assert len(calls) == 1
    assert calls[0][:3] == ("fundraiser", occurrence_id, "claimed")

    # Without --resolve, the proof is reported but resolve_fn is never called.
    calls.clear()
    result = reconcile(
        occurrence_id,
        events_path=events_path,
        evidence_root=evidence_root,
        fenced_row_fn=lambda owner, occ: ("claimed", dt.datetime(2026, 9, 27, 17, 0, 19, tzinfo=dt.timezone.utc)),
        resolve_fn=fake_resolve,
        resolve=False,
    )
    assert "closed" not in result
    assert calls == []


def test_readonly_replay_uses_occurrence_marker_for_no_effect_after_agent_start(tmp_path):
    occurrence_id = "fundraiser:18d9b0b6311a2018-87933"
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {
            "occurrence_id": occurrence_id, "phase": "execute", "status": "running",
            "effect_status": "started", "timestamp": "2026-09-29T04:37:03.415461+00:00",
        },
        {
            "occurrence_id": occurrence_id, "phase": "report", "status": "pass",
            "effect_status": "unknown", "exit_code": 0, "failure_layer": "clean",
            "timestamp": "2026-09-29T04:39:52.679916+00:00",
        },
    ])
    evidence_root = tmp_path / "evidence"
    (evidence_root / "20260929T043704Z-87970").mkdir(parents=True)
    markers_root = tmp_path / "effect-markers"
    _write_marker(markers_root, occurrence_id, "pre_effect")

    proof = pre_effect_proof(
        "fundraiser", occurrence_id, events_path=events_path,
        evidence_root=evidence_root, markers_root=markers_root,
    )

    assert proof["verified"] is True
    assert proof["proof_type"] == "pre_effect"
    assert proof["classification"] == "pre_effect"
    assert proof["evidence_ref"].startswith("lm-fundraiser-marker://")


def test_readonly_replay_keeps_effect_attempted_marker_held_as_post_effect(tmp_path):
    occurrence_id = "fundraiser:post-submit-1"
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {
            "occurrence_id": occurrence_id, "phase": "execute", "status": "running",
            "effect_status": "started", "timestamp": "2026-10-01T01:00:00+00:00",
        },
        {
            "occurrence_id": occurrence_id, "phase": "report", "status": "fail",
            "effect_status": "unknown", "exit_code": 1, "failure_layer": "entrypoint",
            "timestamp": "2026-10-01T01:01:00+00:00",
        },
    ])
    markers_root = tmp_path / "effect-markers"
    _write_marker(markers_root, occurrence_id, "effect_attempted")

    proof = pre_effect_proof(
        "fundraiser", occurrence_id, events_path=events_path,
        evidence_root=tmp_path / "evidence", markers_root=markers_root,
    )

    assert proof["verified"] is False
    assert proof["classification"] == "post_effect"
    assert proof["reason"] == "post_effect_readback_required"


def test_readonly_replay_keeps_human_required_marker_separate_from_effect_fence(tmp_path):
    occurrence_id = "fundraiser:human-required-1"
    events_path = tmp_path / "events.jsonl"
    _write_events(events_path, [
        {
            "occurrence_id": occurrence_id, "phase": "execute", "status": "running",
            "effect_status": "started", "timestamp": "2026-10-01T02:00:00+00:00",
        },
        {
            "occurrence_id": occurrence_id, "phase": "report", "status": "pass",
            "effect_status": "unknown", "exit_code": 0, "failure_layer": "clean",
            "timestamp": "2026-10-01T02:01:00+00:00",
        },
    ])
    markers_root = tmp_path / "effect-markers"
    _write_marker(markers_root, occurrence_id, "human_required")

    proof = pre_effect_proof(
        "fundraiser", occurrence_id, events_path=events_path,
        evidence_root=tmp_path / "evidence", markers_root=markers_root,
    )

    assert proof["verified"] is False
    assert proof["classification"] == "human_required"
    assert proof["reason"] == "human_required"
