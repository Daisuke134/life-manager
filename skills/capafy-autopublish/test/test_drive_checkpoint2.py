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

    assert module._resolve_cp2_url("https://api.capafy.ai/R123") == final
    assert seen == [("https://api.capafy.ai/R123", "HEAD")]


def test_short_cp2_url_rejects_unidentified_blank_new_agent_page(monkeypatch) -> None:
    # Regression: Agent 9466718786 resume (2026-09-28 06:52Z) -- the short
    # link's redirect degraded to a bare ?page=review with no source/token/
    # draftKey, which is Capafy's blank "create a new Agent" form, not the
    # existing draft. _validate_cp2_url alone (page value only) accepted it;
    # the driver must instead fail closed rather than fill in the wrong page.
    module = load_module()
    monkeypatch.setattr(module.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        module,
        "_single_redirect_location",
        lambda *_args: ["https://capafy.ai/developer/createAgent?page=review"],
    )

    with pytest.raises(RuntimeError, match="unidentified draft page"):
        module._resolve_cp2_url("https://api.capafy.ai/R123")


def test_short_cp2_url_retries_a_transient_unidentified_redirect(monkeypatch) -> None:
    # The same short link resolved correctly moments before and hours after
    # the 06:52Z failure (live-verified against Agent 9466718786's real
    # editLink on 2026-09-28) -- a transient degraded redirect, not a
    # permanently dead one. A retry that later sees the identified page must
    # succeed instead of failing closed on the first bad response.
    module = load_module()
    monkeypatch.setattr(module.time, "sleep", lambda *_a, **_k: None)
    final = "https://capafy.ai/developer/createAgent?source=temp-link&token=123&page=review"
    responses = iter([
        ["https://capafy.ai/developer/createAgent?page=review"],
        [final],
    ])
    monkeypatch.setattr(module, "_single_redirect_location", lambda *_args: next(responses))

    assert module._resolve_cp2_url("https://api.capafy.ai/R123") == final


