#!/usr/bin/env python3
"""threads_publish.py -- post the sell loop's video + caption to Threads over the leased CloakBrowser.

Same lease contract as browser_reel_publish (skills/browser/browser-guard.sh). The Threads profile
@<handle> was created from the Instagram session of the same browser identity (2026-10-09,
"Instagramでログイン"), so no separate login exists. Unlike Instagram, a Threads post's links are
clickable, so the caption carries the purchase URL.

Lesson from the Instagram lane (2026-10-09): navigating the posting tab away while the upload is
still running cancels it. The composer tab is left alone until its dialog closes; the profile is
read in a separate tab.
"""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
GUARD = REPO_ROOT / "skills/browser/browser-guard.sh"
UPLOAD_SECONDS = 300
RECONCILE_SECONDS = 120


def post_codes(html: str, handle: str) -> set[str]:
    return set(re.findall(rf'/@{re.escape(handle)}/post/([A-Za-z0-9_-]+)(?=["/?#])', html))


def new_post_code(before: set[str], after: set[str]) -> str | None:
    fresh = after - before
    return next(iter(fresh)) if len(fresh) == 1 else None


def _profile_codes(context, handle: str) -> set[str]:
    page = context.new_page()
    try:
        page.goto(f"https://www.threads.com/@{handle}", timeout=60000)
        page.wait_for_timeout(5000)
        return post_codes(page.content(), handle)
    finally:
        page.close()


def read_post_codes(handle: str, browser_identity: str) -> dict:
    """Official readback for the fence reconciler: every post code on the profile."""
    acquired = subprocess.run(["bash", str(GUARD), "acquire", browser_identity], capture_output=True, text=True)
    if acquired.returncode != 0:
        return {"ok": False, "reason": "browser_unavailable"}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(acquired.stdout.strip().splitlines()[-1])
            return {"ok": True, "codes": _profile_codes(browser.contexts[0], handle)}
    except Exception as exc:  # noqa: BLE001 -- any failure is inconclusive
        return {"ok": False, "reason": f"threads_readback_failed:{type(exc).__name__}"}
    finally:
        subprocess.run(["bash", str(GUARD), "release", browser_identity], capture_output=True)


def publish(*, video: Path, caption_file: Path, handle: str, browser_identity: str, live: bool) -> dict:
    receipt = {"handle": handle, "live": live, "reached": "start", "outcome": "failed", "post_url": None}
    acquired = subprocess.run(["bash", str(GUARD), "acquire", browser_identity], capture_output=True, text=True)
    if acquired.returncode != 0:
        return {**receipt, "error": "browser_unavailable"}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            context = playwright.chromium.connect_over_cdp(acquired.stdout.strip().splitlines()[-1]).contexts[0]
            before = _profile_codes(context, handle)
            page = context.new_page()
            try:
                page.goto("https://www.threads.com/", timeout=60000)
                page.wait_for_timeout(4000)
                page.get_by_text("最近どう？", exact=True).first.click(timeout=15000)
                dialog = page.locator("div[role=dialog]").last
                dialog.locator("input[type=file]").set_input_files(str(video))
                receipt["reached"] = "media"
                dialog.locator("[contenteditable=true]").first.click()
                page.keyboard.insert_text(caption_file.read_text(encoding="utf-8"))
                receipt["reached"] = "caption"
                if not live:
                    return {**receipt, "outcome": "dry_run"}
                dialog.get_by_role("button", name="投稿", exact=True).click(timeout=60000)
                receipt["reached"] = "shared"
                deadline = time.monotonic() + UPLOAD_SECONDS
                while time.monotonic() < deadline and page.locator("div[role=dialog]").count():
                    page.wait_for_timeout(3000)
            finally:
                page.close()
            deadline = time.monotonic() + RECONCILE_SECONDS
            while time.monotonic() < deadline:
                code = new_post_code(before, _profile_codes(context, handle))
                if code:
                    return {**receipt, "reached": "published", "outcome": "published",
                            "post_url": f"https://www.threads.com/@{handle}/post/{code}"}
                time.sleep(15)
            return {**receipt, "reached": "shared-unconfirmed"}
    except Exception as exc:  # noqa: BLE001 -- report, never raise past the receipt
        return {**receipt, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
    finally:
        subprocess.run(["bash", str(GUARD), "release", browser_identity], capture_output=True)
