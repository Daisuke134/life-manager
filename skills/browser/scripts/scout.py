#!/usr/bin/env python3
"""scout — go LOOK at the people who are already winning, and bring back what they actually do.

Articles teach the general theory; the deepest signal is on the actual winning pages — a top
seller's profile photo and 自己紹介, a viral clip's thumbnail and first caption, a best-selling
app's screenshots and onboarding. Every loop should study winners every improve cycle, not just
read tips. This is the shared TOOL that fetches those pages. It does NOT decide who the winners
are or what to copy — the loop's model does that (judgment belongs to the model, never here).

    python3 scout.py '<json>'      # {"urls":["..."], "mode":"public|browser"}
    echo '<json>' | python3 scout.py

Returns {"observations": {url: markdown_excerpt, ...}, "errors": {url: reason}}.
  mode=public  (default): crawl4ai `crwl` — for pages anyone can see (category/ranking/public profile)
  mode=browser           : drive the logged-in daily-driver over CDP — for pages that need a session

The loop then reads these observations and forms ONE testable hypothesis (a profile/listing/
thumbnail/price/caption change) that it applies as a single experiment and measures against its funnel.
"""
import json
import os
import subprocess
import sys
import urllib.request

import target_ownership

try:
    import websockets
except ImportError:
    websockets = None

CRWL = os.path.expanduser("~/.local/bin/crwl")
EXCERPT = 6000  # keep each page small — the model needs the signal, not the whole DOM


def _browser_ws():
    base = os.environ.get("CLOAK_CDP_BASE_URL", "http://localhost:9222").rstrip("/")
    data = json.loads(
        urllib.request.urlopen(f"{base}/json/version", timeout=8).read()
    )
    return data["webSocketDebuggerUrl"]


def _public(url):
    """Fetch a public page as markdown via crawl4ai."""
    exe = CRWL if os.path.exists(CRWL) else "crwl"
    r = subprocess.run([exe, url, "-o", "markdown"], capture_output=True, text=True, timeout=120)
    md = (r.stdout or "").strip()
    if not md:
        raise RuntimeError((r.stderr or "empty output")[:160])
    return md[:EXCERPT]


def _browser(url):
    """Fetch a login-required page by driving the running daily-driver over CDP."""
    import asyncio
    if websockets is None:
        raise RuntimeError("pip install websockets")

    async def run():
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

            t = await call("Target.createTarget", {"url": url})
            tid = t["targetId"]
            claimed = False
            try:
                target_ownership.claim_target(tid, "browser-scout")
                claimed = True
                sess = (await call("Target.attachToTarget", {"targetId": tid, "flatten": True}))["sessionId"]
                await asyncio.sleep(4)
                r = await call("Runtime.evaluate",
                               {"expression": "document.body.innerText", "returnByValue": True}, sess=sess)
                return (r.get("result", {}).get("value") or "")[:EXCERPT]
            finally:
                try:
                    await call("Target.closeTarget", {"targetId": tid})
                finally:
                    if claimed:
                        target_ownership.release_target(tid, "browser-scout")

    return asyncio.run(run())


def scout(payload):
    urls = payload.get("urls") or []
    mode = payload.get("mode", "public")
    if not urls:
        return {"ok": False, "reason": "usage: {\"urls\":[...], \"mode\":\"public|browser\"}"}
    fetch = _browser if mode == "browser" else _public
    obs, errs = {}, {}
    for u in urls[:12]:  # a bounded batch; the loop calls again for more
        try:
            obs[u] = fetch(u)
        except Exception as e:
            errs[u] = f"{type(e).__name__}: {e}"[:160]
    return {"ok": bool(obs), "observations": obs, "errors": errs}


if __name__ == "__main__":
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    try:
        out = scout(json.loads(raw))
    except Exception as e:
        out = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0 if out.get("ok") else 1)
