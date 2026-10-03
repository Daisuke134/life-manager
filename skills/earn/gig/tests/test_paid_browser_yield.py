import importlib.util
import inspect
import os
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("paid_direct_browser_yield_test", SCRIPTS / "paid_direct.py")
paid = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(paid)


def test_with_browser_exports_reacquirable_outer_lease_contract():
    source = (Path(__file__).parents[3] / "browser" / "with-browser.sh").read_text()
    assert "LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID" in source
    assert "AI_BROWSER_HOLDER_START" in source
    assert "LIFE_MANAGER_BROWSER_LEASE_IDENTITY" in source
    assert "LIFE_MANAGER_BROWSER_GUARD" in source


def test_paid_model_stage_yields_and_reacquires_registered_browser(monkeypatch, tmp_path):
    guard = tmp_path / "browser-guard.sh"
    guard.write_text("#!/bin/sh\n")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="http://127.0.0.1:9223\n", stderr="")

    monkeypatch.setenv("LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID", "12345")
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_LEASE_IDENTITY", "coconala:kosuke")
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_GUARD", str(guard))
    monkeypatch.setattr(paid.subprocess, "run", run)

    with paid._yield_registered_browser_lease():
        assert calls[0][0] == [str(guard), "release", "coconala:kosuke"]
        assert calls[0][1]["env"]["AI_BROWSER_HOLDER_PID"] == "12345"

    assert calls[1][0] == [str(guard), "acquire", "coconala:kosuke"]
    assert calls[1][1]["env"]["AI_BROWSER_HOLDER_PID"] == "12345"


def test_paid_browser_yield_is_noop_without_outer_lease(monkeypatch):
    for key in (
        "LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID",
        "LIFE_MANAGER_BROWSER_LEASE_IDENTITY",
        "LIFE_MANAGER_BROWSER_GUARD",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        paid.subprocess, "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not run guard")),
    )
    with paid._yield_registered_browser_lease():
        pass


def test_remote_owner_and_verifier_model_stages_use_browser_yield():
    source = inspect.getsource(paid._run_remote_repair)
    assert source.count("_yield_registered_browser_lease()") >= 2


def test_browser_guard_release_cannot_remove_another_live_holder(tmp_path):
    guard = Path(__file__).parents[3] / "browser" / "browser-guard.sh"
    lease_dir = tmp_path / "leases"
    lease_dir.mkdir()
    lease = lease_dir / "coconala_kosuke.lease"
    holder_pid = os.getpid()
    holder_start = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(holder_pid)], capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    lease.write_text(json.dumps({
        "identity": "coconala:kosuke", "pid": holder_pid, "host": "host",
        "port": 9223, "uuid": "browser", "acquired_at": 1,
        "holder_start": holder_start,
    }) + "\n")
    environment = {**os.environ, "AI_BROWSER_LEASE_DIR": str(lease_dir),
                   "AI_BROWSER_HOLDER_PID": str(holder_pid),
                   "AI_BROWSER_HOLDER_START": "wrong-start"}

    refused = subprocess.run(
        ["bash", str(guard), "release", "coconala:kosuke"], env=environment,
        capture_output=True, text=True, check=False,
    )
    assert refused.returncode != 0
    assert lease.is_file()

    environment["AI_BROWSER_HOLDER_START"] = holder_start
    released = subprocess.run(
        ["bash", str(guard), "release", "coconala:kosuke"], env=environment,
        capture_output=True, text=True, check=False,
    )
    assert released.returncode == 0
    assert not lease.exists()


def test_browser_guard_beat_atomically_preserves_process_identity(tmp_path):
    guard = Path(__file__).parents[3] / "browser" / "browser-guard.sh"
    lease_dir = tmp_path / "leases"
    lease_dir.mkdir()
    lease = lease_dir / "coconala_kosuke.lease"
    original = {
        "identity": "coconala:kosuke", "pid": os.getpid(), "host": "host",
        "port": 9223, "uuid": "browser", "holder_start": "fixed-start",
        "acquired_at": 1,
    }
    lease.write_text(json.dumps(original) + "\n")

    completed = subprocess.run(
        ["bash", str(guard), "beat", "coconala:kosuke"],
        env={**os.environ, "AI_BROWSER_LEASE_DIR": str(lease_dir)},
        capture_output=True, text=True, check=False,
    )

    assert completed.returncode == 0
    updated = json.loads(lease.read_text())
    assert updated["holder_start"] == "fixed-start"
    assert updated["pid"] == os.getpid()
    assert updated["acquired_at"] > 1
