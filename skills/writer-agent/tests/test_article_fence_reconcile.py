"""article-daily fence reconcile: close a fence only on a live-URL proof of a publish, never on absence.

2026-10-09: a single claimed+effect_unknown admission row from 9/29 10:01 JST kept article-daily
deferred (resource_effect_unknown) for 10 days; the run had published to note and Substack.  A
time window is used only to PAIR a fence with a publish, never to infer that nothing happened.
"""

import importlib.util
import json
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
GATE_OCC = f"{OWNER}:18dcb160db0ac660-67443"


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


def test_a_run_that_reached_generation_or_has_no_run_never_closes_as_pre_effect(tmp_path):
    m = _load()
    for n, (files, rows, reason) in enumerate((
        (["git-hash.txt", "article-daily-prompt.txt"], [], "run_reached_generation"),
        (["git-hash.txt", "model-stdout.log"], [], "run_reached_generation"),
        (["git-hash.txt"], [{"run_id": "20261008-232303"}], "run_reached_generation"),
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
