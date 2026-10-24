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


_SWAPINS = re.compile(r"Swapins:\s*(\d+)")


def parse_swapins(output: str) -> int | None:
    match = _SWAPINS.search(output)
    return int(match.group(1)) if match else None


def swapins() -> int | None:
    """Cumulative pages read back from swap since boot (vm_stat)."""
    try:
        result = subprocess.run(["/usr/bin/vm_stat"], capture_output=True, text=True, timeout=5,
                                check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return parse_swapins(result.stdout)


SWAP_WINDOW_SECONDS = 900   # the rate is judged over the last 15 minutes
SWAP_MIN_HISTORY_SECONDS = 300  # less history than this proves no rate
# 2026-10-24 14:1x JST, 16 KB pages: an idle-but-busy host at 28-31% free read 159-618 pages/s over
# 10 s windows and 880 over 30 s while swap sat at 17.1/18.4 GB. 2000 pages/s (~31 MB/s sustained
# for 5-15 minutes) is above that working band, so only real thrashing closes the gate.
MAX_SWAPIN_PAGES_PER_SECOND = 2000


def _swap_samples_path() -> Path:
    configured = os.environ.get("LIFE_MANAGER_SWAP_SAMPLES")
    if configured:
        return Path(configured).expanduser()
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return home / ".local/state/life-manager/host-admission/swapin-samples.json"


def swapin_rate(count: int, now: float | None = None) -> float | None:
    """Record this Swapins reading and return pages/s over the window, or None without proof.

    Swap size is not the signal: macOS keeps swapped pages for hours, and the total swings by
    hundreds of MB in minutes. On 2026-10-24 the 15-minute growth rule (#8823) still deferred every
    producer at 15.5-16.5 GB. Pages being read back from swap is what slows the host.
    """
    now = time.time() if now is None else now
    path = _swap_samples_path()
    try:
        rows = json.loads(path.read_text())
        samples = [(float(t), float(c)) for t, c in rows if now - float(t) <= SWAP_WINDOW_SECONDS]
    except (OSError, ValueError, TypeError):
        samples = []
    oldest = min(samples, default=None)
    samples.append((now, float(count)))
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".swap.", dir=path.parent)
        with os.fdopen(fd, "w") as handle:
            json.dump(samples, handle)
        os.replace(temporary, path)
    except OSError:
        return None
    if oldest is None or now - oldest[0] < SWAP_MIN_HISTORY_SECONDS or count < oldest[1]:
        return None  # count < oldest means a reboot reset the counter
    return (count - oldest[1]) / (now - oldest[0])


SWAP_PROBE_SECONDS = 2  # without window history, measure the rate now instead of guessing


def swapin_pages_per_second() -> float | None:
    """Window rate when the shared history proves one; else a short live probe; None without vm_stat.

    A fresh host or CI runner has no history, and deferring on that alone stopped one-shot runs.
    """
    count = swapins()
    if count is None:
        return None
    rate = swapin_rate(count)
    if rate is not None:
        return rate
    time.sleep(SWAP_PROBE_SECONDS)
    later = swapins()
    if later is None or later < count:
        return None
    return (later - count) / SWAP_PROBE_SECONDS


def swap_pressure() -> dict | None:
    """None while pages come back from swap slower than the limit; else the deferral receipt fields.

    No rate (vm_stat unavailable or its counter reset) defers, the same fail-closed rule as before.
    LIFE_MANAGER_SWAPIN_GATE=off exists only for test subprocesses.
    """
    if os.environ.get("LIFE_MANAGER_SWAPIN_GATE") == "off":
        return None
    rate = swapin_pages_per_second()
    if rate is not None and rate < MAX_SWAPIN_PAGES_PER_SECOND:
        return None
    return {"reason": "swap_pressure_high" if rate is not None else "swap_rate_unavailable",
            "swapin_pages_per_second": rate,
            "max_swapin_pages_per_second": MAX_SWAPIN_PAGES_PER_SECOND,
            "swap_used_mb": swap_used_mb()}


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
        swap = swap_pressure() if available is not None and available >= minimum else None
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
