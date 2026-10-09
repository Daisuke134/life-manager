#!/usr/bin/env python3
"""Registry-owned host cleanup wake without a second release or scratch GC."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import time
from contextlib import redirect_stdout

import disk_cleanup

MAX_LOCK_BUSY_ATTEMPTS = 3
LOCK_BUSY_RETRY_SECONDS = 5


def _is_cleanup_lock_busy(returncode: int, output: str) -> bool:
    if returncode != 75:
        return False

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"non-standard JSON constant: {value}")

    try:
        receipt = json.loads(
            output,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        type(receipt) is dict
        and receipt.get("ok") is False
        and receipt.get("status") == "deferred"
        and receipt.get("reason") == "cleanup_lock_busy"
        and type(receipt.get("effect")) is int
        and receipt["effect"] == 0
        and type(receipt.get("readback")) is int
        and receipt["readback"] == 0
    )


def main() -> int:
    if len(sys.argv) != 1:
        print("disk maintenance entrypoint takes no arguments", file=sys.stderr)
        return 2

    home = Path.home()
    state_dir = Path(os.environ.get(
        "LIFE_MANAGER_HOST_STATE_DIR",
        str(home / ".local/state/life-manager/state"),
    )).expanduser()
    original_argv = sys.argv
    try:
        sys.argv = [
            original_argv[0],
            "--home",
            str(home),
            "--state-dir",
            str(state_dir),
        ]
        for attempt in range(MAX_LOCK_BUSY_ATTEMPTS):
            output = io.StringIO()
            with redirect_stdout(output):
                returncode = disk_cleanup.main()
            result = output.getvalue()
            if (not _is_cleanup_lock_busy(returncode, result)
                    or attempt + 1 == MAX_LOCK_BUSY_ATTEMPTS):
                sys.stdout.write(result)
                return returncode
            time.sleep(LOCK_BUSY_RETRY_SECONDS)
        raise AssertionError("bounded lock retry loop did not terminate")
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
