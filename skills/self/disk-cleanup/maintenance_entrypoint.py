#!/usr/bin/env python3
"""Legacy 15-day owner; host sweeping belongs to the minute watchdog."""

from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) != 1:
        print("disk maintenance entrypoint takes no arguments", file=sys.stderr)
        return 2
    print(json.dumps({
        "ok": True,
        "status": "delegated",
        "owner_id": "com.anicca.disk-watchdog",
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
