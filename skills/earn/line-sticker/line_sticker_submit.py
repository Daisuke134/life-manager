#!/usr/bin/env python3
"""Browser adapter for LINE Creators Market submission (create item, images, tags, request review).

Verified manually against item 48067450 (set-002); this module automates the same steps. Every
stage writes creators-item.json so a crashed or BUSY wake resumes from the right sub-step instead
of creating a second item. If the lease is BUSY (exit 9) or the item page redirects to
access.line.me, the stage returns unchanged (state stays the same, the wake retries next hour).
"""
from __future__ import annotations

import asyncio
import datetime
import re
import unicodedata
import json
import subprocess
import sys
from pathlib import Path

from playwright.async_api import Page, async_playwright

REPO_ROOT = Path(__file__).resolve().parents[3]
GUARD = REPO_ROOT / "skills/browser/browser-guard.sh"
IDENTITY = "line-creators:dais"
BASE = "https://creator.line.me/my/cCX4POFknN2lhLJE"
BUSY_EXIT = 9


class NeedsLogin(RuntimeError):
    pass


async def _close_modals(page: Page) -> None:
    for _ in range(6):
        closed = False
        for check in await page.locator("input[name=check]:visible").all():
            await check.check()
            closed = True
        for button in await page.get_by_text("閉じる", exact=True).all():
            if await button.is_visible():
                await button.click()
                closed = True
        if not closed:
            return
        await page.wait_for_timeout(300)


async def _goto(page: Page, url: str) -> None:
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(1500)
    if "access.line.me" in page.url:
        raise NeedsLogin(url)
    await _close_modals(page)


def _is_title_taken(errors: list[str]) -> bool:
    return any("既に存在するタイトル" in e or "title already exists" in e.lower() for e in errors)


# Creators Market allows 40 units and counts a full-width character as 2 (measured live 2026-10-07:
# a 35-character title with 16 full-width characters was rejected as over 40).
TITLE_MAX = 38


def _title_units(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W", "A") else 1 for ch in text)


# Description limit, same width counting (160 units; measured live 2026-10-07 set-007).
DESC_MAX = 158
LIMIT_TITLE = 40


def _fit(text: str, limit: int) -> str:
    if _title_units(text) <= limit:
        return text
    cut = ""
    for ch in text:
        if _title_units(cut + ch) > limit:
            break
        cut += ch
    # Prefer ending on a sentence, else a word boundary.
    for marks in ("。.!！?？", " 、,"):
        idx = max(cut.rfind(m) for m in marks)
        if idx >= len(cut) // 2:
            return cut[: idx + 1].rstrip(" 、,&-:;・")
    return cut.rstrip(" 、,&-:;・")


_ASCII_PUNCT = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
                               "\u2013": "-", "\u2014": "-", "\u2026": "..."})


def _clean(text: str) -> str:
    """Creators Market rejects some characters (利用できない文字; live 2026-10-07 set-008 had '’').
    Use ASCII punctuation and drop emoji/pictographs the form refuses."""
    text = text.translate(_ASCII_PUNCT)
    return "".join(ch for ch in text if not (unicodedata.category(ch) == "So" or ord(ch) >= 0x1F000)).strip()


def _fit_listing(listing: dict) -> dict:
    """Clamp model-written copy to Creators Market's character set and width-counted limits."""
    titles = {k: _fit(_clean(v), LIMIT_TITLE) for k, v in listing["title"].items()}
    descs = {k: _fit(_clean(v), DESC_MAX) for k, v in listing.get("description", {}).items()}
    if titles == listing["title"] and descs == listing.get("description", {}):
        return listing
    return dict(listing, title=titles, description=descs)


_VOL_RE = re.compile(r"\s*vol\.(\d+)$")


