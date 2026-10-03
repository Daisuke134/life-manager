import importlib.util
import hashlib
import json
import socket
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "resolve_cdp_endpoint.py"
SPEC = importlib.util.spec_from_file_location("resolve_cdp_endpoint", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


REGISTRY = MODULE.parse_registry('''
[[identity]]
id = "interactive:dais"
profile = "/tmp/daily-driver"
declared_port = 9222

[[identity]]
id = "gig:kosuke"
profile = "/tmp/gig"
declared_port = 9223
''')


def test_resolver_rejects_reachable_proxy_when_profile_process_does_not_own_endpoint():
    calls = []

    def fetch(url):
        calls.append(("fetch", url))
        return {"uuid": "proxy-uuid"}

    def listeners(host, port):
        calls.append(("listeners", host, port))
        return [11] if host == "127.0.0.1" else []

    def command(pid):
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    with pytest.raises(ValueError, match="endpoint_not_profile_owned"):
        MODULE.resolve_identity("interactive:dais", REGISTRY, fetch=fetch,
                                listeners=listeners, command=command)
    assert calls[:2] == [("fetch", "http://127.0.0.1:9222"),
                         ("listeners", "127.0.0.1", 9222)]


def test_resolver_selects_ipv6_endpoint_when_profile_process_owns_it():
    def fetch(url):
        return {"uuid": "daily-uuid"} if "[::1]" in url else None

    def listeners(host, port):
        return [1592] if host == "::1" else []

    def command(pid):
        return f"Chromium --user-data-dir={MODULE.os.path.realpath('/tmp/daily-driver')} --remote-debugging-port=9222"

    result = MODULE.resolve_identity("interactive:dais", REGISTRY, fetch=fetch,
                                    listeners=listeners, command=command)
    assert result["endpoint"] == "http://[::1]:9222"
    assert result["uuid"] == "daily-uuid"
    assert result["pid"] == 1592
    assert result["reachable"] is True
    assert result["http_status"] == 200
    assert result["websocket_url_valid"] is True


def test_resolve_all_keeps_unreachable_identities_observable():
    def fetch(url):
        return {"uuid": "daily-uuid"} if "[::1]" in url else None

    def listeners(host, port):
        return [1592] if host == "::1" else []

    def command(pid):
        return f"Chromium --user-data-dir={MODULE.os.path.realpath('/tmp/daily-driver')}"

    rows = MODULE.resolve_all(REGISTRY, fetch=fetch, listeners=listeners, command=command)
    assert rows[0]["identity"] == "gig:kosuke"
    assert rows[0]["reachable"] is False
    assert rows[1]["endpoint"] == "http://[::1]:9222"


def test_resolve_all_exposes_duplicate_browser_uuid_for_guard_to_fail_closed():
    registry = {
        "first:browser": {"profile": "/tmp/first", "declared_port": 9222},
        "second:browser": {"profile": "/tmp/second", "declared_port": 9223},
    }

    def fetch(url):
        return {"uuid": "same-browser"} if "[::1]" in url else None

    def listeners(host, port):
        return [port] if host == "::1" else []

    def command(pid):
        return f"Chromium --user-data-dir={MODULE.os.path.realpath('/tmp/' + ('first' if pid == 9222 else 'second'))}"

    rows = MODULE.resolve_all(registry, fetch=fetch, listeners=listeners, command=command)
    assert [row["uuid"] for row in rows] == ["same-browser", "same-browser"]


def test_listener_pids_finds_lsof_even_when_path_omits_usr_sbin(monkeypatch):
    """Regression for the 2026-09-27 outage: every registered identity showed
    reachable:false with error_class endpoint_not_profile_owned even though the
    daily-driver Chromium was alive. Root cause: resolve_identity's default
    _listener_pids() shells out to bare "lsof", and macOS ships that binary at
    /usr/sbin/lsof -- a directory absent from the trimmed PATH this resolver
    actually runs under (Claude Code's Bash tool and some launchd contexts).
    subprocess.run(["lsof", ...]) raised FileNotFoundError, was swallowed by the
    existing `except (OSError, subprocess.SubprocessError): return []`, and every
    live browser was then reported as not-profile-owned. The fix must locate lsof
    by absolute path when PATH lookup fails.
    """
    monkeypatch.setenv("PATH", "/nonexistent-bin-only")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        port = server.getsockname()[1]
        pids = MODULE._listener_pids("127.0.0.1", port)
    finally:
        server.close()
    assert pids, "expected lsof (found via absolute fallback path) to report the bound listener"


def test_resolver_uses_exact_profile_receipt_when_sandbox_blocks_process_command(
    tmp_path, monkeypatch
):
    profile = tmp_path / "tiktok-profile"
    profile.mkdir()
    state = tmp_path / "browser-ports"
    state.mkdir()
    digest = hashlib.sha256(str(profile.resolve()).encode()).hexdigest()
    receipt = state / f"profile-{digest}.json"
    receipt.write_text(json.dumps({
        "owner": "tiktok-browser",
        "supervisor_pid": 41,
        "browser_root_pid": 42,
        "listener_pid": 42,
        "browser_uuid": "tiktok-browser",
        "port": 9230,
        "profile_name": profile.name,
    }))
    receipt.chmod(0o600)
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_PORT_STATE_DIR", str(state))
    registry = {"tiktok": {"profile": str(profile), "declared_port": 9230}}

    result = MODULE.resolve_identity(
        "tiktok", registry,
        fetch=lambda _url: {"uuid": "tiktok-browser"},
        listeners=lambda host, _port: [42] if host == "127.0.0.1" else [],
        command=lambda _pid: "",
    )

    assert result["pid"] == 42
    assert result["ownership_source"] == "browser_port_owner_receipt"


def test_resolver_rejects_profile_receipt_for_a_different_listener(tmp_path, monkeypatch):
    profile = tmp_path / "tiktok-profile"
    profile.mkdir()
    state = tmp_path / "browser-ports"
    state.mkdir()
    digest = hashlib.sha256(str(profile.resolve()).encode()).hexdigest()
    receipt = state / f"profile-{digest}.json"
    receipt.write_text(json.dumps({
        "owner": "tiktok-browser",
        "supervisor_pid": 41,
        "browser_root_pid": 99,
        "listener_pid": 99,
        "browser_uuid": "tiktok-browser",
        "port": 9230,
        "profile_name": profile.name,
    }))
    receipt.chmod(0o600)
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_PORT_STATE_DIR", str(state))
    registry = {"tiktok": {"profile": str(profile), "declared_port": 9230}}

    with pytest.raises(ValueError, match="endpoint_not_profile_owned"):
        MODULE.resolve_identity(
            "tiktok", registry,
            fetch=lambda _url: {"uuid": "tiktok-browser"},
            listeners=lambda host, _port: [42] if host == "127.0.0.1" else [],
            command=lambda _pid: "",
        )


def test_resolver_rejects_stale_receipt_from_prior_browser_generation(
    tmp_path, monkeypatch
):
    profile = tmp_path / "tiktok-profile"
    profile.mkdir()
    state = tmp_path / "browser-ports"
    state.mkdir()
    digest = hashlib.sha256(str(profile.resolve()).encode()).hexdigest()
    receipt = state / f"profile-{digest}.json"
    receipt.write_text(json.dumps({
        "owner": "tiktok-browser",
        "supervisor_pid": 41,
        "browser_root_pid": 42,
        "listener_pid": 42,
        "browser_uuid": "old-browser-generation",
        "port": 9230,
        "profile_name": profile.name,
    }))
    receipt.chmod(0o600)
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_PORT_STATE_DIR", str(state))
    registry = {"tiktok": {"profile": str(profile), "declared_port": 9230}}

    with pytest.raises(ValueError, match="endpoint_not_profile_owned"):
        MODULE.resolve_identity(
            "tiktok", registry,
            fetch=lambda _url: {"uuid": "new-browser-generation"},
            listeners=lambda host, _port: [42] if host == "127.0.0.1" else [],
            command=lambda _pid: "",
        )
