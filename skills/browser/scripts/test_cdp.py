from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


def _load_module():
    path = Path(__file__).resolve().parent / "cdp.py"
    spec = importlib.util.spec_from_file_location("browser_cdp", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_host_matches_context_lease_websocket_host(monkeypatch):
    monkeypatch.delenv("CDP_HOST", raising=False)
    assert _load_module().HOST == "127.0.0.1"


def test_explicit_host_remains_supported(monkeypatch):
    monkeypatch.setenv("CDP_HOST", "browser.internal")
    assert _load_module().HOST == "browser.internal"


def test_guarded_cdp_url_selects_the_leased_browser(monkeypatch):
    monkeypatch.delenv("CDP_HOST", raising=False)
    monkeypatch.delenv("CDP_PORT", raising=False)
    monkeypatch.setenv("CDP", "http://127.0.0.1:61993")

    module = _load_module()

    assert module.HOST == "127.0.0.1"
    assert module.PORT == "61993"
    assert module.BASE == "http://127.0.0.1:61993"


def test_guarded_lease_overrides_stale_inherited_host_and_port(monkeypatch):
    monkeypatch.setenv("CDP", "http://127.0.0.1:61993")
    monkeypatch.setenv("CDP_HOST", "browser.internal")
    monkeypatch.setenv("CDP_PORT", "9333")

    module = _load_module()

    assert module.HOST == "127.0.0.1"
    assert module.PORT == "61993"


def test_new_claims_target_for_required_owner(monkeypatch, capsys):
    module = _load_module()
    events = []
    monkeypatch.setattr(
        module, "_browser_call", lambda method, params: {"targetId": "new-tab"}
    )
    monkeypatch.setattr(
        module.target_ownership,
        "claim_target",
        lambda target, owner, max_targets=None: events.append(
            (target, owner, max_targets)
        ),
    )

    assert module.main(["new", "about:blank", "paid-room"]) == 0
    assert capsys.readouterr().out.strip() == "new-tab"
    assert events == [("new-tab", "paid-room", 1)]


def test_close_refuses_foreign_target_before_cdp_call(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module.target_ownership, "owns_target", lambda _target, _owner: False
    )
    with patch.object(module, "_browser_call") as browser_call:
        with pytest.raises(PermissionError):
            module.main(["close", "foreign-tab", "paid-room"])
    browser_call.assert_not_called()


def test_new_target_claims_and_returns_id(monkeypatch):
    module = _load_module()
    events = []
    monkeypatch.setattr(
        module, "_browser_call", lambda method, params: {"targetId": "owned-tab"}
    )
    monkeypatch.setattr(
        module.target_ownership,
        "claim_target",
        lambda target, owner, max_targets=None: events.append(
            (target, owner, max_targets)
        ),
    )

    assert module.new_target("https://example.com", "paid-room") == "owned-tab"
    assert events == [("owned-tab", "paid-room", 1)]


def test_new_target_closes_target_when_claim_fails(monkeypatch):
    module = _load_module()
    calls = []

    def browser_call(method, params):
        calls.append((method, params))
        return {"targetId": "unclaimed-tab"}

    monkeypatch.setattr(module, "_browser_call", browser_call)
    monkeypatch.setattr(
        module.target_ownership,
        "claim_target",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("browser_tab_limit")),
    )

    with pytest.raises(RuntimeError, match="browser_tab_limit"):
        module.new_target("about:blank", "paid-room")
    assert calls[-1] == ("Target.closeTarget", {"targetId": "unclaimed-tab"})


def test_close_target_refuses_foreign_owner(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module.target_ownership, "owns_target", lambda _target, _owner: False
    )
    with patch.object(module, "_browser_call") as browser_call:
        with pytest.raises(PermissionError):
            module.close_target("foreign-tab", "paid-room")
    browser_call.assert_not_called()


def test_enter_dispatches_browser_complete_keyboard_identity(monkeypatch):
    module = _load_module()
    calls = []

    class FakeSocket:
        def close(self):
            calls.append(("close", None))

    monkeypatch.setattr(module, "_page", lambda _target: FakeSocket())
    monkeypatch.setattr(
        module,
        "_rpc",
        lambda _ws, _call_id, method, params=None: calls.append((method, params)),
    )

    assert module.key("target", "Enter") == {"key": "Enter"}
    key_events = [params for method, params in calls if method == "Input.dispatchKeyEvent"]
    assert key_events == [
        {
            "type": "keyDown",
            "key": "Enter",
            "code": "Enter",
            "windowsVirtualKeyCode": 13,
            "nativeVirtualKeyCode": 13,
        },
        {
            "type": "keyUp",
            "key": "Enter",
            "code": "Enter",
            "windowsVirtualKeyCode": 13,
            "nativeVirtualKeyCode": 13,
        },
    ]
