#!/usr/bin/env python3
"""Registry-owned host cleanup wake without a second release or scratch GC."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import disk_cleanup


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
        return disk_cleanup.main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
