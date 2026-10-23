#!/usr/bin/env python3
"""Read Coconala's revenue page and append settled sales to earnings.jsonl.

Why this exists: on 2026-07-27 two orders had completed (17,000 + 65,000 JPY gross,
63,960 JPY net) while earnings.jsonl was still empty and the funnel still read
paid=0 / 0 JPY. Nothing in the loop turned "talkroom closed" into a revenue row, so
the loop did not know it had earned. An allocator fed by that ledger would be blind.

Ground truth is the seller revenue page, NOT our own state files:
  https://coconala.com/mypage/revenue      (found via the dashboard menu href
  "売上管理・振込申請" = /mypage/revenue?ref=menu; /mypage/sales, /mypage/sales_management
  and /mypage/transfer all 404)

Coconala credits a sale when the talkroom closes, so each 売上履歴 row is a settled
sale. The row carries: close timestamp, talkroom id, service title, buyer, and the
NET amount (after the 22% fee), plus 申請済み when a payout has been requested.

Idempotency: the talkroom id + close timestamp form the key. Following the pattern
from anthropics/defending-code-reference-harness (cli.py::_judged_runs), the
append-only ledger IS the key store -- we read the existing rows into a set and skip
anything already present. No second database, no lock, safe to run every pass.

Usage:
  revenue_collector.py --cdp http://localhost:9223            # scrape live, append
  revenue_collector.py --from-text FILE                       # parse saved page text
  revenue_collector.py --cdp ... --dry-run                    # show what would append

The caller is responsible for holding the gig browser lease before --cdp is used
(scripts/gig_single_instance.sh acquire); this script never launches a browser.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("GIG_STATE_DIR", str(Path.home() / "gig")))
EARNINGS = STATE_DIR / "earnings.jsonl"
REVENUE_URL = "https://coconala.com/mypage/revenue"

# gig_funnel.py counts a row as paid when status is in this set AND evidence is
# present AND jpy > 0, so emit a status from it.
SETTLED_STATUS = "検収完了"

# 売上履歴 rows look like:
#   2026/07/26 14:24
#   トークルームNo：90000010
#   マインクラフト統合版の銃アドオンのバグ修正
#   buyer_handle_c
#   13,260 円
# with an optional 申請済み line before the amount once a payout is requested, which
# becomes 振込済み once it is paid out (the row is still the same settled sale).
ROW_RE = re.compile(
    r"(?P<ts>\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})\s*\n"
    r"トークルームNo：(?P<room>\d+)\s*\n"
    r"(?P<title>.+?)\n"
    r"(?P<buyer>.+?)\n"
    r"(?:(?P<requested>申請済み|振込済み)\s*\n)?"
    r"(?P<amount>[\d,]+)\s*円",
    re.MULTILINE,
)

TOTALS_RE = {
    "balance_jpy": re.compile(r"売上金残高合計\s*\n+\s*([\d,]+)\s*円"),
    "cumulative_jpy": re.compile(r"累積売上\s*\n+\s*([\d,]+)\s*円"),
    "payout_requested_jpy": re.compile(r"振込申請金額：([\d,]+)円"),
    "payout_date": re.compile(r"振込予定日：([^\n]+)"),
}


def _yen(text: str) -> float:
    return float(text.replace(",", ""))


def parse_revenue_text(text: str) -> dict:
    """Pure function: page text -> {rows: [...], totals: {...}}. No IO."""
    rows = []
    for m in ROW_RE.finditer(text):
        rows.append(
            {
                "closed_at": m.group("ts").strip(),
                "talkroom_id": m.group("room"),
                "title": m.group("title").strip(),
                "buyer": m.group("buyer").strip(),
                "jpy": _yen(m.group("amount")),
                "payout_requested": bool(m.group("requested")),
            }
        )
    totals = {}
    for key, rx in TOTALS_RE.items():
        found = rx.search(text)
        if found:
            value = found.group(1).strip()
            totals[key] = value if key == "payout_date" else _yen(value)
    return {"rows": rows, "totals": totals}


def existing_keys() -> set[str]:
    """Read the append-only ledger; the ledger itself is the idempotence key store."""
    keys: set[str] = set()
    if not EARNINGS.exists():
        return keys
    with EARNINGS.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn line must not stop the pass
            key = row.get("idem_key")
            if key:
                keys.add(key)
    return keys


def reconcile_existing(parsed: dict, source_url: str) -> int:
    """Refresh mutable payout state for rows already in the append-only ledger.

    A sale is immutable, but Coconala can change its payout status later.  Treating
    the ledger as an idempotency store must not turn that mutable UI state into a
    permanent historical false value.
    """
    if not EARNINGS.exists():
        return 0
    live = {
        f"coconala:revenue:{row['talkroom_id']}:{row['closed_at']}": row
        for row in parsed.get("rows", [])
    }
    changed = 0
    observed_at = int(time.time())
    lines: list[str] = []
    with EARNINGS.open(encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            try:
                stored = json.loads(line)
            except json.JSONDecodeError:
                lines.append(raw)
                continue
            live_row = live.get(stored.get("idem_key"))
            if live_row is not None:
                current = stored.get("payout_requested")
                latest = live_row["payout_requested"]
                if current is not latest or stored.get("payout_state_source") != source_url:
                    stored["payout_requested"] = latest
                    stored["payout_state_source"] = source_url
                    changed += 1
                if stored.get("payout_state_observed_at") != observed_at:
                    stored["payout_state_observed_at"] = observed_at
                    changed += 1
                line = json.dumps(stored, ensure_ascii=False)
            lines.append(line + "\n")
    if not changed:
        return 0
    # Replace atomically so a killed pass cannot corrupt the JSONL ledger.
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=EARNINGS.parent, delete=False
    ) as handle:
        handle.writelines(lines)
        temp_name = handle.name
    os.replace(temp_name, EARNINGS)
    return changed


def to_earning(row: dict, source_url: str) -> dict:
    idem = f"coconala:revenue:{row['talkroom_id']}:{row['closed_at']}"
    return {
        "ts": row["closed_at"],
        "loop": "gig",
        "adapter": "coconala",
        "requestId": row["talkroom_id"],
        "talkroom_id": row["talkroom_id"],
        "buyer": row["buyer"],
        "title": row["title"],
        "jpy": row["jpy"],
        "net_of_fee": True,
        "status": SETTLED_STATUS,
        "payout_requested": row["payout_requested"],
        "evidence": source_url,
        "payout_state_source": source_url,
        "payout_state_observed_at": int(time.time()),
        "idem_key": idem,
    }


def append_new(parsed: dict, source_url: str, dry_run: bool = False) -> list[dict]:
    if not dry_run:
        reconcile_existing(parsed, source_url)
    seen = existing_keys()
    fresh = []
    repeats: dict[str, int] = {}
    for row in parsed["rows"]:
        base = f"coconala:revenue:{row['talkroom_id']}:{row['closed_at']}"
        # A tip and its order can close in the same minute; later rows get ":n" so none is lost.
        count = repeats[base] = repeats.get(base, -1) + 1
        idem = base if count == 0 else f"{base}:{count}"
        if idem in seen:
            continue
        candidate = to_earning(row, source_url)
        candidate["idem_key"] = idem
        fresh.append(candidate)
    if fresh and not dry_run:
        EARNINGS.parent.mkdir(parents=True, exist_ok=True)
        with EARNINGS.open("a", encoding="utf-8") as handle:
            for row in fresh:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()  # a kill mid-run still leaves complete rows on disk
    return fresh


def scrape(cdp_url: str, url: str = REVENUE_URL) -> str:
    """Read one revenue page over an EXISTING browser. Never launches one."""
    import inspect

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        kwargs = {}
        if "no_defaults" in inspect.signature(p.chromium.connect_over_cdp).parameters:
            kwargs["no_defaults"] = True
        browser = p.chromium.connect_over_cdp(cdp_url, **kwargs)
        page = browser.contexts[0].new_page()  # never touch pages we do not own
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)
            if "見つかりませんでした" in page.evaluate("document.body.innerText"):
                raise RuntimeError("revenue page not reachable (login lost?)")
            return page.evaluate("document.body.innerText")
        finally:
            page.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", help="CDP endpoint of the already-leased gig browser")
    ap.add_argument("--from-text", help="parse a saved copy of the page text instead")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.from_text:
        text = Path(args.from_text).read_text(encoding="utf-8")
    elif args.cdp:
        text = scrape(args.cdp)
    else:
        ap.error("need --cdp or --from-text")

    parsed = parse_revenue_text(text)
    fresh = append_new(parsed, REVENUE_URL, dry_run=args.dry_run)
    print(
        json.dumps(
            {
                "status": "ok",
                "parsed_rows": len(parsed["rows"]),
                "appended": len(fresh),
                "dry_run": args.dry_run,
                "totals": parsed["totals"],
                "appended_keys": [r["idem_key"] for r in fresh],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
