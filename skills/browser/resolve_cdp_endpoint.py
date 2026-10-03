#!/usr/bin/env python3
"""Resolve a registered browser identity to its live, profile-owned CDP endpoint.

Ports are only hints.  A machine can expose the same numeric port on IPv4 and
IPv6, or put a proxy in front of one listener.  The resolver therefore requires
both a valid ``/json/version`` response and a listening browser process whose
command line contains the registered profile.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
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


def _lsof_binary() -> str | None:
    """Resolve lsof even when PATH omits the directory that ships it.

    macOS ships lsof at /usr/sbin/lsof, but /usr/sbin is absent from some
    trimmed PATHs the resolver actually runs under (observed 2026-09-27:
    Claude Code's Bash tool PATH has /usr/bin and /bin but not /usr/sbin).
    shutil.which("lsof") then returns None, subprocess.run(["lsof", ...])
    raises FileNotFoundError, and the caller's except clause silently turns
    that into an empty listener list -- indistinguishable from "nothing is
    listening", so every live, profile-owned browser was misreported as
    endpoint_not_profile_owned.
    """
    found = shutil.which("lsof")
    if found:
        return found
    for candidate in ("/usr/sbin/lsof", "/usr/bin/lsof"):
        if os.path.exists(candidate):
            return candidate
    return None


def _listener_pids(host: str, port: int) -> list[int]:
    binary = _lsof_binary()
    if binary is None:
        return []
    rendered_host = f"[{host}]" if ":" in host else host
    try:
        result = subprocess.run(
            [binary, "-nP", "-a", f"-iTCP@{rendered_host}:{port}",
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


def _profile_receipt_owned(
    profile: str, pids: Iterable[int], port: int, browser_uuid: str,
) -> tuple[int, str] | None:
    """Verify a live listener against the exact profile-hash owner receipt.

    Nested Seatbelt permits lsof but can reject ps, so the command-line proof is
    unavailable inside the paid owner. browser_port_owner writes this receipt
    atomically at mode 0600; callers sandboxed for model work must deny writes
    to its directory.
    """
    state_dir = Path(os.environ.get(
        "LIFE_MANAGER_BROWSER_PORT_STATE_DIR",
        "~/.local/state/life-manager/browser-ports",
    )).expanduser()
    digest = hashlib.sha256(os.path.realpath(profile).encode()).hexdigest()
    receipt = state_dir / f"profile-{digest}.json"
    try:
        info = receipt.lstat()
        if receipt.is_symlink() or not receipt.is_file():
            return None
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            return None
        value = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    root_pid = value.get("listener_pid")
    if root_pid is None and value.get("adopted") is True:
        root_pid = value.get("browser_root_pid")
    supervisor_pid = value.get("supervisor_pid")
    owner = value.get("owner")
    if (
        not isinstance(root_pid, int) or isinstance(root_pid, bool)
        or root_pid not in set(pids)
        or not isinstance(supervisor_pid, int) or isinstance(supervisor_pid, bool)
        or supervisor_pid <= 0
        or value.get("port") != port
        or value.get("profile_name") != Path(profile).name
        or value.get("browser_uuid") != browser_uuid
        or not isinstance(owner, str) or not IDENTITY_RE.fullmatch(owner)
    ):
        return None
    return root_pid, f"browser_port_owner_receipt:{receipt.name}"


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
        ownership_source = "process_command"
        if owner is None:
            owner = _profile_receipt_owned(profile, pids, port, str(live["uuid"]))
            ownership_source = "browser_port_owner_receipt"
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
            "ownership_source": ownership_source,
            "reachable": True,
            "http_status": 200,
            "websocket_url_valid": True,
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
