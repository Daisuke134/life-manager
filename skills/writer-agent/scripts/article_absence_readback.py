#!/usr/bin/env python3
"""Official owner readbacks: is one Writer run's article absent from every active destination?

Each reader reads the authenticated owner's complete drafts+published roster.  A destination is
"absent" only when the roster is complete (every page read, or anchored by a known earlier
publication from the Writer ledger), no item was created/updated/published in the run window
(plus grace), and no item carries the run's title.  Any read, identity, completeness, anchor or
timezone failure is "unreadable" -- never absence.

    python3 article_absence_readback.py --run-dir DIR --since EPOCH --until EPOCH
Run it under writer-runtime-env.sh (credentials) with the Writer managed Python.  The X reader
re-invokes this file under skills/browser/with-browser.sh x:diceai0 (no wait; the lease
is released when that one command exits).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
ARTICLES = Path.home() / ".local/state/life-manager/writer/articles.jsonl"
ACTIVE_DESTINATIONS = ("note/ja", "substack/ja", "substack/en", "x-article/ja")
GRACE_SECONDS = 1800          # a killed model pass cannot act after its terminal; margin anyway
TITLE_PREFIX = 20             # titles may be truncated in owner listings
MAX_PAGES = 40
SUBSTACK_PAGE = 25
# The Writer X Article account (X_ACCOUNT_HANDLE) lives in its own registered browser; the
# interactive daily-driver holds no x.com session (login redirect measured 2026-10-16).
X_BROWSER_IDENTITY = "x:diceai0"


def _epoch(value: object) -> float | None:
    """Empty -> None.  A naive or unparseable time cannot be placed in the window: refuse."""
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone-naive timestamp")
    return parsed.timestamp()


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", value).strip().casefold()


def run_titles(run_dir: Path) -> list[str]:
    titles = []
    for name in ("article-ja.md", "article-en.md"):
        path = run_dir / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            front = re.match(r'^title:\s*["\']?(.*?)["\']?\s*$', line)
            if front and front.group(1):
                titles.append(front.group(1))
            elif line.startswith("# "):
                titles.append(line[2:].strip())
                break
    return list(dict.fromkeys(titles))


def _title_matches(remote: str, titles: list[str]) -> bool:
    remote = _norm(remote).rstrip("…").rstrip(".")
    if not remote:
        return False
    for title in map(_norm, titles):
        if remote == title or (len(remote) >= TITLE_PREFIX and title.startswith(remote[:TITLE_PREFIX])) \
                or (len(title) >= TITLE_PREFIX and title[:TITLE_PREFIX] in remote):
            return True
    return False


def judge(items: list[dict], *, since: float, until: float, titles: list[str], complete: bool) -> dict:
    if not complete:
        return {"status": "unreadable", "reason": "listing_incomplete"}
    for item in items:
        if any(since <= t <= until + GRACE_SECONDS for t in item.get("times", []) if t is not None):
            return {"status": "present", "reason": "item_in_run_window", "title": item.get("title", "")}
        if item.get("in_window"):
            return {"status": "present", "reason": "item_in_run_window", "title": item.get("title", "")}
        if _title_matches(str(item.get("title") or ""), titles):
            return {"status": "present", "reason": "title_match", "title": item.get("title", "")}
    newest = max((t for item in items for t in item.get("times", []) if t is not None), default=None)
    return {"status": "absent", "items_read": len(items), "newest_item_epoch": newest}


def ledger_anchor(rows: list[dict], platform: str, since: float, field: str) -> str:
    """Newest Writer-ledger publication on this platform before the window: a parse/reach anchor."""
    best, best_time = "", None
    for row in rows:
        if row.get("platform") != platform or row.get("published") is not True:
            continue
        try:
            stamp = _epoch(row.get("published_at") or row.get("ts"))
        except ValueError:
            continue
        if stamp is not None and stamp < since and (best_time is None or stamp > best_time) and row.get(field):
            best, best_time = str(row[field]), stamp
    return best


def parse_note(pages: list[dict], expected: str, anchor_key: str) -> tuple[list[dict], bool]:
    """pages = successive `data` objects of api/v2/note_list/contents (drafts and published)."""
    items, keys = [], set()
    for data in pages:
        for note in data["notes"]:
            if (note.get("user") or {}).get("urlname") != expected:
                raise ValueError("note listing contains another owner")
            keys.add(note.get("key"))
            draft = note.get("noteDraft") if isinstance(note.get("noteDraft"), dict) else {}
            times = [_epoch(note.get(k)) for k in ("createdAt", "publishAt", "updatedAt")]
            for title in {note.get("name") or "", draft.get("name") or ""}:
                items.append({"title": title, "times": times})
    complete = bool(pages) and pages[-1].get("isLastPage") is True and bool(anchor_key) and anchor_key in keys
    return items, complete


def parse_substack(listings: dict[str, list[dict]]) -> tuple[list[dict], bool]:
    """listings[kind] = successive post_management pages; complete only when every post was read."""
    items, complete = [], True
    for pages in listings.values():
        posts = [post for page in pages for post in page["posts"]]
        complete = complete and bool(pages) and len(posts) >= int(pages[0]["total"])
        for post in posts:
            times = [_epoch(post.get(k)) for k in ("draft_updated_at", "draft_created_at", "post_date")]
            for title in {post.get("draft_title") or "", post.get("title") or ""}:
                items.append({"title": title, "times": times})
    return items, complete


def _x_row(text: str, reference: datetime) -> tuple[str, str, object, bool]:
    """'Draft · Last saved <date>' / 'Published · <date>', then the title line."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines or lines[0] not in {"Draft", "Published", "Scheduled"}:
        raise ValueError("x article row status unreadable")
    rest = [line for line in lines[1:] if line not in {"·", "Last saved"}]
    if len(rest) < 2:
        raise ValueError("x article row without date and title")
    label, title = rest[0], rest[1]
    if re.fullmatch(r"\d+[smh]", label):
        return lines[0], title, reference.date(), True
    for value, fmt in ((label, "%b %d, %Y"), (f"{label} {reference.year}", "%b %d %Y")):
        try:
            parsed = datetime.strptime(value, fmt).date()
        except ValueError:
            continue
        if fmt == "%b %d %Y" and parsed > reference.date():
            parsed = parsed.replace(year=reference.year - 1)
        return lines[0], title, parsed, False
    raise ValueError("x article row date unreadable")


