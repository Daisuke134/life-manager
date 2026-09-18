from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "skills/earn/lancers/scripts/application_tick.py"


def _module():
    spec = importlib.util.spec_from_file_location("lancers_application_tick_cleanup_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cleanup_closes_only_stale_auth_targets(monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "_cdp_inventory",
        lambda _url: [
            ("job", "https://www.lancers.jp/work/detail/5599830"),
            ("dashboard", "https://www.lancers.jp/mypage"),
            ("login", "https://www.lancers.jp/user/login"),
            ("google", "https://accounts.google.com/info/sessionexpired"),
        ],
    )
    closed = []
    monkeypatch.setattr(module, "_cdp_request", lambda url, limit=None: closed.append(url) or True)

    assert module._cleanup_stale_targets(module.CDP_URL) is True
    assert closed == [
        f"{module.CDP_URL}/json/close/login",
        f"{module.CDP_URL}/json/close/google",
    ]


def test_cleanup_skips_unavailable_cdp_inventory(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "_cdp_inventory", lambda _url: None)
    assert module._cleanup_stale_targets(module.CDP_URL) is False


def test_browser_attach_diagnostic_redacts_endpoint():
    module = _module()
    detail = module._safe_browser_failure(RuntimeError(
        "BrowserType.connect_over_cdp: ws://127.0.0.1:9227/devtools/browser/secret-token failed\nprivate call log"
    ))
    assert detail == "RuntimeError:websocket"
    assert "secret-token" not in detail and "private call log" not in detail
    assert module._safe_browser_failure(RuntimeError(
        "Authorization: Bearer another-secret Cookie: session=private"
    )) == "RuntimeError:other"


def test_browser_attach_diagnostic_cannot_block_cleanup(monkeypatch):
    module = _module()

    class BrokenStderr:
        def write(self, _text):
            raise OSError("log unavailable")

    monkeypatch.setattr(module.sys, "stderr", BrokenStderr())
    module._log_browser_failure("attempt1", RuntimeError("secret"))


def test_cdp_timeout_retries_once_without_stale_auth_tabs(monkeypatch):
    from playwright import sync_api

    module = _module()
    attempts = []
    stopped = []

    class Browser:
        pass

    class Runtime:
        chromium = None

        def __init__(self):
            self.chromium = self

        def connect_over_cdp(self, url, timeout):
            attempts.append((url, timeout))
            if len(attempts) == 1:
                raise sync_api.TimeoutError("transient timeout")
            return Browser()

        def stop(self):
            stopped.append(True)

    class Manager:
        def start(self):
            return Runtime()

    monkeypatch.setattr(sync_api, "sync_playwright", lambda: Manager())
    monkeypatch.setattr(module, "_cdp_inventory", lambda _url: None)

    browser = module._default_browser_factory()

    assert len(attempts) == 2
    assert attempts[0] == attempts[1] == (module.CDP_URL, module.BROWSER_ATTACH_TIMEOUT_MS)
    assert stopped == [True]
    assert browser._anicca_playwright_runtime is not None


def test_open_owned_page_closes_failed_browser_before_retry(monkeypatch):
    module = _module()
    closed = []
    attempts = []

    class BrokenBrowser:
        contexts = [type("BrokenContext", (), {"new_page": lambda _self: (_ for _ in ()).throw(RuntimeError("page create failed"))})()]

        def close(self):
            closed.append("broken")

    class HealthyBrowser:
        contexts = [type("HealthyContext", (), {"new_page": lambda _self: "page"})()]

        def close(self):
            closed.append("healthy")

    browsers = [BrokenBrowser(), HealthyBrowser()]

    def factory(url):
        attempts.append(url)
        return browsers.pop(0)

    browser, page = module._open_owned_page(factory)

    assert page == "page"
    assert isinstance(browser, HealthyBrowser)
    assert attempts == [module.CDP_URL, module.CDP_URL]
    assert closed == ["broken"]


