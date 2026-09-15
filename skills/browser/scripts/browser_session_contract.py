"""Shared browser-session boundary for the Python CDP helpers.

The JavaScript Steel adapter and these local helpers must make the same small set of
decisions: which browser endpoint is allowed, whether a visible browser is legal, and
which purpose is allowed to request it.  Keeping this validator dependency-free makes
it safe to import from recovery scripts before the rest of the application starts.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit


DEFAULT_BROWSER_ENDPOINT = "http://127.0.0.1:9222"


def _is_private_hostname(hostname: str) -> bool:
    host = hostname.rstrip(".").lower()
    if host in {"localhost"} or host.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return "." not in host
    return address.is_private or address.is_loopback or address.is_link_local


def normalize_endpoint(value: str | None = None, *, allow_public: bool = False) -> str:
    """Return a safe HTTP endpoint without credentials, path, or query material."""

    raw = str(value or DEFAULT_BROWSER_ENDPOINT).strip()
    parsed = urlsplit(raw)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.hostname.endswith(".")
    ):
        raise ValueError("browser session contract: endpoint URL invalid")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("browser session contract: endpoint URL invalid") from error
    if not _is_private_hostname(parsed.hostname):
        if not allow_public or parsed.scheme != "https":
            raise ValueError(
                "browser session contract: private endpoint required "
                "(public HTTPS requires explicit opt-in)"
            )
    hostname = parsed.hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    default_port = 443 if parsed.scheme == "https" else 80
    authority = hostname if port in {None, default_port} else f"{hostname}:{port}"
    return f"{parsed.scheme}://{authority}"


def browser_mode(*, mode: str | None = None, purpose: str | None = None) -> dict[str, object]:
    """Normalize display mode and reject accidental headed autonomous work."""

    selected_mode = str(mode or os.environ.get("CLOAK_BROWSER_MODE", "headless")).strip().lower()
    selected_purpose = str(
        purpose or os.environ.get("CLOAK_BROWSER_PURPOSE", "autonomous")
    ).strip().lower()
    if selected_mode not in {"headless", "headed"}:
        raise ValueError("browser session contract: mode unsupported")
    if selected_purpose not in {"autonomous", "human_gate", "diagnostic"}:
        raise ValueError("browser session contract: purpose unsupported")
    if selected_mode == "headed" and selected_purpose not in {"human_gate", "diagnostic"}:
        raise ValueError(
            "browser session contract: headed mode is only allowed for human_gate or diagnostic"
        )
    return {
        "mode": selected_mode,
        "purpose": selected_purpose,
        "headless": selected_mode == "headless",
    }


def configured_endpoint() -> str:
    """Resolve the same endpoint variable for local and remote CDP helpers."""

    allow_public = os.environ.get("LIFE_MANAGER_BROWSER_ALLOW_PUBLIC_ENDPOINT") == "1"
    return normalize_endpoint(
        os.environ.get("LIFE_MANAGER_BROWSER_ENDPOINT")
        or os.environ.get("CLOAK_CDP_BASE_URL")
        or DEFAULT_BROWSER_ENDPOINT,
        allow_public=allow_public,
    )
