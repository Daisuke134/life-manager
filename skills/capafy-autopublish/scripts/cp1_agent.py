#!/usr/bin/env python3
"""
cp1_agent.py — THIN, DUMB browser primitives for Capafy CP1 (Agent Card save).

This is the DETERMINISTIC TOOL half of a two-layer agentic loop. It does NOT
decide anything — it just performs one primitive action against the running
CloakBrowser daily-driver (CDP :9222) and dumps a screenshot + a compact state
readout. The JUDGMENT half is the AGENT (the running LLM) who LOOKS at the
screenshot, decides the next click/type, and calls this tool again — looping
until the real success signal ("カードを保存しました" toast / card-done URL /
server isConfirmedSkills=1) appears.

WHY it exists: the old drive_cp1.py hardcoded DOM-coordinate/text heuristics that
silently broke whenever Capafy changed its publish UI. Per Anthropic "effective
context engineering" (no brittle if-else hardcoded logic — give the model the
data + tools + let it decide), the fix is agentic, not more coordinate tuning.

Every command reconnects over CDP (stateless between calls); the Capafy tab stays
open in the browser across calls, so the agent can act incrementally.

Commands (all print a state readout; most also save a screenshot):
  open <url>                 goto url (reuse capafy tab if present, else new tab)
  shot                       screenshot + dump interactive elements
  state                      dump interactive elements only (no screenshot)
  click <x> <y>              mouse click at viewport coords, then shot
  clicktext "<text>" [nth]   click element whose trimmed text == text (nth, 0-based), then shot
  fill <idx> "<value>"       fill the idx-th field (from `state` field list) via Playwright .fill()
  typeinto <idx> "<text>"    click field idx then type char-by-char (RHF-safe), then shot
  press <key>                press a key on the active element (e.g. Enter)
  upload <idx> <path>        set_input_files on the idx-th file input
  scroll <y>                 window.scrollTo(0, y), then shot
  toast                      report whether success toast / card-done url is present

Screenshot is saved to $CP1_SHOT (default /tmp/cp1_shot.png), viewport-relative
so the (x,y) in the state readout map directly to `click <x> <y>`.
"""
import fcntl
import json, os, re, signal, sys, time, urllib.request
from urllib.parse import parse_qsl, quote, urlsplit
from playwright.sync_api import sync_playwright

SHOT = os.environ.get("CP1_SHOT", "/tmp/cp1_shot.png")
CONNECT_TIMEOUT_MS = int(os.environ.get("CP1_CONNECT_TIMEOUT_MS", "15000"))
SAFE_PAGE_VALUES = frozenset({"edit", "review", "credential", "card-done", "credential-done"})
# CP1 is a sequence of small, agent-directed commands, but all of those commands
# still share one Chromium CDP endpoint.  Serialise the *individual* CDP session:
# a second command gets a bounded wait instead of opening another Playwright driver
# and leaving both callers stuck in connect_over_cdp forever.
LOCK_PATH = os.environ.get("CP1_CDP_LOCK", "/tmp/capafy-cp1-cdp.lock")
LOCK_WAIT_SECONDS = float(os.environ.get("CP1_CDP_LOCK_WAIT_SECONDS", "20"))


class Cp1Busy(RuntimeError):
    pass


def _acquire_cdp_lock():
    lock = open(LOCK_PATH, "a+")
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock
        except BlockingIOError:
            if time.monotonic() >= deadline:
                lock.close()
                raise Cp1Busy(f"shared CDP busy for {LOCK_WAIT_SECONDS:g}s")
            time.sleep(0.2)


def _detect_cdp():
    """The daily-driver's CDP port drifts (observed 9222 -> 9223 when 9222 is
    already held by an unrelated local Chrome instance) — auto-detect instead
    of trusting a hardcoded port (self-fix-capafy-loop, 2026-07-21)."""
    override = os.environ.get("CP1_CDP_URL")
    if override:
        return override
    # Prefer the endpoint that already has a Capafy page.  On this host 9222
    # and 9223 can both be alive (different daily drivers); choosing the first
    # /json/version response sent CP1 to an unrelated browser during a drainer.
    reachable = []
    for port in (9222, 9223):
        url = f"http://localhost:{port}"
        try:
            with urllib.request.urlopen(f"{url}/json/version", timeout=2) as r:
                if r.status == 200:
                    reachable.append(url)
        except Exception:
            continue
    for url in reachable:
        try:
            with urllib.request.urlopen(f"{url}/json/list", timeout=2) as r:
                targets = json.load(r)
            if any("capafy.ai" in str(t.get("url", "")) for t in targets):
                return url
        except Exception:
            continue
    if reachable:
        return reachable[0]
    return "http://localhost:9222"  # fall back to the documented default


