#!/usr/bin/env python3
"""capafy_devto_post.py — publish ONE full free (published:true) Dev.to post
for the Capafy distribute loop, straight to the Dev.to API.

Reuses the Writer's own Dev.to frontmatter/tag parsing and HTTP call helpers
(skills/writer-agent/scripts/devto-publish/devto.py: `_frontmatter`, `_tags`,
`_request`, `_identity`) instead of re-implementing them. Deliberately does
NOT go through that same module's `stage()`/`publish_existing()` or
`publication-guard.py`/`publication_resume.py`: those enforce
article-daily.sh's own dormant-pair policy (`devto/en` is dormant there,
skills/writer-agent/scripts/publication_contract.py) via
`PublicationStore._assert_pair_mutation_allowed`, which raises for any
non-legacy state -- there is no honest way to publish through that path
without editing the shared contract or faking a "legacy-exact8" state, and
both are the shared-contract change this loop must not make. Dev.to's own
API has no concept of "dormant"; that policy is internal Life Manager
bookkeeping for the daily Writer loop's own state machine, not a property of
the Dev.to account, so this loop (with its own ledger/idempotency) calls the
API directly, published:true, using the SAME DEVTO_API_KEY/account as the
Writer.

Duplicate guard (defense in depth on top of the loop's own JST-date ledger):
before posting, list the account's own recent articles and skip creating a
new one if the title already exists -- covers a lost/corrupted ledger.

  capafy_devto_post.py --draft-file article.md [--dry-run]
  capafy_devto_post.py --draft-file article.md --existing-articles-json rows.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEVTO_PUBLISH_DIR = Path(__file__).resolve().parents[3] / "writer-agent" / "scripts" / "devto-publish"


def _load_devto_module():
    sys.path.insert(0, str(DEVTO_PUBLISH_DIR.parent))  # for the pii_gate _shared import
    sys.path.insert(0, str(DEVTO_PUBLISH_DIR))
    import devto  # noqa: PLC0415

    return devto


def build_article_payload(markdown_text: str, devto_module) -> dict:
    """Pure: parse frontmatter title/tags, return the Dev.to create payload.

    No network, no filesystem beyond the text already read by the caller --
    the same shape devto.py's own prepare() builds, minus the immutable-media
    machinery this loop does not use.
    """
    values, body = devto_module._frontmatter(markdown_text)  # noqa: SLF001
    title = values.get("title", "").strip()
    tags = devto_module._tags(values.get("tags", ""))  # noqa: SLF001
    if not title or not tags:
        raise ValueError("Dev.to draft requires frontmatter title and tags")
    return {
        "article": {
            "title": title,
            "tags": tags,
            "published": True,
            "body_markdown": body.strip() + "\n",
        }
    }


def find_existing_by_title(rows: list[dict], title: str) -> dict | None:
    """Pure: case/whitespace-insensitive title match against the account's own articles."""
    normalized = " ".join(title.split()).casefold()
    for row in rows:
        row_title = " ".join(str(row.get("title", "")).split()).casefold()
        if row_title == normalized:
            return row
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft-file", required=True)
    parser.add_argument("--api-key", default=None, help="defaults to $DEVTO_API_KEY")
    parser.add_argument("--account-handle", default=None, help="defaults to $DEVTO_ACCOUNT_HANDLE")
    parser.add_argument("--existing-articles-json", default=None,
                         help="test fixture: pre-fetched /articles/me/all rows, skips the network list call")
    parser.add_argument("--dry-run", action="store_true", help="build payload + run duplicate-check offline, no HTTP call")
    args = parser.parse_args(argv)

    devto_module = _load_devto_module()
    markdown_text = Path(args.draft_file).read_text(encoding="utf-8")
    payload = build_article_payload(markdown_text, devto_module)
    title = payload["article"]["title"]

    existing_rows: list[dict] = []
    if args.existing_articles_json:
        existing_rows = json.loads(Path(args.existing_articles_json).read_text(encoding="utf-8"))
        existing = find_existing_by_title(existing_rows, title)
        if existing:
            print(json.dumps({"dry_run": args.dry_run, "action": "duplicate-skip", "existing": existing}, ensure_ascii=False))
            return 0

    if args.dry_run:
        print(json.dumps({"dry_run": True, "action": "would-create", "payload": payload}, ensure_ascii=False))
        return 0

    api_key = args.api_key or os.environ.get("DEVTO_API_KEY", "")
    if not api_key:
        raise SystemExit("DEVTO_API_KEY is required")
    account_handle = (args.account_handle or os.environ.get("DEVTO_ACCOUNT_HANDLE", "")).strip().lstrip("@").lower()
    if not account_handle:
        raise SystemExit("DEVTO_ACCOUNT_HANDLE is required")

    me = devto_module._request("https://dev.to/api/users/me", api_key)  # noqa: SLF001
    if not isinstance(me, dict) or str(me.get("username", "")).lower() != account_handle:
        raise SystemExit("Dev.to API identity does not match configured account")

    if not args.existing_articles_json:
        rows = devto_module._request("https://dev.to/api/articles/me/all?per_page=1000", api_key)  # noqa: SLF001
        existing = find_existing_by_title(rows if isinstance(rows, list) else [], title)
        if existing:
            print(json.dumps({"dry_run": False, "action": "duplicate-skip", "existing": existing}, ensure_ascii=False))
            return 0

    created = devto_module._request(  # noqa: SLF001
        "https://dev.to/api/articles", api_key, method="POST", payload=payload,
    )
    article_id = str(created.get("id", "") if isinstance(created, dict) else "")
    if not article_id.isdigit():
        raise SystemExit(f"Dev.to create returned no stable article ID: {created}")

    # Read back before claiming success (HTTP 200 + title match).
    readback = devto_module._request(f"https://dev.to/api/articles/{article_id}", api_key)  # noqa: SLF001
    if not isinstance(readback, dict) or readback.get("title") != title or not readback.get("url"):
        raise SystemExit(f"Dev.to readback did not confirm the published article: {readback}")

    print(json.dumps({
        "dry_run": False, "action": "created", "article_id": article_id,
        "url": readback["url"], "title": readback["title"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
