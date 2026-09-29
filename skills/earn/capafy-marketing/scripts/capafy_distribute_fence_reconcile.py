#!/usr/bin/env python3
"""Close one capafy-distribute-daily effect_unknown admission fence.

Same decision shape as capafy_ig_fence_reconcile.py (one effected / no-effect
proof per occurrence, never a guess). capafy-distribute-daily's only external
effects are (1) a free article committed to the aniccaai.com landing repo on
GitHub and served live, and (2) an X post created through Postiz, which only
happens after (1). The official readbacks are therefore:
  - GitHub: commits "publish free article capafy-..." on the landing repo's
    remote branch inside [queued_at, queued_at + MAX_RUN_SECONDS];
  - the live aniccaai.com page for that slug (HTTP 200);
  - Postiz: posts on the X integration inside the same window.

  - A landing commit in the window whose live page answers 200 proves the
    effect happened: close as effected (the page URL + commit is the receipt).
  - No landing commit AND no Postiz X post in the window AND enough time has
    passed proves no effect: close as no-effect, citing both listings.
  - Any readback failure, or not enough time yet: stays fenced.

Usage:
    python3 capafy_distribute_fence_reconcile.py --occurrence capafy-distribute-daily:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OWNER_ID = "capafy-distribute-daily"
# model pass timeout (1800 s) + aniccaai deploy readback (<= 15 min) + X readback (<= 10 min).
MAX_RUN_SECONDS = 4200
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + 900
LANDING_ROOT = Path(os.environ.get(
    "CAPAFY_DISTRIBUTE_LANDING_ROOT",
    "~/.local/state/life-manager/writer/checkouts/self-owned-landing")).expanduser()
BASE_URL = "https://aniccaai.com/blog/"
X_INTEGRATION_ID = os.environ.get("POSTIZ_X_INTEGRATION_ID", "cmt4l2jld031tqp0y8qtyo983")
COMMIT_PREFIX = "feat(capafy-distribute): publish free article "


def fenced_row(owner_id: str, occurrence_id: str) -> tuple[str, dt.datetime]:
    """Read (state, queued_at) of the fenced row without mutating the ledger."""
    from runtime.host import resource_admission

    database = resource_admission.state_root() / "admission-v2.sqlite3"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            """SELECT state, queued_at FROM occurrences
                 WHERE owner_id=? AND occurrence_id=? AND effect_unknown=1""",
            (owner_id, occurrence_id),
        ).fetchone()
    if row is None or row[1] is None:
        raise ValueError("occurrence is not an effect_unknown row")
    return str(row[0]), dt.datetime.fromtimestamp(float(row[1]), dt.timezone.utc)


def read_landing_commits(start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    """Commits on the landing repo's GitHub remote branch inside the window."""
    try:
        subprocess.run(["git", "-C", str(LANDING_ROOT), "fetch", "-q", "origin"],
                       check=True, capture_output=True, timeout=120)
        out = subprocess.run(
            ["git", "-C", str(LANDING_ROOT), "log", "origin/main", "--format=%H|%cI|%s",
             f"--since={start.isoformat()}", f"--until={end.isoformat()}"],
            check=True, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "reason": f"github_readback_failed:{type(exc).__name__}"}
    hits = []
    for line in out.splitlines():
        sha, when, subject = line.split("|", 2)
        if subject.startswith(COMMIT_PREFIX):
            hits.append({"sha": sha, "at": when, "slug": subject[len(COMMIT_PREFIX):].strip()})
    return {"ok": True, "commits": hits}


def page_status(slug: str) -> int:
    try:
        with urllib.request.urlopen(BASE_URL + slug, timeout=20) as response:
            return response.status
    except Exception:  # noqa: BLE001 -- any failure is "not proven live"
        return 0


def read_x_posts(start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    key = os.environ.get("POSTIZ_API_KEY") or os.environ.get("LM_POSTIZ_API_KEY")
    if not key:
        return {"ok": False, "reason": "postiz_key_missing"}
    try:
        sys.path.insert(0, str(REPO_ROOT / "skills/earn/marketing-engine/publish"))
        from postiz_adapter import HttpPostizClient  # noqa: PLC0415
        posts = HttpPostizClient(key).list_posts(start, end)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"postiz_readback_failed:{type(exc).__name__}"}
    ours = [p for p in posts if (p.get("integration") or {}).get("id") == X_INTEGRATION_ID]
    return {"ok": True, "posts": [p.get("id") for p in ours]}


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                commits: dict[str, Any], x_posts: dict[str, Any],
                page_status_fn: Callable[[str], int] = page_status) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    if not commits.get("ok"):
        proof["reason"] = commits.get("reason")
        return proof
    for commit in commits["commits"]:
        if page_status_fn(commit["slug"]) == 200:
            proof.update(verified=True, effected=True,
                         provider_receipt_id=f"github:{commit['sha']}|{BASE_URL}{commit['slug']}",
                         proof_kind="official_github_landing_commit_and_live_page",
                         checked_at=now.isoformat(timespec="seconds"))
            return proof
    if commits["commits"]:
        proof["reason"] = "landing_commit_without_live_page"
        return proof
    age = (now - queued_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    if not x_posts.get("ok"):
        proof["reason"] = x_posts.get("reason")
        return proof
    if x_posts["posts"]:
        proof["reason"] = "x_post_without_article"
        return proof
    proof.update(verified=True, effected=False,
                 provider_receipt_id=f"github-landing-and-postiz-x-empty:{queued_at.isoformat()}",
                 proof_kind="official_github_commits_and_postiz_listing",
                 checked_at=now.isoformat(timespec="seconds"))
    return proof


def reconcile(occurrence_id: str, *, resolve: bool = False, now: dt.datetime | None = None,
              fenced_row_fn=fenced_row, commits_fn=read_landing_commits,
              x_fn=read_x_posts, page_status_fn=page_status, resolve_fn=None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row_fn(OWNER_ID, occurrence_id)
    end = queued_at + dt.timedelta(seconds=MAX_RUN_SECONDS)
    proof = build_proof(occurrence_id, queued_at, now=now, commits=commits_fn(queued_at, end),
                        x_posts=x_fn(queued_at, end), page_status_fn=page_status_fn)
    result = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
    if resolve_fn is None:
        from runtime.host.resource_admission import resolve_unknown_occurrence
        resolve_fn = resolve_unknown_occurrence
    result["closed"] = resolve_fn(OWNER_ID, occurrence_id,
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
        print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str))
    if not result.get("verified"):
        print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("CAPAFY_DISTRIBUTE_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
