#!/usr/bin/env python3
"""Read a provider page through an existing CDP browser and emit a receipt."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from websocket import WebSocketTimeoutException, create_connection
from job_journal import (
    JobStateError, reconcile_effect, resume_effect, start_effect,
    unresolved_effect, verify_effect,
)


class ProviderError(Exception):
    pass


class ProviderRendererError(ProviderError):
    pass


def load_playbook(root, provider):
    if not re.fullmatch(r"[a-z0-9-]+", provider):
        raise ProviderError("invalid provider name")
    path = root / "config" / "provider-playbooks" / f"{provider}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ProviderError("invalid provider playbook") from error
    if value.get("schema_version") != 1 or value.get("provider") != provider:
        raise ProviderError("unsupported provider playbook")
    return value


def read_json(url):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def choose_target(targets, playbook):
    wanted = playbook["target"]
    url_parts = wanted.get("url_contains_any", [wanted.get("url_contains", "")])
    title_parts = wanted.get("title_contains_any", [wanted.get("title_contains", "")])
    matches = [
        item for item in targets
        if item.get("type") == "page"
        and any(part in item.get("url", "") for part in url_parts)
        and any(part in item.get("title", "") for part in title_parts)
    ]
    if len(matches) != 1:
        raise ProviderError(f"expected one provider tab, found {len(matches)}")
    return matches[0]


def _evaluate_once(host, port, target_id):
    ws = create_connection(
        f"ws://{host}:{port}/devtools/page/{target_id}",
        timeout=20,
        max_size=None,
        suppress_origin=True,
    )
    try:
        ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": "({url:location.href,title:document.title,text:document.body.innerText})",
                "returnByValue": True,
            },
        }))
        while True:
            message = json.loads(ws.recv())
            if message.get("id") == 1:
                if "error" in message:
                    raise ProviderError("CDP evaluation failed")
                return message["result"]["result"]["value"]
    finally:
        ws.close()


def _send_cdp(ws, request_id, method, params=None, session_id=None):
    request = {
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    if session_id is not None:
        request["sessionId"] = session_id
    ws.send(json.dumps(request))


def _recv_cdp_object(ws):
    message = json.loads(ws.recv())
    if not isinstance(message, dict):
        raise ProviderRendererError("invalid CDP renderer recovery reply")
    return message


def _wait_cdp_reply(ws, request_id):
    while True:
        message = _recv_cdp_object(ws)
        if message.get("id") == request_id:
            if "error" in message:
                raise ProviderRendererError("CDP renderer recovery failed")
            return message.get("result", {})


def reload_renderer(host, port, target_id):
    """Reload one unresponsive provider renderer without restarting its browser."""
    ws = None
    try:
        version = read_json(f"http://{host}:{port}/json/version")
        if not isinstance(version, dict):
            raise ProviderRendererError("invalid browser CDP endpoint")
        browser_ws = version.get("webSocketDebuggerUrl")
        parsed = urlparse(browser_ws) if isinstance(browser_ws, str) else None
        if (
            parsed is None
            or parsed.scheme != "ws"
            or parsed.hostname != host
            or parsed.port != port
            or parsed.username is not None
            or parsed.password is not None
            or re.fullmatch(r"/devtools/browser/[^/?#]+", parsed.path) is None
            or bool(parsed.query)
            or bool(parsed.fragment)
        ):
            raise ProviderRendererError("invalid browser CDP endpoint")
        ws = create_connection(
            browser_ws, timeout=20, max_size=None, suppress_origin=True,
        )
        _send_cdp(
            ws, 1, "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        session_id = _wait_cdp_reply(ws, 1).get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ProviderRendererError("CDP renderer recovery failed")
        _send_cdp(ws, 2, "Page.enable", session_id=session_id)
        _wait_cdp_reply(ws, 2)
        _send_cdp(
            ws, 3, "Page.reload", {"ignoreCache": False}, session_id=session_id,
        )
        replied = False
        loaded = False
        deadline = time.monotonic() + 20
        while not (replied and loaded):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderRendererError("CDP renderer recovery timed out")
            ws.settimeout(remaining)
            message = _recv_cdp_object(ws)
            if message.get("id") == 3:
                if "error" in message:
                    raise ProviderRendererError("CDP renderer recovery failed")
                replied = True
            elif (
                message.get("method") == "Page.loadEventFired"
                and message.get("sessionId") == session_id
            ):
                loaded = True
    except ProviderRendererError:
        raise
    except (OSError, ValueError, KeyError, WebSocketTimeoutException) as error:
        raise ProviderRendererError("CDP renderer recovery failed") from error
    finally:
        if ws is not None:
            ws.close()


def evaluate(host, port, target_id):
    try:
        return _evaluate_once(host, port, target_id)
    except WebSocketTimeoutException:
        reload_renderer(host, port, target_id)
        try:
            page = _evaluate_once(host, port, target_id)
            page["renderer_recovered"] = True
            return page
        except WebSocketTimeoutException as error:
            raise ProviderRendererError("CDP renderer stayed unresponsive") from error


def cdp_call(ws, request_id, method, params=None):
    ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == request_id:
            if "error" in message:
                raise ProviderError(f"CDP {method} failed")
            return message.get("result", {})


def query_node(ws, request_id, selector):
    document = cdp_call(ws, request_id, "DOM.getDocument", {"depth": 1})
    result = cdp_call(
        ws, request_id + 1, "DOM.querySelector",
        {"nodeId": document["root"]["nodeId"], "selector": selector},
    )
    if not result.get("nodeId"):
        raise ProviderError("required login control is unavailable")
    return result["nodeId"], request_id + 2


def focus_and_type(ws, request_id, selector, value):
    node_id, request_id = query_node(ws, request_id, selector)
    resolved = cdp_call(ws, request_id, "DOM.resolveNode", {"nodeId": node_id})
    cdp_call(ws, request_id + 1, "Runtime.callFunctionOn", {
        "objectId": resolved["object"]["objectId"],
        "functionDeclaration": """function () {
            const setter = Object.getOwnPropertyDescriptor(
                HTMLInputElement.prototype, 'value'
            ).set;
            setter.call(this, '');
            this.dispatchEvent(new Event('input', {bubbles: true}));
            this.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
    })
    cdp_call(ws, request_id + 2, "DOM.focus", {"nodeId": node_id})
    cdp_call(ws, request_id + 3, "Input.insertText", {"text": value})
    return request_id + 4


