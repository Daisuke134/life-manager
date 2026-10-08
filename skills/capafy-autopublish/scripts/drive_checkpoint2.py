#!/usr/bin/env python3
"""
drive_checkpoint2.py — Capafy CP2 (credential hosting) automation.

Sets the LLM Config to the CANONICAL recipe (verified 2026-06-25):
  Base URL = https://openrouter.ai/api/v1
  Model    = $CAPAFY_HOSTED_MODEL_ID (from the prepared listing contract)
  API Key  = $CAPAFY_HOST_OPENROUTER_KEY   (Life Manager state env)
  Format   = openai-responses (Capafy default; OpenRouter /responses verified working)
Deletes the blockrun (127.0.0.1 localhost) card which always fails verification.
Clicks "キーを確認して保存" and waits for the "キー確認済み" success toast.

If $CAPAFY_DISPLAY_MODEL is set, also sets the Agent card's "LLM モデル"
display field (モデル設定 section) to that exact preset name and verifies it
via the official GET /agent/agents/<id> `model` field. This runs even when
the Hosted Key section above is already saved/collapsed (idempotent: it is
independent of the hosted-key step and is a no-op if already correct).

Usage: drive_checkpoint2.py <CP2_review_url>
Requires: its own CloakBrowser identity `capafy:kosuke` (registry:
~/.config/ai/registry/browsers.toml) LEASED via skills/browser/with-browser.sh
(never probe a hardcoded port directly), plus CAPAFY_HOST_OPENROUTER_KEY in env.
CAPAFY_ACCESS_TOKEN in env is required only to verify CAPAFY_DISPLAY_MODEL.
Exit 0 + prints VERIFIED on success; exit 1 on failure (fail-closed); exit 75
if the browser identity is not leased (retryable).
"""
import math
import os, sys, time, json, urllib.request
import re
from urllib.error import HTTPError
from urllib.parse import parse_qs, parse_qsl, quote, urlsplit

BASE_URL = "https://openrouter.ai/api/v1"
# Default to the cheap hosted model (charge more, spend less). A CP2 run that
# omitted the env var wrote Sonnet into draft 4973250899 (2026-09-29).
MODEL    = os.environ.get("CAPAFY_HOSTED_MODEL_ID", "deepseek/deepseek-v4.1-flash")
CDP_ATTACH_TIMEOUT_MS = int(os.environ.get("CP2_CDP_ATTACH_TIMEOUT_MS", "15000"))
RAW_NAV_TIMEOUT_S = float(os.environ.get("CP2_RAW_NAV_TIMEOUT_S", "30"))
RAW_CALL_TIMEOUT_S = float(os.environ.get("CP2_RAW_CALL_TIMEOUT_S", "20"))
RAW_SECTION_TIMEOUT_S = float(os.environ.get("CP2_SECTION_TIMEOUT_S", "45"))
RAW_SECTION_POLL_S = float(os.environ.get("CP2_SECTION_POLL_S", "0.25"))
_CP2_RESOLVE_RETRIES = int(os.environ.get("CP2_RESOLVE_RETRIES", "3"))
_CP2_RESOLVE_RETRY_DELAY_S = float(os.environ.get("CP2_RESOLVE_RETRY_DELAY_S", "5"))
CP2_HOST = "capafy.ai"
CP2_PATH = "/developer/createAgent"
OPENROUTER_API_KEY_PATH = "models.providers.openrouter.apiKey"
OPENROUTER_BASE_URL_PATH = "models.providers.openrouter.baseUrl"
AGENT_DETAIL_URL = "https://api.capafy.ai/agent/agents/{agent_id}"
DISPLAY_MODEL_VERIFY_TRIES = int(os.environ.get("CP2_DISPLAY_MODEL_VERIFY_TRIES", "4"))
DISPLAY_MODEL_VERIFY_DELAY_S = float(os.environ.get("CP2_DISPLAY_MODEL_VERIFY_DELAY_S", "3"))
BLOCKRUN_API_KEY_PATH = "models.providers.blockrun.apiKey"


def _is_loopback_host(host):
    return str(host or "").lower().strip("[]") in {"localhost", "127.0.0.1", "::1"}


def _validate_cdp_base(cdp_base):
    parts = urlsplit(str(cdp_base or ""))
    if parts.scheme != "http" or not _is_loopback_host(parts.hostname) or parts.username or parts.password:
        raise RuntimeError("CDP base must be an unauthenticated loopback HTTP URL")
    return str(cdp_base).rstrip("/")


def _validate_ws_url(ws_url):
    parts = urlsplit(str(ws_url or ""))
    if parts.scheme not in {"ws", "wss"} or not _is_loopback_host(parts.hostname) or parts.username or parts.password:
        raise RuntimeError("CDP websocket must use a loopback host")
    return str(ws_url)


def _is_capafy_target_url(url):
    parts = urlsplit(str(url or ""))
    return parts.scheme == "https" and parts.netloc.lower() == CP2_HOST and parts.path == CP2_PATH


def _target_url_key(url):
    if not _is_capafy_target_url(url):
        return None
    parts = urlsplit(str(url))
    query = tuple(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return (parts.scheme.lower(), parts.netloc.lower(), parts.path, query)


# The identity capafy:kosuke banks the Capafy seller session (registry:
# ~/.config/ai/registry/browsers.toml).
CAPAFY_BROWSER_IDENTITY = os.environ.get("CAPAFY_BROWSER_IDENTITY", "capafy:kosuke").strip() or "capafy:kosuke"


def _detect_cdp():
    """Resolve the CDP endpoint ONLY from an already-leased identity.

    Never probes hardcoded ports (9222/9223): the 2026-07-26 incident was
    exactly that — :9222 turned out to be a proxy onto the SAME browser as
    production :9223 (identical CDP UUID). A shared browser must be leased
    first via skills/browser/with-browser.sh, which resolves the identity's
    real endpoint and exports it as CLOAK_CDP_BASE_URL/CDP. CP1_CDP_URL is
    kept for a caller that already resolved its own explicit leased endpoint.
    Returns None (never a guessed port) if nothing is set.
    """
    for var in ("CP1_CDP_URL", "CLOAK_CDP_BASE_URL", "CDP"):
        value = os.environ.get(var, "").strip()
        if value:
            return _validate_cdp_base(value)
    return None


def _require_cdp():
    """Fail closed (exit 75, retryable) instead of guessing a port."""
    cdp = _detect_cdp()
    if cdp is None:
        print(json.dumps({
            "error": "capafy_browser_not_leased", "retryable": True,
            "identity": CAPAFY_BROWSER_IDENTITY,
            "detail": ("no leased CDP endpoint in env (CP1_CDP_URL/CLOAK_CDP_BASE_URL/CDP). "
                       f"Run under skills/browser/with-browser.sh {CAPAFY_BROWSER_IDENTITY} -- "
                       "...; refuses to probe 9222/9223 directly."),
        }, ensure_ascii=False))
        sys.exit(75)
    return cdp


def _load_playwright():
    from playwright.sync_api import sync_playwright
    return sync_playwright


def _raw_page_targets(cdp_base, cp2):
    _validate_cp2_url(cp2)
    expected = _target_url_key(cp2)
    cdp_base = _validate_cdp_base(cdp_base)
    with urllib.request.urlopen(f"{cdp_base}/json/list", timeout=8) as r:
        targets = json.loads(r.read())
    matches = [
        target for target in reversed(targets if isinstance(targets, list) else [])
        if isinstance(target, dict)
        and target.get("type") == "page"
        and _target_url_key(target.get("url")) == expected
        and target.get("webSocketDebuggerUrl")
    ]
    if not matches:
        raise RuntimeError("no exact CP2 page target for raw CDP fallback")
    return matches


def _capafy_page_targets(cdp_base):
    """Return existing Capafy createAgent pages that are safe to navigate to CP2."""
    cdp_base = _validate_cdp_base(cdp_base)
    with urllib.request.urlopen(f"{cdp_base}/json/list", timeout=8) as r:
        targets = json.loads(r.read())
    matches = [
        target for target in reversed(targets if isinstance(targets, list) else [])
        if isinstance(target, dict)
        and target.get("type") == "page"
        and _is_capafy_target_url(target.get("url"))
        and target.get("webSocketDebuggerUrl")
    ]
    if not matches:
        raise RuntimeError("no existing Capafy createAgent page target")
    return matches


def _open_cp2_target(cdp_base, cp2):
    """Open the validated CP2 URL in a new tab and wait until DevTools lists it."""
    _validate_cp2_url(cp2)
    cdp_base = _validate_cdp_base(cdp_base)
    request = urllib.request.Request(
        f"{cdp_base}/json/new?{quote(cp2, safe='')}", method="PUT")
    with urllib.request.urlopen(request, timeout=8) as r:
        r.read()
    deadline = time.time() + RAW_NAV_TIMEOUT_S
    while time.time() < deadline:
        try:
            return _raw_page_targets(cdp_base, cp2)
        except RuntimeError:
            time.sleep(1)
    raise RuntimeError("opened CP2 tab did not appear as a page target")


class _RawPage:
    """Small synchronous page-level CDP adapter for the CP2 interactions below."""

    def __init__(self, ws_url, *, call_timeout=None, connect_timeout=None):
        try:
            import websocket
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError("websocket-client is required for raw CDP fallback") from exc
        self._call_timeout_s = float(call_timeout if call_timeout is not None else RAW_CALL_TIMEOUT_S)
        self._ws = websocket.create_connection(
            _validate_ws_url(ws_url),
            timeout=float(connect_timeout if connect_timeout is not None else 15),
            enable_multithread=True,
        )
        self._next_id = 0
        self._events = []

    def close(self):
        self._ws.close()

    def call(self, method, params=None):
        self._next_id += 1
        request_id = self._next_id
        message = {"id": request_id, "method": method, "params": params or {}}
        self._ws.send(json.dumps(message))
        deadline = time.monotonic() + self._call_timeout_s
        while time.monotonic() < deadline:
            self._ws.settimeout(max(0.1, min(2.0, deadline - time.monotonic())))
            try:
                message = json.loads(self._ws.recv())
            except Exception as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"CDP call timeout: {method}") from exc
                continue
            if message.get("id") != request_id:
                self._events.append(message)
                continue
            if "error" in message:
                raise RuntimeError(f"{method}: {message['error']}")
            return message.get("result", {})
        raise RuntimeError(f"CDP call timeout: {method}")

    def evaluate(self, expression):
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if result.get("exceptionDetails"):
            raise RuntimeError(f"Runtime.evaluate failed: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def click_coords(self, expression):
        coords = self.evaluate(expression)
        if not isinstance(coords, dict) or not {"x", "y"} <= coords.keys():
            return False
        x, y = float(coords["x"]), float(coords["y"])
        self.call("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1,
        })
        self.call("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1,
        })
        return True

    def strict_focus_and_insert(self, path, role, value):
        result = self.evaluate(_strict_focus_expression(path, role))
        if not isinstance(result, dict) or not result.get("ok"):
            raise RuntimeError(f"ambiguous CP2 {role} field ({result})")
        self.call("Input.insertText", {"text": value})

    def strict_click(self, path, kind):
        result = self.evaluate(_strict_button_expression(path, kind))
        if not isinstance(result, dict) or not result.get("ok"):
            raise RuntimeError(f"ambiguous CP2 {kind} button ({result})")
        if result.get("disabled"):
            raise RuntimeError(f"CP2 {kind} button is disabled")
        x, y = result.get("x"), result.get("y")
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise RuntimeError(f"CP2 {kind} button coordinates missing")
        if not math.isfinite(float(x)) or not math.isfinite(float(y)):
            raise RuntimeError(f"CP2 {kind} button coordinates invalid")
        try:
            self.call("Input.dispatchMouseEvent", {
                "type": "mousePressed", "x": float(x), "y": float(y), "button": "left", "clickCount": 1,
            })
            self.call("Input.dispatchMouseEvent", {
                "type": "mouseReleased", "x": float(x), "y": float(y), "button": "left", "clickCount": 1,
            })
        except Exception as exc:
            raise RuntimeError(f"CP2 {kind} dispatch failed") from exc
        return True

    def press_enter(self):
        self.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter"})
        self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter"})