def test_short_cp2_url_rejects_cross_domain_location(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(
        module,
        "_single_redirect_location",
        lambda *_args: ["https://evil.example/developer/createAgent?token=123&page=credential"],
    )

    with pytest.raises(RuntimeError, match="exact Capafy"):
        module._resolve_cp2_url("https://api.capafy.ai/R123")


def test_short_cp2_url_rejects_invalid_path() -> None:
    module = load_module()

    with pytest.raises(RuntimeError, match="exactly https://api.capafy.ai/R"):
        module._resolve_cp2_url("https://api.capafy.ai/not-a-short-url")


def test_short_cp2_url_rejects_the_old_c_prefix() -> None:
    # Regression: /C<digits> was the pattern this validator checked for until
    # 2026-09-28, but Capafy's actual review-page short link (both
    # publish-refresh-url --step publish and continue_upload's review_url) is
    # /R<digits> -- the exact prefix drive_checkpoint3.py (CP3) already uses for
    # the same review page (Agent 4243672453 live verification). A stray /C link
    # must still fail closed, just with the corrected message.
    module = load_module()

    with pytest.raises(RuntimeError, match="exactly https://api.capafy.ai/R"):
        module._resolve_cp2_url("https://api.capafy.ai/C123")


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
                {"ok": False, "reason": "llm-config-field-count"},
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
                {"ok": False, "reason": "llm-config-field-count"},
                {"ok": False},  # no Agent workspace tab on this page
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
                {"count": 0}, {"ok": False, "reason": "configured-proxy-field-count"},
                {"ok": False, "reason": "llm-config-field-count"}, {"ok": False},
                {"ok": False, "count": 0},
                {"count": 0}, {"ok": False, "reason": "configured-proxy-field-count"},
                {"ok": False, "reason": "llm-config-field-count"}, {"ok": True, "x": 10, "y": 20},
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


def test_provider_section_accepts_llm_config_form_layout() -> None:
    module = load_module()

    class _Page:
        def evaluate(self, expression):
            if "llm-config-field-count" in expression:
                return {"ok": True}
            return {"count": 0}

        def call(self, *_args, **_kwargs):
            pytest.fail("llm config form layout must not click the detected-keys button")

    assert module._ensure_raw_provider_section(_Page()) == "llm_config_form"


def test_provider_section_accepts_workspace_llm_form_layout() -> None:
    module = load_module()

    class _Page:
        def __init__(self):
            self.calls = []

        def evaluate(self, expression):
            if "workspace-llm-field-count" in expression:
                return {"ok": True}
            if "Agent ワークスペース" in expression:
                return {"ok": True, "x": 10, "y": 20}
            return {"count": 0}

        def call(self, method, params=None):
            self.calls.append((method, params))

    page = _Page()
    assert module._ensure_raw_provider_section(page) == "workspace_llm_form"
    assert [method for method, _ in page.calls] == [
        "Input.dispatchMouseEvent", "Input.dispatchMouseEvent"
    ]


def test_raw_configure_workspace_llm_writes_fields_and_saves() -> None:
    module = load_module()
    calls = []

    class _Page:
        def evaluate(self, expression):
            if "workspace-llm-field-count" in expression:
                return {"ok": True}
            if "workspace-save-count" in expression:
                return {"ok": True, "disabled": False, "x": 10, "y": 20}
            return {"ok": True}

        def call(self, method, params=None):
            calls.append((method, params))

    assert module._raw_configure_workspace_llm(_Page(), "test-secret") is True
    assert calls[:3] == [
        ("Input.insertText", {"text": module.BASE_URL}),
        ("Input.insertText", {"text": module.MODEL}),
        ("Input.insertText", {"text": "test-secret"}),
    ]
    assert [method for method, _ in calls[3:]] == [
        "Input.dispatchMouseEvent", "Input.dispatchMouseEvent"
    ]


def test_raw_configure_llm_form_writes_base_url_model_key_when_vendor_already_openrouter() -> None:
    module = load_module()
    focused = []
    calls = []

    class _Page:
        def evaluate(self, expression):
            if "llm-config-field-count" in expression:
                return {"ok": True}
            if "vendor-button-count" in expression:
                return {"ok": True, "text": "OpenRouter"}
            focused.append(expression)
            return {"ok": True}

        def call(self, method, params=None):
            calls.append((method, params))

    module._raw_configure_llm_form(_Page(), "test-secret")
    assert len(focused) == 3
    assert calls == [
        ("Input.insertText", {"text": module.BASE_URL}),
        ("Input.insertText", {"text": module.MODEL}),
        ("Input.insertText", {"text": "test-secret"}),
    ]


def test_raw_configure_llm_form_fails_closed_when_vendor_is_not_openrouter() -> None:
    module = load_module()

    class _Page:
        def evaluate(self, expression):
            if "llm-config-field-count" in expression:
                return {"ok": True}
            if "vendor-button-count" in expression:
                return {"ok": True, "text": "ベンダーを選択"}
            pytest.fail("must not write fields before the vendor guard passes")

        def call(self, *_args, **_kwargs):
            pytest.fail("must not click/write before the vendor guard passes")

    with pytest.raises(RuntimeError, match="not OpenRouter"):
        module._raw_configure_llm_form(_Page(), "test-secret")


def test_raw_configure_llm_form_rejects_ambiguous_field_counts() -> None:
    module = load_module()

    class _Page:
        def evaluate(self, _expression):
            return {"ok": False, "reason": "llm-config-field-count", "counts": [1, 2, 1, 1]}

        def call(self, *_args, **_kwargs):
            pytest.fail("ambiguous llm config form must not write")

    with pytest.raises(RuntimeError, match="ambiguous llm config"):
        module._raw_configure_llm_form(_Page(), "test-secret")


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


def test_provider_section_clicks_workspace_tab_once() -> None:
    module = load_module()
    module.RAW_SECTION_POLL_S = 0

    class _Page:
        def __init__(self):
            self.states = iter((
                {"count": 0}, {"ok": False}, {"ok": False}, {"ok": True, "x": 5, "y": 6},
                {"count": 1},
            ))
            self.calls = []

        def evaluate(self, _expression):
            return next(self.states)

        def call(self, method, params=None):
            self.calls.append((method, params["type"]))

    page = _Page()
    module.time.sleep, sleep = (lambda _s: None), module.time.sleep
    try:
        assert module._ensure_raw_provider_section(page) == "provider"
    finally:
        module.time.sleep = sleep
    assert page.calls == [("Input.dispatchMouseEvent", "mousePressed"),
                          ("Input.dispatchMouseEvent", "mouseReleased")]


def test_official_agent_model_requires_token_and_numeric_id(monkeypatch) -> None:
    module = load_module()
    monkeypatch.delenv("CAPAFY_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("must not call the API without a token"))
    assert module._official_agent_model("8123079349") is None

    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "t")
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("must not call the API for a non-numeric id"))
    assert module._official_agent_model("not-a-number") is None