CDP = _detect_cdp()

# JS that returns a compact, bounded list of interactive elements with
# viewport-center coords, so the agent can both SEE (screenshot) and target
# precisely (coords). Fields (inputs/textareas/selects) are listed first with a
# stable index the agent references for fill/typeinto/upload.
STATE_JS = r"""
() => {
  const vis = (e) => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
      && r.bottom > 0 && r.top < innerHeight + 400;
  };
  const ctr = (e) => { const r = e.getBoundingClientRect();
    return { x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) }; };
  const short = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 60);

  const fields = [];
  [...document.querySelectorAll('input, textarea, select')].forEach((e) => {
    if (!vis(e) && e.type !== 'file') return;
    const c = ctr(e);
    fields.push({
      i: fields.length, tag: e.tagName.toLowerCase(),
      type: e.type || '', ph: short(e.placeholder), name: e.name || '',
      val: short(e.value || (e.selectedOptions ? [...e.selectedOptions].map(o=>o.textContent).join(',') : '')),
      x: c.x, y: c.y, vis: vis(e),
    });
  });

  const buttons = [];
  [...document.querySelectorAll('button, [role=button], a')].forEach((e) => {
    if (!vis(e)) return;
    const t = short(e.textContent);
    if (!t || t.length > 34) return;
    const c = ctr(e);
    buttons.push({ t, x: c.x, y: c.y, disabled: !!e.disabled });
  });

  // marker texts that matter for CP1 decisions (dedup, show coords)
  const markers = ['基本情報','価格設定','下書きを保存','提出を確認','審査に提出',
    'カードを保存しました','Capafy で実行','On-Demand','Subscription','Daily','Weekly','Monthly',
    'Add Plan','無料トライアル','Enable Free Trial','No Free Trial','重複するプラン',
    'メインカテゴリ','確認','ファイル','アップロード','スキル'];
  const found = {};
  [...document.querySelectorAll('*')].forEach((e) => {
    const t = (e.textContent || '').replace(/\s+/g,' ').trim();
    const r = e.getBoundingClientRect();
    if (r.height > 60 || r.height < 5 || !vis(e)) return;
    for (const m of markers) {
      if (t === m || (m.length > 6 && t.startsWith(m) && t.length < m.length + 8)) {
        if (!found[m]) { const c = ctr(e); found[m] = { x: c.x, y: c.y }; }
      }
    }
  });

  const toastOK = [...document.querySelectorAll('*')].some(e => /カードを保存しました/.test(e.textContent||''));
  // price tab svg color (green rgb(61,220,132)=ok)
  let priceSvg = '';
  const pt = [...document.querySelectorAll('button')].find(e => (e.textContent||'').trim() === '価格設定');
  if (pt) priceSvg = [...pt.querySelectorAll('svg')].map(s => getComputedStyle(s).color).join(',');

  const current = new URL(location.href);
  const rawPage = current.searchParams.get('page') || '';
  const safePages = new Set(['edit','review','credential','card-done','credential-done']);
  const page = safePages.has(rawPage) ? rawPage : '';
  const safeUrl = current.origin + current.pathname + (page ? '?page=' + encodeURIComponent(page) : '');
  const cardDone = /card-done|credential/.test(current.pathname) || /credential(-done)?/.test(rawPage);
  return { url: safeUrl, page, scrollY: Math.round(scrollY), vh: innerHeight,
           fields, buttons: buttons.slice(0, 60), markers: found,
           toastOK, priceSvg, cardDone };
}
"""


def all_pages(br):
    out = []
    for c in br.contexts:
        out.extend(c.pages)
    return out


