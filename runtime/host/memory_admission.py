#!/usr/bin/env python3
"""Defer new loop work while macOS memory headroom is unsafe."""

from __future__ import annotations

import json
import math
import os
import pwd
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Sequence


_FREE_PERCENT = re.compile(r"System-wide memory free percentage:\s*(\d+)%")
_RESOURCE_CLASSES = frozenset({"agent", "deterministic", "browser", "model", "unknown"})


def _metric_int(name: str, value: object, *, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"invalid {name}")
    if maximum is not None and value > maximum:
        raise ValueError(f"invalid {name}")
    return value


def _optional_metric_int(name: str, value: object, *, maximum: int | None = None) -> int | None:
    if value is None:
        return None
    return _metric_int(name, value, maximum=maximum)


def _metric_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"invalid {name}")
    return float(value)


def build_host_pressure_record(
    *, observed_at: str, resource_class: str,
    memory_free_percent: int | None, swap_used_bytes: int | None,
    load_1m: int | float | None, active_finite_wakes: int,
    active_browser_sessions: int, browser_processes: int,
    browser_debug_endpoints: int,
) -> dict[str, object]:
    """Build a secret-free host/browser pressure snapshot for admission decisions."""
    if not isinstance(observed_at, str) or not observed_at:
        raise ValueError("invalid observed_at")
    try:
        datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid observed_at") from error
    if resource_class not in _RESOURCE_CLASSES:
        raise ValueError("invalid resource_class")
    return {
        "schema_version": 1,
        "record_type": "host_pressure",
        "observed_at": observed_at,
        "resource_class": resource_class,
        "memory_free_percent": _optional_metric_int(
            "memory_free_percent", memory_free_percent, maximum=100
        ),
        "swap_used_bytes": _optional_metric_int("swap_used_bytes", swap_used_bytes),
        "load_1m": None if load_1m is None else _metric_number("load_1m", load_1m),
        "active_finite_wakes": _metric_int("active_finite_wakes", active_finite_wakes),
        "active_browser_sessions": _metric_int("active_browser_sessions", active_browser_sessions),
        "browser_processes": _metric_int("browser_processes", browser_processes),
        "browser_debug_endpoints": _metric_int("browser_debug_endpoints", browser_debug_endpoints),
        "redaction": "metrics_only",
    }


def parse_free_percent(output: str) -> int | None:
    match = _FREE_PERCENT.search(output)
    if not match:
        return None
    value = int(match.group(1))
    return value if 0 <= value <= 100 else None


def memory_free_percent() -> int | None:
    try:
        result = subprocess.run(
            ["/usr/bin/memory_pressure", "-Q"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return parse_free_percent(result.stdout)


def _receipt_path() -> Path:
    configured = os.environ.get("LIFE_MANAGER_MEMORY_RECEIPT")
    if configured:
        return Path(configured).expanduser()
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return home / ".local/state/life-manager/host-admission/memory.json"


def _write_receipt(payload: dict[str, object]) -> None:
    path = _receipt_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".memory.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(temporary).unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    wait_seconds = 0
    if args[:1] == ["--wait-seconds"]:
        if len(args) < 4 or args[2] != "--":
            return 64
        try:
            wait_seconds = int(args[1])
        except ValueError:
            return 64
        if not 1 <= wait_seconds <= 3600:
            return 64
        args = args[3:]
    command = args
    if not command:
        return 64
    try:
        minimum = int(os.environ.get("LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT", "15"))
    except ValueError:
        return 64
    if not 1 <= minimum <= 100:
        return 64
    while True:
        available = memory_free_percent()
        if available is None:
            _write_receipt({
                "status": "deferred", "effect": 0,
                "reason": "memory_headroom_unavailable",
                "minimum_free_percent": minimum,
            })
        elif available < minimum:
            _write_receipt({
                "status": "deferred", "effect": 0,
                "reason": "memory_headroom_low", "free_percent": available,
                "minimum_free_percent": minimum,
            })
        else:
            break
        if not wait_seconds:
            return 75
        time.sleep(wait_seconds)
    _write_receipt({
        "status": "pass", "effect": 0, "reason": "memory_headroom_ok",
        "free_percent": available, "minimum_free_percent": minimum,
    })
    os.execvpe(command[0], command, os.environ)
    return 70


if __name__ == "__main__":
    raise SystemExit(main())