def parse_x(data: dict, anchor_edit_id: str, *, since: float, until: float) -> tuple[list[dict], bool]:
    """data = x_list_in_leased_browser() output: Drafts and Published tab rows, newest first.

    Rows show day-granular dates in the browser's JST; a row dated on any run-window day (or with
    a relative age) is in the window.  Each tab must be newest-first and reach back before the
    window, and the ledger's newest earlier X Article (edit id) must be a parsed Published row.
    """
    if not data.get("expected") or str(data.get("identity", "")).casefold() != data["expected"].casefold():
        raise ValueError("x authenticated identity mismatch")
    if not str(data.get("url", "")).startswith("https://x.com/compose/articles"):
        raise ValueError("x articles list did not render")
    jst = timezone(timedelta(hours=9))   # ponytail: the leased browsers run in JST; read tz from the page if that changes
    reference = datetime.fromtimestamp(until + GRACE_SECONDS, jst)
    first_day = datetime.fromtimestamp(since, jst).date()
    window_days = {first_day + timedelta(days=n) for n in range((reference.date() - first_day).days + 1)}
    items, dates, anchored = [], {"drafts": [], "published": []}, False
    for row in data.get("rows") or []:
        _, title, day, relative = _x_row(row.get("text"), reference)
        tab = row.get("tab")
        if tab not in dates:
            raise ValueError("x article row tab unknown")
        dates[tab].append(day)
        items.append({"title": title, "times": [], "in_window": relative or day in window_days})
        anchored = anchored or (tab == "published" and bool(anchor_edit_id) and str(row.get("href", "")).rstrip("/")
                                .endswith(f"/compose/articles/edit/{anchor_edit_id}"))
    complete = anchored and all(
        days and days == sorted(days, reverse=True) and days[-1] < first_day for days in dates.values())
    return items, complete


def note_reader(since: float, rows: list[dict]) -> tuple[list[dict], bool, dict]:
    from publication_remote import get_json
    from writer_runtime_paths import note_work_dir
    cookies = json.loads((note_work_dir() / "note-cookies.json").read_text(encoding="utf-8"))
    headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()), "User-Agent": "Mozilla/5.0"}
    expected = os.environ.get("NOTE_URLNAME", "").strip()
    identity = get_json("https://note.com/api/v2/current_user", headers)["data"]["urlname"]
    if not expected or identity != expected:
        raise ValueError("note authenticated identity mismatch")
    pages = []
    for page in range(1, MAX_PAGES + 1):
        pages.append(get_json(f"https://note.com/api/v2/note_list/contents?page={page}", headers)["data"])
        if pages[-1].get("isLastPage") is True:
            break
    anchor = ledger_anchor(rows, "note", since, "public_id")
    items, complete = parse_note(pages, expected, anchor)
    return items, complete, {"readback_url": "https://note.com/api/v2/note_list/contents",
                             "identity": identity, "pages": len(pages), "anchor": anchor}