def test_official_agent_model_returns_model_only_on_matching_agent_id(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "t")
    payload = {"code": 0, "data": {"agentId": "8123079349", "model": "DeepSeek V4.1 Flash"}}
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_a, **_k: _Response(payload))
    assert module._official_agent_model("8123079349") == "DeepSeek V4.1 Flash"
    assert module._official_agent_model("9466718786") is None


def test_official_agent_model_returns_none_on_network_or_json_error(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setenv("CAPAFY_ACCESS_TOKEN", "t")

    def boom(*_a, **_k):
        raise OSError("network down")

    monkeypatch.setattr(module.urllib.request, "urlopen", boom)
    assert module._official_agent_model("8123079349") is None


def test_verify_official_display_model_polls_until_match(monkeypatch) -> None:
    module = load_module()
    module.DISPLAY_MODEL_VERIFY_DELAY_S = 0
    values = iter(["Claude Sonnet 4.6", "Claude Sonnet 4.6", "DeepSeek V4.1 Flash"])
    monkeypatch.setattr(module, "_official_agent_model", lambda _id: next(values))
    assert module._verify_official_display_model("8123079349", "DeepSeek V4.1 Flash") is True


def test_verify_official_display_model_gives_up_after_retries(monkeypatch) -> None:
    module = load_module()
    module.DISPLAY_MODEL_VERIFY_TRIES = 2
    module.DISPLAY_MODEL_VERIFY_DELAY_S = 0
    monkeypatch.setattr(module, "_official_agent_model", lambda _id: "Claude Sonnet 4.6")
    assert module._verify_official_display_model("8123079349", "DeepSeek V4.1 Flash") is False


def test_raw_fix_display_model_is_a_noop_when_already_correct(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(module, "_verify_official_display_model", lambda *_a: True)

    class _Page:
        def evaluate(self, expression):
            if "display-model-combobox-count" in expression:
                return {"ok": True, "value": "DeepSeek V4.1 Flash"}
            if "no-agent-meta" in expression:
                return {"ok": True, "agentId": "8123079349"}
            pytest.fail(f"must not touch the DOM when already correct: {expression}")

        def call(self, *_a, **_k):
            pytest.fail("must not click/type when already correct")

    assert module._raw_fix_display_model(_Page(), "DeepSeek V4.1 Flash") is True


def test_raw_fix_display_model_selects_preset_and_saves() -> None:
    module = load_module()
    calls = []

    class _Page:
        def __init__(self):
            self._combo_value = "Claude Sonnet 4.6"

        def evaluate(self, expression):
            if "display-model-combobox-count" in expression:
                return {"ok": True, "value": self._combo_value}
            if "display-model-option-count" in expression:
                return {"ok": True, "x": 1, "y": 2}
            if "submit-button-count" in expression:
                # No finalReviewSubmitButton on this page state -- distinct
                # from a page where the tab already flipped to "submit".
                return {"ok": False, "reason": "submit-button-count", "count": 0}
            if "draft-save-count" in expression:
                return {"ok": True, "x": 3, "y": 4, "disabled": False}
            if "no-agent-meta" in expression:
                return {"ok": True, "agentId": "8123079349"}
            pytest.fail(f"unexpected evaluate: {expression}")

        def call(self, method, params=None):
            calls.append((method, params))
            if method == "Input.insertText":
                self._combo_value = params["text"]

    module.RAW_SECTION_POLL_S = 0
    module._verify_official_display_model = lambda *_a: True
    assert module._raw_fix_display_model(_Page(), "DeepSeek V4.1 Flash") is True
    assert ("Input.insertText", {"text": "DeepSeek V4.1 Flash"}) in calls
    assert ("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 3.0, "y": 4.0, "button": "left", "clickCount": 1}) in calls


def test_raw_fix_display_model_skips_save_when_tab_already_flipped_to_submit() -> None:
    """2026-09-29 regression (Agent 4973250899): once every tab is valid, the
    model combo's own commit can flip finalReviewSubmitButton's label from
    下書きを保存 to 審査に提出 before this function clicks anything -- the
    now-absent 下書きを保存 button then reads draft-save-count=0 and the old
    code raised 'ambiguous draft-save button' even though the model pick had
    already persisted. Must skip the click instead of raising."""
    module = load_module()
    calls = []

    class _Page:
        def __init__(self):
            self._combo_value = "Claude Sonnet 4.6"

        def evaluate(self, expression):
            if "display-model-combobox-count" in expression:
                return {"ok": True, "value": self._combo_value}
            if "display-model-option-count" in expression:
                return {"ok": True, "x": 1, "y": 2}
            if "submit-button-count" in expression:
                return {"ok": True, "label": "submit", "text": "審査に提出"}
            if "draft-save-count" in expression:
                pytest.fail("must not query the absent draft-save button once the tab is valid")
            if "no-agent-meta" in expression:
                return {"ok": True, "agentId": "8123079349"}
            pytest.fail(f"unexpected evaluate: {expression}")

        def call(self, method, params=None):
            calls.append((method, params))
            if method == "Input.insertText":
                self._combo_value = params["text"]

    module.RAW_SECTION_POLL_S = 0
    module._verify_official_display_model = lambda *_a: True
    assert module._raw_fix_display_model(_Page(), "DeepSeek V4.1 Flash") is True
    assert ("Input.insertText", {"text": "DeepSeek V4.1 Flash"}) in calls
    assert ("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 1.0, "y": 2.0, "button": "left", "clickCount": 1}) in calls
    assert not any(m == "Input.dispatchMouseEvent" and p.get("x") == 3.0 for m, p in calls)


def test_raw_fix_display_model_fails_closed_without_a_matching_preset() -> None:
    module = load_module()
    module.RAW_SECTION_TIMEOUT_S = 0.01
    module.RAW_SECTION_POLL_S = 0.001

    class _Page:
        def evaluate(self, expression):
            if "display-model-combobox-count" in expression:
                return {"ok": True, "value": ""}
            if "display-model-option-count" in expression:
                return {"ok": False, "reason": "display-model-option-count", "count": 0}
            pytest.fail(f"unexpected evaluate: {expression}")

        def call(self, *_a, **_k):
            pass

    with pytest.raises(RuntimeError, match="no exact preset option"):
        module._raw_fix_display_model(_Page(), "Some Unknown Model")


def test_raw_cp2_falls_back_to_display_model_fix_when_hosted_key_already_configured(monkeypatch) -> None:
    module = load_module()

    def raise_hydrate_timeout(_page):
        raise RuntimeError("provider path and detected-keys button did not hydrate before deadline")

    monkeypatch.setattr(module, "_raw_page_targets", lambda *_a: [{"webSocketDebuggerUrl": "ws://127.0.0.1:1/x"}])
    monkeypatch.setattr(module, "_open_responsive_page", lambda _targets: _FakePage())
    monkeypatch.setattr(module, "_wait_raw_navigation", lambda *_a: None)
    monkeypatch.setattr(module, "_ensure_raw_provider_section", raise_hydrate_timeout)
    monkeypatch.setattr(module, "_raw_configure_hosted_key", lambda *_a: pytest.fail("must not fill an already-configured card"))
    monkeypatch.setenv("CAPAFY_DISPLAY_MODEL", "DeepSeek V4.1 Flash")
    fix_calls = []
    monkeypatch.setattr(module, "_raw_fix_display_model", lambda _page, model: fix_calls.append(model) or True)

    assert module._raw_cp2("https://capafy.ai/developer/createAgent?token=t&page=review", "secret", "http://localhost:9222") is True
    assert fix_calls == ["DeepSeek V4.1 Flash"]


_LISTING_MD = """Primary Model: DeepSeek V4.1 Flash · category: マーケティング · tags: a, b, c

| cycle | price | cap | trial |
|---|---:|---|---|
| week | $3.99 | 40 | Free Trial 24h / 3 requests |

## Title
Ad Hook Lab

## shortDescription
Short.

## welcomeMessage
Hi, I write hooks. Example: "A $49/month meal-planning app."

## detailedDescription
Detailed body.
"""


def test_parse_listing_conversation_fields_extracts_welcome_and_example(tmp_path) -> None:
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(_LISTING_MD, encoding="utf-8")

    welcome, test_input = module._parse_listing_conversation_fields(str(listing))
    assert welcome == 'Hi, I write hooks. Example: "A $49/month meal-planning app."'
    assert test_input == "A $49/month meal-planning app."


def test_parse_listing_conversation_fields_returns_none_for_missing_file() -> None:
    module = load_module()
    welcome, test_input = module._parse_listing_conversation_fields("/no/such/LISTING.md")
    assert welcome is None
    assert test_input is None


def test_raw_fill_workspace_conversation_fields_fills_only_empty_fields_and_saves(tmp_path) -> None:
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(_LISTING_MD, encoding="utf-8")
    calls = []

    class _Page:
        def evaluate(self, expression):
            if "role=tab" in expression or "Agent Workspace" in expression:
                return {"ok": False}
            if "workspace-field-count" in expression:
                if "資料整理アシスタントです" in expression:
                    return {"ok": True, "value": ""}
                if "画像をアップロードして希望する結果を説明する" in expression:
                    return {"ok": True, "value": "already set"}
                if "韻を踏んだキャッチーな広告コピー" in expression:
                    return {"ok": True, "value": ""}
                if "たくさん買って" in expression:
                    return {"ok": True, "value": ""}
                if "OpenAI" in expression and "Anthropic" in expression:
                    return {"ok": True, "value": ""}
            if "workspace-focus-count" in expression:
                return {"ok": True}
            if "dpa-checkbox-count" in expression:
                return {"ok": True, "checked": False, "x": 5, "y": 6}
            if "submit-button-count" in expression:
                return {"ok": True, "label": "draft", "text": "下書きを保存"}
            if "draft-save-count" in expression:
                return {"ok": True, "x": 3, "y": 4, "disabled": False}
            pytest.fail(f"unexpected evaluate: {expression}")

        def call(self, method, params=None):
            calls.append((method, params))

        def press_enter(self):
            calls.append(("press_enter", None))

    assert module._raw_fill_workspace_conversation_fields(_Page(), str(listing)) is True
    inserted = [p["text"] for (m, p) in calls if m == "Input.insertText"]
    assert inserted.count('Hi, I write hooks. Example: "A $49/month meal-planning app."') == 1
    assert inserted.count("A $49/month meal-planning app.") == 2  # test_case_1 + test_case_2
    assert inserted.count("openrouter.ai") == 1
    assert ("press_enter", None) in calls
    assert ("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 3.0, "y": 4.0, "button": "left", "clickCount": 1}) in calls
    assert ("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 5.0, "y": 6.0, "button": "left", "clickCount": 1}) in calls


def test_raw_fill_workspace_conversation_fields_checks_dpa_checkbox_even_when_text_fields_are_filled(tmp_path) -> None:
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(_LISTING_MD, encoding="utf-8")
    calls = []

    class _Page:
        def evaluate(self, expression):
            if "role=tab" in expression or "Agent Workspace" in expression:
                return {"ok": False}
            if "workspace-field-count" in expression:
                return {"ok": True, "value": "already set"}
            if "dpa-checkbox-count" in expression:
                return {"ok": True, "checked": False, "x": 5, "y": 6}
            if "submit-button-count" in expression:
                return {"ok": True, "label": "draft", "text": "下書きを保存"}
            if "draft-save-count" in expression:
                return {"ok": True, "x": 3, "y": 4, "disabled": False}
            pytest.fail(f"unexpected evaluate: {expression}")

        def call(self, method, params=None):
            calls.append((method, params))

    assert module._raw_fill_workspace_conversation_fields(_Page(), str(listing)) is True
    assert ("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 5.0, "y": 6.0, "button": "left", "clickCount": 1}) in calls
    assert ("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 3.0, "y": 4.0, "button": "left", "clickCount": 1}) in calls


def test_raw_fill_workspace_conversation_fields_never_clicks_an_already_submit_labeled_button(tmp_path) -> None:
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(_LISTING_MD, encoding="utf-8")

    class _Page:
        def evaluate(self, expression):
            if "role=tab" in expression or "Agent Workspace" in expression:
                return {"ok": False}
            if "workspace-field-count" in expression:
                return {"ok": True, "value": "already set"}
            if "dpa-checkbox-count" in expression:
                return {"ok": True, "checked": False, "x": 5, "y": 6}
            if "submit-button-count" in expression:
                return {"ok": True, "label": "submit", "text": "審査に提出"}
            pytest.fail(f"must not look for the draft-save button once labelled submit: {expression}")

        def call(self, method, params=None):
            if method == "Input.dispatchMouseEvent":
                assert (params["x"], params["y"]) == (5.0, 6.0), "must only click the DPA checkbox, never the submit button"

    assert module._raw_fill_workspace_conversation_fields(_Page(), str(listing)) is True


def test_raw_fill_workspace_conversation_fields_leaves_checked_dpa_checkbox_alone(tmp_path) -> None:
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(_LISTING_MD, encoding="utf-8")

    class _Page:
        def evaluate(self, expression):
            if "role=tab" in expression or "Agent Workspace" in expression:
                return {"ok": False}
            if "workspace-field-count" in expression:
                return {"ok": True, "value": "already set"}
            if "dpa-checkbox-count" in expression:
                return {"ok": True, "checked": True, "x": 5, "y": 6}
            pytest.fail(f"unexpected evaluate: {expression}")

        def call(self, *_a, **_k):
            pytest.fail("must not click anything when nothing needs filling/checking")

    assert module._raw_fill_workspace_conversation_fields(_Page(), str(listing)) is True


def test_raw_fill_workspace_conversation_fields_is_noop_when_all_filled(tmp_path) -> None:
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(_LISTING_MD, encoding="utf-8")

    class _Page:
        def evaluate(self, expression):
            if "role=tab" in expression or "Agent Workspace" in expression:
                return {"ok": False}
            if "workspace-field-count" in expression:
                return {"ok": True, "value": "already set"}
            if "dpa-checkbox-count" in expression:
                return {"ok": True, "checked": True, "x": 5, "y": 6}
            pytest.fail(f"must not focus/save when already filled: {expression}")

        def call(self, *_a, **_k):
            pytest.fail("must not click/type when already filled")

    assert module._raw_fill_workspace_conversation_fields(_Page(), str(listing)) is True


def test_raw_fill_workspace_conversation_fields_returns_false_when_listing_unparsable() -> None:
    module = load_module()

    class _Page:
        def evaluate(self, *_a, **_k):
            pytest.fail("must not touch the DOM when LISTING can't be parsed")

        def call(self, *_a, **_k):
            pytest.fail("must not touch the DOM when LISTING can't be parsed")

    assert module._raw_fill_workspace_conversation_fields(_Page(), "/no/such/LISTING.md") is False


def test_raw_cp2_runs_workspace_fields_fix_via_listing_path_env(monkeypatch, tmp_path) -> None:
    module = load_module()
    listing = tmp_path / "LISTING.md"
    listing.write_text(_LISTING_MD, encoding="utf-8")

    def raise_hydrate_timeout(_page):
        raise RuntimeError("provider path and detected-keys button did not hydrate before deadline")

    monkeypatch.setattr(module, "_raw_page_targets", lambda *_a: [{"webSocketDebuggerUrl": "ws://127.0.0.1:1/x"}])
    monkeypatch.setattr(module, "_open_responsive_page", lambda _targets: _FakePage())
    monkeypatch.setattr(module, "_wait_raw_navigation", lambda *_a: None)
    monkeypatch.setattr(module, "_ensure_raw_provider_section", raise_hydrate_timeout)
    monkeypatch.setattr(module, "_raw_configure_hosted_key", lambda *_a: pytest.fail("must not fill an already-configured card"))
    monkeypatch.setenv("CAPAFY_LISTING_PATH", str(listing))
    workspace_calls = []
    monkeypatch.setattr(
        module, "_raw_fill_workspace_conversation_fields",
        lambda _page, path: workspace_calls.append(path) or True,
    )

    assert module._raw_cp2("https://capafy.ai/developer/createAgent?token=t&page=review", "secret", "http://localhost:9222") is True
    assert workspace_calls == [str(listing)]


class _FakePage:
    def call(self, *_a, **_k):
        return {}

    def close(self):
        pass
