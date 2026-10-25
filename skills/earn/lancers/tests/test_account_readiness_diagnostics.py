from __future__ import annotations

import importlib.util
from io import BytesIO, StringIO
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
import urllib.request

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "skills/earn/lancers/scripts/work_sync.py"
DASHBOARD_URL = "https://www.lancers.jp/mypage"
BOUND_ACCOUNT = "bound-private-seller"
OTHER_ACCOUNT = "different-private-seller"


def _account_snapshot(**updates):
    return {
        "url": DASHBOARD_URL, "ready": "complete", "login_form": False,
        "human_verification": False,
        "profile_links": [f"https://www.lancers.jp/profile/{BOUND_ACCOUNT}"],
        "body": "PRIVATE-DOM", **updates,
    }


@pytest.fixture(autouse=True)
def isolated_account_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *_a, **_k: pytest.fail("real HTTP/browser/solver access is forbidden"),
    )
    spec = importlib.util.spec_from_file_location(
        "lancers_readiness_onboarding_fixture", SCRIPT.with_name("lancers_onboarding.py")
    )
    onboarding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(onboarding)
    assert onboarding.connect(home, _account_snapshot()) == {
        "ok": True, "status": "account_connected",
    }
    return home


def _module():
    spec = importlib.util.spec_from_file_location(
        "lancers_account_readiness_diagnostics_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _page(*, status=200, url=DASHBOARD_URL, login_count=0, error=None,
          aws_waf=False, snapshots=None, observation_error=None):
    class Page:
        def __init__(self):
            self.url = url
            self.navigations = []
            self.snapshot_reads = 0
            self.waits = []
            self.context = SimpleNamespace(
                cookies=lambda _urls: [], add_cookies=lambda _cookies: None,
            )

        def goto(self, requested_url):
            assert requested_url == DASHBOARD_URL
            self.navigations.append(requested_url)
            if error is not None:
                raise RuntimeError(error)
            if aws_waf and len(self.navigations) == 1:
                return SimpleNamespace(status=405)
            return None if status is None else SimpleNamespace(status=status)

        def locator(self, selector):
            assert selector == "#login_form"
            return SimpleNamespace(count=lambda: login_count)

        def evaluate(self, expression):
            if "Boolean(window.gokuProps)" in expression:
                return False
            if "const props = window.gokuProps" in expression:
                return {
                    "gokuProps": {"key": "fixture-key", "iv": "fixture-iv", "context": "fixture-context"},
                    "challengeJS": "https://scripts.token.awswaf.com/fixture/challenge.js",
                } if aws_waf else {}
            assert ".mypage.result-summary a[href*=" in expression
            self.snapshot_reads += 1
            if observation_error is not None:
                raise observation_error
            samples = snapshots if snapshots is not None else [_account_snapshot()]
            return samples[min(self.snapshot_reads - 1, len(samples) - 1)]

        def wait_for_timeout(self, milliseconds):
            self.waits.append(milliseconds / 1000)

    return Page()


def _fake_waf_solver(module, monkeypatch):
    calls = []
    monkeypatch.setattr(module._capsolver, "api_key", lambda: calls.append("key") or "fixture-api-key")
    monkeypatch.setattr(
        module._capsolver, "create_aws_waf_task",
        lambda *_a, **_k: calls.append("create") or {"task_id": "fixture-task-id"},
    )
    monkeypatch.setattr(
        module._capsolver, "solve_aws_waf_task",
        lambda *_a, **_k: calls.append("solve") or {"cookie": "fixture-waf-cookie", "cost": 0.001},
    )
    return calls


def _binding_bytes(home):
    directory = home / ".config/anicca/lancers"
    return {path.name: path.read_bytes() for path in directory.iterdir()}


def _assert_safe_diagnostic(diagnostic, *, aws_waf):
    assert set(diagnostic) == {
        "ready", "reason", "http_status", "final_route_category", "login_form_count", "exception_type",
    } | ({"aws_waf"} if aws_waf else set())
    rendered = json.dumps(diagnostic)
    for secret in (BOUND_ACCOUNT, OTHER_ACCOUNT, "PRIVATE-DOM", "PRIVATE-EXCEPTION",
                   "fixture-api-key", "fixture-waf-cookie", "fixture-key", "fixture-iv", "fixture-context"):
        assert secret not in rendered