def _location_key(url):
    parts = urlsplit(str(url or ""))
    return (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/")


def _validate_cp2_url(cp2):
    parts = urlsplit(cp2)
    page_values = parse_qs(parts.query, keep_blank_values=True).get("page", [])
    if (
        not _is_capafy_target_url(cp2)
        or len(page_values) != 1
        or page_values[0] not in {"credential", "review"}
    ):
        raise RuntimeError("CP2 URL must use the exact Capafy HTTPS origin/path")


def _is_identified_cp2_url(url):
    """True only if <url> carries the draft-identifying params Capafy's short
    review link (/R<digits>) is supposed to redirect to: either a temp-link
    token or a draftKey, alongside page=credential|review.

    Root cause (2026-09-28, Agent 9466718786 resume): a short link's redirect
    target sometimes degrades to a bare ?page=review with NO source/token/
    draftKey -- that is Capafy's blank "create a new Agent" form, not the
    existing draft. _validate_cp2_url alone accepts it (it only checks the
    `page` value), so the resume driver silently opened/would have driven the
    wrong page. Only the resolved target of a short link needs this extra
    check: a caller-supplied full URL (tests, manual invocation) already
    carries whatever identity it carries by construction.
    """
    try:
        _validate_cp2_url(url)
    except RuntimeError:
        return False
    parts = urlsplit(url)
    try:
        query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    keys = [key for key, _value in query]
    if len(set(keys)) != len(keys):
        return False
    values = dict(query)
    if set(keys) == {"page", "source", "token"}:
        return values.get("source") == "temp-link" and re.fullmatch(r"[0-9]+", values.get("token", "")) is not None
    if set(keys) == {"draftKey", "page"}:
        return bool(values.get("draftKey", "").strip())
    return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _single_redirect_location(url, method):
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, method=method)
    try:
        response = opener.open(request, timeout=8)
    except HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
            return []
        headers = exc.headers
    else:
        try:
            headers = response.headers
        finally:
            response.close()
    locations = headers.get_all("Location") if headers is not None else None
    return [str(value).strip() for value in (locations or []) if str(value).strip()]


def _resolve_cp2_url(raw_url):
    raw_url = str(raw_url or "").strip()
    if _is_capafy_target_url(raw_url):
        _validate_cp2_url(raw_url)
        return raw_url

    parts = urlsplit(raw_url)
    if (
        parts.scheme != "https"
        or parts.netloc.lower() != "api.capafy.ai"
        # Verified live 2026-09-28 (Agent 4243672453): both publish-refresh-url
        # --step publish and publish-submit --action continue_upload's review_url
        # return an /R<digits> short link -- the same prefix drive_checkpoint3.py
        # (CP3) already expects for the identical review page. /C<digits> was
        # never observed and made every CP2 call fail closed on this exact
        # RuntimeError before the browser was ever touched.
        or not re.fullmatch(r"/R[0-9]+", parts.path)
        or parts.query
        or parts.fragment
    ):
        raise RuntimeError("CP2 short URL must be exactly https://api.capafy.ai/R<digits>")

    # Retry ONLY the "resolved but unidentified" case: a resume drove Agent
    # 9466718786 into a bare ?page=review (Capafy's blank new-Agent form, no
    # source/token/draftKey) on 2026-09-28 06:52Z, while the identical short
    # link resolved correctly moments before (06:13Z, same-pass) and again on
    # manual re-check hours later -- a transient degraded redirect, not a
    # permanently dead link. A malformed/cross-domain/missing Location is a
    # real structural failure and must still fail closed immediately below.
    last_error = None
    for attempt in range(_CP2_RESOLVE_RETRIES):
        if attempt:
            time.sleep(_CP2_RESOLVE_RETRY_DELAY_S)
        locations = _single_redirect_location(raw_url, "HEAD")
        if not locations:
            locations = _single_redirect_location(raw_url, "GET")
        if len(locations) != 1:
            raise RuntimeError("CP2 short URL must return exactly one redirect Location")
        resolved = locations[0]
        _validate_cp2_url(resolved)
        if _is_identified_cp2_url(resolved):
            return resolved
        last_error = resolved
    raise RuntimeError(
        "CP2 short URL redirected to an unidentified draft page after "
        f"{_CP2_RESOLVE_RETRIES} attempts (no source+token or draftKey; last: {last_error!r}) "
        "-- this is Capafy's blank new-Agent form, not the existing draft; refusing to drive it"
    )


def _wait_raw_navigation(page, cp2):
    _validate_cp2_url(cp2)
    expected = _location_key(cp2)
    result = page.call("Page.navigate", {"url": cp2})
    error_text = str(result.get("errorText") or "").strip()
    if error_text:
        raise RuntimeError(f"Page.navigate failed: {error_text}")
    deadline = time.monotonic() + RAW_NAV_TIMEOUT_S
    while time.monotonic() < deadline:
        state = page.evaluate("({ready:document.readyState,href:location.href})")
        if isinstance(state, dict) and state.get("ready") in {"interactive", "complete"}:
            actual = str(state.get("href") or "")
            if _location_key(actual) != expected:
                raise RuntimeError("CP2 navigation reached the wrong origin/path")
            return actual
        time.sleep(0.25)
    raise RuntimeError("CP2 navigation did not reach ready state before deadline")


def _fresh_success(before_url, before_toasts, current_url, toast):
    if current_url != before_url and "credential-done" in str(current_url or ""):
        return True
    return "キー確認済み" in str(toast or "") and str(toast) not in set(before_toasts or ())


def _strict_focus_expression(path, role):
    predicates = {
        "base": "(x.value||'').includes('api.')||(x.value||'').includes('openrouter.ai')||/^https?:\\/\\//.test(x.value||'')||(x.placeholder||'').includes('api.')",
        "model": "(x.value||'').startsWith('gpt-')||(x.value||'').startsWith('claude-')||(x.value||'').startsWith('anthropic/')||(x.value||'')==='auto'||['Model','モデル'].includes(x.placeholder||'')",
        "key": "x.type==='password'&&((x.placeholder||'').includes('Paste')||(x.placeholder||'').toLowerCase().includes('key')||(x.placeholder||'').includes('キー'))",
    }
    predicate = predicates[role]
    return (
        "(() => {"
        f"const path={json.dumps(path)};"
        "const leaves=[...document.querySelectorAll('*')].filter(e=>(e.textContent||'').trim()===path&&![...e.children].some(c=>(c.textContent||'').trim()===path));"
        "if(leaves.length>1)return {ok:false,reason:'path-count',count:leaves.length};"
        "if(leaves.length===0){"
        "const visible=b=>!!(b.offsetWidth||b.offsetHeight||b.getClientRects().length);"
        "const saves=[...document.querySelectorAll('button')].filter(b=>visible(b)&&/^(保存|Save)$/.test((b.textContent||'').trim()));"
        "const cancels=[...document.querySelectorAll('button')].filter(b=>visible(b)&&/^(キャンセル|Cancel)$/.test((b.textContent||'').trim()));"
        "if(saves.length!==1||cancels.length!==1)return {ok:false,reason:'edit-signature',saveCount:saves.length,cancelCount:cancels.length};"
        f"const xs=[...document.querySelectorAll('input')].filter(x=>{predicate});"
        "if(xs.length!==1)return {ok:false,reason:'edit-field-count',count:xs.length};"
        "const x=xs[0];x.scrollIntoView({block:'center'});x.focus();x.select();return {ok:true,mode:'edit'};"
        "}"
        "let card=leaves[0],matches=[];"
        "for(let k=0;k<12&&card;k++,card=card.parentElement){"
        f"const xs=[...card.querySelectorAll('input')].filter(x=>{predicate});"
        "if(xs.length===1){matches=xs;break;}"
        "}"
        "if(matches.length!==1)return {ok:false,reason:'field-count',count:matches.length};"
        "const x=matches[0];x.scrollIntoView({block:'center'});x.focus();x.select();return {ok:true};"
        "})()"
    )


