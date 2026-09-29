#!/usr/bin/env python3
"""capafy_x_post.py — one REAL (not draft) X (Twitter) link post for the
Capafy distribute loop, over Postiz.

Reuses HttpPostizClient's already-proven HTTP transport and the SAME
create-then-promote flow this repo already uses to take a Postiz post out of
draft (skills/earn/marketing-engine/publish/postiz_adapter.py:
`create_draft` + `PostizAdapter.promote` -> `PUT /posts/{id}/status
{"status":"schedule"}`, proven by that module's own tests). Does NOT reuse
`PostizAdapter` itself -- its `_draft_payload` hard-requires a stored media
receipt (raises without one); a text-only CTA post has no image, so building
the payload here directly is the smaller diff. X Articles
(skills/writer-agent/scripts/x-publish, browser/CDP) is the OTHER existing X
poster named in the spec, but the spec itself records that path as unusable
for this account (2026-09-29: "X 編集画面はアカウントで使えないため
skip", #6140) and already routes X posts through Postiz instead.

Flow: create_draft(type=draft, scheduled "now") -> promote(post_id) -> poll
list_posts for state=="PUBLISHED" (the same field convention already used by
skills/earn/marketing-engine/publish/reconcile.py and
test_postiz_adapter.py) before printing success. Never claims success on a
QUEUE/DRAFT/ERROR state.

  capafy_x_post.py --caption "..." --integration-id <id> [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

MARKETING_ENGINE_PUBLISH_DIR = (
    Path(__file__).resolve().parents[3] / "earn" / "marketing-engine" / "publish"
)


def _load_http_postiz_client():
    sys.path.insert(0, str(MARKETING_ENGINE_PUBLISH_DIR))
    from postiz_adapter import HttpPostizClient  # noqa: PLC0415

    return HttpPostizClient


def build_payload(*, integration_id: str, caption: str, scheduled_at: str) -> dict:
    return {
        "type": "draft",
        "date": scheduled_at,
        "shortLink": False,
        "tags": [],
        "posts": [
            {
                "integration": {"id": integration_id},
                "value": [{"content": caption, "image": []}],
                "settings": {},
            }
        ],
    }


def extract_post_id(create_response) -> str:
    first = create_response[0] if isinstance(create_response, list) and create_response else create_response
    if not isinstance(first, dict):
        raise SystemExit(f"Postiz create returned no usable post row: {create_response}")
    post_id = str(first.get("postId") or first.get("id") or "")
    if not post_id:
        raise SystemExit(f"Postiz create response missing postId: {create_response}")
    return post_id


def find_published(posts: list[dict], post_id: str) -> dict | None:
    for post in posts:
        if str(post.get("id") or post.get("postId") or "") == post_id and post.get("state") == "PUBLISHED":
            return post
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caption", required=True, help="post text, must already contain the ct= link")
    parser.add_argument("--integration-id", required=True)
    parser.add_argument("--api-key", default=None, help="defaults to $POSTIZ_API_KEY")
    parser.add_argument("--scheduled-at", default=None, help="ISO-8601 UTC; defaults to now")
    parser.add_argument("--readback-attempts", type=int, default=5)
    parser.add_argument("--readback-interval-seconds", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true", help="build and print the payload, no HTTP call")
    args = parser.parse_args(argv)

    scheduled_at = args.scheduled_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    payload = build_payload(integration_id=args.integration_id, caption=args.caption, scheduled_at=scheduled_at)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "payload": payload}, ensure_ascii=False))
        return 0

    import os

    api_key = args.api_key or os.environ.get("POSTIZ_API_KEY", "")
    if not api_key:
        raise SystemExit("POSTIZ_API_KEY is required")
    HttpPostizClient = _load_http_postiz_client()
    client = HttpPostizClient(api_key)

    created = client.create_draft(payload)
    post_id = extract_post_id(created)
    promoted = client.promote(post_id)
    if str(promoted.get("id") or "") != post_id or promoted.get("state") not in {"QUEUE", "PUBLISHED"}:
        raise SystemExit(f"Postiz promote did not confirm the post left draft: {promoted}")

    now = dt.datetime.now(dt.timezone.utc)
    published = None
    for _ in range(max(1, args.readback_attempts)):
        posts = client.list_posts(now - dt.timedelta(hours=1), now + dt.timedelta(hours=1))
        published = find_published(posts, post_id)
        if published:
            break
        time.sleep(args.readback_interval_seconds)
    if not published:
        raise SystemExit(f"Postiz readback never reached state=PUBLISHED for post_id={post_id}")

    print(json.dumps({"dry_run": False, "action": "published", "post_id": post_id, "post": published}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
