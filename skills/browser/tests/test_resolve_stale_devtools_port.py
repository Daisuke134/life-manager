"""2026-10-11: the Capafy browser restarted on its declared port but DevToolsActivePort still named the
previous dynamic port; the resolver trusted the dead file port, reported endpoint_unavailable, and every
CP1 agent stopped with 'browser lease never completed'."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "resolve_cdp_endpoint.py"
SPEC = importlib.util.spec_from_file_location("resolve_cdp_endpoint_stale", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_resolver_falls_back_to_declared_port_when_devtools_active_port_is_stale(tmp_path):
    profile = tmp_path / "capafy"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text("54514\n/devtools/browser/stale\n", encoding="utf-8")
    registry = MODULE.parse_registry(f'''
[[identity]]
id = "capafy:kosuke"
profile = "{profile}"
declared_port = 9229
''')

    def fetch(url):
        return {"uuid": "capafy-uuid"} if url == "http://127.0.0.1:9229" else None

    def listeners(host, port):
        return [4242] if (host, port) == ("127.0.0.1", 9229) else []

    def command(pid):
        return f"Chromium --user-data-dir={MODULE.os.path.realpath(str(profile))} --remote-debugging-port=9229"

    result = MODULE.resolve_identity("capafy:kosuke", registry, fetch=fetch,
                                    listeners=listeners, command=command)
    assert result["endpoint"] == "http://127.0.0.1:9229"
    assert result["pid"] == 4242


def test_live_file_port_still_wins_over_declared_port(tmp_path):
    profile = tmp_path / "capafy"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text("54514\n/devtools/browser/live\n", encoding="utf-8")
    registry = MODULE.parse_registry(f'''
[[identity]]
id = "capafy:kosuke"
profile = "{profile}"
declared_port = 9229
''')
    real = MODULE.os.path.realpath(str(profile))
    result = MODULE.resolve_identity(
        "capafy:kosuke", registry,
        fetch=lambda url: {"uuid": "u"} if url.endswith(":54514") and "127.0.0.1" in url else None,
        listeners=lambda host, port: [7] if (host, port) == ("127.0.0.1", 54514) else [],
        command=lambda pid: f"Chromium --user-data-dir={real}")
    assert result["port"] == 54514
