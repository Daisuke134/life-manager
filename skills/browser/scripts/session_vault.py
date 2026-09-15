#!/usr/bin/env python3
"""Keep the logins alive across crashes so no human ever has to re-authenticate.

Cookies live inside the Chromium profile, and a hard kill (OOM, crash, an unlucky cleanup) can take
recent ones with it. Losing them means re-login, and re-login means 2FA, and 2FA means a human —
which is exactly the thing the loops must never need.

So: snapshot every cookie the browser holds into a JSON vault on a schedule, and restore from the
vault when a session turns out to be gone. Same idea as Playwright's storageState ("produce
authenticated browser state and save it to a file... reuse this state and start already
authenticated"), done over CDP against the running daily-driver.

    python3 session_vault.py dump      # snapshot every cookie -> auth-state.json
    python3 session_vault.py restore   # push the vault back into the live browser
    python3 session_vault.py status    # how many cookies, which origins, how old
    python3 session_vault.py keepalive <url> [url...]   # navigate authed pages to extend server-side session + detect logout
    python3 session_vault.py totp <secret_key_or_@service>  # print a fresh TOTP code so login can finish without a human

Why keepalive: cookie restore only saves a HARD crash. It does NOT save (b) the server invalidating
the session or (c) a 2FA/passkey re-prompt. keepalive hits an authenticated page on a schedule so the
server keeps the session warm, and reports logged_out=true the moment a page redirects to /login — so
a loop can re-auth itself early instead of discovering it mid-task.

Why totp: authenticator-app 2FA is the one re-login path a machine CAN finish alone. Store the TOTP
secret once (issued when 2FA is enabled) and generate the 6-digit code with pyotp — no phone, no human.
Google passkey and Apple-ID-SMS are NOT solvable in-browser; earn accounts must use an AI-owned account
with app-based 2FA, never Dais's passkey-locked Google.
"""
import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
import shutil
import sys
import time
import urllib.request

import target_ownership
from browser_session_contract import browser_mode, configured_endpoint, normalize_endpoint

CDP_PORT = os.environ.get("SESSION_VAULT_PORT", "9222")
CDP = f"http://127.0.0.1:{CDP_PORT}"
VAULT_DIR = os.path.expanduser(os.environ.get("SESSION_VAULT_DIR", "~/.cloak/vault/daily-driver"))
VAULT = os.path.join(VAULT_DIR, "auth-state.json")
TOTP_SECRETS = os.path.join(VAULT_DIR, "totp-secrets.json")  # {"@coconala": "BASE32SECRET", ...}, chmod 600
KEEP_BACKUPS = 8


@contextlib.contextmanager
def _vault_lock():
    os.makedirs(VAULT_DIR, exist_ok=True)
    with open(VAULT + ".lock", "a+", encoding="utf-8") as handle:
        os.chmod(VAULT + ".lock", 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

try:
    import websockets
except ImportError:
    print(json.dumps({"ok": False, "reason": "pip install websockets"}))
    sys.exit(1)


def _browser_ws():
    browser_mode()
    if os.environ.get("LIFE_MANAGER_BROWSER_ENDPOINT") or os.environ.get("CLOAK_CDP_BASE_URL"):
        endpoint = configured_endpoint()
    else:
        endpoint = normalize_endpoint(CDP)
    d = json.loads(urllib.request.urlopen(f"{endpoint}/json/version", timeout=8).read())
    return d["webSocketDebuggerUrl"]


async def _call(method, params=None):
    async with websockets.connect(_browser_ws(), max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == 1:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})


# Which origins are worth carrying localStorage for. Cookies cover auth on most sites,
# but some SPAs keep the auth/session token in localStorage — so a hard kill that loses the
# profile also loses login unless we snapshot it too (steel-browser: "cookies AND local
# storage across requests"). Keep this list to the sites the loops actually log into.
LS_ORIGINS = [
    "https://coconala.com", "https://www.instagram.com", "https://www.tiktok.com",
    "https://www.youtube.com", "https://x.com",
]


