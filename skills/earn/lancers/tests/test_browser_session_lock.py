from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "application_tick.py"


def _load():
    spec = importlib.util.spec_from_file_location("lancers_browser_session_lock", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_browser_session_lock_rejects_a_second_client_until_the_first_releases(tmp_path):
    module = _load()
    module.BROWSER_SESSION_LOCK_PATH = tmp_path / "browser-session.lock"

    first = module._acquire_browser_session_lock(timeout_seconds=0.01)
    try:
        with pytest.raises(module.BrowserSessionBusy):
            module._acquire_browser_session_lock(timeout_seconds=0.01)
    finally:
        first.release()

    second = module._acquire_browser_session_lock(timeout_seconds=0.01)
    second.release()


def test_page_close_releases_the_browser_session_lease(tmp_path):
    module = _load()
    module.BROWSER_SESSION_LOCK_PATH = tmp_path / "browser-session.lock"
    runtime = type("Runtime", (), {})()
    lease = module._acquire_browser_session_lock(timeout_seconds=0.01)
    module._attach_browser_session_lease(runtime, lease)

    class Page:
        context = type("Context", (), {"browser": type("Browser", (), {
            "_anicca_playwright_runtime": runtime,
        })()})()

        def close(self):
            return None

    assert module._close_owned_page(Page()) is True
    module._stop_playwright_runtime(runtime)
    released = module._acquire_browser_session_lock(timeout_seconds=0.01)
    released.release()
