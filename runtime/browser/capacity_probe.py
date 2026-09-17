#!/usr/bin/env python3
"""Check an isolated local browser transport through its own CDP endpoint."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def _stop_owned_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    time.sleep(0.5)
    # Keep the parent unreaped so its process-group ID cannot be reused here.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # macOS may report EPERM for a group with only its unreaped leader.
        pass
    process.wait(timeout=2)


def run_probe(binary: Path, state_root: Path, *, timeout_seconds: float = 20) -> dict:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return {"ok": False, "reason": "browser_unavailable"}
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    watched = (signal.SIGTERM, signal.SIGINT)
    previous = {signum: signal.getsignal(signum) for signum in watched}
    cancelled = False

    def cancel(_signum, _frame):
        nonlocal cancelled
        cancelled = True

    for signum in watched:
        signal.signal(signum, cancel)
    try:
        with tempfile.TemporaryDirectory(prefix="browser-probe-", dir=state_root) as profile:
            command = [
                str(binary), "--no-sandbox", "--no-first-run", "--no-default-browser-check",
                "--disable-sync", "--disable-extensions",
                "--disable-features=MacAppCodeSignClone",
                "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                "--no-startup-window", f"--user-data-dir={profile}",
            ]
            process = None
            if cancelled:
                return {"ok": False, "reason": "cancelled"}
            try:
                process = subprocess.Popen(
                    command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                port_file = Path(profile) / "DevToolsActivePort"
                deadline = time.monotonic() + timeout_seconds
                while time.monotonic() < deadline:
                    if cancelled:
                        return {"ok": False, "reason": "cancelled"}
                    if port_file.is_file():
                        try:
                            port = int(port_file.read_text().splitlines()[0])
                            if not 1 <= port <= 65535:
                                raise ValueError("invalid CDP port")
                            with urllib.request.urlopen(
                                f"http://127.0.0.1:{port}/json/version", timeout=2,
                            ) as response:
                                details = json.load(response)
                            if isinstance(details.get("Browser"), str) and details["Browser"]:
                                return {"ok": True, "reason": "cdp_ready"}
                        except (OSError, ValueError, IndexError, json.JSONDecodeError):
                            pass
                    time.sleep(0.1)
                return {"ok": False, "reason": "cdp_unavailable"}
            finally:
                if process is not None:
                    _stop_owned_group(process)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main() -> int:
    state_root = os.environ.get("LIFE_MANAGER_STATE_ROOT")
    binaries = sorted(Path.home().glob(
        ".cloakbrowser/chromium-*/Chromium.app/Contents/MacOS/Chromium"))
    result = (run_probe(binaries[-1], Path(state_root)) if state_root and binaries
              else {"ok": False, "reason": "browser_unavailable"})
    print(json.dumps({"status": "ok" if result["ok"] else "failed",
                      "reason": result["reason"], "effect": 0}, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
