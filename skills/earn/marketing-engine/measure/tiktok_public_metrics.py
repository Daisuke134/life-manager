#!/usr/bin/env python3
"""Read TikTok's native public post-list response in an isolated browser context."""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from collections import defaultdict
from typing import Any, Iterable


HANDLE = re.compile(r"^@[A-Za-z0-9._-]+$")
NATIVE_ID = re.compile(r"^[0-9]{10,30}$")
STAT_FIELDS = (
    "playCount",
    "diggCount",
    "commentCount",
    "shareCount",
    "collectCount",
)


def handle_from_url(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.netloc.lower() not in {
        "www.tiktok.com",
        "tiktok.com",
    }:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or not HANDLE.fullmatch(parts[0]) or parts[1] != "video":
        return None
    if not NATIVE_ID.fullmatch(parts[2]):
        return None
    return parts[0][1:]


def extract_wanted_items(
    payload: dict[str, Any],
    *,
    wanted_ids: set[str],
    expected_handle: str,
) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for item in payload.get("itemList") or []:
        native_id = str(item.get("id") or "")
        author = item.get("author") or {}
        handle = str(author.get("uniqueId") or "")
        stats = item.get("stats")
        if (
            native_id not in wanted_ids
            or handle.lower() != expected_handle.lower()
            or not isinstance(stats, dict)
        ):
            continue
        found[native_id] = {
            "native_post_id": native_id,
            "handle": handle,
            "native_url": f"https://www.tiktok.com/@{handle}/video/{native_id}",
            "stats": {field: stats.get(field) for field in STAT_FIELDS},
        }
    return found


def extract_profile_identity_items(
    payload: dict[str, Any], *, expected_handle: str
) -> list[dict[str, Any]]:
    """Return only stable fields needed for caption+time identity matching."""

    items: list[dict[str, Any]] = []
    for item in payload.get("itemList") or []:
        native_id = str(item.get("id") or "")
        author = item.get("author") or {}
        handle = str(author.get("uniqueId") or "")
        if not native_id or handle.lower() != expected_handle.lower():
            continue
        items.append(
            {
                "id": native_id,
                "webVideoUrl": f"https://www.tiktok.com/@{handle}/video/{native_id}",
                "text": str(item.get("desc") or ""),
                "createTime": item.get("createTime"),
                "authorMeta": {"name": handle},
            }
        )
    return items


async def _collect_profiles_async(
    handles: Iterable[str], *, cdp_url: str, wait_ms: int
) -> list[dict[str, Any]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("playwright is required for TikTok public identity") from exc

    wanted = sorted(
        {
            str(handle).lstrip("@")
            for handle in handles
            if HANDLE.fullmatch("@" + str(handle).lstrip("@"))
        }
    )
    if not wanted:
        return []
    found: dict[str, dict[str, Any]] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        context = await browser.new_context()
        try:
            page = await context.new_page()
            for handle in wanted:
                pending: set[asyncio.Task[Any]] = set()

                async def capture(response: Any, expected_handle: str = handle) -> None:
                    if "/api/post/item_list/" not in response.url or response.status != 200:
                        return
                    try:
                        payload = await response.json()
                    except Exception:
                        return
                    for item in extract_profile_identity_items(
                        payload, expected_handle=expected_handle
                    ):
                        found[str(item["id"])] = item

                def schedule(response: Any) -> None:
                    task = asyncio.create_task(capture(response))
                    pending.add(task)
                    task.add_done_callback(pending.discard)

                page.on("response", schedule)
                try:
                    await page.goto(
                        f"https://www.tiktok.com/@{handle}",
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                    await page.wait_for_timeout(wait_ms)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2_000)
                    if pending:
                        await asyncio.gather(*list(pending), return_exceptions=True)
                finally:
                    page.remove_listener("response", schedule)
        finally:
            await context.close()
            await browser.close()
    return list(found.values())


def collect_tiktok_public_profiles(
    handles: Iterable[str],
    *,
    cdp_url: str = "http://localhost:9222",
    wait_ms: int = 7_000,
) -> list[dict[str, Any]]:
    return asyncio.run(
        _collect_profiles_async(handles, cdp_url=cdp_url, wait_ms=wait_ms)
    )


async def _collect_async(
    publications: Iterable[dict[str, Any]],
    *,
    cdp_url: str,
    wait_ms: int,
) -> dict[str, dict[str, Any]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("playwright is required for TikTok public metrics") from exc

    groups: dict[str, set[str]] = defaultdict(set)
    for row in publications:
        native_id = str(row.get("native_post_id") or "")
        handle = handle_from_url(str(row.get("native_post_url") or ""))
        if handle and NATIVE_ID.fullmatch(native_id):
            groups[handle].add(native_id)

    found: dict[str, dict[str, Any]] = {}
    if not groups:
        return found

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        context = await browser.new_context()
        try:
            page = await context.new_page()
            for handle, wanted_ids in sorted(groups.items()):
                pending: set[asyncio.Task[Any]] = set()

                async def capture(response: Any) -> None:
                    if "/api/post/item_list/" not in response.url or response.status != 200:
                        return
                    try:
                        payload = await response.json()
                    except Exception:
                        return
                    found.update(
                        extract_wanted_items(
                            payload,
                            wanted_ids=wanted_ids,
                            expected_handle=handle,
                        )
                    )

                def schedule(response: Any) -> None:
                    task = asyncio.create_task(capture(response))
                    pending.add(task)
                    task.add_done_callback(pending.discard)

                page.on("response", schedule)
                try:
                    await page.goto(
                        f"https://www.tiktok.com/@{handle}",
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                    await page.wait_for_timeout(wait_ms)
                    if not wanted_ids.issubset(found):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(2_000)
                    if pending:
                        await asyncio.gather(*list(pending), return_exceptions=True)
                finally:
                    page.remove_listener("response", schedule)
        finally:
            await context.close()
            await browser.close()
    return found


def collect_tiktok_public_metrics(
    publications: Iterable[dict[str, Any]],
    *,
    cdp_url: str = "http://localhost:9222",
    wait_ms: int = 7_000,
) -> dict[str, dict[str, Any]]:
    return asyncio.run(
        _collect_async(publications, cdp_url=cdp_url, wait_ms=wait_ms)
    )
