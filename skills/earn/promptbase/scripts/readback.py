#!/usr/bin/env python3
"""Read the PromptBase seller dashboard and refresh ledger status for every
tracked listing.

Parsing is a pure function (`parse_dashboard_cards` / `status_for_title`) so
it has a test that runs with no browser. The only browser-touching part is
fetching account?view=prompts' rendered text, exactly like publish.py's own
dashboard check.

Usage (endpoint from the lease wrapper only):
    ENDPOINT=$(browser-guard.sh acquire interactive:dais) || exit 1
    python3 readback.py --endpoint "$ENDPOINT"
    browser-guard.sh release interactive:dais
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as ledger_mod  # noqa: E402

PROMPTS_URL = "https://promptbase.com/account?view=prompts"

_STATUSES = {
    "Approved",
    "Pending",
    "Scheduled",
    "Draft",
    "Declined",
    "Archived",
    "Disputed",
}

# PromptBase's own dashboard label -> this ledger's status vocabulary.
_STATUS_MAP = {
    "Approved": "live",
    "Pending": "pending_review",
    "Scheduled": "scheduled",
    "Draft": "draft",
    "Declined": "rejected",
    "Archived": "archived",
    "Disputed": "disputed",
}


def parse_dashboard_cards(text: str) -> list[tuple[str, str]]:
    """(status, title) pairs from the Prompts dashboard's rendered body text.
    Each card renders as a short run of lines: an emoji/model line, the
    status label, then the title -- in that order, one after another."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cards: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        if lines[i] in _STATUSES and i + 1 < len(lines) and lines[i + 1] not in _STATUSES:
            cards.append((lines[i], lines[i + 1]))
            i += 2
        else:
            i += 1
    return cards


def status_for_title(text: str, title: str) -> str | None:
    for status, card_title in parse_dashboard_cards(text):
        if card_title == title:
            return _STATUS_MAP.get(status, status.lower())
    return None


def run(endpoint: str) -> dict:
    from playwright.sync_api import sync_playwright

    rows = ledger_mod.latest_by_slug()
    if not rows:
        return {"ok": True, "checked": 0, "updates": []}

    updates = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            page.goto(PROMPTS_URL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            text = page.inner_text("body")
        finally:
            page.close()

    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for slug, row in rows.items():
        title = row.get("title")
        if not title:
            continue
        new_status = status_for_title(text, title)
        if new_status is None or new_status == row.get("status"):
            continue
        ledger_mod.update_status(slug, status=new_status, checked_at=checked_at)
        updates.append({"slug": slug, "old_status": row.get("status"), "new_status": new_status})

    return {"ok": True, "checked": len(rows), "updates": updates}


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args()
    result = run(args.endpoint)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
