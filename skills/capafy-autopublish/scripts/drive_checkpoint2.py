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

Usage: drive_checkpoint2.py <CP2_review_url>
Requires: CloakBrowser daemon on CDP :9222 (never close it), CAPAFY_HOST_OPENROUTER_KEY in env.
Exit 0 + prints VERIFIED on success; exit 1 on failure (fail-closed).
"""
import math
import os, sys, time, json, urllib.request
import re
from urllib.error import HTTPError
from urllib.parse import parse_qs, parse_qsl, urlsplit

BASE_URL = "https://openrouter.ai/api/v1"
MODEL    = os.environ.get("CAPAFY_HOSTED_MODEL_ID", "anthropic/claude-sonnet-4.6")
CDP_ATTACH_TIMEOUT_MS = int(os.environ.get("CP2_CDP_ATTACH_TIMEOUT_MS", "15000"))
RAW_NAV_TIMEOUT_S = float(os.environ.get("CP2_RAW_NAV_TIMEOUT_S", "30"))
RAW_CALL_TIMEOUT_S = float(os.environ.get("CP2_RAW_CALL_TIMEOUT_S", "20"))
RAW_SECTION_TIMEOUT_S = float(os.environ.get("CP2_SECTION_TIMEOUT_S", "15"))
RAW_SECTION_POLL_S = float(os.environ.get("CP2_SECTION_POLL_S", "0.25"))
CP2_HOST = "capafy.ai"
CP2_PATH = "/developer/createAgent"
OPENROUTER_API_KEY_PATH = "models.providers.openrouter.apiKey"
OPENROUTER_BASE_URL_PATH = "models.providers.openrouter.baseUrl"
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


def _detect_cdp():
    """CDP port drifts (observed 9222 -> 9223) — auto-detect instead of trusting
    a hardcoded port (self-fix-capafy-loop, 2026-07-21)."""
    override = os.environ.get("CP1_CDP_URL")
    if override:
        return _validate_cdp_base(override)
    for port in (9222, 9223):
        url = f"http://localhost:{port}"
        try:
            with urllib.request.urlopen(f"{url}/json/version", timeout=2) as r:
                if r.status == 200:
                    return url
        except Exception:
            continue
    return "http://localhost:9222"


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
        or not re.fullmatch(r"/C[0-9]+", parts.path)
        or parts.query
        or parts.fragment
    ):
        raise RuntimeError("CP2 short URL must be exactly https://api.capafy.ai/C<digits>")

    locations = _single_redirect_location(raw_url, "HEAD")
    if not locations:
        locations = _single_redirect_location(raw_url, "GET")
    if len(locations) != 1:
        raise RuntimeError("CP2 short URL must return exactly one redirect Location")
    resolved = locations[0]
    _validate_cp2_url(resolved)
    return resolved


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

    while time.monotonic() < deadline:
        state = provider_state()
        if require_count_one(state, "initial hydration"):
            return "provider"
        proxy_form = _bounded_page_evaluate(page, _configured_proxy_form_expression(), deadline)
        if isinstance(proxy_form, dict) and proxy_form.get("ok"):
            return "configured_proxy"
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


def _open_responsive_page(targets):
    probe_deadline = time.monotonic() + 5.0
    last_error = None
    for target in targets:
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


def _raw_cp2(cp2, key, cdp_base):
    """Drive CP2 through an existing page websocket when browser attach is unavailable."""
    _validate_cp2_url(cp2)
    try:
        targets = _raw_page_targets(cdp_base, cp2)
    except RuntimeError:
        targets = _capafy_page_targets(cdp_base)
    page = _open_responsive_page(targets)
    try:
        page.call("Page.enable")
        page.call("Page.bringToFront")
        _wait_raw_navigation(page, cp2)
        section_mode = _ensure_raw_provider_section(page)

        if section_mode == "configured_proxy":
            # The form itself supplies the provider metadata after the field
            # paths are saved; it intentionally has no separate model input.
            _raw_configure_proxy_form(page, key)
            print("configured proxy fields: True")
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

    cdp = _detect_cdp()
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
