from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "skills/earn/lancers/scripts/work_sync.py"
DASHBOARD_URL = "https://www.lancers.jp/mypage"


def _module():
    spec = importlib.util.spec_from_file_location(
        "lancers_account_readiness_diagnostics_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _page(*, status=200, url=DASHBOARD_URL, login_count=0, error=None):
    class Page:
        def __init__(self):
            self.url = url

        def goto(self, requested_url):
            assert requested_url == DASHBOARD_URL
            if error is not None:
                raise RuntimeError(error)
            return None if status is None else SimpleNamespace(status=status)

        def locator(self, selector):
            assert selector == "#login_form"
            return SimpleNamespace(count=lambda: login_count)

    return Page()


@pytest.mark.parametrize(
    ("name", "status", "url", "login_count", "error", "expected"),
    [
        (
            "response_none",
            None,
            DASHBOARD_URL,
            0,
            None,
            {
                "ready": False,
                "reason": "response_none",
                "http_status": None,
                "final_route_category": "unavailable",
                "login_form_count": None,
                "exception_type": None,
            },
        ),
        (
            "http_non_200",
            403,
            DASHBOARD_URL,
            0,
            None,
            {
                "ready": False,
                "reason": "http_non_200",
                "http_status": 403,
                "final_route_category": "unavailable",
                "login_form_count": None,
                "exception_type": None,
            },
        ),
        (
            "final_route_mismatch",
            200,
            "https://www.lancers.jp/users/4242?email=private%40example.test&token=url-secret",
            0,
            None,
            {
                "ready": False,
                "reason": "final_route_mismatch",
                "http_status": 200,
                "final_route_category": "other",
                "login_form_count": None,
                "exception_type": None,
            },
        ),
        (
            "login_form_present",
            200,
            DASHBOARD_URL,
            2,
            None,
            {
                "ready": False,
                "reason": "login_form_present",
                "http_status": 200,
                "final_route_category": "dashboard",
                "login_form_count": 2,
                "exception_type": None,
            },
        ),
        (
            "exception",
            200,
            DASHBOARD_URL,
            0,
            "private exception text https://www.lancers.jp/mypage?token=exception-secret",
            {
                "ready": False,
                "reason": "exception",
                "http_status": None,
                "final_route_category": "unavailable",
                "login_form_count": None,
                "exception_type": "RuntimeError",
            },
        ),
        (
            "ready",
            200,
            DASHBOARD_URL,
            0,
            None,
            {
                "ready": True,
                "reason": "ready",
                "http_status": 200,
                "final_route_category": "dashboard",
                "login_form_count": 0,
                "exception_type": None,
            },
        ),
    ],
)
def test_account_readiness_diagnostic_distinguishes_failures_without_url_or_message(
    name, status, url, login_count, error, expected
):
    module = _module()
    page = _page(status=status, url=url, login_count=login_count, error=error)

    diagnostic = module.application_tick._production_account_diagnostic(page)

    assert diagnostic == expected, name
    assert module.application_tick._production_account_ready(
        _page(status=status, url=url, login_count=login_count, error=error)
    ) is expected["ready"]
    serialized = json.dumps(diagnostic)
    for secret in ("4242", "private%40example.test", "url-secret", "exception-secret", "private exception text"):
        assert secret not in serialized


def test_work_sync_result_keeps_account_unavailable_and_safe_diagnostic(tmp_path, monkeypatch):
    module = _module()
    page = _page(
        status=200,
        url="https://www.lancers.jp/mypage?account=hidden-user&token=work-sync-secret",
    )
    monkeypatch.setattr(module, "_verified_proposals", lambda _path: set())
    monkeypatch.setattr(
        module.application_tick,
        "_open_owned_page",
        lambda *_args, **_kwargs: (object(), page),
    )
    monkeypatch.setattr(module, "_cleanup", lambda *_args: True)

    result = module.run_tick(state_path=tmp_path / "state.json")

    assert result["error"] == "account_unavailable"
    assert result["logged_in"] is False
    assert result["account_diagnostic"] == {
        "ready": False,
        "reason": "final_route_mismatch",
        "http_status": 200,
        "final_route_category": "other",
        "login_form_count": None,
        "exception_type": None,
    }
    serialized = json.dumps(result)
    assert "hidden-user" not in serialized
    assert "work-sync-secret" not in serialized