def query_nodes(ws, request_id, selector):
    document = cdp_call(ws, request_id, "DOM.getDocument", {"depth": 1})
    result = cdp_call(
        ws, request_id + 1, "DOM.querySelectorAll",
        {"nodeId": document["root"]["nodeId"], "selector": selector},
    )
    return result.get("nodeIds", []), request_id + 2


def focus_and_type_node(ws, request_id, node_id, value):
    resolved = cdp_call(ws, request_id, "DOM.resolveNode", {"nodeId": node_id})
    cdp_call(ws, request_id + 1, "Runtime.callFunctionOn", {
        "objectId": resolved["object"]["objectId"],
        "functionDeclaration": """function () {
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(this, '');
            this.dispatchEvent(new Event('input', {bubbles: true}));
            this.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
    })
    cdp_call(ws, request_id + 2, "DOM.focus", {"nodeId": node_id})
    cdp_call(ws, request_id + 3, "Input.insertText", {"text": value})
    return request_id + 4


def click(ws, request_id, selector):
    node_id, request_id = query_node(ws, request_id, selector)
    return click_node(ws, request_id, node_id)


def click_node(ws, request_id, node_id):
    box = cdp_call(ws, request_id, "DOM.getBoxModel", {"nodeId": node_id})
    content = box["model"]["content"]
    x = (content[0] + content[2]) / 2
    y = (content[1] + content[5]) / 2
    for event_type in ("mousePressed", "mouseReleased"):
        cdp_call(ws, request_id + 1, "Input.dispatchMouseEvent", {
            "type": event_type, "x": x, "y": y, "button": "left", "clickCount": 1,
        })
        request_id += 1
    return request_id + 1


def query_node_by_text(ws, request_id, selector, allowed_text):
    nodes, request_id = query_nodes(ws, request_id, selector)
    allowed = {" ".join(value.split()).casefold() for value in allowed_text}
    matches = []
    for node_id in nodes:
        resolved = cdp_call(ws, request_id, "DOM.resolveNode", {"nodeId": node_id})
        result = cdp_call(ws, request_id + 1, "Runtime.callFunctionOn", {
            "objectId": resolved["object"]["objectId"],
            "functionDeclaration": "function () { return (this.innerText || this.value || '').trim(); }",
            "returnByValue": True,
        })
        request_id += 2
        value = result.get("result", {}).get("value", "")
        if " ".join(value.split()).casefold() in allowed:
            matches.append(node_id)
    if len(matches) != 1:
        raise ProviderError("expected exactly one semantic login control")
    return matches[0], request_id


def click_text(ws, request_id, selector, allowed_text):
    node_id, request_id = query_node_by_text(ws, request_id, selector, allowed_text)
    resolved = cdp_call(ws, request_id, "DOM.resolveNode", {"nodeId": node_id})
    cdp_call(ws, request_id + 1, "Runtime.callFunctionOn", {
        "objectId": resolved["object"]["objectId"],
        "functionDeclaration": "function () { this.scrollIntoView({block: 'center'}); this.click(); }",
    })
    return request_id + 2


def playwright_click_text(host, port, expected_url, allowed_text, response_url_contains=None):
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://{host}:{port}")
            pages = [
                page for context in browser.contexts for page in context.pages
                if page.url == expected_url
            ]
            if len(pages) != 1:
                raise ProviderError("expected exactly one Playwright provider page")
            matches = []
            for text in allowed_text:
                locator = pages[0].get_by_role(
                    "button", name=re.compile(rf"^{re.escape(text)}$", re.IGNORECASE),
                )
                matches.extend(locator.nth(index) for index in range(locator.count()))
            if len(matches) != 1:
                raise ProviderError("expected exactly one Playwright semantic control")
            if response_url_contains:
                with pages[0].expect_response(
                    lambda response: response_url_contains in response.url,
                    timeout=20_000,
                ) as response_info:
                    matches[0].click(timeout=5_000)
                response = response_info.value
                return {
                    "http_status": response.status,
                    "url_sha256": hashlib.sha256(response.url.encode()).hexdigest(),
                    "body_sha256": hashlib.sha256(response.body()).hexdigest(),
                }
            matches[0].click(timeout=5_000)
            return None
    except ProviderError:
        raise
    except Exception as error:
        raise ProviderError("Playwright semantic activation failed") from error


def wait_for_selector(ws, request_id, selector, attempts=20):
    expression = f"document.querySelector({json.dumps(selector)}) !== null"
    for _ in range(attempts):
        result = cdp_call(ws, request_id, "Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
        })
        request_id += 1
        if result.get("result", {}).get("value") is True:
            return request_id
        time.sleep(0.25)
    raise ProviderError("next login stage did not render")


def selector_exists(ws, request_id, selector):
    result = cdp_call(ws, request_id, "Runtime.evaluate", {
        "expression": f"document.querySelector({json.dumps(selector)}) !== null",
        "returnByValue": True,
    })
    return result.get("result", {}).get("value") is True, request_id + 1


def read_login_credentials(path, section_name):
    path = path.expanduser()
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ProviderError("private credential file is unavailable")
    text = path.read_text(encoding="utf-8")
    section = re.search(
        rf"(?ms)^## {re.escape(section_name)}\n.*?(?=^## |\Z)", text,
    )
    if not section:
        raise ProviderError("provider credential section is unavailable")

    def field(label):
        match = re.search(
            rf"(?m)^- {re.escape(label)}:[ \t]*(.*?)[ \t]*$", section.group(),
        )
        value = match.group(1).strip().strip("`") if match else ""
        if not value:
            raise ProviderError("provider credential field is unavailable")
        return value

    return field("Login"), field("Password")


def extract_six_digit_codes(text, attributed_body):
    candidates = set(re.findall(r"(?<!\d)\d{6}(?!\d)", text or ""))
    if attributed_body:
        raw = bytes(attributed_body)
        for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
            decoded = raw.decode(encoding, errors="ignore")
            candidates.update(re.findall(r"(?<!\d)\d{6}(?!\d)", decoded))
    return candidates


def read_recent_messages_code(database, sender, max_age_seconds=600):
    database = database.expanduser()
    if not database.is_file():
        raise ProviderError("macOS Messages database is unavailable")
    cutoff = int((time.time() - 978307200 - max_age_seconds) * 1_000_000_000)
    uri = f"file:{database}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            """SELECT m.text, m.attributedBody
               FROM message AS m JOIN handle AS h ON h.ROWID = m.handle_id
               WHERE h.id = ? AND m.is_from_me = 0 AND m.date >= ?
               ORDER BY m.date DESC LIMIT 10""",
            (sender, cutoff),
        ).fetchall()
    candidates = set()
    for text, attributed_body in rows:
        candidates.update(extract_six_digit_codes(text, attributed_body))
    if len(candidates) != 1:
        raise ProviderError("expected exactly one recent device verification code")
    return candidates.pop()


def is_authenticated_state(state):
    return state in {"AUTHENTICATED", "APPLICATION_PENDING", "APPROVED", "REJECTED"}


def submit_login(args, playbook, target):
    login = playbook.get("login")
    if not login:
        raise ProviderError("provider login automation is unsupported")
    username, password = read_login_credentials(
        args.private_markdown, login["credential_section"],
    )
    ws = create_connection(
        f"ws://{args.cdp_host}:{args.cdp_port}/devtools/page/{target['id']}",
        timeout=20, max_size=None, suppress_origin=True,
    )
    login_response = None
    try:
        cdp_call(ws, 1, "DOM.enable")
        username_ready, request_id = selector_exists(ws, 2, login["username_selector"])
        password_ready, request_id = selector_exists(ws, request_id, login["password_selector"])
        if username_ready:
            request_id = focus_and_type(ws, request_id, login["username_selector"], username)
        if not password_ready:
            if not username_ready:
                raise ProviderError("username and password controls are unavailable")
            if login.get("username_submit_text_any"):
                playwright_click_text(
                    args.cdp_host, args.cdp_port, target["url"],
                    login["username_submit_text_any"],
                )
                request_id = wait_for_selector(ws, request_id, login["password_selector"])
        request_id = focus_and_type(ws, request_id, login["password_selector"], password)
        if login.get("password_submit_text_any"):
            login_response = playwright_click_text(
                args.cdp_host, args.cdp_port, target["url"],
                login["password_submit_text_any"],
                login.get("response_url_contains"),
            )
        else:
            request_id = wait_for_selector(ws, request_id, login["submit_selector"])
            click(ws, request_id, login["submit_selector"])
    finally:
        ws.close()
    return login_response


def classify(playbook, page):
    if not all(isinstance(page.get(key), str) for key in ("url", "title", "text")):
        raise ProviderError("invalid rendered page")
    allowed = set(playbook["allowed_origins"])
    parsed = urlparse(page["url"])
    if f"{parsed.scheme}://{parsed.netloc}" not in allowed:
        raise ProviderError("provider origin mismatch")
    for candidate in playbook["states"]:
        if (
            candidate.get("url_contains", "") in page["url"]
            and all(marker in page["text"] for marker in candidate.get("all_text", []))
        ):
            return candidate["state"], candidate["next_action"], candidate["all_text"]
    return playbook["fallback_state"], playbook["fallback_next_action"], []


def atomic_write(path, payload):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def observe(args):
    root = Path(__file__).resolve().parents[1]
    playbook = load_playbook(root, args.provider)
    base = f"http://{args.cdp_host}:{args.cdp_port}"
    target = choose_target(read_json(f"{base}/json/list"), playbook)
    page = evaluate(args.cdp_host, args.cdp_port, target["id"])
    state, next_action, markers = classify(playbook, page)
    return {
        "schema_version": 1,
        "receipt_type": "PROVIDER_OBSERVATION",
        "provider": args.provider,
        "state": state,
        "next_action": next_action,
        "url": page["url"],
        "title": page["title"],
        "matched_markers": markers,
        "renderer_recovered": bool(page.get("renderer_recovered", False)),
        "rendered_text_sha256": hashlib.sha256(page["text"].encode()).hexdigest(),
    }


def resume(args):
    root = Path(__file__).resolve().parents[1]
    playbook = load_playbook(root, args.provider)
    before = observe(args)
    submitted = False
    login_response = None
    if before["state"] == "SIGN_IN_REQUIRED":
        base = f"http://{args.cdp_host}:{args.cdp_port}"
        target = choose_target(read_json(f"{base}/json/list"), playbook)
        state = getattr(args, "state", args.receipt.expanduser().parent / "affiliate-state").expanduser()
        pending = unresolved_effect(state, "PROVIDER_LOGIN", args.provider)
        if pending:
            cooldown = int(pending.get("cooldown", {}).get("seconds", 300))
            retry_due = int(time.time()) - int(pending.get("updated_at", 0)) >= cooldown
            if retry_due and int(pending.get("attempt", 1)) < 3:
                job = resume_effect(state, "PROVIDER_LOGIN", args.provider)
            else:
                job = None
        else:
            job = start_effect(
                state, "PROVIDER_LOGIN", args.provider,
                {"operation": "submit_login", "provider": args.provider},
                {key: before.get(key) for key in ("state", "url", "rendered_text_sha256")}, 300,
            )
        if job is None:
            after = before
        else:
            login_response = submit_login(args, playbook, target)
            submitted = True
            for _ in range(20):
                time.sleep(1)
                after = observe(args)
                if after["state"] != "SIGN_IN_REQUIRED":
                    break
            if is_authenticated_state(after["state"]):
                verify_effect(state, job["job_id"], {
                    key: after.get(key) for key in ("state", "url", "rendered_text_sha256")
                })
    else:
        after = before
        state = getattr(args, "state", args.receipt.expanduser().parent / "affiliate-state").expanduser()
        if is_authenticated_state(after["state"]):
            reconcile_effect(state, "PROVIDER_LOGIN", args.provider, {
                key: after.get(key) for key in ("state", "url", "rendered_text_sha256")
            })
    receipt = {
        **after,
        "receipt_type": "PROVIDER_RESUME",
        "previous_state": before["state"],
        "submitted": submitted,
        "login_response": login_response,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(args.receipt.expanduser(), receipt)
    return receipt


def verify_device(args):
    root = Path(__file__).resolve().parents[1]
    playbook = load_playbook(root, args.provider)
    verification = playbook.get("device_verification")
    if not verification:
        raise ProviderError("provider device verification automation is unsupported")
    before = observe(args)
    if before["state"] != "DEVICE_VERIFICATION_REQUIRED":
        raise ProviderError("device verification page is unavailable")
    code = read_recent_messages_code(
        args.messages_database, verification["messages_sender"],
        verification.get("max_age_seconds", 600),
    )
    target = choose_target(
        read_json(f"http://{args.cdp_host}:{args.cdp_port}/json/list"), playbook,
    )
    state = args.state.expanduser()
    job = start_effect(
        state, "PROVIDER_DEVICE_VERIFY", args.provider,
        {"operation": "verify_device", "provider": args.provider},
        {key: before.get(key) for key in ("state", "url", "rendered_text_sha256")}, 300,
    )
    ws = create_connection(
        f"ws://{args.cdp_host}:{args.cdp_port}/devtools/page/{target['id']}",
        timeout=20, max_size=None, suppress_origin=True,
    )
    try:
        cdp_call(ws, 1, "DOM.enable")
        request_id = focus_and_type(ws, 2, verification["code_selector"], code)
        code = None
        playwright_click_text(
            args.cdp_host, args.cdp_port, target["url"],
            verification["submit_text_any"],
        )
    finally:
        code = None
        ws.close()
    after = None
    for _ in range(20):
        time.sleep(1)
        after = observe(args)
        if after["state"] != "DEVICE_VERIFICATION_REQUIRED":
            break
    if after is None or not is_authenticated_state(after["state"]):
        raise ProviderError("device verification outcome is ambiguous")
    verify_effect(state, job["job_id"], {
        key: after.get(key) for key in ("state", "url", "rendered_text_sha256")
    })
    receipt = {
        **after,
        "receipt_type": "PROVIDER_DEVICE_VERIFICATION",
        "previous_state": before["state"],
        "submitted": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(args.receipt.expanduser(), receipt)
    return receipt


def reset_password(args):
    root = Path(__file__).resolve().parents[1]
    playbook = load_playbook(root, args.provider)
    reset = playbook.get("password_reset")
    if not reset:
        raise ProviderError("provider password reset automation is unsupported")
    target = choose_target(read_json(f"http://{args.cdp_host}:{args.cdp_port}/json/list"), playbook)
    page = evaluate(args.cdp_host, args.cdp_port, target["id"])
    parsed = urlparse(page["url"])
    if parsed.path != reset["path"]:
        raise ProviderError("provider password reset page is unavailable")
    _, password = read_login_credentials(args.private_markdown, reset["credential_section"])
    state = args.state.expanduser()
    ws = create_connection(
        f"ws://{args.cdp_host}:{args.cdp_port}/devtools/page/{target['id']}",
        timeout=20, max_size=None, suppress_origin=True,
    )
    try:
        cdp_call(ws, 1, "DOM.enable")
        nodes, request_id = query_nodes(ws, 2, reset["password_selector"])
        if len(nodes) != 2:
            raise ProviderError("expected exactly two password reset fields")
        for node_id in nodes:
            request_id = focus_and_type_node(ws, request_id, node_id, password)
        job = start_effect(
            state, "PROVIDER_PASSWORD_RESET", args.provider,
            {"operation": "password_reset", "provider": args.provider},
            {"state": "RESET_FORM", "url": page["url"], "field_count": len(nodes)}, 900,
        )
        click(ws, request_id, reset["submit_selector"])
    finally:
        ws.close()
    after = None
    for _ in range(20):
        time.sleep(1)
        target = choose_target(read_json(f"http://{args.cdp_host}:{args.cdp_port}/json/list"), playbook)
        after = evaluate(args.cdp_host, args.cdp_port, target["id"])
        if urlparse(after["url"]).path != reset["path"]:
            break
    if after is None or urlparse(after["url"]).path == reset["path"]:
        raise ProviderError("provider password reset outcome is ambiguous")
    verify_effect(state, job["job_id"], {
        "state": "PASSWORD_RESET_ACCEPTED", "url": after["url"],
        "rendered_text_sha256": hashlib.sha256(after["text"].encode()).hexdigest(),
    })
    receipt = {
        "schema_version": 1, "receipt_type": "PROVIDER_PASSWORD_RESET",
        "provider": args.provider, "state": "PASSWORD_RESET_ACCEPTED",
        "url": after["url"], "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(args.receipt.expanduser(), receipt)
    return receipt


def poll(args, receipt):
    path = args.receipt.expanduser()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = None
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            if previous.get("provider") != args.provider:
                raise ProviderError("provider receipt mismatch")
            if previous.get("receipt_type") != "PROVIDER_POLL_STATE":
                previous = None
        previous_state = previous.get("state") if previous else None
        changed = previous_state != receipt["state"]
        sequence = (previous.get("sequence", 0) if previous else 0) + int(changed)
        material = "\0".join((
            args.provider,
            previous_state or "NONE",
            receipt["state"],
            receipt["rendered_text_sha256"],
        ))
        receipt.update({
            "receipt_type": "PROVIDER_POLL_STATE",
            "changed": changed,
            "previous_state": previous_state,
            "provider_next_action": receipt["next_action"],
            "next_action": receipt["next_action"] if changed else "NO_STATE_CHANGE",
            "sequence": sequence,
            "transition_id": (
                hashlib.sha256(material.encode()).hexdigest()
                if changed else previous.get("transition_id")
            ),
            "observed_at": datetime.now(timezone.utc).isoformat(),
        })
        login_job = None
        if receipt["state"] in {"AUTHENTICATED", "APPLICATION_PENDING", "APPROVED", "REJECTED"}:
            login_job = reconcile_effect(args.state.expanduser(), "PROVIDER_LOGIN", args.provider, {
                key: receipt.get(key) for key in ("state", "url", "rendered_text_sha256")
            })
        receipt["login_reconciled_job_id"] = login_job.get("job_id") if login_job else None
        atomic_write(path, receipt)
    if receipt["state"] in {"APPLICATION_PENDING", "APPROVED", "REJECTED"}:
        reconcile_effect(args.state.expanduser(), "PROVIDER_APPLICATION", args.provider, {
            key: receipt.get(key) for key in ("state", "url", "rendered_text_sha256")
        })
    return receipt


def main():
    parser = argparse.ArgumentParser(prog="affiliate provider")
    parser.add_argument(
        "command", choices=("inspect", "poll", "resume", "reset-password", "verify-device"),
    )
    parser.add_argument("--provider", required=True)
    parser.add_argument("--cdp-port", required=True, type=int)
    parser.add_argument("--cdp-host", default="127.0.0.1")
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--state", type=Path, default=Path("~/.local/state/life-manager/affiliate"))
    parser.add_argument(
        "--private-markdown", type=Path,
        default=Path("~/.config/anicca/affiliate-credentials.md"),
    )
    parser.add_argument(
        "--messages-database", type=Path,
        default=Path("~/Library/Messages/chat.db"),
    )
    args = parser.parse_args()

    if args.command == "reset-password":
        receipt = reset_password(args)
    elif args.command == "verify-device":
        receipt = verify_device(args)
    elif args.command == "resume":
        receipt = resume(args)
    else:
        receipt = observe(args)
    if args.command == "poll":
        receipt = poll(args, receipt)
    elif args.command == "inspect":
        atomic_write(args.receipt.expanduser(), receipt)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ProviderError, JobStateError, OSError, ValueError, KeyError, json.JSONDecodeError):
        print("affiliate provider: failed closed", file=sys.stderr)
        sys.exit(1)
