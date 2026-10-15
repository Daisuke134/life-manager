from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/mercor/scripts/reconcile_fence_readback.py"
APP = "mercor-revenue-application"
REPLY = "mercor-revenue-reply"
PAID = "mercor-revenue-paid"


def load():
    spec = importlib.util.spec_from_file_location("mercor_fence_readback_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def event(owner, run_id, phase, timestamp, **extra):
    row = {"loop_id": owner, "run_id": run_id, "phase": phase,
           "status": "running" if phase == "execute" else "fail",
           "timestamp": timestamp, "evidence_refs": []}
    row.update(extra)
    return row


def write_events(root: Path, rows) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "events.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return root


class Search:
    def __init__(self, result):
        self.result = result
        self.queries = []

    def __call__(self, query):
        self.queries.append(query)
        return self.result


def test_application_claim_run_without_submission_mail_is_pre_effect(tmp_path):
    module = load()
    occurrence = f"{APP}:run-a"
    root = write_events(tmp_path / "application", [
        event(APP, "run-a", "execute", "2026-10-01T00:00:00+00:00",
              occurrence_id=occurrence),
        event(APP, "run-a", "report", "2026-10-01T00:08:00+00:00",
              occurrence_id=occurrence, release_sha="a" * 40),
    ])
    search = Search({"messages": []})
    calls = []

    result = module.reconcile(
        state_root=root, owner=APP, occurrence=occurrence, resolve=True,
        search=search,
        resolver=lambda owner, occ, *, pre_effect_readback, expected_state:
            calls.append((owner, occ, pre_effect_readback(), expected_state)) or True,
    )

    start = 1790812800  # 2026-10-01T00:00:00Z
    assert search.queries == [
        f'from:mercor.com subject:"Application Submitted" after:{start - 60} '
        f'before:{start + 480 + 600}'
    ]
    assert result["resolved"] is True
    assert result["proof_type"] == "pre_effect"
    assert result["release_sha"] == "a" * 40
    assert calls[0][0:2] == (APP, occurrence)
    assert calls[0][2]["evidence_ref"].startswith("gmail-search://")
    assert calls[0][3] == "claimed"


def test_any_submission_mail_or_incomplete_search_keeps_application_fenced(tmp_path):
    module = load()
    occurrence = f"{APP}:run-a"
    root = write_events(tmp_path / "application", [
        event(APP, "run-a", "execute", "2026-10-01T00:00:00+00:00",
              occurrence_id=occurrence),
        event(APP, "run-a", "report", "2026-10-01T00:08:00+00:00",
              occurrence_id=occurrence),
    ])
    for result in ({"messages": [{"id": "m1"}]},
                   {"messages": [], "nextPageToken": "next"},
                   None, {"messages": None}):
        proof, reason = module.find_proof(root, APP, occurrence, search=Search(result))
        assert proof is None
        assert reason == "official_readback_not_absent"


def test_legacy_journal_without_occurrence_binding_reads_back_until_now(tmp_path):
    module = load()
    occurrence = f"{APP}:run-a"
    root = write_events(tmp_path / "application", [
        event(APP, "run-a", "execute", "2026-10-01T00:00:00+00:00"),
        event(APP, "run-a", "report", "2026-10-01T00:08:00+00:00"),
    ])
    search = Search({"messages": []})

    proof, reason = module.find_proof(root, APP, occurrence, search=search)

    assert reason == "ok" and proof["window"] == [1790812800.0, None]
    assert search.queries == [
        f'from:mercor.com subject:"Application Submitted" after:{1790812800 - 60}'
    ]


def test_reply_uses_the_later_run_that_claimed_the_occurrence(tmp_path):
    module = load()
    occurrence = f"{REPLY}:old-run"
    root = write_events(tmp_path / "reply", [
        event(REPLY, "old-run", "execute", "2026-09-01T00:00:00+00:00",
              occurrence_id=f"{REPLY}:old-run"),
        event(REPLY, "old-run", "report", "2026-09-01T00:01:00+00:00",
              occurrence_id=f"{REPLY}:older", status="pass"),
        event(REPLY, "claimer", "execute", "2026-10-01T00:00:00+00:00",
              occurrence_id=f"{REPLY}:claimer"),
        event(REPLY, "claimer", "report", "2026-10-01T00:00:04+00:00",
              occurrence_id=occurrence,
              evidence_refs=[f"lm-occurrence://{REPLY}/old-run/claim"]),
    ])
    search = Search({"messages": []})

    proof, reason = module.find_proof(root, REPLY, occurrence, search=search)

    assert reason == "ok"
    assert search.queries == [f"in:sent after:{1790812800 - 60} before:{1790812804 + 600}"]
    assert proof["window"] == [1790812800.0, 1790812804.0]


def test_ambiguous_or_unbound_claim_run_keeps_fenced(tmp_path):
    module = load()
    occurrence = f"{REPLY}:old-run"
    claim = [f"lm-occurrence://{REPLY}/old-run/claim"]
    ambiguous = write_events(tmp_path / "a", [
        event(REPLY, "x", "execute", "2026-10-01T00:00:00+00:00", occurrence_id=f"{REPLY}:x"),
        event(REPLY, "x", "report", "2026-10-01T00:00:04+00:00", occurrence_id=occurrence,
              evidence_refs=claim),
        event(REPLY, "y", "execute", "2026-10-02T00:00:00+00:00", occurrence_id=f"{REPLY}:y"),
        event(REPLY, "y", "report", "2026-10-02T00:00:04+00:00", occurrence_id=occurrence,
              evidence_refs=claim),
    ])
    unbound = write_events(tmp_path / "b", [
        event(REPLY, "old-run", "execute", "2026-10-01T00:00:00+00:00",
              occurrence_id=f"{REPLY}:old-run"),
        event(REPLY, "old-run", "report", "2026-10-01T00:00:04+00:00",
              occurrence_id=f"{REPLY}:older", status="pass"),
    ])
    for root in (ambiguous, unbound):
        search = Search({"messages": []})
        proof, _ = module.find_proof(root, REPLY, occurrence, search=search)
        assert proof is None and search.queries == []


def write_snapshot(root: Path, observed_at: str, mtime: float) -> None:
    path = root / "paid-official-snapshot.json"
    path.write_text(json.dumps({"version": 1, "observed_at": observed_at, "contracts": []}),
                    encoding="utf-8")
    os.utime(path, (mtime, mtime))


def paid_root(tmp_path: Path, previous_release: str = "b" * 40) -> Path:
    occurrence = f"{PAID}:run-p"
    return write_events(tmp_path / "mercor", [
        # The previous wake on the same release wrote the snapshot, so that
        # release gates its kernel on a fresh snapshot.
        event(PAID, "run-prev", "execute", "2026-09-30T23:54:50+00:00",
              occurrence_id=f"{PAID}:run-prev", release_sha=previous_release),
        event(PAID, "run-prev", "report", "2026-09-30T23:55:10+00:00", status="pass",
              occurrence_id=f"{PAID}:run-prev", release_sha=previous_release),
        event(PAID, "run-p", "execute", "2026-10-01T00:00:00+00:00",
              occurrence_id=occurrence, release_sha="b" * 40),
        event(PAID, "run-p", "report", "2026-10-01T00:00:11+00:00",
              occurrence_id=occurrence, release_sha="b" * 40),
    ])


def test_paid_kernel_never_started_when_its_snapshot_was_not_refreshed(tmp_path):
    module = load()
    occurrence = f"{PAID}:run-p"
    root = paid_root(tmp_path)
    write_snapshot(root, "2026-09-30T23:55:00+00:00", 1790812500)
    search = Search({"messages": []})

    proof, reason = module.find_proof(root, PAID, occurrence, search=search)

    assert reason == "ok" and proof["proof_type"] == "pre_effect"
    assert proof["evidence_ref"].startswith("lm-mercor-paid-snapshot://")
    assert search.queries == []


def test_paid_snapshot_refreshed_in_run_or_existing_marker_keeps_fenced(tmp_path):
    module = load()
    occurrence = f"{PAID}:run-p"
    root = paid_root(tmp_path)
    write_snapshot(root, "2026-10-01T00:00:05+00:00", 1790812805)
    assert module.find_proof(root, PAID, occurrence)[0] is None

    write_snapshot(root, "2026-09-30T23:55:00+00:00", 1790812500)
    digest = hashlib.sha256(occurrence.encode()).hexdigest()
    marker = root / "shared-paid" / "runs" / f"{digest}.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"version": 1, "occurrence_id": occurrence,
                                  "status": "effect_started"}), encoding="utf-8")
    assert module.find_proof(root, PAID, occurrence) == (None, "paid_run_marker_present")


