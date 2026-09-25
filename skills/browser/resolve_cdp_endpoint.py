#!/usr/bin/env python3
"""Resolve a registered browser identity to its live, profile-owned CDP endpoint.

Ports are only hints.  A machine can expose the same numeric port on IPv4 and
IPv6, or put a proxy in front of one listener.  The resolver therefore requires
both a valid ``/json/version`` response and a listening browser process whose
command line contains the registered profile.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterable


IDENTITY_RE = re.compile(r"^[a-z0-9][a-z0-9:_-]{1,127}$")
WS_RE = re.compile(r"^ws://.+/devtools/browser/([A-Za-z0-9-]{8,128})$")


def parse_registry(text: str) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for block in text.split("[[identity]]")[1:]:
        def field(name: str) -> str | None:
            match = re.search(rf"^{name}\s*=\s*\"([^\"]*)\"", block, re.M)
            return match.group(1) if match else None

        def number(name: str) -> int | None:
            match = re.search(rf"^{name}\s*=\s*(\d+)", block, re.M)
            return int(match.group(1)) if match else None

        identity = field("id")
        if identity:
            rows[identity] = {
                "id": identity,
                "profile": os.path.expanduser(field("profile") or ""),
                "declared_port": number("declared_port"),
            }
    return rows


def endpoint(host: str, port: int) -> str:
    rendered = f"[{host}]" if ":" in host else host
    return f"http://{rendered}:{port}"


def _profile_port(profile: str, declared_port: int | None) -> int | None:
    active = Path(profile) / "DevToolsActivePort"
    try:
        value = active.read_text(encoding="utf-8").splitlines()[0].strip()
        if value.isdigit() and 1 <= int(value) <= 65535:
            return int(value)
    except (OSError, IndexError):
        pass
    return declared_port


def _fetch_version(url: str) -> dict[str, object] | None:
    try:
        request = urllib.request.Request(f"{url}/json/version", method="GET")
        with urllib.request.urlopen(request, timeout=3) as response:
            if response.status != 200:
                return None
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    if not isinstance(value, dict):
        return None
    websocket = value.get("webSocketDebuggerUrl")
    match = WS_RE.fullmatch(str(websocket or ""))
    if not match:
        return None
    return {"uuid": match.group(1), "websocket": websocket}


def _listener_pids(host: str, port: int) -> list[int]:
    rendered_host = f"[{host}]" if ":" in host else host
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-a", f"-iTCP@{rendered_host}:{port}",
             "-sTCP:LISTEN", "-F", "p"],
            capture_output=True, text=True, check=False, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(line[1:]) for line in result.stdout.splitlines()
            if line.startswith("p") and line[1:].isdigit()]


def _command_line(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, check=False, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _profile_owned(
    profile: str,
    pids: Iterable[int],
    command: Callable[[int], str] = _command_line,
) -> tuple[int, str] | None:
    marker = f"--user-data-dir={os.path.realpath(profile)}"
    for pid in pids:
        command_line = command(pid)
        if marker in command_line:
            return pid, command_line
    return None


def resolve_identity(
    identity: str,
    registry: dict[str, dict[str, object]],
    *,
    fetch: Callable[[str], dict[str, object] | None] = _fetch_version,
    listeners: Callable[[str, int], list[int]] = _listener_pids,
    command: Callable[[int], str] = _command_line,
) -> dict[str, object]:
    if not IDENTITY_RE.fullmatch(identity):
        raise ValueError("identity_invalid")
    row = registry.get(identity)
    if not row:
        raise ValueError("identity_unknown")
    profile = str(row.get("profile") or "")
    port = _profile_port(profile, row.get("declared_port"))
    if not profile or port is None:
        raise ValueError("profile_port_unavailable")
    candidates = []
    saw_live_endpoint = False
    for host in ("127.0.0.1", "::1"):
        live = fetch(endpoint(host, port))
        if not live:
            continue
        saw_live_endpoint = True
        pids = listeners(host, port)
        owner = _profile_owned(profile, pids, command)
        if owner is None:
            continue
        pid, _ = owner
        candidates.append({
            "identity": identity,
            "profile": profile,
            "host": host,
            "port": port,
            "endpoint": endpoint(host, port),
            "uuid": str(live["uuid"]),
            "pid": pid,
        })
    if len(candidates) != 1:
        raise ValueError("endpoint_ambiguous" if candidates else (
            "endpoint_not_profile_owned" if saw_live_endpoint else "endpoint_unavailable"
        ))
    return candidates[0]


def resolve_all(registry: dict[str, dict[str, object]], **kwargs: object) -> list[dict[str, object]]:
    rows = []
    for identity in sorted(registry):
        try:
            rows.append(resolve_identity(identity, registry, **kwargs))
        except ValueError as error:
            rows.append({"identity": identity, "reachable": False, "error_class": str(error)})
    for row in rows:
        row.setdefault("reachable", True)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--identity")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    registry = parse_registry(Path(args.registry).expanduser().read_text(encoding="utf-8"))
    if args.all:
        print(json.dumps({"identities": resolve_all(registry)}, ensure_ascii=False))
        return 0
    if not args.identity:
        parser.error("--identity or --all is required")
    try:
        print(json.dumps(resolve_identity(args.identity, registry), ensure_ascii=False))
    except (OSError, ValueError) as error:
        print(json.dumps({"identity": args.identity, "reachable": False,
                          "error_class": str(error)}, ensure_ascii=False))
        return 10
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