def _strict_button_expression(path, kind):
    if kind == "save":
        predicate = "['Save','保存'].includes((b.textContent||'').trim())"
    elif kind == "confirm":
        predicate = "/キーを確認して保存/.test(b.textContent||'')"
    elif kind == "edit":
        predicate = "true"
    else:
        raise ValueError(kind)
    return (
        "(() => {"
        f"const path={json.dumps(path)};"
        "const leaves=[...document.querySelectorAll('*')].filter(e=>(e.textContent||'').trim()===path&&![...e.children].some(c=>(c.textContent||'').trim()===path));"
        "if(leaves.length>1)return {ok:false,reason:'path-count',count:leaves.length};"
        "if(leaves.length===0){"
        "if(" + ("true" if kind == "save" else "false") + "){"
        "const visible=b=>!!(b.offsetWidth||b.offsetHeight||b.getClientRects().length);"
        "const saves=[...document.querySelectorAll('button')].filter(b=>visible(b)&&/^(保存|Save)$/.test((b.textContent||'').trim()));"
        "const cancels=[...document.querySelectorAll('button')].filter(b=>visible(b)&&/^(キャンセル|Cancel)$/.test((b.textContent||'').trim()));"
        "if(saves.length!==1||cancels.length!==1)return {ok:false,reason:'edit-signature',saveCount:saves.length,cancelCount:cancels.length};"
        "const b=saves[0];b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return {ok:true,mode:'edit',x:r.x+r.width/2,y:r.y+r.height/2,disabled:!!b.disabled};"
        "}return {ok:false,reason:'path-missing'};"
        "}"
        "let card=leaves[0],buttons=[];"
        "for(let k=0;k<12&&card;k++,card=card.parentElement){"
        f"const bs=[...card.querySelectorAll('button')].filter(b=>{predicate});"
        "if(bs.length===1){buttons=bs;break;}"
        "}"
        "if(buttons.length!==1)return {ok:false,reason:'button-count',count:buttons.length};"
        "const b=buttons[0];b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return {ok:true,x:r.x+r.width/2,y:r.y+r.height/2,disabled:!!b.disabled};"
        "})()"
    )


def _provider_path_state_expression(path=OPENROUTER_API_KEY_PATH):
    return (
        "(() => {"
        f"const path={json.dumps(path)};"
        "const xs=[...document.querySelectorAll('*')].filter(x=>(x.textContent||'').trim()===path&&![...x.children].some(c=>(c.textContent||'').trim()===path));"
        "return {count:xs.length};"
        "})()"
    )


def _detected_keys_button_expression():
    return (
        "(() => {"
        "const bs=[...document.querySelectorAll('button')].filter(b=>{const t=(b.textContent||'').trim();return /^検出されたキー（[0-9]+ 件）$/.test(t)||t==='検出されたキー';});"
        "if(bs.length!==1)return {ok:false,reason:'button-count',count:bs.length};"
        "const b=bs[0];b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return {ok:true,x:r.x+r.width/2,y:r.y+r.height/2};"
        "})()"
    )


def _configured_proxy_form_expression():
    """Recognize the editable proxy card on the final review page emitted by continue_upload.

    Capafy currently expands a freshly configured OpenRouter pair as a generic
    ``proxy_env`` card.  It has no provider-path text yet, so treating the
    absence of ``models.providers.openrouter.apiKey`` as a failed expansion
    makes a valid card unreachable.  The four fields below are Capafy's form
    contract (field name, secret name, URL, secret), not a visual coordinate
    heuristic; all four must be uniquely present before we write anything.
    """
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const by=(predicate)=>[...document.querySelectorAll('input')].filter(x=>visible(x)&&predicate(x));"
        "const urlName=by(x=>(x.placeholder||'').trim()==='urlName');"
        "const secretName=by(x=>(x.placeholder||'').includes('Anthropic API'));"
        "const url=by(x=>(x.placeholder||'').trim()==='https://api.example.com');"
        "const key=by(x=>x.type==='password'&&(x.placeholder||'').includes('貼り付け'));"
        "if(urlName.length!==1||secretName.length!==1||url.length!==1||key.length!==1)"
        "return {ok:false,reason:'configured-proxy-field-count',counts:[urlName.length,secretName.length,url.length,key.length]};"
        "return {ok:true};"
        "})()"
    )


def _configured_proxy_focus_expression(role):
    selectors = {
        "url_name": "(x.placeholder||'').trim()==='urlName'",
        "secret_name": "(x.placeholder||'').includes('Anthropic API')",
        "url": "(x.placeholder||'').trim()==='https://api.example.com'",
        "key": "x.type==='password'&&(x.placeholder||'').includes('貼り付け')",
    }
    if role not in selectors:
        raise ValueError(role)
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        f"const xs=[...document.querySelectorAll('input')].filter(x=>visible(x)&&({selectors[role]}));"
        "if(xs.length!==1)return {ok:false,reason:'configured-proxy-focus-count',count:xs.length};"
        "const x=xs[0];x.scrollIntoView({block:'center'});x.focus();x.select();return {ok:true};"
        "})()"
    )


def _llm_config_form_expression():
    """Recognize the "LLM 設定とホスト型キー · プロキシホスト型" Hosted Key card
    rendered under the "Agent ワークスペース" tab on same-Agent update/resumed
    drafts (live, 2026-09-28, Agent 8123079349 / 9466718786). Neither the
    provider-path-text layout nor the four-field configured-proxy layout match
    it: it has no `models.providers.openrouter.apiKey` text node yet (nothing
    is saved), and its field placeholders differ from the configured-proxy
    card's literal `urlName` / `https://api.example.com` contract. These four
    field placeholders are this card's own form contract, verified live via
    read-only DOM inspection; all four must be uniquely present.
    """
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const by=(predicate)=>[...document.querySelectorAll('input')].filter(x=>visible(x)&&predicate(x));"
        "const keyName=by(x=>(x.placeholder||'').includes('Anthropic API')&&(x.placeholder||'').includes('TikTok'));"
        "const baseUrl=by(x=>(x.placeholder||'').trim()==='api.anthropic.com');"
        "const model=by(x=>(x.placeholder||'').trim()==='モデル');"
        "const key=by(x=>x.type==='password'&&(x.placeholder||'').includes('新しいキーを貼り付けて'));"
        "if(keyName.length!==1||baseUrl.length!==1||model.length!==1||key.length!==1)"
        "return {ok:false,reason:'llm-config-field-count',counts:[keyName.length,baseUrl.length,model.length,key.length]};"
        "return {ok:true};"
        "})()"
    )


def _llm_config_focus_expression(role):
    selectors = {
        "base_url": "(x.placeholder||'').trim()==='api.anthropic.com'",
        "model": "(x.placeholder||'').trim()==='モデル'",
        "key": "x.type==='password'&&(x.placeholder||'').includes('新しいキーを貼り付けて')",
    }
    if role not in selectors:
        raise ValueError(role)
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        f"const xs=[...document.querySelectorAll('input')].filter(x=>visible(x)&&({selectors[role]}));"
        "if(xs.length!==1)return {ok:false,reason:'llm-config-focus-count',count:xs.length};"
        "const x=xs[0];x.scrollIntoView({block:'center'});x.focus();x.select();return {ok:true};"
        "})()"
    )


def _llm_config_vendor_state_expression():
    """Read the vendor picker scoped to this card (walk up from the base-URL
    field, same ancestor-search pattern the strict field/button lookups use
    elsewhere) without clicking it. Live (2026-09-28) the picker is already
    "OpenRouter" by default, matching CAPAFY_HOSTED_MODEL_ID's provider -- so
    the normal path never has to drive its dropdown."""
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const bases=[...document.querySelectorAll('input')].filter(x=>visible(x)&&(x.placeholder||'').trim()==='api.anthropic.com');"
        "if(bases.length!==1)return {ok:false,reason:'base-count',count:bases.length};"
        "let card=bases[0],buttons=[];"
        "for(let k=0;k<12&&card;k++,card=card.parentElement){"
        "const bs=[...card.querySelectorAll('button')].filter(b=>visible(b)&&/^(OpenRouter|ベンダーを選択|Select Vendor)/.test((b.textContent||'').trim()));"
        "if(bs.length===1){buttons=bs;break;}"
        "}"
        "if(buttons.length!==1)return {ok:false,reason:'vendor-button-count',count:buttons.length};"
        "return {ok:true,text:(buttons[0].textContent||'').trim()};"
        "})()"
    )