@pytest.mark.parametrize("aws_waf", [False, True], ids=["http200", "waf_solved"])
@pytest.mark.parametrize("account", [BOUND_ACCOUNT, OTHER_ACCOUNT], ids=["same_account", "other_account"])
def test_live_readiness_requires_the_bound_summary_account(
    isolated_account_home, monkeypatch, aws_waf, account,
):
    module = _module().application_tick
    calls = _fake_waf_solver(module, monkeypatch)
    previous = _binding_bytes(isolated_account_home)
    snapshot = _account_snapshot(profile_links=[f"https://www.lancers.jp/profile/{account}"])
    page = _page(aws_waf=aws_waf, snapshots=[snapshot])
    monkeypatch.setattr(module.time, "sleep", page.waits.append)

    diagnostic = module._production_account_diagnostic(
        page, solve_aws_waf=True, solver_state_path=isolated_account_home / "diagnostic-waf.json",
    )

    assert diagnostic["ready"] is (account == BOUND_ACCOUNT)
    assert (diagnostic["reason"] == "ready") is (account == BOUND_ACCOUNT)
    assert diagnostic["http_status"] == 200
    assert diagnostic["final_route_category"] == "dashboard"
    assert diagnostic["login_form_count"] == 0
    assert page.snapshot_reads == 1
    assert page.waits == []
    _assert_safe_diagnostic(diagnostic, aws_waf=aws_waf)
    if aws_waf:
        assert diagnostic["aws_waf"] == {
            "task_id": "fixture-task-id", "status": "ready", "cost": 0.001, "http_statuses": [405, 200],
        }
    ready_page = _page(aws_waf=aws_waf, snapshots=[snapshot])
    assert module._production_account_ready(ready_page) is (account == BOUND_ACCOUNT)
    assert ready_page.snapshot_reads == 1
    assert len(page.navigations) == len(ready_page.navigations) == (2 if aws_waf else 1)
    assert calls == (["key", "create", "solve"] * 2 if aws_waf else [])
    assert _binding_bytes(isolated_account_home) == previous


@pytest.mark.parametrize("aws_waf", [False, True], ids=["http200", "waf_solved"])
@pytest.mark.parametrize("binding", ["missing", "corrupt"])
def test_missing_or_corrupt_binding_stops_before_goto_or_solver(
    isolated_account_home, monkeypatch, aws_waf, binding,
):
    profile_path = isolated_account_home / ".config/anicca/lancers/public-profile.json"
    profile = json.loads(profile_path.read_text())
    if binding == "missing":
        profile.pop("account_binding")
    else:
        profile["account_binding"]["observation_sha256"] = "b" * 64
    profile_path.write_text(json.dumps(profile))
    previous = _binding_bytes(isolated_account_home)
    module = _module().application_tick
    calls = _fake_waf_solver(module, monkeypatch)
    page = _page(aws_waf=aws_waf)

    diagnostic = module._production_account_diagnostic(
        page, solve_aws_waf=True, solver_state_path=isolated_account_home / "diagnostic-waf.json",
    )

    assert diagnostic["ready"] is False
    assert diagnostic["reason"] not in {"ready", "exception"}
    assert diagnostic["http_status"] is None
    assert diagnostic["final_route_category"] == "unavailable"
    assert diagnostic["login_form_count"] is None
    assert diagnostic["exception_type"] is None
    _assert_safe_diagnostic(diagnostic, aws_waf=False)
    ready_page = _page(aws_waf=aws_waf)
    assert module._production_account_ready(ready_page) is False
    assert page.navigations == ready_page.navigations == []
    assert page.snapshot_reads == ready_page.snapshot_reads == 0
    assert calls == []
    assert _binding_bytes(isolated_account_home) == previous