def test_confirmation_transition_detail_records_safe_dom_shape():
    module = _module()

    class Page:
        url = "https://www.lancers.jp/work/propose_start/123?proposeReferer=detail"

        def evaluate(self, script):
            assert "document.readyState" in script
            return {
                "ready_state": "complete",
                "proposal_form": True,
                "confirmation_form": False,
                "invalid_controls": 1,
                "alerts": 1,
            }

    detail = module._confirmation_transition_detail(Page(), "123")

    assert detail == {
        "project_id": "123",
        "page_url": "https://www.lancers.jp/work/propose_start/123?proposeReferer=detail",
        "ready_state": "complete",
        "proposal_form": True,
        "confirmation_form": False,
        "invalid_controls": 1,
        "alerts": 1,
    }


def test_confirmation_timeout_path_skips_unbounded_dom_evaluate():
    module = _module()

    class Page:
        url = "https://www.lancers.jp/work/propose_start/123?proposeReferer=detail"

        def evaluate(self, _script):
            raise AssertionError("timeout diagnostics must not evaluate a stalled renderer")

    detail = module._confirmation_transition_detail(Page(), "123", allow_evaluate=False)

    assert detail == {
        "project_id": "123",
        "page_url": "https://www.lancers.jp/work/propose_start/123?proposeReferer=detail",
        "diagnostic": "page_url_only_after_transition_timeout",
    }


def test_playwright_cleanup_force_stops_client_when_stop_fails():
    module = _module()

    class Process:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

    process = Process()

    class Runtime:
        _connection = type(
            "Connection", (), {"_transport": type("Transport", (), {"_proc": process})()}
        )()

        def stop(self):
            raise RuntimeError("client already gone")

    module._stop_playwright_runtime(Runtime())

    assert process.terminated is True


def test_playwright_cleanup_watchdog_terminates_stalled_client(monkeypatch):
    module = _module()
    released = threading.Event()

    class Process:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True
            released.set()

        def wait(self, timeout=None):
            return 0

    process = Process()

    class Runtime:
        _connection = type(
            "Connection", (), {"_transport": type("Transport", (), {"_proc": process})()}
        )()

        def stop(self):
            assert released.wait(1)

    monkeypatch.setattr(module, "PLAYWRIGHT_STOP_TIMEOUT_SECONDS", 0.01)
    module._stop_playwright_runtime(Runtime())

    assert process.terminated is True


def test_page_cleanup_force_stops_client_when_close_fails():
    module = _module()

    class Process:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            return 0

    process = Process()
    runtime = type(
        "Runtime",
        (), {
            "_connection": type(
                "Connection", (), {"_transport": type("Transport", (), {"_proc": process})()}
            )(),
        },
    )()

    class Page:
        context = type("Context", (), {"browser": type("Browser", (), {"_anicca_playwright_runtime": runtime})()})()

        def close(self):
            raise RuntimeError("renderer already gone")

    assert module._close_owned_page(Page()) is False
    assert process.terminated is True


def test_page_cleanup_watchdog_terminates_stalled_client(monkeypatch):
    module = _module()
    released = threading.Event()

    class Process:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None if not self.terminated else 0

        def terminate(self):
            self.terminated = True
            released.set()

        def wait(self, timeout=None):
            return 0

    process = Process()
    runtime = type(
        "Runtime",
        (), {
            "_connection": type(
                "Connection", (), {"_transport": type("Transport", (), {"_proc": process})()}
            )(),
        },
    )()

    class Page:
        context = type("Context", (), {"browser": type("Browser", (), {"_anicca_playwright_runtime": runtime})()})()

        def close(self):
            assert released.wait(1)

    monkeypatch.setattr(module, "PLAYWRIGHT_STOP_TIMEOUT_SECONDS", 0.01)
    assert module._close_owned_page(Page()) is True
    assert process.terminated is True
