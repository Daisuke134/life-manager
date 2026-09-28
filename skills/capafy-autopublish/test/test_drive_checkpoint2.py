from __future__ import annotations

import importlib.util
import builtins
import json
import sys
import types
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "drive_checkpoint2.py"


def load_module():
    spec = importlib.util.spec_from_file_location("drive_checkpoint2", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def test_raw_page_targets_only_exact_resolved_cp2_url(monkeypatch) -> None:
    module = load_module()
    cp2 = "https://capafy.ai/developer/createAgent?source=temp-link&token=123&page=credential"
    targets = [
        {"type": "page", "url": "https://coconala.com/", "webSocketDebuggerUrl": "ws://other"},
        {"type": "page", "url": "https://capafy.ai/developer/createAgent?page=credential&source=temp-link&token=123", "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/order"},
        {"type": "page", "url": "https://capafy.ai/developer/createAgent?source=temp-link&token=wrong&page=credential", "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/wrong"},
        {"type": "iframe", "url": "https://capafy.ai/iframe", "webSocketDebuggerUrl": "ws://iframe"},
    ]
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response(targets))

    assert module._raw_page_targets("http://localhost:9222", cp2) == [targets[1]]


def test_raw_target_rejects_evil_host_and_non_loopback_ws(monkeypatch) -> None:
    module = load_module()
    targets = [{
        "type": "page",
        "url": "https://evil.example/developer/createAgent?page=credential",
        "webSocketDebuggerUrl": "ws://evil.example/devtools/page/x",
    }]
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response(targets))

    with pytest.raises(RuntimeError, match="no exact CP2 page"):
        module._raw_page_targets("http://localhost:9222", "https://capafy.ai/developer/createAgent?token=123&page=credential")
    with pytest.raises(RuntimeError, match="loopback HTTP"):
        module._raw_page_targets("http://evil.example:9222", "https://capafy.ai/developer/createAgent?token=123&page=credential")
    with pytest.raises(RuntimeError, match="loopback host"):
        module._validate_ws_url("ws://evil.example/devtools/browser/x")


def test_short_cp2_url_resolves_one_valid_redirect(monkeypatch) -> None:
    module = load_module()
    final = "https://capafy.ai/developer/createAgent?source=temp-link&token=123&page=credential"
    seen = []

    def redirect(url, method):
        seen.append((url, method))
        return [final]

    monkeypatch.setattr(module, "_single_redirect_location", redirect)

    assert module._resolve_cp2_url("https://api.capafy.ai/C123") == final
    assert seen == [("https://api.capafy.ai/C123", "HEAD")]


