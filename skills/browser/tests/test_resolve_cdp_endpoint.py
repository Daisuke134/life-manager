import importlib.util
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