def _workspace_llm_form_expression():
    """Recognize the newer Agent Workspace hosted-key form.

    Same-Agent model-switch drafts can render the provider fields directly in
    the workspace tab instead of the older ``api.anthropic.com`` card.  The
    fields are identified by their live form contract, not coordinates.
    """
    return (
        "(() => {"
        "const v=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const xs=[...document.querySelectorAll('input')].filter(v);"
        "const base=xs.filter(x=>x.type==='text'&&(/^https?:\\/\\//.test(x.value||'')||(x.placeholder||'').includes('api.')));"
        "const model=xs.filter(x=>x.type==='text'&&(x.placeholder||'').trim()==='モデル');"
        "const key=xs.filter(x=>x.type==='password');"
        "if(base.length!==1||model.length!==1||key.length!==1)"
        "return {ok:false,reason:'workspace-llm-field-count',counts:[base.length,model.length,key.length]};"
        "return {ok:true};"
        "})()"
    )


def _workspace_focus_expression(role):
    predicates = {
        "base": "x.type==='text'&&(/^https?:\\/\\//.test(x.value||'')||(x.placeholder||'').includes('api.'))",
        "model": "x.type==='text'&&(x.placeholder||'').trim()==='モデル'",
        "key": "x.type==='password'",
    }
    if role not in predicates:
        raise ValueError(role)
    return (
        "(() => {const v=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        f"const xs=[...document.querySelectorAll('input')].filter(x=>v(x)&&({predicates[role]}));"
        "if(xs.length!==1)return {ok:false,count:xs.length};"
        "const x=xs[0];x.scrollIntoView({block:'center'});x.focus();x.select();return {ok:true};})()"
    )


def _workspace_save_expression():
    return (
        "(() => {const v=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const bs=[...document.querySelectorAll('button')].filter(b=>v(b)&&(b.textContent||'').trim()==='保存');"
        "if(bs.length!==1)return {ok:false,reason:'workspace-save-count',count:bs.length};"
        "const b=bs[0];b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();"
        "return {ok:true,disabled:!!b.disabled,x:r.x+r.width/2,y:r.y+r.height/2};})()"
    )


def _raw_configure_workspace_llm(page, key):
    state = page.evaluate(_workspace_llm_form_expression())
    if not isinstance(state, dict) or not state.get("ok"):
        raise RuntimeError(f"ambiguous workspace LLM form ({state})")
    for role, value in (("base", BASE_URL), ("model", MODEL), ("key", key)):
        focused = page.evaluate(_workspace_focus_expression(role))
        if not isinstance(focused, dict) or not focused.get("ok"):
            raise RuntimeError(f"workspace LLM {role} focus failed ({focused})")
        page.call("Input.insertText", {"text": value})
    save = page.evaluate(_workspace_save_expression())
    if not isinstance(save, dict) or not save.get("ok"):
        raise RuntimeError(f"ambiguous workspace LLM save button ({save})")
    if save.get("disabled"):
        raise RuntimeError("workspace LLM save button is disabled")
    for kind in ("mousePressed", "mouseReleased"):
        page.call("Input.dispatchMouseEvent", {
            "type": kind, "x": float(save["x"]), "y": float(save["y"]),
            "button": "left", "clickCount": 1,
        })
    print("workspace LLM fields: True")
    return True


def _raw_configure_llm_form(page, key):
    """Fill the llm_config_form Hosted Key card. Vendor is only set when the
    picker is empty/unset -- Capafy already shows "OpenRouter" by default in
    every observed live case, so driving its dropdown is not automated.
    ponytail: no dropdown automation; upgrade if a real draft ever needs it.
    """
    state = page.evaluate(_llm_config_form_expression())
    if not isinstance(state, dict) or not state.get("ok"):
        raise RuntimeError(f"ambiguous llm config hosted-key form ({state})")
    # The vendor button renders a moment after the base-URL field (live 2026-09-29,
    # 8123079349: count 0 right after the tab click, present a few seconds later).
    deadline = time.monotonic() + 20.0
    vendor = page.evaluate(_llm_config_vendor_state_expression())
    while (not isinstance(vendor, dict) or not vendor.get("ok")) and time.monotonic() < deadline:
        time.sleep(1.0)
        vendor = page.evaluate(_llm_config_vendor_state_expression())
    if not isinstance(vendor, dict) or not vendor.get("ok"):
        raise RuntimeError(f"ambiguous llm config vendor picker ({vendor})")
    if vendor.get("text") != "OpenRouter":
        raise RuntimeError(
            f"llm config vendor picker is not OpenRouter ({vendor.get('text')!r}); "
            "set it manually once, then rerun -- vendor-dropdown selection is not automated"
        )
    for role, value in (("base_url", BASE_URL), ("model", MODEL), ("key", key)):
        focused = page.evaluate(_llm_config_focus_expression(role))
        if not isinstance(focused, dict) or not focused.get("ok"):
            raise RuntimeError(f"llm config {role} focus failed ({focused})")
        page.call("Input.insertText", {"text": value})


def _raw_configure_proxy_form(page, key):
    state = page.evaluate(_configured_proxy_form_expression())
    if not isinstance(state, dict) or not state.get("ok"):
        raise RuntimeError(f"ambiguous configured OpenRouter proxy form ({state})")
    for role, value in (
        ("url_name", OPENROUTER_BASE_URL_PATH),
        ("secret_name", OPENROUTER_API_KEY_PATH),
        ("url", BASE_URL),
        ("key", key),
    ):
        focused = page.evaluate(_configured_proxy_focus_expression(role))
        if not isinstance(focused, dict) or not focused.get("ok"):
            raise RuntimeError(f"configured OpenRouter proxy {role} focus failed ({focused})")
        page.call("Input.insertText", {"text": value})


