#!/usr/bin/env python3
"""Daily readback of LINE Creators Market account-level sales/分配 (distribution) numbers.

Reads the official 売上・統計情報：アイテム page (per-product cumulative statistics, a provisional
distribution estimate rather than finalized gross sales) and the 送金申請 page (送金可能額 / payable
amount and the current 分配額 / withholding-tax period). It matches rows by the official
item-management ID in each detail link, then writes one JSON snapshot to ``sales.json`` for the
factory planner. Self-gates to once per day (UTC/JST date of the last ``observed_at``); every other
hourly wake is a fast no-op. Unknown numbers (a tracked product absent from the page, or a field the
page itself did not render) stay ``null`` -- never silently become 0.

    sales_readback.py
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
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / "skills" / "browser" / "browser-guard.sh"
IDENTITY = "line-creators:dais"
CREATOR_BASE = "https://creator.line.me/my/cCX4POFknN2lhLJE"
STATE_ROOT_DEFAULT = Path.home() / ".local/state/life-manager" / "line-sticker"
JST = datetime.timezone(datetime.timedelta(hours=9))
SALES_SNAPSHOT_SCHEMA_VERSION = 2

STICKER_ROW_RE = re.compile(r"([^\n\t￥]+?)[\t\n]+(\d{4}/\d{1,2}/\d{1,2})[\t\n]+￥([\d,]+)")
PRODUCT_ID_RE = re.compile(r"/stats/sticker/(\d+)(?:/)?(?:[?#].*)?$")
PAYABLE_RE = re.compile(r"送金可能額¥([\d,]+)")
PERIOD_RE = re.compile(r"対象期間\t([\d.\-]+)")
DISTRIBUTED_RE = re.compile(r"分配額\t¥([\d,]+)")
WITHHOLDING_RE = re.compile(r"源泉所得税\t¥([\d,]+)")


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _yen(value: str) -> int:
    return int(value.replace(",", ""))


def parse_sticker_stats(text: str) -> list[dict]:
    """Parse 売上・統計情報：アイテム's table body into one row per listed item."""
    return [
        {"title_ja": title.strip(), "sale_start_date": date, "sales_jpy": _yen(amount)}
        for title, date, amount in STICKER_ROW_RE.findall(text)
    ]


def parse_sticker_table_rows(rows: list[dict]) -> list[dict]:
    """Parse the official table's row text together with its stable item-management ID link."""
    parsed = []
    for row in rows:
        href = str(row.get("href") or "")
        product_id = PRODUCT_ID_RE.search(href)
        values = parse_sticker_stats(str(row.get("text") or ""))
        if not product_id or len(values) != 1:
            raise ValueError("official sticker statistics row is missing its product ID or values")
        parsed.append({"product_id": product_id.group(1), **values[0]})
    return parsed


def _stats_table_is_complete(snapshot: dict) -> bool:
    rows = snapshot.get("rows")
    page_numbers = snapshot.get("page_numbers")
    current_page = snapshot.get("current_page")
    return (
        snapshot.get("ready_state") == "complete"
        and snapshot.get("table_count") == 1
        and snapshot.get("busy") is False
        and snapshot.get("stable") is True
        and isinstance(rows, list)
        and bool(rows)
        and snapshot.get("body_row_count") == len(rows)
        and isinstance(page_numbers, list)
        and bool(page_numbers)
        and all(type(number) is int and number >= 1 for number in page_numbers)
        and page_numbers == list(range(1, len(page_numbers) + 1))
        and type(current_page) is int
        and current_page in page_numbers
        and isinstance(snapshot.get("has_next_control"), bool)
    )


def _stats_page_matches_api(snapshot: dict, payload: object) -> bool:
    """Require the rendered page IDs to match the official page response exactly."""
    if not isinstance(payload, dict):
        return False
    products = payload.get("products")
    pager = payload.get("pager")
    page_numbers = snapshot.get("page_numbers")
    current_page = snapshot.get("current_page")
    rows = snapshot.get("rows")
    if (not isinstance(products, list) or not products
            or not isinstance(pager, dict)
            or type(pager.get("currentPage")) is not int
            or type(pager.get("maxPage")) is not int
            or not isinstance(page_numbers, list)
            or pager["currentPage"] != current_page
            or pager["maxPage"] != len(page_numbers)):
        return False
    api_ids = []
    for product in products:
        product_id = product.get("id") if isinstance(product, dict) else None
        if type(product_id) not in (int, str) or not str(product_id):
            return False
        api_ids.append(str(product_id))
    try:
        dom_ids = [row["product_id"] for row in parse_sticker_table_rows(rows)]
    except (TypeError, ValueError):
        return False
    return len(api_ids) == len(set(api_ids)) and set(api_ids) == set(dom_ids)


