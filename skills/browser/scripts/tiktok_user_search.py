#!/usr/bin/env python3
"""Read TikTok's official user-search profile URLs under a guarded identity."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import cdp


READBACK = r"""
(() => ({
  url: location.href,
  title: document.title,
  profiles: [...new Set([...document.querySelectorAll('a[href*="/@"]')]
    .map(node => node.href).filter(Boolean))].slice(0, 50)
}))()
"""


def _profile_urls(values: object) -> list[str]:
    result = []
    for value in values if isinstance(values, list) else []:
        if not isinstance(value, str):
            continue
        parsed = urlparse(value)
        if parsed.hostname not in {"tiktok.com", "www.tiktok.com"}:
            continue
        if not parsed.path.startswith("/@"):
            continue
        if value not in result:
            result.append(value)
    return result


def _write(output: Path, value: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=output.name + ".", suffix=".tmp", dir=output.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def search_users(query: str, owner: str, output: Path, *, cdp_client=cdp,
                 wait=time.sleep, attempts: int = 20) -> dict:
    url = "https://www.tiktok.com/search/user?q=" + quote(query) + "&lang=ja-JP"
    target = cdp_client.new_target(url, owner)
    try:
        observed = None
        for attempt in range(attempts):
            observed = cdp_client.evaluate(target, READBACK)
            if not isinstance(observed, dict) or "__error__" in observed:
                raise RuntimeError(f"TikTok user search readback failed: {observed}")
            profiles = _profile_urls(observed.get("profiles"))
            if profiles or attempt == attempts - 1:
                result = {
                    "version": 1,
                    "provider": "tiktok.com",
                    "query": query,
                    "url": observed.get("url"),
                    "title": observed.get("title"),
                    "profiles": profiles,
                    "complete": True,
                }
                _write(output.resolve(), result)
                return result
            wait(0.5)
        raise AssertionError("unreachable")
    finally:
        cdp_client.close_target(target, owner)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--attempts", type=int, default=20)
    args = parser.parse_args()
    if not args.query.strip() or not 1 <= args.attempts <= 120:
        raise SystemExit("query required and attempts must be 1..120")
    result = search_users(args.query, args.owner, args.output, attempts=args.attempts)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