@pytest.mark.parametrize("aws_waf", [False, True], ids=["http200", "waf_solved"])
@pytest.mark.parametrize("failure,updates", [
    ("empty", {"profile_links": []}),
    ("ambiguous", {"profile_links": [f"https://www.lancers.jp/profile/{BOUND_ACCOUNT}",
                                       f"https://www.lancers.jp/profile/{OTHER_ACCOUNT}"]}),
    ("public_profile", {"url": f"https://www.lancers.jp/profile/{BOUND_ACCOUNT}"}),
    ("invalid_origin", {"url": "https://www.lancers.jp.evil.example/mypage"}),
    ("login", {"login_form": True}),
    ("challenge", {"human_verification": True}),
    ("timeout", {"ready": "loading"}),
    ("exception", {}),
])
def test_live_readiness_rejects_unconfirmed_summary_without_leaking_or_rebinding(
    isolated_account_home, monkeypatch, aws_waf, failure, updates,
):
    module = _module().application_tick
    _fake_waf_solver(module, monkeypatch)
    previous = _binding_bytes(isolated_account_home)
    page = _page(
        aws_waf=aws_waf, snapshots=[_account_snapshot(**updates)],
        observation_error=RuntimeError("PRIVATE-EXCEPTION") if failure == "exception" else None,
    )
    monkeypatch.setattr(module.time, "sleep", page.waits.append)

    diagnostic = module._production_account_diagnostic(
        page, solve_aws_waf=True, solver_state_path=isolated_account_home / "diagnostic-waf.json",
    )

    assert diagnostic["ready"] is False
    assert diagnostic["reason"] != "ready"
    assert diagnostic["http_status"] == 200
    assert 1 <= page.snapshot_reads <= 20
    if failure == "timeout":
        assert page.snapshot_reads == 20
    assert len(page.waits) <= 20
    assert all(delay == 0.5 for delay in page.waits)
    _assert_safe_diagnostic(diagnostic, aws_waf=aws_waf)
    assert _binding_bytes(isolated_account_home) == previous


@pytest.mark.parametrize("aws_waf", [False, True], ids=["http200", "waf_solved"])
def test_live_readiness_waits_for_loading_then_positive_summary(
    isolated_account_home, monkeypatch, aws_waf,
):
    module = _module().application_tick
    _fake_waf_solver(module, monkeypatch)
    previous = _binding_bytes(isolated_account_home)
    page = _page(aws_waf=aws_waf, snapshots=[
        _account_snapshot(ready="loading", profile_links=[]),
        _account_snapshot(profile_links=[]),
        _account_snapshot(),
    ])
    monkeypatch.setattr(module.time, "sleep", page.waits.append)

    diagnostic = module._production_account_diagnostic(
        page, solve_aws_waf=True, solver_state_path=isolated_account_home / "diagnostic-waf.json",
    )

    assert diagnostic["ready"] is True
    assert page.snapshot_reads == 3
    assert page.waits == [0.5, 0.5]
    assert len(page.navigations) == (2 if aws_waf else 1)
    _assert_safe_diagnostic(diagnostic, aws_waf=aws_waf)
    assert _binding_bytes(isolated_account_home) == previous


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

    @contextmanager
    def fake_guard():
        yield

    monkeypatch.setattr(module.application_tick, "lancers_browser_guard", fake_guard, raising=False)

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