def _bounded_page_call(page, method, params, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("provider section deadline exhausted")
    if not hasattr(page, "_call_timeout_s"):
        return page.call(method, params)
    original = page._call_timeout_s
    page._call_timeout_s = min(float(original), remaining)
    try:
        return page.call(method, params)
    finally:
        page._call_timeout_s = original


def _bounded_page_evaluate(page, expression, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("provider section deadline exhausted")
    if not hasattr(page, "_call_timeout_s"):
        return page.evaluate(expression)
    original = page._call_timeout_s
    page._call_timeout_s = min(float(original), remaining)
    try:
        return page.evaluate(expression)
    finally:
        page._call_timeout_s = original


_WORKSPACE_TAB_EXPRESSION = """(() => {
  const tabs = [...document.querySelectorAll('[role=tab],button,div,span,a')].filter(e => {
    const t = (e.textContent || '').trim();
    const r = e.getBoundingClientRect();
    return (t === 'Agent ワークスペース' || t === 'Agent Workspace') && r.width > 0 && r.height > 0 && r.height < 80;
  });
  if (!tabs.length) return {ok: false};
  const e = tabs[tabs.length - 1];
  e.scrollIntoView({block: 'center'});
  const r = e.getBoundingClientRect();
  return {ok: true, x: r.x + r.width / 2, y: r.y + r.height / 2};
})()"""


def _ensure_raw_provider_section(page):
    deadline = time.monotonic() + RAW_SECTION_TIMEOUT_S

    def provider_state():
        return _bounded_page_evaluate(page, _provider_path_state_expression(), deadline)

    def require_count_one(state, phase):
        if isinstance(state, dict) and state.get("count") == 1:
            return True
        count = state.get("count") if isinstance(state, dict) else None
        if isinstance(count, (int, float)) and not isinstance(count, bool) and count > 1:
            raise RuntimeError(f"ambiguous OpenRouter provider path during {phase} ({state})")
        return False

    workspace_tab_clicked = False
    while time.monotonic() < deadline:
        state = provider_state()
        if require_count_one(state, "initial hydration"):
            return "provider"
        proxy_form = _bounded_page_evaluate(page, _configured_proxy_form_expression(), deadline)
        if isinstance(proxy_form, dict) and proxy_form.get("ok"):
            return "configured_proxy"
        llm_form = _bounded_page_evaluate(page, _llm_config_form_expression(), deadline)
        if isinstance(llm_form, dict) and llm_form.get("ok"):
            return "llm_config_form"
        if not workspace_tab_clicked:
            # A resumed review page opens on 基本情報; the hosted-key fields live
            # under the "Agent ワークスペース" tab (2026-09-28, 9466718786).
            # Look once: a page that already shows the form has no such tab.
            tab = _bounded_page_evaluate(page, _WORKSPACE_TAB_EXPRESSION, deadline)
            if isinstance(tab, dict) and tab.get("ok"):
                # Mark clicked only once the tab exists: on a still-hydrating page the
                # tab is absent and a one-shot look never retried (live 2026-09-29).
                workspace_tab_clicked = True
                for kind in ("mousePressed", "mouseReleased"):
                    _bounded_page_call(page, "Input.dispatchMouseEvent", {"type": kind, "x": float(tab["x"]), "y": float(tab["y"]), "button": "left", "clickCount": 1}, deadline)
                time.sleep(1)
                continue
        if workspace_tab_clicked:
            workspace_llm_form = _bounded_page_evaluate(page, _workspace_llm_form_expression(), deadline)
            if isinstance(workspace_llm_form, dict) and workspace_llm_form.get("ok"):
                return "workspace_llm_form"
        button = _bounded_page_evaluate(page, _detected_keys_button_expression(), deadline)
        if isinstance(button, dict) and button.get("ok"):
            x, y = button.get("x"), button.get("y")
            if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                raise RuntimeError(f"detected-keys button coordinates invalid ({button})")
            _bounded_page_call(page, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": float(x), "y": float(y), "button": "left", "clickCount": 1}, deadline)
            _bounded_page_call(page, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": float(x), "y": float(y), "button": "left", "clickCount": 1}, deadline)
            break
        button_count = button.get("count") if isinstance(button, dict) else None
        if isinstance(button_count, (int, float)) and not isinstance(button_count, bool) and button_count > 1:
            raise RuntimeError(f"ambiguous detected-keys button ({button})")
        time.sleep(RAW_SECTION_POLL_S)
    else:
        raise RuntimeError("provider path and detected-keys button did not hydrate before deadline")

    deadline = time.monotonic() + RAW_SECTION_TIMEOUT_S
    while time.monotonic() < deadline:
        state = provider_state()
        if require_count_one(state, "post-expansion hydration"):
            return "provider"
        proxy_form = _bounded_page_evaluate(page, _configured_proxy_form_expression(), deadline)
        if isinstance(proxy_form, dict) and proxy_form.get("ok"):
            return "configured_proxy"
        time.sleep(RAW_SECTION_POLL_S)
    raise RuntimeError("OpenRouter provider path did not appear after expansion before deadline")


def _pw_strict_focus_and_insert(page, path, role, value):
    result = page.evaluate(_strict_focus_expression(path, role))
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"ambiguous CP2 {role} field ({result})")
    page.keyboard.insert_text(value)


def _pw_strict_click(page, path, kind):
    result = page.evaluate(_strict_button_expression(path, kind))
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"ambiguous CP2 {kind} button ({result})")
    if result.get("disabled"):
        return False
    page.mouse.click(float(result["x"]), float(result["y"]))
    return True


PROBE_SECONDS_PER_TARGET = 2.5


def _open_responsive_page(targets):
    # Each target gets its own probe budget: on 2026-10-05 a frozen page=card-done
    # tab used up a shared 5s budget and the healthy page=edit tab was never tried.
    last_error = None
    for target in targets:
        probe_deadline = time.monotonic() + PROBE_SECONDS_PER_TARGET
        remaining = probe_deadline - time.monotonic()
        if remaining <= 0:
            break
        page = None
        try:
            page = _RawPage(
                target["webSocketDebuggerUrl"],
                call_timeout=max(0.05, remaining),
                connect_timeout=max(0.05, remaining),
            )
            remaining = probe_deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("raw CDP probe deadline exhausted")
            page._call_timeout_s = remaining
            page.evaluate("1")
            page._call_timeout_s = RAW_CALL_TIMEOUT_S
            return page
        except Exception as exc:
            last_error = exc
            if page is not None:
                page.close()
    raise RuntimeError(f"no responsive exact CP2 page target ({last_error})")


def _official_agent_model(agent_id):
    """GET /agent/agents/<id> the same way verify_cp1_model.py does, returning
    the official `model` field. Returns None on any failure (missing token,
    network error, id mismatch) -- never raises, so a caller can poll instead
    of treating one slow read as a hard error."""
    token = os.environ.get("CAPAFY_ACCESS_TOKEN", "").strip()
    if not token or not str(agent_id or "").isdecimal():
        return None
    request = urllib.request.Request(
        AGENT_DETAIL_URL.format(agent_id=agent_id),
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except (OSError, ValueError):
        return None
    data = payload.get("data") if isinstance(payload, dict) and payload.get("code") == 0 else None
    if not isinstance(data, dict) or str(data.get("agentId") or "") != str(agent_id):
        return None
    return data.get("model")


def _verify_official_display_model(agent_id, display_model):
    """Poll the official Agent detail (server is eventually consistent, same
    reasoning as publish_finish.sh's own poll()) until `model` matches, or
    give up after DISPLAY_MODEL_VERIFY_TRIES."""
    last = None
    for _ in range(DISPLAY_MODEL_VERIFY_TRIES):
        last = _official_agent_model(agent_id)
        if last == display_model:
            return True
        time.sleep(DISPLAY_MODEL_VERIFY_DELAY_S)
    print(f"official model mismatch after retries: {last!r} != {display_model!r}")
    return False


def _agent_id_from_page_expression():
    """The Agent id is rendered read-only in the review header (e.g.
    "8123079349 · v1.0.3") -- read it from the DOM instead of threading it
    through the CLI, since drive_checkpoint2.py's only argument is the CP2
    URL, which does not carry the numeric agent id."""
    return (
        "(() => {"
        "const e=document.querySelector('.finalReviewAgentMeta');"
        "if(!e)return {ok:false,reason:'no-agent-meta'};"
        "const m=(e.textContent||'').match(/(\\d+)/);"
        "return m?{ok:true,agentId:m[1]}:{ok:false,reason:'no-digits'};"
        "})()"
    )


def _display_model_combobox_expression():
    """The "LLM モデル" combobox under モデル設定 (Agent ワークスペース tab) --
    the field verify_cp1_model.py's official `model` readback is sourced
    from. Verified live (2026-09-28, Agent 8123079349): a single
    role=combobox input with this exact placeholder."""
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const xs=[...document.querySelectorAll('input')].filter(x=>visible(x)&&x.getAttribute('role')==='combobox'&&(x.placeholder||'').trim()==='モデルを選択または入力');"
        "if(xs.length!==1)return {ok:false,reason:'display-model-combobox-count',count:xs.length};"
        "return {ok:true,value:xs[0].value};"
        "})()"
    )


def _display_model_focus_expression():
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const xs=[...document.querySelectorAll('input')].filter(x=>visible(x)&&x.getAttribute('role')==='combobox'&&(x.placeholder||'').trim()==='モデルを選択または入力');"
        "if(xs.length!==1)return {ok:false,reason:'display-model-combobox-count',count:xs.length};"
        "const x=xs[0];x.scrollIntoView({block:'center'});x.focus();x.select();return {ok:true};"
        "})()"
    )


def _display_model_option_expression(display_model):
    """Typing into the combobox filters #pricingTabModelList to
    role=option buttons (verified live: typing "DeepSeek" surfaced "DeepSeek
    V4.1 Flash" as the first match). Require an EXACT text match -- never
    click a near-miss preset."""
    return (
        "(() => {"
        f"const model={json.dumps(display_model)};"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const list=document.getElementById('pricingTabModelList');"
        "if(!list)return {ok:false,reason:'no-model-list'};"
        "const opts=[...list.querySelectorAll('button')].filter(b=>visible(b)&&(b.textContent||'').trim()===model);"
        "if(opts.length!==1)return {ok:false,reason:'display-model-option-count',count:opts.length};"
        "const b=opts[0];b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();"
        "return {ok:true,x:r.x+r.width/2,y:r.y+r.height/2};"
        "})()"
    )


def _draft_save_button_expression():
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const bs=[...document.querySelectorAll('button')].filter(b=>visible(b)&&(b.textContent||'').trim()==='下書きを保存');"
        "if(bs.length!==1)return {ok:false,reason:'draft-save-count',count:bs.length};"
        "const b=bs[0];b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();"
        "return {ok:true,x:r.x+r.width/2,y:r.y+r.height/2,disabled:!!b.disabled};"
        "})()"
    )


def _draft_save_or_submit_button_expression():
    """Read finalReviewSubmitButton's CURRENT label without clicking anything.
    Same button element renders 下書きを保存 while the active tab is invalid
    and 審査に提出/Submit for Review once every tab is valid -- distinguishing
    the two is what lets the workspace-field fix stop safely instead of ever
    clicking a real submit-for-review action (CP3 alone does that)."""
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const bs=[...document.querySelectorAll('button.finalReviewSubmitButton')].filter(visible);"
        "if(bs.length!==1)return {ok:false,reason:'submit-button-count',count:bs.length};"
        "const t=(bs[0].textContent||'').trim();"
        "const label=['審査に提出','Submit for Review'].includes(t)?'submit':(t==='下書きを保存'?'draft':'unknown');"
        "return {ok:true,label:label,text:t};"
        "})()"
    )


def _workspace_conversation_field_expression(role):
    """Locate one of the Agent ワークスペース tab's 会話の開始/テストケース
    textareas by its fixed example placeholder (verified live, 2026-09-28,
    Agents 6273179459 / 9466718786). These render EMPTY on a same-Agent
    resumed draft's final review page even though CP1 already saved a real
    welcome message + test input earlier in the flow -- nothing re-hydrates
    them here, so the finalReviewSubmitButton stays labelled 下書きを保存
    instead of 審査に提出."""
    selectors = {
        "welcome": "(x.placeholder||'').includes('資料整理アシスタントです')",
        "input_placeholder": "(x.placeholder||'').includes('画像をアップロードして希望する結果を説明する')",
        "test_case_1": "(x.placeholder||'').includes('韻を踏んだキャッチーな広告コピー')",
        "test_case_2": "(x.placeholder||'').includes('たくさん買って')",
        # AI service provider tag input -- REQUIRED per drive_cp1.py's own gotcha
        # #7, and still empty live on both resumed drafts (2026-09-28,
        # 6273179459 / 9466718786) even after the four textareas above were
        # filled and saved.
        "ai_service_provider": "(x.placeholder||'').includes('OpenAI')&&(x.placeholder||'').includes('Anthropic')",
    }
    if role not in selectors:
        raise ValueError(role)
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        f"const xs=[...document.querySelectorAll('input,textarea')].filter(x=>visible(x)&&({selectors[role]}));"
        "if(xs.length!==1)return {ok:false,reason:'workspace-field-count',count:xs.length};"
        "return {ok:true,value:xs[0].value};"
        "})()"
    )


