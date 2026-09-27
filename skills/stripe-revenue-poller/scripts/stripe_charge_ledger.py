#!/usr/bin/env python3
"""Append-only Stripe charge ledger + read-only summarizer.

poll.sh pipes the Charges API list-response JSON on stdin to `append`; each
charge id is written at most once (idempotent by id, checked against the
existing file). `summarize` prints totals by currency and by product for the
last N days, reading only the local ledger — no Stripe API calls.

Never talks to Stripe directly and never creates/refunds/pays anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _product_id(charge: dict) -> str | None:
    # ponytail: charges carry no line items; only metadata is free (no extra API call).
    meta = charge.get("metadata") or {}
    return meta.get("product_id") or meta.get("product") or meta.get("price_id") or meta.get("price")


def to_row(charge: dict, observed_at: str) -> dict:
    return {
        "id": charge["id"],
        "created": _iso(charge["created"]),
        "amount": charge.get("amount", 0),
        "currency": charge.get("currency"),
        "amount_refunded": charge.get("amount_refunded", 0),
        "status": charge.get("status"),
        "paid": bool(charge.get("paid", False)),
        "refunded": bool(charge.get("refunded", False)),
        "description": charge.get("description") or charge.get("statement_descriptor"),
        "product_id": _product_id(charge),
        "livemode": bool(charge.get("livemode", False)),
        "observed_at": observed_at,
    }


def existing_ids(ledger: Path) -> set:
    ids = set()
    if not ledger.exists():
        return ids
    with ledger.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def append(ledger: Path, charges: list) -> int:
    """Append charges not already present (by id). Returns rows written."""
    seen = existing_ids(ledger)
    observed_at = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    new_rows = [to_row(c, observed_at) for c in charges if c.get("id") not in seen]
    if not new_rows:
        return 0
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as fh:
        for row in new_rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    ledger.chmod(0o600)
    return len(new_rows)


def summarize(ledger: Path, since_days: int) -> dict:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=since_days)
    by_currency: dict = {}
    by_product: dict = {}
    if ledger.exists():
        with ledger.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                created = datetime.fromisoformat(row["created"].replace("Z", "+00:00"))
                if created < cutoff:
                    continue
                cur = row.get("currency") or "unknown"
                net = row.get("amount", 0) - row.get("amount_refunded", 0)
                bucket = by_currency.setdefault(cur, {"amount": 0, "count": 0})
                bucket["amount"] += net
                bucket["count"] += 1
                prod = row.get("product_id") or "unknown"
                pbucket = by_product.setdefault(prod, {}).setdefault(cur, {"amount": 0, "count": 0})
                pbucket["amount"] += net
                pbucket["count"] += 1
    return {"since_days": since_days, "by_currency": by_currency, "by_product": by_product}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_append = sub.add_parser("append", help="read a Stripe charges list-response JSON from stdin")
    p_append.add_argument("--ledger", required=True, type=Path)

    p_sum = sub.add_parser("summarize", help="print totals by currency and product")
    p_sum.add_argument("--ledger", required=True, type=Path)
    p_sum.add_argument("--since", default="30d", help="lookback window, e.g. 30d")

    args = parser.parse_args(argv)

    if args.cmd == "append":
        payload = json.load(sys.stdin)
        charges = payload.get("data") if isinstance(payload, dict) else payload
        print(append(args.ledger, charges or []))
        return 0

    if args.cmd == "summarize":
        since_days = int(args.since.rstrip("dD"))
        print(json.dumps(summarize(args.ledger, since_days), indent=2, sort_keys=True))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