@pytest.mark.parametrize(
    ("name", "status", "url", "login_count", "error", "expected"),
    [
        (
            "http_405",
            405,
            DASHBOARD_URL,
            0,
            None,
            {
                "ready": False,
                "reason": "http_non_200",
                "http_status": 405,
                "final_route_category": "unavailable",
                "login_form_count": None,
                "exception_type": None,
            },
        ),
        (
            "http_503",
            503,
            DASHBOARD_URL,
            0,
            None,
            {
                "ready": False,
                "reason": "http_non_200",
                "http_status": 503,
                "final_route_category": "unavailable",
                "login_form_count": None,
                "exception_type": None,
            },
        ),
        (
            "final_route_mismatch",
            200,
            "https://www.lancers.jp/users/4242?email=private%40example.test&token=route-secret",
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
    ],
)
def test_preflight_cli_retains_safe_account_diagnostic(
    tmp_path, monkeypatch, name, status, url, login_count, error, expected
):
    module = _module()
    page = _page(status=status, url=url, login_count=login_count, error=error)
    diagnostic_calls = []
    cleanup_calls = []
    surface_reads = []
    original_diagnostic = module.application_tick._production_account_diagnostic

    def observe_diagnostic(observed_page, **kwargs):
        diagnostic_calls.append(kwargs)
        return original_diagnostic(observed_page, **kwargs)

    monkeypatch.setattr(
        module.application_tick, "_production_account_diagnostic", observe_diagnostic
    )
    monkeypatch.setattr(module, "_verified_proposals", lambda _path: set())
    monkeypatch.setattr(
        module.application_tick,
        "_open_owned_page",
        lambda *_args, **_kwargs: (object(), page),
    )
    monkeypatch.setattr(
        module,
        "_read_surfaces",
        lambda *_args: surface_reads.append(True),
    )

    def cleanup(*_args):
        cleanup_calls.append(True)
        return True

    monkeypatch.setattr(module, "_cleanup", cleanup)

    @contextmanager
    def fake_account_lock(_path):
        yield

    monkeypatch.setattr(module.application_tick, "account_lock", fake_account_lock)

    output = StringIO()
    exit_code = module.main(
        ["--preflight", "--json", "--state-path", str(tmp_path / "state.json")],
        output_stream=output,
        browser_factory=lambda _name: None,
    )

    result = json.loads(output.getvalue())
    assert exit_code == 1, name
    assert result["error"] == "account_unavailable"
    assert result["failed_read"] == 1
    assert result["logged_in"] is False
    assert result["account_diagnostic"] == expected
    assert diagnostic_calls == [{"solve_aws_waf": False}]
    assert surface_reads == []
    assert len(cleanup_calls) == 1
    serialized = json.dumps(result)
    for secret in (
        "4242",
        "private%40example.test",
        "route-secret",
        "exception-secret",
        "private exception text",
    ):
        assert secret not in serialized


@pytest.mark.parametrize(
    ("readback_status", "challenge_after_readback", "expected_ready", "expected_reason"),
    [(200, False, True, "ready"), (405, True, False, "aws_waf_challenge_remains")],
)
def test_live_work_sync_uses_one_aws_waf_task_and_checks_official_readback(
    tmp_path, monkeypatch, readback_status, challenge_after_readback,
    expected_ready, expected_reason,
):
    module = _module()
    cookie_values = [
        {"name": "aws-waf-token", "value": "stale", "domain": ".lancers.jp", "path": "/"},
        {"name": "aws-waf-token", "value": "stale", "domain": "www.lancers.jp", "path": "/challenge"},
        {"name": "aws-waf-token", "value": "keep", "domain": "otherlancers.jp", "path": "/"},
        {"name": "lancers_session", "value": "keep", "domain": ".lancers.jp", "path": "/"},
    ]
    cleared, added, navigations = [], [], []

    class Context:
        def cookies(self, _urls):
            return list(cookie_values)

        def clear_cookies(self, **selectors):
            cleared.append(selectors)

        def add_cookies(self, cookies):
            added.extend(cookies)

    class Page:
        url = DASHBOARD_URL
        context = Context()

        def goto(self, url):
            assert url == DASHBOARD_URL
            navigations.append(url)
            return SimpleNamespace(status=405 if len(navigations) == 1 else readback_status)

        def evaluate(self, script):
            if "Boolean(window.gokuProps)" in script:
                return challenge_after_readback
            if ".mypage.result-summary a[href*=" in script:
                return _account_snapshot()
            return {
                "gokuProps": {"key": "fixture-key", "iv": "fixture-iv", "context": "fixture-context"},
                "challengeJS": "https://scripts.token.awswaf.com/fixture/challenge.js",
            }

        def locator(self, selector):
            assert selector == "#login_form"
            return SimpleNamespace(count=lambda: 0)

    page = Page()
    monkeypatch.setattr(module, "_verified_proposals", lambda _path: set())
    surface_reads = []

    def fake_read_surfaces(*_args):
        surface_reads.append(True)
        return {
            "board_count": 0,
            "unread_count": 0,
            "required_reply_count": 0,
            "application_board_count": 0,
            "boards": [],
            "proposal_pipeline": {},
            "finance": {},
            "project_working_count": 0,
            "monthly_contract_count": 0,
            "incoming_monthly_offer_count": 0,
            "incoming_monthly_offers": [],
            "storefront_contract_candidate_count": 0,
            "contract_candidate_count": 0,
            "contract_candidates": [],
            "ok": True,
            "source_complete": True,
        }

    monkeypatch.setattr(module, "_read_surfaces", fake_read_surfaces)
    monkeypatch.setattr(module.application_tick, "_open_owned_page", lambda *_args, **_kwargs: (object(), page))
    monkeypatch.setattr(module, "_cleanup", lambda *_args: True)

    guard_entries = []

    @contextmanager
    def fake_guard():
        guard_entries.append(True)
        yield

    monkeypatch.setattr(module.application_tick, "lancers_browser_guard", fake_guard, raising=False)

    solver = module.application_tick._capsolver
    monkeypatch.setattr(solver, "api_key", lambda: "fixture-api-key")
    posts = []
    state_path = tmp_path / "application.json"
    solver_state = state_path.with_name("aws-waf-solver.json")

    def fake_post(path, payload, *, timeout=30):
        posts.append((path, payload, timeout))
        if path == "/createTask":
            assert json.loads(solver_state.read_text()) == {
                "record_type": "lancers_aws_waf_task.v1",
                "status": "effect_unknown",
                "task_id": None,
            }
            return {"taskId": "fixture-task-id"}
        return {
            "taskId": "fixture-task-id",
            "status": "ready",
            "solution": {"cookie": "fixture-waf-cookie"},
            "cost": 0.001,
        }

    monkeypatch.setattr(solver, "post", fake_post)

    result = module.run_tick(state_path=state_path)

    assert result["ok"] is expected_ready
    assert result["account_diagnostic"]["reason"] == expected_reason
    assert result["account_diagnostic"]["http_status"] == readback_status
    assert result["account_diagnostic"]["aws_waf"] == {
        "task_id": "fixture-task-id",
        "status": "ready",
        "cost": 0.001,
        "http_statuses": [405, readback_status],
    }
    assert navigations == [DASHBOARD_URL, DASHBOARD_URL]
    assert guard_entries == [True]
    assert [call[0] for call in posts].count("/createTask") == 1
    assert len(posts) == 2
    assert posts[0][1]["task"] == {
        "type": "AntiAwsWafTaskProxyLess",
        "websiteURL": DASHBOARD_URL,
        "awsKey": "fixture-key",
        "awsIv": "fixture-iv",
        "awsContext": "fixture-context",
        "awsChallengeJS": "https://scripts.token.awswaf.com/fixture/challenge.js",
    }
    assert cleared == [
        {"name": "aws-waf-token", "domain": ".lancers.jp", "path": "/"},
        {"name": "aws-waf-token", "domain": "www.lancers.jp", "path": "/challenge"},
    ]
    assert added == [{
        "name": "aws-waf-token",
        "value": "fixture-waf-cookie",
        "domain": ".lancers.jp",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "Lax",
    }]
    assert len(surface_reads) == (1 if expected_ready else 0)
    if expected_ready:
        assert not solver_state.exists()
    else:
        assert json.loads(solver_state.read_text()) == {
            "record_type": "lancers_aws_waf_task.v1",
            "status": "pending",
            "task_id": "fixture-task-id",
        }
        resumed = module.run_tick(state_path=state_path)
        assert resumed["account_diagnostic"]["reason"] == "aws_waf_challenge_remains"
        assert [call[0] for call in posts] == ["/createTask", "/getTaskResult", "/getTaskResult"]
        assert solver_state.exists()
    rendered = json.dumps(result)
    for secret in ("fixture-api-key", "fixture-waf-cookie", "fixture-context", "fixture-key", "fixture-iv"):
        assert secret not in rendered


def test_work_sync_does_not_solve_non_aws_405_or_read_only_inventory(tmp_path, monkeypatch):
    module = _module()
    posts = []
    monkeypatch.setattr(module.application_tick._capsolver, "post", lambda *args, **kwargs: posts.append(args))
    monkeypatch.setattr(module, "_verified_proposals", lambda _path: set())
    monkeypatch.setattr(module.application_tick, "_open_owned_page", lambda *_args, **_kwargs: (object(), _page(status=405)))
    monkeypatch.setattr(module, "_cleanup", lambda *_args: True)

    @contextmanager
    def fake_guard():
        yield

    monkeypatch.setattr(module.application_tick, "lancers_browser_guard", fake_guard, raising=False)

    result = module.run_tick(state_path=tmp_path / "application.json")

    assert result["error"] == "account_unavailable"
    readonly_page = SimpleNamespace(
        url=DASHBOARD_URL,
        goto=lambda _url: SimpleNamespace(status=405),
        evaluate=lambda _script: {
            "gokuProps": {"key": "fixture-key", "iv": "fixture-iv", "context": "fixture-context"},
            "challengeJS": "https://scripts.token.awswaf.com/fixture/challenge.js",
        },
    )
    monkeypatch.setattr(module.application_tick, "_open_owned_page", lambda *_args, **_kwargs: (object(), readonly_page))
    readonly = module.read_only_inventory(state_path=tmp_path / "application.json")
    assert readonly["error"] == "account_unavailable"
    assert posts == []


def test_aws_waf_create_timeout_is_held_without_reposting_or_leaking_secrets(tmp_path, monkeypatch):
    module = _module()
    page = SimpleNamespace(
        url=DASHBOARD_URL,
        goto=lambda _url: SimpleNamespace(status=405),
        evaluate=lambda _script: {
            "gokuProps": {"key": "private-key", "iv": "private-iv", "context": "private-context"},
            "challengeJS": "https://scripts.token.awswaf.com/fixture/challenge.js",
        },
    )
    solver = module.application_tick._capsolver
    monkeypatch.setattr(solver, "api_key", lambda: "private-api-key")
    posts = []

    def timed_out_post(path, _payload, **_kwargs):
        posts.append(path)
        raise TimeoutError("private response body and token")

    monkeypatch.setattr(solver, "post", timed_out_post)
    state_path = tmp_path / "application.json"
    solver_state = state_path.with_name("aws-waf-solver.json")

    first = module.application_tick._production_account_diagnostic(
        page, solve_aws_waf=True, solver_state_path=solver_state,
    )
    second = module.application_tick._production_account_diagnostic(
        page, solve_aws_waf=True, solver_state_path=solver_state,
    )

    assert first["reason"] == "aws_waf_effect_unknown"
    assert second["reason"] == "aws_waf_effect_unknown"
    assert posts == ["/createTask"]
    assert json.loads(solver_state.read_text()) == {
        "record_type": "lancers_aws_waf_task.v1",
        "status": "effect_unknown",
        "task_id": None,
    }
    rendered = json.dumps([first, second, json.loads(solver_state.read_text())])
    for secret in ("private-api-key", "private response body", "private-key", "private-iv", "private-context"):
        assert secret not in rendered


def test_aws_waf_no_credits_is_typed_without_retry(tmp_path, monkeypatch):
    module = _module()
    page = SimpleNamespace(
        url=DASHBOARD_URL,
        goto=lambda _url: SimpleNamespace(status=405),
        evaluate=lambda _script: {
            "gokuProps": {"key": "fixture-key", "iv": "fixture-iv", "context": "fixture-context"},
            "challengeJS": "https://scripts.token.awswaf.com/fixture/challenge.js",
        },
    )
    solver = module.application_tick._capsolver
    monkeypatch.setattr(solver, "api_key", lambda: "fixture-api-key")
    urls = []

    def no_credits(request, **_kwargs):
        urls.append(request.full_url)
        raise HTTPError(
            request.full_url, 400, "Bad Request", None,
            BytesIO(b'{"errorId":1,"errorCode":"ERROR_ZERO_BALANCE","errorDescription":"private api detail"}'),
        )

    monkeypatch.setattr(solver, "urlopen", no_credits)
    solver_state = tmp_path / "aws-waf-solver.json"
    result = module.application_tick._production_account_diagnostic(
        page, solve_aws_waf=True, solver_state_path=solver_state,
    )

    assert result["reason"] == "aws_waf_no_credits"
    assert urls == ["https://api.capsolver.com/createTask"]
    assert not solver_state.exists()
    rendered = json.dumps(result)
    assert "fixture-api-key" not in rendered
    assert "private api detail" not in rendered


def test_aws_waf_challenge_parameters_accepts_observed_token_subdomain():
    module = _module()
    challenge_js = (
        "https://7dcb501c5ea9.423e5b42.ap-northeast-1.token.awswaf.com/a/b/challenge.js"
    )
    page = SimpleNamespace(evaluate=lambda _script: {
        "gokuProps": {"key": "fixture-key", "iv": "fixture-iv", "context": "fixture-context"},
        "challengeJS": challenge_js,
    })

    assert module.application_tick._aws_waf_challenge_parameters(page) == {
        "key": "fixture-key",
        "iv": "fixture-iv",
        "context": "fixture-context",
        "challenge_js": challenge_js,
    }


@pytest.mark.parametrize("challenge_js", [
    "https://not-token.awswaf.com/a/challenge.js",
    "https://token.awswaf.com.evil.test/a/challenge.js",
    "http://scripts.token.awswaf.com/a/challenge.js",
    "https://user@scripts.token.awswaf.com/a/challenge.js",
    "https://scripts.token.awswaf.com:8443/a/challenge.js",
    "https://scripts.token.awswaf.com/a/challenge.js?key=secret",
    "https://scripts.token.awswaf.com/a/challenge.js#secret",
])
def test_aws_waf_challenge_parameters_rejects_lookalikes_and_url_secrets(challenge_js):
    module = _module()
    page = SimpleNamespace(evaluate=lambda _script: {
        "gokuProps": {"key": "fixture-key", "iv": "fixture-iv", "context": "fixture-context"},
        "challengeJS": challenge_js,
    })

    assert module.application_tick._aws_waf_challenge_parameters(page) is None


@pytest.mark.parametrize(
    ("recorded_start", "reuses_inherited"),
    [("fixture-holder-token", True), ("different-token", False)],
)
def test_browser_guard_reuses_only_a_status_verified_inherited_lease(
    monkeypatch, tmp_path, recorded_start, reuses_inherited,
):
    module = _module().application_tick
    guard = tmp_path / "browser-guard.sh"
    monkeypatch.setattr(module, "_browser_guard_path", lambda: guard)
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_IDENTITY", "lancers:dais")
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_LEASE_IDENTITY", "lancers:dais")
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID", str(os.getpid()))
    monkeypatch.setenv("AI_BROWSER_HOLDER_START", "fixture-holder-token")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get("env")))
        if command[1] == "status":
            holder = {
                "identity": "lancers:dais",
                "pid": os.getpid(),
                "host": module.socket.gethostname().split(".")[0],
                "holder_start": recorded_start,
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "identities": [{"identity": "lancers:dais", "holder": json.dumps(holder)}],
            }), stderr="")
        return SimpleNamespace(returncode=9, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    if reuses_inherited:
        with module.lancers_browser_guard():
            pass
        assert [call[0][1] for call in calls] == ["status"]
    else:
        with pytest.raises(module.BrowserGuardBusy):
            with module.lancers_browser_guard():
                pass
        assert [call[0][1] for call in calls] == ["status", "acquire"]


def test_browser_guard_acquires_and_releases_only_its_own_holder(monkeypatch, tmp_path):
    module = _module().application_tick
    guard = tmp_path / "browser-guard.sh"
    monkeypatch.setattr(module, "_browser_guard_path", lambda: guard)
    monkeypatch.setenv("LIFE_MANAGER_BROWSER_IDENTITY", "lancers:dais")
    monkeypatch.delenv("LIFE_MANAGER_BROWSER_LEASE_IDENTITY", raising=False)
    monkeypatch.delenv("LIFE_MANAGER_BROWSER_LEASE_HOLDER_PID", raising=False)
    monkeypatch.delenv("AI_BROWSER_HOLDER_START", raising=False)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get("env")))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with module.lancers_browser_guard():
        pass

    assert [call[0][1] for call in calls] == ["acquire", "release"]
    acquire_env, release_env = calls[0][1], calls[1][1]
    assert acquire_env["AI_BROWSER_HOLDER_PID"] == str(os.getpid())
    assert release_env["AI_BROWSER_HOLDER_PID"] == str(os.getpid())
    assert acquire_env["AI_BROWSER_HOLDER_START"] == release_env["AI_BROWSER_HOLDER_START"]