def _redact_url_for_output(value):
    """Keep only a safe origin/path and allowlisted page enum in output state."""
    try:
        parts = urlsplit(str(value or ""))
        host = str(parts.hostname or "").lower()
        if parts.scheme not in {"http", "https"} or not host:
            return "<redacted-url>"
        if host == "api.capafy.ai" and re.fullmatch(r"/(?:E[1-9][0-9]{18}|[1-9][0-9]{19}|R[1-9][0-9]{18})", parts.path):
            return "https://api.capafy.ai/<redacted-short-link>"
        authority = host
        if parts.port is not None and not (
            (parts.scheme == "http" and parts.port == 80)
            or (parts.scheme == "https" and parts.port == 443)
        ):
            authority = f"{authority}:{parts.port}"
        page = next(
            (item for key, item in parse_qsl(parts.query, keep_blank_values=True) if key == "page" and item in SAFE_PAGE_VALUES),
            "",
        )
        return f"{parts.scheme}://{authority}{parts.path}" + (f"?page={page}" if page else "")
    except (TypeError, ValueError):
        return "<redacted-url>"


def _state_for_output(state):
    if not isinstance(state, dict):
        return state
    redacted = dict(state)
    if "url" in redacted:
        redacted["url"] = _redact_url_for_output(redacted["url"])
    return redacted


def _toast_for_output(state):
    safe_state = _state_for_output(state)
    return {
        "toastOK": safe_state.get("toastOK"),
        "cardDone": safe_state.get("cardDone"),
        "priceSvg": safe_state.get("priceSvg"),
        "url": safe_state.get("url"),
    }


def _require_safe_edit_url(url):
    """Validate an edit URL before selecting, attaching to, or navigating a page."""
    from save_review_url import _is_edit_url

    if not isinstance(url, str) or not _is_edit_url(url):
        raise RuntimeError("CP1 open requires a safe Capafy edit URL")
    return url


def get_page(br, prefer_capafy=True, create_ctx=None):
    pages = all_pages(br)
    if prefer_capafy:
        cap = [p for p in pages if 'capafy.ai' in (p.url or '')]
        if cap:
            return cap[-1]
    if pages:
        return pages[-1]
    ctx = create_ctx or (br.contexts[0] if br.contexts else br.new_context())
    return ctx.new_page()


def dump(pg, shot=True):
    st = _state_for_output(pg.evaluate(STATE_JS))
    if shot:
        try:
            pg.screenshot(path=SHOT)
            st['shot'] = SHOT
        except Exception as e:
            st['shot_err'] = str(e)
    print(json.dumps(st, ensure_ascii=False, indent=1))


def _raw_capafy_page(cdp, target_hint=""):
    """Attach to one page websocket, not the browser websocket.

    Browser-level Playwright attachment can stall after the websocket handshake
    when another daily driver has many targets.  A page CDP socket remains
    responsive in that state (the same proven approach used by CP2).
    """
    # The Cloak Playwright venv deliberately stays minimal and on this host does
    # not include websocket-client, while the system Python used by CP2 does.
    # Reuse that read-only site-packages location for the raw-CDP fallback.
    try:
        import websocket  # noqa: F401
    except ImportError:
        system_site = f"/opt/homebrew/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
        if os.path.isdir(system_site) and system_site not in sys.path:
            sys.path.append(system_site)
        import websocket  # noqa: F401
    from drive_checkpoint2 import _RawPage, _capafy_page_targets
    failures = []
    # Some old Capafy renderer targets can be frozen while a newer card page is
    # healthy.  Probe each page with a short Runtime.evaluate instead of treating
    # "newest target" as an availability guarantee.
    targets = _capafy_page_targets(cdp)
    if not targets:
        raise RuntimeError("no existing Capafy createAgent page target")
    if target_hint:
        exact = [t for t in targets if target_hint in str(t.get("url", ""))]
        if exact:
            targets = exact
    for target in targets:
        page = None
        try:
            page = _RawPage(target["webSocketDebuggerUrl"], call_timeout=4, connect_timeout=4)
            page.evaluate("document.readyState")
            return page
        except Exception as exc:
            failures.append(str(exc))
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
    raise RuntimeError("no responsive Capafy CDP page: " + "; ".join(failures[-3:]))


