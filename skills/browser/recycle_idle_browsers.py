#!/usr/bin/env python3
"""Recycle always-on owner browsers that have run too long while idle.

Chromium owners grow back to ~8 GB within hours even with tab sweeping; swap reached 10 GB
and free disk fell below the producer floor three times on 2026-10-18, pausing the Capafy
distribute loop. Each run leases every launchd keep-alive owner (ai.anicca.*-browser) that is
free, and closes the browser gracefully once it has been up longer than MAX_AGE; launchd
KeepAlive starts a fresh one. Busy leases, Dais's Chrome and provisioned browsers are skipped.
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
REGISTRY = Path(os.environ.get("AI_BROWSER_REGISTRY", str(Path.home() / ".config/ai/registry/browsers.toml")))
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


def browser_uptime(profile: str) -> int | None:
    marker = f"--user-data-dir={os.path.realpath(os.path.expanduser(profile))}"
    out = subprocess.run(["ps", "-u", str(os.getuid()), "-ww", "-o", "etime=,command="],
                         capture_output=True, text=True).stdout
    ages = [_etime_seconds(line.split(None, 1)[0]) for line in out.splitlines()
            if "MacOS/Chromium" in line and marker in line and "--type=" not in line]
    return max(ages) if ages else None


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
        uptime = browser_uptime(ident["profile"])
        if not should_recycle(uptime, MAX_AGE):
            report.append({"id": ident["id"], "action": "keep", "uptime": uptime})
            continue
        acquired = subprocess.run(["bash", guard, "acquire", ident["id"]], capture_output=True, text=True)
        cdp = acquired.stdout.strip().splitlines()[-1] if acquired.returncode == 0 and acquired.stdout.strip() else ""
        if not re.match(r"^(ws|http)://", cdp):
            report.append({"id": ident["id"], "action": "busy", "uptime": uptime})
            continue
        try:
            _close(cdp)
            report.append({"id": ident["id"], "action": "recycled", "uptime": uptime})
        finally:
            subprocess.run(["bash", guard, "release", ident["id"]], capture_output=True, text=True)
    print(json.dumps({"max_age": MAX_AGE, "browsers": report}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
