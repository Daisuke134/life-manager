import contextlib
import http.server
import json
import os
import subprocess
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENSURE = ROOT / "skills/browser/ensure_browser.sh"
GUARD = ROOT / "skills/earn/gig/scripts/cdp_daily_driver_guard.sh"


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 200
    payload = b""

    def do_GET(self):
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *_args):
        pass


@contextlib.contextmanager
def _server(status, payload=b""):
    handler = type("FixtureHandler", (_Handler,), {"status": status, "payload": payload})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        worker.join(timeout=2)
        server.server_close()


def _failing_resolver(tmp_path):
    resolver = tmp_path / "resolver-python"
    resolver.write_text(
        "#!/bin/sh\nprintf '%s\\n' '{\"ok\":false,\"reason\":\"cdp_port_owner_mismatch\"}' >&2\nexit 75\n",
        encoding="utf-8",
    )
    resolver.chmod(0o700)
    return resolver


def _environment(tmp_path, port):
    return {
        **os.environ,
        "HOME": str(tmp_path),
        "LIFE_MANAGER_HOME": str(tmp_path / "state"),
        "CLOAK_CDP_BASE_URL": f"http://127.0.0.1:{port}",
        "CDP_DAILY_DRIVER_PORT": str(port),
        "CLOAK_BROWSER_RUNTIME_OWNER": "life-manager-daily-driver",
        "BROWSER_PORT_OWNER_PYTHON": str(_failing_resolver(tmp_path)),
        "BROWSER_PORT_OWNER_BIN": str(ROOT / "runtime/host/browser_port_owner.py"),
    }


def test_ensure_browser_does_not_report_alive_for_an_http_404(tmp_path):
    with _server(404) as port:
        result = subprocess.run(
            ["/bin/bash", str(ENSURE)],
            env={**_environment(tmp_path, port), "CLOAK_BROWSER_LAUNCHD_LABEL": "invalid/value"},
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    assert result.returncode != 0
    assert result.stdout.strip() != "ALIVE"


def test_daily_driver_probe_rejects_well_formed_cdp_from_the_wrong_owner(tmp_path):
    payload = json.dumps({
        "Browser": "Chrome/145.0.0.0",
        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/wrong-owner",
    }).encode("utf-8")
    with _server(200, payload) as port:
        result = subprocess.run(
            ["/bin/bash", "-c", f"source {GUARD!s}; _cdp_guard_probe 1"],
            env=_environment(tmp_path, port),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    assert result.returncode != 0


def test_ensure_browser_owner_mismatch_never_enters_legacy_recovery(tmp_path):
    guard_log = tmp_path / "guard.log"
    with _server(200, b"{}") as port:
        result = subprocess.run(
            ["/bin/bash", str(ENSURE)],
            env={
                **_environment(tmp_path, port),
                "CDP_GUARD_LOG": str(guard_log),
                "CDP_GUARD_LOCK": str(tmp_path / "guard.lock"),
                "CDP_DAILY_DRIVER_PROFILE": str(tmp_path / "profile"),
            },
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    assert result.returncode != 0
    assert result.stdout.strip() == "FAILED"
    assert not guard_log.exists()


def test_daily_driver_registered_owner_mismatch_never_kills_or_relaunches(tmp_path):
    guard_log = tmp_path / "guard.log"
    result = subprocess.run(
        ["/bin/bash", "-c", f"source {GUARD!s}; cdp_guard_ensure_healthy 1 1"],
        env={
            **_environment(tmp_path, 9222),
            "CDP_GUARD_LOG": str(guard_log),
            "CDP_GUARD_LOCK": str(tmp_path / "guard.lock"),
            "CDP_DAILY_DRIVER_PROFILE": str(tmp_path / "profile"),
        },
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode != 0
    assert not guard_log.exists()
