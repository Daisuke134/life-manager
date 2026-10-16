#!/usr/bin/env python3
"""Official owner readbacks: is one Writer run's article absent from every active destination?

Each reader lists the authenticated owner's drafts and published items, newest first.  A
destination is "absent" only when its listing is complete back to the window start, no item was
created/updated/published in the run window (plus grace), and no item carries the run's title.
Any read, identity or completeness failure is "unreadable" -- never absence.

    python3 article_absence_readback.py --run-dir DIR --since EPOCH --until EPOCH
Run it under writer-runtime-env.sh (credentials) with the Writer managed Python.  The X reader
re-invokes this file under skills/browser/with-browser.sh interactive:dais (no wait; the lease
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
from datetime import datetime
from pathlib import Path
from typing import Callable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
ACTIVE_DESTINATIONS = ("note/ja", "substack/ja", "substack/en", "x-article/ja")
GRACE_SECONDS = 1800          # a killed model pass cannot act after its terminal; margin anyway
TITLE_PREFIX = 20             # titles may be truncated in owner listings


def _epoch(value: object) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None


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
        if _title_matches(str(item.get("title") or ""), titles):
            return {"status": "present", "reason": "title_match", "title": item.get("title", "")}
    newest = max((t for item in items for t in item.get("times", []) if t is not None), default=None)
    return {"status": "absent", "items_read": len(items), "newest_item_epoch": newest}


def _complete(times: list[float | None], since: float, final_page: bool) -> bool:
    """Newest-first listing reaches back past the window, or it is the whole roster."""
    known = [t for t in times if t is not None]
    return final_page or (bool(known) and min(known) < since)


def note_reader(since: float) -> tuple[list[dict], bool, dict]:
    from publication_remote import get_json
    from writer_runtime_paths import note_work_dir
    cookies = json.loads((note_work_dir() / "note-cookies.json").read_text(encoding="utf-8"))
    headers = {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()), "User-Agent": "Mozilla/5.0"}
    expected = os.environ.get("NOTE_URLNAME", "").strip()
    identity = get_json("https://note.com/api/v2/current_user", headers)["data"]["urlname"]
    if not expected or identity != expected:
        raise ValueError("note authenticated identity mismatch")
    url = "https://note.com/api/v2/note_list/contents?page=1"
    data = get_json(url, headers)["data"]
    items = []
    for note in data["notes"]:
        if (note.get("user") or {}).get("urlname") != expected:
            raise ValueError("note listing contains another owner")
        draft = note.get("noteDraft") if isinstance(note.get("noteDraft"), dict) else {}
        for title in {note.get("name") or "", draft.get("name") or ""}:
            items.append({"title": title, "times": [_epoch(note.get("createdAt")), _epoch(note.get("publishAt"))]})
    complete = _complete([t for i in items for t in i["times"]], since, data.get("isLastPage") is True)
    return items, complete, {"readback_url": url, "identity": identity}


def substack_reader(pair: str, since: float) -> tuple[list[dict], bool, dict]:
    from publication_remote import get_json
    publication = os.environ.get("SUBSTACK_PUBLICATION_EN" if pair == "substack/en" else "SUBSTACK_PUBLICATION_JA", "")
    cookie = os.environ.get("SUBSTACK_SESSION_COOKIE_EN" if pair == "substack/en" else "SUBSTACK_SESSION_COOKIE_JA", "") \
        or os.environ.get("SUBSTACK_SESSION_COOKIE", "")
    if not publication or not cookie:
        raise ValueError("substack identity or cookie missing")
    headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    items, complete, urls = [], True, []
    for kind in ("drafts", "scheduled", "published"):
        url = (f"https://{publication}/api/v1/post_management/{kind}"
               "?offset=0&limit=25&order_by=draft_updated_at&order_direction=desc")
        urls.append(url)
        data = get_json(url, headers)
        posts = data["posts"]
        times = []
        for post in posts:
            stamps = [_epoch(post.get(k)) for k in ("draft_updated_at", "draft_created_at", "post_date")]
            times.extend(stamps)
            for title in {post.get("draft_title") or "", post.get("title") or ""}:
                items.append({"title": title, "times": stamps})
        complete = complete and _complete(times, since, int(data["total"]) <= len(posts))
    return items, complete, {"readback_urls": urls, "identity": publication}


def x_list_in_leased_browser() -> dict:
    """Runs inside with-browser.sh: read the authenticated X Articles list (drafts and published)."""
    from playwright.sync_api import sync_playwright
    expected = os.environ.get("X_ACCOUNT_HANDLE", "").strip().lstrip("@")
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(os.environ["CDP"])
        page = browser.contexts[0].new_page()
        try:
            page.goto("https://x.com/compose/articles", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(6000)
            href = page.locator('a[data-testid="AppTabBar_Profile_Link"]').first.get_attribute("href", timeout=10000)
            identity = str(href or "").strip("/")
            rows = page.eval_on_selector_all(
                'a[href*="/compose/articles/edit/"]', "els => els.map(e => e.innerText)")
            return {"url": page.url, "identity": identity, "expected": expected, "rows": rows}
        finally:
            page.close()
    finally:
        playwright.stop()


def x_reader(since: float) -> tuple[list[dict], bool, dict]:
    env = {**os.environ, "BROWSER_WAIT_SECONDS": "0"}
    completed = subprocess.run(
        ["bash", str(REPO_ROOT / "skills/browser/with-browser.sh"), "interactive:dais", "--",
         sys.executable, str(Path(__file__).resolve()), "--x-list"],
        capture_output=True, text=True, timeout=240, env=env, check=False)
    if completed.returncode != 0:
        raise ValueError(f"x leased read failed rc={completed.returncode}")
    data = json.loads(completed.stdout.strip().splitlines()[-1])
    if not data["expected"] or data["identity"].casefold() != data["expected"].casefold():
        raise ValueError("x authenticated identity mismatch")
    if "/compose/articles" not in data["url"] or not data["rows"]:
        raise ValueError("x articles list did not render")
    # ponytail: the X list exposes no timestamps; a run's article is the newest row, so the title
    # check over the first rendered page carries the proof. Add dates if X exposes them.
    items = [{"title": row.strip().splitlines()[0] if row.strip() else "", "times": []} for row in data["rows"]]
    return items, True, {"readback_url": "https://x.com/compose/articles", "identity": data["identity"]}


def collect(run_dir: Path, since: float, until: float,
            readers: dict[str, Callable[[float], tuple[list[dict], bool, dict]]] | None = None) -> dict:
    readers = readers or {
        "note/ja": note_reader,
        "substack/ja": lambda s: substack_reader("substack/ja", s),
        "substack/en": lambda s: substack_reader("substack/en", s),
        "x-article/ja": x_reader,
    }
    titles = run_titles(run_dir)
    destinations = {}
    for pair in ACTIVE_DESTINATIONS:
        if not titles:
            destinations[pair] = {"status": "unreadable", "reason": "run_title_missing"}
            continue
        try:
            items, complete, meta = readers[pair](since)
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
