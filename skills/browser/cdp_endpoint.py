"""Validate a lease-provided local CDP endpoint before provider adapters use it."""

from __future__ import annotations

import os
from urllib.parse import urlsplit


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_MAX_ENDPOINT_LENGTH = 256


def _validated(value: str) -> tuple[str, int]:
    if not isinstance(value, str) or not value or len(value) > _MAX_ENDPOINT_LENGTH:
        raise ValueError("browser_endpoint_invalid")
    if any(ord(char) < 0x20 or char.isspace() for char in value):
        raise ValueError("browser_endpoint_invalid")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError("browser_endpoint_invalid") from None
    if (
        parsed.scheme != "http"
        or hostname not in _LOCAL_HOSTS
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("browser_endpoint_invalid")
    return value.rstrip("/"), port


def configured_cdp_endpoint(
    default: str,
    *,
    environment: str = "CLOAK_CDP_BASE_URL",
    require_identity_join: bool = False,
) -> str:
    """Return the lease endpoint, or the provider default when no lease is projected."""
    fallback, _ = _validated(default)
    candidate = os.environ.get(environment, "").strip()
    if not candidate:
        return fallback
    if require_identity_join and (
        not os.environ.get("LIFE_MANAGER_BROWSER_IDENTITY", "").strip()
        or not os.environ.get("LIFE_MANAGER_BROWSER_TARGET_OWNER", "").strip()
    ):
        raise ValueError("browser_identity_join_missing")
    endpoint, _ = _validated(candidate)
    return endpoint


def endpoint_port(endpoint: str) -> int:
    """Return the validated port from an endpoint."""
    _, port = _validated(endpoint)
    return port


__all__ = ["configured_cdp_endpoint", "endpoint_port"]
