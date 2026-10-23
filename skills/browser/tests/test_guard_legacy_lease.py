"""2026-10-16: a lease for interactive:dais written without holder_start, whose pid is the
always-alive Codex app-server daemon ($PPID of the real caller), stayed BUSY forever and blocked
the Writer X readback/publish. A legacy lease past the stale window is now treated as stale;
current-format leases keep the live-pid rule."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / "browser-guard.sh"


def _setup(tmp: Path):
    registry = tmp / "browsers.toml"
    registry.write_text('[[identity]]\nid = "test:dais"\nprofile = "/tmp/x"\nowner = "t"\ndeclared_port = 1\n')
    resolver = tmp / "resolver.py"
    resolver.write_text(
        "import json,sys\n"
        "print(json.dumps({'identities': []}) if '--all' in sys.argv else "
        "json.dumps({'endpoint': 'http://127.0.0.1:1', 'port': 1, 'uuid': 'u1'}))\n")
    leases = tmp / "leases"
    leases.mkdir()
    env = dict(os.environ, HOME=str(tmp), PY=sys.executable,
               AI_BROWSER_REGISTRY=str(registry), AI_BROWSER_LEASE_DIR=str(leases),
               AI_BROWSER_ENDPOINT_RESOLVER=str(resolver), AI_BROWSER_STALE_SECONDS="60")
    return leases / "test_dais.lease", env


def _acquire(env):
    return subprocess.run(["bash", str(GUARD), "acquire", "test:dais"], env=env,
                          capture_output=True, text=True)


def _ps_start_time(tmp: Path, env, pid: int, started_at: int):
    ps = tmp / "ps"
    started = time.strftime("%a %b %d %H:%M:%S %Y", time.localtime(started_at))
    ps.write_text(f"#!{sys.executable}\nimport sys\n"
                  f"assert sys.argv[1:] == ['-o', 'lstart=', '-p', {str(pid)!r}]\n"
                  f"print({started!r})\n")
    ps.chmod(0o700)
    env.update(PATH=f"{tmp}{os.pathsep}{env['PATH']}", AI_BROWSER_HOLDER_START="fixture-caller-start")


def test_legacy_lease_held_by_live_daemon_past_stale_window_is_reclaimed(tmp_path):
    lease, env = _setup(tmp_path)
    acquired_at = int(time.time()) - 120
    _ps_start_time(tmp_path, env, 1, acquired_at - 120)
    lease.write_text(json.dumps({"identity": "test:dais", "pid": 1, "host": os.uname().nodename.split(".")[0],
                                 "port": 1, "uuid": "u1", "acquired_at": acquired_at}) + "\n")
    result = _acquire(env)
    assert result.returncode == 0, result.stderr
    assert "holder_start" in json.loads(lease.read_text().strip().splitlines()[-1])


def test_current_format_lease_with_live_holder_stays_busy(tmp_path):
    lease, env = _setup(tmp_path)
    start = subprocess.run(["ps", "-o", "lstart=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip()
    lease.write_text(json.dumps({"identity": "test:dais", "pid": os.getpid(), "host": os.uname().nodename.split(".")[0],
                                 "port": 1, "uuid": "u1", "holder_start": " ".join(start.split()),
                                 "acquired_at": int(time.time()) - 3600}) + "\n")
    assert _acquire(env).returncode == 9


def test_legacy_lease_whose_holder_started_just_before_acquiring_stays_busy(tmp_path):
    # ~/.config/ai/bin/with-browser.sh writes legacy leases with its own shell pid and never
    # beats; a long job there must not be robbed after 30 minutes.
    lease, env = _setup(tmp_path)
    acquired_at = int(time.time()) - 120
    _ps_start_time(tmp_path, env, os.getpid(), acquired_at - 1)
    original = json.dumps({"identity": "test:dais", "pid": os.getpid(),
                           "host": os.uname().nodename.split(".")[0], "port": 1, "uuid": "u1",
                           "acquired_at": acquired_at}) + "\n"
    lease.write_text(original)
    assert _acquire(env).returncode == 9
    assert lease.read_text() == original


@pytest.mark.parametrize("matching_holder", [True, False], ids=["authorized", "wrong-holder"])
def test_release_preserves_tabs_and_checks_lease_holder(tmp_path, matching_holder):
    lease, env = _setup(tmp_path)
    owner_pid, owner_start = os.getpid(), "fixture-holder-start"
    original = json.dumps({"identity": "test:dais", "pid": owner_pid,
                           "holder_start": owner_start, "port": 1}) + "\n"
    lease.write_text(original)
    tab_calls = tmp_path / "tab-calls.json"
    python_spy = tmp_path / "python-spy"
    python_spy.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "if len(sys.argv) > 1 and pathlib.Path(sys.argv[1]).name == 'sweep_tabs.py':\n"
        f"    pathlib.Path({str(tab_calls)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        "    raise SystemExit(0)\n"
        "assert sys.argv[1] in ('-', '-c'), 'unexpected browser helper'\n"
        f"os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n"
    )
    python_spy.chmod(0o700)
    env.update(PY=str(python_spy), AI_BROWSER_HOLDER_START=owner_start,
               AI_BROWSER_HOLDER_PID=str(owner_pid if matching_holder else owner_pid + 1))

    result = subprocess.run(["bash", str(GUARD), "release", "test:dais"],
                            env=env, capture_output=True, text=True, timeout=10)

    assert result.returncode == (0 if matching_holder else 9), result.stderr
    assert lease.exists() is not matching_holder
    if not matching_holder:
        assert lease.read_text() == original
    assert not tab_calls.exists(), tab_calls.read_text()
