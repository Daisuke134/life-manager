#!/usr/bin/env python3
"""Model-judged fix + re-request for a LINE Creators Market リジェクト (rejected) sticker item.

Verified by hand against item 48067450 (set-002, message 2026-10-06 14:21): the message center
names the real cause (e.g. a 特集企画 feature whose stamp-count condition is no longer met), the
primary fixes the setting on the product's ``/update`` page, and re-requests review through the
same agree-checkbox / OK flow ``line_sticker_submit._request_review`` already drives. The MODEL
decides which fix applies -- via ``runtime/agent-runner/agent_runner.py``, the same pattern as
``line_sticker_planner.py`` -- from a small closed action set; this module only executes the typed
action it returns. Capped at 2 automatic re-requests per product (``auto_resubmit_count`` in
creators-item.json); re-request is an external effect, so success is recorded only after a status
readback shows 審査待ち or 審査中, and a daily request-counter reading at or above 30/30 on the
confirm modal stops the click before it is sent.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import re
import subprocess
from pathlib import Path

from playwright.async_api import Page

from line_sticker_notify import notify
from line_sticker_planner import _run_agent  # noqa: E402  (reuse the agent_runner wrapper)
from line_sticker_submit import BASE, GUARD, IDENTITY, NeedsLogin, _goto, _retitle, _tag_all  # noqa: E402

HERE = Path(__file__).resolve().parent
MAX_AUTO_RESUBMITS = 2
DAILY_COUNTER_RE = re.compile(r"(\d+)\s*/\s*30")


def _build_decide_prompt(rejection_message: str, item: dict, listing: dict) -> str:
    return f"""あなたはLINE Creators Marketで動くスタンプを運営するエージェント。以下のスタンプが
リジェクト（審査却下）された。メッセージセンターの原文はこれ:

{rejection_message}

対象アイテム: product_id={item.get('product_id')}, title_ja={listing.get('title', {}).get('ja')}

次の4つの選択肢から、原因に最も合う修正アクションを1つだけ選ぶ:
- leave_features: 特集企画（キャンペーン）の参加条件を満たせていない場合（例: 画像枚数不足、条件不一致）。
  商品編集ページの特集企画設定を「参加しない」に変更してから再リクエストする。
- retitle: タイトルが原因（例: 既存タイトルと重複、ガイドライン違反のタイトル文言）の場合。
  タイトルにキャラクター名を付記してから再リクエストする。
- retag: タグが原因（例: 不適切なタグ、ガイドライン外のタグ）の場合。タグを選び直してから再リクエストする。
- cannot_fix: 上記のどれにも当てはまらない、または画像内容そのもの（絵柄・動き）の修正が必要で
  自動修正できない場合。この場合は再リクエストしない。

