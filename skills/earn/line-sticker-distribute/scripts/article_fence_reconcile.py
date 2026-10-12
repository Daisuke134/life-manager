#!/usr/bin/env python3
"""Close one line-sticker-articles effect_unknown admission fence.

Same decision shape as capafy_distribute_fence_reconcile.py (its free aniccaai.com articles go
through the same publisher, capafy_free_article.py) and distribute_fence_reconcile.py (official
listing vs this loop's ledger), one proof per occurrence, never a guess. This loop's only external
effect is a free article committed to the aniccaai.com landing repo as
apps/landing/data/research/line-sticker-<set_id>-<YYYY-MM-DD>-<HH>.json, and every published
article's URL is written to article-ledger.json. The official readback is the landing repo's
GitHub remote branch:
  - Every line-sticker article the remote gained inside [queued_at, queued_at + MAX_RUN_SECONDS]
    is in the ledger as published, and enough time has passed: nothing unaccounted was published,
    so close as no-effect, citing the remote head as the receipt.
  - An article in that window missing from the ledger may be this run's publish: stays fenced.
  - Any readback failure, or too recent: stays fenced.
An article added before the window cannot be this run's effect (e.g. the ones published while the
article step still ran inside line-sticker-distribute, ledgered in that loop's state root).

Usage:
    python3 article_fence_reconcile.py --occurrence line-sticker-articles:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
for path in (REPO_ROOT, HERE):  # `python3 -I` puts neither on sys.path
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from distribute_fence_reconcile import fenced_row  # noqa: E402

OWNER_ID = "line-sticker-articles"
# compose (<= 300 s) + PII gate + git push + live readback (40 x 15 s); the default runtime cap.
MAX_RUN_SECONDS = 3600
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + 900
STATE_ROOT = Path(os.environ.get(
    "LINE_STICKER_ARTICLES_STATE_ROOT", "~/.local/state/life-manager/line-sticker-articles")).expanduser()
LANDING_ROOT = Path(os.environ.get(
    "ARTICLE_SELF_OWNED_LANDING_ROOT",
    "~/.local/state/life-manager/writer/checkouts/self-owned-landing")).expanduser()
ARTICLES_GLOB = "apps/landing/data/research/line-sticker-*.json"


def ledger_slugs(rows: dict) -> set[str]:
    return {str(row["url"]).rstrip("/").rsplit("/", 1)[-1] for row in rows.values()
            if isinstance(row, dict) and row.get("status") == "published" and row.get("url")}


def parse_added(out: str) -> list[dict[str, str]]:
    """`git log --format=@%H|%cI --name-only` -> one row per added article file."""
    rows, sha, at = [], "", ""
    for line in out.splitlines():
        if line.startswith("@"):
            sha, at = line[1:].split("|", 1)
        elif line.strip():
            rows.append({"slug": Path(line.strip()).stem, "sha": sha, "at": at})
    return rows


def read_landing_articles(start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    """line-sticker articles added on the landing repo's GitHub remote branch inside the window."""
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(LANDING_ROOT), *args], check=True,
                              capture_output=True, text=True, timeout=120).stdout
    try:
        git("fetch", "-q", "origin")
        head = git("rev-parse", "origin/main").strip()
        out = git("log", "origin/main", "--diff-filter=A", "--format=@%H|%cI", "--name-only",
                  f"--since={start.isoformat()}", f"--until={end.isoformat()}", "--", ARTICLES_GLOB)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "reason": f"github_readback_failed:{type(exc).__name__}"}
    return {"ok": True, "head": head, "articles": parse_added(out)}


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                landing: dict[str, Any], ledger_slugs: set[str]) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    if not landing.get("ok"):
        proof["reason"] = landing.get("reason")
        return proof
    window = sorted({a["slug"] for a in landing["articles"]})
    unledgered = [slug for slug in window if slug not in ledger_slugs]
    if unledgered:
        proof["reason"] = "unledgered_article:" + ",".join(unledgered)
        return proof
    age = (now - queued_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    proof.update(verified=True, effected=False, ledgered_window_articles=window,
                 provider_receipt_id=f"github:{landing['head']}|line-sticker-articles-all-ledgered:{len(window)}",
                 proof_kind="official_github_landing_articles_vs_ledger",
                 checked_at=now.isoformat(timespec="seconds"))
    return proof


def reconcile(occurrence_id: str, *, resolve: bool = False) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row(OWNER_ID, occurrence_id)
    ledger_path = STATE_ROOT / "article-ledger.json"
    rows = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    proof = build_proof(occurrence_id, queued_at, now=now,
                        landing=read_landing_articles(queued_at, queued_at + dt.timedelta(seconds=MAX_RUN_SECONDS)),
                        ledger_slugs=ledger_slugs(rows))
    result = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
    from runtime.host.resource_admission import resolve_unknown_occurrence

    result["closed"] = resolve_unknown_occurrence(OWNER_ID, occurrence_id,
                                                  official_readback=lambda: proof, expected_state=state)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--occurrence", required=True)
    parser.add_argument("--resolve", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = reconcile(args.occurrence, resolve=args.resolve)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"owner_id": OWNER_ID, "occurrence_id": args.occurrence,
                          "verified": False, "error": f"{type(exc).__name__}:{exc}"}))
        print("LINE_STICKER_ARTICLES_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str, ensure_ascii=False))
    if not result.get("verified"):
        print("LINE_STICKER_ARTICLES_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("LINE_STICKER_ARTICLES_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("LINE_STICKER_ARTICLES_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("LINE_STICKER_ARTICLES_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