def _workspace_conversation_focus_expression(role):
    selectors = {
        "welcome": "(x.placeholder||'').includes('資料整理アシスタントです')",
        "input_placeholder": "(x.placeholder||'').includes('画像をアップロードして希望する結果を説明する')",
        "test_case_1": "(x.placeholder||'').includes('韻を踏んだキャッチーな広告コピー')",
        "test_case_2": "(x.placeholder||'').includes('たくさん買って')",
        "ai_service_provider": "(x.placeholder||'').includes('OpenAI')&&(x.placeholder||'').includes('Anthropic')",
    }
    if role not in selectors:
        raise ValueError(role)
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        f"const xs=[...document.querySelectorAll('input,textarea')].filter(x=>visible(x)&&({selectors[role]}));"
        "if(xs.length!==1)return {ok:false,reason:'workspace-focus-count',count:xs.length};"
        "const x=xs[0];x.scrollIntoView({block:'center'});x.focus();return {ok:true};"
        "})()"
    )


def _parse_listing_conversation_fields(listing_path):
    """Extract welcomeMessage (and its 'Example:' line as test_input) from a
    catalog LISTING.md -- same parsing build_config.py uses to build CP1's
    config.json. Returns (welcome, test_input); either may be None if the
    file is missing/unparsable (never raises)."""
    try:
        text = open(listing_path, encoding="utf-8").read()
    except OSError:
        return None, None
    m = re.search(r"## welcomeMessage\n(.+?)\n## detailedDescription", text, re.S)
    welcome = m.group(1).strip() if m else None
    test_input = None
    if welcome:
        ex = re.search(r'Example:\s*"?([^"\n]+)"?', welcome)
        test_input = ex.group(1).strip() if ex else None
    return welcome, test_input


def _dpa_agreement_checkbox_expression():
    """Locate the REQUIRED Capafy 'データ処理契約' (Data Processing Agreement)
    checkbox next to the 主要モデル提供元 disclosure field (drive_cp1.py's own
    gotcha #13: "DPA checkbox -- REQUIRED, red if unchecked"). Nothing in the
    CP2 resume/llm_config path ever checks it, and it renders UNCHECKED on a
    resumed draft (verified live 2026-09-28, 6273179459 / 9466718786) --
    leaving finalReviewTabStatusInvalid even after every textarea above is
    filled and saved."""
    return (
        "(() => {"
        "const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);"
        "const xs=[...document.querySelectorAll('input[type=checkbox].pricingTabAgreementCheckboxInput')].filter(visible);"
        "if(xs.length!==1)return {ok:false,reason:'dpa-checkbox-count',count:xs.length};"
        "const x=xs[0];x.scrollIntoView({block:'center'});const r=x.getBoundingClientRect();"
        "return {ok:true,checked:x.checked,x:r.x+r.width/2,y:r.y+r.height/2};"
        "})()"
    )


def _raw_fill_workspace_conversation_fields(page, listing_path):
    """Fill the Agent ワークスペース tab's welcome-message / input-placeholder /
    test-case / AI-service-provider fields from the catalog LISTING.md, and
    check the REQUIRED DPA agreement checkbox, when a resumed draft's final
    review page renders them empty/unchecked (LLM モデル and 推定実行時間
    already have their own fixes above/below; only 会話の開始 + テストケース
    + データ共有に関する申告 are missing here). Idempotent: a field that
    already has a value/is already checked (a fresh CP1 flow already filled
    it) is left untouched. Returns True if there was nothing to do or the
    draft-save succeeded; False only if LISTING itself can't be parsed (this
    fix is best-effort next to the hosted-key gate, which is the
    authoritative is_confirmed_config_keys check)."""
    welcome, test_input = _parse_listing_conversation_fields(listing_path)
    if not welcome:
        print(f"workspace conversation fields: LISTING unreadable/unparsable ({listing_path})")
        return False

    # CP3 reloads the final review page and calls this at once, so the tab bar itself may not be
    # rendered yet (2026-10-08 20:08, draft 3257394572): no click, every field "absent", and a false
    # "already filled". Wait for the tab, click it, then wait for its fields.
    tab = None
    tab_waited = 0.0
    while tab_waited < 10.0:
        tab = page.evaluate(_WORKSPACE_TAB_EXPRESSION)
        if isinstance(tab, dict) and tab.get("ok"):
            break
        time.sleep(0.5)
        tab_waited += 0.5
    else:
        print("workspace tab: not rendered within 10s; continuing with what is present")
    if isinstance(tab, dict) and tab.get("ok"):
        for kind in ("mousePressed", "mouseReleased"):
            page.call("Input.dispatchMouseEvent", {"type": kind, "x": float(tab["x"]), "y": float(tab["y"]), "button": "left", "clickCount": 1})
        # Wait for the tab content to render instead of a fixed 1s sleep. On 2026-10-08 (drafts
        # 8580209829 / 3257394572) the fields were not there after 1s, every role was skipped as
        # "absent on this layout", the function printed "already filled" while the required provider
        # field and the DPA checkbox were empty, and the submit button never appeared.
        waited = 0.0
        while waited < 10.0:
            probe = page.evaluate(_workspace_conversation_field_expression("welcome"))
            if isinstance(probe, dict) and probe.get("ok"):
                break
            time.sleep(0.5)
            waited += 0.5
        else:
            print("workspace tab: fields did not render within 10s; continuing with what is present")

    example = test_input or welcome
    values = {
        "welcome": welcome,
        "input_placeholder": example,
        "test_case_1": example,
        "test_case_2": example,
        # tag-style input (Enter commits the chip) -- matches this pipeline's
        # actual hosted provider (OpenRouter), same value drive_cp1.py's old
        # CP1 form used for this exact field.
        "ai_service_provider": "openrouter.ai",
    }
    filled_any = False
    for role, value in values.items():
        state = page.evaluate(_workspace_conversation_field_expression(role))
        if not isinstance(state, dict) or not state.get("ok"):
            continue  # field absent on this layout -- not fatal, skip it
        if state.get("value"):
            continue  # already filled -- never overwrite an existing value
        focused = page.evaluate(_workspace_conversation_focus_expression(role))
        if not isinstance(focused, dict) or not focused.get("ok"):
            raise RuntimeError(f"workspace {role} focus failed ({focused})")
        page.call("Input.insertText", {"text": value})
        if role == "ai_service_provider":
            page.press_enter()
        filled_any = True

    dpa = page.evaluate(_dpa_agreement_checkbox_expression())
    if isinstance(dpa, dict) and dpa.get("ok") and not dpa.get("checked"):
        for kind in ("mousePressed", "mouseReleased"):
            page.call("Input.dispatchMouseEvent", {
                "type": kind, "x": float(dpa["x"]), "y": float(dpa["y"]),
                "button": "left", "clickCount": 1,
            })
        print("workspace DPA agreement checkbox: checked")
        filled_any = True

    if not filled_any:
        print("workspace conversation fields: already filled")
        return True

    # The DPA checkbox's onChange can itself flip finalReviewSubmitButton's
    # label from 下書きを保存 to 審査に提出 the instant the tab becomes valid
    # (observed live, 2026-09-28) -- before any explicit save click. Never
    # click it in that state (CP3 alone submits); the button's own commit
    # already happened via the checkbox's onChange.
    submit_state = page.evaluate(_draft_save_or_submit_button_expression())
    if isinstance(submit_state, dict) and submit_state.get("ok") and submit_state.get("label") == "submit":
        print("workspace conversation fields: tab already valid (審査に提出 visible) -- not clicking it")
        return True

    save = page.evaluate(_draft_save_button_expression())
    if not isinstance(save, dict) or not save.get("ok"):
        raise RuntimeError(f"ambiguous draft-save button ({save})")
    if save.get("disabled"):
        raise RuntimeError("draft-save button is disabled")
    for kind in ("mousePressed", "mouseReleased"):
        page.call("Input.dispatchMouseEvent", {
            "type": kind, "x": float(save["x"]), "y": float(save["y"]),
            "button": "left", "clickCount": 1,
        })
    print("workspace conversation fields: filled + draft saved")
    time.sleep(3)
    return True


