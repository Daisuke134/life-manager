#!/usr/bin/env python3
"""Defer new loop work while macOS memory headroom is unsafe."""

from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Sequence


_FREE_PERCENT = re.compile(r"System-wide memory free percentage:\s*(\d+)%")


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


_SWAP_USED = re.compile(r"used\s*=\s*([0-9.]+)M")


def parse_swap_used_mb(output: str) -> float | None:
    match = _SWAP_USED.search(output)
    return float(match.group(1)) if match else None


def swap_used_mb() -> float | None:
    """macOS grows swap files on demand, so used/total is always near 1; the absolute used size
    against physical RAM is the signal (2026-10-23: 15.7-18.1 GB on a 16 GB Mac while
    memory_pressure -Q still read 29-31% free)."""
    try:
        result = subprocess.run(["/usr/sbin/sysctl", "-n", "vm.swapusage"], capture_output=True,
                                text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return parse_swap_used_mb(result.stdout)


SWAP_WINDOW_SECONDS = 900   # a rise is judged over the last 15 minutes
SWAP_MIN_HISTORY_SECONDS = 300  # less history than this proves nothing, so the gate stays closed
SWAP_RISE_MB = 500  # a storm grows; an idle host sitting high does not


def _swap_samples_path() -> Path:
    configured = os.environ.get("LIFE_MANAGER_SWAP_SAMPLES")
    if configured:
        return Path(configured).expanduser()
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return home / ".local/state/life-manager/host-admission/swap-samples.json"


def swap_plateau(used_mb: float, now: float | None = None) -> bool:
    """Record this swap reading and say whether swap is sitting high without growing.

    2026-10-24: the host idles at 14-15.6 GB, above the fixed 13.9 GB limit, so every revenue
    loop was deferred for ~10 hours although nothing was growing. The 10-23 storm GREW from 15.7
    to 18.1 GB. True only with >=5 minutes of history and a rise under 500 MB; any doubt
    (no history, unwritable file) returns False so the gate stays closed.
    """
    now = time.time() if now is None else now
    path = _swap_samples_path()
    try:
        rows = json.loads(path.read_text())
        samples = [(float(t), float(u)) for t, u in rows if now - float(t) <= SWAP_WINDOW_SECONDS]
    except (OSError, ValueError, TypeError):
        samples = []
    oldest = min(samples, default=None)
    samples.append((now, used_mb))
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".swap.", dir=path.parent)
        with os.fdopen(fd, "w") as handle:
            json.dump(samples, handle)
        os.replace(temporary, path)
    except OSError:
        return False
    if oldest is None or now - oldest[0] < SWAP_MIN_HISTORY_SECONDS:
        return False
    return used_mb - oldest[1] < SWAP_RISE_MB


def physical_memory_mb() -> float | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 * 1024)
    except (ValueError, OSError, AttributeError):
        return None


def swap_pressure(max_percent_of_ram: int) -> dict | None:
    """None when swap is within budget or unmeasurable; else the receipt fields for a deferral."""
    used = swap_used_mb()
    ram = physical_memory_mb()
    if used is None or not ram:
        return None
    limit = ram * max_percent_of_ram / 100
    if used < limit or swap_plateau(used):
        return None
    return {"reason": "swap_pressure_high", "swap_used_mb": used, "swap_limit_mb": limit,
            "max_swap_percent_of_ram": max_percent_of_ram}


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
    try:
        max_swap = int(os.environ.get("LIFE_MANAGER_MAX_SWAP_PERCENT_OF_RAM", "85"))
    except ValueError:
        return 64
    if not 1 <= max_swap <= 1000:
        return 64
    while True:
        available = memory_free_percent()
        swap = swap_pressure(max_swap) if available is not None and available >= minimum else None
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
        elif swap is not None:
            _write_receipt({"status": "deferred", "effect": 0, "free_percent": available,
                            "minimum_free_percent": minimum, **swap})
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
