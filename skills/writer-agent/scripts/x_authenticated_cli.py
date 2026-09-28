#!/usr/bin/env python3
"""Run one read-only twitter-cli request with ephemeral cookies from daily-driver CDP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import urlopen
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from x_article_identity import is_link_only_x_article_shell_title  # noqa: E402


class XArticleCaptureError(RuntimeError):
    """The authenticated DOM did not expose a trustworthy X Article body."""


def _x_target_id(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or parsed.hostname not in {
        "x.com",
        "www.x.com",
        "twitter.com",
        "www.twitter.com",
    }:
        raise XArticleCaptureError("X Article URL must use an HTTPS X host")
    parts = [part for part in parsed.path.split("/") if part]
    if not parts or not re.fullmatch(r"[0-9]{3,}", parts[-1]):
        raise XArticleCaptureError("X Article URL has no stable target id")
    return parts[-1]


def _normalize_dom_text(value: str) -> str:
    if not isinstance(value, str):
        raise XArticleCaptureError("rendered Article body is not text")
    # inner_text() is already rendered text. HTML tags indicate that a public
    # shell or response body was supplied instead of a DOM text capture.
    if re.search(r"<(?:html|head|body|script|style|div|main|article)\b", value, re.I):
        raise XArticleCaptureError("rendered Article body is shell HTML")
    normalized = "\n".join(line.rstrip() for line in value.splitlines()).strip()
    if len(normalized) < 40:
        raise XArticleCaptureError("rendered Article body is too short")
    return normalized


MIN_ARTICLE_BODY_CHARS = 1000
MIN_ARTICLE_BLOCKS = 3
ARTICLE_DOM_SETTLE_SECONDS = 15
CDP_TARGET_ATTEMPTS = 2


_ARTICLE_BODY_JS = r"""
(() => {
  const articles = Array.from(document.querySelectorAll('article'));
  if (articles.length !== 1) return null;
  const selected = articles[0];
  const text = (selected.innerText || '').trim();
  const rect = selected.getBoundingClientRect();
  if (rect.width < 120 || rect.height < 40) return null;
  const blocks = text.split(/\n{2,}|\n+/).map((value) => value.trim()).filter(Boolean);
  const title = (document.title || '').trim();
  const shellLinkOnly = (() => {
    const tcoUrls = title.match(/https:\/\/t\.co\/[A-Za-z0-9]+/gi) || [];
    if (tcoUrls.length !== 1) return false;
    const match = title.match(/^(.*?)([「『“\"']?)(https:\/\/t\.co\/[A-Za-z0-9]+)([」』”\"']?)\s*\/\s*X$/is);
    if (!match) return false;
    const prefix = match[1];
    const opening = match[2];
    const closing = match[4];
    if (prefix && !/[：:]\s*$/.test(prefix)) return false;
    if (/https?:\/\/\S+/i.test(prefix)) return false;
    const pairs = {'「': '」', '『': '』', '“': '”', '\"': '\"', "'": "'"};
    if (opening) return pairs[opening] === closing;
    return !closing;
  })();
  return {
    selector: 'article',
    text,
    article_count: articles.length,
    block_count: blocks.length,
    shell_title: title,
    shell_link_only: shellLinkOnly,
    rendered_url: window.location.href,
    status_target_id: (window.location.pathname.match(/(?:status|article)\/(\d+)(?:$|\/)/) || [])[1] || null
  };
})()
"""


def _read_article_dom(url: str, cdp_url: str) -> tuple[str, str, dict[str, Any]]:
    """Read a stable rendered Article container through CDP Runtime.evaluate.

    This deliberately does not start Playwright or fall back to body.innerText. It
    attaches to an already-open daily-driver target when available; otherwise it
    creates one isolated CDP target, navigates it, and closes only that target.
    """

    def read_json(path: str) -> Any:
        try:
            with urlopen(f"{cdp_url.rstrip('/')}{path}", timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise XArticleCaptureError("daily-driver CDP endpoint unavailable") from error

    def page_target(targets: Any, *, target_id: str | None = None) -> dict[str, Any] | None:
        if not isinstance(targets, list):
            raise XArticleCaptureError("daily-driver CDP target list is invalid")
        return next(
            (
                item
                for item in targets
                if isinstance(item, dict)
                and item.get("type") == "page"
                and isinstance(item.get("webSocketDebuggerUrl"), str)
                and (target_id is None or item.get("id") == target_id)
                and (target_id is not None or str(item.get("url", "")).rstrip("/") == url.rstrip("/"))
            ),
            None,
        )

    def receive_command(socket: Any, command_id: int, *, deadline: float) -> dict[str, Any]:
        while time.monotonic() < deadline:
            try:
                value = json.loads(socket.recv())
            except Exception as error:
                raise XArticleCaptureError("X Article CDP websocket read failed") from error
            if isinstance(value, dict) and value.get("id") == command_id:
                return value
        raise XArticleCaptureError("X Article CDP command timed out")

    def send_command(socket: Any, command_id: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        socket.send(
            json.dumps(
                {
                    "id": command_id,
                    "method": method,
                    **({"params": params} if params is not None else {}),
                }
            )
        )
        return receive_command(socket, command_id, deadline=time.monotonic() + 10)

    def retryable_cdp_error(error: XArticleCaptureError) -> bool:
        return str(error) in {
            "X Article CDP websocket read failed",
            "X Article CDP websocket unavailable",
            "X Article CDP command timed out",
            "X Article CDP navigation read failed",
            "X Article CDP navigation failed",
            "X Article CDP navigation did not reach load",
            "X Article DOM evaluation failed",
            "rendered Article body selector or stable container is unavailable",
            "created X Article target did not become available",
        }

    def evaluate_stable_dom(socket: Any, command_id: int) -> dict[str, Any]:
        settle_deadline = time.monotonic() + ARTICLE_DOM_SETTLE_SECONDS
        value: Any = None
        while True:
            evaluated = send_command(
                socket,
                command_id,
                "Runtime.evaluate",
                {
                    "expression": _ARTICLE_BODY_JS,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
            )
            command_id += 1
            if "error" in evaluated:
                raise XArticleCaptureError("X Article DOM evaluation failed")
            value = evaluated.get("result", {}).get("result", {}).get("value")
            if isinstance(value, dict) and isinstance(value.get("text"), str):
                block_count = value.get("block_count")
                if (
                    len(value["text"]) >= MIN_ARTICLE_BODY_CHARS
                    and isinstance(block_count, int)
                    and block_count >= MIN_ARTICLE_BLOCKS
                ):
                    return dict(value)
            if time.monotonic() >= settle_deadline:
                raise XArticleCaptureError(
                    "rendered Article body selector or stable container is unavailable"
                )
            time.sleep(0.25)

    targets = read_json("/json/list")
    target = page_target(targets)
    try:
        import websocket

        if target is not None:
            socket = websocket.create_connection(
                str(target["webSocketDebuggerUrl"]), timeout=10
            )
            try:
                value = evaluate_stable_dom(socket, 1)
                return str(target["url"]), value["text"], value
            finally:
                socket.close()

        # The requested Article is not open. Create an isolated page target through
        # the existing browser endpoint, navigate it explicitly, and close only the
        # target created by this call. Existing daily-driver tabs are never touched.
        version = read_json("/json/version")
        browser_url = version.get("webSocketDebuggerUrl") if isinstance(version, dict) else None
        if not isinstance(browser_url, str) or not browser_url:
            raise XArticleCaptureError("daily-driver browser websocket unavailable")
        browser_socket = websocket.create_connection(browser_url, timeout=10)
        try:
            for attempt in range(CDP_TARGET_ATTEMPTS):
                created_target_id: str | None = None
                page_socket: Any | None = None
                command_base = attempt * 100 + 1
                try:
                    created = send_command(
                        browser_socket,
                        command_base,
                        "Target.createTarget",
                        {"url": "about:blank"},
                    )
                    created_target_id = str(created.get("result", {}).get("targetId") or "")
                    if not created_target_id:
                        raise XArticleCaptureError("daily-driver failed to create an Article target")
                    created_page: dict[str, Any] | None = None
                    for _ in range(50):
                        created_page = page_target(read_json("/json/list"), target_id=created_target_id)
                        if created_page is not None:
                            break
                        time.sleep(0.1)
                    if created_page is None:
                        raise XArticleCaptureError("created X Article target did not become available")
                    page_socket = websocket.create_connection(
                        str(created_page["webSocketDebuggerUrl"]), timeout=10
                    )
                    send_command(page_socket, command_base + 1, "Page.enable")
                    send_command(page_socket, command_base + 2, "Runtime.enable")
                    navigate_command_id = command_base + 3
                    page_socket.send(
                        json.dumps(
                            {
                                "id": navigate_command_id,
                                "method": "Page.navigate",
                                "params": {"url": url},
                            }
                        )
                    )
                    navigation_deadline = time.monotonic() + 15
                    navigated = False
                    loaded = False
                    while time.monotonic() < navigation_deadline:
                        try:
                            message = json.loads(page_socket.recv())
                        except Exception as error:
                            raise XArticleCaptureError("X Article CDP navigation read failed") from error
                        if not isinstance(message, dict):
                            continue
                        if message.get("id") == navigate_command_id:
                            if "error" in message:
                                raise XArticleCaptureError("X Article CDP navigation failed")
                            navigated = True
                        if message.get("method") == "Page.loadEventFired":
                            loaded = True
                        if navigated and loaded:
                            break
                    if not navigated or not loaded:
                        raise XArticleCaptureError("X Article CDP navigation did not reach load")
                    value = evaluate_stable_dom(page_socket, command_base + 4)
                    resolved_url = value.get("rendered_url")
                    if not isinstance(resolved_url, str) or resolved_url.rstrip("/") != url.rstrip("/"):
                        raise XArticleCaptureError("X Article CDP final URL mismatch")
                    return resolved_url, value["text"], dict(value)
                except XArticleCaptureError as error:
                    if attempt + 1 >= CDP_TARGET_ATTEMPTS or not retryable_cdp_error(error):
                        raise
                except Exception as error:
                    wrapped = XArticleCaptureError("X Article CDP websocket unavailable")
                    if attempt + 1 >= CDP_TARGET_ATTEMPTS or not retryable_cdp_error(wrapped):
                        raise wrapped from error
                finally:
                    if page_socket is not None:
                        page_socket.close()
                    if created_target_id:
                        try:
                            send_command(
                                browser_socket,
                                command_base + 90,
                                "Target.closeTarget",
                                {"targetId": created_target_id},
                            )
                        except Exception:
                            pass
        finally:
            browser_socket.close()
    except XArticleCaptureError:
        raise
    except Exception as error:
        raise XArticleCaptureError("X Article CDP websocket unavailable") from error


def capture_x_article_body(
    url: str,
    *,
    cdp_url: str | None = None,
    dom_reader: Callable[[str], tuple[str, str] | tuple[str, str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Capture one X Article's rendered DOM text with an immutable hash receipt.

    ``dom_reader`` is an offline test seam. Production callers leave it unset,
    which forces the authenticated daily-driver CDP path above.
    """

    target_id = _x_target_id(url)
    metadata: dict[str, Any] = {}
    if dom_reader is None:
        resolved_url, raw_body, metadata = _read_article_dom(
            url, cdp_url or os.environ.get("WRITER_CDP_URL", "http://localhost:9222")
        )
    else:
        try:
            result = dom_reader(url)
            if not isinstance(result, tuple) or len(result) not in {2, 3}:
                raise XArticleCaptureError("rendered Article DOM reader returned an invalid tuple")
            resolved_url, raw_body = result[0], result[1]
            if len(result) == 3:
                if not isinstance(result[2], dict):
                    raise XArticleCaptureError("rendered Article DOM metadata is invalid")
                metadata = result[2]
        except XArticleCaptureError:
            raise
        except Exception as error:
            raise XArticleCaptureError("rendered Article DOM reader failed") from error
    if not isinstance(resolved_url, str) or resolved_url.rstrip("/") != url.rstrip("/"):
        raise XArticleCaptureError("rendered Article DOM resolved to a different URL")
    body = _normalize_dom_text(raw_body)
    parsed_url = urlsplit(url)
    path_parts = [part for part in parsed_url.path.split("/") if part]
    expected_target_id = _x_target_id(url)
    status_path = bool(
        len(path_parts) >= 3
        and path_parts[-2] in {"status", "article"}
        and path_parts[-1] == expected_target_id
    )
    rendered_url = metadata.get("rendered_url", resolved_url)
    if not isinstance(rendered_url, str) or rendered_url.rstrip("/") != url.rstrip("/"):
        raise XArticleCaptureError("rendered Article DOM status URL mismatch")
    if metadata.get("status_target_id") != expected_target_id:
        raise XArticleCaptureError("rendered Article DOM target id mismatch")
    article_count = metadata.get("article_count")
    if article_count != 1:
        raise XArticleCaptureError("rendered Article DOM must contain exactly one article")
    article_container_count = metadata.get("article_container_count", article_count)
    if article_container_count != 1:
        raise XArticleCaptureError(
            "rendered Article DOM must contain exactly one article container"
        )
    selector = metadata.get("selector")
    if selector != "article":
        raise XArticleCaptureError("rendered Article DOM selector is not the article container")
    shell_title = metadata.get("shell_title")
    shell_link_only = metadata.get("shell_link_only") is True
    if not shell_link_only or not is_link_only_x_article_shell_title(shell_title):
        raise XArticleCaptureError("rendered Article shell is not a link-only t.co title")
    block_count = metadata.get("block_count")
    if not isinstance(block_count, int):
        block_count = len([line for line in body.splitlines() if line.strip()])
    if len(body) < MIN_ARTICLE_BODY_CHARS or block_count < MIN_ARTICLE_BLOCKS:
        raise XArticleCaptureError("rendered Article body is not longform")
    if not status_path:
        raise XArticleCaptureError("rendered Article status URL path is invalid")
    return {
        "source_url": url,
        "target_id": target_id,
        "full_body": body,
        "source_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "capture_method": "rendered_cdp_dom",
        "container_selector": selector,
        "article_identity": True,
        "rendered_identity": {
            "exact_status_url": rendered_url.rstrip("/") == url.rstrip("/"),
            "rendered_url": rendered_url,
            "target_id_match": metadata.get("status_target_id") == expected_target_id,
            "status_target_id": metadata.get("status_target_id"),
            "shell_title": shell_title,
            "shell_link_only": shell_link_only,
            "article_count": article_count,
            "article_container_count": article_container_count,
            "longform_chars": len(body),
            "block_count": block_count,
            "container_selector": selector,
        },
    }


def _cookies(cdp_url: str) -> dict[str, str]:
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            for context in browser.contexts:
                values = {
                    cookie["name"]: cookie["value"]
                    for cookie in context.cookies("https://x.com")
                    if cookie.get("name") in {"auth_token", "ct0"}
                }
                if values.get("auth_token") and values.get("ct0"):
                    return values
    except PlaywrightError as error:
        raise RuntimeError("daily-driver CDP unavailable") from error
    raise RuntimeError("daily-driver has no usable X authentication cookies")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handle", required=True)
    parser.add_argument("--limit", required=True, type=int)
    parser.add_argument("--cdp-url", default="http://localhost:9222")
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > 50:
        raise SystemExit("limit must be between 1 and 50")
    executable = shutil.which("twitter")
    if executable is None:
        raise SystemExit("twitter CLI unavailable")
    try:
        cookies = _cookies(args.cdp_url)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 75
    environment = {
        **os.environ,
        "TWITTER_AUTH_TOKEN": cookies["auth_token"],
        "TWITTER_CT0": cookies["ct0"],
    }
    try:
        result = subprocess.run(
            [executable, "user-posts", args.handle.lstrip("@"), "-n", str(args.limit), "--json"],
            capture_output=True,
            env=environment,
            timeout=40,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("authenticated X read timed out", file=sys.stderr)
        return 75
    if result.stdout:
        sys.stdout.buffer.write(result.stdout)
    if result.returncode != 0 and result.stderr:
        sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
