import datetime as dt
import json
from pathlib import Path

from fundraiser_fence_reconcile import pre_effect_proof, reconcile


def _write_events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


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