async def _localstorage(op, data=None):
    """op='read' -> {origin: {k:v}}; op='write' -> push data back. One tab per origin over CDP."""
    out = {}
    async with websockets.connect(_browser_ws(), max_size=64 * 1024 * 1024) as ws:
        mid = [0]

        async def call(method, params=None, sess=None):
            mid[0] += 1
            i = mid[0]
            m = {"id": i, "method": method, "params": params or {}}
            if sess:
                m["sessionId"] = sess
            await ws.send(json.dumps(m))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == i:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg.get("result", {})

        origins = LS_ORIGINS if op == "read" else list((data or {}).keys())
        for origin in origins:
            tid = None
            claimed = False
            try:
                t = await call("Target.createTarget", {"url": origin})
                tid = t["targetId"]
                target_ownership.claim_target(tid, "session-vault-localstorage")
                claimed = True
                sess = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["sessionId"]
                await asyncio.sleep(2)
                if op == "read":
                    r = await call("Runtime.evaluate",
                                   {"expression": "JSON.stringify(Object.fromEntries(Object.entries(localStorage)))",
                                    "returnByValue": True}, sess=sess)
                    val = r.get("result", {}).get("value")
                    if val and val != "{}":
                        out[origin] = json.loads(val)
                else:
                    kv = data.get(origin, {})
                    expr = "".join(f"localStorage.setItem({json.dumps(k)},{json.dumps(v)});" for k, v in kv.items())
                    if expr:
                        await call("Runtime.evaluate", {"expression": expr}, sess=sess)
            except Exception:
                pass  # one bad origin must not abort the whole snapshot
            finally:
                if tid:
                    try:
                        await call("Target.closeTarget", {"targetId": tid})
                    except Exception:
                        pass
                    finally:
                        if claimed:
                            target_ownership.release_target(
                                tid, "session-vault-localstorage"
                            )
    return out


# task #75 (2026-07-17, spec docs/loop-engineering/56): X rotates ct0 (its CSRF cookie)
# alongside auth_token, and a dump taken mid-rotation or from a half-dead tab can capture
# auth_token WITHOUT a valid ct0 (or neither). Overwriting a previously-healthy vault with that
# half-dead snapshot is worse than not dumping at all -- the next restore() would push a
# guaranteed-broken pair. So each site in SITE_HEALTH_REQUIRED must have ALL of its listed
# cookie names present in the same dump, or that site's cookies are spliced back in from the
# PRIOR vault (if it had a healthy set) instead of being overwritten. Other sites are unaffected.
SITE_HEALTH_REQUIRED = {"x.com": ("auth_token", "ct0")}


def _guard_degraded_site_cookies(new_cookies):
    """Return new_cookies with any SITE_HEALTH_REQUIRED site's cookies replaced by the prior
    vault's cookies for that site, if the new dump is missing a required cookie name for it and
    the prior vault had a complete set. Never invents cookies; only preserves a known-good set."""
    if not os.path.exists(VAULT):
        return new_cookies, []
    try:
        prior = json.load(open(VAULT)).get("cookies", [])
    except Exception:
        return new_cookies, []

    degraded_sites = []
    result = list(new_cookies)
    for site, required in SITE_HEALTH_REQUIRED.items():
        new_site_names = {c["name"] for c in new_cookies if site in c.get("domain", "")}
        if all(r in new_site_names for r in required):
            continue  # healthy in the new dump, nothing to do
        prior_site_cookies = [c for c in prior if site in c.get("domain", "")]
        prior_site_names = {c["name"] for c in prior_site_cookies}
        if not all(r in prior_site_names for r in required):
            continue  # prior vault wasn't healthy either -- nothing good to preserve
        degraded_sites.append(site)
        result = [c for c in result if site not in c.get("domain", "")] + prior_site_cookies
    return result, degraded_sites


