#!/usr/bin/env python3
"""Read-only health and context-count probe for the registered daily-driver."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any


IDENTITY = "interactive:dais"


def run_probe(endpoint: str, inventory: dict[str, Any]) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(str(endpoint))
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or not parsed.port
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return {"ok": False, "reason": "browser_endpoint_invalid", "effect": 0}

    context_count = inventory.get("context_count")
    leased = inventory.get("leased_context_ids")
    unknown = inventory.get("unknown_owner_contexts")
    if (
        inventory.get("ok") is not True
        or isinstance(context_count, bool)
        or not isinstance(context_count, int)
        or context_count < 0
        or not isinstance(leased, list)
        or not isinstance(unknown, list)
    ):
        return {"ok": False, "reason": "context_inventory_unavailable", "effect": 0}

    return {
        "ok": True,
        "reason": "cdp_ready",
        "effect": 0,
        "context_count": context_count,
        "leased_context_count": len(leased),
        "unknown_owner_context_count": len(unknown),
    }


def _run_json(command: list[str], *, env: dict[str, str] | None = None) -> tuple[int, dict[str, Any] | None]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
            env=env,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return 1, None
    return result.returncode, payload if isinstance(payload, dict) else None


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    resolver = root / "skills/browser/resolve_cdp_endpoint.py"
    context_lease = root / "skills/browser/scripts/cdp_context_lease.py"
    registry = Path(os.environ.get(
        "AI_BROWSER_REGISTRY",
        "~/.config/ai/registry/browsers.toml",
    )).expanduser()

    resolver_rc, resolved = _run_json([
        sys.executable, str(resolver), "--registry", str(registry), "--identity", IDENTITY,
    ])
    endpoint = resolved.get("endpoint") if resolved else None
    if resolver_rc != 0 or resolved is None or resolved.get("identity") != IDENTITY or not endpoint:
        result = {"ok": False, "reason": "registered_browser_unavailable", "effect": 0}
    else:
        lease_env = dict(os.environ)
        lease_env["CLOAK_CDP_BASE_URL"] = str(endpoint)
        lease_rc, inventory = _run_json(
            [sys.executable, str(context_lease), "audit"],
            env=lease_env,
        )
        result = (
            run_probe(str(endpoint), inventory)
            if lease_rc == 0 and inventory is not None
            else {"ok": False, "reason": "context_inventory_unavailable", "effect": 0}
        )

    print(json.dumps({
        "status": "ok" if result["ok"] else "failed",
        "reason": result["reason"],
        "effect": 0,
        **{
            key: result[key]
            for key in ("context_count", "leased_context_count", "unknown_owner_context_count")
            if key in result
        },
    }, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