def _numbered(listing: dict) -> dict:
    """Make a taken title unique with a "vol.N" suffix (a normal sequel marker on the store), counting up
    from an existing one, clamped so the suffix survives the width limit."""
    titles = {}
    for lang, title in listing["title"].items():
        match = _VOL_RE.search(title)
        base, number = (title[:match.start()], int(match.group(1)) + 1) if match else (title, 2)
        suffix = f" vol.{number}"
        limit = TITLE_MAX - _title_units(suffix)
        # Keep a trailing bracketed mark such as 【文字入り】 / (with text) whole; cut the words before it.
        mark = re.search(r"(【[^】]*】|\([^)]*\))$", base)
        if mark and _title_units(base) > limit:
            head, tail = base[:mark.start()].rstrip(), mark.group(1)
            gap = " " if base[mark.start() - 1:mark.start()] == " " else ""
            base = _fit(head, max(0, limit - _title_units(tail) - len(gap))).rstrip() + gap + tail
        titles[lang] = _fit(base, limit) + suffix
    return dict(listing, title=titles)


def _retitle(listing: dict) -> dict | None:
    name = listing.get("character_name") or ""
    if not name:
        # set-015 (2026-10-08): no character name meant no retry at all, and the factory stalled on a
        # duplicate title; a numbered title always works.
        return _numbered(listing)
    fallback = {"en": f"{name} Stickers", "ja": f"{name}のスタンプ"}
    titles = {}
    for lang, title in listing["title"].items():
        candidate = f"{title} ({name})"
        titles[lang] = candidate if _title_units(candidate) <= TITLE_MAX else fallback.get(lang, name)
    return dict(listing, title=titles)


async def _visible_errors(page) -> list[str]:
    return await page.evaluate("""() => [...document.querySelectorAll("[class*=rror], .mdTxtError")]
        .filter(e => e.offsetParent && e.innerText.trim()).map(e => e.innerText.trim().slice(0, 120))""")


class TitleTaken(RuntimeError):
    """Creators Market titles are unique per language across all creators."""


def _sticker_type_value(listing: dict) -> str:
    """Creators Market's sticker_type radio value (confirmed live 2026-10-08: static=スタンプ,
    animation=アニメーションスタンプ)."""
    return "static" if listing.get("type") == "static_sticker" else "animation"


def _image_count_value(listing_or_item: dict) -> str:
    return str(listing_or_item.get("count") or listing_or_item.get("sticker_count") or 24)


async def _create_item(page: Page, listing: dict, selection: dict) -> dict:
    listing = _fit_listing(listing)
    saves: list = []
    page.on("response", lambda r: saves.append(r) if r.request.method == "POST" and r.url.endswith("/api/v2/sticker") else None)
    await _goto(page, f"{BASE}/sticker/create")
    radio = page.locator(f"input[name=sticker_type][value={_sticker_type_value(listing)}]")
    await radio.locator("xpath=ancestor::label[1]").click()
    assert await radio.is_checked()
    await page.fill('input[name="meta[en][title]"]', listing["title"]["en"])
    await page.fill('textarea[name="meta[en][description]"]', listing["description"]["en"])
    await page.locator("select").first.select_option("ja")
    await page.get_by_role("button", name="追加", exact=True).click()
    await page.wait_for_timeout(500)
    await page.fill('input[name="meta[ja][title]"]', listing["title"]["ja"])
    await page.fill('textarea[name="meta[ja][description]"]', listing["description"]["ja"])
    await page.fill("input[name=copyright]", listing.get("copyright", "anicca"))
    ai_radio = page.locator("input[name=is_ai_generated][value=true]")
    await ai_radio.locator("xpath=ancestor::label[1]").click()
    assert await ai_radio.is_checked()
    auto_release = page.locator("input[name=is_auto_release][value=true]")
    await auto_release.locator("xpath=ancestor::label[1]").click()
    assert await auto_release.is_checked()
    await _select_taste_character_campaign(page, selection)
    await page.evaluate("document.querySelector('input[type=submit].mdBtn').click()")
    # The page keeps several hidden confirm dialogs; only the visible "OK" belongs to this save.
    ok_button = page.locator("button:visible", has_text="OK").last
    try:
        await ok_button.wait_for(timeout=15000)
    except Exception as exc:
        # No confirm dialog means client-side validation stopped the save; nothing was sent.
        errors = await _visible_errors(page)
        if _is_title_taken(errors):
            raise TitleTaken("; ".join(errors)) from exc
        raise RuntimeError(f"save_dialog_missing errors={errors[:5]}") from exc
    await ok_button.click()
    # "/sticker/*" also matches the create page itself; only a numeric item id proves the save.
    try:
        await page.wait_for_url(re.compile(re.escape(BASE) + r"/sticker/\d+/?$"), timeout=30000)
    except Exception as exc:
        if saves and saves[-1].status >= 400:
            detail = (await saves[-1].text())[:300]
            if "title already exists" in detail:
                raise TitleTaken(detail) from exc
            raise RuntimeError(f"create_rejected status={saves[-1].status} detail={detail}") from exc
        errors = await _visible_errors(page)
        raise RuntimeError(f"create_not_saved url={page.url} errors={errors[:5]}") from exc
    product_id = page.url.rstrip("/").rsplit("/", 1)[-1]
    return {
        "product_id": product_id, "url": page.url,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "state": "metadata_saved", "title_ja": listing["title"]["ja"],
        "price_jpy": listing.get("price_jpy", 250), "sticker_count": listing.get("count", 24),
    }


