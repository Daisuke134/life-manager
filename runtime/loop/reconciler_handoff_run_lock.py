#!/usr/bin/env python3
"""Hold the reconciler's existing per-label run lock during self-handoff."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

from runtime.loop.lm_loop import _apply_lock, _label_apply_lock_path


def _write_status(path: Path, status: str, *, label: str, lock_path: Path,
                  parent_pid: int, error_class: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump({
            "status": status,
            "label": label,
            "lock_path": str(lock_path),
            "parent_pid": parent_pid,
            "error_class": error_class,
        }, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--status-path", required=True, type=Path)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--timeout-seconds", required=True, type=int)
    args = parser.parse_args(argv)
    if (not re.fullmatch(r"[A-Za-z0-9_.-]+", args.label)
            or args.parent_pid <= 1 or args.timeout_seconds < 1):
        return 64

    current = Path("~/loops/current").expanduser()
    lock_path = _label_apply_lock_path(current, args.label)
    deadline = time.monotonic() + args.timeout_seconds
    while True:
        if os.getppid() != args.parent_pid:
            _write_status(args.status_path, "parent_gone", label=args.label,
                          lock_path=lock_path, parent_pid=args.parent_pid)
            return 75
        try:
            with _apply_lock(current, lock_path):
                _write_status(args.status_path, "acquired", label=args.label,
                              lock_path=lock_path, parent_pid=args.parent_pid)
                while os.getppid() == args.parent_pid:
                    time.sleep(0.1)
                return 0
        except RuntimeError as exc:
            if str(exc) != "production apply is already owned":
                _write_status(args.status_path, "failed", label=args.label,
                              lock_path=lock_path, parent_pid=args.parent_pid,
                              error_class=type(exc).__name__)
                return 1
            if time.monotonic() >= deadline:
                _write_status(args.status_path, "timeout", label=args.label,
                              lock_path=lock_path, parent_pid=args.parent_pid,
                              error_class="apply_lock_busy")
                return 75
            time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