def _raw_create_capafy_target(cdp, url):
    """Create a dedicated, safe createAgent target through Chrome's HTTP CDP API.

    Raw page CDP can only attach to an already-existing page websocket.  CP1
    `open` is also the operation that establishes that page, so a browser with
    no Capafy tab used to fail before it could navigate.  `/json/new` creates a
    separate tab instead of repurposing one of the daily driver's tabs.
    """
    from drive_checkpoint2 import _validate_cdp_base
    cdp = _validate_cdp_base(cdp)
    _require_safe_edit_url(url)
    request = urllib.request.Request(
        f"{cdp}/json/new?{quote(url, safe='')}", method="PUT"
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            target = json.loads(response.read())
    except Exception as exc:
        raise RuntimeError("unable to create safe Capafy CDP target") from exc
    if not isinstance(target, dict) or not target.get("webSocketDebuggerUrl"):
        raise RuntimeError("Chrome did not return a page websocket for safe Capafy target")
    return target


def _raw_page_from_target(target):
    from drive_checkpoint2 import _RawPage
    page = _RawPage(target["webSocketDebuggerUrl"], call_timeout=4, connect_timeout=4)
    try:
        page.evaluate("document.readyState")
        return page
    except Exception:
        page.close()
        raise


def _raw_open_page(cdp, url):
    """Return a Capafy page for `open`, creating a dedicated one if required."""
    _require_safe_edit_url(url)
    try:
        return _raw_capafy_page(cdp, url)
    except RuntimeError as exc:
        # Do not mask a frozen/failed existing Capafy renderer.  Creation is
        # only the recovery for the precise no-target condition.
        if "no existing Capafy createAgent page target" not in str(exc):
            raise
    return _raw_page_from_target(_raw_create_capafy_target(cdp, url))


def _raw_click(pg, coords):
    if not isinstance(coords, dict) or not {"x", "y"} <= coords.keys():
        raise RuntimeError("CP1 target coordinates unavailable")
    for kind in ("mousePressed", "mouseReleased"):
        pg.call("Input.dispatchMouseEvent", {"type": kind, "x": coords["x"], "y": coords["y"],
                                               "button": "left", "clickCount": 1})


def _raw_dump(pg, shot=True):
    st = _state_for_output(pg.evaluate("(" + STATE_JS + ")()"))
    if shot:
        try:
            import base64
            image = pg.call("Page.captureScreenshot", {"format": "png"}).get("data", "")
            with open(SHOT, "wb") as f:
                f.write(base64.b64decode(image))
            st["shot"] = SHOT
        except Exception as e:
            st["shot_err"] = str(e)
    print(json.dumps(st, ensure_ascii=False, indent=1))


def _raw_field_expression(idx, value=None, focus_only=False):
    # Keep this visibility predicate byte-for-byte aligned with STATE_JS so the
    # agent's displayed field index is also the raw fallback's field index.
    action = "e.focus();e.select();return {ok:true};" if focus_only else (
        "const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
        "const setter=Object.getOwnPropertyDescriptor(proto,'value').set;setter.call(e,value);"
        "e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));"
        "return {ok:true};")
    return (
        "(() => { const idx=" + str(idx) + "; const value=" + json.dumps(value or "") + ";"
        "const vis=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&r.bottom>0&&r.top<innerHeight+400};"
        "const fs=[...document.querySelectorAll('input,textarea,select')].filter(e=>vis(e)||e.type==='file');"
        "const e=fs[idx];if(!e)return {ok:false,count:fs.length};e.scrollIntoView({block:'center'});" + action + " })()")


def _raw_upload(pg, idx, path):
    """Set a file chooser selection without attaching Playwright to the browser.

    Capafy's browser-level CDP endpoint can accept a websocket but then stall while
    enumerating contexts.  The page websocket is still able to use the DevTools DOM
    domain, including DOM.setFileInputFiles.  Keeping upload here means the thin
    agentic CP1 driver has every primitive it needs on that responsive page.
    """
    if not os.path.isfile(path):
        raise RuntimeError(f"CP1 upload file does not exist: {path}")
    # `idx` is the index printed by STATE_JS, which enumerates every visible
    # field (title, description, file inputs, etc.).  DOM.querySelectorAll
    # below only returns file inputs, so using `idx` directly made an otherwise
    # valid `upload 2 …` fail whenever text fields preceded the logo chooser.
    # Convert the public field index to the file-input ordinal using the exact
    # same selector and visibility rule as STATE_JS.
    fields = pg.evaluate("""(() => { const vis=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&r.bottom>0&&r.top<innerHeight+400}; return [...document.querySelectorAll('input,textarea,select')].filter(e=>vis(e)||e.type==='file').map(e=>({type:e.type||'',cls:e.className||''})) })()""")
    if idx < 0 or idx >= len(fields) or fields[idx]["type"] != "file":
        raise RuntimeError(f"CP1 field idx {idx} is not a file input")
    file_idx = sum(1 for field in fields[:idx] if field["type"] == "file")
    root = pg.call("DOM.getDocument", {"depth": 1}).get("root", {})
    # Capafy's logo and markdown attachment inputs use different classes.  Use
    # the class for the logo rather than trusting DOM enumeration across a
    # React remount: without this, a logo upload can land in the markdown
    # attachment input and leave the required logo unset.
    if "agentFormLogoFileInput" in fields[idx]["cls"]:
        logo_node = pg.call("DOM.querySelector", {
            "nodeId": root.get("nodeId"), "selector": "input.agentFormLogoFileInput"
        }).get("nodeId", 0)
        if not logo_node:
            raise RuntimeError("CP1 logo input not found")
        pg.call("DOM.setFileInputFiles", {"files": [os.path.abspath(path)], "nodeId": logo_node})
        return
    node_ids = pg.call("DOM.querySelectorAll", {
        "nodeId": root.get("nodeId"), "selector": "input[type=file]"
    }).get("nodeIds", [])
    if file_idx >= len(node_ids):
        raise RuntimeError(f"CP1 file input ordinal {file_idx} out of range ({len(node_ids)})")
    pg.call("DOM.setFileInputFiles", {"files": [os.path.abspath(path)], "nodeId": node_ids[file_idx]})


def raw_main(cmd):
    """Bounded raw-CDP fallback for every CP1 primitive except file upload."""
    if cmd == "open":
        url = _require_safe_edit_url(sys.argv[2])
        target_hint = url
    else:
        target_hint = os.environ.get("CP1_TARGET_TOKEN", "")
    pg = _raw_open_page(CDP, target_hint) if cmd == "open" else _raw_capafy_page(CDP, target_hint)
    try:
        if cmd == "open":
            pg.call("Page.navigate", {"url": url})
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                state = pg.evaluate("({ready:document.readyState,href:location.href})")
                if isinstance(state, dict) and state.get("ready") in {"interactive", "complete"} and "capafy.ai" in state.get("href", ""):
                    _raw_dump(pg); return
                time.sleep(.25)
            raise RuntimeError("CP1 raw navigation timeout")
        if cmd == "shot":
            _raw_dump(pg); return
        if cmd == "state":
            _raw_dump(pg, shot=False); return
        if cmd == "click":
            _raw_click(pg, {"x": int(sys.argv[2]), "y": int(sys.argv[3])})
        elif cmd == "clicktext":
            text = sys.argv[2]; nth = int(sys.argv[3]) if len(sys.argv) > 3 else 0
            coords = pg.evaluate("(" + """(a)=>{const[t,n]=a,els=[...document.querySelectorAll('*')].filter(e=>{const s=(e.textContent||'').replace(/\\s+/g,' ').trim(),r=e.getBoundingClientRect();return s===t&&r.height<60&&r.height>5&&r.width>0});const e=els[n];if(!e)return null;e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)}}""" + ")(" + json.dumps([text, nth]) + ")")
            if not coords:
                print(json.dumps({"error": f"text not found: {text} (nth={nth})"})); return
            _raw_click(pg, coords)
        elif cmd in {"fill", "typeinto"}:
            idx, value = int(sys.argv[2]), sys.argv[3]
            result = pg.evaluate(_raw_field_expression(idx, value, focus_only=(cmd == "typeinto")))
            if not result.get("ok"):
                print(json.dumps({"error": f"field idx {idx} out of range ({result.get('count')})"})); return
            if cmd == "typeinto":
                pg.call("Input.insertText", {"text": value})
        elif cmd == "press":
            key = sys.argv[2]
            pg.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": key})
            pg.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": key})
        elif cmd == "scroll":
            dy = int(sys.argv[2])
            # CDP's mouseWheel acknowledgement is unreliable on a busy shared
            # renderer.  Move the actual scrollable form container directly;
            # this is still a thin primitive and is bounded by Runtime.evaluate.
            pg.evaluate("""(dy=>{const xs=[...document.querySelectorAll('*')].filter(e=>{const s=getComputedStyle(e);return /(auto|scroll)/.test(s.overflowY)&&e.scrollHeight>e.clientHeight+20});const e=xs.sort((a,b)=>b.clientHeight-a.clientHeight)[0];(e||document.scrollingElement).scrollBy(0,dy);return !!e})""" + "(" + str(dy) + ")")
        elif cmd == "into":
            text = sys.argv[2]; nth = int(sys.argv[3]) if len(sys.argv) > 3 else 0
            pg.evaluate("(" + """(a)=>{const[t,n]=a,els=[...document.querySelectorAll('*')].filter(e=>{const s=(e.textContent||'').replace(/\\s+/g,' ').trim(),r=e.getBoundingClientRect();return s===t&&r.height<60&&r.height>5});if(els[n])els[n].scrollIntoView({block:'center'})}""" + ")(" + json.dumps([text, nth]) + ")")
        elif cmd == "toast":
            st = _state_for_output(pg.evaluate("(" + STATE_JS + ")()"))
            print(json.dumps(_toast_for_output(st), ensure_ascii=False)); return
        elif cmd == "upload":
            _raw_upload(pg, int(sys.argv[2]), sys.argv[3])
        else:
            print(f"unknown cmd: {cmd}"); return
        time.sleep(1)
        _raw_dump(pg)
    finally:
        pg.close()


def main():
    if len(sys.argv) < 2:
        print("usage: cp1_agent.py <cmd> ..."); sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "open":
        try:
            _require_safe_edit_url(sys.argv[2])
        except (IndexError, RuntimeError) as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            raise SystemExit(1)
    try:
        lock = _acquire_cdp_lock()
    except Cp1Busy as e:
        print(json.dumps({"error": "cp1_browser_busy", "retryable": True,
                          "detail": str(e)}))
        return

    # Browser-level Playwright attachment is the failure mode being repaired:
    # it can finish the websocket handshake yet hang while enumerating another
    # driver's contexts.  CP1 needs one Capafy page, so page-level raw CDP is
    # the normal path; it has bounded calls and never starts a run-driver.
    if os.environ.get("CP1_BROWSER_BACKEND", "raw") == "raw":
        try:
            raw_main(cmd)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
        return

    # SIGTERM is how the outer bounded runner stops CP1.  Convert it to a
    # normal exception so the finally block closes the Playwright driver rather
    # than orphaning run-driver processes that poison later CDP connections.
    def _terminate(_signum, _frame):
        raise SystemExit(143)

    old_term = signal.signal(signal.SIGTERM, _terminate)
    pw = None
    try:
        open_url = _require_safe_edit_url(sys.argv[2]) if cmd == "open" else None
        pw = sync_playwright().start()
        try:
            br = pw.chromium.connect_over_cdp(CDP, timeout=CONNECT_TIMEOUT_MS)
        except Exception as exc:
            # A raw page socket is deliberately the recovery path, not a retry:
            # the browser websocket has already completed its handshake here, so
            # retrying Playwright only adds another stalled driver to the queue.
            print(json.dumps({"warning": "playwright_browser_attach_failed",
                              "fallback": "raw_page_cdp", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
            # stop() itself waits on the same wedged Playwright transport; do
            # not turn the bounded fallback into another hang.  Dropping the
            # driver lets its pipe close when this command returns normally.
            pw = None
            raw_main(cmd)
            return

        if cmd == "open":
            url = open_url
        # reuse an existing capafy tab if present; otherwise create a BRAND-NEW tab.
        # NEVER hijack a daily-driver tab (its watchdog restores the original URL,
        # so a hijacked tab silently reverts). A fresh new_page persists.
            cap = [p for p in all_pages(br) if 'capafy.ai' in (p.url or '')]
            if cap:
                pg = cap[-1]
            else:
                ctx = br.contexts[0] if br.contexts else br.new_context()
                pg = ctx.new_page()
            pg.bring_to_front()
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(2)
            dump(pg); return

        pg = get_page(br, prefer_capafy=True)
        pg.bring_to_front()

        if cmd == "shot":
            dump(pg)
        elif cmd == "state":
            dump(pg, shot=False)
        elif cmd == "click":
            x, y = int(sys.argv[2]), int(sys.argv[3])
            pg.mouse.click(x, y); time.sleep(1.2); dump(pg)
        elif cmd == "clicktext":
            text = sys.argv[2]; nth = int(sys.argv[3]) if len(sys.argv) > 3 else 0
            c = pg.evaluate(
            """(a)=>{const[t,n]=a;const els=[...document.querySelectorAll('*')].filter(e=>{const s=(e.textContent||'').replace(/\\s+/g,' ').trim();const r=e.getBoundingClientRect();return s===t&&r.height<60&&r.height>5&&r.width>0;});const e=els[n];if(!e)return null;e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();return{x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)};}""",
                [text, nth])
            if not c:
                print(json.dumps({"error": f"text not found: {text} (nth={nth})"})); return
            pg.mouse.click(c["x"], c["y"]); time.sleep(1.2); dump(pg)
        elif cmd == "fill":
            idx = int(sys.argv[2]); val = sys.argv[3]
            els = pg.query_selector_all("input, textarea, select")
        # rebuild the same visible-field order used in STATE_JS
            fields = [e for e in els if (e.get_attribute("type") == "file") or pg.evaluate("(e)=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&r.bottom>0&&r.top<innerHeight+400;}", e)]
            if idx >= len(fields):
                print(json.dumps({"error": f"field idx {idx} out of range ({len(fields)} fields)"})); return
            e = fields[idx]; e.scroll_into_view_if_needed(); e.click()
            try: e.fill(val)
            except Exception: e.fill(""); e.type(val, delay=12)
            time.sleep(0.5); dump(pg)
        elif cmd == "typeinto":
            idx = int(sys.argv[2]); val = sys.argv[3]
            els = pg.query_selector_all("input, textarea, select")
            fields = [e for e in els if (e.get_attribute("type") == "file") or pg.evaluate("(e)=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&r.bottom>0&&r.top<innerHeight+400;}", e)]
            if idx >= len(fields):
                print(json.dumps({"error": f"field idx {idx} out of range"})); return
            e = fields[idx]; e.scroll_into_view_if_needed(); e.click()
            try: e.fill("")
            except Exception: pass
            e.type(val, delay=14); time.sleep(0.5); dump(pg)
        elif cmd == "press":
            key = sys.argv[2]; pg.keyboard.press(key); time.sleep(0.6); dump(pg)
        elif cmd == "upload":
            idx = int(sys.argv[2]); path = sys.argv[3]
            fis = pg.query_selector_all("input[type=file]")
            if idx >= len(fis):
                print(json.dumps({"error": f"file input idx {idx} out of range ({len(fis)})"})); return
            fis[idx].set_input_files(path); time.sleep(4); dump(pg)
        elif cmd == "scroll":
            # Capafy's form scrolls an INNER container, not window -> use mouse wheel
            # over the form area. Positive dy scrolls down, negative up.
            dy = int(sys.argv[2])
            pg.mouse.move(700, 500)
            pg.mouse.wheel(0, dy); time.sleep(0.8); dump(pg)
        elif cmd == "into":
            # scroll an element with exact text into view (for off-screen targets)
            text = sys.argv[2]; nth = int(sys.argv[3]) if len(sys.argv) > 3 else 0
            pg.evaluate(
            """(a)=>{const[t,n]=a;const els=[...document.querySelectorAll('*')].filter(e=>{const s=(e.textContent||'').replace(/\\s+/g,' ').trim();const r=e.getBoundingClientRect();return s===t&&r.height<60&&r.height>5;});if(els[n])els[n].scrollIntoView({block:'center'});}""",
                [text, nth]); time.sleep(0.6); dump(pg)
        elif cmd == "toast":
            st = _state_for_output(pg.evaluate(STATE_JS))
            print(json.dumps(_toast_for_output(st), ensure_ascii=False))
        else:
            print(f"unknown cmd: {cmd}"); sys.exit(2)
    finally:
        signal.signal(signal.SIGTERM, old_term)
        if pw is not None:
            pw.stop()
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    main()