JSON Schemaに厳密に従ったJSONだけを返す。reasonには日本語で短く根拠を書く。"""


def decide_action(set_dir: Path, rejection_message: str, item: dict, listing: dict) -> dict:
    prompt = _build_decide_prompt(rejection_message, item, listing)
    evidence_dir = set_dir / f".resubmit-{item.get('product_id', 'x')}-{item.get('auto_resubmit_count', 0)}"
    return _run_agent(prompt=prompt, schema=HERE / "schemas/resubmit-action.schema.json",
                       evidence_dir=evidence_dir, task_label=f"line-sticker-resubmit-{set_dir.name}")


async def _leave_features(page: Page, item: dict) -> None:
    await _goto(page, f"{BASE}/sticker/{item['product_id']}/update")
    # 参加しない has no value attribute (DOM .value reads "on", CSS [value='on'] matches nothing).
    radio = page.locator("input[type=radio]:not([value])")
    await radio.first.evaluate("e => e.click()")  # feature radios are not wrapped in a <label>
    assert await radio.first.is_checked()
    await page.evaluate("document.querySelector('input[data-test=btn-save]').click()")
    ok_button = page.locator("button:visible", has_text="OK").last
    await ok_button.wait_for(timeout=15000)
    await ok_button.click()
    await page.wait_for_timeout(1000)


async def _retitle_item(page: Page, item: dict, listing: dict) -> dict:
    retitled = _retitle(listing) or listing
    await _goto(page, f"{BASE}/sticker/{item['product_id']}/update")
    await page.fill('input[name="meta[en][title]"]', retitled["title"]["en"])
    await page.fill('input[name="meta[ja][title]"]', retitled["title"]["ja"])
    await page.evaluate("document.querySelector('input[data-test=btn-save]').click()")
    ok_button = page.locator("button:visible", has_text="OK").last
    await ok_button.wait_for(timeout=15000)
    await ok_button.click()
    await page.wait_for_timeout(1000)
    return retitled


async def _retag_item(page: Page, item: dict, set_dir: Path) -> None:
    from line_sticker_planner import selector  # local import: avoids a hard dep for the common case

    plan = json.loads((set_dir / "plan.json").read_text())
    selection = selector(set_dir, plan)
    (set_dir / "select.json").write_text(json.dumps(selection, ensure_ascii=False, indent=1))
    tags = {row["sticker_number"]: row["tags"] for row in selection["tags"]}
    (set_dir / "tags.json").write_text(json.dumps(tags, ensure_ascii=False, indent=1))
    await _tag_all(page, item, tags)


async def _request_review_with_cap_guard(page: Page, item: dict) -> dict:
    """Same agree/OK flow as ``line_sticker_submit._request_review``, plus a daily-counter fence."""
    await _goto(page, f"{BASE}/sticker/{item['product_id']}")
    await page.locator("a:visible", has_text="リクエスト").first.click(timeout=15000)
    await page.wait_for_timeout(500)
    body = await page.inner_text("body")
    counter = DAILY_COUNTER_RE.search(body)
    if counter and int(counter.group(1)) >= 30:
        return dict(item, state="resubmit_blocked", resubmit_block_reason="daily_request_cap_30")
    agree = page.get_by_text("同意します", exact=True)
    await agree.click()
    await page.wait_for_timeout(300)
    ok_buttons = page.get_by_role("button", name="OK", exact=True)
    visible = [button for button in await ok_buttons.all() if await button.is_visible() and await button.is_enabled()]
    await visible[-1].click()
    await page.wait_for_timeout(2000)
    body = await page.inner_text("body")
    item = dict(item)
    if "審査待ち" in body or "審査中" in body:
        item["state"] = "review_requested"
        item["review_requested_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        item["state_observed"] = "審査待ち" if "審査待ち" in body else "審査中"
    return item


async def _drive(cdp: str, set_dir: Path, item: dict, action: dict, listing: dict) -> dict:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp)
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            name = action["action"]
            if name == "leave_features":
                await _leave_features(page, item)
            elif name == "retitle":
                retitled = await _retitle_item(page, item, listing)
                (set_dir / "listing.json").write_text(json.dumps(retitled, ensure_ascii=False, indent=1))
            elif name == "retag":
                await _retag_item(page, item, set_dir)
            return await _request_review_with_cap_guard(page, item)
        finally:
            await page.close()


def resubmit(set_dir: Path, item: dict, rejection_message: str) -> dict:
    """Decide + execute exactly one fix, then re-request review. Returns the (possibly unchanged) item."""
    count = item.get("auto_resubmit_count", 0)
    listing = json.loads((set_dir / "listing.json").read_text()) if (set_dir / "listing.json").exists() else {}
    if count >= MAX_AUTO_RESUBMITS:
        item = dict(item, resubmit_decision="cannot_fix", resubmit_decision_reason="auto_resubmit_cap_reached")
        notify(set_dir, {"status": "cannot_fix", "product_id": item.get("product_id"), "reason": item["resubmit_decision_reason"]})
        return item

    action = decide_action(set_dir, rejection_message, item, listing)
    item = dict(item, resubmit_decision=action["action"], resubmit_decision_reason=action.get("reason"))
    if action["action"] == "cannot_fix":
        notify(set_dir, {"status": "cannot_fix", "product_id": item.get("product_id"), "reason": action.get("reason")})
        return item

    acquired = subprocess.run(["bash", str(GUARD), "acquire", IDENTITY], capture_output=True, text=True)
    if acquired.returncode != 0:
        return item  # BUSY/unreachable: next hourly wake retries
    cdp = acquired.stdout.strip().splitlines()[-1]
    try:
        result = asyncio.run(_drive(cdp, set_dir, item, action, listing))
    except NeedsLogin:
        return item
    finally:
        subprocess.run(["bash", str(GUARD), "release", IDENTITY], capture_output=True)

    result["resubmit_decision"] = action["action"]
    result["resubmit_decision_reason"] = action.get("reason")
    if result.get("state") == "review_requested":
        result["auto_resubmit_count"] = count + 1
        result["last_auto_resubmit_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return result
