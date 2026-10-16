import datetime as dt
import json
from pathlib import Path

from fundraiser_fence_reconcile import pre_effect_proof, reconcile


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


def test_post_effect_verified_marker_stays_fenced_until_provider_readback(tmp_path):
    occurrence_id = "fundraiser:foundersedge-submitted"
    calls = []
    markers_root = tmp_path / "effect-markers"
    _write_marker(markers_root, occurrence_id, "post_effect_verified")

    proof = reconcile(
        occurrence_id,
        events_path=tmp_path / "events.jsonl",
        evidence_root=tmp_path / "evidence",
        markers_root=markers_root,
        fenced_row_fn=lambda _owner, _occurrence: (
            "claimed", dt.datetime(2026, 10, 8, 9, 1, tzinfo=dt.timezone.utc),
        ),
        resolve_fn=lambda *args, **kwargs: calls.append((args, kwargs)) or True,
        resolve=True,
    )

    assert proof["verified"] is False
    assert proof["reason"] == "post_effect_readback_required"
    assert "closed" not in proof
    assert calls == []


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


def _lost_terminal_events(path: Path, occurrence_id: str) -> None:
    _write_events(path, [{
        "loop_id": "fundraiser", "owner_id": "fundraiser", "occurrence_id": occurrence_id,
        "phase": "report", "status": "fail", "effect_status": "unknown",
        "effect_class": "application", "exit_code": 75, "release_sha": "a" * 40,
        "timestamp": "2026-10-10T18:48:24+00:00",
    }])


def test_lost_terminal_row_is_accepted_and_proved_by_its_pre_effect_marker(tmp_path, monkeypatch):
    import fundraiser_fence_reconcile as module
    occurrence_id = "fundraiser:lost-1"
    events_path = tmp_path / "events.jsonl"
    _lost_terminal_events(events_path, occurrence_id)
    markers_root = tmp_path / "effect-markers"
    _write_marker(markers_root, occurrence_id, "pre_effect")
    calls = []

    result = reconcile(
        occurrence_id, events_path=events_path, evidence_root=tmp_path / "evidence",
        markers_root=markers_root,
        fenced_row_fn=lambda owner, occ: module.lost_or_fenced_row(
            owner, occ, row=("released", 1760000000.0, 0), events_path=events_path),
        resolve_fn=lambda *args, **kwargs: calls.append(kwargs) or True,
        resolve=True,
    )

    assert result["verified"] is True and result["closed"] is True
    assert calls[0]["expected_state"] == "released"


def test_released_row_without_terminal_unknown_is_still_rejected(tmp_path):
    import pytest
    import fundraiser_fence_reconcile as module
    with pytest.raises(ValueError):
        module.lost_or_fenced_row("fundraiser", "fundraiser:lost-2", row=("released", 1.0, 0),
                                  events_path=tmp_path / "events.jsonl")


def test_lost_row_accepts_exact_host_pre_effect_receipt(tmp_path):
    import fundraiser_fence_reconcile as module
    occurrence_id = "fundraiser:lost-3"
    receipt_root = tmp_path / "reconciliation"
    receipt_root.mkdir()
    path = receipt_root / "pre-effect-lost-3.json"
    path.write_text(json.dumps({
        "receipt_type": "HOST_PRE_EFFECT_RECONCILIATION", "resolution": "RESOLVED",
        "owner_id": "fundraiser", "occurrence_id": occurrence_id, "verified": True,
        "proof_type": "pre_effect", "evidence_ref": "lm-event://fundraiser/lost-3/x",
    }))
    path.chmod(0o600)

    proof = module.host_pre_effect_receipt_proof(occurrence_id, reconciliation_root=receipt_root)

    assert proof["verified"] is True
    assert proof["evidence_ref"] == "lm-event://fundraiser/lost-3/x"
    assert module.host_pre_effect_receipt_proof("fundraiser:other", reconciliation_root=receipt_root) is None


