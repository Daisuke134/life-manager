"""Regression coverage for CP1's raw-CDP tab bootstrap."""
import importlib.util
import json
from pathlib import Path
import pytest
import sys


SCRIPTS = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "cp1_agent.py"
SPEC = importlib.util.spec_from_file_location("cp1_agent_under_test", SCRIPT)
cp1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cp1)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_raw_open_creates_a_dedicated_target_when_no_capafy_page_exists(monkeypatch):
    created = {}
    expected_url = "https://capafy.ai/developer/createAgent?draftKey=draft-key-1&page=edit"
    target = {"webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/new"}

    def no_target(*_):
        raise RuntimeError("no existing Capafy createAgent page target")

    def urlopen(request, timeout):
        created["method"] = request.get_method()
        created["url"] = request.full_url
        created["timeout"] = timeout
        return _Response(target)

    sentinel = object()
    monkeypatch.setattr(cp1, "_raw_capafy_page", no_target)
    monkeypatch.setattr(cp1.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(cp1, "_raw_page_from_target", lambda got: sentinel if got == target else None)

    assert cp1._raw_open_page("http://localhost:9222", expected_url) is sentinel
    assert created["method"] == "PUT"
    assert "json/new?https%3A%2F%2Fcapafy.ai%2Fdeveloper%2FcreateAgent" in created["url"]
    assert created["timeout"] == 8


def test_raw_open_creates_a_dedicated_target_for_official_short_review_url(monkeypatch):
    created = {}
    expected_url = "https://api.capafy.ai/E1234567890123456789"
    target = {"webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/short"}

    def no_target(*_):
        raise RuntimeError("no existing Capafy createAgent page target")

    def urlopen(request, timeout):
        created["method"] = request.get_method()
        created["url"] = request.full_url
        created["timeout"] = timeout
        return _Response(target)

    sentinel = object()
    monkeypatch.setattr(cp1, "_raw_capafy_page", no_target)
    monkeypatch.setattr(cp1.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(cp1, "_raw_page_from_target", lambda got: sentinel if got == target else None)

    assert cp1._raw_open_page("http://localhost:9222", expected_url) is sentinel
    assert created["method"] == "PUT"
    assert "json/new?https%3A%2F%2Fapi.capafy.ai%2FE1234567890123456789" in created["url"]
    assert created["timeout"] == 8


@pytest.mark.parametrize(
    "url",
    (
        "http://api.capafy.ai/E1234567890123456789",
        "https://api.capafy.ai:443/E1234567890123456789",
        "https://user@api.capafy.ai/E1234567890123456789",
        "https://api.capafy.ai/E1234567890123456789?x=1",
        "https://api.capafy.ai/E1234567890123456789#fragment",
        "https://api.capafy.ai/e1234567890123456789",
        "https://api.capafy.ai/Eabcdefghijklmnopqrs",
        "https://api.capafy.ai/E123456789012345678",
        "https://api.capafy.ai/E12345678901234567890",
        "https://api.capafy.ai/E1234567890123456789/extra",
    ),
)
def test_raw_create_rejects_invalid_short_review_url_before_urlopen(monkeypatch, url):
    calls = []

    def urlopen(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("invalid short URL must not reach CDP urlopen")

    monkeypatch.setattr(cp1.urllib.request, "urlopen", urlopen)

    with pytest.raises(RuntimeError, match="safe Capafy edit URL"):
        cp1._raw_create_capafy_target("http://localhost:9222", url)

    assert calls == []


def test_raw_open_does_not_create_a_tab_for_an_unrelated_renderer_failure(monkeypatch):
    monkeypatch.setattr(cp1, "_raw_capafy_page", lambda *_: (_ for _ in ()).throw(RuntimeError("CDP call timeout")))
    monkeypatch.setattr(cp1, "_raw_create_capafy_target", lambda *_: (_ for _ in ()).throw(AssertionError("must not create")))

    try:
        cp1._raw_open_page("http://localhost:9222", "https://capafy.ai/developer/createAgent?draftKey=draft-key-1&page=edit")
    except RuntimeError as exc:
        assert str(exc) == "CDP call timeout"
    else:
        raise AssertionError("expected original renderer error")


def test_raw_open_rejects_invalid_url_before_page_selection(monkeypatch):
    calls = []
    invalid_url = "https://api.capafy.ai/E1234567890123456789?invalid=1"

    monkeypatch.setattr(cp1, "_raw_capafy_page", lambda *_: calls.append("page"))
    monkeypatch.setattr(cp1, "_raw_create_capafy_target", lambda *_: calls.append("create"))

    with pytest.raises(RuntimeError, match="safe Capafy edit URL"):
        cp1._raw_open_page("http://localhost:9222", invalid_url)

    assert calls == []


def test_main_rejects_invalid_open_before_backend_connect_or_navigation(monkeypatch, capsys):
    calls = []
    invalid_url = "https://api.capafy.ai/E1234567890123456789#invalid"

    monkeypatch.setattr(cp1, "_acquire_cdp_lock", lambda: calls.append("lock"))
    monkeypatch.setattr(cp1, "sync_playwright", lambda: calls.append("connect"))
    monkeypatch.setattr(cp1, "raw_main", lambda *_: calls.append("raw"))
    monkeypatch.setattr(sys, "argv", ["cp1_agent.py", "open", invalid_url])

    with pytest.raises(SystemExit) as exc:
        cp1.main()

    assert exc.value.code == 1
    assert calls == []
    assert invalid_url not in capsys.readouterr().out


@pytest.mark.parametrize(
    "url",
    (
        "https://capafy.ai/developer/createAgent?draftKey=secret-draft&page=edit#secret-fragment",
        "https://capafy.ai/developer/createAgent?source=temp-link&token=123456789&page=review",
    ),
)
def test_state_dump_and_toast_redact_query_and_fragment(url, capsys):
    state = {
        "url": url,
        "toastOK": True,
        "cardDone": False,
        "priceSvg": "",
    }

    class _Page:
        def evaluate(self, _expression):
            return state

    page = _Page()
    cp1.dump(page, shot=False)
    cp1._raw_dump(page, shot=False)
    print(json.dumps(cp1._toast_for_output(state), ensure_ascii=False))
    output = capsys.readouterr().out
    assert "secret-draft" not in output
    assert "secret-fragment" not in output
    assert "token=123456789" not in output
    assert "?page=edit" in output or "?page=review" in output


def test_build_state_js_embeds_expected_model_as_safe_json_literal(monkeypatch):
    monkeypatch.setenv("CP1_EXPECTED_MODEL", 'DeepSeek "V4.1" Flash')
    js = cp1._build_state_js()
    assert 'const EXPECTED_MODEL = "DeepSeek \\"V4.1\\" Flash";' in js
    # Injection must stay inside the JSON string literal, never break out of it.
    assert 'Flash";alert' not in js


def test_build_state_js_defaults_to_null_when_env_unset(monkeypatch):
    monkeypatch.delenv("CP1_EXPECTED_MODEL", raising=False)
    js = cp1._build_state_js()
    assert "const EXPECTED_MODEL = null;" in js


def test_build_state_js_blank_env_also_defaults_to_null(monkeypatch):
    monkeypatch.setenv("CP1_EXPECTED_MODEL", "   ")
    js = cp1._build_state_js()
    assert "const EXPECTED_MODEL = null;" in js


def test_module_level_state_js_is_the_built_template():
    # STATE_JS is what dump()/_raw_dump() actually evaluate; it must be the
    # rendered template (placeholder substituted), not the raw template string.
    assert "__EXPECTED_MODEL_JSON__" not in cp1.STATE_JS
    assert "modelSelected" in cp1.STATE_JS
    assert "modelDropdownVisible" in cp1.STATE_JS


def test_state_dump_and_toast_redact_short_link_path(capsys):
    short_url = "https://api.capafy.ai/E1234567890123456789"
    state = {
        "url": short_url,
        "toastOK": True,
        "cardDone": False,
        "priceSvg": "",
    }

    class _Page:
        def evaluate(self, _expression):
            return state

    page = _Page()
    cp1.dump(page, shot=False)
    cp1._raw_dump(page, shot=False)
    print(json.dumps(cp1._toast_for_output(state), ensure_ascii=False))
    output = capsys.readouterr().out
    assert short_url not in output
    assert "api.capafy.ai/<redacted-short-link>" in output


def test_price_gate_reads_japanese_period_labels():
    # 2026-10-07: the Capafy console rendered 週次/月次 after a Japanese-locale
    # login and the gate reported every plan as missing.
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "cp1_agent_ja", pathlib.Path(__file__).parents[1] / "scripts" / "cp1_agent.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    plans = [{"cycle": "week", "price": "9.99", "cap": 15, "trial": None},
             {"cycle": "month", "price": "24.99", "cap": 35, "trial": None}]
    cards = [{"period": "週次", "price": "9.99", "cap": "15", "trial": None},
             {"period": "月次", "price": "24.99", "cap": "35", "trial": None}]
    assert m.compare_price_cards(plans, cards) == []
