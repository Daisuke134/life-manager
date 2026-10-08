#!/usr/bin/env python3
"""Daily read-only scan of LINE Creators Market's open 特集 (feature-campaign) list.

Top creators ride these feature campaigns for free store/LINE-official exposure; the factory never
joined because the selector prompt hardcoded "no participation". This script is the read half: it
visits one tracked item's edit page (the feature radios there are account-wide, not per-item --
measured live 2026-10-08), reads the single shared radio group whose "on" option is 参加しない
(non-participation), matches each remaining option's title to the matching お知らせ (announcement)
list entry, and copies that article's body text verbatim as ``conditions`` -- parsed for the model
to judge in ``line_sticker_planner.selector``, not here. Self-gates to once per day like
``sales_readback.py``; every other hourly wake is a fast no-op.

    features_readback.py
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

REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / "skills" / "browser" / "browser-guard.sh"
IDENTITY = "line-creators:dais"
CREATOR_BASE = "https://creator.line.me/my/cCX4POFknN2lhLJE"
STATE_ROOT_DEFAULT = Path.home() / ".local/state/life-manager" / "line-sticker"
JST = datetime.timezone(datetime.timedelta(hours=9))
NON_PARTICIPATION_VALUE = "on"
TITLE_RE = re.compile(r"「([^」]+)」")
PERIOD_RE = re.compile(r"受付\s*([0-9/〜\-]+)")
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})")


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _deadline_from_period(period: str, today: datetime.date) -> str | None:
    """The period text's last M/D is the 受付 (reception) end date; roll to next year if it would
    otherwise read as already past (a Jan deadline read in December, for example)."""
    dates = DATE_RE.findall(period)
    if not dates:
        return None
    month, day = (int(part) for part in dates[-1])
    try:
        candidate = datetime.date(today.year, month, day)
    except ValueError:
        return None
    if candidate < today:
        candidate = datetime.date(today.year + 1, month, day)
    return candidate.isoformat()


def parse_feature_radio(value: str, label: str, today: datetime.date) -> dict | None:
    """One radio option from the shared campaign group -> an open-feature record, or None for the
    参加しない option and any option whose label does not name a 「タイトル」 (unparseable)."""
    if value == NON_PARTICIPATION_VALUE:
        return None
    title_match = TITLE_RE.search(label)
    if not title_match:
        return None
    period_match = PERIOD_RE.search(label)
    deadline = _deadline_from_period(period_match.group(1), today) if period_match else None
    return {"value": value, "title": title_match.group(1), "deadline": deadline}


def match_announce_link(title: str, links: list[dict]) -> str | None:
    """Find the お知らせ list entry naming this feature, by substring match on its title."""
    for link in links:
        if title in link.get("title", ""):
            return link.get("href")
    return None


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _item_url(state_root: Path) -> str | None:
    """The feature radio group lives on any item's edit page; reuse the first tracked item."""
    for set_dir in sorted(state_root.glob("set-*")):
        item = _read_json(set_dir / "creators-item.json")
        product_id = (item or {}).get("product_id")
        if product_id:
            return f"{CREATOR_BASE}/sticker/{product_id}/update"
    return None


def should_run_today(ledger_path: Path) -> bool:
    if not ledger_path.exists():
        return True
    try:
        observed_at = json.loads(ledger_path.read_text()).get("observed_at")
        observed = datetime.datetime.fromisoformat(observed_at)
    except (json.JSONDecodeError, TypeError, ValueError):
        return True
    return observed.astimezone(JST).date() != now_utc().astimezone(JST).date()


async def _fetch(cdp: str, item_url: str) -> dict:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp)
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(item_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            if "access.line.me" in page.url:
                return {"status": "needs_login"}
            radios = await page.evaluate(
                """() => {
                    const radios = [...document.querySelectorAll('input[type=radio]')];
                    const groups = {};
                    for (const r of radios) { (groups[r.name] ||= []).push(r); }
                    const group = Object.values(groups).find(g => g.some(r => r.value === 'on'));
                    return (group || []).map(r => ({
                        value: r.value,
                        label: (r.closest('label') || {}).innerText || '',
                    }));
                }"""
            )
            await page.goto(f"{CREATOR_BASE}/announce/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            links = await page.evaluate(
                """() => [...document.querySelectorAll('a[href*="/announce/article"]')]
                    .map(a => ({title: a.innerText.trim(), href: a.getAttribute('href')}))"""
            )
            today = now_utc().astimezone(JST).date()
            features = []
            for radio in radios:
                parsed = parse_feature_radio(radio["value"], radio["label"], today)
                if not parsed:
                    continue
                href = match_announce_link(parsed["title"], links)
                conditions = None
                announce_url = None
                if href:
                    announce_url = href if href.startswith("http") else f"{CREATOR_BASE}{href}"
                    await page.goto(announce_url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(1500)
                    conditions = await page.inner_text("body")
                parsed["announce_url"] = announce_url
                parsed["conditions"] = conditions
                features.append(parsed)
            return {"status": "ok", "features": features}
        finally:
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, default=STATE_ROOT_DEFAULT)
    args = parser.parse_args()
    state_root = args.state_root
    ledger = state_root / "features.json"

    if not should_run_today(ledger):
        print(json.dumps({"status": "skipped_already_today"}))
        return

    item_url = _item_url(state_root)
    if not item_url:
        print(json.dumps({"status": "no_item_yet"}))
        return

    acquired = subprocess.run(["bash", str(GUARD), "acquire", IDENTITY], capture_output=True, text=True)
    if acquired.returncode != 0:
        # BUSY or unreachable is a skipped cycle; the self-gate retries on the next hourly wake.
        print(json.dumps({"status": "browser_unavailable", "detail": acquired.stderr.strip()[-200:]}))
        return
    try:
        fetched = asyncio.run(_fetch(acquired.stdout.strip().splitlines()[-1], item_url))
    finally:
        subprocess.run(["bash", str(GUARD), "release", IDENTITY], capture_output=True)

    if fetched.get("status") != "ok":
        print(json.dumps(fetched))
        return

    row = {
        "observed_at": now_utc().isoformat(),
        "source_urls": [item_url, f"{CREATOR_BASE}/announce/"],
        "features": fetched["features"],
    }
    state_root.mkdir(parents=True, exist_ok=True)
    tmp = ledger.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(row, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    tmp.replace(ledger)
    print(json.dumps({"status": "ok", "features": len(row["features"])}))


if __name__ == "__main__":
    main()