def test_not_found_waf_task_is_cleared_without_recreating_in_same_run(tmp_path, monkeypatch):
    module = _module().application_tick
    solver = module._capsolver
    monkeypatch.setattr(solver, "api_key", lambda: "fixture-api-key")
    calls = []

    def fake_post(path, payload, *, timeout=30):
        calls.append((path, payload))
        return {"errorId": 1, "errorCode": "ERROR_TASK_NOT_FOUND"}

    monkeypatch.setattr(solver, "post", fake_post)
    state_path = tmp_path / "aws-waf-solver.json"
    state_path.write_text(json.dumps({
        "record_type": "lancers_aws_waf_task.v1",
        "status": "pending",
        "task_id": "stale-task",
    }))

    class ChallengePage:
        url = DASHBOARD_URL

        def evaluate(self, _script):
            return {
                "gokuProps": {"key": "fixture-key", "iv": "fixture-iv", "context": "fixture-context"},
                "challengeJS": "https://token.awswaf.com/challenge.js",
            }

    result = module._solve_aws_waf_challenge(ChallengePage(), {"http_status": 405}, state_path)

    assert calls == [("/getTaskResult", {"clientKey": "fixture-api-key", "taskId": "stale-task"})]
    assert result["aws_waf"]["status"] == "failed"
    assert not state_path.exists()
