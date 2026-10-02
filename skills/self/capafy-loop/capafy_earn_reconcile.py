#!/usr/bin/env python3
"""capafy_earn_reconcile.py — mirror Capafy SERVER sales/payout into a LOCAL capafy ledger.

WHY THIS EXISTS (A4, 2026-07-18):
  Capafy revenue is REAL money but it settles to a BANK account (wire_transfer, acct ****1900),
  NOT on-chain. The colony's realized-P&L ledger (skills/earn/state/earn-ledger.jsonl, read by
  self-improve/lib/ledger_reader.py) only counts rows with an on-chain confirmation
  (EVM tx/status, Solana sig/confirmed, Hyperliquid fill_tid) — a Capafy bank sale can NEVER pass
  that gate, and FAKING a tx to make it pass would be fabrication. So Capafy revenue was invisible
  locally: the daily report said "$0" while the server had a $9.99 sale (2026-06-23) and an $8.00
  seller balance PENDING payout. (Confirmed live: GET /agent/sales/trend + /agent/developer/payout-info.)

  This tool keeps a DEDICATED ledger (state/capafy-earn-ledger.jsonl, the same pattern clip uses
  with clip-earn-ledger.jsonl) that mirrors the server truth, so the local record is honest without
  contaminating the on-chain realized-P&L reader. "Earned" judgment still defers to the SERVER
  (this ledger is a record/leading-indicator; realized bank income = payout-info.totalPayout).

Honesty invariants:
  - gross (buyer paid) and seller balance (our take, pending) and realized payout are recorded
    SEPARATELY and never conflated.
  - NEVER writes tx/sig/fill_tid/external — a capafy row must never be mistaken for on-chain realized.
  - Idempotent (dedup by (source,date)), atomic (tmp+replace), backup-first, never drops existing rows.

Usage:
  capafy_earn_reconcile.py [--lookback-days N] [--backfill]
  capafy_earn_reconcile.py --sales-json <f> --payout-json <f>   # offline/test injection
Prints ONE line of JSON to stdout (clean, parseable). Exit 0 on success, 1 on hard failure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_HOME = Path(os.environ.get(
    "LIFE_MANAGER_STATE_HOME",
    Path.home() / ".local/state/life-manager",
)).expanduser()
LEDGER = str(STATE_HOME / "state/capafy-earn-ledger.jsonl")
CONFIG = os.environ.get(
    "CAPAFY_PUBLISHER_CONFIG",
    str(STATE_HOME / "credentials/capafy-publisher.json"),
)
API = "https://api.capafy.ai"


def _token() -> str:
    token = os.environ.get("CAPAFY_ACCESS_TOKEN") or os.environ.get("CAPAFY_TOKEN")
    if token:
        return token
    try:
        return json.load(open(CONFIG)).get("access_token", "") or ""
    except Exception:
        return ""


def _get(path: str, token: str) -> dict:
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def _date_windows(lookback_days: int):
    """Yield (start,end) date strings in <=7-day chunks (sales/trend returns per-day detail only
    for ranges <= 7 days; > 7 days collapses to a single date=null summary)."""
    today = dt.date.today()
    start = today - dt.timedelta(days=lookback_days)
    cur = start
    while cur <= today:
        end = min(cur + dt.timedelta(days=6), today)
        yield cur.isoformat(), end.isoformat()
        cur = end + dt.timedelta(days=1)


def fetch_sales(token: str, lookback_days: int) -> list:
    """Return per-day sales entries (orders>0) across the lookback, deduped by date."""
    seen = {}
    for s, e in _date_windows(lookback_days):
        try:
            resp = _get(f"/agent/sales/trend?startDate={s}&endDate={e}", token)
        except Exception:
            continue
        if resp.get("code", 0) != 0:
            continue
        days = (resp.get("data") or {}).get("data")
        if not isinstance(days, list):
            continue
        for d in days:
            date = d.get("date")
            if not date:
                continue
            if float(d.get("orders", 0) or 0) <= 0 and float(d.get("revenue", 0) or 0) <= 0:
                continue
            seen[date] = d
    return [seen[k] for k in sorted(seen)]


def load_rows(path: str) -> list:
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    rows.append({"_raw": line})  # preserve unparseable verbatim
    except FileNotFoundError:
        pass
    return rows


def atomic_write(path: str, rows: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        bak = path + ".bak-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            with open(path) as a, open(bak, "w") as b:
                b.write(a.read())
        except Exception:
            pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            if "_raw" in r:
                f.write(r["_raw"] + "\n")
            else:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _date_to_ts(date: str) -> int:
    return int(dt.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback-days", type=int, default=35)
    ap.add_argument("--backfill", action="store_true", help="extend lookback to 90 days")
    ap.add_argument("--sales-json", help="offline: file with a sales/trend response OR a list of day dicts")
    ap.add_argument("--payout-json", help="offline: file with a payout-info response")
    ap.add_argument("--ledger", default=LEDGER)
    args = ap.parse_args()

    lookback = 90 if args.backfill else args.lookback_days

    # --- gather server truth (live or injected) ---
    token = ""
    if args.sales_json:
        raw = json.load(open(args.sales_json))
        days = raw.get("data", {}).get("data") if isinstance(raw, dict) else raw
        sales = [d for d in (days or []) if d.get("date") and (float(d.get("orders", 0) or 0) > 0 or float(d.get("revenue", 0) or 0) > 0)]
        sales.sort(key=lambda d: d["date"])
    else:
        token = _token()
        if not token:
            print(json.dumps({"ok": False, "reason": "no_access_token"}))
            return 1
        sales = fetch_sales(token, lookback)

    # Fail closed: a payout-info read failure (exception, code!=0, non-object data) must NOT be
    # written as a $0 snapshot — 2026-10-01 produced an all-zero row while the official seller
    # balance was $59.00. On failure no capafy-payout row is written and the summary says so.
    payout: dict | None
    try:
        if args.payout_json:
            praw = json.load(open(args.payout_json))
        else:
            praw = _get("/agent/developer/payout-info", token)
    except Exception:
        praw = None
    if isinstance(praw, dict) and praw.get("code", 0) == 0:
        payout = praw.get("data", praw)
        if not isinstance(payout, dict):
            payout = None
    else:
        payout = None
    payout_fetch_status = "fresh" if payout is not None else "failed"

    # --- merge into ledger (idempotent by (source,date)) ---
    existing = load_rows(args.ledger)
    have = set()
    for r in existing:
        if isinstance(r, dict) and "source" in r and "date" in r:
            have.add((r["source"], r["date"]))

    today = dt.date.today().isoformat()
    added = []
    new_rows = list(existing)

    for d in sales:
        key = ("capafy-sales", d["date"])
        if key in have:
            continue
        row = {
            "ts": _date_to_ts(d["date"]),
            "source": "capafy-sales",
            "date": d["date"],
            "orders": int(d.get("orders", 0) or 0),
            "gross_usd": round(float(d.get("revenue", 0) or 0), 2),
            "net_revenue_usd": round(float(d.get("netRevenue", d.get("revenue", 0)) or 0), 2),
            "refund_amount_usd": round(float(d.get("refundAmount", 0) or 0), 2),
            "new_buyers": int(d.get("newBuyers", 0) or 0),
            "currency": (d.get("currency") or "usd"),
            "channel": "capafy_bank_wire",
            "note": "capafy sales/trend reconcile; gross buyer payment (NOT on-chain; seller take in capafy-payout snapshot)",
            "wake": "capafy_earn_reconcile",
        }
        new_rows.append(row)
        have.add(key)
        added.append(d["date"])

    # payout snapshot: one per day (upsert today's — replace if already present today).
    # Skipped entirely when the fetch failed, so an earlier good snapshot for today survives.
    payout_row = None
    if payout is not None:
        payout_row = {
            "ts": int(dt.datetime.now(dt.timezone.utc).timestamp()),
            "source": "capafy-payout",
            "date": today,
            "balance_payout_usd": round(float(payout.get("balancePayout", 0) or 0), 2),
            "total_payout_usd": round(float(payout.get("totalPayout", 0) or 0), 2),
            "balance_pending_usd": round(float(payout.get("balancePending", 0) or 0), 2),
            "balance_confirmed_usd": round(float(payout.get("balanceConfirmed", 0) or 0), 2),
            "currency": (payout.get("currency") or "usd"),
            "channel": "capafy_bank_wire",
            "account": payout.get("accountNumber", ""),
            "note": "capafy seller balance snapshot; balance_payout=pending unpaid, total_payout=realized to bank",
            "wake": "capafy_earn_reconcile",
        }
        # drop any prior capafy-payout snapshot for today, then append the fresh one
        new_rows = [r for r in new_rows if not (isinstance(r, dict) and r.get("source") == "capafy-payout" and r.get("date") == today)]
        new_rows.append(payout_row)

    atomic_write(args.ledger, new_rows)

    sale_rows = [r for r in new_rows if isinstance(r, dict) and r.get("source") == "capafy-sales"]
    lifetime_gross = round(sum(float(r.get("gross_usd", 0)) for r in sale_rows), 2)
    lifetime_orders = sum(int(r.get("orders", 0)) for r in sale_rows)

    summary = {
        "ok": True,
        "ledger_path": args.ledger,
        "sale_rows_added": added,
        "lifetime_gross_usd": lifetime_gross,
        "lifetime_orders": lifetime_orders,
        "payout_fetch_status": payout_fetch_status,
        "newest_sale_date": sale_rows[-1]["date"] if sale_rows else None,
    }
    if payout_row is not None:
        summary["balance_payout_usd"] = payout_row["balance_payout_usd"]
        summary["total_payout_usd"] = payout_row["total_payout_usd"]
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
