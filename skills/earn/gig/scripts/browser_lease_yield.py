#!/usr/bin/env python3
"""Temporarily yield an outer browser identity during provider-independent work."""

from __future__ import annotations

import os
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class BrowserLeaseYieldError(RuntimeError):
    def __init__(self, stage: str, reason: str):
        super().__init__(f"{stage}:{reason}")
        self.stage = stage
        self.reason = reason


@contextmanager
def yield_registered_browser_lease() -> Iterator[None]:
    holder = os.environ.get("LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID", "").strip()
    identity = os.environ.get("LIFE_MANAGER_BROWSER_LEASE_IDENTITY", "").strip()
    guard_value = os.environ.get("LIFE_MANAGER_BROWSER_GUARD", "").strip()
    if not holder or not holder.isdigit() or not identity or not guard_value:
        yield
        return
    guard = Path(guard_value)
    if not guard.is_file() or guard.is_symlink():
        raise BrowserLeaseYieldError("browser_lease_yield", "browser_guard_invalid")
    environment = dict(os.environ)
    environment["AI_BROWSER_HOLDER_PID"] = holder
    released = subprocess.run(
        [str(guard), "release", identity], capture_output=True, text=True, check=False,
        env=environment,
    )
    if released.returncode != 0:
        raise BrowserLeaseYieldError("browser_lease_yield", "browser_release_failed")
    try:
        yield
    finally:
        try:
            wait_seconds = int(os.environ.get("BROWSER_WAIT_SECONDS", "300"))
        except ValueError:
            wait_seconds = 300
        deadline = time.monotonic() + max(1, min(wait_seconds, 3600))
        acquired = None
        while time.monotonic() <= deadline:
            acquired = subprocess.run(
                [str(guard), "acquire", identity], capture_output=True, text=True,
                check=False, env=environment,
            )
            if acquired.returncode == 0:
                endpoint = acquired.stdout.strip()
                match = re.fullmatch(r"http://127\.0\.0\.1:([0-9]{1,5})/?", endpoint)
                if match is None:
                    raise BrowserLeaseYieldError(
                        "browser_lease_reacquire", "browser_endpoint_invalid"
                    )
                port = match.group(1)
                os.environ.update({
                    "CLOAK_CDP_BASE_URL": endpoint,
                    "CDP": endpoint,
                    "CDP_DAILY_DRIVER_PORT": port,
                    "SESSION_VAULT_PORT": port,
                    "GIG_CDP_HEALTH_URL": f"{endpoint.rstrip('/')}/json/version",
                })
                break
            time.sleep(1)
        else:
            raise BrowserLeaseYieldError(
                "browser_lease_reacquire",
                f"browser_reacquire_failed:{getattr(acquired, 'returncode', 'missing')}",
            )
