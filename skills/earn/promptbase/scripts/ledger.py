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


def already_listed(slug: str, ledger_path: Path = DEFAULT_LEDGER_PATH) -> Optional[dict]:
    """Return the existing row for `slug` unless its last known status is a
    terminal failure the caller is explicitly allowed to retry."""
    row = latest_by_slug(ledger_path).get(slug)
    if row is None:
        return None
    if row.get("status") == "rejected":
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
