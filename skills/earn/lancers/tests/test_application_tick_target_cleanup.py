from __future__ import annotations

import importlib.util
import sys
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
