#!/usr/bin/env python3
"""Read the PromptBase seller dashboard and refresh ledger status for every
tracked listing.

Parsing is a pure function (`parse_dashboard_cards` / `status_for_title`) so
it has a test that runs with no browser. The only browser-touching part is
fetching account?view=prompts' rendered text, exactly like publish.py's own
dashboard check.

Usage (endpoint from the lease wrapper only):
    ENDPOINT=$(browser-guard.sh acquire promptbase:dais) || exit 1
    python3 readback.py --endpoint "$ENDPOINT"
    browser-guard.sh release promptbase:dais
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger as ledger_mod  # noqa: E402

PROMPTS_URL = "https://promptbase.com/account?view=prompts"
SALES_URL = "https://promptbase.com/account?view=sales"
SUMMARY_PATH = Path.home() / ".local/state/life-manager/state/promptbase-sales.json"

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


def account_view_is_official(url: str, view: str) -> bool:
    parsed = urlsplit(str(url))
    return (
        parsed.scheme == "https"
        and parsed.hostname == "promptbase.com"
        and parsed.path.rstrip("/") == "/account"
        and parse_qs(parsed.query).get("view") == [view]
    )


def prompts_dashboard_is_official(url: str, text: str) -> bool:
    if not account_view_is_official(url, "prompts") or _page_has_login_or_challenge(text):
        return False
    lines = {line.strip().casefold() for line in text.splitlines() if line.strip()}
    if "dashboard" not in lines or "prompts" not in lines:
        return False
    return bool(parse_dashboard_cards(text)) or "no prompts yet" in lines


def sales_dashboard_is_official(url: str, text: str) -> bool:
    if not account_view_is_official(url, "sales") or _page_has_login_or_challenge(text):
        return False
    lines = {line.strip().casefold() for line in text.splitlines() if line.strip()}
    if "dashboard" not in lines or "sales" not in lines:
        return False
    try:
        parse_sales(text)
    except ValueError:
        return False
    return True


def _money(cell: str) -> float | None:
    cell = cell.strip().replace(",", "")
    if not cell.startswith("$"):
        return None
    try:
        return float(cell[1:])
    except ValueError:
        return None


def parse_sales(text: str) -> dict:
    """Sales tab rows render as tab-separated lines: Amount, Net, Status, Item, ...
    ponytail: column order read from the live header (2026-09-29, zero sales);
    re-check against the first real sale row."""
    lines = {line.strip().casefold() for line in text.splitlines() if line.strip()}
    by_item: dict[str, dict] = {}
    count, net_total = 0, 0.0
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("\t")]
        if len(cells) < 4:
            continue
        amount, net = _money(cells[0]), _money(cells[1])
        if amount is None or net is None:
            continue
        item = by_item.setdefault(cells[3], {"sales": 0, "net_usd": 0.0})
        item["sales"] += 1
        item["net_usd"] = round(item["net_usd"] + net, 2)
        count += 1
        net_total += net
    if count == 0:
        if ("no sales yet" in lines and "dashboard" in lines and "sales" in lines
                and not _page_has_login_or_challenge(text)):
            return {"sales_count": 0, "net_usd": 0.0, "by_item": {}}
        raise ValueError("sales_readback_unrecognized")
    return {"sales_count": count, "net_usd": round(net_total, 2), "by_item": by_item}


def title_key(title: str) -> str:
    """Compare titles as PromptBase renders them: the dashboard drops the em dash
    and title-cases words ("Reels Hook Lab Win The Cover Frame" for our
    "Reels Hook Lab — Win the Cover Frame"), so exact equality never matched."""
    return "".join(ch for ch in title.lower() if ch.isalnum())


_STATUS_RANK = ["Approved", "Pending", "Scheduled", "Disputed", "Declined", "Draft", "Archived"]

_UNVERIFIED_PAGE_MARKERS = (
    "security verification",
    "verify you are human",
    "checking your browser",
    "confirm you're human",
    "complete the recaptcha",
    "just a moment...",
)


def _page_has_login_or_challenge(text: str) -> bool:
    lowered = text.casefold()
    lines = {line.strip().casefold() for line in text.splitlines() if line.strip()}
    return "login" in lines or any(marker in lowered for marker in _UNVERIFIED_PAGE_MARKERS)


def status_for_title(text: str, title: str) -> str | None:
    # One title can have several cards (old drafts plus the submitted one); report the furthest.
    found = [status for status, card_title in parse_dashboard_cards(text)
             if title_key(card_title) == title_key(title)]
    if not found:
        return None
    best = min(found, key=lambda st: _STATUS_RANK.index(st) if st in _STATUS_RANK else len(_STATUS_RANK))
    return _STATUS_MAP.get(best, best.lower())


def run(endpoint: str) -> dict:
    from playwright.sync_api import sync_playwright

    rows = ledger_mod.latest_by_slug()

    updates = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        try:
            prompts_response = page.goto(PROMPTS_URL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            text = page.inner_text("body")
            if (prompts_response is None or prompts_response.status != 200
                    or not prompts_dashboard_is_official(page.url, text)):
                raise RuntimeError("promptbase_prompts_readback_unverified")
            sales_response = page.goto(SALES_URL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            sales_text = page.inner_text("body")
            if (sales_response is None or sales_response.status != 200
                    or not sales_dashboard_is_official(page.url, sales_text)):
                raise RuntimeError("promptbase_sales_readback_unverified")
            sales = parse_sales(sales_text)
        finally:
            page.close()

    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for slug, row in rows.items():
        title = row.get("title")
        if not title:
            continue
        new_status = status_for_title(text, title)
        item_sales = sales["by_item"].get(title, {"net_usd": 0.0})["net_usd"]
        if new_status is None or (new_status == row.get("status") and item_sales == row.get("sales_usd")):
            continue
        ledger_mod.update_status(slug, status=new_status, checked_at=checked_at, sales=item_sales)
        updates.append({"slug": slug, "old_status": row.get("status"), "new_status": new_status})

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps({"observed_at": checked_at, "source": SALES_URL, **sales}, indent=2) + "\n")
    return {"ok": True, "checked": len(rows), "updates": updates, "sales": sales}


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args()
    result = run(args.endpoint)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
