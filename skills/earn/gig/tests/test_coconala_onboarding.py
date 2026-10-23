"""Current authentication observations stay separate from verified setup history."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import coconala_onboarding as onboarding
import coconala_onboarding_observe as observer


@pytest.fixture(autouse=True)
def _isolate_browser_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", "http://fixture.invalid")
    monkeypatch.setenv("CLOAK_TARGET_OWNERS_FILE", str(tmp_path / "targets.json"))


def _completed_history(home):
    for state in onboarding.ACCOUNT_GATES:
        onboarding.record(home, state, "a" * 64)
    return onboarding.receipt(home)


def _browser(monkeypatch, page=None):
    def open_tab(url, *, background, owner):
        assert background and owner == "gig-onboarding"
        state = next(state for state, expected in observer.PAGES.items() if url == expected)
        return {"ws": state, "target_id": state}

    async def evaluate(state):
        raw = {"url": observer.PAGES[state], "ready": "complete", "forms": 0,
               "controls": [], "body": "PRIVATE-PAGE-TEXT"}
        return {**raw, **(page(state) if page else {})}

    monkeypatch.setattr(observer.cdp_default_tab, "open_tab", open_tab)
    monkeypatch.setattr(observer.cdp_default_tab, "close_tab", lambda *_a, **_k: None)
    monkeypatch.setattr(observer, "_evaluate", evaluate)
    monkeypatch.setattr(observer.time, "sleep", lambda *_: None)


@pytest.mark.parametrize("redirected", ["all", "bank_registered"])
def test_login_redirect_blocks_resume_without_erasing_setup_history(tmp_path, monkeypatch, redirected):
    before = _completed_history(tmp_path)
    _browser(monkeypatch, lambda state: (
        {"url": "https://coconala.com/login", "forms": 1,
         "controls": [{"type": "email", "required": True, "has_value": True}]}
        if redirected == "all" or state == redirected else {}
    ))

    evidence = observer.observe(tmp_path)
    result, exit_code = onboarding.ready(tmp_path)

    assert exit_code == 2
    assert result == {"status": "blocked", "missing": ["authenticated"]}
    assert evidence["classifications"]["authenticated"] is False
    assert onboarding.receipt(tmp_path) == before
    assert "PRIVATE-PAGE-TEXT" not in json.dumps(evidence)
    if redirected == "all":
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "coconala_onboarding.py"), "ready"],
            env={**os.environ, "HOME": str(tmp_path)}, capture_output=True, text=True,
            timeout=10,
        )
        assert completed.returncode == 2
        assert json.loads(completed.stdout) == result


def test_fresh_authentication_reuses_existing_identity_and_bank_history(tmp_path, monkeypatch):
    before = _completed_history(tmp_path)
    _browser(monkeypatch, lambda _: {"url": "https://coconala.com/login"})
    observer.observe(tmp_path)
    assert onboarding.ready(tmp_path)[1] == 2
    _browser(monkeypatch)

    observer.observe(tmp_path)
    result, exit_code = onboarding.ready(tmp_path)

    assert (result, exit_code) == ({"status": "ready", "missing": []}, 0)
    after = onboarding.receipt(tmp_path)
    for state in ("sms_verified", "seller_information", "identity_approved", "bank_registered"):
        assert after["states"][state] == before["states"][state]


def test_setup_history_without_current_observation_does_not_allow_activation(tmp_path):
    before = _completed_history(tmp_path)

    result, exit_code = onboarding.ready(tmp_path)

    assert (result, exit_code) == ({"status": "blocked", "missing": ["authenticated"]}, 2)
    assert onboarding.receipt(tmp_path) == before


@pytest.mark.parametrize("snapshot", [
    {"url": "https://coconala.com/mypage", "ready": "loading"},
    {"url": "https://coconala.com/error", "ready": "complete"},
    {"url": "https://coconala.com/mypage-unavailable", "ready": "complete"},
])
def test_unconfirmed_current_page_never_reuses_past_authentication(tmp_path, monkeypatch, snapshot):
    before = _completed_history(tmp_path)
    _browser(monkeypatch, lambda _: snapshot)

    evidence = observer.observe(tmp_path)
    result, exit_code = onboarding.ready(tmp_path)

    assert exit_code == 2
    assert result["missing"] == ["authenticated"]
    assert evidence["classifications"]["authenticated"] is None
    assert onboarding.receipt(tmp_path) == before


@pytest.mark.parametrize("boundary", ["open", "evaluate"])
def test_observation_failure_replaces_stale_success_with_unknown(tmp_path, monkeypatch, boundary):
    _completed_history(tmp_path)
    _browser(monkeypatch)
    observer.observe(tmp_path)
    assert onboarding.ready(tmp_path)[1] == 0
    before = onboarding.receipt(tmp_path)

    def fail_open(*_a, **_k):
        raise TimeoutError("fixture_transport_timeout")

    async def fail_evaluate(*_a, **_k):
        raise TimeoutError("fixture_transport_timeout")

    if boundary == "open":
        monkeypatch.setattr(observer.cdp_default_tab, "open_tab", fail_open)
    else:
        monkeypatch.setattr(observer, "_evaluate", fail_evaluate)

    with pytest.raises(TimeoutError, match="fixture_transport_timeout"):
        observer.observe(tmp_path)

    result, exit_code = onboarding.ready(tmp_path)
    assert exit_code == 2
    assert result["missing"] == ["authenticated"]
    latest = json.loads((tmp_path / ".config/anicca/gig/onboarding-observation.json").read_text())
    assert latest["classifications"]["authenticated"] is None
    assert onboarding.receipt(tmp_path) == before


def test_current_authentication_does_not_approve_missing_identity_or_bank(tmp_path, monkeypatch):
    onboarding.record(tmp_path, "preflight", "a" * 64)
    _browser(monkeypatch)

    observer.observe(tmp_path)
    result, exit_code = onboarding.ready(tmp_path)

    assert exit_code == 2
    assert result["missing"] == [
        "sms_verified", "seller_information", "identity_approved", "bank_registered",
    ]


@pytest.mark.parametrize("latest", [
    [],
    {"version": 1, "platform": "other", "classifications": {"authenticated": True}},
    {"version": 1, "platform": "coconala", "classifications": []},
])
def test_invalid_latest_observation_cannot_approve_activation(tmp_path, latest):
    _completed_history(tmp_path)
    (tmp_path / ".config/anicca/gig/onboarding-observation.json").write_text(json.dumps(latest))

    with pytest.raises(ValueError, match="invalid_coconala_onboarding_observation"):
        onboarding.ready(tmp_path)