def substack_reader(pair: str, since: float, rows: list[dict]) -> tuple[list[dict], bool, dict]:
    from publication_remote import get_json
    publication = os.environ.get("SUBSTACK_PUBLICATION_EN" if pair == "substack/en" else "SUBSTACK_PUBLICATION_JA", "")
    cookie = os.environ.get("SUBSTACK_SESSION_COOKIE_EN" if pair == "substack/en" else "SUBSTACK_SESSION_COOKIE_JA", "") \
        or os.environ.get("SUBSTACK_SESSION_COOKIE", "")
    if not publication or not cookie:
        raise ValueError("substack identity or cookie missing")
    headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    listings: dict[str, list[dict]] = {}
    for kind in ("drafts", "scheduled", "published"):
        pages = listings.setdefault(kind, [])
        for index in range(MAX_PAGES):
            pages.append(get_json(
                f"https://{publication}/api/v1/post_management/{kind}?offset={index * SUBSTACK_PAGE}"
                f"&limit={SUBSTACK_PAGE}&order_by=draft_updated_at&order_direction=desc", headers))
            if not pages[-1]["posts"] or (index + 1) * SUBSTACK_PAGE >= int(pages[0]["total"]):
                break
    items, complete = parse_substack(listings)
    return items, complete, {"readback_url": f"https://{publication}/api/v1/post_management/{{drafts,scheduled,published}}",
                             "identity": publication,
                             "totals": {kind: int(pages[0]["total"]) for kind, pages in listings.items()}}


def x_list_in_leased_browser() -> dict:
    """Runs inside with-browser.sh: read the authenticated X Articles Drafts and Published tabs."""
    from playwright.sync_api import sync_playwright
    expected = os.environ.get("X_ACCOUNT_HANDLE", "").strip().lstrip("@")
    rows_js = "els => els.map(e => ({href: e.getAttribute('href'), text: e.innerText}))"
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(os.environ["CDP"])
        page = browser.contexts[0].new_page()
        try:
            page.goto("https://x.com/compose/articles", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(6000)
            href = page.locator('a[data-testid="AppTabBar_Profile_Link"]').first.get_attribute("href", timeout=10000)
            rows = []
            for tab in ("Drafts", "Published"):
                control = page.get_by_role("tab", name=tab)
                if control.get_attribute("aria-selected", timeout=10000) != "true":
                    control.click(timeout=10000)
                    page.wait_for_timeout(5000)
                if control.get_attribute("aria-selected", timeout=10000) != "true":
                    raise RuntimeError(f"x {tab} tab not selected")
                rows += [{**row, "tab": tab.lower()} for row in
                         page.eval_on_selector_all('a[href*="/compose/articles/edit/"]', rows_js)]
            return {"url": page.url, "identity": str(href or "").strip("/"), "expected": expected, "rows": rows}
        finally:
            page.close()
    finally:
        playwright.stop()


def x_reader(since: float, rows: list[dict], until: float) -> tuple[list[dict], bool, dict]:
    env = {**os.environ, "BROWSER_WAIT_SECONDS": "0"}
    completed = subprocess.run(
        ["bash", str(REPO_ROOT / "skills/browser/with-browser.sh"), X_BROWSER_IDENTITY, "--",
         sys.executable, str(Path(__file__).resolve()), "--x-list"],
        capture_output=True, text=True, timeout=240, env=env, check=False)
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip().splitlines()[-1:] or [""]
        raise ValueError(f"x leased read failed rc={completed.returncode} {tail[0][:100]}")
    data = json.loads(completed.stdout.strip().splitlines()[-1])
    target = ledger_anchor(rows, "x-article", since, "stable_target")
    anchor = target.rstrip("/").rsplit("/", 1)[-1] if "/compose/articles/edit/" in target else ""
    items, complete = parse_x(data, anchor, since=since, until=until)
    return items, complete, {"readback_url": "https://x.com/compose/articles", "identity": data["identity"],
                             "browser_identity": X_BROWSER_IDENTITY, "rows": len(items), "anchor_edit_id": anchor}


def collect(run_dir: Path, since: float, until: float,
            readers: dict[str, Callable[[float, list[dict]], tuple[list[dict], bool, dict]]] | None = None,
            ledger_rows: list[dict] | None = None) -> dict:
    readers = readers or {
        "note/ja": note_reader,
        "substack/ja": lambda s, r: substack_reader("substack/ja", s, r),
        "substack/en": lambda s, r: substack_reader("substack/en", s, r),
        "x-article/ja": lambda s, r: x_reader(s, r, until),
    }
    if ledger_rows is None:
        ledger_rows = [json.loads(line) for line in ARTICLES.read_text(encoding="utf-8").splitlines() if line.strip()]
    titles = run_titles(run_dir)
    destinations = {}
    for pair in ACTIVE_DESTINATIONS:
        if not titles:
            destinations[pair] = {"status": "unreadable", "reason": "run_title_missing"}
            continue
        try:
            items, complete, meta = readers[pair](since, ledger_rows)
            destinations[pair] = {**judge(items, since=since, until=until, titles=titles, complete=complete), **meta}
        except Exception as error:   # any read failure keeps the fence
            destinations[pair] = {"status": "unreadable", "reason": f"{type(error).__name__}: {str(error)[:120]}"}
    return {"titles": titles, "since": since, "until": until, "destinations": destinations}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run-dir")
    parser.add_argument("--since", type=float)
    parser.add_argument("--until", type=float)
    parser.add_argument("--x-list", action="store_true")
    args = parser.parse_args(argv)
    if args.x_list:
        print(json.dumps(x_list_in_leased_browser(), ensure_ascii=False))
        return 0
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    print(json.dumps(collect(Path(args.run_dir), args.since, args.until), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
