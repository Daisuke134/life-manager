import hashlib
import json
from types import SimpleNamespace

from skills.earn.gig.scripts import paid_direct as paid


def test_terminal_reconciliation_is_one_rotating_candidate_per_wake(
    tmp_path, monkeypatch
):
    projects = tmp_path / "projects"
    evidence = tmp_path / "evidence"
    for room in ("100", "200", "300"):
        root = projects / room
        root.mkdir(parents=True)
        (root / "state.json").write_text(json.dumps({
            "talkroom_id": room, "buyer": f"buyer-{room}",
        }))
    calls = []
    monkeypatch.setattr(paid, "_collector", lambda *_args: ["collector"])

    def fail(*_args, **_kwargs):
        calls.append(True)
        raise paid.Failure("terminal_reconciliation")

    monkeypatch.setattr(paid, "_run", fail)
    monkeypatch.setattr(paid.subprocess, "run", lambda *_args, **_kwargs: None)
    args = SimpleNamespace(
        projects_root=projects,
        evidence_dir=evidence,
        cdp_helper=tmp_path / "cdp_default_tab.py",
        cdp_lock_dir=tmp_path / "cdp-locks",
    )

    result = paid._reconcile_absent_talkrooms(args, [])

    assert len(calls) == 1
    assert len(result["results"]) == 1
    assert result["remaining_candidates"] == 2


def test_terminal_reconciliation_budget_stays_below_half_paid_cadence():
    worst_case = paid.PAID_TERMINAL_RECONCILES_PER_WAKE * (
        paid.TERMINAL_RECONCILIATION_TIMEOUT_SECONDS
        + paid.TERMINAL_RECONCILIATION_CLEANUP_TIMEOUT_SECONDS
    )
    assert worst_case < 150


def test_official_cancellation_closes_project_without_an_effect(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    evidence = tmp_path / "evidence"
    root = projects / "18184558"
    paid.project_ledger.init_project(projects, "18184558", "coconala", {
        "talkroom_id": "18184558", "next_action": "delivery_evidence",
    })
    snapshot = evidence / "terminal-reconciliation" / "18184558" / "snapshot.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("{}")
    monkeypatch.setattr(paid, "_collector", lambda *_args: ["collector"])
    monkeypatch.setattr(paid, "_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(paid.subprocess, "run", lambda *_args, **_kwargs: None)
    original_load = paid._load
    monkeypatch.setattr(paid, "_load", lambda path: (
        {"talkroom": {"talkroom_id": "18184558", "transaction_state": "キャンセル",
                      "talkroom_state": "キャンセル"}}
        if path.name == "snapshot.json" else original_load(path)
    ))
    args = SimpleNamespace(projects_root=projects, evidence_dir=evidence,
                           cdp_helper=tmp_path / "cdp.py", cdp_lock_dir=tmp_path / "locks")

    result = paid._reconcile_absent_talkrooms(args, [])

    state = json.loads((root / "state.json").read_text())
    receipt = json.loads((root / "project-terminal.json").read_text())
    assert result["results"][0]["terminal_receipt_written"] is True
    assert state["next_action"] == "terminal_cancelled"
    assert state["work_state"] == "CANCELLED"
    assert receipt["transaction_state"] == receipt["talkroom_state"] == "キャンセル"
    assert receipt["state_sha256"] == hashlib.sha256((root / "state.json").read_bytes()).hexdigest()
    accepted, reason = paid.project_janitor._terminal_receipt(root, root / "state.json")
    assert accepted == receipt
    assert reason == ""

    events_before_replay = (root / "events.jsonl").read_bytes()
    replay = paid._reconcile_absent_talkrooms(args, [])
    assert replay["results"] == []
    assert replay["remaining_candidates"] == 0
    assert (root / "events.jsonl").read_bytes() == events_before_replay
