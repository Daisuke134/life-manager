import importlib.util
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[4]
LOCKER = ROOT / "skills" / "browser" / "scripts" / "run_with_file_lock.py"
ACCOUNT = ROOT / "skills" / "earn" / "crowdworks" / "scripts" / "account.py"


def _account():
    spec = importlib.util.spec_from_file_location("crowdworks_account_health_test", ACCOUNT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + 3
    while not path.exists():
        if time.monotonic() >= deadline:
            raise AssertionError(f"timed out waiting for {path}")
        time.sleep(0.01)


def test_all_browser_lanes_share_one_provider_lock():
    scripts = ROOT / "skills" / "earn" / "crowdworks" / "scripts"
    for owner in ("application-owner", "reply-owner", "paid-owner"):
        source = (scripts / owner).read_text(encoding="utf-8")
        assert "run_with_file_lock.py" in source
        assert '"$STATE_ROOT/provider-browser.lock"' in source


def test_application_owner_exports_its_fallback_state_root_to_dom_evidence():
    script = ROOT / "skills" / "earn" / "crowdworks" / "scripts" / "application-owner"
    source = script.read_text(encoding="utf-8")
    assert 'STATE_ROOT="${LIFE_MANAGER_STATE_ROOT:-$HOME/.local/state/anicca/crowdworks}"' in source
    assert 'export LIFE_MANAGER_STATE_ROOT="$STATE_ROOT"' in source


def test_http_only_is_not_enough_for_browser_ownership(monkeypatch):
    account = _account()
    reaped = []
    launched = []
    listeners = iter([123, 456])
    health = iter([False, True])
    monkeypatch.setattr(account, "_listener", lambda: next(listeners, 456))
    monkeypatch.setattr(account, "_owned_listener", lambda pid, deadline: True)
    monkeypatch.setattr(account, "_cdp_alive", lambda: True)
    monkeypatch.setattr(account, "_playwright_alive", lambda: next(health))
    monkeypatch.setattr(account, "_reap", lambda pid: reaped.append(pid))
    monkeypatch.setattr(account.subprocess, "Popen", lambda *args, **kwargs: launched.append(args[0]))

    assert account._owner() is True
    assert reaped == [123]
    assert len(launched) == 1


def test_playwright_connect_has_a_bounded_timeout():
    assert "connect_over_cdp(CDP_URL,timeout=10_000)" in ACCOUNT.read_text(encoding="utf-8")


def test_lock_survives_exec_until_child_exits(tmp_path):
    lock = tmp_path / "provider.lock"
    first_ready = tmp_path / "first-ready"
    second_ready = tmp_path / "second-ready"
    first = subprocess.Popen([
        sys.executable, str(LOCKER), str(lock), "--", sys.executable, "-c",
        "import pathlib,sys,time; pathlib.Path(sys.argv[1]).touch(); time.sleep(.4)",
        str(first_ready),
    ])
    _wait_for(first_ready)
    second = subprocess.Popen([
        sys.executable, str(LOCKER), str(lock), "--", sys.executable, "-c",
        "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", str(second_ready),
    ])
    time.sleep(0.1)
    assert not second_ready.exists()
    assert first.wait(timeout=3) == 0
    assert second.wait(timeout=3) == 0
    assert second_ready.exists()


def test_sigkill_releases_lock_for_next_process(tmp_path):
    lock = tmp_path / "provider.lock"
    first_ready = tmp_path / "first-ready"
    second_ready = tmp_path / "second-ready"
    first = subprocess.Popen([
        sys.executable, str(LOCKER), str(lock), "--", sys.executable, "-c",
        "import pathlib,sys,time; pathlib.Path(sys.argv[1]).touch(); time.sleep(30)",
        str(first_ready),
    ])
    _wait_for(first_ready)
    second = subprocess.Popen([
        sys.executable, str(LOCKER), str(lock), "--", sys.executable, "-c",
        "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", str(second_ready),
    ])
    time.sleep(0.1)
    assert not second_ready.exists()
    first.kill()
    first.wait(timeout=3)
    assert second.wait(timeout=3) == 0
    assert second_ready.exists()
