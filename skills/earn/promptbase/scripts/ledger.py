#!/usr/bin/env python3
"""JSONL ledger of PromptBase listings — the idempotency source of truth.

One line per slug. `already_listed` is the guard the publisher calls before
ever opening the /sell wizard: a slug that already has a row (any status
except a terminal "rejected"/"failed" the caller chooses to retry) must never
get a second listing created for it.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

DEFAULT_LEDGER_PATH = Path(
    os.path.expanduser(
        "~/.local/state/life-manager/state/promptbase-listings.jsonl"
    )
)

REQUIRED_FIELDS = ("slug", "promptbase_id", "url", "status", "submitted_at")


def read_all(ledger_path: Path = DEFAULT_LEDGER_PATH) -> list[dict]:
    if not ledger_path.exists():
        return []
    rows = []
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def latest_by_slug(ledger_path: Path = DEFAULT_LEDGER_PATH) -> dict[str, dict]:
    """Last row per slug wins (append-only log, status updates append new rows)."""
    out: dict[str, dict] = {}
    for row in read_all(ledger_path):
        slug = row.get("slug")
        if slug:
            out[slug] = row
    return out


# Terminal-but-retryable statuses: a slug parked here never got a real
# PromptBase submission, so the next day's run is allowed to pick it again.
# "draft" included per this ledger's own idempotency contract (SKILL.md): a
# leftover unsubmitted Draft card (e.g. a dry run, or a submit click that
# silently failed to navigate) is not a listing -- only a real submission is.
RETRYABLE_STATUSES = {"rejected", "captcha_challenge_deferred", "draft"}


def already_listed(slug: str, ledger_path: Path = DEFAULT_LEDGER_PATH) -> Optional[dict]:
    """Return the existing row for `slug` unless its last known status is a
    terminal failure the caller is explicitly allowed to retry."""
    row = latest_by_slug(ledger_path).get(slug)
    if row is None:
        return None
    if row.get("status") in RETRYABLE_STATUSES:
        return None
    return row


def append(row: dict, ledger_path: Path = DEFAULT_LEDGER_PATH) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in row]
    if missing:
        raise ValueError(f"ledger_row_missing_fields:{','.join(missing)}")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    os.chmod(ledger_path, 0o600)


def update_status(
    slug: str,
    *,
    status: str,
    sales: Optional[float] = None,
    checked_at: Optional[str] = None,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> dict:
    """Append a status-update row derived from the slug's last known row
    (append-only log — never rewrites history in place)."""
    existing = latest_by_slug(ledger_path).get(slug)
    if existing is None:
        raise ValueError(f"ledger_no_row_for_slug:{slug}")
    row = dict(existing)
    row["status"] = status
    if sales is not None:
        row["sales_usd"] = sales
    if checked_at is not None:
        row["checked_at"] = checked_at
    append(row, ledger_path)
    return row


def record_captcha_deferred(
    slug: str,
    *,
    title: Optional[str] = None,
    evidence_dir: Optional[str] = None,
    checked_at: Optional[str] = None,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> dict:
    """The clean-stop path daily.sh takes when publish.py's --confirm run
    raises recaptcha_requires_human_verification: never solve/bypass/outsource
    the challenge, just record the deferral and let tomorrow's run retry the
    same slug (already_listed treats this status as retryable, like
    "rejected"). Works whether or not this slug already has a prior row."""
    checked_at = checked_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    existing = latest_by_slug(ledger_path).get(slug)
    if existing is not None:
        return update_status(slug, status="captcha_challenge_deferred", checked_at=checked_at, ledger_path=ledger_path)
    row = {
        "slug": slug,
        "promptbase_id": "",
        "url": "",
        "status": "captcha_challenge_deferred",
        "submitted_at": checked_at,
    }
    if title is not None:
        row["title"] = title
    if evidence_dir is not None:
        row["evidence_dir"] = evidence_dir
    append(row, ledger_path)
    return row


def _main() -> int:
    import argparse
    import json as _json

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    deferred = sub.add_parser("record-captcha-deferred")
    deferred.add_argument("--slug", required=True)
    deferred.add_argument("--title")
    deferred.add_argument("--evidence-dir")
    deferred.add_argument("--ledger-path", type=Path, default=DEFAULT_LEDGER_PATH)
    args = parser.parse_args()
    if args.command == "record-captcha-deferred":
        row = record_captcha_deferred(
            args.slug, title=args.title, evidence_dir=args.evidence_dir, ledger_path=args.ledger_path
        )
        print(_json.dumps(row, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