def _raw_fix_display_model(page, display_model):
    """Idempotently set the Agent card's "LLM モデル" display field to
    <display_model> (preferring a matching preset option over free text --
    free-text entry is not automated, since every model this pipeline hosts
    has a preset), persist via the page's own "下書きを保存" draft-save
    button, then verify against the official Agent detail API.

    Independent of the Hosted Key card: it also runs when that card is
    already saved/collapsed, because 2026-09-28 (Hook Lab 8123079349) showed
    the official `model` field can stay stale ("Claude Sonnet 4.6") even
    after the hosted key is confirmed -- nothing had ever driven this
    separate combobox.
    """
    combo = page.evaluate(_display_model_combobox_expression())
    if not isinstance(combo, dict) or not combo.get("ok"):
        raise RuntimeError(f"ambiguous display-model combobox ({combo})")

    if combo.get("value") != display_model:
        focused = page.evaluate(_display_model_focus_expression())
        if not isinstance(focused, dict) or not focused.get("ok"):
            raise RuntimeError(f"display-model focus failed ({focused})")
        page.call("Input.insertText", {"text": display_model})

        deadline = time.monotonic() + RAW_SECTION_TIMEOUT_S
        option = None
        while time.monotonic() < deadline:
            option = page.evaluate(_display_model_option_expression(display_model))
            if isinstance(option, dict) and option.get("ok"):
                break
            count = option.get("count") if isinstance(option, dict) else None
            if isinstance(count, (int, float)) and not isinstance(count, bool) and count > 1:
                raise RuntimeError(f"ambiguous display-model preset option ({option})")
            time.sleep(RAW_SECTION_POLL_S)
        if not isinstance(option, dict) or not option.get("ok"):
            raise RuntimeError(
                f"no exact preset option for display model {display_model!r} ({option}); "
                "free-text fallback is not automated"
            )
        for kind in ("mousePressed", "mouseReleased"):
            page.call("Input.dispatchMouseEvent", {
                "type": kind, "x": float(option["x"]), "y": float(option["y"]),
                "button": "left", "clickCount": 1,
            })
        time.sleep(0.5)

        combo_after = page.evaluate(_display_model_combobox_expression())
        if not isinstance(combo_after, dict) or combo_after.get("value") != display_model:
            raise RuntimeError(f"display-model combobox did not commit {display_model!r} ({combo_after})")

        # Same race as the workspace-fields fix above (2026-09-28): once every
        # tab is valid, finalReviewSubmitButton's own onChange can flip its
        # label from 下書きを保存 to 審査に提出 the instant the model combo
        # commits -- before this function ever clicks anything. Querying for
        # the now-absent 下書きを保存 button then returns count=0
        # ("ambiguous draft-save button") even though the combo pick already
        # persisted. Check the shared submit/draft button first and skip the
        # click when the tab is already valid; CP3 alone submits.
        submit_state = page.evaluate(_draft_save_or_submit_button_expression())
        if isinstance(submit_state, dict) and submit_state.get("ok") and submit_state.get("label") == "submit":
            print("display model: tab already valid (審査に提出 visible) -- not clicking draft-save")
        else:
            save = page.evaluate(_draft_save_button_expression())
            if not isinstance(save, dict) or not save.get("ok"):
                raise RuntimeError(f"ambiguous draft-save button ({save})")
            if save.get("disabled"):
                raise RuntimeError("draft-save button is disabled")
            for kind in ("mousePressed", "mouseReleased"):
                page.call("Input.dispatchMouseEvent", {
                    "type": kind, "x": float(save["x"]), "y": float(save["y"]),
                    "button": "left", "clickCount": 1,
                })
            print("draft save: clicked")
        time.sleep(3)
    else:
        print("display model already:", display_model)

    agent_info = page.evaluate(_agent_id_from_page_expression())
    agent_id = agent_info.get("agentId") if isinstance(agent_info, dict) and agent_info.get("ok") else None
    if not agent_id:
        raise RuntimeError(f"could not read agent id from page ({agent_info})")
    verified = _verify_official_display_model(agent_id, display_model)
    print("official model verified:", verified)
    return verified


def _raw_configure_hosted_key(page, key, section_mode):
    """Fill + save + verify the CP2 Hosted Key card for <section_mode>.
    Extracted from _raw_cp2 so the caller can run the independent
    display-model fix afterward regardless of whether this ran at all (it is
    skipped entirely when the card is already saved/collapsed)."""
    if section_mode == "workspace_llm_form":
        return _raw_configure_workspace_llm(page, key)
    if section_mode == "configured_proxy":
        # The form itself supplies the provider metadata after the field
        # paths are saved; it intentionally has no separate model input.
        _raw_configure_proxy_form(page, key)
        print("configured proxy fields: True")
    elif section_mode == "llm_config_form":
        # Third CP2 layout (2026-09-28, Agent ワークスペース tab, same-Agent
        # update/resumed drafts): a direct "LLM 設定とホスト型キー" Hosted Key
        # card, already in edit mode (no edit-pencil step, unlike the
        # provider-path layout).
        _raw_configure_llm_form(page, key)
        print("llm config form fields: True")
    else:
        has_input = page.evaluate(
            "[...document.querySelectorAll('input')].some(i=>{const v=i.value||'';return v.includes('api.')||v.includes('openrouter')})"
        )
        if not has_input:
            page.strict_click(OPENROUTER_API_KEY_PATH, "edit")
            time.sleep(2)

        page.strict_focus_and_insert(OPENROUTER_BASE_URL_PATH, "base", BASE_URL)
        print("baseurl: True")
        page.strict_focus_and_insert(OPENROUTER_API_KEY_PATH, "model", MODEL)
        page.press_enter()
        print("model: True")
        page.strict_focus_and_insert(OPENROUTER_API_KEY_PATH, "key", key)
        print("key pasted len", len(key))

    def card_save():
        return page.strict_click(OPENROUTER_API_KEY_PATH, "save")

    if not card_save():
        raise RuntimeError("CP2 card Save is disabled")
    time.sleep(2)
    blockrun_state = page.evaluate("(() => {const path='models.providers.blockrun.apiKey';const xs=[...document.querySelectorAll('*')].filter(x=>(x.textContent||'').trim()===path&&![...x.children].some(c=>(c.textContent||'').trim()===path));if(xs.length===0)return {ok:true,none:true};if(xs.length!==1)return {ok:false,count:xs.length};let card=xs[0],bs=[];for(let k=0;k<12&&card;k++,card=card.parentElement){const ys=[...card.querySelectorAll('button')];if(ys.length===1){bs=ys;break;}}if(bs.length!==1)return {ok:false,count:bs.length};const b=bs[0];b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return {ok:true,x:r.x+r.width/2,y:r.y+r.height/2};})()")
    if not isinstance(blockrun_state, dict) or not blockrun_state.get("ok"):
        raise RuntimeError(f"ambiguous blockrun card ({blockrun_state})")
    if not blockrun_state.get("none"):
        page.click_coords("(() => {const path='models.providers.blockrun.apiKey';const xs=[...document.querySelectorAll('*')].filter(x=>(x.textContent||'').trim()===path&&![...x.children].some(c=>(c.textContent||'').trim()===path));if(xs.length!==1)return null;let card=xs[0],b=null;for(let k=0;k<12&&card&&!b;k++,card=card.parentElement){const ys=[...card.querySelectorAll('button')];if(ys.length===1)b=ys[0];}if(!b)return null;b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2};})()")
    time.sleep(1.2)

    if section_mode == "llm_config_form":
        # This card's own Save both persists and verifies the hosted key in
        # one click -- there is no separate page-level "キーを確認して保存"
        # button for this layout (live-confirmed 2026-09-28, Agent
        # 8123079349: official is_confirmed_config_keys flipped to true
        # right after this card's Save, with `page.strict_click(...,
        # "confirm")` correctly finding nothing to click). Watch a short
        # window for an error toast; its absence is the success signal.
        # ponytail: no positive "saved" toast is known for this layout, so
        # success is inferred from the absence of an error within the
        # window; tighten if a false-positive is ever observed.
        result = "VERIFIED"
        deadline = time.monotonic() + 9
        while time.monotonic() < deadline:
            time.sleep(3)
            toast = page.evaluate(
                "[...document.querySelectorAll('*')].map(e=>(e.textContent||'').trim())"
                ".find(x=>/Verification failed|失敗|エラー/i.test(x)&&x.length<120)||''"
            )
            if toast:
                result = "FAILED: " + str(toast)[:80]
                break
        print("RESULT:", result)
        return result == "VERIFIED"

    baseline_url = str(page.evaluate("location.href") or "")
    baseline_toasts = page.evaluate("[...document.querySelectorAll('*')].map(e=>(e.textContent||'').trim()).filter(x=>/キー確認済み|Verification failed|失敗|エラー/i.test(x)&&x.length<120)") or []
    if not page.strict_click(OPENROUTER_API_KEY_PATH, "confirm"):
        raise RuntimeError("CP2 confirmation button is disabled")
    print("save: clicked")

    result = "TIMEOUT"
    deadline = time.monotonic() + RAW_NAV_TIMEOUT_S
    for _ in range(10):
        if time.monotonic() >= deadline:
            break
        time.sleep(3)
        toast = page.evaluate("[...document.querySelectorAll('*')].map(e=>(e.textContent||'').trim()).find(x=>/キー確認済み|Verification failed|失敗|エラー/i.test(x)&&x.length<120)||''")
        url = page.evaluate("location.href") or ""
        if _fresh_success(baseline_url, baseline_toasts, url, toast):
            result = "VERIFIED"
            break
        if "Verification failed" in str(toast) or "失敗" in str(toast):
            result = "FAILED: " + str(toast)[:80]
            break
    print("RESULT:", result)
    return result == "VERIFIED"