def parse_payment_request(text: str) -> dict:
    """Parse 送金申請: 送金可能額 (payable) and the current collection-period 分配額/源泉所得税.

    Any field absent from the page (e.g. before the account has ever earned anything, before the
    period block renders) stays None -- not 0.
    """
    payable = PAYABLE_RE.search(text)
    period = PERIOD_RE.search(text)
    distributed = DISTRIBUTED_RE.search(text)
    withholding = WITHHOLDING_RE.search(text)
    current_period = None
    if period and distributed and withholding:
        current_period = {
            "period": period.group(1),
            "distributed_jpy": _yen(distributed.group(1)),
            "withholding_tax_jpy": _yen(withholding.group(1)),
        }
    return {
        "payable_jpy": _yen(payable.group(1)) if payable else None,
        "current_period": current_period,
    }


def match_products(tracked: list[dict], rows: list[dict]) -> list[dict]:
    """Join official rows to tracked items by item-management ID; absent IDs stay unknown."""
    by_id: dict[str, list[dict]] = {}
    for row in rows:
        product_id = row.get("product_id")
        if product_id:
            by_id.setdefault(str(product_id), []).append(row)
    tracked_counts: dict[str, int] = {}
    for item in tracked:
        product_id = str(item["product_id"])
        tracked_counts[product_id] = tracked_counts.get(product_id, 0) + 1
    products = []
    for item in tracked:
        product_id = str(item["product_id"])
        matches = by_id.get(product_id, [])
        row = matches[0] if len(matches) == 1 and tracked_counts[product_id] == 1 else None
        products.append({
            "product_id": item["product_id"],
            "title_ja": item["title_ja"],
            "sale_start_date": row["sale_start_date"] if row else None,
            "sales_jpy": row["sales_jpy"] if row else None,
        })
    return products


def should_run_today(ledger_path: Path, tracked_products: list[dict] | None = None) -> bool:
    if not ledger_path.exists():
        return True
    try:
        snapshot = json.loads(ledger_path.read_text())
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != SALES_SNAPSHOT_SCHEMA_VERSION:
            return True
        if tracked_products is not None:
            saved_products = snapshot.get("products")
            if not isinstance(saved_products, list):
                return True
            current_ids = sorted(str(item["product_id"]) for item in tracked_products)
            saved_ids = sorted(
                str(item["product_id"])
                for item in saved_products
                if isinstance(item, dict) and item.get("product_id") is not None
            )
            if len(saved_ids) != len(saved_products) or current_ids != saved_ids:
                return True
        observed_at = snapshot.get("observed_at")
        observed = datetime.datetime.fromisoformat(observed_at)
    except (json.JSONDecodeError, TypeError, ValueError):
        return True
    return observed.astimezone(JST).date() != now_utc().astimezone(JST).date()


def _tracked_products(state_root: Path) -> list[dict]:
    tracked = []
    for set_dir in sorted(state_root.glob("set-*")):
        item = _read_json(set_dir / "creators-item.json")
        product_id = (item or {}).get("product_id")
        title_ja = (item or {}).get("title_ja")
        if product_id and title_ja:
            tracked.append({"product_id": product_id, "title_ja": title_ja})
    return tracked


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