def test_short_cp2_url_rejects_cross_domain_location(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(
        module,
        "_single_redirect_location",
        lambda *_args: ["https://evil.example/developer/createAgent?token=123&page=credential"],
    )

    with pytest.raises(RuntimeError, match="exact Capafy"):
        module._resolve_cp2_url("https://api.capafy.ai/C123")


def test_short_cp2_url_rejects_invalid_path() -> None:
    module = load_module()

    with pytest.raises(RuntimeError, match="exactly https://api.capafy.ai/C"):
        module._resolve_cp2_url("https://api.capafy.ai/not-a-short-url")


def test_raw_page_connects_to_validated_page_websocket(monkeypatch) -> None:
    module = load_module()
    calls = []

    class _Socket:
        def close(self):
            pass

    fake_websocket = types.SimpleNamespace(
        create_connection=lambda url, **kwargs: (calls.append((url, kwargs)) or _Socket())
    )
    monkeypatch.setitem(sys.modules, "websocket", fake_websocket)

    page = module._RawPage("ws://localhost:9222/devtools/page/capafy")
    page.close()

    assert calls == [("ws://localhost:9222/devtools/page/capafy", {"timeout": 15, "enable_multithread": True})]


@pytest.mark.parametrize(
    "evaluation",
    (
        {"ok": False, "reason": "path-count", "count": 0},
        {"ok": False, "reason": "button-count", "count": 2},
        {"ok": True, "disabled": True, "x": 1, "y": 2},
        {"ok": True, "disabled": False, "x": None, "y": 2},
    ),
)
def test_strict_click_rejects_missing_ambiguous_disabled_or_invalid_coords(evaluation) -> None:
    module = load_module()
    page = object.__new__(module._RawPage)
    page.evaluate = lambda _expression: evaluation
    page.call = lambda *_args, **_kwargs: pytest.fail("no dispatch on rejected strict click")

    with pytest.raises(RuntimeError):
        page.strict_click(module.OPENROUTER_API_KEY_PATH, "confirm")


def test_strict_click_dispatches_first_evaluation_coordinates_only() -> None:
    module = load_module()
    page = object.__new__(module._RawPage)
    page.evaluate = lambda _expression: {"ok": True, "disabled": False, "x": 12, "y": 34}
    calls = []
    page.call = lambda method, params=None: calls.append((method, params)) or {}

    assert page.strict_click(module.OPENROUTER_API_KEY_PATH, "confirm") is True
    assert [method for method, _ in calls] == ["Input.dispatchMouseEvent", "Input.dispatchMouseEvent"]
    assert calls[0][1]["x"] == 12 and calls[0][1]["y"] == 34


def test_strict_click_dispatch_failure_is_fail_closed() -> None:
    module = load_module()
    page = object.__new__(module._RawPage)
    page.evaluate = lambda _expression: {"ok": True, "disabled": False, "x": 12, "y": 34}
    page.call = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("socket closed"))

    with pytest.raises(RuntimeError, match="dispatch failed"):
        page.strict_click(module.OPENROUTER_API_KEY_PATH, "confirm")


def test_raw_navigation_error_text_aborts_before_ready_probe() -> None:
    module = load_module()

    class _Page:
        def __init__(self):
            self.calls = []

        def call(self, method, params=None):
            self.calls.append(method)
            return {"errorText": "net::ERR_CONNECTION_RESET"}

        def evaluate(self, _expression):
            raise AssertionError("navigation error must not probe or write the page")

    page = _Page()
    with pytest.raises(RuntimeError, match="Page.navigate failed"):
        module._wait_raw_navigation(page, "https://capafy.ai/developer/createAgent?token=t&page=credential")
    assert page.calls == ["Page.navigate"]


def test_raw_navigation_location_mismatch_aborts_before_write() -> None:
    module = load_module()

    class _Page:
        def call(self, method, params=None):
            assert method == "Page.navigate"
            return {}

        def evaluate(self, _expression):
            return {"ready": "complete", "href": "https://evil.example/developer/createAgent?token=x"}

    with pytest.raises(RuntimeError, match="wrong origin/path"):
        module._wait_raw_navigation(_Page(), "https://capafy.ai/developer/createAgent?token=t&page=credential")


def test_raw_call_queues_interleaved_events_and_honors_deadline(monkeypatch) -> None:
    module = load_module()

    class _Socket:
        def __init__(self, messages):
            self.messages = iter(messages)

        def send(self, _message):
            pass

        def settimeout(self, _timeout):
            pass

        def recv(self):
            return next(self.messages)

    page = object.__new__(module._RawPage)
    page._next_id = 0
    page._events = []
    page._call_timeout_s = module.RAW_CALL_TIMEOUT_S
    page._session_id = None
    page._ws = _Socket([
        json.dumps({"method": "Page.loadEventFired"}),
        json.dumps({"id": 1, "result": {"value": 7}}),
    ])
    assert page.call("Runtime.evaluate") == {"value": 7}
    assert page._events == [{"method": "Page.loadEventFired"}]

    class _Never:
        def send(self, _message):
            pass

        def settimeout(self, _timeout):
            pass

        def recv(self):
            raise TimeoutError("never")

    page._ws = _Never()
    monkeypatch.setattr(module, "RAW_CALL_TIMEOUT_S", 0.01)
    page._call_timeout_s = module.RAW_CALL_TIMEOUT_S
    with pytest.raises(RuntimeError, match="CDP call timeout"):
        page.call("Runtime.evaluate")


