#!/usr/bin/env python3
"""Real X views for the last published Postiz posts (read-only).

The distribute ledger records Postiz post ids, not X status ids, so fxtwitter cannot read them directly.
Postiz lists each published post with `releaseURL`, which carries the X status id; fxtwitter then returns
the public view count. Usage: capafy_x_views.py [--days 7] [--limit 10]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

POSTIZ = "https://api.postiz.com/public/v1/posts"
STATUS = re.compile(r"/status/(\d+)")


def status_id(release_url: str) -> str | None:
    match = STATUS.search(release_url or "")
    return match.group(1) if match else None


def published_x_posts(posts: list[dict], limit: int) -> list[dict]:
    """Newest `limit` PUBLISHED posts on the X integration that expose a status id."""
    rows = [p for p in posts
            if (p.get("integration") or {}).get("providerIdentifier") == "x"
            and p.get("state") == "PUBLISHED" and status_id(p.get("releaseURL") or "")]
    rows.sort(key=lambda p: p.get("publishDate") or "")
    return rows[-limit:]


def summarize(views: list[int | None]) -> dict:
    known = [v for v in views if isinstance(v, int)]
    return {"posts": len(views), "read": len(known), "sum": sum(known),
            "mean": round(sum(known) / len(known), 1) if known else None, "max": max(known) if known else None}


def _postiz_key() -> str:
    data = json.loads((Path.home() / ".local/share/anicca/credentials.json").read_text())
    return next(r["api_key"] for r in data["credentials"] if r.get("service") == "postiz")


def _get(url: str, headers: dict | None = None) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30) as response:
        return json.load(response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=args.days)
    query = f"?startDate={start:%Y-%m-%dT%H:%M:%SZ}&endDate={end + dt.timedelta(days=1):%Y-%m-%dT%H:%M:%SZ}"
    try:
        posts = _get(POSTIZ + query, {"Authorization": _postiz_key()}).get("posts") or []
    except Exception as exc:  # noqa: BLE001 -- report, never invent a number
        print(json.dumps({"ok": False, "error": type(exc).__name__}))
        return 1
    views = []
    for post in published_x_posts(posts, args.limit):
        try:
            tweet = _get(f"https://api.fxtwitter.com/status/{status_id(post['releaseURL'])}").get("tweet") or {}
            views.append(tweet.get("views"))
        except Exception:  # noqa: BLE001
            views.append(None)
    print(json.dumps({"ok": True, **summarize(views)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
