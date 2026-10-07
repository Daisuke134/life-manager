#!/usr/bin/env python3
"""line_sticker_distribute_ledger.py -- one-post-per-slot idempotency fence.

Copied shape (per skills/loop-development/SKILL.md "copy a sibling loop
before any fix") from
skills/earn/capafy-marketing/scripts/capafy_distribute_ledger.py: a single
JSON object keyed by an idempotency key (here "<lane_id>-<slot_at>") so a
retry or double launchd wake never reposts the same lane's slot. Atomic
writes (tmp file + os.replace) preserve every other key's entry.

  line_sticker_distribute_ledger.py check --ledger <path> --key <lane-slot>
      exit 0  = not yet posted for this key, safe to proceed
      exit 10 = already posted for this key (fail closed, no duplicate)

  line_sticker_distribute_ledger.py record --ledger <path> --key <lane-slot> --json '{"...":"..."}'
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
        raise ValueError("ledger must be a JSON object keyed by lane-slot")
    return value


def is_published(ledger_path: Path, key: str) -> bool:
    entry = load(ledger_path).get(key)
    return bool(entry and entry.get("status") == "published")


def record(ledger_path: Path, key: str, entry: dict) -> dict:
    ledger_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = load(ledger_path)
    data[key] = entry
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
    check_p.add_argument("--key", required=True)

    record_p = sub.add_parser("record")
    record_p.add_argument("--ledger", required=True)
    record_p.add_argument("--key", required=True)
    record_p.add_argument("--json", required=True, help='entry payload, e.g. {"status":"published",...}')

    args = parser.parse_args(argv)
    ledger_path = Path(args.ledger).expanduser()

    if args.command == "check":
        if is_published(ledger_path, args.key):
            print(json.dumps({"already_published": True, "key": args.key}))
            return ALREADY_PUBLISHED
        print(json.dumps({"already_published": False, "key": args.key}))
        return 0

    entry = json.loads(args.json)
    if not isinstance(entry, dict):
        raise ValueError("--json entry must be an object")
    data = record(ledger_path, args.key, entry)
    print(json.dumps({"key": args.key, "entry": data[args.key]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
