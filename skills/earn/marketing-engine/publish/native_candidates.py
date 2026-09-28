#!/usr/bin/env python3
"""Read TikTok public profile responses into native publication candidates."""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import json
import os
import pathlib
import tempfile
from typing import Any


NATIVE_ID = re.compile(r"^[0-9]{10,30}$")


def _published_at(value: object) -> str | None:
    try:
        timestamp = int(value)
        parsed = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None
    return parsed.isoformat().replace("+00:00", "Z")


def extract_tiktok_candidates(payload: dict[str, Any], *, expected_handle: str) -> list[dict]:
    found: dict[str, dict] = {}
    for item in payload.get("itemList") or []:
        if not isinstance(item, dict):
            continue
        native_id = str(item.get("id") or "")
        author = item.get("author") or {}
        handle = str(author.get("uniqueId") or "") if isinstance(author, dict) else ""
        published_at = _published_at(item.get("createTime"))
        if (not NATIVE_ID.fullmatch(native_id) or
                handle.casefold() != expected_handle.casefold() or
                published_at is None):
            continue
        found[native_id] = {
            "native_handle": handle,
            "native_post_id": native_id,
            "native_post_url": f"https://www.tiktok.com/@{handle}/video/{native_id}",
            "caption": str(item.get("desc") or ""),
            "published_at": published_at,
        }
    return [found[key] for key in sorted(found)]


async def _collect_async(*, expected_handle: str, cdp_url: str,
                         wait_ms: int) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("playwright is required for TikTok native readback") from exc
    found: dict[str, dict] = {}
    observed = {"api_responses_observed": 0, "profile_items_observed": 0}
    pending: set[asyncio.Task[Any]] = set()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        context = await browser.new_context()
        page = await context.new_page()

        async def capture(response: Any) -> None:
            if "/api/post/item_list/" not in response.url or response.status != 200:
                return
            try:
                payload = await response.json()
            except Exception:
                return
            observed["api_responses_observed"] += 1
            items = payload.get("itemList") if isinstance(payload, dict) else None
            observed["profile_items_observed"] += len(items) if isinstance(items, list) else 0
            for row in extract_tiktok_candidates(payload, expected_handle=expected_handle):
                found[row["native_post_id"]] = row

        def schedule(response: Any) -> None:
            task = asyncio.create_task(capture(response))
            pending.add(task)
            task.add_done_callback(pending.discard)

        page.on("response", schedule)
        try:
            await page.goto(f"https://www.tiktok.com/@{expected_handle}",
                            wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(wait_ms)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2_000)
            if pending:
                await asyncio.gather(*list(pending), return_exceptions=True)
        finally:
            page.remove_listener("response", schedule)
            await context.close()
            await browser.close()
    return {**observed, "candidates": [found[key] for key in sorted(found)]}


def collect_tiktok_candidates(*, expected_handle: str,
                              cdp_url: str = "http://localhost:9222",
                              wait_ms: int = 7_000) -> dict:
    return asyncio.run(_collect_async(expected_handle=expected_handle,
                                      cdp_url=cdp_url, wait_ms=wait_ms))


def write_json_atomic(path: pathlib.Path, value: object) -> None:
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_candidates(path: pathlib.Path, rows: list[dict]) -> None:
    write_json_atomic(path, rows)