def _receipts(path: Path, occurrence_id: str, *extra: dict) -> None:
    record = path.parent / "app.json"
    record.write_text(json.dumps({"question_answers": [
        {"question": "Contact email", "answer": "founder@example.com"}]}))
    rows = [
        {"occurrence_id": occurrence_id, "status": "verified_pre_effect_failure", "effect": 0,
         "official_url": "https://nvidia.example/apply"},
        {"occurrence_id": occurrence_id, "status": "submitted_verified",
         "organization": "FoundersEdge", "program": "AI-native software pitch",
         "official_url": "https://apply.foundersedge.com/", "utc_timestamp": "2026-10-08T09:00:52Z",
         "application_record_path": str(record)},
        *extra,
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _post_effect(tmp_path, occurrence_id, search, *extra):
    markers_root = tmp_path / "effect-markers"
    _write_marker(markers_root, occurrence_id, "post_effect_verified")
    receipts = tmp_path / "application-receipts.jsonl"
    _receipts(receipts, occurrence_id, *extra)
    calls = []
    result = reconcile(
        occurrence_id, events_path=tmp_path / "events.jsonl", evidence_root=tmp_path / "evidence",
        markers_root=markers_root, receipts_path=receipts, gmail_search=search,
        fenced_row_fn=lambda _o, _c: ("claimed", dt.datetime(2026, 10, 8, 8, 3, tzinfo=dt.timezone.utc)),
        resolve_fn=lambda *args, **kwargs: calls.append(kwargs) or True,
        resolve=True,
    )
    return result, calls


def test_post_effect_closes_from_provider_mail_after_submission(tmp_path):
    seen = []

    def search(account, query):
        seen.append((account, query))
        return {"messages": [{"id": "m1", "date": "2026-10-09 22:35",
                              "from": "Team <team@foundersedge.com>",
                              "subject": "Update to your FoundersEdge submission"}]}

    result, calls = _post_effect(tmp_path, "fundraiser:fe-1", search)

    assert result["verified"] is True and result["closed"] is True
    assert result["provider_receipt_id"] == "gmail:m1"
    assert seen == [("founder@example.com", "in:anywhere from:foundersedge.com after:2026/10/08")]
    assert calls[0]["official_readback"]()["provider_receipt_id"] == "gmail:m1"


def test_post_effect_without_provider_mail_stays_fenced(tmp_path):
    result, calls = _post_effect(tmp_path, "fundraiser:fe-2", lambda a, q: {"messages": []})
    assert result["verified"] is False and calls == []
    assert result["reason"] == "provider_readback_absent:foundersedge.com"


def test_post_effect_with_unresolved_sibling_receipt_stays_fenced(tmp_path):
    result, calls = _post_effect(
        tmp_path, "fundraiser:fe-3",
        lambda a, q: {"messages": [{"id": "m1", "date": "2026-10-09 22:35"}]},
        {"occurrence_id": "fundraiser:fe-3", "status": "submit_unknown", "effect": 1,
         "official_url": "https://a16z.com/"},
    )
    assert result["verified"] is False and calls == []
    assert result["reason"] == "receipt_effect_unresolved:submit_unknown"


def test_post_effect_with_another_submission_to_the_same_domain_stays_fenced(tmp_path):
    result, calls = _post_effect(
        tmp_path, "fundraiser:fe-4",
        lambda a, q: {"messages": [{"id": "m1", "date": "2026-10-09 22:35"}]},
        {"occurrence_id": "fundraiser:older", "status": "submitted_verified",
         "official_url": "https://www.foundersedge.com/apply"},
    )
    assert result["verified"] is False and calls == []
    assert result["reason"] == "provider_readback_ambiguous:foundersedge.com"


def test_post_effect_on_a_shared_form_host_fails_closed(tmp_path):
    import fundraiser_fence_reconcile as module
    seen = []
    receipts = tmp_path / "application-receipts.jsonl"
    receipts.write_text(json.dumps({
        "occurrence_id": "fundraiser:fe-5", "status": "submitted_verified",
        "organization": "Acme Ventures", "program": "Pitch",
        "official_url": "https://app.notion.com/acme-apply", "utc_timestamp": "2026-10-08T09:00:52Z",
    }) + "\n")
    for url in ("https://app.notion.com/x", "https://tally.so/r/x", "https://form.fillout.com/t/x",
                "https://airtable.com/app/x", "https://acme.decilehub.com/apply"):
        assert module._mail_domain(url) is None

    result = module.post_effect_readback(
        "fundraiser:fe-5", receipts_path=receipts,
        search=lambda a, q: seen.append(q) or {"messages": [{"id": "m1", "date": "2026-10-09 22:35"}]})

    assert result["verified"] is False and seen == []
    assert result["reason"] == "provider_readback_unbindable"


def test_post_effect_mail_without_org_or_program_in_subject_is_not_a_receipt(tmp_path):
    result, calls = _post_effect(
        tmp_path, "fundraiser:fe-6",
        lambda a, q: {"messages": [{"id": "m1", "date": "2026-10-09 22:35",
                                    "subject": "Your weekly digest"}]})
    assert result["verified"] is False and calls == []
    assert result["reason"] == "provider_readback_absent:foundersedge.com"
