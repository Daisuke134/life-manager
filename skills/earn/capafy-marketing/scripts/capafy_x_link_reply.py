#!/usr/bin/env python3
"""Reply to our own published Capafy X posts with their registered ct link.

Postiz strips every link from X posts (2026-10-11), so each capafy-distribute post
reached buyers with no clickable route: hooklab_x/tiktok_x read 0-2 visits a week.
A self-reply carrying the ct link is not stripped (it is posted from the leased
@selawmqt browser, not Postiz). Each reply is read back from the public tweet text
before it is recorded; a post is never replied to twice.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

LEDGER = Path("~/.local/state/life-manager/writer/capafy-distribute/capafy-distribute/ledger.json").expanduser()
STATE = Path("~/.local/state/life-manager/writer/capafy-distribute/x-link-replies.jsonl").expanduser()
GUARD = Path(__file__).resolve().parents[3] / "browser" / "browser-guard.sh"
IDENTITY = "x:anicca"
HANDLE = "selawmqt"


def reply_text(cta_url: str) -> str:
    return f"Try it on Capafy: {cta_url}"


def _slot_time(key: str) -> dt.datetime | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2})-h(\d{2})(?:m(\d{2}))?", key)
    if not m:
        return None
    return dt.datetime.fromisoformat(f"{m[1]}T{m[2]}:{m[3] or '00'}:00+09:00")


def pending(ledger: dict, done: set, now: dt.datetime, *, hours: int, limit: int) -> list[tuple[str, str]]:
    rows = []
    for key, entry in ledger.items():
        at = _slot_time(key)
        x = (entry.get("destinations") or {}).get("x") or {}
        url, cta = x.get("url"), entry.get("x_cta_url")
        if (at is None or now - at > dt.timedelta(hours=hours) or x.get("status") != "PUBLISHED"
                or not url or not cta or url in done):
            continue
        rows.append((at, url, cta))
    rows.sort(reverse=True)
    return [(url, cta) for _, url, cta in rows[:limit]]


HOOKLAB_X = "https://capafy.ai/agent/8123079349?ct=hooklab_x"
X_INTEGRATION = "cmt4l2jld031tqp0y8qtyo983"


def postiz_pending(posts: list, ledger_urls: set, done: set, now: dt.datetime, *, hours: int) -> list[tuple[str, str]]:
    """Published @selawmqt Postiz posts outside the distribute ledger (daily Hook Lab
    reels, carousels) get the Hook Lab link; ledger posts keep their own x_cta_url."""
    rows = []
    for post in posts:
        url = post.get("releaseURL")
        try:
            at = dt.datetime.fromisoformat(str(post.get("publishDate")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if (post.get("state") != "PUBLISHED" or not url or url in ledger_urls or url in done
                or "hook" not in str(post.get("content") or "").lower()  # other lanes share this account
                or now - at > dt.timedelta(hours=hours)):
            continue
        rows.append((at, url))
    rows.sort(reverse=True)
    return [(url, HOOKLAB_X) for _, url in rows]


def _postiz_x_posts(now: dt.datetime, hours: int) -> list:
    rows = json.load(open(os.path.expanduser("~/.local/share/anicca/credentials.json")))["credentials"]
    key = next(r["api_key"] for r in rows if r.get("service") == "postiz")
    start = (now - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    req = urllib.request.Request(f"https://api.postiz.com/public/v1/posts?startDate={start}&endDate={end}",
                                 headers={"Authorization": key})
    data = json.loads(urllib.request.urlopen(req, timeout=60).read())
    posts = data.get("posts") if isinstance(data, dict) else data
    return [p for p in posts if ((p.get("integration") or {}).get("id") or p.get("integrationId")) == X_INTEGRATION]


def _status_id(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _public_text(status_id: str) -> dict:
    with urllib.request.urlopen(f"https://api.fxtwitter.com/{HANDLE}/status/{status_id}", timeout=30) as r:
        return json.load(r).get("tweet") or {}


def _post_reply(cdp: str, url: str, text: str) -> str | None:
    """Reply in the leased browser; return the new reply status id, read back publicly."""
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    source = _status_id(url)
    with sync_playwright() as p:
        page = p.chromium.connect_over_cdp(cdp).contexts[0].new_page()
        try:
            page.goto(f"https://x.com/{HANDLE}/status/{source}", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            before = {a.get_attribute("href") for a in page.locator('article a[href*="/status/"]').all()}
            cta = text.split(": ", 1)[1]
            for href in sorted(h for h in before if h and re.fullmatch(rf"/{HANDLE}/status/\d+", h)):
                tweet = _public_text(_status_id(href))  # readback first: never post a second reply
                if str(tweet.get("replying_to_status")) == source and cta in (tweet.get("text") or ""):
                    return _status_id(href)
            box = page.locator('[data-testid="tweetTextarea_0"]').first
            box.click(timeout=20000)
            box.type(text, delay=20)
            page.wait_for_timeout(1500)
            page.locator('[data-testid="tweetButtonInline"]').first.click(timeout=20000)
            page.wait_for_timeout(6000)
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            after = {a.get_attribute("href") for a in page.locator('article a[href*="/status/"]').all()}
        finally:
            page.close()
    for href in sorted(h for h in after - before if h and re.fullmatch(rf"/{HANDLE}/status/\d+", h)):
        tweet = _public_text(_status_id(href))
        if str(tweet.get("replying_to_status")) == source and text.split(": ", 1)[1] in (tweet.get("text") or ""):
            return _status_id(href)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    done = set()
    if STATE.exists():
        done = {json.loads(line)["source_url"] for line in STATE.read_text().splitlines() if line.strip()}
    now = dt.datetime.now(dt.timezone.utc)
    ledger = json.loads(LEDGER.read_text())
    todo = pending(ledger, done, now, hours=args.hours, limit=args.limit)
    if len(todo) < args.limit:
        try:
            ledger_urls = {((e.get("destinations") or {}).get("x") or {}).get("url") for e in ledger.values()}
            todo += postiz_pending(_postiz_x_posts(now, args.hours), ledger_urls, done | {u for u, _ in todo},
                                   now, hours=args.hours)[: args.limit - len(todo)]
        except Exception as exc:  # Postiz read failure must not stop ledger replies
            print(json.dumps({"postiz_read": "failed", "error": type(exc).__name__}))
    if args.dry_run or not todo:
        print(json.dumps({"pending": todo}))
        return 0
    lease = subprocess.run(["bash", str(GUARD), "acquire", IDENTITY], capture_output=True, text=True)
    if lease.returncode != 0:
        print(json.dumps({"status": "browser_busy", "rc": lease.returncode}))
        return 0
    cdp = lease.stdout.strip().splitlines()[-1]
    try:
        for url, cta in todo:
            reply_id = _post_reply(cdp, url, reply_text(cta))
            rec = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "source_url": url, "cta_url": cta,
                   "reply_url": f"https://x.com/{HANDLE}/status/{reply_id}" if reply_id else None}
            if reply_id:
                with STATE.open("a") as fh:
                    fh.write(json.dumps(rec) + "\n")
            print(json.dumps(rec))
            if not reply_id:  # unverified: stop, never re-post blind on the next item
                return 1
    finally:
        subprocess.run(["bash", str(GUARD), "release", IDENTITY], capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
