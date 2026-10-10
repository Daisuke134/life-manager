"""article-daily fence reconcile: require publish proof or exact historical gate-stop proof.

2026-10-09: a single claimed+effect_unknown admission row from 9/29 10:01 JST kept article-daily
deferred (resource_effect_unknown) for 10 days; the run had published to note and Substack.  A
time window is used only to PAIR a fence with a publish, never to infer that nothing happened.
"""

import hashlib
import importlib.util
import json
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
