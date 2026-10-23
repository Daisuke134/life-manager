#!/usr/bin/env python3
"""Write Coconala's CFO marketplace financial readback from the official revenue history.

Source: every page of https://coconala.com/mypage/revenue (売上履歴), read over the
already-leased gig browser (see paid-direct-owner).  Each row is one settled sale; its
amount is the 売上 Coconala credits the seller after its service fee.  That credited
amount is recorded as the sale and no fee is invented.

Honesty rules for skills/cfo/adapters/marketplace.py:
- pagination/receipt_map are complete only when the rows sum exactly to the page's own
  累積売上; otherwise the adapter emits no revenue (unknown, never zero).
- coverage.complete stays false: the page itemizes neither fees nor refunds, so the
  CFO reports this credited 売上 as revenue only and keeps refunds, fees and net unknown.

Usage:
  coconala_cfo_financial_readback.py --output PATH [--cdp URL]          # live read, write
  coconala_cfo_financial_readback.py --output PATH --from-text P1 --from-text P2 \\
      [--observed-at RFC3339]                                            # saved page texts
  coconala_cfo_financial_readback.py --output PATH --min-interval-seconds N --check-due
      # exit 0 when a refresh is due, 3 when the existing readback is newer than N seconds
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import revenue_collector
from revenue_collector import REVENUE_URL, parse_revenue_text, scrape

JST = timezone(timedelta(hours=9))
MAX_PAGES = 50  # ponytail: page cap; ~10 rows per page, raise when sales pass 500 rows


def _utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_readback(pages: list[str], observed_at: str) -> dict:
    """Pure: ordered revenue page texts -> signed marketplace_financial_readback."""
    rows = parse_revenue_text("\n".join(pages))["rows"]
    cumulative = parse_revenue_text(pages[0])["totals"].get("cumulative_jpy") if pages else None
    total = sum(int(row["jpy"]) for row in rows)
    complete = cumulative is not None and total == int(cumulative)
    records, seen = [], {}
    for row in rows:
        moment = datetime.strptime(row["closed_at"], "%Y/%m/%d %H:%M").replace(tzinfo=JST)
        # Identical rows (e.g. two tips in one talkroom at one minute) are distinct sales.
        key = f"{row['talkroom_id']}-{moment:%Y%m%d%H%M}"
        index = seen[key] = seen.get(key, -1) + 1
        amount = int(row["jpy"])
        records.append({
            "schema_version": 1, "record_type": "payment_receipt", "platform": "coconala",
            "work_external_id": f"talkroom-{row['talkroom_id']}",
            "payment_external_id": f"coconala-talkroom-{key}-{index}",
            "receipt_id": f"coconala-revenue-{key}-{index}",
            "gross_amount_minor": amount, "fee_amount_minor": 0, "cost_amount_minor": 0,
            "net_amount_minor": amount, "currency": "JPY", "status": "settled",
            "occurred_at": _utc(moment), "observed_at": observed_at,
        })
    trailing_start = _utc(_parse_utc(observed_at) - timedelta(days=30))
    payload = {
        "schema_version": 1,
        "record_type": "marketplace_financial_readback",
        "platform": "coconala",
        "product_loop_id": "gig-coconala",
        "observed_at": observed_at,
        "coverage": {
            "historical": {"complete": False, "window_start": None, "window_end": observed_at},
            "trailing": {"complete": False, "window_start": trailing_start, "window_end": observed_at},
        },
        "pagination": {
            "complete": complete, "pages_fetched": len(pages),
            "records_fetched": len(records), "next_cursor": None,
        },
        "receipt_map": {"complete": complete, "records": records},
        "aggregate": {"currency": "JPY", "sales_count": len(records), "net_amount_minor": total},
    }
    digest = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    payload["content_sha256"] = digest
    payload["evidence_ref"] = f"marketplace://coconala/financial-readback/sha256/{digest}"
    return payload


def read_pages(cdp_url: str) -> list[str]:
    """Read history pages until the rows reach the page's own 累積売上 (or rows run out)."""
    pages = [scrape(cdp_url)]
    cumulative = parse_revenue_text(pages[0])["totals"].get("cumulative_jpy")
    while cumulative is not None and len(pages) < MAX_PAGES:
        seen = sum(row["jpy"] for row in parse_revenue_text("\n".join(pages))["rows"])
        if seen >= cumulative:
            break
        text = scrape(cdp_url, f"{REVENUE_URL}/page:{len(pages) + 1}")
        if not parse_revenue_text(text)["rows"]:
            break
        pages.append(text)
    return pages


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _fresh(path: Path, min_interval_seconds: int) -> bool:
    try:
        observed = _parse_utc(json.loads(path.read_text(encoding="utf-8"))["observed_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    age = datetime.now(timezone.utc) - observed
    return timedelta(0) <= age < timedelta(seconds=min_interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cdp", default=os.environ.get("CDP") or os.environ.get("CLOAK_CDP_BASE_URL"))
    parser.add_argument("--from-text", action="append", type=Path, default=[])
    parser.add_argument("--observed-at")
    parser.add_argument("--min-interval-seconds", type=int, default=0)
    parser.add_argument("--check-due", action="store_true")
    args = parser.parse_args()

    if args.min_interval_seconds and _fresh(args.output, args.min_interval_seconds):
        if args.check_due:
            return 3
        print(json.dumps({"status": "fresh", "output": str(args.output)}))
        return 0
    if args.check_due:
        return 0

    appended: list[dict] = []
    if args.from_text:
        pages = [path.read_text(encoding="utf-8") for path in args.from_text]
        observed_at = args.observed_at or _utc(datetime.now(timezone.utc))
    elif args.cdp:
        pages = read_pages(args.cdp)
        observed_at = _utc(datetime.now(timezone.utc))
    else:
        parser.error("need --cdp (or CDP env from with-browser.sh) or --from-text")

    payload = build_readback(pages, _utc(_parse_utc(observed_at)))
    write_atomic(args.output, payload)
    # Talkroom -> service title for experiment_evaluator's receipt join; buyers stay out.
    write_atomic(args.output.with_name(f"{args.output.stem}-titles.json"), {
        "observed_at": payload["observed_at"],
        "titles": {row["talkroom_id"]: row["title"]
                   for row in parse_revenue_text("\n".join(pages))["rows"]},
    })
    if not args.from_text:
        # Same official pages feed the settled-sales ledger (~/gig/earnings.jsonl); idempotent.
        appended = revenue_collector.append_new(parse_revenue_text("\n".join(pages)), REVENUE_URL)
    print(json.dumps({
        "status": "written", "output": str(args.output),
        "complete": payload["receipt_map"]["complete"],
        "pages": payload["pagination"]["pages_fetched"],
        "records": payload["pagination"]["records_fetched"],
        "net_jpy": payload["aggregate"]["net_amount_minor"],
        "observed_at": payload["observed_at"],
        "earnings_appended": len(appended),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