def dump():
    res = _run(_call("Storage.getCookies"))
    cookies = res.get("cookies", [])
    if not cookies:
        # never overwrite a good vault with an empty snapshot from a half-dead browser
        return {"ok": False, "reason": "browser returned zero cookies; vault left untouched"}

    try:
        local_storage = _run(_localstorage("read"))
    except Exception:
        local_storage = {}

    with _vault_lock():
        cookies, degraded_sites = _guard_degraded_site_cookies(cookies)
        if os.path.exists(VAULT):
            backup = os.path.join(VAULT_DIR, f"auth-state.{int(os.path.getmtime(VAULT))}.json")
            shutil.copy2(VAULT, backup)
            backups = sorted(f for f in os.listdir(VAULT_DIR)
                             if f.startswith("auth-state.") and f != "auth-state.json")
            for old in backups[:-KEEP_BACKUPS]:
                os.remove(os.path.join(VAULT_DIR, old))

        payload = {"ts": int(time.time()), "cookies": cookies, "localStorage": local_storage}
        tmp = f"{VAULT}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, VAULT)
        os.chmod(VAULT, 0o600)  # cookies + tokens are credentials

    domains = sorted({c.get("domain", "") for c in cookies})
    result = {"ok": True, "cookies": len(cookies), "domains": len(domains),
              "localStorage_origins": len(local_storage), "vault": VAULT}
    if degraded_sites:
        result["degraded_sites_preserved_from_prior_vault"] = degraded_sites
    return result