async def _select_taste_character_campaign(page: Page, selection: dict) -> None:
    selects = page.locator("select")
    count = await selects.count()
    for index in range(count):
        select = selects.nth(index)
        options = await select.locator("option").all()
        values = {await option.get_attribute("value") for option in options}
        if selection.get("taste_id") in values:
            await select.select_option(selection["taste_id"])
        elif selection.get("character_category_id") in values:
            await select.select_option(selection["character_category_id"])
    campaign_value = selection.get("campaign_value")
    # 参加しない has no value attribute (DOM .value reads "on", CSS [value='on'] matches nothing).
    campaign_radio = page.locator(f"input[type=radio][value='{campaign_value}']" if campaign_value
                                  else "input[type=radio]:not([value])")
    if await campaign_radio.count():
        await campaign_radio.first.evaluate("e => e.click()")  # feature radios are not wrapped in a <label>


async def _upload_images(page: Page, item: dict, package_dir: Path) -> None:
    await _goto(page, f"{BASE}/sticker/{item['product_id']}/image")
    await page.select_option("#number_of_images", _image_count_value(item))
    ok_button = page.locator("button:visible", has_text="OK").last
    try:
        await ok_button.wait_for(timeout=15000)
    except Exception as exc:
        # No confirm dialog means client-side validation stopped the save; nothing was sent.
        errors = await _visible_errors(page)
        if _is_title_taken(errors):
            raise TitleTaken("; ".join(errors)) from exc
        raise RuntimeError(f"save_dialog_missing errors={errors[:5]}") from exc
    await ok_button.click()
    await page.wait_for_timeout(500)
    await page.locator("input[type=file]").first.set_input_files(str(package_dir / "submission.zip"))
    await page.wait_for_timeout(20000)
    body = await page.inner_text("body")
    # Rejected slots show an English "Error" badge (live 2026-10-08); "未登録の画像" means some
    # images did not register. Either way the upload is not done.
    if "エラー" in body or re.search(r"\bError\b", body) or "未登録の画像" in body:
        raise RuntimeError(f"image_upload_error:{body[:300]}")


async def _tag_all(page: Page, item: dict, tags: dict) -> None:
    for number in range(1, int(_image_count_value(item)) + 1):
        sticker_id = f"{number:02d}"
        wanted = set(tags.get(sticker_id, []))
        await _goto(page, f"{BASE}/sticker/{item['product_id']}/tag#/{sticker_id}")
        await page.reload(wait_until="domcontentloaded")
        await page.wait_for_timeout(3500)
        for label in await page.locator("label").all():
            text = (await label.inner_text()).strip()
            name = text.rsplit("(", 1)[0].strip() if "(" in text else text
            if name in wanted:
                checkbox = label.locator("input[type=checkbox]")
                if await checkbox.count() and not await checkbox.is_checked():
                    # A pointer click timed out on every wake for 48156132 (2026-10-08, 16-image tag page);
                    # the DOM click toggles and persists the tag (verified with a reload).
                    await label.evaluate("e => e.click()")
        await page.wait_for_timeout(1500)


IN_REVIEW = ("審査待ち", "審査中", "審査処理中")


def _mark_requested(item: dict, observed: str) -> dict:
    return dict(item, state="review_requested", state_observed=observed,
                review_requested_at=datetime.datetime.now(datetime.timezone.utc).isoformat())