def _raw_cp2(cp2, key, cdp_base):
    """Drive CP2 through an existing page websocket when browser attach is unavailable."""
    _validate_cp2_url(cp2)
    try:
        targets = _raw_page_targets(cdp_base, cp2)
    except RuntimeError:
        try:
            targets = _capafy_page_targets(cdp_base)
        except RuntimeError:
            # A deterministic resume of a CP1-confirmed draft never ran the CP1
            # agent, so no createAgent tab exists (2026-09-28, 9466718786).
            _open_cp2_target(cdp_base, cp2)
            targets = _raw_page_targets(cdp_base, cp2)
    page = _open_responsive_page(targets)
    try:
        page.call("Page.enable")
        page.call("Page.bringToFront")
        _wait_raw_navigation(page, cp2)

        try:
            section_mode = _ensure_raw_provider_section(page)
        except RuntimeError as hydrate_error:
            if "did not hydrate" not in str(hydrate_error):
                raise
            # No known fillable Hosted Key layout is present. Most likely it
            # is already saved/collapsed from a prior run (2026-09-28, Hook
            # Lab 8123079349: is_confirmed_config_keys was already true here
            # after PR #6092) -- nothing to fill. Fall through to the
            # independent display-model fix below instead of failing closed
            # on a step that is already done.
            print(f"hosted key section: none fillable, assuming already configured ({hydrate_error})")
            section_mode = None

        key_host_verified = True
        if section_mode is not None:
            key_host_verified = _raw_configure_hosted_key(page, key, section_mode)

        # Independent of the Hosted Key card and the display-model fix below:
        # a resumed draft's Agent ワークスペース tab can render the
        # welcome-message/input-placeholder/test-case fields empty even when
        # the hosted key is already confirmed, which leaves the whole tab
        # invalid and 審査に提出 never appears (2026-09-28, 6273179459 /
        # 9466718786). Runs whenever a LISTING.md is known for this agent.
        listing_path = os.environ.get("CAPAFY_LISTING_PATH", "").strip()
        display_model = os.environ.get("CAPAFY_DISPLAY_MODEL", "").strip()

        # Pick the display model BEFORE filling the workspace fields. While those fields are
        # empty the tab is invalid and the page still shows 下書きを保存, so the pick is
        # persisted by a draft-save. Filling them first (2026-10-08, new agent 6569536614) made
        # the tab valid, the button turned into 審査に提出, the pick was never saved, the
        # official model read None and CP3 correctly refused to submit.
        display_verified = True
        if display_model:
            display_verified = _raw_fix_display_model(page, display_model)

        workspace_fields_ok = True
        if listing_path:
            workspace_fields_ok = _raw_fill_workspace_conversation_fields(page, listing_path)

        return key_host_verified and workspace_fields_ok and display_verified
    finally:
        page.close()

def main():
    if len(sys.argv) < 2:
        print("ERR: need CP2 url"); sys.exit(1)
    cp2 = _resolve_cp2_url(sys.argv[1])
    key = os.environ.get("CAPAFY_HOST_OPENROUTER_KEY", "").strip()
    if not key:
        # fallback: read from the per-user Life Manager state env
        try:
            state_home = os.environ.get(
                "LIFE_MANAGER_STATE_HOME",
                os.path.expanduser("~/.local/state/life-manager"),
            )
            for ln in open(os.path.join(state_home, ".env")):
                if ln.startswith("CAPAFY_HOST_OPENROUTER_KEY="):
                    key = ln.split("=", 1)[1].strip(); break
        except Exception:
            pass
    if not key:
        print("ERR: CAPAFY_HOST_OPENROUTER_KEY missing"); sys.exit(1)

    cdp = _require_cdp()
    transport = os.environ.get("CP2_TRANSPORT", "raw").strip().lower()
    if transport != "playwright":
        try:
            ok = _raw_cp2(cp2, key, cdp)
        except Exception as raw_error:
            print(f"ERR: raw page CDP failed ({type(raw_error).__name__}: {str(raw_error)[:160]})")
            sys.exit(1)
        sys.exit(0 if ok else 1)

    try:
        sync_playwright = _load_playwright()
    except Exception as import_error:
        print(f"ERR: Playwright dependency unavailable ({type(import_error).__name__})")
        sys.exit(1)
    p = sync_playwright().start()
    try:
        b = p.chromium.connect_over_cdp(cdp, timeout=CDP_ATTACH_TIMEOUT_MS)
    except Exception as attach_error:
        try:
            p.stop()
        except Exception:
            pass
        print(f"ERR: Playwright CDP attach failed ({type(attach_error).__name__})")
        sys.exit(1)
    # Reuse an existing capafy tab; else create a BRAND-NEW tab. NEVER hijack a
    # daily-driver tab (ctx.pages[0] may be coconala/discord/etc and its watchdog
    # reverts a hijacked URL -> silent CP2 failure).
    allpg = [pg for c in b.contexts for pg in c.pages]
    cap = [pg for pg in allpg if _is_capafy_target_url(pg.url)]
    if cap:
        pg = cap[-1]
    else:
        ctx = b.contexts[0] if b.contexts else b.new_context()
        pg = ctx.new_page()
    pg.bring_to_front()
    _validate_cp2_url(cp2)
    pg.goto(cp2, wait_until="domcontentloaded", timeout=60000)
    before_url = pg.url
    if _location_key(before_url) != _location_key(cp2):
        raise RuntimeError("CP2 navigation reached the wrong origin/path")
    time.sleep(2)

    # expand 検出されたキー if collapsed
    if not pg.evaluate("""()=>[...document.querySelectorAll('input')].some(i=>/apiKey/.test(i.value||''))"""):
        label_state = pg.evaluate("(() => {const xs=[...document.querySelectorAll('*')].filter(x=>(x.textContent||'').trim()==='検出されたキー'&&![...x.children].some(c=>(c.textContent||'').trim()==='検出されたキー'));if(xs.length!==1)return {ok:false,count:xs.length};const x=xs[0];x.scrollIntoView({block:'center'});const r=x.getBoundingClientRect();return {ok:true,x:r.x+r.width/2,y:r.y+r.height/2};})()")
        if not isinstance(label_state, dict) or not label_state.get("ok"):
            raise RuntimeError(f"ambiguous detected-keys label ({label_state})")
        pg.mouse.click(float(label_state["x"]), float(label_state["y"]))
        time.sleep(1.5)

    # CRITICAL: the LLM card is often in SUMMARY mode (shows Base URL/Model as text, no inputs).
    # Click its Edit pencil (first button in the card) to enter edit mode, else field-setting finds nothing.
    has_input = pg.evaluate("""()=>[...document.querySelectorAll('input')].some(i=>{const v=i.value||'';return v.indexOf('api.')>-1||v.indexOf('openrouter')>-1;})""")
    if not has_input:
        if not _pw_strict_click(pg, OPENROUTER_API_KEY_PATH, "edit"):
            raise RuntimeError("CP2 OpenRouter edit button is disabled")
        time.sleep(2)

    _pw_strict_focus_and_insert(pg, OPENROUTER_BASE_URL_PATH, "base", BASE_URL)
    print("baseurl: True")
    _pw_strict_focus_and_insert(pg, OPENROUTER_API_KEY_PATH, "model", MODEL)
    pg.keyboard.press("Enter")
    print("model: True")
    _pw_strict_focus_and_insert(pg, OPENROUTER_API_KEY_PATH, "key", key)
    print("key pasted len", len(key))

    # ★ commit the LLM card. It is often in EDIT mode (Base URL/Model/Key inputs
    #   shown) — a card-level "Save"/"保存" button MUST be clicked to commit, else
    #   "キーを確認して保存" stays DISABLED. Scroll each Save into view and click. ★
    if not _pw_strict_click(pg, OPENROUTER_API_KEY_PATH, "save"):
        raise RuntimeError("CP2 card Save is disabled")
    time.sleep(2)

    # delete blockrun (localhost) card (always fails verification)
    blockrun_state = pg.evaluate("(() => {const path='models.providers.blockrun.apiKey';const xs=[...document.querySelectorAll('*')].filter(x=>(x.textContent||'').trim()===path&&![...x.children].some(c=>(c.textContent||'').trim()===path));if(xs.length===0)return {ok:true,none:true};if(xs.length!==1)return {ok:false,count:xs.length};let card=xs[0],bs=[];for(let k=0;k<12&&card;k++,card=card.parentElement){const ys=[...card.querySelectorAll('button')];if(ys.length===1){bs=ys;break;}}if(bs.length!==1)return {ok:false,count:bs.length};const b=bs[0];b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return {ok:true,x:r.x+r.width/2,y:r.y+r.height/2};})()")
    if not isinstance(blockrun_state, dict) or not blockrun_state.get("ok"):
        raise RuntimeError(f"ambiguous blockrun card ({blockrun_state})")
    if not blockrun_state.get("none"):
        pg.mouse.click(float(blockrun_state["x"]), float(blockrun_state["y"]))
    time.sleep(1.2)

    # final verify: click キーを確認して保存 once ENABLED. If disabled, the card is
    # still uncommitted -> click its Save again and retry (up to 4 rounds).
    baseline_toasts = pg.evaluate("[...document.querySelectorAll('*')].map(e=>(e.textContent||'').trim()).filter(x=>/キー確認済み|Verification failed|失敗|エラー/i.test(x)&&x.length<120)") or []
    if not _pw_strict_click(pg, OPENROUTER_API_KEY_PATH, "confirm"):
        raise RuntimeError("CP2 confirmation button is disabled")
    print("save: clicked")
    result = "TIMEOUT"
    deadline = time.monotonic() + RAW_NAV_TIMEOUT_S
    for _ in range(10):
        if time.monotonic() >= deadline:
            break
        time.sleep(3)
        toast = pg.evaluate("""()=>{const t=[...document.querySelectorAll('*')].map(e=>(e.textContent||'').trim()).find(x=>/キー確認済み|Verification failed|失敗|エラー/i.test(x)&&x.length<120);return t||'';}""")
        url = pg.evaluate("()=>location.href")
        if _fresh_success(before_url, baseline_toasts, url, toast):
            result = "VERIFIED"; break
        if "Verification failed" in toast or "失敗" in toast:
            result = "FAILED: " + toast[:80]; break
    print("RESULT:", result)
    sys.exit(0 if result == "VERIFIED" else 1)

if __name__ == "__main__":
    main()
