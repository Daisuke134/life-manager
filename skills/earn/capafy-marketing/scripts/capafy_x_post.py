#!/usr/bin/env python3
"""capafy_x_post.py — one plain-text X (Twitter) link post for the Capafy
distribute loop, over Postiz.

Reuses HttpPostizClient's already-proven HTTP transport
(skills/earn/marketing-engine/publish/postiz_adapter.py) instead of a new API
client. Does NOT reuse PostizAdapter itself -- that class is the video/image
distribution domain module and hard-requires a stored media receipt
(`_draft_payload` raises without one); a text-only CTA post has no image, so
building the draft payload here directly is the smaller, correct diff. X
Articles (skills/writer-agent/scripts/x-publish, browser/CDP) is the OTHER
existing X poster named in the spec, but the spec itself already records that
path as unusable for this account (2026-09-29: "X 編集画面はアカウントで
使えないため skip", #6140) and routes X posts through Postiz instead -- so
Postiz is the one live X channel to reuse, not a new choice made here.

  capafy_x_post.py --caption "..." --integration-id <id> [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caption", required=True, help="post text, must already contain the ct= link")
    parser.add_argument("--integration-id", required=True)
    parser.add_argument("--api-key", default=None, help="defaults to $POSTIZ_API_KEY")
    parser.add_argument("--scheduled-at", default=None, help="ISO-8601 UTC; defaults to now")
    parser.add_argument("--dry-run", action="store_true", help="build and print the payload, no HTTP call")
    args = parser.parse_args(argv)

    scheduled_at = args.scheduled_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    payload = build_payload(integration_id=args.integration_id, caption=args.caption, scheduled_at=scheduled_at)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "payload": payload}, ensure_ascii=False))
        return 0

    import os

    api_key = args.api_key or os.environ.get("POSTIZ_API_KEY", "")
    HttpPostizClient = _load_http_postiz_client()
    client = HttpPostizClient(api_key)
    response = client.create_draft(payload)
    print(json.dumps({"dry_run": False, "response": response}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
