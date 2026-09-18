from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/earn/lancers/scripts/application_tick.py"


def _load():
    spec = importlib.util.spec_from_file_location("lancers_application_tick_bounded_lock", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_live_tick_defers_when_shared_browser_lock_is_busy(tmp_path, monkeypatch):
    module = _load()
    observed = {}

    @contextmanager
    def busy_lock(path, timeout_seconds=None):
        observed["path"] = Path(path)
        observed["timeout_seconds"] = timeout_seconds
        raise module.shared._AccountLockBusy()
        yield

    monkeypatch.setattr(module, "account_lock", busy_lock)
    browser_called = False

    def browser_factory(_url):
        nonlocal browser_called
        browser_called = True
        raise AssertionError("browser must not open while the shared lock is busy")

    result = module.run_live_tick(
        project_id="5603557",
        proposal_text="x" * 200,
        proposed_amount_minor=200000,
        delivery_due_on="2026-09-20",
        state_path=tmp_path / "application.json",
        browser_factory=browser_factory,
    )

    assert result.error == "account_lock_busy"
    assert observed["path"].name == "work-sync.json"
    assert observed["timeout_seconds"] == module.SHARED_BROWSER_LOCK_TIMEOUT_SECONDS
    assert browser_called is False
