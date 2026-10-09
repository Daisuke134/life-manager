#!/usr/bin/env python3
"""browser_reel_publish.py -- post a Reel via ~/.agents/skills/ig-reels-poster
(CloakBrowser-direct, no Postiz) for a dedicated sticker account whose Postiz
channel slot is unavailable (Dais 2026-10-07: Postiz workspace hit its
channel limit for @stardust_doubutsu, "Payment Required").

Flow per call:
  1. lease the account's browser identity via skills/browser/browser-guard.sh
     (same lease contract every other loop uses for a shared CloakBrowser).
  2. open a fresh tab, confirm the account logged in on this tab is the
     target handle; if not (this browser profile hosts several sequentially
     created accounts and only remembers the most recent login), log in with
     the stored creds (~/.cloak/ig-<handle>.json) and read the email OTP via
     `gog gmail` (same technique as
     ~/.agents/skills/ig-reels-poster/scripts/ensure_post_context.py's
     fetch_verify_code -- copied in miniature here rather than reusing that
     module, since its create_context_tab() targets a different
     incognito-per-account browser shape and 404s against this shared
     single-context provisioning profile).
  3. call ig-reels-poster's post_reel against that tid (source .py if present,
     else the still-working compiled .pyc -- see PR notes).
  4. close the tab, release the lease, return the parsed JSON result.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import threading
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[4]
BROWSER_GUARD = REPO_ROOT / "skills/browser/browser-guard.sh"
CDP_PY = Path("~/.claude/skills/ig-account-create/scripts/cdp.py").expanduser()
POST_REEL_PY = Path("~/.agents/skills/ig-reels-poster/scripts/post_reel.py").expanduser()
POST_REEL_PYC = Path(
    "~/.agents/skills/ig-reels-poster/scripts/__pycache__/post_reel.cpython-314.pyc"
).expanduser()
PY314 = "/opt/homebrew/bin/python3.14"
PY3 = sys.executable


class BrowserReelError(RuntimeError):
    pass


# 2026-10-09: four shares in a row stuck on 'シェア中' (different sets each time), and one photo before
# and after cannot tell a frozen page from a slow one. Photograph the tab while post_reel runs,
# overwriting a small ring of files so the near-full disk does not grow. Observation only.
WATCH_INTERVAL_SECONDS = 20.0
WATCH_SLOTS = 6
WATCH_DIR = Path("/tmp/ig-share-watch")


def _watch_tab(tid: str, *, cdp_host: str, cdp_port: str, stop: threading.Event) -> None:
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    index = 0
    while not stop.wait(WATCH_INTERVAL_SECONDS):
        try:
            _cdp(["shot", tid, str(WATCH_DIR / f"{index % WATCH_SLOTS:02d}.png")],
                 cdp_host=cdp_host, cdp_port=cdp_port, timeout=30)
        except Exception:  # noqa: BLE001 -- an observer must never break the post
            pass
        index += 1


def _cdp(tid_cmd: list[str], *, cdp_host: str, cdp_port: str, timeout: int = 60) -> str:
    env = {**os.environ, "CDP_HOST": cdp_host, "CDP_PORT": cdp_port}
    done = subprocess.run(
        [PY3, str(CDP_PY), *tid_cmd], capture_output=True, text=True, timeout=timeout, env=env,
    )
    if done.returncode != 0:
        raise BrowserReelError(f"cdp.py {tid_cmd[0]} failed: {done.stderr[-500:]}")
    return done.stdout.strip()


def _lease(identity: str) -> str:
    done = subprocess.run(
        [str(BROWSER_GUARD), "acquire", identity], capture_output=True, text=True, timeout=30,
    )
    if done.returncode != 0:
        raise BrowserReelError(f"browser lease unavailable for {identity}: {done.stdout}{done.stderr}")
    return done.stdout.strip()  # http://host:port


def _release(identity: str) -> None:
    subprocess.run([str(BROWSER_GUARD), "release", identity], capture_output=True, text=True, timeout=30)


def _fetch_otp(gmail_account: str, timeout: int = 150, poll: int = 8) -> str | None:
    deadline = time.time() + timeout
    queries = [
        'in:anywhere subject:"Verify your profile" newer_than:1h',
        'in:anywhere subject:"is your Instagram code" newer_than:1h',
    ]
    seen = set()
    while time.time() < deadline:
        for query in queries:
            done = subprocess.run(
                ["gog", "gmail", "search", "--account", gmail_account, "--json", "--limit", "3", query],
                capture_output=True, text=True, timeout=30,
            )
            try:
                threads = json.loads(done.stdout).get("threads", [])
            except (ValueError, AttributeError):
                threads = []
            for thread in threads:
                thread_id = thread.get("id")
                if not thread_id or thread_id in seen:
                    continue
                seen.add(thread_id)
                read = subprocess.run(
                    ["gog", "gmail", "read", "--account", gmail_account, "--json", thread_id],
                    capture_output=True, text=True, timeout=30,
                )
                try:
                    import base64
                    payload = json.loads(read.stdout)
                    body_b64 = payload["thread"]["messages"][0]["payload"]["body"]["data"]
                    html = base64.urlsafe_b64decode(body_b64 + "===").decode("utf-8", errors="ignore")
                    match = re.search(r"\b\d{6}\b", html)
                    if match:
                        return match.group(0)
                except (KeyError, ValueError, IndexError):
                    continue
        time.sleep(poll)
    return None


_CONSENT_CHECK_JS = (
    "(function(){const ds=[...document.querySelectorAll('div[role=dialog]')];"
    "const d=ds.find(x=>(x.textContent||'').includes('次の項目に同意が必要です'));"
    "if(!d)return 'none';"
    "const boxes=[...d.querySelectorAll('input[type=checkbox]')];"
    "boxes.forEach(b=>{if(!b.checked)b.click();});"
    "const agree=[...d.querySelectorAll('[role=button]')].find(x=>(x.textContent||'').trim()==='同意する');"
    "if(agree){agree.click();return 'agreed';}"
    "return 'no-agree-btn';})()"
)
_CONSENT_CLOSE_JS = (
    "(function(){const b=[...document.querySelectorAll('[role=button],button')]"
    ".find(x=>(x.textContent||'').trim()==='閉じる');if(b){b.click();return 'closed';}return 'no-close';})()"
)


def _eval_js(tid: str, js_source: str, *, cdp_host: str, cdp_port: str) -> str:
    script = Path("/tmp") / f".lsd-eval-{os.getpid()}-{id(js_source) & 0xFFFF}.js"
    script.write_text(js_source, encoding="utf-8")
    try:
        return _cdp(["eval", tid, str(script)], cdp_host=cdp_host, cdp_port=cdp_port)
    finally:
        script.unlink(missing_ok=True)


def _dismiss_consent_interstitial(
    tid: str, *, cdp_host: str, cdp_port: str, eval_fn=None,
) -> bool:
    """Instagram sometimes shows a GDPR-style "Instagramを利用するには次の項目に
    同意が必要です" modal (4 required toggles + 同意する) that covers the whole
    page -- including the account's own profile. document.body.innerText still
    contains the obscured "プロフィールを編集" text behind it, so
    _ensure_logged_in's already-logged-in check passes while every click past
    it lands on the dialog's backdrop. This was the actual root cause of every
    "file chooser load failed" run: the real composer never opened (confirmed
    live 2026-10-07 against @stardust_doubutsu and via the failed runs'
    1-composer.png / 2-loadfail.png screenshots, which show this exact dialog,
    not the composer). Toggling the 4 required checkboxes and clicking
    同意する dismisses it for the rest of the browser profile's session.
    eval_fn(js_source) -> raw JSON string is injectable for tests; defaults to
    a real CDP eval call against tid.
    """
    if eval_fn is None:
        eval_fn = lambda js_source: _eval_js(tid, js_source, cdp_host=cdp_host, cdp_port=cdp_port)
    outcome = eval_fn(_CONSENT_CHECK_JS).strip().strip('"')
    if outcome != "agreed":
        return False
    time.sleep(2)
    eval_fn(_CONSENT_CLOSE_JS)
    time.sleep(1)
    return True


def _ensure_logged_in(tid: str, *, cdp_host: str, cdp_port: str, creds: dict) -> None:
    handle = creds["username"]
    _cdp(["nav", tid, f"https://www.instagram.com/{handle}/"], cdp_host=cdp_host, cdp_port=cdp_port)
    time.sleep(3)
    _dismiss_consent_interstitial(tid, cdp_host=cdp_host, cdp_port=cdp_port)
    page_text = _cdp(["text", tid], cdp_host=cdp_host, cdp_port=cdp_port)
    if "プロフィールを編集" in page_text or "Edit profile" in page_text:
        return  # already the right account's own profile page

    # Not logged in as this handle: reach the username/password login form.
    _cdp(
        ["nav", tid, "https://www.instagram.com/accounts/login/?force_authentication=1"],
        cdp_host=cdp_host, cdp_port=cdp_port,
    )
    time.sleep(3)
    other_profile_js = Path("/tmp") / f".lsd-other-profile-{os.getpid()}.js"
    other_profile_js.write_text(
        "(function(){const els=Array.from(document.querySelectorAll('*'));"
        "const t=els.find(e=>e.children.length===0&&e.textContent&&"
        "e.textContent.trim()==='別のプロフィールを使用');if(t){t.click();return 'clicked';}"
        "return 'already-on-login-form';})()",
        encoding="utf-8",
    )
    _cdp(["eval", tid, str(other_profile_js)], cdp_host=cdp_host, cdp_port=cdp_port)
    other_profile_js.unlink(missing_ok=True)
    time.sleep(2)

    fill_js = Path("/tmp") / f".lsd-fill-login-{os.getpid()}.js"
    fill_js.write_text(
        "(function(){const inputs=Array.from(document.querySelectorAll('input'));"
        "const user=inputs.find(i=>i.type==='text'||i.name==='username');"
        "const pass=inputs.find(i=>i.type==='password');"
        "function setVal(el,val){const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype,'value').set;setter.call(el,val);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));}"
        f"setVal(user,{json.dumps(handle)});setVal(pass,{json.dumps(creds['pw'])});"
        "return 'filled';})()",
        encoding="utf-8",
    )
    _cdp(["eval", tid, str(fill_js)], cdp_host=cdp_host, cdp_port=cdp_port)
    fill_js.unlink(missing_ok=True)
    time.sleep(1)

    click_login_js = Path("/tmp") / f".lsd-click-login-{os.getpid()}.js"
    click_login_js.write_text(
        "(function(){const btns=Array.from(document.querySelectorAll('button, div[role=\"button\"]'));"
        "const b=btns.find(x=>x.textContent&&x.textContent.trim()==='ログイン');"
        "if(b){b.click();return 'clicked';}return 'not_found';})()",
        encoding="utf-8",
    )
    _cdp(["eval", tid, str(click_login_js)], cdp_host=cdp_host, cdp_port=cdp_port)
    click_login_js.unlink(missing_ok=True)
    time.sleep(6)

    page_text = _cdp(["text", tid], cdp_host=cdp_host, cdp_port=cdp_port)
    if "コードを入力" in page_text or "コード" in page_text and "メールをご確認" in page_text:
        gmail_account = creds["email"].split("+", 1)[0] + "@" + creds["email"].split("@", 1)[1]
        code = _fetch_otp(gmail_account)
        if not code:
            raise BrowserReelError(f"email OTP for {handle} did not arrive in time")
        otp_js = Path("/tmp") / f".lsd-otp-{os.getpid()}.js"
        otp_js.write_text(
            "(function(){const inputs=Array.from(document.querySelectorAll('input'));"
            "const field=inputs.find(i=>i.offsetParent!==null);"
            "function setVal(el,val){const setter=Object.getOwnPropertyDescriptor("
            "window.HTMLInputElement.prototype,'value').set;setter.call(el,val);"
            "el.dispatchEvent(new Event('input',{bubbles:true}));}"
            f"if(field){{setVal(field,{json.dumps(code)});return 'filled';}}return 'not_found';}})()",
            encoding="utf-8",
        )
        _cdp(["eval", tid, str(otp_js)], cdp_host=cdp_host, cdp_port=cdp_port)
        otp_js.unlink(missing_ok=True)
        time.sleep(1)
        click_next_js = Path("/tmp") / f".lsd-click-next-{os.getpid()}.js"
        click_next_js.write_text(
            "(function(){const btns=Array.from(document.querySelectorAll('button, div[role=\"button\"]'));"
            "const b=btns.find(x=>x.textContent&&x.textContent.trim()==='次へ');"
            "if(b){b.click();return 'clicked';}return 'not_found';})()",
            encoding="utf-8",
        )
        _cdp(["eval", tid, str(click_next_js)], cdp_host=cdp_host, cdp_port=cdp_port)
        click_next_js.unlink(missing_ok=True)
        time.sleep(6)

    _cdp(["nav", tid, f"https://www.instagram.com/{handle}/"], cdp_host=cdp_host, cdp_port=cdp_port)
    time.sleep(3)
    page_text = _cdp(["text", tid], cdp_host=cdp_host, cdp_port=cdp_port)
    if "プロフィールを編集" not in page_text and "Edit profile" not in page_text:
        raise BrowserReelError(f"could not confirm login as {handle} after the login flow")


def publish(
    *, video: Path, caption_file: Path, handle: str, browser_identity: str, live: bool,
) -> dict:
    creds_path = Path(f"~/.cloak/ig-{handle}.json").expanduser()
    if not creds_path.is_file():
        raise BrowserReelError(f"no stored IG credentials for {handle} at {creds_path}")
    creds = json.loads(creds_path.read_text(encoding="utf-8"))

    endpoint = _lease(browser_identity)
    match = re.fullmatch(r"https?://([^:/]+):(\d+)", endpoint)
    if not match:
        raise BrowserReelError(f"unexpected browser lease endpoint: {endpoint}")
    cdp_host, cdp_port = match.group(1), match.group(2)
    tid = None
    try:
        tid = _cdp(["new", "https://www.instagram.com/"], cdp_host=cdp_host, cdp_port=cdp_port)
        # Root cause (2026-10-07, measured): under launchd a tab has no real OS
        # window focus, so Chromium throttles it as a background/occluded tab
        # (rAF, timers, the upload/encode pipeline). post_reel.py's own compiled
        # bytecode never calls bring_front/focus, so 3 of 4 natural runs reached
        # "shared-unconfirmed" -- the share click fired but the reel never showed
        # up in the profile-href poll before the budget ran out. The identical
        # call made interactively (real window focused) always finished. cdp.py's
        # `focus` command (Page.bringToFront + Emulation.setFocusEmulationEnabled
        # + Page.setWebLifecycleState('active')) is the sibling fix
        # ig-account-warmer already uses for this exact "background tab" class of
        # problem; apply it to every new tab before any other step.
        _cdp(["focus", tid], cdp_host=cdp_host, cdp_port=cdp_port)
        _ensure_logged_in(tid, cdp_host=cdp_host, cdp_port=cdp_port, creds=creds)

        poster = POST_REEL_PY if POST_REEL_PY.is_file() else POST_REEL_PYC
        interpreter = PY3 if poster == POST_REEL_PY else PY314
        args = [interpreter, str(poster), "--video", str(video), "--caption-file", str(caption_file),
                "--handle", handle, "--tid", tid]
        if live:
            args.append("--live")
        env = {**os.environ, "CDP_HOST": cdp_host, "CDP_PORT": cdp_port}
        # post_reel.py's own internal waits can total far more than 180s on a --live
        # run: up to 100s waiting for the video to load, ~25s clicking through the
        # cover/trim step, then (live only) up to 340s polling the profile for the
        # new reel href to reconcile (range(20) * (12s sleep + nav + 5s settle)).
        # A 180s subprocess timeout killed a confirmed-live run here on 2026-10-07
        # (TimeoutExpired fired after シェア had already been clicked -- the reel
        # published on Instagram's side, but this process never saw the receipt and
        # crashed instead of returning it). 540s covers the measured worst case with
        # headroom.
        stop = threading.Event()
        watcher = threading.Thread(
            target=_watch_tab, kwargs={"tid": tid, "cdp_host": cdp_host, "cdp_port": cdp_port, "stop": stop},
            daemon=True,
        )
        watcher.start()
        try:
            done = subprocess.run(args, capture_output=True, text=True, timeout=540, env=env)
        finally:
            stop.set()
            watcher.join(timeout=5)
        try:
            result = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            result = {}
        if done.returncode != 0 and not result:
            raise BrowserReelError(f"post_reel failed: {done.stderr[-1000:]}")
        return result
    finally:
        if tid:
            _cdp(["close", tid], cdp_host=cdp_host, cdp_port=cdp_port)
        _release(browser_identity)
