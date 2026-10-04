#!/usr/bin/env python3
"""Exec one command while holding an advisory file lock."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import sys


def main(argv: list[str]) -> int:
    args = argv[1:]
    non_blocking = bool(args and args[0] == "--non-blocking")
    if non_blocking:
        args = args[1:]
    if len(args) < 3 or args[1] != "--":
        print(f"usage: {argv[0]} [--non-blocking] LOCK -- COMMAND [ARGS...]", file=sys.stderr)
        return 64
    path = Path(args[0]).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | (fcntl.LOCK_NB if non_blocking else 0))
    except BlockingIOError:
        os.close(descriptor)
        print(f"provider_browser_busy: {path}", file=sys.stderr)
        return 75
    os.set_inheritable(descriptor, True)
    os.execvp(args[2], args[2:])
    return 70


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
