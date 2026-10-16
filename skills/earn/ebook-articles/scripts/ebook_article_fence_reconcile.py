#!/usr/bin/env python3
"""Close one ebook-articles effect_unknown admission fence.

Copy of line-sticker-articles' article_fence_reconcile.py (same publisher, same landing repo): the
only external effect is apps/landing/data/research/ebook-<en|ja>-<YYYY-MM-DD>-<HH>.json committed to
the aniccaai.com landing repo, so the official readback is that repo's GitHub remote branch.
  - The fenced slot's own article is on the remote inside the run window, carries the product's
    checkout link, and the ledger attempted that slot: close as effected and record it.
  - Any other article in the window missing from the ledger, a failed readback, or too recent:
    stays fenced.
  - No article in the window and old enough: close as no-effect, citing the remote head.

Usage:
    python3 ebook_article_fence_reconcile.py --occurrence ebook-articles:<run_id> [--resolve]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
STICKER_SCRIPTS = REPO_ROOT / "skills/earn/line-sticker-distribute/scripts"
for path in (REPO_ROOT, HERE, STICKER_SCRIPTS):  # `python3 -I` puts none of them on sys.path
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from article_fence_reconcile import parse_added, write_ledger_patch  # noqa: E402
from distribute_fence_reconcile import fenced_row  # noqa: E402
from ebook_article_daily import JST, load_product  # noqa: E402

OWNER_ID = "ebook-articles"
MAX_RUN_SECONDS = 3600
NO_EFFECT_MIN_AGE_SECONDS = MAX_RUN_SECONDS + 900
STATE_ROOT = Path(os.environ.get(
    "EBOOK_ARTICLES_STATE_ROOT", "~/.local/state/life-manager/ebook-articles")).expanduser()
LANDING_ROOT = Path(os.environ.get(
    "ARTICLE_SELF_OWNED_LANDING_ROOT",
    "~/.local/state/life-manager/writer/checkouts/self-owned-landing")).expanduser()
ARTICLES_GLOB = "apps/landing/data/research/ebook-*.json"
ARTICLE_SLUG = re.compile(r"^(ebook-(?:en|ja))-(\d{4}-\d{2}-\d{2})-(\d{2})$")


def read_landing_articles(start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(LANDING_ROOT), *args], check=True,
                              capture_output=True, text=True, timeout=120).stdout
    try:
        git("fetch", "-q", "origin")
        head = git("rev-parse", "origin/main").strip()
        articles = parse_added(git("log", "origin/main", "--diff-filter=A", "--format=@%H|%cI", "--name-only",
                                   f"--since={start.isoformat()}", f"--until={end.isoformat()}",
                                   "--", ARTICLES_GLOB))
        for article in articles:
            if not ARTICLE_SLUG.fullmatch(article["slug"]):
                return {"ok": False, "reason": "invalid_landing_article_slug"}
            document = json.loads(git("show", f"origin/main:apps/landing/data/research/{article['slug']}.json"))
            article.update(date=document.get("date"), title=document.get("title"),
                           markdown=document.get("markdown"))
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "reason": f"github_readback_failed:{type(exc).__name__}"}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "reason": "github_article_readback_invalid"}
    return {"ok": True, "head": head, "articles": articles}


def _slot_patch(article: dict[str, Any], queued_at: dt.datetime, rows: dict[str, Any]) -> dict[str, Any] | None:
    """The fenced slot's own article, committed inside the run window with its checkout link."""
    match = ARTICLE_SLUG.fullmatch(str(article.get("slug", "")))
    if not match:
        return None
    product_id, date, hour = match.groups()
    key = f"{date}@{hour}"
    current = rows.get(key)
    if queued_at.astimezone(JST).strftime("%Y-%m-%d@%H") != key or not isinstance(current, dict) \
            or current.get("product_id") != product_id or not isinstance(current.get("attempts"), int) \
            or current["attempts"] < 1 or current.get("status") not in (None, "failed", "published"):
        return None
    try:
        committed = dt.datetime.fromisoformat(str(article["at"])).astimezone(dt.timezone.utc)
    except (KeyError, ValueError):
        return None
    start = queued_at.astimezone(dt.timezone.utc)
    url_count = str(article.get("markdown", "")).count(load_product(product_id)["destination_url"])
    if not start <= committed <= start + dt.timedelta(seconds=MAX_RUN_SECONDS) or url_count != 1 \
            or not re.fullmatch(r"[0-9a-f]{40}", str(article.get("sha"))) or not str(article.get("title", "")).strip():
        return None
    url = f"https://aniccaai.com/blog/{article['slug']}"
    if current.get("status") == "published" and (current.get("url") != url or current.get("commit") != article["sha"]):
        return None
    entry = {**current, "status": "published", "url": url, "title": article["title"], "commit": article["sha"]}
    return {"key": key, "expected": current, "entry": entry, "slug": article["slug"]}


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                landing: dict[str, Any], ledger_rows: dict[str, Any]) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    if not landing.get("ok"):
        proof["reason"] = landing.get("reason")
        return proof
    articles = landing["articles"]
    ledgered = {str(r.get("url", "")).rsplit("/", 1)[-1] for r in ledger_rows.values()
                if isinstance(r, dict) and r.get("status") == "published"}
    patches = [p for a in articles if (p := _slot_patch(a, queued_at, ledger_rows))]
    unexplained = sorted(a["slug"] for a in articles
                         if a["slug"] not in ledgered and a["slug"] not in {p["slug"] for p in patches})
    if unexplained:
        proof["reason"] = "unledgered_article:" + ",".join(unexplained)
        return proof
    if patches:
        patch = patches[0]
        proof.update(verified=True, effected=True, ledger_patch=patch,
                     provider_receipt_id=f"github:{patch['entry']['commit']}|ebook-article:{patch['slug']}",
                     proof_kind="official_github_article_exact_slot_checkout_url",
                     checked_at=now.isoformat(timespec="seconds"))
        return proof
    age = (now - queued_at).total_seconds()
    if age <= NO_EFFECT_MIN_AGE_SECONDS:
        proof["reason"] = f"too_recent:{int(age)}s<={NO_EFFECT_MIN_AGE_SECONDS}s"
        return proof
    proof.update(verified=True, effected=False,
                 provider_receipt_id=f"github:{landing['head']}|ebook-articles-all-ledgered:{len(articles)}",
                 proof_kind="official_github_landing_articles_vs_ledger",
                 checked_at=now.isoformat(timespec="seconds"))
    return proof


def reconcile(occurrence_id: str, *, resolve: bool = False) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row(OWNER_ID, occurrence_id)
    ledger_path = STATE_ROOT / "article-ledger.json"
    rows = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    proof = build_proof(occurrence_id, queued_at, now=now, ledger_rows=rows,
                        landing=read_landing_articles(queued_at, queued_at + dt.timedelta(seconds=MAX_RUN_SECONDS)))
    result = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
    if proof.get("effected") is True:
        write_ledger_patch(ledger_path, proof["ledger_patch"])
        result["ledger_recorded"] = True
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
        print("EBOOK_ARTICLES_FENCE_RECONCILE=FAIL", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, default=str, ensure_ascii=False))
    if not result.get("verified"):
        print("EBOOK_ARTICLES_FENCE_RECONCILE=HELD")
        return 1
    if not args.resolve:
        print("EBOOK_ARTICLES_FENCE_RECONCILE=PROOF_READY")
        return 0
    if not result.get("closed"):
        print("EBOOK_ARTICLES_FENCE_RECONCILE=FAIL reason=admission_refused_close", file=sys.stderr)
        return 1
    print("EBOOK_ARTICLES_FENCE_RECONCILE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
