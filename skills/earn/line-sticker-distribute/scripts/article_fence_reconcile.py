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
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
JST = ZoneInfo("Asia/Tokyo")
STATE_ROOT = Path(os.environ.get(
    "LINE_STICKER_ARTICLES_STATE_ROOT", "~/.local/state/life-manager/line-sticker-articles")).expanduser()
LANDING_ROOT = Path(os.environ.get(
    "ARTICLE_SELF_OWNED_LANDING_ROOT",
    "~/.local/state/life-manager/writer/checkouts/self-owned-landing")).expanduser()
ARTICLES_GLOB = "apps/landing/data/research/line-sticker-*.json"
ARTICLE_SLUG = re.compile(r"^line-sticker-(set-\d{3})-(\d{4}-\d{2}-\d{2})-(\d{2})$")
LINE_URL = re.compile(r"(?:(?:https?:)?//)(?:www\.)?line\.me/[^\s<>()\[\]\"']+", re.IGNORECASE)


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
        articles = parse_added(out)
        for article in articles:
            if not ARTICLE_SLUG.fullmatch(article["slug"]):
                return {"ok": False, "reason": "invalid_landing_article_slug"}
            path = f"apps/landing/data/research/{article['slug']}.json"
            document = json.loads(git("show", f"origin/main:{path}"))
            if document.get("slug") != article["slug"]:
                return {"ok": False, "reason": "landing_article_slug_mismatch"}
            article.update(date=document.get("date"), title=document.get("title"),
                           markdown=document.get("markdown"), path=path)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "reason": f"github_readback_failed:{type(exc).__name__}"}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "reason": "github_article_readback_invalid"}
    return {"ok": True, "head": head, "articles": articles}


def load_purchase_urls() -> dict[str, str]:
    from pick_set import load_on_sale_sets

    state_root = Path(os.environ.get(
        "LINE_STICKER_STATE_ROOT", "~/.local/state/life-manager/line-sticker")).expanduser()
    return {row["set_id"]: row["purchase_url"]
            for row in load_on_sale_sets(state_root, require_clips=False)}


def positive_ledger_patch(article: dict[str, Any], queued_at: dt.datetime,
                          ledger_rows: dict[str, Any], purchase_urls: dict[str, str]) -> dict[str, Any] | None:
    match = ARTICLE_SLUG.fullmatch(str(article.get("slug", "")))
    if not match:
        return None
    set_id, date, hour = match.groups()
    slot_key = f"{date}@{hour}"
    queued_local = queued_at.astimezone(JST)
    if queued_local.strftime("%Y-%m-%d@%H") != slot_key:
        return None
    current = ledger_rows.get(slot_key)
    if (not isinstance(current, dict) or current.get("set_id") != set_id
            or type(current.get("attempts")) is not int or current["attempts"] < 1):
        return None
    try:
        committed_at = dt.datetime.fromisoformat(str(article["at"]))
        if committed_at.tzinfo is None:
            return None
        committed_at = committed_at.astimezone(dt.timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None
    start = queued_at.astimezone(dt.timezone.utc)
    end = start + dt.timedelta(seconds=MAX_RUN_SECONDS)
    if not start <= committed_at <= end:
        return None
    if committed_at.astimezone(JST).strftime("%Y-%m-%d@%H") != slot_key:
        return None

    commit = article.get("sha")
    title = article.get("title")
    expected_url = purchase_urls.get(set_id)
    urls = LINE_URL.findall(str(article.get("markdown", "")))
    if (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or not isinstance(title, str) or not title.strip()
            or article.get("date") != date or urls != [expected_url]
            or not isinstance(expected_url, str)):
        return None

    url = f"https://aniccaai.com/blog/{article['slug']}"
    if current.get("status") == "published":
        if current.get("url") != url or current.get("commit") != commit:
            return None
    elif current.get("status") not in (None, "failed"):
        return None
    elif current.get("url") not in (None, url) or current.get("commit") not in (None, commit):
        return None

    entry = {**current, "status": "published", "url": url, "title": title, "commit": commit}
    return {"key": slot_key, "expected": current, "entry": entry,
            "slug": article["slug"], "purchase_url": expected_url}


def build_proof(occurrence_id: str, queued_at: dt.datetime, *, now: dt.datetime,
                landing: dict[str, Any], ledger_slugs: set[str],
                ledger_rows: dict[str, Any] | None = None,
                purchase_urls: dict[str, str] | None = None) -> dict[str, Any]:
    proof: dict[str, Any] = {"owner_id": OWNER_ID, "occurrence_id": occurrence_id,
                             "verified": False, "queued_at": queued_at.isoformat()}
    if not landing.get("ok"):
        proof["reason"] = landing.get("reason")
        return proof
    articles = landing.get("articles")
    if not isinstance(articles, list) or any(not isinstance(a, dict) or not isinstance(a.get("slug"), str)
                                               for a in articles):
        proof["reason"] = "invalid_landing_article_rows"
        return proof
    window = sorted({a["slug"] for a in articles})
    unledgered = [slug for slug in window if slug not in ledger_slugs]
    patches = [patch for article in articles
               if (patch := positive_ledger_patch(article, queued_at, ledger_rows or {}, purchase_urls or {}))]
    if len(patches) > 1:
        proof["reason"] = "multiple_positive_slot_articles:" + ",".join(sorted(p["slug"] for p in patches))
        return proof
    if patches:
        patch = patches[0]
        unrelated = [slug for slug in unledgered if slug != patch["slug"]]
        if unrelated:
            proof["reason"] = "unledgered_article:" + ",".join(unrelated)
            return proof
        proof.update(verified=True, effected=True, ledger_patch=patch,
                     provider_receipt_id=f"github:{next(a['sha'] for a in articles if a['slug'] == patch['slug'])}|line-sticker-article:{patch['slug']}",
                     proof_kind="official_github_article_exact_slot_purchase_url",
                     official_readback_ref=f"github:{landing['head']}:{patch['slug']}",
                     checked_at=now.isoformat(timespec="seconds"))
        return proof
    target_slot = queued_at.astimezone(JST).strftime("%Y-%m-%d@%H")
    ambiguous = []
    for slug in window:
        match = ARTICLE_SLUG.fullmatch(slug)
        if match and f"{match.group(2)}@{match.group(3)}" == target_slot:
            ambiguous.append(slug)
    if ambiguous:
        proof["reason"] = "target_slot_article_unverified:" + ",".join(ambiguous)
        return proof
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


def write_ledger_patch(path: Path, patch: dict[str, Any]) -> None:
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    key, expected, entry = patch["key"], patch["expected"], patch["entry"]
    current = rows.get(key)
    if current == entry:
        return
    if current != expected:
        raise ValueError("article ledger slot changed during reconciliation")
    rows[key] = entry
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), mode)
            json.dump(rows, stream, ensure_ascii=False, indent=1)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def reconcile(occurrence_id: str, *, resolve: bool = False) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    state, queued_at = fenced_row(OWNER_ID, occurrence_id)
    ledger_path = STATE_ROOT / "article-ledger.json"
    rows = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    proof = build_proof(occurrence_id, queued_at, now=now,
                        landing=read_landing_articles(queued_at, queued_at + dt.timedelta(seconds=MAX_RUN_SECONDS)),
                        ledger_slugs=ledger_slugs(rows), ledger_rows=rows,
                        purchase_urls=load_purchase_urls())
    result = {**proof, "admission_state": state}
    if not proof.get("verified") or not resolve:
        return result
    if proof.get("effected") is True and proof.get("ledger_patch"):
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
