"""article-daily fence reconcile: require publish proof or exact historical gate-stop proof.

2026-10-09: a single claimed+effect_unknown admission row from 9/29 10:01 JST kept article-daily
deferred (resource_effect_unknown) for 10 days; the run had published to note and Substack.  A
time window is used only to PAIR a fence with a publish, never to infer that nothing happened.
"""

import gzip
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


def _archived_start_block_fixture(tmp_path, monkeypatch, m):
    root, source = _start_block_fixture(tmp_path, monkeypatch, m)
    pinned = m.HISTORICAL_GATE_STOP_PROOFS[START_BLOCK_OCCURRENCE]
    archive = root / "events-fixture.jsonl.gz"
    archive.write_bytes(gzip.compress((root / "events.jsonl").read_bytes()))
    (root / "events.jsonl").write_text("", encoding="utf-8")
    marker = root / "loop-tmp" / OWNER / pinned["runtime_run_id"] / "entrypoint-result.json"
    marker.parent.mkdir(parents=True, mode=0o700)
    marker.write_text('{"effect":0,"status":"pre_effect_failure"}', encoding="utf-8")
    marker.chmod(0o600)
    pinned.update({"events_archive": archive.name,
                   "events_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                   "pre_effect_marker_sha256": hashlib.sha256(marker.read_bytes()).hexdigest(),
                   "helper_sha256": {pinned["entrypoint"]: pinned["entrypoint_sha256"]}})
    return root, source, archive, marker


def test_historical_start_stop_binds_archive_and_surviving_marker(tmp_path, monkeypatch):
    m = _load()
    root, source, archive, marker = _archived_start_block_fixture(tmp_path, monkeypatch, m)
    proof = m._historical_gate_stop_proof(
        START_BLOCK_OCCURRENCE, START_BLOCK_QUEUED_AT, writer_root=root, source_repo=source,
        now=START_BLOCK_QUEUED_AT + 3600)
    assert proof is not None
    assert proof["events_archive"] == archive.name
    assert proof["pre_effect_marker_sha256"] == hashlib.sha256(marker.read_bytes()).hexdigest()