async def _fetch(cdp: str) -> dict:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp)
        context = browser.contexts[0]
        page = await context.new_page()
        stats_api_path = urlsplit(f"{CREATOR_BASE}/api/stats/sticker").path
        api_responses: list[tuple[int | None, int, asyncio.Task[object] | None]] = []
        capture_stats_responses = True

        def capture_stats_response(response) -> None:
            if not capture_stats_responses:
                return
            parsed_url = urlsplit(response.url)
            if parsed_url.path != stats_api_path:
                return
            page_values = parse_qs(parsed_url.query, keep_blank_values=True).get("page", [])
            page_number = None
            if len(page_values) == 1 and re.fullmatch(r"[0-9]+", page_values[0]):
                try:
                    page_number = int(page_values[0])
                except ValueError:
                    pass
            task = asyncio.create_task(response.json()) if page_number is not None else None
            api_responses.append((page_number, response.status, task))

        page.on("response", capture_stats_response)
        try:
            await page.goto(f"{CREATOR_BASE}/stats/sticker", wait_until="load", timeout=60000)
            if "access.line.me" in page.url:
                return {"status": "needs_login"}
            snapshot_script = """/* LINE_STICKER_STATS_SNAPSHOT */ () => {
                const tables = [...document.querySelectorAll('table')];
                const table = tables.find(candidate => candidate.classList.contains('item-list-table'));
                const bodyRows = table
                    ? [...table.querySelectorAll('tr')].filter(row => !row.querySelector('th'))
                    : [];
                const rows = bodyRows.map(row => {
                    const link = row.querySelector('a[href*="/stats/sticker/"]');
                    return link ? {href: link.href, text: row.innerText} : null;
                }).filter(Boolean);
                const controls = [...document.querySelectorAll('a,button,[role="button"]')]
                    .filter(element => element.getClientRects().length > 0);
                const controlText = element =>
                    (element.innerText || element.getAttribute('aria-label') || '').trim();
                const pageNumbers = [...new Set(controls
                    .map(controlText)
                    .filter(text => /^\\d+$/.test(text))
                    .map(Number))].sort((a, b) => a - b);
                const selected = controls.find(element =>
                    element.classList.contains('selected') && /^\\d+$/.test(controlText(element)));
                const currentPage = selected ? Number(controlText(selected)) : null;
                const hasNextControl = controls.some(element => {
                    const text = controlText(element).toLowerCase();
                    return !element.disabled
                        && element.getAttribute('aria-disabled') !== 'true'
                        && /^(next|次へ|次|›|»|>|>>)$/.test(text);
                });
                return {
                    ready_state: document.readyState,
                    table_count: tables.length,
                    rows,
                    body_row_count: bodyRows.length,
                    page_numbers: pageNumbers,
                    current_page: currentPage,
                    has_next_control: hasNextControl,
                    busy: !!document.querySelector(
                        '[aria-busy="true"],[role="progressbar"],.loading,.spinner'
                    )
                };
            }"""
            click_page_script = """/* LINE_STICKER_STATS_CLICK_PAGE */ targetPage => {
                const controls = [...document.querySelectorAll('a,button,[role="button"]')]
                    .filter(element => element.getClientRects().length > 0);
                const controlText = element =>
                    (element.innerText || element.getAttribute('aria-label') || '').trim();
                const matches = controls.filter(element =>
                    controlText(element) === String(targetPage)
                    && !element.classList.contains('selected')
                    && !element.disabled
                    && element.getAttribute('aria-disabled') !== 'true');
                if (matches.length !== 1) return false;
                matches[0].click();
                return true;
            }"""
            selected_page_script = """targetPage => {
                const control = [...document.querySelectorAll('a,button,[role="button"]')]
                    .find(element => element.getClientRects().length > 0
                        && element.classList.contains('selected'));
                const text = control
                    ? (control.innerText || control.getAttribute('aria-label') || '').trim()
                    : '';
                return text === String(targetPage);
            }"""
            stats_rows = []
            seen_ids: set[str] = set()
            expected_pages: list[int] | None = None
            visited_pages: set[int] = set()
            page_snapshots: dict[int, dict] = {}
            while True:
                await page.wait_for_timeout(700)
                first_snapshot = await page.evaluate(snapshot_script)
                await page.wait_for_timeout(700)
                snapshot = await page.evaluate(snapshot_script)
                snapshot["stable"] = first_snapshot == snapshot
                if not _stats_table_is_complete(snapshot):
                    return {"status": "incomplete_stats_table"}

                page_numbers = snapshot["page_numbers"]
                current_page = snapshot["current_page"]
                if expected_pages is None:
                    expected_pages = page_numbers
                if (page_numbers != expected_pages
                        or current_page != len(visited_pages) + 1
                        or current_page in visited_pages):
                    return {"status": "incomplete_stats_table"}
                page_responses = [entry for entry in api_responses if entry[0] == current_page]
                if (any(entry[0] is None for entry in api_responses)
                        or len(page_responses) != 1
                        or page_responses[0][1] != 200
                        or page_responses[0][2] is None):
                    return {"status": "incomplete_stats_table"}
                try:
                    api_payload = await page_responses[0][2]
                except Exception:
                    return {"status": "incomplete_stats_table"}
                if not _stats_page_matches_api(snapshot, api_payload):
                    return {"status": "incomplete_stats_table"}
                page_snapshots[current_page] = snapshot
                try:
                    parsed_page = parse_sticker_table_rows(snapshot["rows"])
                except ValueError:
                    return {"status": "incomplete_stats_table"}
                page_ids = [row["product_id"] for row in parsed_page]
                if len(page_ids) != len(set(page_ids)) or seen_ids.intersection(page_ids):
                    return {"status": "incomplete_stats_table"}
                seen_ids.update(page_ids)
                stats_rows.extend(snapshot["rows"])
                visited_pages.add(current_page)

                later_pages = [number for number in page_numbers if number > current_page]
                if later_pages:
                    next_page = min(later_pages)
                    if next_page != current_page + 1:
                        return {"status": "incomplete_stats_table"}
                    clicked = await page.evaluate(click_page_script, next_page)
                    if clicked is not True:
                        return {"status": "incomplete_stats_table"}
                    try:
                        await page.wait_for_function(
                            selected_page_script, arg=next_page, timeout=15000
                        )
                    except PlaywrightTimeoutError:
                        return {"status": "incomplete_stats_table"}
                    continue
                if snapshot["has_next_control"]:
                    return {"status": "incomplete_stats_table"}
                break

            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                return {"status": "incomplete_stats_table"}
            await page.goto(f"{CREATOR_BASE}/payment_request/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            payment_text = await page.inner_text("body")
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                return {"status": "incomplete_stats_table"}
            response_pages = [entry[0] for entry in api_responses]
            if (expected_pages is None
                    or visited_pages != set(expected_pages)
                    or set(page_snapshots) != set(expected_pages)
                    or len(api_responses) != len(expected_pages)
                    or set(response_pages) != set(expected_pages)):
                return {"status": "incomplete_stats_table"}
            for page_number in expected_pages:
                page_response = next(entry for entry in api_responses if entry[0] == page_number)
                if page_response[1] != 200 or page_response[2] is None:
                    return {"status": "incomplete_stats_table"}
                try:
                    api_payload = await page_response[2]
                except Exception:
                    return {"status": "incomplete_stats_table"}
                if not _stats_page_matches_api(page_snapshots[page_number], api_payload):
                    return {"status": "incomplete_stats_table"}
            capture_stats_responses = False
            return {"status": "ok", "stats_rows": stats_rows, "payment_text": payment_text}
        finally:
            await page.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, default=STATE_ROOT_DEFAULT)
    args = parser.parse_args()
    state_root = args.state_root
    ledger = state_root / "sales.json"
    tracked = _tracked_products(state_root)

    if not should_run_today(ledger, tracked):
        print(json.dumps({"status": "skipped_already_today"}))
        return 0

    acquired = subprocess.run(["bash", str(GUARD), "acquire", IDENTITY], capture_output=True, text=True)
    if acquired.returncode != 0:
        # BUSY or unreachable is a skipped cycle; the self-gate retries on the next hourly wake.
        print(json.dumps({"status": "browser_unavailable", "detail": acquired.stderr.strip()[-200:]}))
        return 75
    try:
        fetched = asyncio.run(_fetch(acquired.stdout.strip().splitlines()[-1]))
    finally:
        subprocess.run(["bash", str(GUARD), "release", IDENTITY], capture_output=True)

    if fetched.get("status") != "ok":
        print(json.dumps(fetched))
        return 75 if fetched.get("status") == "needs_login" else 1

    rows = parse_sticker_table_rows(fetched["stats_rows"])
    distribution = parse_payment_request(fetched["payment_text"])
    row = {
        "schema_version": SALES_SNAPSHOT_SCHEMA_VERSION,
        "observed_at": now_utc().isoformat(),
        "source_urls": [f"{CREATOR_BASE}/stats/sticker", f"{CREATOR_BASE}/payment_request/"],
        "products": match_products(tracked, rows),
        "distribution": distribution,
    }
    state_root.mkdir(parents=True, exist_ok=True)
    tmp = ledger.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(row, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    tmp.replace(ledger)
    print(json.dumps({"status": "ok", "products": len(row["products"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
