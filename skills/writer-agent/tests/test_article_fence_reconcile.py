"""article-daily fence reconcile: require publish proof or exact historical gate-stop proof.

2026-10-09: a single claimed+effect_unknown admission row from 9/29 10:01 JST kept article-daily
deferred (resource_effect_unknown) for 10 days; the run had published to note and Substack.  A
time window is used only to PAIR a fence with a publish, never to infer that nothing happened.
"""

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "article_fence_reconcile.py"
spec = importlib.util.spec_from_file_location("article_fence_reconcile", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules["article_fence_reconcile"] = mod

OWNER = "article-daily"
QUEUED = datetime(2026, 9, 29, 1, 1, 24, tzinfo=timezone.utc).timestamp()   # 10:01:24 JST
OCC = f"{OWNER}:18d9a4f19ed7acb8-67928"


def _load():
    spec.loader.exec_module(mod)
    return mod


def _articles(tmp_path, rows):
    p = tmp_path / "articles.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def _row(run_id, ts, url, platform="note"):
    return {"ts": ts, "run_id": run_id, "platform": platform, "lang": "ja", "live_url": url}


HISTORICAL_OCCURRENCE = "article-daily:18dcb160db0ac660-67443"
HISTORICAL_RUNTIME_RUN_ID = "18dcb160db0ac660-67443"
HISTORICAL_WRITER_RUN_ID = "20261008-232303"
HISTORICAL_QUEUED_AT = 1791501539.804287
HISTORICAL_START_EVENT_ID = "f788745c9942592c5dda4bbe"
HISTORICAL_TERMINAL_EVENT_ID = "4d8c87b93955946219a77aeb"


def _historical_gate_stop_fixture(tmp_path, monkeypatch, m, *, event_release_sha=None,
                                  add_generation_artifact=False):
    writer_root = tmp_path / "writer"
    run_dir = writer_root / "runs" / HISTORICAL_WRITER_RUN_ID
    gates = run_dir / "gates"
    gates.mkdir(parents=True)
    (gates / "product-selection.json").write_text("{}\n", encoding="utf-8")
    (gates / "strategy-consumption.json").write_text("{}\n", encoding="utf-8")
    (run_dir / "git-hash.txt").write_text("harness_git_hash=UNKNOWN\n", encoding="utf-8")
    if add_generation_artifact:
        (gates / "generation-state.json").write_text("{}\n", encoding="utf-8")

    source = """#!/bin/bash
# DEMAND AUTHORITY PREFLIGHT
if ! python3 \"$DEMAND_AUTHORITY_SCRIPT\" --demand-mode required; then
  echo \"=== article-daily demand authority blocked generation; pending claim-loop supply ===\" >>\"$LOG\"
  telegram_notify \"Writer pending: no provider invocation occurred.\" >>\"$LOG\" 2>&1 || true
  exit 75
fi
PROMPT='Run ONE daily Writer Agent article pass'
"""
    source_repo = tmp_path / "source"
    entrypoint = source_repo / "skills" / "writer-agent" / "article-daily.sh"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text(source, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(source_repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(source_repo), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(source_repo), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(source_repo), "add", "skills/writer-agent/article-daily.sh"], check=True)
    subprocess.run(["git", "-C", str(source_repo), "commit", "-qm", "gate fixture"], check=True)
    source_sha = subprocess.check_output(
        ["git", "-C", str(source_repo), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(source_repo), "update-ref", "refs/remotes/origin/main", source_sha], check=True)

    start = {
        "event_id": HISTORICAL_START_EVENT_ID,
        "loop_id": "article-daily",
        "owner_id": "article-daily",
        "run_id": HISTORICAL_RUNTIME_RUN_ID,
        "occurrence_id": HISTORICAL_OCCURRENCE,
        "release_sha": source_sha,
        "timestamp": "2026-10-08T23:23:01.360937+00:00",
        "phase": "execute",
        "status": "running",
        "effect_class": "publish",
        "effect_status": "started",
    }
    terminal = {
        "event_id": HISTORICAL_TERMINAL_EVENT_ID,
        "loop_id": "article-daily",
        "owner_id": "article-daily",
        "run_id": HISTORICAL_RUNTIME_RUN_ID,
        "occurrence_id": HISTORICAL_OCCURRENCE,
        "release_sha": event_release_sha or source_sha,
        "timestamp": "2026-10-08T23:23:08.513757+00:00",
        "phase": "report",
        "exit_code": 75,
        "status": "fail",
        "effect_class": "publish",
        "effect_status": "unknown",
        "error_class": "entrypoint_exit_75",
        "next_action": "official_readback_required",
    }
    start_line = json.dumps(start)
    terminal_line = json.dumps(terminal)
    events_path = writer_root / "events.jsonl"
    events_path.write_text(start_line + "\n" + terminal_line + "\n", encoding="utf-8")
    (writer_root / "articles.jsonl").write_text("", encoding="utf-8")
    (writer_root / "logs").mkdir()
    run_log = (
        "=== article-daily start control: completed prior run released a new "
        f"run={HISTORICAL_WRITER_RUN_ID} reason=no-same-jst-day-run 2026-10-09 08:23:03 JST ===\n"
        "demand topic queue contains non-paid-demand cards: marketing-intel-48c88abc36f3.md\n"
        "=== article-daily demand authority blocked generation; pending claim-loop supply ==="
    )
    (writer_root / "logs" / "article-daily.log").write_text(run_log + "\n", encoding="utf-8")

    expected = {
        "runtime_run_id": HISTORICAL_RUNTIME_RUN_ID,
        "writer_run_id": HISTORICAL_WRITER_RUN_ID,
        "release_sha": source_sha,
        "entrypoint": "skills/writer-agent/article-daily.sh",
        "entrypoint_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "start_event_id": HISTORICAL_START_EVENT_ID,
        "terminal_event_id": HISTORICAL_TERMINAL_EVENT_ID,
        "event_hashes": {
            HISTORICAL_START_EVENT_ID: hashlib.sha256(start_line.encode()).hexdigest(),
            HISTORICAL_TERMINAL_EVENT_ID: hashlib.sha256(
                json.dumps({**terminal, "release_sha": source_sha}).encode()
            ).hexdigest(),
        },
        "run_artifacts": {
            path.relative_to(run_dir).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted([
                run_dir / "git-hash.txt",
                gates / "product-selection.json",
                gates / "strategy-consumption.json",
            ])
        },
        "article_log_segment_sha256": hashlib.sha256(run_log.encode("utf-8")).hexdigest(),
        "queued_at": HISTORICAL_QUEUED_AT,
        "gate_error": "demand topic queue contains non-paid-demand cards: "
                      "marketing-intel-48c88abc36f3.md",
        "gate_terminal": "article-daily demand authority blocked generation; "
                         "pending claim-loop supply",
    }
    monkeypatch.setattr(m, "HISTORICAL_GATE_STOP_PROOFS", {
        HISTORICAL_OCCURRENCE: expected,
    }, raising=False)
    return writer_root, source_repo


def test_gate_stopped_historical_occurrence_closes_from_bound_no_dispatch_proof(
        tmp_path, monkeypatch):
    m = _load()
    writer_root, source_repo = _historical_gate_stop_fixture(tmp_path, monkeypatch, m)
    events_path = writer_root / "events.jsonl"
    original_events = events_path.read_bytes()
    calls = []

    def resolve_historical(owner, occurrence, *, no_dispatch_proof, expected_state):
        calls.append((owner, occurrence, no_dispatch_proof(), expected_state))
        return True

    result = m.reconcile(
        HISTORICAL_OCCURRENCE,
        queued_at=HISTORICAL_QUEUED_AT,
        state="claimed",
        articles_path=writer_root / "articles.jsonl",
        fetch_status=lambda _url: 0,
        resolver=resolve_historical,
        resolve=True,
        now=HISTORICAL_QUEUED_AT + 3600,
        writer_root=writer_root,
        source_repo=source_repo,
    )

    assert result["status"] == "no_dispatch_proven" and result["closed"] is True
    assert calls[0][0:2] == ("article-daily", HISTORICAL_OCCURRENCE)
    assert calls[0][2]["proof_type"] == "historical_writer_gate_stop_no_dispatch"
    assert calls[0][2]["runtime_run_id"] == HISTORICAL_RUNTIME_RUN_ID
    assert calls[0][2]["writer_run_id"] == HISTORICAL_WRITER_RUN_ID
    assert events_path.read_bytes() == original_events
    receipt = writer_root / "fence-reconciliation" / "article-daily-18dcb160db0ac660-67443.json"
    assert json.loads(receipt.read_text(encoding="utf-8"))["proof_type"] == \
        "historical_writer_gate_stop_no_dispatch"


def test_gate_stop_proof_rejects_release_mismatch_or_generation_artifact(tmp_path, monkeypatch):
    for name, kwargs in (
        ("release-mismatch", {"event_release_sha": "f" * 40}),
        ("generation-artifact", {"add_generation_artifact": True}),
    ):
        m = _load()
        case_root = tmp_path / name
        case_root.mkdir()
        writer_root, source_repo = _historical_gate_stop_fixture(
            case_root, monkeypatch, m, **kwargs)
        called = []
        result = m.reconcile(
            HISTORICAL_OCCURRENCE,
            queued_at=HISTORICAL_QUEUED_AT,
            state="claimed",
            articles_path=writer_root / "articles.jsonl",
            fetch_status=lambda _url: 0,
            resolver=lambda *_args, **_kwargs: called.append(True) or True,
            resolve=True,
            now=HISTORICAL_QUEUED_AT + 3600,
            writer_root=writer_root,
            source_repo=source_repo,
        )
        assert result["status"] == "inconclusive" and result["closed"] is False
        assert called == []


def test_gate_stop_proof_requires_source_commit_to_be_on_origin_main(tmp_path, monkeypatch):
    m = _load()
    writer_root, source_repo = _historical_gate_stop_fixture(tmp_path, monkeypatch, m)
    subprocess.run(
        ["git", "-C", str(source_repo), "update-ref", "-d", "refs/remotes/origin/main"],
        check=True,
    )
    called = []
    result = m.reconcile(
        HISTORICAL_OCCURRENCE,
        queued_at=HISTORICAL_QUEUED_AT,
        state="claimed",
        articles_path=writer_root / "articles.jsonl",
        fetch_status=lambda _url: 0,
        resolver=lambda *_args, **_kwargs: called.append(True) or True,
        resolve=True,
        now=HISTORICAL_QUEUED_AT + 3600,
        writer_root=writer_root,
        source_repo=source_repo,
    )
    assert result["status"] == "inconclusive" and result["closed"] is False
    assert called == []


CURRENT_OCCURRENCE = "article-daily:18dcb869e78c3c38-58827"
CURRENT_RUNTIME_RUN_ID = "18dcb869e78c3c38-58827"
CURRENT_WRITER_RUN_ID = "20261008-232303"
CURRENT_QUEUED_AT = 1791509208.924928


def _tree_manifest(root):
    manifest = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise AssertionError(f"unexpected symlink in fixture: {path}")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            manifest.append({"path": relative, "type": "directory"})
        else:
            manifest.append({"path": relative, "type": "file",
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return manifest


def _current_generation_gate_stop_fixture(tmp_path, monkeypatch, m):
    writer_root, source_repo = _historical_gate_stop_fixture(tmp_path, monkeypatch, m)
    run_dir = writer_root / "runs" / CURRENT_WRITER_RUN_ID
    gates = run_dir / "gates"
    broker = gates / "judge-broker"
    for directory in (broker / "requests", broker / "responses", broker / "done"):
        directory.mkdir(parents=True)
    (run_dir / "article-daily-prompt.txt").write_text("immutable prompt\n", encoding="utf-8")
    (gates / ".generation-state.json.lock").write_text("", encoding="utf-8")
    (broker / "heartbeat").write_text("", encoding="utf-8")

    source = """#!/bin/bash
python3 \"$GENERATION_STATE\" \"${GENERATION_ARGS[@]}\" init || exit 1
run_model_pass() { python3 \"$ARTICLE_ROOT/runtime/model-runner.sh\" agent; }
run_model_pass
"""
    entrypoint = source_repo / "skills" / "writer-agent" / "article-daily.sh"
    entrypoint.write_text(source, encoding="utf-8")
    subprocess.run(["git", "-C", str(source_repo), "add", "skills/writer-agent/article-daily.sh"], check=True)
    subprocess.run(["git", "-C", str(source_repo), "commit", "-qm", "generation gate fixture"], check=True)
    source_sha = subprocess.check_output(
        ["git", "-C", str(source_repo), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(source_repo), "update-ref",
                    "refs/remotes/origin/main", source_sha], check=True)

    start = {
        "event_id": "start-current", "loop_id": "article-daily", "owner_id": "article-daily",
        "run_id": CURRENT_RUNTIME_RUN_ID, "occurrence_id": CURRENT_OCCURRENCE,
        "release_sha": source_sha, "timestamp": "2026-10-09T01:31:56.802640+00:00",
        "phase": "execute", "status": "running", "effect_class": "publish",
        "effect_status": "started",
    }
    terminal = {
        "event_id": "terminal-current", "loop_id": "article-daily", "owner_id": "article-daily",
        "run_id": CURRENT_RUNTIME_RUN_ID, "occurrence_id": CURRENT_OCCURRENCE,
        "release_sha": source_sha, "timestamp": "2026-10-09T01:32:05.470204+00:00",
        "phase": "report", "exit_code": 1, "status": "fail", "effect_class": "publish",
        "effect_status": "unknown", "error_class": "entrypoint_exit_1",
        "next_action": "official_readback_required",
    }
    start_line, terminal_line = json.dumps(start), json.dumps(terminal)
    (writer_root / "events.jsonl").write_text(start_line + "\n" + terminal_line + "\n", encoding="utf-8")
    run_log = (
        f"=== article-daily start control: completed prior run released a new run={CURRENT_WRITER_RUN_ID} "
        "reason=no-same-jst-day-run 2026-10-09 10:31:56 JST ===\n"
        "GenerationInvariant: generated-or-staged-artifacts:gates/product-selection.json\n"
        "=== article-daily done rc=1 ==="
    )
    (writer_root / "logs" / "article-daily.log").write_text(
        run_log + "\narticle-daily start control: next run\n", encoding="utf-8")

    expected = dict(next(iter(m.HISTORICAL_GATE_STOP_PROOFS.values())))
    expected.update({
        "runtime_run_id": CURRENT_RUNTIME_RUN_ID, "writer_run_id": CURRENT_WRITER_RUN_ID,
        "release_sha": source_sha,
        "entrypoint_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "start_event_id": "start-current", "terminal_event_id": "terminal-current",
        "event_hashes": {
            "start-current": hashlib.sha256(start_line.encode()).hexdigest(),
            "terminal-current": hashlib.sha256(terminal_line.encode()).hexdigest(),
        },
        "run_tree": _tree_manifest(run_dir),
        "article_log_segment_sha256": hashlib.sha256(run_log.encode("utf-8")).hexdigest(),
        "queued_at": CURRENT_QUEUED_AT,
        "gate_error": "GenerationInvariant: generated-or-staged-artifacts:gates/product-selection.json",
        "gate_terminal": "article-daily done rc=1",
    })
    monkeypatch.setattr(m, "HISTORICAL_GATE_STOP_PROOFS", {
        CURRENT_OCCURRENCE: expected,
    }, raising=False)
    return writer_root, source_repo


def test_generation_init_failure_with_empty_broker_proves_no_dispatch(tmp_path, monkeypatch):
    m = _load()
    writer_root, source_repo = _current_generation_gate_stop_fixture(tmp_path, monkeypatch, m)
    calls = []

    def resolve(owner, occurrence, *, no_dispatch_proof, expected_state):
        calls.append((owner, occurrence, no_dispatch_proof(), expected_state))
        return True

    result = m.reconcile(
        CURRENT_OCCURRENCE, queued_at=CURRENT_QUEUED_AT, state="claimed",
        articles_path=writer_root / "articles.jsonl", fetch_status=lambda _url: 0,
        resolver=resolve, resolve=True, now=CURRENT_QUEUED_AT + 3600,
        writer_root=writer_root, source_repo=source_repo,
    )
    assert result["status"] == "no_dispatch_proven" and result["closed"] is True
    proof = calls[0][2]
    assert proof["runtime_run_id"] == CURRENT_RUNTIME_RUN_ID
    assert proof["writer_run_id"] == CURRENT_WRITER_RUN_ID
    assert any(item["path"] == "gates/judge-broker/requests" for item in proof["run_tree"])
    assert any(item["path"] == "gates/judge-broker/responses" for item in proof["run_tree"])
    assert not any(item["path"].startswith("gates/judge-broker/requests/")
                   or item["path"].startswith("gates/judge-broker/responses/")
                   for item in proof["run_tree"])


def test_generation_init_proof_rejects_any_broker_request(tmp_path, monkeypatch):
    m = _load()
    writer_root, source_repo = _current_generation_gate_stop_fixture(tmp_path, monkeypatch, m)
    request = writer_root / "runs" / CURRENT_WRITER_RUN_ID / "gates" / "judge-broker" / "requests" / "request.json"
    request.write_text('{"id":"request"}\n', encoding="utf-8")
    calls = []
    result = m.reconcile(
        CURRENT_OCCURRENCE, queued_at=CURRENT_QUEUED_AT, state="claimed",
        articles_path=writer_root / "articles.jsonl", fetch_status=lambda _url: 0,
        resolver=lambda *_args, **_kwargs: calls.append(True) or True,
        resolve=True, now=CURRENT_QUEUED_AT + 3600,
        writer_root=writer_root, source_repo=source_repo,
    )
    assert result["status"] == "inconclusive" and result["closed"] is False
    assert calls == []


def test_publish_started_within_the_window_with_a_live_url_closes_as_effected(tmp_path):
    m = _load()
    arts = _articles(tmp_path, [
        _row("20260929-010128", "2026-09-29T02:44:15Z", "https://note.com/x/n/1"),
        _row("20260929-010128", "2026-09-29T02:50:56Z", "https://x.substack.com/p/a", "substack"),
    ])
    closed = []
    result = m.reconcile(OCC, queued_at=QUEUED, state="claimed", articles_path=arts,
                         fetch_status=lambda url: 200,
                         resolver=lambda owner, occ, **k: closed.append(occ) or True, resolve=True)
    assert result["status"] == "effected" and result["closed"] is True and closed == [OCC]
    assert result["provider_receipt_id"].startswith("https://")


def test_without_resolve_nothing_is_written(tmp_path):
    m = _load()
    arts = _articles(tmp_path, [_row("20260929-010128", "2026-09-29T02:44:15Z", "https://note.com/x/n/1")])
    called = []
    result = m.reconcile(OCC, queued_at=QUEUED, state="claimed", articles_path=arts,
                         fetch_status=lambda url: 200,
                         resolver=lambda *a, **k: called.append(1) or True, resolve=False)
    assert result["status"] == "effected" and result["closed"] is False and called == []


def test_a_dead_url_a_far_run_or_no_run_never_closes(tmp_path):
    m = _load()
    live = [_row("20260929-010128", "2026-09-29T02:44:15Z", "https://note.com/x/n/1")]
    far = [_row("20260928-010128", "2026-09-28T02:44:15Z", "https://note.com/x/n/9")]
    for rows, fetch in ((live, lambda u: 404), (far, lambda u: 200), ([], lambda u: 200)):
        arts = _articles(tmp_path, rows)
        called = []
        result = m.reconcile(OCC, queued_at=QUEUED, state="claimed", articles_path=arts, fetch_status=fetch,
                             resolver=lambda *a, **k: called.append(1) or True, resolve=True)
        assert result["status"] == "inconclusive" and result["closed"] is False and called == []


def test_a_fence_younger_than_the_minimum_age_is_left_alone(tmp_path):
    m = _load()
    arts = _articles(tmp_path, [_row("20260929-010128", "2026-09-29T02:44:15Z", "https://note.com/x/n/1")])
    result = m.reconcile(OCC, queued_at=QUEUED, state="claimed", articles_path=arts,
                         fetch_status=lambda u: 200, resolver=lambda *a, **k: True, resolve=True,
                         now=QUEUED + 600)
    assert result["status"] == "inconclusive" and result["reason"] == "fence_too_young"


def test_only_the_article_daily_owner_is_accepted(tmp_path):
    m = _load()
    arts = _articles(tmp_path, [])
    result = m.reconcile("other-loop:18d9a4f19ed7acb8-67928", queued_at=QUEUED, state="claimed",
                         articles_path=arts, fetch_status=lambda u: 200,
                         resolver=lambda *a, **k: True, resolve=True)
    assert result["status"] == "inconclusive" and result["reason"] == "owner_not_allowlisted"


def _run_dir(runs, run_id, files):
    d = runs / run_id
    (d / "gates").mkdir(parents=True)
    for name in files:
        (d / name).write_text("x")
    return d


GATE_QUEUED = datetime(2026, 10, 8, 23, 18, 59, tzinfo=timezone.utc).timestamp()   # 08:18:59 JST
# Keep the generic paired-run proof test separate from the one historical occurrence
# that requires the stronger source/event/log hash contract above.
GATE_OCC = f"{OWNER}:generic-gate-stop"


def _pre(m, tmp_path, runs, rows=(), resolve=True, closed=None):
    closed = [] if closed is None else closed
    return m.reconcile(GATE_OCC, queued_at=GATE_QUEUED, state="claimed", articles_path=_articles(tmp_path, list(rows)),
                       runs_root=runs, fetch_status=lambda u: 200,
                       pre_effect_resolver=lambda owner, occ, **k: closed.append((occ, k["pre_effect_readback"]())) or True,
                       resolve=resolve), closed


def test_a_run_that_stopped_at_the_gate_closes_as_pre_effect(tmp_path):
    m = _load()
    runs = tmp_path / "runs"
    _run_dir(runs, "20261008-232303", ["git-hash.txt"])        # 08:23:03 JST, 4 min after the claim
    result, closed = _pre(m, tmp_path, runs)
    assert result["status"] == "pre_effect" and result["closed"] is True
    assert result["owner_id"] == OWNER and result["verified"] is True
    assert result["evidence_ref"] == closed[0][1]["evidence_ref"]
    from runtime.loop.fence_reconcile import _closure_proof
    closure = _closure_proof(json.dumps(result), owner_id=OWNER,
                             occurrence_id=GATE_OCC, release_sha="a" * 40)
    assert closure and closure["receipt_ref"] == result["evidence_ref"]
    occ, proof = closed[0]
    assert occ == GATE_OCC and proof["proof_type"] == "pre_effect" and proof["verified"] is True
    assert proof["owner_id"] == OWNER and proof["occurrence_id"] == GATE_OCC and proof["evidence_ref"]


def test_a_run_that_reached_publication_or_has_no_run_never_closes_as_pre_effect(tmp_path):
    m = _load()
    for n, (files, rows, reason) in enumerate((
        (["git-hash.txt", "article-daily-prompt.txt", "gates/publication-state.json"], [], "run_reached_publication"),
        (["git-hash.txt", "model-stdout.log", "gates/publication-state.json"], [], "run_reached_publication"),
        (["git-hash.txt"], [{"run_id": "20261008-232303"}], "run_reached_publication"),
        (None, [], "no_run_paired_with_this_fence"),
    )):
        runs = tmp_path / f"runs{n}"
        runs.mkdir()
        if files is not None:
            _run_dir(runs, "20261008-232303", files)
        result, closed = _pre(m, tmp_path, runs, rows)
        assert result["status"] == "inconclusive" and result["reason"] == reason and closed == []


def test_pre_effect_without_resolve_writes_nothing(tmp_path):
    m = _load()
    runs = tmp_path / "runs"
    _run_dir(runs, "20261008-232303", ["git-hash.txt"])
    result, closed = _pre(m, tmp_path, runs, resolve=False)
    assert result["status"] == "pre_effect" and result["closed"] is False and closed == []
    assert result.get("verified") is not True


def test_released_fence_is_reread_and_returns_idempotent_closure_proof(tmp_path, capsys):
    m = _load()
    occurrence = GATE_OCC
    admission_db = tmp_path / "admission-v2.sqlite3"
    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            "CREATE TABLE occurrences (owner_id TEXT, occurrence_id TEXT, queued_at REAL, "
            "state TEXT, effect_unknown INTEGER)"
        )
        connection.execute(
            "INSERT INTO occurrences VALUES (?, ?, ?, ?, ?)",
            (OWNER, occurrence, GATE_QUEUED, "released", 0),
        )
    m.ADMISSION_DB = admission_db
    m.ARTICLES = _articles(tmp_path, [])
    m.RUNS_ROOT = tmp_path / "runs"
    _run_dir(m.RUNS_ROOT, "20261008-232303", ["git-hash.txt"])

    exit_code = m.main(["--occurrence", occurrence])
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0, result
    assert result["status"] == "pre_effect" and result["closed"] is True
    assert result["owner_id"] == OWNER and result["verified"] is True
    assert result["evidence_ref"].startswith("writer-run-no-publication-state:")
    with sqlite3.connect(admission_db) as connection:
        state, effect_unknown = connection.execute(
            "SELECT state, effect_unknown FROM occurrences WHERE occurrence_id=?", (occurrence,)
        ).fetchone()
    assert (state, effect_unknown) == ("released", 0)

    with sqlite3.connect(admission_db) as connection:
        connection.execute("UPDATE occurrences SET effect_unknown=2 WHERE occurrence_id=?", (occurrence,))
    exit_code = m.main(["--occurrence", occurrence])
    result = json.loads(capsys.readouterr().out)
    assert exit_code == 1 and result["reason"] == "occurrence_not_fenced_or_unreadable"

    with sqlite3.connect(admission_db) as connection:
        connection.execute(
            "UPDATE occurrences SET state='claimed', effect_unknown=0 WHERE occurrence_id=?", (occurrence,)
        )
    exit_code = m.main(["--occurrence", occurrence])
    result = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert result["status"] == "inconclusive" and result["reason"] == "occurrence_not_fenced_or_unreadable"


def test_a_generated_run_without_publication_state_closes_as_pre_effect(tmp_path):
    # Every managed publish adapter refuses without gates/publication-state.json
    # (publication-guard register-intent precedes the first live side effect).
    m = _load()
    runs = tmp_path / "runs"
    _run_dir(runs, "20261008-232303", ["git-hash.txt", "article-daily-prompt.txt", "article-ja.md"])
    result, closed = _pre(m, tmp_path, runs)
    assert result["status"] == "pre_effect" and result["closed"] is True
    assert "no-publication-state" in closed[0][1]["evidence_ref"]


def test_a_resumed_run_pairs_through_its_attempt_start(tmp_path):
    # 2026-10-09 15:19 JST: occurrence 18dcc8165ae08ca0-96619 resumed run 20261008-232303
    # (created 08:23 JST), generated the article, then died on ENOSPC before publication.
    m = _load()
    runs = tmp_path / "runs"
    d = _run_dir(runs, "20261008-120000", ["git-hash.txt", "article-daily-prompt.txt", "article-ja.md"])
    attempt = datetime.fromtimestamp(GATE_QUEUED, timezone.utc) + timedelta(minutes=4)
    (d / "gates" / "generation-state.json").write_text(json.dumps(
        {"attempts": [{"attempt": 1, "started_at": attempt.isoformat().replace("+00:00", "Z")}]}))
    result, closed = _pre(m, tmp_path, runs)
    assert result["status"] == "pre_effect" and result["closed"] is True
    (d / "gates" / "publication-state.json").write_text("{}")
    result, closed = _pre(m, tmp_path, runs)
    assert result["status"] == "inconclusive" and result["reason"] == "run_reached_publication" and closed == []


def test_resumed_live_publication_pairs_using_attempt_start(tmp_path):
    # The run directory name predates the fence, but this same run was resumed
    # inside the pairing window and its exact public article URL is in the ledger.
    m = _load()
    runs = tmp_path / "runs"
    run_id = "20261008-120000"
    d = _run_dir(runs, run_id, [
        "git-hash.txt", "article-daily-prompt.txt", "gates/publication-state.json",
    ])
    attempt = datetime.fromtimestamp(GATE_QUEUED, timezone.utc) + timedelta(minutes=4)
    (d / "gates" / "generation-state.json").write_text(json.dumps({
        "attempts": [{"attempt": 1, "started_at": attempt.isoformat().replace("+00:00", "Z")}],
    }))
    live_url = "https://note.com/anicca123/n/resumed-live"
    articles = _articles(tmp_path, [_row(run_id, "2026-10-09T01:23:00Z", live_url)])
    resolved = []

    def resolve_effect(owner, occurrence, *, official_readback, expected_state):
        proof = official_readback()
        resolved.append((owner, occurrence, proof, expected_state))
        return True

    result = m.reconcile(
        GATE_OCC, queued_at=GATE_QUEUED, state="claimed", articles_path=articles,
        fetch_status=lambda url: 200 if url == live_url else 404,
        resolver=resolve_effect, resolve=True, now=GATE_QUEUED + 3600, runs_root=runs,
    )

    assert result["status"] == "effected" and result["closed"] is True, result
    assert result["provider_receipt_id"] == live_url
    assert resolved == [(OWNER, GATE_OCC, {
        "owner_id": OWNER, "occurrence_id": GATE_OCC, "verified": True,
        "provider_receipt_id": live_url,
    }, "claimed")]


START_BLOCK_OCCURRENCE = "article-daily:18dd0bf091a5d3d0-57499"
START_BLOCK_QUEUED_AT = 1791601208.371748


def _start_block_fixture(tmp_path, monkeypatch, m, *, extra_log_line=""):
    """2026-10-10 12:02 JST: start control blocked on an unclassified same-day run and exited
    before any generation; no new Writer run dir exists, so the proof binds the log segment."""
    writer_root = tmp_path / "writer"
    (writer_root / "logs").mkdir(parents=True)
    source = ('#!/bin/bash\nif [ "$BLOCK" = 1 ]; then\n'
              '  echo "=== article-daily start control BLOCK: $START_DECISION ===" >>"$LOG"\n  exit 0\nfi\n')
    source_repo = tmp_path / "source"
    entrypoint = source_repo / "skills" / "writer-agent" / "article-daily.sh"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text(source, encoding="utf-8")
    for args in (["init", "-q"], ["config", "user.name", "T"], ["config", "user.email", "t@e.invalid"],
                 ["add", "skills/writer-agent/article-daily.sh"], ["commit", "-qm", "f"]):
        subprocess.run(["git", "-C", str(source_repo), *args] if args[0] != "init" else ["git", "init", "-q", str(source_repo)],
                       check=True, capture_output=True)
    sha = subprocess.check_output(["git", "-C", str(source_repo), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(source_repo), "update-ref", "refs/remotes/origin/main", sha], check=True)
    lines = [json.dumps({"event_id": "s1", "occurrence_id": START_BLOCK_OCCURRENCE, "phase": "execute", "release_sha": sha}),
             json.dumps({"event_id": "t1", "occurrence_id": START_BLOCK_OCCURRENCE, "phase": "report", "exit_code": 0, "release_sha": sha})]
    (writer_root / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (writer_root / "articles.jsonl").write_text("", encoding="utf-8")
    segment = ["=== article-daily run 2026-10-10 12:02:35 JST ===", '{"status": "clear"}']
    if extra_log_line:
        segment.append(extra_log_line)
    segment.append('=== article-daily start control BLOCK: {"action":"block-incomplete"} ===')
    (writer_root / "logs" / "article-daily.log").write_text(
        "=== article-daily run 2026-10-10 10:02:40 JST ===\nold\n" + "\n".join(segment) + "\n", encoding="utf-8")
    pinned = {
        "stop_kind": "start_control_block",
        "runtime_run_id": "18dd0bf091a5d3d0-57499",
        "writer_run_id": "20261010-001933",
        "release_sha": sha,
        "entrypoint": "skills/writer-agent/article-daily.sh",
        "entrypoint_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "start_event_id": "s1", "terminal_event_id": "t1",
        "event_hashes": {"s1": hashlib.sha256(lines[0].encode()).hexdigest(),
                         "t1": hashlib.sha256(lines[1].encode()).hexdigest()},
        "log_header": "=== article-daily run 2026-10-10 12:02:35 JST ===",
        "article_log_segment_sha256": hashlib.sha256("\n".join(
            [s for s in segment if s != extra_log_line]).encode()).hexdigest(),
        "queued_at": START_BLOCK_QUEUED_AT,
        "gate_error": "block-incomplete",
        "gate_terminal": "article-daily start control BLOCK",
        "evidence_ref": "writer://fence-reconciliation/article-daily-18dd0bf091a5d3d0-57499.json",
    }
    monkeypatch.setitem(m.HISTORICAL_GATE_STOP_PROOFS, START_BLOCK_OCCURRENCE, pinned)
    return writer_root, source_repo


def test_start_control_block_closes_without_a_run_dir(tmp_path, monkeypatch):
    m = _load()
    writer_root, source_repo = _start_block_fixture(tmp_path, monkeypatch, m)
    calls = []
    result = m.reconcile(START_BLOCK_OCCURRENCE, queued_at=START_BLOCK_QUEUED_AT, state="claimed",
                         articles_path=writer_root / "articles.jsonl", fetch_status=lambda _u: 0,
                         resolver=lambda *a, **k: calls.append(k["no_dispatch_proof"]()) or True,
                         resolve=True, now=START_BLOCK_QUEUED_AT + 3600,
                         writer_root=writer_root, source_repo=source_repo)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is True
    assert calls[0]["runtime_run_id"] == "18dd0bf091a5d3d0-57499"
    assert calls[0]["proof_type"] == "historical_writer_gate_stop_no_dispatch"


def test_start_control_block_rejects_a_segment_that_began_generation(tmp_path, monkeypatch):
    m = _load()
    writer_root, source_repo = _start_block_fixture(
        tmp_path, monkeypatch, m, extra_log_line="=== article-daily generation begin ===")
    called = []
    result = m.reconcile(START_BLOCK_OCCURRENCE, queued_at=START_BLOCK_QUEUED_AT, state="claimed",
                         articles_path=writer_root / "articles.jsonl", fetch_status=lambda _u: 0,
                         resolver=lambda *a, **k: called.append(True) or True,
                         resolve=True, now=START_BLOCK_QUEUED_AT + 3600,
                         writer_root=writer_root, source_repo=source_repo)
    assert result["status"] == "inconclusive" and called == []


# --- article-resume: historical no-dispatch from official readbacks (2026-10-12) ---
# One claimed+effect_unknown row from 2026-09-29 16:55 UTC deferred every article-resume wake and blocked
# Writer run 20261011-134916.  Close only when every official destination's newest post and the ledger's
# newest row predate the fence, at least 7 days later (measured publish lag 25 min-30 h).

RESUME_OCC = "article-resume:18d9d90239bcb040-18058"
RESUME_QUEUED = datetime(2026, 9, 29, 16, 55, 20, tzinfo=timezone.utc).timestamp()
RESUME_NOW = RESUME_QUEUED + 13 * 86400
NOTE_URL = "https://note.com/api/v2/creators/anicca123/contents?kind=note&page=1"
BUDDHA_URL = "https://aniccabuddha.substack.com/api/v1/posts?limit=3"
AI2026_URL = "https://aniccaai2026.substack.com/api/v1/posts?limit=3"


def _readbacks(note="2026-09-29T11:44:21+09:00", buddha="2026-09-29T02:50:56.362Z",
               ai2026="2026-09-29T02:57:45.886Z"):
    payloads = {
        NOTE_URL: {"data": {"contents": [{"publishAt": "2026-08-08T16:31:34+09:00"},
                                         {"publishAt": note}]}},
        BUDDHA_URL: [{"post_date": buddha}, {"post_date": "2026-09-28T13:56:28.205Z"}],
        AI2026_URL: [{"post_date": ai2026}],
    }
    return lambda url: payloads[url]


def _resume_ledger(tmp_path, last_ts="2026-09-29T02:57:52.292141Z"):
    return _articles(tmp_path, [
        {"run_id": "daily-2026-08-08", "platform": "note", "published": False},   # undated draft row
        _row("20260929-010128", "2026-09-29T02:44:15.431815Z", "https://note.com/x/n/1"),
        _row("20260929-010128", last_ts, "https://x.substack.com/p/a", "substack"),
    ])


def _resume(m, tmp_path, *, fetch_json=None, ledger=None, now=RESUME_NOW, resolve=True):
    calls = []

    def resolver(owner, occurrence, *, no_dispatch_proof, expected_state):
        calls.append((owner, occurrence, no_dispatch_proof(), expected_state))
        return True

    result = m.reconcile(RESUME_OCC, queued_at=RESUME_QUEUED, state="claimed",
                         articles_path=ledger or _resume_ledger(tmp_path),
                         fetch_json=fetch_json or _readbacks(), resolver=resolver,
                         resolve=resolve, now=now, writer_root=tmp_path / "writer")
    return result, calls


def test_resume_fence_closes_when_every_readback_and_the_ledger_predate_it(tmp_path):
    m = _load()
    result, calls = _resume(m, tmp_path)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is True
    assert result["owner_id"] == "article-resume" and result["verified"] is True
    assert result["evidence_ref"] == result["proof_ref"]
    owner, occurrence, proof, state = calls[0]
    assert (owner, occurrence, state) == ("article-resume", RESUME_OCC, "claimed")
    assert proof["proof_type"] == "historical_writer_resume_no_dispatch"
    assert proof["provider"] == "writer" and proof["verified"] is True
    assert proof["runtime_run_id"] == "18d9d90239bcb040-18058"
    assert proof["readback_newest_post_at"]["note:anicca123"] == "2026-09-29T02:44:21+00:00"
    receipt = tmp_path / "writer" / "fence-reconciliation" / "article-resume-18d9d90239bcb040-18058.json"
    assert json.loads(receipt.read_text(encoding="utf-8")) == proof


def test_resume_fence_stays_when_any_destination_published_after_it(tmp_path):
    m = _load()
    after = "2026-09-30T01:00:00Z"
    for fetch in (_readbacks(note="2026-09-30T10:00:00+09:00"), _readbacks(buddha=after),
                  _readbacks(ai2026=after)):
        result, calls = _resume(m, tmp_path, fetch_json=fetch)
        assert result["status"] == "inconclusive" and result["closed"] is False and calls == []
        assert result["reason"].startswith("publication_after_fence:")


def test_resume_fence_stays_when_a_readback_fails_or_is_empty(tmp_path):
    m = _load()
    good = _readbacks()
    for broken in (None, [], {"data": {"contents": []}}, [{"post_date": None}], "<html>"):
        fetch = lambda url, broken=broken: broken if url == AI2026_URL else good(url)
        result, calls = _resume(m, tmp_path, fetch_json=fetch)
        assert result["status"] == "inconclusive" and calls == []
        assert result["reason"] == "readback_failed:substack:aniccaai2026"


def test_resume_fence_stays_when_the_ledger_has_a_row_after_it_or_an_undated_tail(tmp_path):
    m = _load()
    newer = _resume_ledger(tmp_path, last_ts="2026-09-30T00:00:00Z")
    result, calls = _resume(m, tmp_path, ledger=newer)
    assert result["reason"] == "writer_ledger_row_after_fence" and calls == []
    undated_tail = tmp_path / "tail.jsonl"
    undated_tail.write_text(newer.read_text().replace("2026-09-30T00:00:00Z", "2026-09-29T00:00:00Z")
                            + json.dumps({"run_id": "x", "published": False}) + "\n")
    result, calls = _resume(m, tmp_path, ledger=undated_tail)
    assert result["status"] == "inconclusive" and calls == []


def test_resume_fence_younger_than_seven_days_is_left_alone(tmp_path):
    m = _load()
    result, calls = _resume(m, tmp_path, now=RESUME_QUEUED + 6 * 86400)
    assert result["reason"] == "fence_too_young" and calls == []


def test_resume_without_resolve_writes_nothing(tmp_path):
    m = _load()
    result, calls = _resume(m, tmp_path, resolve=False)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is False and calls == []
    assert not (tmp_path / "writer").exists()


MARKER_RUN = "18de88fef43e89b0-51032"
MARKER_OCC = f"{OWNER}:{MARKER_RUN}"
MARKER_QUEUED = datetime(2026, 10, 14, 23, 18, 2, tzinfo=timezone.utc).timestamp()   # 08:18 JST


def _marker_fixture(tmp_path, *, marker='{"effect":0,"status":"pre_effect_failure"}', mode=0o600,
                    identity=False, terminal=None):
    """Start control BLOCK before any run dir: the host marker is the only no-dispatch evidence."""
    root = tmp_path / "writer"
    scratch = root / "loop-tmp" / OWNER / MARKER_RUN
    scratch.mkdir(parents=True)
    for d in (root, root / "loop-tmp", root / "loop-tmp" / OWNER, scratch):
        d.chmod(0o700)
    if marker is not None:
        (scratch / "entrypoint-result.json").write_text(marker)
        (scratch / "entrypoint-result.json").chmod(mode)
    if identity:
        (scratch / "effect-identity.jsonl").write_text("{}\n")
    terminal = {"occurrence_id": MARKER_OCC, "owner_id": OWNER, "phase": "report", "status": "fail",
                "exit_code": 75, "effect_status": "unknown", "effect_identity_status": "not_written",
                "provider_receipt_id": None, "official_readback_ref": None} if terminal is None else terminal
    start = {"occurrence_id": MARKER_OCC, "owner_id": OWNER, "phase": "execute", "status": "running"}
    (root / "events.jsonl").write_text(json.dumps(start) + "\n" + json.dumps(terminal) + "\n")
    (tmp_path / "runs").mkdir()
    return root


def _marker_reconcile(m, tmp_path, root, rows=()):
    closed = []
    result = m.reconcile(MARKER_OCC, queued_at=MARKER_QUEUED, state="claimed",
                         articles_path=_articles(tmp_path, list(rows)), runs_root=tmp_path / "runs",
                         fetch_status=lambda u: 404, writer_root=root, now=MARKER_QUEUED + 86400,
                         pre_effect_resolver=lambda o, occ, **k: closed.append(k["pre_effect_readback"]()) or True,
                         resolve=True)
    return result, closed


def test_start_control_block_closes_from_the_surviving_host_pre_effect_marker(tmp_path):
    m = _load()
    result, closed = _marker_reconcile(m, tmp_path, _marker_fixture(tmp_path))
    assert result["status"] == "pre_effect" and result["closed"] is True and result["verified"] is True
    assert closed[0]["proof_type"] == "pre_effect" and closed[0]["occurrence_id"] == MARKER_OCC
    assert closed[0]["evidence_ref"] == f"lm-loop://{OWNER}/{MARKER_RUN}/entrypoint-result.json"


def test_host_marker_proof_refuses_any_sign_of_a_crossed_boundary(tmp_path):
    m = _load()
    bad_terminal = {"occurrence_id": MARKER_OCC, "owner_id": OWNER, "phase": "report", "status": "fail",
                    "exit_code": 75, "effect_identity_status": "persisted"}
    cases = [dict(marker=None), dict(marker='{"effect":1,"status":"pre_effect_failure"}'),
             dict(mode=0o644), dict(identity=True), dict(terminal=bad_terminal)]
    for index, kwargs in enumerate(cases):
        case = tmp_path / str(index)
        case.mkdir()
        result, closed = _marker_reconcile(m, case, _marker_fixture(case, **kwargs))
        assert result["status"] == "inconclusive" and closed == [], kwargs
    # A ledger row in the pairing window means publication was reached: the marker is not consulted.
    case = tmp_path / "ledger"
    case.mkdir()
    rows = [_row("20261014-232000", "2026-10-14T23:40:00Z", "https://note.com/x/n/2")]
    result, closed = _marker_reconcile(m, case, _marker_fixture(case), rows=rows)
    assert result["status"] == "inconclusive" and closed == []


CARRY_RUN = "20261016-014724"
CARRY_RUNTIME = "18dee9fd8809c358-44131"
CARRY_OCC = f"{OWNER}:{CARRY_RUNTIME}"
CARRY_QUEUED = datetime(2026, 10, 16, 4, 57, 53, tzinfo=timezone.utc).timestamp()
ABSENT = {pair: {"status": "absent"} for pair in ("note/ja", "substack/ja", "substack/en", "x-article/ja")}


def _carry_fixture(tmp_path, *, ledger=None, publication_state=False, dispatch=False):
    """Conscience BLOCK after the model pass started: a carry-over ledger row, no dispatch files."""
    root = tmp_path / "writer"
    run = root / "runs" / CARRY_RUN
    (run / "gates").mkdir(parents=True)
    (run / "article-ja.md").write_text("# 記事\n")
    (run / "article-en.md").write_text("# Article\n")
    (run / "gates" / "generation-state.json").write_text(json.dumps(
        {"attempts": [{"started_at": "2026-10-16T05:03:05.326244Z"}]}))
    if publication_state:
        (run / "gates" / "publication-state.json").write_text("{}")
    if dispatch:
        (run / "gates" / "platform-dispatch.jsonl").write_text("{}\n")
    row = {"ts": "2026-10-16T05:15:43Z", "run_id": CARRY_RUN, "platform": "carry-over",
           "draft_url": None, "published": False, "state": "carry-over:conscience-block"}
    terminal = {"occurrence_id": CARRY_OCC, "phase": "report", "status": "fail", "exit_code": 1,
                "timestamp": "2026-10-16T05:16:15.083428+00:00"}
    (root / "events.jsonl").write_text(json.dumps(terminal) + "\n")
    return root, _articles(tmp_path, [ledger or row])


def _carry_reconcile(m, root, arts, readback, resolve=True):
    calls, closed = [], []

    def fake_readback(run_dir, since, until):
        calls.append((run_dir.name, since, until))
        return readback

    result = m.reconcile(CARRY_OCC, queued_at=CARRY_QUEUED, state="claimed", articles_path=arts,
                         runs_root=root / "runs", writer_root=root, fetch_status=lambda u: 404,
                         now=CARRY_QUEUED + 7200, absence_readback=fake_readback,
                         resolver=lambda o, occ, **k: closed.append(k["no_dispatch_proof"]()) or True,
                         pre_effect_resolver=lambda *a, **k: closed.append("pre_effect") or True,
                         resolve=resolve)
    return result, calls, closed


def test_carry_over_run_closes_only_after_every_destination_reads_absent(tmp_path):
    m = _load()
    root, arts = _carry_fixture(tmp_path)
    result, calls, closed = _carry_reconcile(m, root, arts, {"destinations": ABSENT})
    assert calls == [(CARRY_RUN, CARRY_QUEUED,
                      datetime(2026, 10, 16, 5, 16, 15, 83428, tzinfo=timezone.utc).timestamp())]
    assert result["status"] == "no_dispatch_proven" and result["closed"] is True
    proof = closed[0]
    assert proof["proof_type"] == "historical_writer_gate_stop_no_dispatch"
    assert proof["provider"] == "writer" and proof["runtime_run_id"] == CARRY_RUNTIME
    assert proof["destinations"] == ABSENT and set(proof["article_sha256"]) == {"article-ja.md", "article-en.md"}
    assert (root / "fence-reconciliation" / f"article-daily-{CARRY_RUNTIME}.json").exists()


def test_carry_over_dry_run_writes_nothing(tmp_path):
    m = _load()
    root, arts = _carry_fixture(tmp_path)
    result, _, closed = _carry_reconcile(m, root, arts, {"destinations": ABSENT}, resolve=False)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is False and closed == []
    assert not (root / "fence-reconciliation").exists()


def test_carry_over_stays_held_when_any_destination_is_not_proven_absent(tmp_path):
    m = _load()
    for index, bad in enumerate(({"status": "unreadable", "reason": "browser_busy"},
                                 {"status": "present", "reason": "title_match"})):
        case = tmp_path / str(index)
        case.mkdir()
        root, arts = _carry_fixture(case)
        result, _, closed = _carry_reconcile(
            m, root, arts, {"destinations": {**ABSENT, "x-article/ja": bad}})
        assert result["status"] == "inconclusive" and closed == []
    case = tmp_path / "missing"
    case.mkdir()
    root, arts = _carry_fixture(case)
    partial = {k: v for k, v in ABSENT.items() if k != "substack/en"}
    result, _, closed = _carry_reconcile(m, root, arts, {"destinations": partial})
    assert result["status"] == "inconclusive" and closed == []


def test_a_run_that_reached_publication_never_uses_the_absence_readback(tmp_path):
    m = _load()
    published = {"ts": "2026-10-16T05:15:43Z", "run_id": CARRY_RUN, "platform": "note",
                 "published": True, "live_url": "https://note.com/x/n/1"}
    for index, kwargs in enumerate((dict(ledger=published), dict(publication_state=True),
                                    dict(dispatch=True))):
        case = tmp_path / str(index)
        case.mkdir()
        root, arts = _carry_fixture(case, **kwargs)
        result, calls, closed = _carry_reconcile(m, root, arts, {"destinations": ABSENT})
        assert result["status"] == "inconclusive" and calls == [] and closed == [], kwargs


def test_held_reason_names_each_destination_failure(tmp_path):
    m = _load()
    root, arts = _carry_fixture(tmp_path)
    readback = {"destinations": {**ABSENT, "note/ja": {"status": "unreadable", "reason": "HTTPError: 429"},
                                 "x-article/ja": {"status": "present", "reason": "title_match"}}}
    result, _, closed = _carry_reconcile(m, root, arts, readback)
    assert closed == [] and result["status"] == "inconclusive"
    assert result["reason"].startswith("destination_not_proven_absent:note/ja,x-article/ja")
    assert result["destinations"]["note/ja"] == {"status": "unreadable", "reason": "HTTPError: 429"}


def test_absence_readback_runs_with_the_writer_state_dir_not_the_reconciler_root(tmp_path, monkeypatch):
    # 2026-10-16: under lm-fence-reconciler LIFE_MANAGER_STATE_ROOT is the reconciler's root and
    # writer-runtime-env.sh fell back to it, so note cookies were looked up in the wrong place.
    m = _load()
    writer_root = tmp_path / "writer"
    run_dir = writer_root / "runs" / "20261016-014724"
    run_dir.mkdir(parents=True)
    monkeypatch.setenv("LIFE_MANAGER_STATE_ROOT", str(tmp_path / "lm-fence-reconciler"))
    monkeypatch.delenv("WRITER_STATE_DIR", raising=False)
    seen = {}

    class Done:
        returncode = 0
        stdout = '{"ok": true}\n'

    monkeypatch.setattr(m.subprocess, "run", lambda argv, **kw: seen.update(kw) or Done())
    assert m._official_absence_readback(run_dir, 0.0, 1.0) == {"ok": True}
    assert seen["env"]["WRITER_STATE_DIR"] == str(writer_root)
    assert seen["env"]["ARTICLE_STATE_DIR"] == str(writer_root)


def test_pending_media_rows_take_the_official_absence_path(tmp_path):
    # 2026-10-16 22:43: run rows were pending:media-renderer-unavailable, not carry-over.
    m = _load()
    pending = {"ts": "2026-10-16T05:15:43Z", "run_id": CARRY_RUN, "platform": "note", "lang": "ja",
               "draft_url": None, "published": False,
               "state": "pending:media-renderer-unavailable:body-diagram candidate was not produced"}
    root, arts = _carry_fixture(tmp_path, ledger=pending)
    result, calls, closed = _carry_reconcile(m, root, arts, {"destinations": ABSENT})
    assert calls and result["status"] == "no_dispatch_proven" and result["closed"] is True
