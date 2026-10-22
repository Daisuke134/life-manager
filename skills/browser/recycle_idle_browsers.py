#!/usr/bin/env python3
"""Recycle always-on owner browsers that have run too long while idle.

Chromium owners grow back to ~8 GB within hours even with tab sweeping; swap reached 10 GB
and free disk fell below the producer floor three times on 2026-10-18, pausing the Capafy
distribute loop. Each run leases every launchd keep-alive owner (ai.anicca.*-browser) that is
free, and closes the browser gracefully once it has been up longer than MAX_AGE; launchd
KeepAlive starts a fresh one. Busy leases, Dais's Chrome and provisioned browsers are skipped.
Below the shared producer disk floor, the existing recycle cadence shortens the idle age.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT))
from runtime.host import disk_admission  # noqa: E402

REGISTRY = Path(os.environ.get("AI_BROWSER_REGISTRY", str(Path.home() / ".config/ai/registry/browsers.toml")))
LOOP_REGISTRY = REPO_ROOT / "config" / "loop-registry.json"
MAX_AGE = int(os.environ.get("BROWSER_RECYCLE_MAX_AGE_SECONDS", str(4 * 3600)))


def recycle_targets(registry: dict) -> list[dict]:
    return [i for i in registry.get("identity", [])
            if i.get("id") != "interactive:dais"
            and str(i.get("launched_by", "")).startswith("ai.anicca.")
            and str(i.get("launched_by", "")).endswith("-browser")]


def should_recycle(uptime_seconds: int | None, max_age: int) -> bool:
    return uptime_seconds is not None and uptime_seconds > max_age


def _etime_seconds(etime: str) -> int:
    days, _, rest = etime.rpartition("-")
    parts = [int(p) for p in rest.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return int(days or 0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def effective_max_age() -> tuple[int, bool | None]:
    try:
        available = disk_admission.disk_free_bytes(disk_admission._host_state_dir())
        pressure = None if available is None else available < disk_admission._producer_floor_bytes()
        if pressure:
            cadence = json.loads(LOOP_REGISTRY.read_text())["loops"]["browser-recycle-idle"]["cadence"]["start_interval_seconds"]
            if type(cadence) is int and cadence > 0:
                return min(MAX_AGE, cadence), pressure
    except (OSError, KeyError, ValueError, TypeError):
        return MAX_AGE, None
    return MAX_AGE, pressure


def browser_process(profile: str) -> tuple[int, int] | None:
    """Read one exact profile owner, retaining its PID for the lease recheck."""
    marker = f"--user-data-dir={os.path.realpath(os.path.expanduser(profile))}"
    try:
        result = subprocess.run(["ps", "-u", str(os.getuid()), "-ww", "-o", "pid=,etime=,command="],
                                capture_output=True, text=True)
        if result.returncode != 0:
            return None
        owners = []
        for line in result.stdout.splitlines():
            if ("MacOS/Chromium" in line and "--type=" not in line
                    and re.search(re.escape(marker) + r"(?=\s|$)", line)):
                pid, etime, _ = line.split(None, 2)
                owners.append((int(pid), _etime_seconds(etime)))
        return owners[0] if len(owners) == 1 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _close(cdp: str) -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415
    with sync_playwright() as p:
        session = p.chromium.connect_over_cdp(cdp).new_browser_cdp_session()
        try:
            session.send("Browser.close")
        except Exception:  # noqa: BLE001 -- the connection drops as the browser exits
            pass


def main() -> int:
    guard = str(HERE / "browser-guard.sh")
    report = []
    for ident in recycle_targets(tomllib.loads(REGISTRY.read_text())):
        process = browser_process(ident["profile"])
        uptime = process[1] if process else None
        max_age, pressure = effective_max_age()
        entry = {"id": ident["id"], "action": "keep", "uptime": uptime,
                 "effective_max_age": max_age, "disk_pressure": pressure}
        report.append(entry)
        if not should_recycle(uptime, max_age):
            continue
        try:
            acquired = subprocess.run(["bash", guard, "acquire", ident["id"]], capture_output=True, text=True)
            cdp = acquired.stdout.strip().splitlines()[-1] if acquired.returncode == 0 and acquired.stdout.strip() else ""
        except (OSError, subprocess.SubprocessError):
            cdp = ""
        if not re.match(r"^(ws|http)://", cdp):
            entry["action"] = "busy"
            continue
        try:
            fresh = browser_process(ident["profile"])
            uptime = fresh[1] if fresh else None
            max_age, pressure = effective_max_age()
            entry.update(uptime=uptime, effective_max_age=max_age, disk_pressure=pressure)
            if fresh is None or fresh[0] != process[0] or not should_recycle(uptime, max_age):
                continue
            _close(cdp)
            entry["action"] = "recycled"
        finally:
            subprocess.run(["bash", guard, "release", ident["id"]], capture_output=True, text=True)
    print(json.dumps({"max_age": MAX_AGE, "browsers": report}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