async def _review_status(page: Page) -> str | None:
    body = await page.inner_text("body")
    status = body[body.find("ステータス"):][:40]
    return next((s for s in IN_REVIEW if s in status), None)


async def _request_review(page: Page, item: dict) -> dict:
    await _goto(page, f"{BASE}/sticker/{item['product_id']}")
    # Idempotent: a request that already went through (e.g. readback missed it last wake) is done.
    already = await _review_status(page)
    if already:
        return _mark_requested(item, already)
    await page.locator("a:visible", has_text="リクエスト").first.click(timeout=15000)  # <a> without href has no link role
    await page.wait_for_timeout(500)
    agree = page.get_by_text("同意します", exact=True)
    await agree.click()
    await page.wait_for_timeout(300)
    ok_buttons = page.get_by_role("button", name="OK", exact=True)
    visible = [button for button in await ok_buttons.all() if await button.is_visible() and await button.is_enabled()]
    await visible[-1].click()
    # The status flips a few seconds after OK (2s missed it live 2026-10-07); reload and poll.
    for _ in range(10):
        await page.wait_for_timeout(2000)
        await _goto(page, f"{BASE}/sticker/{item['product_id']}")
        observed = await _review_status(page)
        if observed:
            return _mark_requested(item, observed)
    return dict(item)


async def _idempotent_step(step, item: dict, next_state: str) -> dict:
    """Run an overwrite-only step (image upload, tagging). A failure here cannot leave a partial
    external effect worth fencing, so keep the state and let the next launch redo it instead of
    crashing into an unknown-effect fence (a fleet apply restarted the browser mid-tagging live
    2026-10-07 10:00Z)."""
    try:
        await step()
    except Exception as exc:  # noqa: BLE001 - any browser failure means "redo next launch"
        print(json.dumps({"retry_step": next_state, "error": str(exc)[:300]}, ensure_ascii=False), file=sys.stderr)
        return dict(item)
    return dict(item, state=next_state)


MAX_TITLE_ATTEMPTS = 6


def _title_attempts(listing: dict):
    """Titles to try in order when Creators Market reports one as taken: the planned one, then its
    vol.2 / vol.3 numbered forms (they keep what the set is: 【文字入り】, the theme), and only
    then the character-name-led title, which throws the wording away (set-015: it became
    "Stardust Otterのスタンプ", an on-sale item of ours, and giving up there stalled the factory)."""
    yield listing
    current = listing
    count = 1
    while count < MAX_TITLE_ATTEMPTS - 1:
        current = _numbered(current)
        count += 1
        yield current
    if listing.get("character_name"):
        yield _retitle(listing)


async def _drive(cdp: str, item: dict, listing: dict, tags: dict, package_dir: Path, selection: dict) -> dict:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp)
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            if not item:
                last: TitleTaken | None = None
                for candidate in _title_attempts(listing):
                    try:
                        return await _create_item(page, candidate, selection)
                    except TitleTaken as exc:
                        last = exc
                raise last
            if item.get("state") == "metadata_saved":
                return await _idempotent_step(lambda: _upload_images(page, item, package_dir), item, "images_uploaded")
            if item.get("state") == "images_uploaded":
                return await _idempotent_step(lambda: _tag_all(page, item, tags), item, "tagged")
            if item.get("state") == "tagged":
                return await _request_review(page, item)
            return item
        finally:
            try:
                await page.close()
            except Exception:  # noqa: BLE001 - the browser may already be gone
                pass


def submit(set_dir: Path, item: dict, listing: dict, tags: dict) -> dict:
    """One browser sub-step per call (resumable via item['state']); BUSY/needs_login leaves item unchanged."""
    package_dir = set_dir / "package"
    selection = json.loads((set_dir / "select.json").read_text()) if (set_dir / "select.json").exists() else {}
    acquired = subprocess.run(["bash", str(GUARD), "acquire", IDENTITY], capture_output=True, text=True)
    if acquired.returncode != 0:
        return item
    cdp = acquired.stdout.strip().splitlines()[-1]
    try:
        return asyncio.run(_drive(cdp, item, listing, tags, package_dir, selection))
    except NeedsLogin:
        return item
    finally:
        subprocess.run(["bash", str(GUARD), "release", IDENTITY], capture_output=True)


if __name__ == "__main__":
    sys.exit(0)
