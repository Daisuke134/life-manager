"""2026-10-16: a lease for interactive:dais written without holder_start, whose pid is the
always-alive Codex app-server daemon ($PPID of the real caller), stayed BUSY forever and blocked
the Writer X readback/publish. A legacy lease past the stale window is now treated as stale;
current-format leases keep the live-pid rule."""
import json
import os
import subprocess
import time
from pathlib import Path

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
    env = dict(os.environ, AI_BROWSER_REGISTRY=str(registry), AI_BROWSER_LEASE_DIR=str(leases),
               AI_BROWSER_ENDPOINT_RESOLVER=str(resolver), AI_BROWSER_STALE_SECONDS="60")
    return leases / "test_dais.lease", env


def _acquire(env):
    return subprocess.run(["bash", str(GUARD), "acquire", "test:dais"], env=env,
                          capture_output=True, text=True)


def test_legacy_lease_held_by_live_daemon_past_stale_window_is_reclaimed(tmp_path):
    lease, env = _setup(tmp_path)
    lease.write_text(json.dumps({"identity": "test:dais", "pid": os.getpid(), "host": os.uname().nodename.split(".")[0],
                                 "port": 1, "uuid": "u1", "acquired_at": int(time.time()) - 3600}) + "\n")
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
