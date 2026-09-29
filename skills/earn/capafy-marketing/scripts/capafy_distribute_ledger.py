#!/usr/bin/env python3
"""capafy_distribute_ledger.py — one-article-per-JST-date idempotency ledger
for the capafy-distribute-daily loop.

Keeps a single JSON object keyed by date so a re-run (retry, double launchd
wake, manual invocation) never republishes the same day's article. Writes are
atomic (tmp file + os.replace) and preserve every other date's entry -- the
same law article-daily's own durable cursor follows (see
skills/loop-development/SKILL.md "a loop recreates an already published item
after a successful wake").

  capafy_distribute_ledger.py check --ledger <path> --date 2026-09-29
      exit 0  = not yet published today, safe to proceed
      exit 10 = already published today (fail closed, no duplicate)

  capafy_distribute_ledger.py record --ledger <path> --date 2026-09-29 --json '{"...":"..."}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ALREADY_PUBLISHED = 10


def load(ledger_path: Path) -> dict:
    if not ledger_path.exists():
        return {}
    text = ledger_path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("ledger must be a JSON object keyed by date")
    return value


def is_published(ledger_path: Path, date: str) -> bool:
    entry = load(ledger_path).get(date)
    return bool(entry and entry.get("status") == "published")


def record(ledger_path: Path, date: str, entry: dict) -> dict:
    ledger_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = load(ledger_path)
    data[date] = entry
    tmp = ledger_path.with_suffix(ledger_path.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, ledger_path)
    os.chmod(ledger_path, 0o600)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    check_p = sub.add_parser("check")
    check_p.add_argument("--ledger", required=True)
    check_p.add_argument("--date", required=True)

    record_p = sub.add_parser("record")
    record_p.add_argument("--ledger", required=True)
    record_p.add_argument("--date", required=True)
    record_p.add_argument("--json", required=True, help="entry payload, e.g. {\"status\":\"published\",...}")

    args = parser.parse_args(argv)
    ledger_path = Path(args.ledger).expanduser()

    if args.command == "check":
        if is_published(ledger_path, args.date):
            print(json.dumps({"already_published": True, "date": args.date}))
            return ALREADY_PUBLISHED
        print(json.dumps({"already_published": False, "date": args.date}))
        return 0

    entry = json.loads(args.json)
    if not isinstance(entry, dict):
        raise ValueError("--json entry must be an object")
    data = record(ledger_path, args.date, entry)
    print(json.dumps({"date": args.date, "entry": data[args.date]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
