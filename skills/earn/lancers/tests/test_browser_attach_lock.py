from __future__ import annotations

import importlib.util
import sys
import threading
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "skills/earn/lancers/scripts/application_tick.py"


def _module():
    spec = importlib.util.spec_from_file_location(
        "lancers_application_tick_attach_lock_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_browser(page="page"):
    class _Context:
        def new_page(self):
            return page

    class _Browser:
        contexts = (_Context(),)

        def close(self):
            pass

    return _Browser()


def test_normal_attach_returns_browser_and_page_and_releases_lock(tmp_path):
    module = _module()
    lock_path = tmp_path / "browser-attach-9227"
    browser, page = module._open_owned_page(
        lambda _url: _fake_browser("p1"), lock_path=lock_path, lock_timeout_seconds=5
    )
    assert page == "p1"
    assert browser is not None
    # A lock released after a normal attach must be immediately re-acquirable.
    browser2, page2 = module._open_owned_page(
        lambda _url: _fake_browser("p2"), lock_path=lock_path, lock_timeout_seconds=5
    )
    assert page2 == "p2"


def test_concurrent_attaches_are_serialized_not_raced(tmp_path):
    """Two concurrent attach attempts never overlap; the second waits then succeeds."""
    module = _module()
    lock_path = tmp_path / "browser-attach-9227"
    active = {"count": 0, "max_seen": 0}
    active_lock = threading.Lock()
    finished = []

    def slow_factory(_url):
        with active_lock:
            active["count"] += 1
            active["max_seen"] = max(active["max_seen"], active["count"])
        time.sleep(0.2)
        with active_lock:
            active["count"] -= 1
        finished.append(time.monotonic())
        return _fake_browser()

    results = {}

    def worker(name):
        results[name] = module._open_owned_page(
            slow_factory, lock_path=lock_path, lock_timeout_seconds=5
        )

    threads = [
        threading.Thread(target=worker, args=("a",)),
        threading.Thread(target=worker, args=("b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    # Never more than one factory call in flight at a time -- proves the lock
    # actually serializes the attach, not just that both eventually finished.
    assert active["max_seen"] == 1
    assert len(finished) == 2
    assert set(results) == {"a", "b"}
    for _, page in results.values():
        assert page == "page"


def test_lock_timeout_raises_typed_transient_error(tmp_path):
    module = _module()
    lock_path = tmp_path / "browser-attach-9227"
    held = threading.Event()
    release = threading.Event()

    def holder():
        with module.shared.account_lock(lock_path, timeout_seconds=5):
            held.set()
            release.wait(timeout=5)

    thread = threading.Thread(target=holder)
    thread.start()
    assert held.wait(timeout=5)
    try:
        started = time.monotonic()
        try:
            module._open_owned_page(
                lambda _url: _fake_browser(),
                lock_path=lock_path,
                lock_timeout_seconds=0.2,
            )
            raise AssertionError("expected BrowserAttachBusy")
        except module.BrowserAttachBusy:
            elapsed = time.monotonic() - started
            assert elapsed < 2
    finally:
        release.set()
        thread.join(timeout=5)


def test_lock_is_released_when_factory_raises(tmp_path):
    module = _module()
    lock_path = tmp_path / "browser-attach-9227"

    def failing_factory(_url):
        raise RuntimeError("connect_over_cdp:websocket")

    try:
        module._open_owned_page(
            failing_factory, lock_path=lock_path, lock_timeout_seconds=2
        )
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass

    # A prior failed attempt must not leave the lock held for the next tick.
    browser, page = module._open_owned_page(
        lambda _url: _fake_browser("after-failure"),
        lock_path=lock_path,
        lock_timeout_seconds=2,
    )
    assert page == "after-failure"