def test_archived_start_stop_refuses_modified_or_linked_evidence(tmp_path, monkeypatch):
    for case in ("archive", "events", "log", "helper", "marker", "marker-mode",
                 "archive-link", "marker-link", "marker-parent-link", "effect-identity"):
        m = _load()
        case_root = tmp_path / case
        case_root.mkdir()
        root, source, archive, marker = _archived_start_block_fixture(case_root, monkeypatch, m)
        pinned = m.HISTORICAL_GATE_STOP_PROOFS[START_BLOCK_OCCURRENCE]
        if case == "archive":
            archive.write_bytes(archive.read_bytes() + b"changed")
        elif case == "events":
            archive.write_bytes(gzip.compress(gzip.decompress(archive.read_bytes()).replace(
                b'"exit_code": 0', b'"exit_code": 1')))
            pinned["events_archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        elif case == "log":
            (root / "logs/article-daily.log").write_text("changed")
        elif case == "helper":
            pinned["helper_sha256"][pinned["entrypoint"]] = "0" * 64
        elif case == "marker":
            marker.write_text('{"effect":1,"status":"pre_effect_failure"}')
        elif case == "marker-mode":
            marker.chmod(0o644)
        elif case in {"archive-link", "marker-link"}:
            path = archive if case == "archive-link" else marker
            target = path.with_suffix(".saved")
            path.rename(target)
            path.symlink_to(target)
        elif case == "marker-parent-link":
            parent = marker.parent
            target = parent.with_name("saved-scratch")
            parent.rename(target)
            parent.symlink_to(target, target_is_directory=True)
        else:
            (marker.parent / "effect-identity.jsonl").write_text("{}\n")
        assert m._historical_gate_stop_proof(
            START_BLOCK_OCCURRENCE, START_BLOCK_QUEUED_AT, writer_root=root, source_repo=source,
            now=START_BLOCK_QUEUED_AT + 3600) is None, case


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


def test_unpublished_row_with_an_external_identifier_never_takes_the_absence_path(tmp_path):
    m = _load()
    for extra in ({"public_id": "n123"}, {"status_id": "199"}, {"edit_id": "77"}):
        row = {"ts": "2026-10-16T05:15:43Z", "run_id": CARRY_RUN, "platform": "note", "lang": "ja",
               "draft_url": None, "published": False, "state": "pending:x"} | extra
        sub = tmp_path / next(iter(extra))
        sub.mkdir()
        root, arts = _carry_fixture(sub, ledger=row)
        result, calls, closed = _carry_reconcile(m, root, arts, {"destinations": ABSENT})
        assert not calls and not closed, extra


def test_a_young_fence_whose_run_already_reported_is_judged_now(tmp_path):
    # 2026-10-17: the 08:05 and 11:05 runs ended (report event written after the runner reaped the
    # process group) but each fence waited the full hour, so the next hourly start was lost too.
    m = _load()
    arts = _articles(tmp_path, [_row("20260929-010128", "2026-09-29T02:44:15Z", "https://note.com/x/n/1")])
    root = tmp_path / "writer"
    root.mkdir()
    report = {"occurrence_id": OCC, "phase": "report", "status": "fail", "exit_code": 1,
              "timestamp": datetime.fromtimestamp(QUEUED + 300, timezone.utc).isoformat()}
    (root / "events.jsonl").write_text(json.dumps(report) + "\n")
    result = m.reconcile(OCC, queued_at=QUEUED, state="claimed", articles_path=arts, writer_root=root,
                         runs_root=tmp_path / "no-runs",
                         fetch_status=lambda u: 200, resolver=lambda *a, **k: True, resolve=False,
                         now=QUEUED + 600)
    assert result["status"] == "effected"
    # A killed run (timeout/cancel) can leave detached tool shells alive past the report: wait.
    for code in (75, 124, 143):
        (root / "events.jsonl").write_text(json.dumps(dict(report, exit_code=code)) + "\n")
        result = m.reconcile(OCC, queued_at=QUEUED, state="claimed", articles_path=arts, writer_root=root,
                             runs_root=tmp_path / "no-runs",
                             fetch_status=lambda u: 200, resolver=lambda *a, **k: True, resolve=False,
                             now=QUEUED + 600)
        assert result["reason"] == "fence_too_young", code
    # The entrypoint exited 1 but its model pass was killed by the bounded timeout: wait.
    (root / "events.jsonl").write_text(json.dumps(report) + "\n")
    run = tmp_path / "runs" / "20260929-010128" / "gates"
    run.mkdir(parents=True)
    (run / "generation-state.json").write_text(json.dumps(
        {"attempts": [{"started_at": "2026-09-29T01:01:30Z", "return_code": 124}]}))
    result = m.reconcile(OCC, queued_at=QUEUED, state="claimed", articles_path=arts, writer_root=root,
                         runs_root=tmp_path / "runs",
                         fetch_status=lambda u: 200, resolver=lambda *a, **k: True, resolve=False,
                         now=QUEUED + 600)
    assert result["reason"] == "fence_too_young"
    (root / "events.jsonl").write_text("")
    result = m.reconcile(OCC, queued_at=QUEUED, state="claimed", articles_path=arts, writer_root=root,
                         fetch_status=lambda u: 200, resolver=lambda *a, **k: True, resolve=False,
                         now=QUEUED + 600)
    assert result["reason"] == "fence_too_young"


CATCHUP_OCC = "article-resume:18dd959f92920ff0-56630"
CATCHUP_QUEUED = 1791752648.92176
CATCHUP_RUN = "20261011-210544"
CATCHUP_LINE = "article-resume: missed daily schedule catch-up date=2026-10-12 hour=06"
CATCHUP_PREV = "article-resume: daily schedule not due date=2026-10-12 hour=05"
ABSENT = {pair: {"status": "absent"} for pair in ("note/ja", "substack/ja", "substack/en", "x-article/ja")}


def _event(occ, phase, ts, release, **extra):
    loop = occ.split(":", 1)[0]
    return json.dumps({"loop_id": loop, "owner_id": loop, "occurrence_id": occ, "phase": phase,
                       "timestamp": ts, "release_sha": release, **extra})


def _catchup_fixture(tmp_path, monkeypatch, m, *, extra_events=(), resume_log=None,
                     ledger_rows=(), publication_state=False):
    """The 2026-10-12 06:05 JST pass: catch-up exec'd article-daily.sh, the new run stopped pre-publication."""
    import gzip
    writer_root = tmp_path / "writer"
    run_dir = writer_root / "runs" / CATCHUP_RUN
    (run_dir / "gates").mkdir(parents=True)
    (run_dir / "gates" / "publication-blocker.json").write_text('{"status":"blocked-before-publication"}\n')
    (run_dir / "gates" / "generation-state.json").write_text('{"status":"provider-failed-ambiguous"}\n')
    if publication_state:
        (run_dir / "gates" / "publication-state.json").write_text("{}\n")
    source_repo = tmp_path / "source"
    files = {"skills/writer-agent/scripts/article-resume-pending.sh": "resume\n",
             "skills/writer-agent/article-daily.sh": "daily\n"}
    for name, text in files.items():
        (source_repo / name).parent.mkdir(parents=True, exist_ok=True)
        (source_repo / name).write_text(text)
    subprocess.run(["git", "init", "-q", str(source_repo)], check=True)
    subprocess.run(["git", "-C", str(source_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source_repo), "-c", "user.name=T", "-c", "user.email=t@e.invalid",
                    "commit", "-qm", "fixture"], check=True)
    sha = subprocess.check_output(["git", "-C", str(source_repo), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(source_repo), "update-ref", "refs/remotes/origin/main", sha], check=True)
    start = _event(CATCHUP_OCC, "execute", "2026-10-11T21:05:39.385339+00:00", sha)
    terminal = _event(CATCHUP_OCC, "report", "2026-10-11T21:17:16.270268+00:00", sha, exit_code=1)
    blocked = "article-resume:18dd958a6725c358-54254"
    lines = [_event(blocked, "execute", "2026-10-11T21:04:08+00:00", sha),
             _event(blocked, "report", "2026-10-11T21:04:09+00:00", sha,
                    blocker="host_admission_deferred:resource_capacity_busy"),
             start, terminal, *extra_events]
    with gzip.open(writer_root / "events-20261013T124916565876Z.jsonl.gz", "wt", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    (writer_root / "events.jsonl").write_text("")
    (writer_root / "logs").mkdir()
    (writer_root / "logs" / "article-resume.log").write_text(
        "\n".join(resume_log or [CATCHUP_PREV, CATCHUP_LINE, "article-resume: later pass"]) + "\n")
    segment = "\n".join(["=== article-daily run 2026-10-12 06:05:42 JST ===",
                         f"=== article-daily start control: released a new run={CATCHUP_RUN} ===",
                         "=== article-daily: generation incomplete before publication state ===",
                         "=== article-daily done rc=1 2026-10-12 06:17:15 JST ==="])
    (writer_root / "logs" / "article-daily.log").write_text("before\n" + segment + "\nafter\n")
    (writer_root / "articles.jsonl").write_text("".join(json.dumps(row) + "\n" for row in [
        _row("20261011-134916", "2026-10-11T20:19:10.502338Z", "https://x.substack.com/p/a", "substack"),
        *ledger_rows,
        _row("20261017-050403", "2026-10-17T10:00:00Z", "https://note.com/x/n/later"),
    ]))
    expected = dict(m.HISTORICAL_RESUME_CATCHUP_PROOFS[CATCHUP_OCC])
    expected.update({
        "release_sha": sha,
        "entrypoint_sha256": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()},
        "event_hashes": [hashlib.sha256(line.encode()).hexdigest() for line in (start, terminal)],
        "article_log_segment_sha256": hashlib.sha256(segment.encode()).hexdigest(),
        "run_artifacts": {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
                          for name in ("gates/generation-state.json", "gates/publication-blocker.json")},
    })
    monkeypatch.setitem(m.HISTORICAL_RESUME_CATCHUP_PROOFS, CATCHUP_OCC, expected)
    return writer_root, source_repo, sha


def _catchup(m, writer_root, source_repo, *, destinations=ABSENT, resolve=True):
    calls, windows = [], []

    def resolver(owner, occurrence, *, no_dispatch_proof, expected_state):
        calls.append((owner, occurrence, no_dispatch_proof(), expected_state))
        return True

    def readback(run_dir, since, until):
        windows.append((run_dir.name, since, until))
        return {"destinations": destinations}

    result = m.reconcile(CATCHUP_OCC, queued_at=CATCHUP_QUEUED, state="claimed",
                         articles_path=writer_root / "articles.jsonl", resolver=resolver,
                         resolve=resolve, now=CATCHUP_QUEUED + 6 * 86400, writer_root=writer_root,
                         source_repo=source_repo, absence_readback=readback)
    return result, calls, windows


def test_resume_catchup_occurrence_closes_from_bound_exec_proof(tmp_path, monkeypatch):
    m = _load()
    writer_root, source_repo, _ = _catchup_fixture(tmp_path, monkeypatch, m)
    result, calls, windows = _catchup(m, writer_root, source_repo)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is True, result
    owner, occurrence, proof, state = calls[0]
    assert (owner, occurrence, state) == ("article-resume", CATCHUP_OCC, "claimed")
    assert proof["proof_type"] == "historical_writer_resume_no_dispatch"
    assert proof["runtime_run_id"] == "18dd959f92920ff0-56630"
    assert proof["writer_run_id"] == CATCHUP_RUN and proof["branch"] == "missed-daily-schedule-catch-up"
    assert windows == [(CATCHUP_RUN, CATCHUP_QUEUED, 1791753436.270268)]
    receipt = writer_root / "fence-reconciliation" / "article-resume-18dd959f92920ff0-56630.json"
    assert json.loads(receipt.read_text(encoding="utf-8")) == proof


def test_resume_catchup_dry_run_writes_nothing(tmp_path, monkeypatch):
    m = _load()
    writer_root, source_repo, _ = _catchup_fixture(tmp_path, monkeypatch, m)
    result, calls, _ = _catchup(m, writer_root, source_repo, resolve=False)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is False and calls == []
    assert not (writer_root / "fence-reconciliation").exists()


def test_resume_catchup_stays_fenced_without_every_binding(tmp_path, monkeypatch):
    m = _load()
    cases = {
        "destination": dict(destinations={**ABSENT, "substack/en": {"status": "unreadable"}}),
        "second-execution": dict(extra_events=(
            _event("article-resume:other", "execute", "2026-10-11T21:30:00+00:00", "x"),
            _event("article-resume:other", "report", "2026-10-11T21:30:05+00:00", "x", exit_code=0))),
        "daily-overlap": dict(extra_events=(
            _event("article-daily:other", "execute", "2026-10-11T21:06:00+00:00", "x"),)),
        "pass-logged-a-branch": dict(resume_log=[CATCHUP_PREV, "article-resume: prepublication adoption run=x",
                                                 CATCHUP_LINE]),
        "duplicate-line": dict(resume_log=[CATCHUP_PREV, CATCHUP_LINE, CATCHUP_PREV, CATCHUP_LINE]),
        "ledger-in-window": dict(ledger_rows=[
            _row("20261011-134916", "2026-10-11T21:10:00Z", "https://x.substack.com/p/b", "substack")]),
        "run-ledger-row": dict(ledger_rows=[{"run_id": CATCHUP_RUN, "platform": "note", "published": False}]),
        "publication-state": dict(publication_state=True),
    }
    for name, kwargs in cases.items():
        destinations = kwargs.pop("destinations", ABSENT)
        root = tmp_path / name
        root.mkdir()
        writer_root, source_repo, _ = _catchup_fixture(root, monkeypatch, m, **kwargs)
        result, calls, _ = _catchup(m, writer_root, source_repo, destinations=destinations)
        assert result["status"] == "inconclusive" and calls == [], (name, result)


def test_resume_catchup_proof_is_pinned_to_the_measured_occurrence():
    m = _load()
    pinned = m.HISTORICAL_RESUME_CATCHUP_PROOFS[CATCHUP_OCC]
    assert pinned["queued_at"] == CATCHUP_QUEUED and pinned["writer_run_id"] == CATCHUP_RUN
    assert pinned["release_sha"] == "6f25bb2e95e9efbea58a0d8f04b4cc6eefbea7d2"
    assert pinned["entrypoint_sha256"]["skills/writer-agent/scripts/article-resume-pending.sh"] == \
        "5134fab95ab2b3056789ff7a1ed51383f5f0baf36baed81b32090c00369bf299"
    assert sorted(m.HISTORICAL_RESUME_CATCHUP_PROOFS) == sorted(
        [CATCHUP_OCC, "article-resume:18e00a32b6c907c0-21320"])


def test_no_drafts_catchup_proof_is_pinned_and_opt_in():
    # 2026-10-20 06:04 JST catch-up run 20261019-210430 wrote no draft, so the owner listings
    # had no title to search; only this measured entry may use the no-drafts stop line.
    m = _load()
    pinned = m.HISTORICAL_RESUME_CATCHUP_PROOFS["article-resume:18e00a32b6c907c0-21320"]
    assert pinned["writer_run_id"] == "20261019-210430"
    assert pinned["release_sha"] == "baac8c681314edd1fc430199f30da410d31a4c1c"
    assert pinned["no_drafts_stop_line"].endswith("run=20261019-210430 2026-10-20 06:04:43 JST ===")
    assert "no_drafts_stop_line" not in m.HISTORICAL_RESUME_CATCHUP_PROOFS[CATCHUP_OCC]


# 2026-10-18: article-resume:18df6fc53500b510-26567 took the WAIT -> self-heal path (no publisher),
# exited 0, but its admission release was lost; the fence deferred every later pass.
PASS_OCC = "article-resume:18df6fc53500b510-26567"
PASS_QUEUED = 1792273749.2848   # 2026-10-17T21:49:09Z


def _pass_record(branch, at, run_ids=(), occurrence=PASS_OCC, pid=26638):
    return "article-resume: pass " + json.dumps(
        {"at": at, "occurrence_id": occurrence, "pid": pid, "branch": branch, "run_ids": list(run_ids)},
        separators=(",", ":"))


def _pass_fixture(tmp_path, *, records=None, after_self_heal='{"status":"NO_ACTIONABLE_INCIDENT"}',
                  exit_code=0):
    writer = tmp_path / "writer"
    (writer / "logs").mkdir(parents=True)
    records = records if records is not None else [
        _pass_record("start", "2026-10-17T21:54:30Z"), _pass_record("self-heal", "2026-10-17T21:54:38Z")]
    lines = [_pass_record("start", "2026-10-17T21:44:16Z", occurrence="article-resume:other", pid=8272)]
    for record in records:
        lines.append(record)
        if '"branch":"self-heal"' in record:
            lines.append(after_self_heal)
    (writer / "logs/article-resume.log").write_text("\n".join(lines) + "\n")
    events = [
        {"occurrence_id": PASS_OCC, "phase": "execute", "timestamp": "2026-10-17T21:54:29.523644+00:00"},
        {"occurrence_id": PASS_OCC, "phase": "report", "status": "pass" if exit_code == 0 else "fail",
         "exit_code": exit_code, "event_id": "a2cf923ffa1a9dbcf638175c",
         "release_sha": "4bfa2d2397666171669e14d62d289c214062ed8f",
         "timestamp": "2026-10-17T21:54:39.825888+00:00"},
    ]
    (writer / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    return writer


def _pass_readbacks(note="2026-10-16T06:10:00+09:00", buddha="2026-10-16T21:30:00Z",
                    ai2026="2026-10-16T21:31:00Z", newer="2026-10-18T06:30:00Z"):
    payloads = {
        NOTE_URL: {"data": {"contents": [{"publishAt": newer}, {"publishAt": note}]}},
        BUDDHA_URL: [{"post_date": newer}, {"post_date": buddha}],
        AI2026_URL: [{"post_date": ai2026}],
    }
    return lambda url: payloads[url]


def _pass_reconcile(m, tmp_path, writer, *, fetch_json=None, ledger=None, resolve=True):
    calls = []

    def resolver(owner, occurrence, *, no_dispatch_proof, expected_state):
        calls.append((owner, occurrence, no_dispatch_proof(), expected_state))
        return True

    result = m.reconcile(PASS_OCC, queued_at=PASS_QUEUED, state="claimed",
                         articles_path=ledger or _articles(tmp_path, [
                             _row("20261016-205812", "2026-10-16T21:31:00Z", "https://note.com/x/n/1")]),
                         fetch_json=fetch_json or _pass_readbacks(), resolver=resolver,
                         resolve=resolve, now=PASS_QUEUED + 3600, writer_root=writer,
                         runs_root=tmp_path / "no-runs", fetch_status=lambda url: 0,
                         absence_readback=lambda *a: None)
    return result, calls


def test_a_publication_free_resume_pass_closes_from_its_own_pass_records(tmp_path):
    m = _load()
    writer = _pass_fixture(tmp_path)
    result, calls = _pass_reconcile(m, tmp_path, writer)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is True, result
    owner, occurrence, proof, state = calls[0]
    assert (owner, occurrence, state) == ("article-resume", PASS_OCC, "claimed")
    assert proof["proof_type"] == "historical_writer_resume_no_dispatch" and proof["provider"] == "writer"
    assert proof["runtime_run_id"] == "18df6fc53500b510-26567"
    assert proof["branches"] == ["start", "self-heal"]
    receipt = writer / "fence-reconciliation" / "article-resume-18df6fc53500b510-26567.json"
    assert json.loads(receipt.read_text(encoding="utf-8")) == proof
    for branches in (["publication-paused"], ["lock-held"], ["start", "daily-schedule-not-due"]):
        writer = _pass_fixture(tmp_path / "-".join(branches), records=[
            _pass_record(branch, "2026-10-17T21:54:3%dZ" % i) for i, branch in enumerate(branches)])
        result, _ = _pass_reconcile(m, tmp_path, writer)
        assert result["status"] == "no_dispatch_proven", (branches, result)


def test_a_resume_pass_that_may_have_published_stays_fenced(tmp_path):
    m = _load()
    cases = {
        "publisher branch": dict(records=[_pass_record("start", "2026-10-17T21:54:30Z"),
                                          _pass_record("publication", "2026-10-17T21:54:31Z",
                                                       ["20261017-223414"])]),
        "catch-up exec": dict(records=[_pass_record("start", "2026-10-17T21:54:30Z"),
                                       _pass_record("missed-daily-schedule-catch-up", "2026-10-17T21:54:31Z")]),
        "repair model routed": dict(after_self_heal='{"status":"ROUTED"}'),
        "dispatcher failed": dict(after_self_heal='{"status":"NO_ACTIONABLE_INCIDENT"}\n'
                                                  'article-resume: repair routing failed closed'),
        "nonzero exit": dict(exit_code=1),
        "no records": dict(records=[]),
        "foreign pid": dict(records=[_pass_record("start", "2026-10-17T21:54:30Z"),
                                     _pass_record("self-heal", "2026-10-17T21:54:38Z", pid=1)]),
    }
    for name, kwargs in cases.items():
        writer = _pass_fixture(tmp_path / name.replace(" ", "-"), **kwargs)
        result, calls = _pass_reconcile(m, tmp_path, writer)
        assert result["status"] == "inconclusive" and calls == [], (name, result)
        assert result["reason"] == "fence_too_young" and result["pass_record"], (name, result)


def test_a_resume_pass_with_a_publication_inside_its_window_stays_fenced(tmp_path):
    m = _load()
    writer = _pass_fixture(tmp_path)
    in_window = "2026-10-17T21:54:35Z"
    ledger = _articles(tmp_path, [_row("20261017-223414", in_window, "https://note.com/x/n/2")])
    for kwargs, reason in (
            (dict(ledger=ledger), "writer_ledger_row_in_window"),
            (dict(fetch_json=_pass_readbacks(buddha=in_window)), "publication_in_window:substack:aniccabuddha"),
            (dict(fetch_json=_pass_readbacks(note="2026-10-18T07:00:00+09:00")),
             "readback_window_not_covered:note:anicca123"),
            (dict(fetch_json=lambda url: None), "readback_failed:note:anicca123")):
        result, calls = _pass_reconcile(m, tmp_path, writer, **kwargs)
        assert result["status"] == "inconclusive" and calls == [], result
        assert result["pass_record"] == reason, result


def test_a_pass_record_proof_without_resolve_writes_nothing(tmp_path):
    m = _load()
    writer = _pass_fixture(tmp_path)
    result, calls = _pass_reconcile(m, tmp_path, writer, resolve=False)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is False and calls == []
    assert not (writer / "fence-reconciliation").exists()


# 2026-10-18 01:24Z: article-resume:18df7b7d9c470800-55543 ran the deterministic substack/en publisher
# for run 20261017-223414 (draft 220918523); verify-preview refused before the publish POST and the
# pass exited 1.  The exit-0-only pass proof and the 7-day "nothing newer anywhere" proof both kept
# the fence forever, deferring every later resume wake.  Lines below are verbatim from the pass log
# (the 1 KB pending-notification JSON and the self-heal enqueue JSON are shortened; neither is read).
FATAL_OCC = "article-resume:18df7b7d9c470800-55543"
FATAL_QUEUED = 1792286648.46845   # 2026-10-18T01:24:08Z
FATAL_RUN = "20261017-223414"
FATAL_DRAFT = "220918523"
FATAL_LINE = ("FATAL: verify-preview FAILED — NOT publishing (an image may be too tall on screen, "
              "or the preview could not be opened at all -- check the message above for which).")
EN50_URL = "https://aniccaai2026.substack.com/api/v1/posts?limit=50"


def _fatal_record(branch, at, run_ids=(), pid=55713):
    return _pass_record(branch, at, run_ids, occurrence=FATAL_OCC, pid=pid)


def _fatal_segment():
    return [
        '{"status":"complete","run_id":"20261017-223414"}',
        "PII-GATE PASS stage=publish-substack-wrapper scanned=1",
        "== step 1/3: reuse stable Substack draft id=220918523 ==",
        "== step 3/3: verify + publish (send=false) + self-verify ==",
        "preview unavailable: RuntimeError: paid Substack preview unavailable",
        FATAL_LINE,
        "",
        json.dumps({"action": "retry", "count": 1, "notify": False, "pair": "substack/en",
                    "signature": FATAL_LINE}, ensure_ascii=False),
        json.dumps({"action": "retry", "count": 1, "notify": False, "pair": "substack/en",
                    "signature": FATAL_LINE}, ensure_ascii=False, separators=(",", ":")),
        '{"status":"pending"}',
        '{"version":1,"event_id":"article-pending:20261017-223414:cb94396de1f5ffd3","run_id":"20261017-223414"}',
    ]


def _fatal_fixture(tmp_path, *, segment=None, rc=1, exit_code=1, target=FATAL_DRAFT, tail=(),
                   terminal_pair="substack/en"):
    writer = tmp_path / "writer"
    (writer / "logs").mkdir(parents=True)
    lines = [
        "article-resume: run=20261017-223414 rc=0 deterministic=substack/ja",
        _fatal_record("start", "2026-10-18T01:29:18Z"),
        "article-resume: older publication backlog does not block daily schedule run=20261017-223414 "
        "date=2026-10-17 local=2026-10-18",
        '{"runs":6,"enqueued":6,"results":[]}',
        "article-resume: publication queue foreground; self-heal deferred run=20261017-223414",
        '{"status":"NO_ACTIONABLE_INCIDENT","observed_at":"2026-10-18T01:29:34Z","quarantined_run_handoffs":[],'
        '"reclaimed_stranded_leases":[],"recovered_orphaned_handoffs":[],"rearmed_on_new_code":[],'
        '"deployed_commit":"06141970eb640087ef4f9e696c909fbc607cfc5e"}',
        _fatal_record("publication", "2026-10-18T01:29:35Z", [FATAL_RUN]),
        *(segment if segment is not None else _fatal_segment()),
        f"article-resume: run={FATAL_RUN} rc={rc} deterministic={terminal_pair}",
        *tail,
    ]
    (writer / "logs/article-resume.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    events = [
        {"occurrence_id": FATAL_OCC, "phase": "execute", "status": "running", "exit_code": None,
         "event_id": "5df0847b871dcfbda41ad857", "timestamp": "2026-10-18T01:29:16.185904+00:00"},
        {"occurrence_id": FATAL_OCC, "phase": "report", "status": "fail" if exit_code else "pass",
         "exit_code": exit_code, "effect_status": "unknown", "event_id": "d4bec8d7df3d715a2646bccc",
         "release_sha": "c4a73cf5fb0b4d658f0a51d47e536b6d04070b12",
         "timestamp": "2026-10-18T01:30:14.907129+00:00"},
    ]
    (writer / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    gates = writer / "runs" / FATAL_RUN / "gates"
    gates.mkdir(parents=True)
    (gates / "publication-state.json").write_text(json.dumps({
        "destination_identities": {"substack/ja": "aniccabuddha.substack.com",
                                   "substack/en": "aniccaai2026.substack.com"},
        "pairs": {"substack/ja": {"status": "live", "target": "220918512"},
                  "substack/en": {"status": "intent", "target": target}}}))
    return writer


def _fatal_ledger(tmp_path, extra=()):
    return _articles(tmp_path, [
        _row(FATAL_RUN, "2026-10-18T01:11:14.903640Z", "https://note.com/anicca123/n/n824660e9ee21"),
        _row(FATAL_RUN, "2026-10-18T01:20:26.906060Z", "https://aniccabuddha.substack.com/p/claude-code-e8d",
             "substack"),
        *extra,
    ])


def _fatal_readbacks(en_posts=None, newer=None):
    """Readbacks observed 2026-10-19; `newer` adds a later post on every destination."""
    later = [{"id": 221500001, "post_date": newer}] if newer else []
    payloads = {
        NOTE_URL: {"data": {"contents": [{"publishAt": "2026-08-08T16:31:34+09:00"},
                                         *([{"publishAt": newer}] if newer else []),
                                         {"publishAt": "2026-10-18T10:11:09+09:00"}]}},
        BUDDHA_URL: [*later, {"post_date": "2026-10-18T01:20:14.480Z"}, {"post_date": "2026-10-17T11:09:18.659Z"}],
        AI2026_URL: [*later, {"post_date": "2026-09-29T02:57:45.886Z"}, {"post_date": "2026-09-28T14:03:44.337Z"}],
        EN50_URL: en_posts if en_posts is not None else [
            *later, {"id": 217933883, "post_date": "2026-09-29T02:57:45.886Z"},
            {"id": 217831411, "post_date": "2026-09-28T14:03:44.337Z"},
            {"id": 216391003, "post_date": "2026-09-19T02:21:20.926Z"}],
    }
    return lambda url: payloads[url]


def _fatal_reconcile(m, tmp_path, writer, *, fetch_json=None, ledger=None, now=FATAL_QUEUED + 86400,
                     resolve=True):
    calls = []

    def resolver(owner, occurrence, *, no_dispatch_proof, expected_state):
        calls.append((owner, occurrence, no_dispatch_proof(), expected_state))
        return True

    result = m.reconcile(FATAL_OCC, queued_at=FATAL_QUEUED, state="claimed",
                         articles_path=ledger or _fatal_ledger(tmp_path),
                         fetch_json=fetch_json or _fatal_readbacks(), resolver=resolver,
                         resolve=resolve, now=now, writer_root=writer,
                         runs_root=tmp_path / "no-runs", fetch_status=lambda url: 0,
                         absence_readback=lambda *a: None)
    return result, calls


def test_a_substack_pass_refused_by_verify_preview_closes_from_its_own_log(tmp_path):
    m = _load()
    writer = _fatal_fixture(tmp_path)
    result, calls = _fatal_reconcile(m, tmp_path, writer)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is True, result
    owner, occurrence, proof, state = calls[0]
    assert (owner, occurrence, state) == ("article-resume", FATAL_OCC, "claimed")
    assert proof["proof_type"] == "historical_writer_resume_no_dispatch" and proof["provider"] == "writer"
    assert proof["runtime_run_id"] == "18df7b7d9c470800-55543" and proof["branches"] == ["start", "publication"]
    touched = proof["touched"]
    assert (touched["stop"], touched["pair"], touched["draft_id"], touched["writer_run_id"]) == (
        "verify-preview-fatal", "substack/en", FATAL_DRAFT, FATAL_RUN)
    assert touched["readback_url"] == EN50_URL
    receipt = writer / "fence-reconciliation" / "article-resume-18df7b7d9c470800-55543.json"
    assert json.loads(receipt.read_text(encoding="utf-8")) == proof


def test_a_substack_pass_that_may_have_published_stays_fenced(tmp_path):
    m = _load()
    segment = _fatal_segment()
    slug_fail = "FATAL: publish API did not return a slug:"
    other_decision = json.dumps({"action": "retry", "count": 1, "notify": False, "pair": "substack/en",
                                 "signature": slug_fail}, separators=(",", ":"))
    delivered = '{"status":"complete","run_id":"20261017-223414","pending_pairs":[],"waiting":[]}'
    cases = {
        "publish POST failed after the gate": (dict(segment=[*segment[:5], slug_fail, "", other_decision]),
                                               "pass_substack_may_have_published"),
        "published line": (dict(segment=[*segment, "PUBLISHED: https://aniccaai2026.substack.com/p/x"]),
                           "pass_substack_may_have_published"),
        "decision for another pair": (dict(segment=[s.replace("substack/en", "substack/ja") for s in segment]),
                                      "pass_substack_may_have_published"),
        "decision before the FATAL line": (dict(segment=[*segment[:5], segment[7], segment[5]]),
                                           "pass_substack_may_have_published"),
        "terminal rc is not the report exit": (dict(rc=0), "pass_substack_terminal_unbound"),
        "self-owned delivered in this pass": (dict(segment=[delivered, *segment[1:]]),
                                              "pass_self_owned_may_have_published"),
        "durable target is another draft": (dict(target="220918999"), "pass_substack_draft_unbound"),
        "foreign pass record inside": (dict(segment=[*segment[:3], _pass_record("start", "2026-10-18T01:29:40Z"),
                                                     *segment[3:]]), "pass_record_unbound"),
    }
    for name, (kwargs, reason) in cases.items():
        writer = _fatal_fixture(tmp_path / name.replace(" ", "-"), **kwargs)
        result, calls = _fatal_reconcile(m, tmp_path, writer)
        assert result["status"] == "inconclusive" and calls == [], (name, result)
        assert result["reason"] == "fence_too_young" and result["pass_record"] == reason, (name, result)


def test_a_verify_preview_pass_whose_draft_reads_published_stays_fenced(tmp_path):
    m = _load()
    writer = _fatal_fixture(tmp_path)
    published = [{"id": int(FATAL_DRAFT), "post_date": "2026-10-18T01:29:50Z"},
                 {"id": 217933883, "post_date": "2026-09-29T02:57:45.886Z"}]
    uncovered = [{"id": 221500001, "post_date": "2026-10-18T02:00:00Z"}]
    for posts, reason in ((published, "touched_draft_published:aniccaai2026.substack.com"),
                          (uncovered, "readback_window_not_covered:aniccaai2026.substack.com"),
                          ([], "readback_failed:aniccaai2026.substack.com")):
        result, calls = _fatal_reconcile(m, tmp_path, writer, fetch_json=_fatal_readbacks(en_posts=posts))
        assert result["status"] == "inconclusive" and calls == [], result
        assert result["pass_record"] == reason, result


# 7-day path: compare only the pair/draft the bound pass touched.  Later articles publish on every
# destination; that must not keep this occurrence's fence forever.
def test_seven_day_resume_proof_reads_only_the_touched_substack_draft(tmp_path):
    m = _load()
    slug_fail = "FATAL: publish API did not return a slug:"
    segment = [*_fatal_segment()[:5], slug_fail, "",
               json.dumps({"action": "retry", "count": 1, "notify": False, "pair": "substack/en",
                           "signature": slug_fail}, separators=(",", ":"))]
    writer = _fatal_fixture(tmp_path, segment=segment)
    later_ledger = _fatal_ledger(tmp_path, [
        _row("20261024-213000", "2026-10-24T22:00:00Z", "https://note.com/x/n/later"),
        {**_row("20261024-213000", "2026-10-24T22:05:00Z", "https://aniccaai2026.substack.com/p/later",
                "substack"), "lang": "en"}])
    newer = "2026-10-24T22:05:00Z"
    now = FATAL_QUEUED + 8 * 86400
    result, calls = _fatal_reconcile(m, tmp_path, writer, fetch_json=_fatal_readbacks(newer=newer),
                                     ledger=later_ledger, now=now)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is True, result
    proof = calls[0][2]
    assert proof["proof_type"] == "historical_writer_resume_no_dispatch"
    assert (proof["touched"]["pair"], proof["touched"]["draft_id"]) == ("substack/en", FATAL_DRAFT)
    assert "stop" not in proof["touched"]
    # Younger than 7 days the same unproven failure stays fenced.
    result, calls = _fatal_reconcile(m, tmp_path, writer, fetch_json=_fatal_readbacks(newer=newer),
                                     ledger=later_ledger, now=FATAL_QUEUED + 6 * 86400)
    assert result["reason"] == "fence_too_young" and calls == []


def test_seven_day_touched_draft_proof_stays_fenced_without_its_readback(tmp_path):
    m = _load()
    writer = _fatal_fixture(tmp_path, segment=[*_fatal_segment()[:5], "FATAL: publish API did not return a slug:"])
    now = FATAL_QUEUED + 8 * 86400
    own_row = {**_row(FATAL_RUN, "2026-10-18T01:29:50Z", "https://aniccaai2026.substack.com/p/x", "substack"),
               "lang": "en"}
    published = [{"id": int(FATAL_DRAFT), "post_date": "2026-10-18T01:29:50Z"},
                 {"id": 217933883, "post_date": "2026-09-29T02:57:45.886Z"}]
    for kwargs, reason in (
            (dict(ledger=_fatal_ledger(tmp_path, [own_row])), "touched_pair_ledger_row_after_fence"),
            (dict(fetch_json=_fatal_readbacks(en_posts=published)),
             "touched_draft_published:aniccaai2026.substack.com"),
            (dict(fetch_json=_fatal_readbacks(en_posts=[])),
             "readback_failed:aniccaai2026.substack.com")):
        result, calls = _fatal_reconcile(m, tmp_path, writer, now=now, **kwargs)
        assert result["status"] == "inconclusive" and calls == [] and result["reason"] == reason, result


def test_verify_preview_fatal_line_still_precedes_the_only_publish_post():
    """The proof's premise: the wrapper prints PREVIEW_FATAL, exits, and only later POSTs /publish."""
    m = _load()
    wrapper = (SCRIPT.parent / "_shared" / "publish-substack-mermaid.sh").read_text(encoding="utf-8").splitlines()
    fatal = [i for i, line in enumerate(wrapper) if m.PREVIEW_FATAL in line]
    posts = [i for i, line in enumerate(wrapper) if '/publish"' in line and "-X POST" in line]
    assert len(fatal) == 1 and len(posts) == 1 and fatal[0] < posts[0]
    assert wrapper[fatal[0] + 1].strip() == "exit 5"
    # The bare two-key "complete" line is the self-owned worker's return before any git delivery.
    owned = (SCRIPT.parent / "self_owned_article.py").read_text(encoding="utf-8")
    body = owned[owned.index("def resume_publication("):owned.index("def main(")]
    early = body.index('return {"status": "complete", "run_id": contracts[0]["run_id"]}')
    assert early < body.index("commit_contract(") and early < body.index("push_rebased(")


def test_a_disk_deferred_claim_pairs_from_its_execute_event(tmp_path):
    # 2026-10-23: article-daily:18e10850f9d765a8-39094 was queued 01:41Z, the disk floor held it,
    # and it executed at 02:41:10Z; its resumed attempt started 02:41:29Z with no publication
    # state. Pairing from queued_at (60 min earlier) left it "no_run_paired_with_this_fence".
    m = _load()
    runs = tmp_path / "runs"
    d = _run_dir(runs, "20261008-120000", ["git-hash.txt", "article-daily-prompt.txt", "article-ja.md"])
    executed = datetime.fromtimestamp(GATE_QUEUED, timezone.utc) + timedelta(minutes=60)
    (d / "gates" / "generation-state.json").write_text(json.dumps(
        {"attempts": [{"attempt": 3, "started_at": (executed + timedelta(seconds=19))
                       .isoformat().replace("+00:00", "Z")}]}))
    writer = tmp_path / "writer"
    writer.mkdir()
    (writer / "events.jsonl").write_text(json.dumps({
        "phase": "execute", "occurrence_id": GATE_OCC, "loop_id": OWNER,
        "timestamp": executed.isoformat(),
    }) + "\n")
    closed = []
    result = m.reconcile(GATE_OCC, queued_at=GATE_QUEUED, state="claimed",
                         articles_path=_articles(tmp_path, []), runs_root=runs,
                         fetch_status=lambda u: 200, writer_root=writer, resolve=True,
                         pre_effect_resolver=lambda owner, occ, **k: closed.append(occ) or True)
    assert result["status"] == "pre_effect" and result["closed"] is True and closed == [GATE_OCC]


def test_an_earlier_execute_whose_run_published_keeps_the_fence(tmp_path):
    # Review of the execute anchor: a requeued occurrence can execute twice; the run paired with
    # the first execute published, so the later unpublished run must not close the fence.
    m = _load()
    runs = tmp_path / "runs"
    first = datetime.fromtimestamp(GATE_QUEUED, timezone.utc) + timedelta(minutes=2)
    second = first + timedelta(hours=2)
    published = _run_dir(runs, first.strftime("%Y%m%d-%H%M%S"), ["git-hash.txt"])
    (published / "gates" / "publication-state.json").write_text("{}")
    _run_dir(runs, (second + timedelta(seconds=19)).strftime("%Y%m%d-%H%M%S"), ["git-hash.txt"])
    writer = tmp_path / "writer"
    writer.mkdir()
    (writer / "events.jsonl").write_text("".join(json.dumps({
        "phase": "execute", "occurrence_id": GATE_OCC, "timestamp": when.isoformat(),
    }) + "\n" for when in (first, second)))
    closed = []
    result = m.reconcile(GATE_OCC, queued_at=GATE_QUEUED, state="claimed",
                         articles_path=_articles(tmp_path, []), runs_root=runs,
                         fetch_status=lambda u: 200, writer_root=writer, resolve=True,
                         pre_effect_resolver=lambda owner, occ, **k: closed.append(occ) or True)
    assert result["status"] == "inconclusive" and result["reason"] == "run_reached_publication"
    assert closed == []


INIT_REFUSAL = ("refuse initialization: v1 manifest must bind every active pair once "
                "with one landing URL and product id")
REJECTED_SELF_OWNED_PUSH = [
    "Traceback (most recent call last):",
    '  File "/r/skills/writer-agent/scripts/self_owned_article.py", line 622, in resume_publication',
    '    _git(landing_root, "push", remote, f"HEAD:refs/heads/{branch}")',
    "SelfOwnedInvariant: To https://github.com/Daisuke134/anicca-products.git",
    " ! [rejected]        HEAD -> main (fetch first)",
    "error: failed to push some refs to 'https://github.com/Daisuke134/anicca-products.git'",
    "hint: Updates were rejected because the remote contains work that you do not",
    "article-resume: self-owned worker remains pending",
]


def test_a_pass_whose_initialization_refused_before_staging_closes_from_its_own_log(tmp_path):
    # 2026-10-24 article-resume:18e138af98c6dd90-45840: rejected self-owned push, then
    # execute-initialization-pair refused before any staging; Writer resume stayed fenced 7 days.
    m = _load()
    writer = _fatal_fixture(tmp_path, segment=[*REJECTED_SELF_OWNED_PUSH, INIT_REFUSAL],
                            terminal_pair="initialize-note/ja")
    result, calls = _fatal_reconcile(m, tmp_path, writer)
    assert result["status"] == "no_dispatch_proven" and result["closed"] is True, result
    touched = calls[0][2]["touched"]
    assert (touched["stop"], touched["pair"], touched["writer_run_id"], touched["self_owned_push"]) == (
        "initialization-refused", "note/ja", FATAL_RUN, "rejected")


def test_an_initialization_pass_that_may_have_had_an_effect_stays_fenced(tmp_path):
    m = _load()
    pushed = [line for line in REJECTED_SELF_OWNED_PUSH if "[rejected]" not in line]
    cases = {
        "no refusal line": ([*REJECTED_SELF_OWNED_PUSH], "initialize-note/ja"),
        "push not rejected": ([*pushed, "   1a2b3c4..5d6e7f8  HEAD -> main", INIT_REFUSAL], "initialize-note/ja"),
        "unknown line before refusal": ([*REJECTED_SELF_OWNED_PUSH, "staged note draft 123", INIT_REFUSAL],
                                        "initialize-note/ja"),
    }
    for name, (segment, pair) in cases.items():
        case_root = tmp_path / name.replace(" ", "-")
        writer = _fatal_fixture(case_root, segment=segment, terminal_pair=pair)
        result, calls = _fatal_reconcile(m, case_root, writer)
        assert result["closed"] is False and calls == [], (name, result)
