#!/usr/bin/env python3
"""Hourly readback of one LINE Creators Market sticker item.

Leases the line-creators:dais browser, reads the item's official status and purchase URL, confirms
the public LINE STORE page once approved, and appends one JSON line to the state ledger. On
リジェクト (rejected) it also reads the real rejection message from the product's メッセージセンター
and, for that case only, hands off to ``line_sticker_resubmit`` -- the model decides a typed fix
from a closed action set and this module records whatever that returns. Every other status stays
read-only; a missing session is reported as needs_login, never as zero.

    creators_readback.py --item-file ~/.local/state/life-manager/line-sticker/set-002/creators-item.json
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

from playwright.async_api import Page, async_playwright

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import line_sticker_resubmit  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / "skills" / "browser" / "browser-guard.sh"
IDENTITY = "line-creators:dais"
LEDGER = Path.home() / ".local" / "state" / "life-manager" / "line-sticker" / "readback.jsonl"
STATUSES = ("編集中", "審査待ち", "審査中", "審査処理中", "承認", "リジェクト", "販売中", "販売停止", "販売開始待ち")
MESSAGE_FOOTER = "このメッセージに返信することはできません。"


async def _fetch_rejection_message(page: Page, item: dict) -> str | None:
    creator_base = item["url"].split("/sticker/")[0]
    await page.goto(f"{creator_base}/message/", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(2000)
    title_ja = item.get("title_ja") or ""
    rows = await page.evaluate(
        """(title) => [...document.querySelectorAll('a[href*="/message/detail/"]')]
            .filter(a => !title || a.innerText.includes(title))
            .map(a => a.getAttribute('href'))""",
        title_ja,
    )
    if not rows:
        return None
    await page.goto(f"{creator_base}{rows[0]}", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(1500)
    body = await page.inner_text("body")
    match = re.search(r"\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}\n(.*?)" + re.escape(MESSAGE_FOOTER), body, re.S)
    return match.group(1).strip() if match else None


async def read(cdp: str, item: dict) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp)
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(item["url"], wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            if "access.line.me" in page.url:
                return {"status": "needs_login"}
            body = await page.inner_text("body")
            after = body[body.find("ステータス"):]
            status = next((s for s in STATUSES if after[:60].find(s) >= 0), "unknown")
            match = re.search(r"https://line\.me/S/sticker/\d+", body) or re.search(r"https://store\.line\.me/stickershop/product/\d+", body)
            result = {"status": status, "purchase_url": match.group(0) if match else None,
                      "reason": after[:300] if status == "リジェクト" else None}
            if status == "リジェクト":
                result["rejection_message"] = await _fetch_rejection_message(page, item)
                result["rejected_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if result["purchase_url"]:
                store = f"https://store.line.me/stickershop/product/{item['product_id']}/ja"
                await page.goto(store, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)
                text = await page.inner_text("body")
                result["store_url"] = store
                result["store_public"] = item["title_ja"] in text
            return result
        finally:
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--item-file", type=Path, required=True)
    args = parser.parse_args()
    item = json.loads(args.item_file.read_text())
    acquired = subprocess.run(["bash", str(GUARD), "acquire", IDENTITY], capture_output=True, text=True)
    if acquired.returncode != 0:
        # BUSY or unreachable is a skipped cycle, not a reading.
        result = {"status": "browser_unavailable", "detail": acquired.stderr.strip()[-200:]}
    else:
        try:
            result = asyncio.run(read(acquired.stdout.strip().splitlines()[-1], item))
        finally:
            subprocess.run(["bash", str(GUARD), "release", IDENTITY], capture_output=True)
    row = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "product_id": item["product_id"], **result}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as ledger:
        ledger.write(json.dumps(row, ensure_ascii=False) + "\n")
    if result.get("status") != item.get("state_observed"):
        item["state_observed"] = result.get("status")
        item.update({k: v for k, v in result.items()
                     if k in ("purchase_url", "store_url", "store_public", "rejection_message", "rejected_at") and v})
        args.item_file.write_text(json.dumps(item, ensure_ascii=False, indent=1))
    if result.get("status") == "リジェクト" and result.get("rejection_message"):
        fixed = line_sticker_resubmit.resubmit(args.item_file.parent, item, result["rejection_message"])
        if fixed != item:
            args.item_file.write_text(json.dumps(fixed, ensure_ascii=False, indent=1))
            row["resubmit"] = {k: v for k, v in fixed.items()
                               if k in ("resubmit_decision", "resubmit_decision_reason", "state",
                                        "auto_resubmit_count", "resubmit_block_reason")}
    print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