def test_paid_snapshot_written_by_another_release_keeps_fenced(tmp_path):
    # Releases before the snapshot gate exec the kernel directly, so an old
    # snapshot proves nothing unless the claim run's own release wrote it.
    module = load()
    root = paid_root(tmp_path, previous_release="c" * 40)
    write_snapshot(root, "2026-09-30T23:55:00+00:00", 1790812500)

    assert module.find_proof(root, PAID, f"{PAID}:run-p") == (
        None, "paid_snapshot_writer_unproven")


def test_paid_owner_runs_kernel_only_after_a_fresh_snapshot():
    text = (ROOT / "skills/earn/mercor/scripts/paid-owner").read_text(encoding="utf-8")
    snapshot = text.index("job_search_loop.mercor_paid_snapshot")
    failure_exit = text.index("exit 75", snapshot)
    kernel = text.index("exec ")
    assert snapshot < failure_exit < kernel
    assert text.count("paid_kernel.py") == 1


def test_existing_pre_effect_hint_still_closes_without_provider_read(tmp_path):
    module = load()
    occurrence = f"{APP}:run-a"
    root = tmp_path / "application"
    marker = root / "loop-tmp" / APP / "run-a" / "entrypoint-result.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"status": "pre_effect_failure", "effect": 0}), encoding="utf-8")
    marker.chmod(0o600)
    search = Search({"messages": []})

    proof, reason = module.find_proof(root, APP, occurrence, search=search)

    assert reason == "ok" and proof["evidence_ref"].startswith("lm-pre-effect://")
    assert search.queries == []