def _run(coro):
    """Run one coroutine whether or not a caller already has a loop running.

    `dump()` and `restore()` are called both from plain scripts and from inside async
    callers -- the CrowdWorks account flow drives a page and then asks for a dump, and
    `asyncio.run` refuses with "cannot be called from a running event loop", which reached
    that lane as the single word vault_dump_failed. Handing the coroutine to a worker thread
    with its own loop keeps one entry point working for both callers.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _restorable_cookie(cookie):
    """Return one saved cookie in the shape the running browser will accept.

    A partitioned cookie was stored with `partitionKey` as the site string. Chrome now wants
    an object, and rejects the entire `Storage.setCookies` call when one cookie disagrees --
    `Failed to deserialize params.cookies.partitionKey` -- so sixteen cookies out of a hundred
    and twenty made a whole session unrestorable. A key that is neither shape carries nothing
    the browser can use and is dropped rather than guessed at.
    """
    if not isinstance(cookie, dict) or "partitionKey" not in cookie:
        return cookie
    partition = cookie["partitionKey"]
    if isinstance(partition, dict):
        return cookie
    if isinstance(partition, str) and partition:
        return {**cookie, "partitionKey": {"topLevelSite": partition,
                                           "hasCrossSiteAncestor": False}}
    return {key: value for key, value in cookie.items() if key != "partitionKey"}


def restore():
    if not os.path.exists(VAULT):
        return {"ok": False, "reason": "no vault yet — run dump while logged in"}
    saved = json.load(open(VAULT))
    cookies = saved.get("cookies", [])
    if not cookies:
        return {"ok": False, "reason": "vault is empty"}
    cookies = [_restorable_cookie(cookie) for cookie in cookies]
    _run(_call("Storage.setCookies", {"cookies": cookies}))
    ls = saved.get("localStorage", {})
    if ls:
        try:
            _run(_localstorage("write", ls))
        except Exception:
            pass
    return {"ok": True, "restored": len(cookies), "localStorage_origins": len(ls),
            "age_hours": round((time.time() - saved.get("ts", 0)) / 3600, 1)}


def status():
    if not os.path.exists(VAULT):
        return {"ok": False, "reason": "no vault yet"}
    saved = json.load(open(VAULT))
    cookies = saved.get("cookies", [])
    interesting = sorted({c["domain"] for c in cookies if any(
        k in c.get("domain", "") for k in ("coconala", "instagram", "youtube", "google", "x.com", "tiktok", "promote"))})
    return {"ok": True, "cookies": len(cookies), "age_hours": round((time.time() - saved.get("ts", 0)) / 3600, 1),
            "logged_in_origins": interesting}


def _has_instagram_sessionid(cookies):
    """True if any cookie is a live instagram.com sessionid. Used because IG lets a half-dead
    session (ds_user_id survives, sessionid expired) sit on the feed WITHOUT ever redirecting to
    /login — so URL-redirect detection alone false-negatives logged_out on Instagram."""
    return any(
        c.get("name") == "sessionid" and "instagram.com" in c.get("domain", "")
        for c in cookies
    )


def _logged_out_for(url, final, cookies, page_text=""):
    """Decide logged_out for one keepalive page.

    - URL redirected to /login /signin etc -> logged_out (works for coconala and most sites).
    - instagram.com specifically -> ALSO require a live sessionid cookie, since IG does not
      redirect a half-dead session to /login. OR'd with the redirect check per spec: either
      signal alone is enough to declare logged_out on instagram.com.
    - x.com specifically -> ALSO check the rendered page text for "Something went wrong", the
      generic error X's client renders when a stale/invalidated auth_token cookie is present —
      it does NOT redirect to /login (a hard-crashed React tree just sits on the current URL),
      so URL-redirect detection alone false-negatives here exactly like the Instagram case
      (real incident 2026-07-17: keepalive reported logged_out=false while a live screenshot
      showed "Something went wrong" on x.com/home -- this cost a full manual re-diagnosis).
    - zenn.dev specifically -> its login route is /enter (not /login), a real incident
      (2026-07-17, task #75): keepalive on https://zenn.dev/dashboard reported logged_out=false
      while the actual final URL was https://zenn.dev/enter?redirect_to=%2Fdashboard, a genuine
      dead Google-OAuth session that the generic /login-only check missed entirely.
    - non-instagram/non-x/non-zenn domains: only the generic redirect check applies.
    """
    redirected = any(k in final.lower() for k in ("/login", "/signin", "/sign_in", "accounts.google.com/signin"))
    if "instagram.com" in url.lower() and not _has_instagram_sessionid(cookies):
        return True
    if "x.com" in url.lower() and "something went wrong" in (page_text or "").lower():
        return True
    if "zenn.dev" in url.lower() and "/enter" in final.lower():
        return True
    return redirected


async def _keepalive(urls):
    """Open each url in its own tab, wait for it to settle, and see where it ended up.
    A redirect to a /login or /signin URL means the server dropped the session. For
    instagram.com pages, also check the live sessionid cookie; for x.com pages, also read the
    rendered page text for a "Something went wrong" crash state (see _logged_out_for) — neither
    site reliably redirects a half-dead session to /login."""
    results = []
    async with websockets.connect(_browser_ws(), max_size=64 * 1024 * 1024) as ws:
        mid = [0]

        async def call(method, params=None, sess=None):
            mid[0] += 1
            i = mid[0]
            m = {"id": i, "method": method, "params": params or {}}
            if sess:
                m["sessionId"] = sess
            await ws.send(json.dumps(m))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == i:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg.get("result", {})

        for url in urls:
            t = await call("Target.createTarget", {"url": url})
            tid = t["targetId"]
            claimed = False
            try:
                target_ownership.claim_target(tid, "session-vault-keepalive")
                claimed = True
                sess = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["sessionId"]
                await asyncio.sleep(4)  # let redirects/JS settle
                hist = await call("Page.getNavigationHistory", sess=sess)
                entries = hist.get("entries", [])
                final = entries[hist.get("currentIndex", len(entries) - 1)]["url"] if entries else url
                cookies = []
                if "instagram.com" in url.lower():
                    cookies_res = await call("Storage.getCookies", {})
                    cookies = cookies_res.get("cookies", [])
                page_text = ""
                if "x.com" in url.lower():
                    r = await call("Runtime.evaluate",
                                   {"expression": "document.body ? document.body.innerText : ''",
                                    "returnByValue": True}, sess=sess)
                    page_text = r.get("result", {}).get("value", "") or ""
                logged_out = _logged_out_for(url, final, cookies, page_text)
                results.append({"url": url, "final": final, "logged_out": logged_out})
            finally:
                try:
                    await call("Target.closeTarget", {"targetId": tid})
                finally:
                    if claimed:
                        target_ownership.release_target(
                            tid, "session-vault-keepalive"
                        )
    return results


def keepalive(urls):
    if not urls:
        return {"ok": False, "reason": "usage: keepalive <url> [url...]"}
    res = _run(_keepalive(urls))
    any_out = any(r["logged_out"] for r in res)
    return {"ok": not any_out, "logged_out": any_out, "pages": res}


# task #75 (2026-07-17): password re-login self-heal for X specifically. A keepalive-detected
# logged_out=true on x.com should not just sit there until a human notices -- but X actively
# monitors login() frequency and can flag/kill an account for repeated automated login attempts
# (same warning twscrape/twikit document), so this must fire AT MOST ONCE per incident, never on
# every 30-min tick. RELOGIN_COOLDOWN_SEC (6h) plus a marker file written BEFORE the attempt
# (not after) enforces "try once, then wait" even across overlapping/retried tick invocations.
RELOGIN_COOLDOWN_SEC = 6 * 3600
X_RELOGIN_MARKER = os.path.join(VAULT_DIR, ".x-relogin-attempted")
COCONALA_RELOGIN_MARKER = os.path.join(VAULT_DIR, ".coconala-relogin-attempted")
COCONALA_CREDENTIALS = os.path.expanduser("~/.local/share/anicca/credentials.json")
X_LOGIN_USERNAME = os.environ.get("X_LOGIN_USERNAME", "aniccaen")


async def _relogin_x():
    async with websockets.connect(_browser_ws(), max_size=64 * 1024 * 1024) as ws:
        mid = [0]

        async def call(method, params=None, sess=None):
            mid[0] += 1
            i = mid[0]
            m = {"id": i, "method": method, "params": params or {}}
            if sess:
                m["sessionId"] = sess
            await ws.send(json.dumps(m))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == i:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg.get("result", {})

        async def page_text(sess):
            r = await call("Runtime.evaluate",
                            {"expression": "document.body ? document.body.innerText : ''",
                             "returnByValue": True}, sess=sess)
            return r.get("result", {}).get("value", "") or ""

        async def current_url(sess):
            r = await call("Runtime.evaluate",
                            {"expression": "location.href", "returnByValue": True}, sess=sess)
            return r.get("result", {}).get("value", "") or ""

        t = await call("Target.createTarget", {"url": "https://x.com/login"})
        tid = t["targetId"]
        claimed = False
        try:
            target_ownership.claim_target(tid, "session-vault-relogin-x")
            claimed = True
            sess = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["sessionId"]
            await asyncio.sleep(4)

            async def type_and_enter(x, y, text):
                await call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}, sess=sess)
                await call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, sess=sess)
                await asyncio.sleep(0.3)
                await call("Input.insertText", {"text": text}, sess=sess)
                await asyncio.sleep(0.3)
                await call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 13, "key": "Enter"}, sess=sess)
                await call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13, "key": "Enter"}, sess=sess)

            # username field, same coordinates verified working live 2026-07-17 (task #74)
            await type_and_enter(954, 593, X_LOGIN_USERNAME)
            await asyncio.sleep(3)

            txt = await page_text(sess)
            if "phone number" in txt.lower() or "電話番号" in txt:
                return {"ok": False, "stopped": True,
                        "reason": "phone number requested after username -- AI cannot read SMS to a personal phone, this needs Dais, per task #75 scope"}

            password = os.environ.get("TWITTER_PASSWORD", "")
            if not password:
                return {"ok": False, "reason": "TWITTER_PASSWORD not set in environment -- cannot re-login"}

            # password field, same coordinates verified working live 2026-07-17 (task #74)
            await type_and_enter(954, 350, password)
            await asyncio.sleep(4)

            txt = await page_text(sess)
            if "phone number" in txt.lower() or "電話番号" in txt:
                return {"ok": False, "stopped": True,
                        "reason": "phone number verification requested after password -- needs Dais, per task #75 scope"}
            if "something went wrong" in txt.lower():
                return {"ok": False, "reason": "X returned a generic error (anti-automation block or transient failure) after submitting credentials"}

            url = await current_url(sess)
            if "/i/jf/onboarding" in url or "/login" in url:
                return {"ok": False, "reason": f"login did not complete -- still on {url}"}

            return {"ok": True, "final_url": url}
        finally:
            try:
                await call("Target.closeTarget", {"targetId": tid})
            finally:
                if claimed:
                    target_ownership.release_target(
                        tid, "session-vault-relogin-x"
                    )


def _coconala_credentials():
    payload = json.load(open(COCONALA_CREDENTIALS))
    item = next(c for c in payload["credentials"]
                if "coconala" in str(c.get("service", "")).lower())
    email = item.get("email") or item.get("username")
    password = item["password"]
    if not email or not password:
        raise RuntimeError("coconala credentials incomplete")
    return email, password


async def _relogin_coconala():
    """Log the shared gig browser back into Coconala.

    keepalive only extends a session that is still alive; it cannot raise a dead one, and Coconala
    had no re-login path at all -- only x.com did. So when the session expired on 2026-09-01 the
    alarm fired correctly every 30 minutes for five days and nothing could act on it. Apply, Paid,
    Storefront and Reply all share this one browser and one session, so this single path restores
    all four.

    Verified by hand 2026-09-07: the same fill-and-click lands on /mypage/dashboard with the
    account's own menu rendered. The form carries a reCAPTCHA widget that a normal submit passes.
    """
    email, password = _coconala_credentials()
    async with websockets.connect(_browser_ws(), max_size=64 * 1024 * 1024) as ws:
        mid = [0]

        async def call(method, params=None, sess=None):
            mid[0] += 1
            i = mid[0]
            message = {"id": i, "method": method, "params": params or {}}
            if sess:
                message["sessionId"] = sess
            await ws.send(json.dumps(message))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == i:
                    return msg

        async def ev(expr, sess):
            got = await call("Runtime.evaluate",
                             {"expression": expr, "returnByValue": True}, sess)
            return ((got.get("result") or {}).get("result") or {}).get("value")

        made = await call("Target.createTarget", {"url": "about:blank"})
        target = (made.get("result") or {}).get("targetId")
        if not target:
            return {"ok": False, "reason": "could not open a tab"}
        attached = await call("Target.attachToTarget", {"targetId": target, "flatten": True})
        sess = (attached.get("result") or {}).get("sessionId")
        try:
            await call("Page.enable", {}, sess)
            await call("Page.navigate", {"url": "https://coconala.com/login"}, sess)
            for _ in range(40):
                if await ev("document.readyState", sess) in ("interactive", "complete"):
                    break
                await asyncio.sleep(0.3)
            await asyncio.sleep(2.5)

            filled = await ev("""(function(email,pw){
              var set=function(el,v){var s=Object.getOwnPropertyDescriptor(el.constructor.prototype,'value').set;
                s.call(el,v);
                el.dispatchEvent(new Event('input',{bubbles:true}));
                el.dispatchEvent(new Event('change',{bubbles:true}));
                el.dispatchEvent(new Event('blur',{bubbles:true}));};
              var e=document.querySelector('#UserLoginEmail'), p=document.querySelector('#UserLoginPassword');
              if(!e||!p) return 'fields_missing';
              e.focus(); set(e,email); p.focus(); set(p,pw); return 'filled';
            })(%s,%s)""" % (json.dumps(email), json.dumps(password)), sess)
            if filled != "filled":
                return {"ok": False, "reason": "login form not found"}

            clicked = await ev("""(function(){
              var b=[].slice.call(document.querySelectorAll('button'))
                .filter(function(x){return (x.innerText||'').trim()==='メールアドレスでログインする';})[0];
              if(!b) return 'button_missing';
              if(b.disabled) return 'button_disabled';
              b.click(); return 'clicked';})()""", sess)
            if clicked != "clicked":
                return {"ok": False, "reason": clicked}

            for _ in range(40):
                await asyncio.sleep(1)
                here = await ev("location.href", sess)
                if here and "/login" not in here:
                    break

            # Prove it on a page that only a logged-in account renders, not on the landing
            # redirect: Coconala sends anonymous users to the top page, so "not /login" is not proof.
            await call("Page.navigate", {"url": "https://coconala.com/mypage/dashboard"}, sess)
            for _ in range(40):
                if await ev("document.readyState", sess) in ("interactive", "complete"):
                    break
                await asyncio.sleep(0.3)
            await asyncio.sleep(2)
            url = await ev("location.href", sess)
            title = await ev("document.title", sess)
            ok = isinstance(url, str) and "/mypage/dashboard" in url and "/login" not in url
            return {"ok": ok, "url": url, "title": title,
                    "reason": None if ok else "dashboard did not render after login"}
        finally:
            await call("Target.closeTarget", {"targetId": target})


def relogin_coconala():
    """Rate-limited to one attempt per cooldown, same contract as relogin_x."""
    now = time.time()
    if os.path.exists(COCONALA_RELOGIN_MARKER):
        try:
            last = float(open(COCONALA_RELOGIN_MARKER).read().strip())
        except Exception:
            last = 0
        age = now - last
        if age < RELOGIN_COOLDOWN_SEC:
            return {"ok": False, "skipped": True,
                    "reason": f"relogin attempted {round(age/60)}min ago, cooldown is {RELOGIN_COOLDOWN_SEC//3600}h"}

    os.makedirs(VAULT_DIR, exist_ok=True)
    with open(COCONALA_RELOGIN_MARKER, "w") as handle:
        handle.write(str(now))  # before the attempt, so a crash still enforces the cooldown

    try:
        result = _run(_relogin_coconala())
    except Exception as error:
        return {"ok": False, "reason": f"{type(error).__name__}: {error}"}

    # Bank immediately. The lanes seed their isolated contexts from the vault, not from this tab,
    # so a login that is not dumped is a login they never see.
    if result.get("ok"):
        result["dump"] = dump()
    return result


def relogin_x():
    now = time.time()
    if os.path.exists(X_RELOGIN_MARKER):
        try:
            last = float(open(X_RELOGIN_MARKER).read().strip())
        except Exception:
            last = 0
        age = now - last
        if age < RELOGIN_COOLDOWN_SEC:
            return {"ok": False, "skipped": True,
                    "reason": f"relogin attempted {round(age/60)}min ago, cooldown is {RELOGIN_COOLDOWN_SEC//3600}h -- skip to avoid X flagging repeated login() attempts"}

    os.makedirs(VAULT_DIR, exist_ok=True)
    with open(X_RELOGIN_MARKER, "w") as f:
        f.write(str(now))  # write BEFORE attempting so a crash mid-attempt still enforces cooldown

    try:
        result = _run(_relogin_x())
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}

    if result.get("ok"):
        dump_result = dump()
        result["dump"] = dump_result
    return result


def totp(key):
    """Generate a fresh 6-digit code. key is a base32 secret, or @service to look it up in the vault."""
    try:
        import pyotp
    except ImportError:
        return {"ok": False, "reason": "pip install pyotp"}
    secret = key
    if key.startswith("@"):
        if not os.path.exists(TOTP_SECRETS):
            return {"ok": False, "reason": f"no {TOTP_SECRETS}; store {{\"{key}\": \"BASE32\"}} chmod 600"}
        secret = json.load(open(TOTP_SECRETS)).get(key)
        if not secret:
            return {"ok": False, "reason": f"{key} not in totp-secrets.json"}
    try:
        code = pyotp.TOTP(secret.replace(" ", "")).now()
    except Exception as e:
        return {"ok": False, "reason": f"bad secret: {e}"}
    return {"ok": True, "code": code}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    rest = sys.argv[2:]
    try:
        if cmd == "keepalive":
            out = keepalive(rest)
        elif cmd == "totp":
            out = totp(rest[0]) if rest else {"ok": False, "reason": "usage: totp <secret|@service>"}
        else:
            out = {"dump": dump, "restore": restore, "status": status,
                   "relogin_x": relogin_x, "relogin_coconala": relogin_coconala}[cmd]()
    except KeyError:
        out = {"ok": False, "reason": f"unknown command {cmd}"}
    except Exception as e:
        out = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0 if out.get("ok") else 1)
