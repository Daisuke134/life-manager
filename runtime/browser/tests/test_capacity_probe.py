import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]


def _probe_module():
    assert importlib.util.find_spec("runtime.browser.capacity_probe") is not None
    from runtime.browser.capacity_probe import run_probe
    return run_probe


def _fake_browser(path: Path, *, serve: bool, linger_child: bool = False) -> None:
    script = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
profile = pathlib.Path(next(a.split('=', 1)[1] for a in sys.argv if a.startswith('--user-data-dir=')))
pathlib.Path(os.environ['PROBE_FAKE_ARGS_FILE']).write_text(json.dumps({'pid': os.getpid(), 'args': sys.argv[1:]}))
if LINGER:
    child = subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])
    pathlib.Path(os.environ['PROBE_FAKE_CHILD_FILE']).write_text(str(child.pid))
if not SERVE:
    while True: time.sleep(1)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/json/version':
            self.send_error(404); return
        body = b'{"Browser":"Chromium/145"}'
        self.send_response(200); self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
profile.mkdir(parents=True, exist_ok=True)
(profile / 'DevToolsActivePort').write_text(str(server.server_port) + '\\n/devtools/browser/probe\\n')
server.serve_forever()
'''.replace("SERVE", "True" if serve else "False").replace(
        "LINGER", "True" if linger_child else "False")
    path.write_text(script)
    path.chmod(0o700)


def test_browser_capacity_probe_uses_own_profile_and_reaps_process(tmp_path):
    run_probe = _probe_module()
    browser = tmp_path / "fake-browser"
    _fake_browser(browser, serve=True)
    state = tmp_path / "state"
    args_file = tmp_path / "args.json"
    with patch.dict(os.environ, {"PROBE_FAKE_ARGS_FILE": str(args_file)}):
        result = run_probe(browser, state, timeout_seconds=3)
    observed = json.loads(args_file.read_text())
    assert result["ok"] is True
    assert "--remote-debugging-port=0" in observed["args"]
    assert "--no-startup-window" in observed["args"]
    assert not list(state.glob("browser-probe-*"))
    try:
        os.kill(observed["pid"], 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError("probe browser process survived terminal")


def test_browser_capacity_probe_timeout_cleans_own_profile(tmp_path):
    run_probe = _probe_module()
    browser = tmp_path / "fake-browser"
    _fake_browser(browser, serve=False)
    state = tmp_path / "state"
    args_file = tmp_path / "args.json"
    with patch.dict(os.environ, {"PROBE_FAKE_ARGS_FILE": str(args_file)}):
        result = run_probe(browser, state, timeout_seconds=3)
    observed = json.loads(args_file.read_text())
    assert result["ok"] is False
    assert result["reason"] == "cdp_unavailable"
    assert not list(state.glob("browser-probe-*"))
    try:
        os.kill(observed["pid"], 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError("timed out browser process survived terminal")


def _running(pid: int) -> bool:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "stat="],
                            capture_output=True, text=True)
    return result.returncode == 0 and bool(result.stdout.strip()) and not result.stdout.lstrip().startswith("Z")


def test_browser_capacity_probe_cancellation_reaps_separate_browser_group(tmp_path):
    _probe_module()
    browser = tmp_path / "fake-browser"
    _fake_browser(browser, serve=False)
    state = tmp_path / "state"
    args_file = tmp_path / "args.json"
    code = ("from pathlib import Path; from runtime.browser.capacity_probe import run_probe; "
            "run_probe(Path(__import__('sys').argv[1]), Path(__import__('sys').argv[2]), timeout_seconds=20)")
    with patch.dict(os.environ, {"PROBE_FAKE_ARGS_FILE": str(args_file)}):
        process = subprocess.Popen([sys.executable, "-c", code, str(browser), str(state)],
                                   cwd=ROOT, start_new_session=True)
    browser_pid = None
    try:
        deadline = time.monotonic() + 5
        while not args_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert args_file.exists()
        browser_pid = json.loads(args_file.read_text())["pid"]
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
        deadline = time.monotonic() + 3
        while _running(browser_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _running(browser_pid)
        assert not list(state.glob("browser-probe-*"))
    finally:
        if browser_pid is not None and _running(browser_pid):
            os.killpg(browser_pid, signal.SIGKILL)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def test_browser_capacity_probe_reaps_stubborn_child_after_parent_exit(tmp_path):
    run_probe = _probe_module()
    browser = tmp_path / "fake-browser"
    _fake_browser(browser, serve=True, linger_child=True)
    state = tmp_path / "state"
    args_file = tmp_path / "args.json"
    child_file = tmp_path / "child.pid"
    child_pid = None
    try:
        with patch.dict(os.environ, {
            "PROBE_FAKE_ARGS_FILE": str(args_file),
            "PROBE_FAKE_CHILD_FILE": str(child_file),
        }):
            result = run_probe(browser, state, timeout_seconds=3)
        assert result["ok"] is True
        child_pid = int(child_file.read_text())
        deadline = time.monotonic() + 3
        while _running(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _running(child_pid)
        assert not list(state.glob("browser-probe-*"))
    finally:
        if child_pid is not None and _running(child_pid):
            os.kill(child_pid, signal.SIGKILL)


def test_browser_capacity_probe_has_owned_registry_row():
    loops = json.loads((ROOT / "config/loop-registry.json").read_text())["loops"]
    row = loops["life-manager-browser-capacity-probe"]
    assert row["resource_class"] == "browser"
    assert row["effect_class"] == "none"
    assert row["provider_route"] == "deterministic"
    assert row["entrypoint"] == "runtime/browser/capacity_probe.py"
    assert row["state_root"] != loops["life-manager-connector-native"]["state_root"]
