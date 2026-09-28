from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def probe_cdp(endpoint: str) -> dict[str, str]:
    base = endpoint.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/json/version", timeout=5) as response:
            payload: Any = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        return {
            "status": "unavailable",
            "owner": "ai.anicca.job-search-daily",
            "endpoint": base,
            "error": str(error),
        }
    browser = payload.get("Browser") if isinstance(payload, dict) else None
    websocket = (
        payload.get("webSocketDebuggerUrl") if isinstance(payload, dict) else None
    )
    if not isinstance(browser, str) or not isinstance(websocket, str):
        return {
            "status": "unavailable",
            "owner": "ai.anicca.job-search-daily",
            "endpoint": base,
            "error": "CDP version response is incomplete",
        }
    return {
        "status": "ready",
        "owner": "ai.anicca.job-search-daily",
        "endpoint": base,
        "browser": browser,
        "websocket": websocket,
    }


def wait_for_cdp(
    endpoint: str, *, timeout_seconds: float = 30.0, retry_interval_seconds: float = 0.5
) -> dict[str, str]:
    deadline = time.monotonic() + timeout_seconds
    result = probe_cdp(endpoint)
    while result["status"] != "ready":
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return result
        time.sleep(min(retry_interval_seconds, remaining))
        result = probe_cdp(endpoint)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://localhost:9222")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = wait_for_cdp(args.endpoint)
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
