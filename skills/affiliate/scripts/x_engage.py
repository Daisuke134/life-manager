#!/usr/bin/env python3
"""Engagement-only runner for the @selawmqt browser (CDP 9326).

Reads unchecked lines under the heading "Engagement for Mac mini" in the X
queue file and performs exactly one of: like, repost, reply. It never opens
the compose box for a new post and never quotes. Any unrecognized line in the
section stops the whole run before any browser action (fail closed).

Line grammar (one action per line):
  - [ ] like https://x.com/<user>/status/<id>
  - [ ] repost https://x.com/<user>/status/<id>
  - [ ] reply https://x.com/<user>/status/<id> :: <exact reply text>
Done lines are rewritten as:
  - [x] <original action text> → <result url> (YYYY-MM-DD HH:MM JST)
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
HEADING = re.compile(r"^(#{1,6})\s+Engagement for Mac mini\s*$")
ANY_HEADING = re.compile(r"^(#{1,6})\s")
STATUS_URL = r"https://(?:x|twitter)\.com/[A-Za-z0-9_]{1,15}/status/\d{1,25}"
LINE = re.compile(
    rf"^- \[ \] (?P<kind>like|repost) (?P<url>{STATUS_URL})\s*$"
    rf"|^- \[ \] (?P<rkind>reply) (?P<rurl>{STATUS_URL}) :: (?P<text>\S.*?)\s*$"
)
DONE = re.compile(r"^- \[[xX]\] ")
COMMENT = re.compile(r"^\s*<!--.*-->\s*$")
CAPS = {"like": 30, "repost": 10, "reply": 10}
ENABLE_ENV = "AFFILIATE_X_ENGAGE_ENABLED"
MAX_REPLY_CHARS = 280


class EngageError(Exception):
    pass


def parse_section(text):
    """Return (actions, error). actions: list of (line_index, kind, url, reply_text)."""
    lines = text.split("\n")
    start = level = None
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if match:
            if start is not None:
                return [], "duplicate Engagement heading"
            start, level = index, len(match.group(1))
    if start is None:
        return [], None
    actions = []
    for index in range(start + 1, len(lines)):
        line = lines[index]
        heading = ANY_HEADING.match(line)
        if heading and len(heading.group(1)) <= level:
            break
        if not line.strip() or DONE.match(line) or COMMENT.match(line):
            continue
        match = LINE.match(line)
        if not match:
            return [], f"unrecognized line {index + 1}"
        if match.group("kind"):
            actions.append((index, match.group("kind"), match.group("url"), None))
        else:
            reply = match.group("text")
            if len(reply) > MAX_REPLY_CHARS:
                return [], f"reply too long on line {index + 1}"
            actions.append((index, "reply", match.group("rurl"), reply))
    return actions, None


def today():
    return datetime.now(JST).date().isoformat()


def load_counters(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if data.get("day") != today():
        data = {"day": today(), "like": 0, "repost": 0, "reply": 0}
    return data


def atomic_write(path, payload):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)
    os.replace(tmp, path)


def mark_done(path, line_index, result_url):
    lines = path.read_text(encoding="utf-8").split("\n")
    line = lines[line_index]
    if not line.startswith("- [ ] "):
        raise EngageError("queue line moved; refusing to rewrite")
    stamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    lines[line_index] = f"- [x] {line[6:]} → {result_url} ({stamp})"
    atomic_write(path, "\n".join(lines))


def log(event, **fields):
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


class Browser:
    """Minimal CDP driver for one X tab. Only like/repost/reply buttons."""

    def __init__(self, host, port):
        from provider_cli import cdp_call, read_json
        from websocket import create_connection
        self._call = cdp_call
        targets = [t for t in read_json(f"http://{host}:{port}/json/list")
                   if t.get("type") == "page" and "x.com" in t.get("url", "")]
        if not targets:
            raise EngageError("no X tab on the engagement browser")
        self.ws = create_connection(
            f"ws://{host}:{port}/devtools/page/{targets[0]['id']}",
            timeout=30, max_size=None, suppress_origin=True)
        self.rid = 1

    def call(self, method, params=None):
        self.rid += 1
        return self._call(self.ws, self.rid, method, params)

    def eval(self, expression):
        result = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True})
        return result.get("result", {}).get("value")

    def goto(self, url):
        self.call("Page.enable")
        self.call("Page.navigate", {"url": url})
        for _ in range(30):
            time.sleep(1)
            if self.eval("document.readyState") == "complete" and self.eval(
                    "!!document.querySelector('article[data-testid=\"tweet\"]')"):
                time.sleep(2)
                return
        raise EngageError("status page did not render")

    def article_js(self, status_id):
        return ("[...document.querySelectorAll('article[data-testid=\"tweet\"]')]"
                f".find(a => [...a.querySelectorAll('a[href*=\"/status/{status_id}\"]')]"
                ".some(x => /\\/status\\/" + status_id + "(\\/|$|\\?)/.test(x.getAttribute('href'))))")

    def click_in_article(self, status_id, testid):
        return self.eval(f"""(() => {{ const a = {self.article_js(status_id)};
            if (!a) return 'no_article';
            const b = a.querySelector('[data-testid="{testid}"]');
            if (!b) return 'missing';
            b.scrollIntoView({{block: 'center'}}); b.click(); return 'clicked'; }})()""")

    def has_in_article(self, status_id, testid):
        return bool(self.eval(f"""(() => {{ const a = {self.article_js(status_id)};
            return !!(a && a.querySelector('[data-testid="{testid}"]')); }})()"""))


def status_id_of(url):
    return url.rstrip("/").rsplit("/", 1)[1]


def do_like(browser, url):
    sid = status_id_of(url)
    browser.goto(url)
    if browser.has_in_article(sid, "unlike"):
        return url
    if browser.click_in_article(sid, "like") != "clicked":
        raise EngageError("like button not found")
    time.sleep(2)
    if not browser.has_in_article(sid, "unlike"):
        raise EngageError("like not confirmed")
    return url


def do_repost(browser, url):
    sid = status_id_of(url)
    browser.goto(url)
    if browser.has_in_article(sid, "unretweet"):
        return url
    if browser.click_in_article(sid, "retweet") != "clicked":
        raise EngageError("repost button not found")
    time.sleep(1.5)
    # Only the plain Repost menu item; Quote is never clicked.
    clicked = browser.eval("""(() => { const b = document.querySelector('[data-testid="retweetConfirm"]');
        if (!b) return false; b.click(); return true; })()""")
    if not clicked:
        browser.eval("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")
        raise EngageError("repost confirm not found")
    time.sleep(2)
    if not browser.has_in_article(sid, "unretweet"):
        raise EngageError("repost not confirmed")
    return url


def do_reply(browser, url, text, handle):
    sid = status_id_of(url)
    browser.goto(url)
    if browser.click_in_article(sid, "reply") != "clicked":
        raise EngageError("reply button not found")
    time.sleep(2)
    # The reply dialog must exist and target this status; otherwise this could be a new post.
    dialog_ok = browser.eval("""(() => { const d = document.querySelector('[role="dialog"]');
        return !!(d && d.querySelector('[data-testid="tweetTextarea_0"]')
          && /Replying to|返信先/.test(d.innerText)); })()""")
    if not dialog_ok:
        browser.eval("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")
        raise EngageError("reply dialog not confirmed; refusing to type")
    browser.eval("""document.querySelector('[role="dialog"] [data-testid="tweetTextarea_0"]').focus()""")
    browser.call("Input.insertText", {"text": text})
    time.sleep(1)
    typed = browser.eval("""document.querySelector('[role="dialog"] [data-testid="tweetTextarea_0"]').innerText""")
    if (typed or "").strip() != text.strip():
        raise EngageError("reply text mismatch; not sent")
    sent = browser.eval("""(() => { const d = document.querySelector('[role="dialog"]');
        const b = d && d.querySelector('[data-testid="tweetButton"]');
        if (!b || b.getAttribute('aria-disabled') === 'true') return false; b.click(); return true; })()""")
    if not sent:
        raise EngageError("reply send button unavailable")
    time.sleep(5)
    browser.goto(f"https://x.com/{handle}/with_replies")
    found = browser.eval("""(() => { const want = %s;
        for (const a of document.querySelectorAll('article[data-testid="tweet"]')) {
          const t = a.querySelector('[data-testid="tweetText"]');
          if (t && t.innerText.trim() === want.trim()) {
            const l = a.querySelector('a[href*="/status/"] time')?.closest('a');
            if (l) return l.href; } } return null; })()""" % json.dumps(text))
    return found or f"{url} (reply sent; own URL not found yet)"


def run(args):
    queue = Path(args.queue).expanduser()
    state = Path(args.state).expanduser()
    if not args.dry_run and os.environ.get(ENABLE_ENV) != "1":
        log("x_engage_disabled", reason=f"{ENABLE_ENV} != 1")
        return 0
    try:
        text = queue.read_text(encoding="utf-8")
    except OSError:
        log("x_engage_no_queue", queue=str(queue))
        return 0
    actions, error = parse_section(text)
    if error:
        log("x_engage_fail_closed", reason=error)
        return 2
    counters_path = state / "counters.json"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = open(state / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("x_engage_busy")
        return 0
    counters = load_counters(counters_path)
    browser = None
    done = 0
    for line_index, kind, url, reply in actions:
        if args.max_actions and done >= args.max_actions:
            break
        if counters[kind] >= CAPS[kind]:
            log("x_engage_cap_reached", kind=kind, line=line_index + 1)
            continue
        if args.dry_run:
            log("x_engage_plan", kind=kind, url=url, reply=reply, line=line_index + 1)
            done += 1
            continue
        try:
            browser = browser or Browser(args.cdp_host, args.cdp_port)
            if kind == "like":
                result = do_like(browser, url)
            elif kind == "repost":
                result = do_repost(browser, url)
            else:
                result = do_reply(browser, url, reply, args.handle)
        except Exception as exc:  # stop the run on the first failure
            log("x_engage_action_failed", kind=kind, url=url, error=str(exc)[:200])
            return 3
        counters[kind] += 1
        atomic_write(counters_path, json.dumps(counters))
        mark_done(queue, line_index, result)
        log("x_engage_done", kind=kind, url=url, result=result)
        done += 1
    log("x_engage_summary", dry_run=args.dry_run, actions=done, counters=counters)
    return 0


def build_parser():
    parser = argparse.ArgumentParser()
    state_root = os.environ.get("LIFE_MANAGER_STATE_ROOT", "~/.local/state/life-manager/affiliate-x-browser")
    parser.add_argument("--queue", default=os.environ.get(
        "AFFILIATE_X_ENGAGE_QUEUE", f"{state_root}/x-engage/X-QUEUE-selawmqt.md"))
    parser.add_argument("--state", default=f"{state_root}/x-engage")
    parser.add_argument("--cdp-host", default="127.0.0.1")
    parser.add_argument("--cdp-port", type=int, default=int(os.environ.get("AFFILIATE_CDP_PORT", "9326")))
    parser.add_argument("--handle", default="selawmqt")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-actions", type=int, default=0)
    return parser


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(run(build_parser().parse_args()))
