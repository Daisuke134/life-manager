#!/usr/bin/env python3
"""Small repo-owned raw-CDP CLI used by Life Manager browser loops."""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from websocket import create_connection

import target_ownership


def _endpoint() -> tuple[str, str]:
    guarded = os.environ.get("CDP", "").strip()
    if guarded:
        parsed = urlsplit(guarded)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.port is None:
            raise ValueError("CDP must be an absolute http(s) URL with an explicit port")
        return parsed.hostname, str(parsed.port)
    return os.environ.get("CDP_HOST", "127.0.0.1"), os.environ.get("CDP_PORT", "9222")


HOST, PORT = _endpoint()
BASE = f"http://{HOST}:{PORT}"


def _rpc(ws, call_id: int, method: str, params: dict | None = None) -> dict:
    ws.send(json.dumps({"id": call_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") != call_id:
            continue
        if "error" in message:
            raise RuntimeError(f"{method}: {message['error']}")
        return message.get("result", {})


def _browser_ws() -> str:
    with urllib.request.urlopen(BASE + "/json/version", timeout=5) as response:
        return json.load(response)["webSocketDebuggerUrl"]


def _browser_call(method: str, params: dict) -> dict:
    ws = create_connection(_browser_ws(), timeout=20, suppress_origin=True)
    try:
        return _rpc(ws, 1, method, params)
    finally:
        ws.close()


def new_target(url: str = "about:blank", owner: str | None = None) -> str:
    """Create one page and bind its lifecycle to the declared owner."""
    owner = target_ownership.require_owner(owner)
    target_id = _browser_call("Target.createTarget", {"url": url})["targetId"]
    try:
        target_ownership.claim_target(
            target_id,
            owner,
            max_targets=int(os.environ.get("CLOAK_BROWSER_MAX_TABS_PER_OWNER", "1")),
        )
    except Exception:
        _browser_call("Target.closeTarget", {"targetId": target_id})
        raise
    return target_id


def close_target(target_id: str, owner: str | None = None) -> None:
    """Close only a page proven to belong to the declared owner."""
    owner = target_ownership.require_owner(owner)
    if not target_ownership.owns_target(target_id, owner):
        raise PermissionError(f"target {target_id} is not owned by {owner}")
    _browser_call("Target.closeTarget", {"targetId": target_id})
    target_ownership.release_target(target_id, owner)


def _page(tid: str):
    return create_connection(
        f"ws://{HOST}:{PORT}/devtools/page/{tid}", timeout=30, max_size=None, suppress_origin=True
    )


def evaluate(tid: str, expression: str):
    ws = _page(tid)
    try:
        result = _rpc(ws, 1, "Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True, "userGesture": True,
        })
        if result.get("exceptionDetails"):
            return {"__error__": str(result["exceptionDetails"].get("text") or result["exceptionDetails"])}
        return result.get("result", {}).get("value")
    finally:
        ws.close()


def navigate(tid: str, url: str) -> None:
    ws = _page(tid)
    try:
        _rpc(ws, 1, "Page.enable")
        _rpc(ws, 2, "Page.navigate", {"url": url})
        time.sleep(0.5)
    finally:
        ws.close()


def click(tid: str, x: int, y: int) -> dict:
    ws = _page(tid)
    try:
        _rpc(ws, 1, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        _rpc(ws, 2, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y,
                                                 "button": "left", "clickCount": 1})
        _rpc(ws, 3, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y,
                                                 "button": "left", "clickCount": 1})
        return {"clicked": [x, y]}
    finally:
        ws.close()


def insert(tid: str, value: str) -> dict:
    ws = _page(tid)
    try:
        _rpc(ws, 1, "Input.insertText", {"text": value})
        return {"ok": True, "inserted_chars": len(value)}
    finally:
        ws.close()


def key(tid: str, value: str) -> dict:
    ws = _page(tid)
    try:
        identity = ({
            "code": "Enter",
            "windowsVirtualKeyCode": 13,
            "nativeVirtualKeyCode": 13,
        } if value == "Enter" else {})
        for call_id, kind in enumerate(("keyDown", "keyUp"), start=1):
            _rpc(ws, call_id, "Input.dispatchKeyEvent", {
                "type": kind,
                "key": value,
                **identity,
            })
        return {"key": value}
    finally:
        ws.close()


def set_file(tid: str, selector: str, path: str, index: int = 0) -> dict:
    ws = _page(tid)
    try:
        _rpc(ws, 1, "DOM.enable")
        root = _rpc(ws, 2, "DOM.getDocument", {"depth": -1})["root"]["nodeId"]
        nodes = _rpc(ws, 3, "DOM.querySelectorAll", {"nodeId": root, "selector": selector}).get("nodeIds", [])
        if not nodes:
            return {"__error__": f"no file input for {selector}"}
        node = nodes[min(index, len(nodes) - 1)]
        _rpc(ws, 4, "DOM.setFileInputFiles", {"nodeId": node, "files": [path]})
        return {"set": path, "node": node, "of": len(nodes)}
    finally:
        ws.close()


def screenshot(tid: str, path: str) -> dict:
    if not os.path.isabs(path):
        raise ValueError("screenshot path must be absolute")
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    ws = _page(tid)
    try:
        _rpc(ws, 1, "Page.enable")
        encoded = _rpc(ws, 2, "Page.captureScreenshot", {
            "format": "png", "fromSurface": True, "captureBeyondViewport": False,
        })["data"]
    finally:
        ws.close()
    output.write_bytes(base64.b64decode(encoded))
    output.chmod(0o600)
    return {"path": str(output), "bytes": output.stat().st_size}


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit("usage: cdp.py new|nav|eval|screenshot|clickxy|insert|key|setfile|close ...")
    command, *args = argv
    if command == "new":
        print(new_target(
            args[0] if args else "about:blank",
            args[1] if len(args) > 1 else os.environ.get("CLOAK_BROWSER_OWNER"),
        ))
    elif command == "nav":
        navigate(args[0], args[1]); print("OK")
    elif command == "eval":
        source = sys.stdin.read() if args[1] == "-" else open(args[1], encoding="utf-8").read()
        print(json.dumps(evaluate(args[0], source), ensure_ascii=False))
    elif command == "screenshot":
        print(json.dumps(screenshot(args[0], args[1])))
    elif command == "clickxy":
        print(json.dumps(click(args[0], int(args[1]), int(args[2]))))
    elif command == "insert":
        print(json.dumps(insert(args[0], args[1])))
    elif command == "key":
        print(json.dumps(key(args[0], args[1])))
    elif command == "setfile":
        print(json.dumps(set_file(args[0], args[1], args[2], int(args[3]) if len(args) > 3 else 0)))
    elif command == "close":
        close_target(
            args[0], args[1] if len(args) > 1 else os.environ.get("CLOAK_BROWSER_OWNER")
        )
        print("CLOSED")
    else:
        raise SystemExit(f"unknown command: {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
