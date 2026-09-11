#!/usr/bin/env python3
"""Read the authenticated TikTok identity from official navigation DOM."""
from __future__ import annotations

import argparse
import json
import time
from urllib.parse import unquote, urlparse

import cdp


READBACK_EXPRESSION = r"""
(() => {
  const profileLinks = Array.from(document.querySelectorAll(
    'header a[href*="/@"], nav a[href*="/@"], [data-e2e="profile-icon"] a[href*="/@"], a[data-e2e="profile-icon"][href*="/@"], [data-e2e="nav-profile"] a[href*="/@"], a[data-e2e="nav-profile"][href*="/@"]'
  )).map(node => node.href).filter(Boolean);
  const loginControls = document.querySelectorAll(
    '[data-e2e="top-login-button"], [data-e2e="login-button"], a[href*="/login"], button[data-e2e*="login"]'
  );
  return {
    url: location.href,
    profile_navigation_hrefs: [...new Set(profileLinks)],
    login_control_count: loginControls.length
  };
})()
"""


def _normalize_handle(value: str) -> str:
    handle = unquote(value).strip()
    if not handle.startswith("@"):
        handle = "@" + handle
    if len(handle) < 2 or "/" in handle:
        raise ValueError("expected TikTok handle such as @anicca.jp")
    return handle.casefold()


def _handle_from_profile_href(href: str) -> str | None:
    try:
        path = unquote(urlparse(href).path)
    except (TypeError, ValueError):
        return None
    segment = path.strip("/").split("/", 1)[0]
    return segment.casefold() if segment.startswith("@") and len(segment) > 1 else None


def classify_readback(observed: dict, expected_handle: str) -> dict:
    expected = _normalize_handle(expected_handle)
    handles = []
    for href in observed.get("profile_navigation_hrefs") or []:
        handle = _handle_from_profile_href(href)
        if handle and handle not in handles:
            handles.append(handle)
    login_count = observed.get("login_control_count")
    login_absent = isinstance(login_count, int) and not isinstance(login_count, bool) and login_count == 0
    if expected in handles and login_absent:
        status = "authenticated_expected_identity"
        authenticated = True
        selected = expected
    elif handles and login_absent:
        status = "authenticated_identity_mismatch"
        authenticated = False
        selected = handles[0]
    else:
        status = "identity_not_authenticated"
        authenticated = False
        selected = handles[0] if handles else None
    return {
        "version": 1,
        "provider": "tiktok.com",
        "status": status,
        "authenticated": authenticated,
        "expected_handle": expected,
        "observed_handle": selected,
        "url": observed.get("url"),
        "login_control_count": login_count,
    }


def readback(expected_handle: str, owner: str, timeout_seconds: float = 15.0) -> dict:
    target_id = cdp.new_target("https://www.tiktok.com/", owner)
    try:
        deadline = time.monotonic() + timeout_seconds
        last = None
        while True:
            last = cdp.evaluate(target_id, READBACK_EXPRESSION)
            if not isinstance(last, dict) or "__error__" in last:
                raise RuntimeError(f"TikTok identity readback failed: {last}")
            result = classify_readback(last, expected_handle)
            if result["authenticated"] or result["status"] == "authenticated_identity_mismatch":
                return result
            if time.monotonic() >= deadline:
                return result
            time.sleep(0.5)
    finally:
        cdp.close_target(target_id, owner)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-handle", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    args = parser.parse_args()
    result = readback(args.expected_handle, args.owner, args.timeout_seconds)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["authenticated"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