def test_probe_loop_uses_one_shared_five_second_budget(monkeypatch) -> None:
    module = load_module()
    clock = iter((100.0, 100.0, 101.0, 104.0, 104.0))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    budgets = []
    probed = []

    class _Page:
        def __init__(self, ws_url, *, call_timeout, connect_timeout):
            budgets.append((ws_url, call_timeout, connect_timeout))
            if ws_url == "ws://127.0.0.1/bad":
                raise RuntimeError("stale")

        def evaluate(self, _expression):
            probed.append("good")

        def close(self):
            pass

    monkeypatch.setattr(module, "_RawPage", _Page)
    page = module._open_responsive_page([
        {"webSocketDebuggerUrl": "ws://127.0.0.1/bad"},
        {"webSocketDebuggerUrl": "ws://127.0.0.1/good"},
    ])

    assert page is not None
    assert probed == ["good"]
    assert budgets[0][1:] == (5.0, 5.0)
    assert budgets[1][1:] == (4.0, 4.0)


def test_provider_section_skips_count_button_when_path_already_expanded() -> None:
    module = load_module()

    class _Page:
        def __init__(self):
            self.evaluates = []
            self.calls = []

        def evaluate(self, expression):
            self.evaluates.append(expression)
            return {"count": 1}

        def call(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    page = _Page()
    module._ensure_raw_provider_section(page)
    assert len(page.evaluates) == 1
    assert page.calls == []


def test_provider_section_clicks_one_counted_button_then_requires_path() -> None:
    module = load_module()

    class _Page:
        def __init__(self):
            self.states = iter((
                {"count": 0}, {"ok": False, "reason": "configured-proxy-field-count"},
                {"ok": True, "x": 10, "y": 20}, {"count": 1},
            ))
            self.calls = []

        def evaluate(self, expression):
            return next(self.states)

        def call(self, method, params=None):
            self.calls.append((method, params))

    page = _Page()
    module.RAW_SECTION_POLL_S = 0
    module._ensure_raw_provider_section(page)
    assert [method for method, _ in page.calls] == ["Input.dispatchMouseEvent", "Input.dispatchMouseEvent"]


@pytest.mark.parametrize("button_state", ({"ok": False, "reason": "button-count", "count": 0}, {"ok": False, "reason": "button-count", "count": 2}))
def test_provider_section_rejects_missing_or_ambiguous_count_button(button_state) -> None:
    module = load_module()
    module.RAW_SECTION_TIMEOUT_S = 0.01
    module.RAW_SECTION_POLL_S = 0.001

    class _Page:
        def __init__(self):
            self.first = True

        def evaluate(self, _expression):
            if self.first:
                self.first = False
                return {"count": 0}
            return button_state

        def call(self, *_args, **_kwargs):
            pytest.fail("must not click an unavailable/ambiguous detected-keys button")

    with pytest.raises(RuntimeError):
        module._ensure_raw_provider_section(_Page())


def test_provider_section_polls_delayed_provider_path() -> None:
    module = load_module()
    module.RAW_SECTION_POLL_S = 0

    class _Page:
        def __init__(self):
            self.states = iter((
                {"count": 0}, {"ok": False, "reason": "configured-proxy-field-count"},
                {"ok": False, "count": 0}, {"count": 1},
            ))

        def evaluate(self, _expression):
            return next(self.states)

        def call(self, *_args, **_kwargs):
            pytest.fail("detected button should not be clicked")

    module._ensure_raw_provider_section(_Page())


def test_provider_section_polls_delayed_counted_button_and_path() -> None:
    module = load_module()
    module.RAW_SECTION_POLL_S = 0

    class _Page:
        def __init__(self):
            self.states = iter((
                {"count": 0}, {"ok": False, "reason": "configured-proxy-field-count"}, {"ok": False, "count": 0},
                {"count": 0}, {"ok": False, "reason": "configured-proxy-field-count"}, {"ok": True, "x": 10, "y": 20},
                {"count": 1},
            ))
            self.calls = []

        def evaluate(self, _expression):
            return next(self.states)

        def call(self, method, params=None):
            self.calls.append(method)

    page = _Page()
    module._ensure_raw_provider_section(page)
    assert page.calls == ["Input.dispatchMouseEvent", "Input.dispatchMouseEvent"]


def test_provider_section_accepts_expanded_configured_proxy_form() -> None:
    module = load_module()

    class _Page:
        def evaluate(self, expression):
            if "urlName" in expression:
                return {"ok": True}
            return {"count": 0}

        def call(self, *_args, **_kwargs):
            pytest.fail("configured proxy form must not click the detected-keys button")

    assert module._ensure_raw_provider_section(_Page()) == "configured_proxy"


def test_raw_configure_proxy_form_writes_provider_contract_without_model_field() -> None:
    module = load_module()
    focused = []
    calls = []

    class _Page:
        def evaluate(self, expression):
            if "configured-proxy-field-count" in expression:
                return {"ok": True}
            focused.append(expression)
            return {"ok": True}

        def call(self, method, params=None):
            calls.append((method, params))

    module._raw_configure_proxy_form(_Page(), "test-secret")
    assert len(focused) == 4
    assert calls == [
        ("Input.insertText", {"text": module.OPENROUTER_BASE_URL_PATH}),
        ("Input.insertText", {"text": module.OPENROUTER_API_KEY_PATH}),
        ("Input.insertText", {"text": module.BASE_URL}),
        ("Input.insertText", {"text": "test-secret"}),
    ]


def test_provider_section_missing_times_out_and_ambiguous_path_fails_immediately() -> None:
    module = load_module()
    module.RAW_SECTION_TIMEOUT_S = 0.01
    module.RAW_SECTION_POLL_S = 0.001

    class _Missing:
        def evaluate(self, _expression):
            return None

        def call(self, *_args, **_kwargs):
            pytest.fail("missing hydration must not click")

    with pytest.raises(RuntimeError, match="did not hydrate"):
        module._ensure_raw_provider_section(_Missing())

    class _Ambiguous:
        def evaluate(self, _expression):
            return {"count": 2}

        def call(self, *_args, **_kwargs):
            pytest.fail("ambiguous provider path must not click")

    with pytest.raises(RuntimeError, match="ambiguous OpenRouter"):
        module._ensure_raw_provider_section(_Ambiguous())


def test_edit_mode_japanese_field_and_button_signatures_are_strict() -> None:
    module = load_module()
    focus = module._strict_focus_expression(module.OPENROUTER_API_KEY_PATH, "key")
    model_focus = module._strict_focus_expression(module.OPENROUTER_API_KEY_PATH, "model")
    save = module._strict_button_expression(module.OPENROUTER_API_KEY_PATH, "save")
    assert "キャンセル" in focus and "保存" in focus and "キー" in focus
    assert "モデル" in model_focus
    assert "edit-signature" in focus and "edit-field-count" in focus
    assert "キャンセル" in save and "保存" in save and "edit-signature" in save


@pytest.mark.parametrize("failure", ({"ok": False, "reason": "edit-signature"}, {"ok": False, "reason": "edit-field-count", "count": 2}))
def test_edit_mode_fallback_missing_or_duplicate_fails_closed(failure) -> None:
    module = load_module()
    page = object.__new__(module._RawPage)
    page.evaluate = lambda _expression: failure
    page.call = lambda *_args, **_kwargs: pytest.fail("edit fallback failure must not write")

    with pytest.raises(RuntimeError):
        page.strict_focus_and_insert(module.OPENROUTER_API_KEY_PATH, "key", "secret")


def test_provider_state_evaluation_exception_propagates_immediately() -> None:
    module = load_module()

    class _Page:
        def evaluate(self, _expression):
            raise ValueError("renderer disconnected")

    with pytest.raises(ValueError, match="renderer disconnected"):
        module._ensure_raw_provider_section(_Page())


def test_bounded_page_calls_cap_and_restore_timeout(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)

    class _Page:
        _call_timeout_s = 20.0

        def __init__(self):
            self.observed = []

        def evaluate(self, _expression):
            self.observed.append(self._call_timeout_s)
            return {"count": 1}

        def call(self, _method, _params):
            self.observed.append(self._call_timeout_s)
            return {}

    page = _Page()
    deadline = 105.0
    assert module._bounded_page_evaluate(page, "1", deadline) == {"count": 1}
    assert module._bounded_page_call(page, "Input.dispatchMouseEvent", {}, deadline) == {}
    assert page.observed == [5.0, 5.0]
    assert page._call_timeout_s == 20.0


@pytest.mark.parametrize(("raw_ok", "expected_exit"), ((True, 0), (False, 1)))
def test_main_defaults_to_raw_without_playwright_attach(monkeypatch, raw_ok, expected_exit) -> None:
    module = load_module()
    calls = []

    monkeypatch.setattr(module, "_load_playwright", lambda: pytest.fail("default transport must not attach Playwright"))
    monkeypatch.setattr(module, "_detect_cdp", lambda: "http://localhost:9222")

    def raw_fallback(cp2, key, cdp):
        calls.append((cp2, key, cdp))
        return raw_ok

    monkeypatch.setattr(module, "_raw_cp2", raw_fallback)
    monkeypatch.setenv("CAPAFY_HOST_OPENROUTER_KEY", "test-secret")
    monkeypatch.setattr(sys, "argv", ["drive_checkpoint2.py", "https://capafy.ai/developer/createAgent?token=t&page=credential"])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == expected_exit
    assert calls[0][0].startswith("https://capafy.ai/developer/createAgent?")
    assert calls[0][2] == "http://localhost:9222"


def test_raw_default_loads_without_playwright_module(monkeypatch) -> None:
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "playwright" or name.startswith("playwright."):
            raise AssertionError("raw default must not import playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    module = load_module()
    calls = []
    monkeypatch.setattr(module, "_detect_cdp", lambda: "http://localhost:9222")
    monkeypatch.setattr(module, "_raw_cp2", lambda cp2, key, cdp: calls.append((cp2, key, cdp)) or True)
    monkeypatch.setenv("CAPAFY_HOST_OPENROUTER_KEY", "raw-only-key")
    monkeypatch.setattr(sys, "argv", ["drive_checkpoint2.py", "https://capafy.ai/developer/createAgent?token=t&page=credential"])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 0
    assert calls and calls[0][2] == "http://localhost:9222"


def test_fresh_success_accepts_only_new_toast_or_url_transition() -> None:
    module = load_module()
    before = "https://capafy.ai/developer/createAgent?token=t&page=credential"
    assert module._fresh_success(before, ["キー確認済み"], before, "キー確認済み") is False
    assert module._fresh_success(before, [], before, "キー確認済み") is True
    assert module._fresh_success(before, [], before + "&page=credential-done", "") is True


def test_fallback_does_not_print_secret(capsys, monkeypatch) -> None:
    module = load_module()

    class _Chromium:
        def connect_over_cdp(self, *_args, **_kwargs):
            raise TimeoutError("attach")

    class _Playwright:
        chromium = _Chromium()

        def stop(self):
            pass

    class _Factory:
        def start(self):
            return _Playwright()

    monkeypatch.setattr(module, "_load_playwright", lambda: _Factory())
    monkeypatch.setattr(module, "_detect_cdp", lambda: "http://localhost:9222")
    monkeypatch.setattr(module, "_raw_cp2", lambda *_args: True)
    monkeypatch.setenv("CAPAFY_HOST_OPENROUTER_KEY", "do-not-print-secret")
    monkeypatch.setattr(sys, "argv", ["drive_checkpoint2.py", "https://capafy.ai/developer/createAgent?token=t&page=credential"])

    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 0
    assert "do-not-print-secret" not in capsys.readouterr().out
