#!/usr/bin/env python3
"""Close one article-daily effect_unknown admission fence: a live-URL proof of a publish, or a paired
run that stopped before generation (no prompt file, no model output, no ledger row).

The fence is closed only when a Writer run that STARTED shortly after the fenced occurrence has a
published article whose URL answers HTTP 200.  The time window pairs a fence with a run; it is
never used to conclude that nothing happened (2026-10-09: a window-only no-dispatch proof closed
316 growth fences wrongly).  No proof -> the fence stays.

    python3 article_fence_reconcile.py --occurrence article-daily:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "article-daily"
PAIR_WINDOW_SECONDS = 1800        # a Writer run starts within 30 min after the admission claim
MIN_AGE_SECONDS = 3600            # never touch a fence whose run may still be going
ADMISSION_DB = Path.home() / ".local/state/life-manager/host-admission/resources/admission-v2.sqlite3"
ARTICLES = Path.home() / ".local/state/life-manager/writer/articles.jsonl"
RUNS_ROOT = Path.home() / ".local/state/life-manager/writer/runs"
# article-daily.sh writes these only after the paid-demand gate, right before / after the provider call.
GENERATION_MARKERS = ("article-daily-prompt.txt", "model-stdout.log")


def _run_start_epoch(run_id: str) -> float | None:
    """Writer run ids are YYYYMMDD-HHMMSS in UTC."""
    try:
        return datetime.strptime(run_id[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def _http_status(url: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "lm-article-fence-reconcile"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, OSError):
        return 0


def _inconclusive(occurrence_id: str, reason: str) -> dict:
    return {"status": "inconclusive", "reason": reason, "occurrence_id": occurrence_id, "closed": False}


def _pre_effect(occurrence_id: str, queued_at: float, state: str, rows: list, runs_root: Path,
                resolver: Callable[..., bool] | None, resolve: bool) -> dict:
    """Close a fence whose paired run stopped before the provider was ever invoked.

    Positive evidence only: at least one run dir started in the pairing window, and none of the paired
    runs has a generation marker or a ledger row.  No paired run -> the fence stays (absence of a run
    is not proof).
    """
    try:
        paired = sorted(d for d in runs_root.iterdir()
                        if d.is_dir() and (started := _run_start_epoch(d.name)) is not None
                        and 0 <= started - queued_at <= PAIR_WINDOW_SECONDS)
    except OSError:
        return _inconclusive(occurrence_id, "runs_root_unreadable")
    if not paired:
        return _inconclusive(occurrence_id, "no_run_paired_with_this_fence")
    ledger_runs = {str(row.get("run_id", "")) for row in rows}
    if any(d.name in ledger_runs or any((d / m).exists() for m in GENERATION_MARKERS) for d in paired):
        return _inconclusive(occurrence_id, "run_reached_generation")
    evidence = "writer-run-no-generation-marker:" + ",".join(d.name for d in paired)
    result = {"status": "pre_effect", "occurrence_id": occurrence_id, "closed": False, "evidence_ref": evidence}
    if not resolve:
        return result
    if resolver is None:
        from runtime.host.resource_admission import resolve_pre_effect_occurrence
        resolver = resolve_pre_effect_occurrence
    proof = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
             "proof_type": "pre_effect", "evidence_ref": evidence}
    result["closed"] = bool(resolver(OWNER_ID, occurrence_id, pre_effect_readback=lambda: proof,
                                     expected_state=state))
    return result


def reconcile(occurrence_id: str, *, queued_at: float, state: str, articles_path: Path = ARTICLES,
              fetch_status: Callable[[str], int] = _http_status, resolver: Callable[..., bool] | None = None,
              resolve: bool = False, now: float | None = None, runs_root: Path = RUNS_ROOT,
              pre_effect_resolver: Callable[..., bool] | None = None) -> dict:
    if not occurrence_id.startswith(f"{OWNER_ID}:"):
        return _inconclusive(occurrence_id, "owner_not_allowlisted")
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    if now - queued_at < MIN_AGE_SECONDS:
        return _inconclusive(occurrence_id, "fence_too_young")
    try:
        rows = [json.loads(line) for line in articles_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return _inconclusive(occurrence_id, "articles_ledger_unreadable")
    candidates = []
    for row in rows:
        started = _run_start_epoch(str(row.get("run_id", "")))
        url = str(row.get("live_url") or "")
        if started is None or not url.startswith("https://"):
            continue
        if 0 <= started - queued_at <= PAIR_WINDOW_SECONDS:
            candidates.append(row)
    proven = [row for row in candidates if fetch_status(str(row["live_url"])) == 200]
    if not proven:
        return _pre_effect(occurrence_id, queued_at, state, rows, runs_root, pre_effect_resolver, resolve)
    receipt = str(proven[0]["live_url"])
    result = {"status": "effected", "occurrence_id": occurrence_id, "closed": False,
              "provider_receipt_id": receipt, "run_id": proven[0].get("run_id"),
              "live_urls": [str(row["live_url"]) for row in proven]}
    if not resolve:
        return result
    if resolver is None:
        from runtime.host.resource_admission import resolve_unknown_occurrence
        resolver = resolve_unknown_occurrence
    proof = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id, "verified": True,
             "provider_receipt_id": receipt}
    result["closed"] = bool(resolver(OWNER_ID, occurrence_id, official_readback=lambda: proof,
                                     expected_state=state))
    return result


def _admission_row(occurrence_id: str) -> tuple[float, str] | None:
    try:
        with sqlite3.connect(f"file:{ADMISSION_DB}?mode=ro", uri=True, timeout=20) as connection:
            row = connection.execute(
                "SELECT queued_at, state FROM occurrences WHERE occurrence_id=? AND owner_id=? "
                "AND effect_unknown=1", (occurrence_id, OWNER_ID)).fetchone()
    except sqlite3.Error:
        return None
    return (float(row[0]), str(row[1])) if row else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    row = _admission_row(args.occurrence)
    if row is None:
        result = _inconclusive(args.occurrence, "occurrence_not_fenced_or_unreadable")
    else:
        result = reconcile(args.occurrence, queued_at=row[0], state=row[1], resolve=args.resolve)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in ("effected", "pre_effect") and (result["closed"] or not args.resolve) else 1


if __name__ == "__main__":
    raise SystemExit(main())
