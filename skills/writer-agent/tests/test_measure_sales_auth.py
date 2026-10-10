from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import os
import sys
from types import SimpleNamespace
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure-sales.py"
SPEC = importlib.util.spec_from_file_location("writer_measure_sales", SCRIPT)
measure = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(measure)


def completed(payload: dict) -> subprocess.CompletedProcess[str]:
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return subprocess.CompletedProcess([], 0, stdout=f"PAYLOAD_B64:{encoded}\n", stderr="")


def test_note_driver_recovers_the_ordinary_login_form(monkeypatch):
    captured = {}

    def fake(script: str, timeout: int = 90, **kwargs):
        captured["script"] = script
        return completed({
            "sales_url": "https://note.com/dashboard/salesmanage",
            "sales_body": "今月の売上\n総額\n¥0",
            "purchases_url": "https://note.com/dashboard/sales",
            "purchases_body": "2026年10月は購入者がいません",
            "stats_url": "https://note.com/sitesettings/stats",
            "stats_pages": [],
        })

    monkeypatch.setattr(measure, "run_browser_script", fake)
    assert "payload" in measure.measure_note_pages(9222)
    assert 'input[name="login"]' in captured["script"]
    assert 'input[name="password"]' in captured["script"]
    assert "NOTE_EMAIL" in captured["script"]
    assert "'ログイン'" in captured["script"]


def test_substack_driver_injects_the_existing_session_cookie(monkeypatch):
    captured = {}

    def fake(script: str, timeout: int = 90, **kwargs):
        captured["script"] = script
        return completed({
            "home_url": "https://aniccabuddha.substack.com/publish/home",
            "home_body": "有料登録者\n-\n0から",
            "earnings_url": "https://aniccabuddha.substack.com/publish/stats/earnings",
            "earnings_body": "-\n支払いを受け取るようになると、収益がここに表示されます",
        })

    monkeypatch.setenv("SUBSTACK_PUBLICATION_JA", "aniccabuddha.substack.com")
    monkeypatch.setattr(measure, "run_browser_script", fake)
    assert "payload" in measure.measure_substack_pages(9222)
    assert "SUBSTACK_SESSION_COOKIE" in captured["script"]
    assert "Storage.setCookies" in captured["script"]
    assert "browserContextId" in captured["script"]
    assert "ctx.new_page" not in captured["script"]
    assert "b.new_context" not in captured["script"]

@pytest.mark.parametrize("outcome", ("success", "failure", "timeout"))
def test_parent_releases_exact_measurement_context_even_when_child_cannot_cleanup(monkeypatch, outcome):
    events = []
    lease = {"ok": True, "context_id": "own-context", "target_id": "own-target",
             "token": "owned-lease", "generation": 4}
    def acquire(owner, url="about:blank"):
        events.append(("acquire", owner, url))
        assert os.environ["AI_BROWSER_HOLDER_PID"] == str(os.getpid())
        return lease
    def release(owner, **fence):
        events.append(("release", owner, fence))
        return {"ok": True}
    monkeypatch.setattr(measure, "_load_context_lease", lambda: SimpleNamespace(
        acquire=acquire, release=release), raising=False)
    monkeypatch.setattr(measure, "VENV_CLOAK_PYTHON", sys.executable)
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", "http://preserved:9000")
    def child(*args, **kwargs):
        events.append(("child",))
        assert kwargs["env"]["WRITER_LEASED_CONTEXT_ID"] == "own-context"
        assert kwargs["env"]["WRITER_LEASED_TARGET_ID"] == "own-target"
        if outcome == "timeout":
            raise subprocess.TimeoutExpired("fixture", 90)
        return subprocess.CompletedProcess([], 0 if outcome == "success" else 23, "", "")
    monkeypatch.setattr(measure.subprocess, "run", child)
    if outcome == "timeout":
        with pytest.raises(subprocess.TimeoutExpired):
            measure.run_browser_script("fixture")
    else:
        assert measure.run_browser_script("fixture").returncode == (0 if outcome == "success" else 23)
    assert [event[0] for event in events] == ["acquire", "child", "release"]
    assert events[-1][2] == {"token": "owned-lease", "generation": 4}
    assert os.environ["CLOAK_CDP_BASE_URL"] == "http://preserved:9000"


def test_measurement_context_admission_failure_never_starts_child(monkeypatch):
    monkeypatch.setattr(measure, "_load_context_lease", lambda: SimpleNamespace(
        acquire=lambda *_args, **_kwargs: {"ok": False, "reason": "browser_context_limit"}), raising=False)
    monkeypatch.setattr(measure, "VENV_CLOAK_PYTHON", sys.executable)
    calls = []
    monkeypatch.setattr(measure.subprocess, "run", lambda *_args, **_kwargs: calls.append(True))
    with pytest.raises(RuntimeError, match="context admission failed"):
        measure.run_browser_script("fixture")
    assert calls == []


def test_cleanup_pending_is_reported_without_losing_the_existing_tombstone(monkeypatch):
    lease = {"ok": True, "context_id": "own-context", "target_id": "own-target",
             "token": "owned-lease", "generation": 4}
    monkeypatch.setattr(measure, "_load_context_lease", lambda: SimpleNamespace(
        acquire=lambda *_args, **_kwargs: lease,
        release=lambda *_args, **_kwargs: {"ok": True, "cleanup_pending": True}))
    monkeypatch.setattr(measure, "VENV_CLOAK_PYTHON", sys.executable)
    monkeypatch.setattr(measure.subprocess, "run", lambda *_args, **_kwargs:
                        subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setenv("CLOAK_CDP_BASE_URL", "http://preserved:9000")
    with pytest.raises(RuntimeError, match="cleanup remains pending"):
        measure.run_browser_script("fixture")
    assert os.environ["CLOAK_CDP_BASE_URL"] == "http://preserved:9000"


@pytest.mark.parametrize("matching", (True, False))
def test_substack_uses_only_the_leased_target_and_context_for_session_cookie(monkeypatch, matching):
    import types
    import time
    captured = {}
    def capture(script, **kwargs):
        captured["script"] = script
        return completed({"home_url": "https://fixture.substack.com/publish/home",
                          "home_body": "-", "earnings_url": "https://fixture.substack.com/publish/stats/earnings",
                          "earnings_body": "-"})
    monkeypatch.setattr(measure, "run_browser_script", capture)
    monkeypatch.setenv("SUBSTACK_PUBLICATION_JA", "fixture.substack.com")
    measure.measure_substack_pages(9222)
    monkeypatch.setenv("WRITER_LEASED_TARGET_URL", "about:blank#owned")
    monkeypatch.setenv("WRITER_LEASED_TARGET_ID", "owned-target")
    monkeypatch.setenv("WRITER_LEASED_CONTEXT_ID", "owned-context")
    monkeypatch.setenv("SUBSTACK_SESSION_COOKIE_JA", "session=synthetic-fixture")
    calls = []
    class Session:
        def send(self, method, params=None):
            calls.append((method, params))
            if method == "Target.getTargetInfo":
                return {"targetInfo": {"targetId": "owned-target", "browserContextId":
                    "owned-context" if matching else "foreign-context"}}
            return {}
        def detach(self):
            pass
    page = SimpleNamespace(url="about:blank#owned", goto=lambda url, **kw: setattr(page, "url", url),
        evaluate=lambda *_: "-", close=lambda: calls.append(("close-owned", None)))
    foreign = SimpleNamespace(url="https://foreign.invalid")
    def new_session(selected):
        assert selected is page
        return Session()
    context = SimpleNamespace(pages=[foreign, page], new_cdp_session=new_session)
    page.context = context
    browser = SimpleNamespace(contexts=[context], new_browser_cdp_session=Session)
    api = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=lambda *_: browser))
    package = types.ModuleType("playwright")
    sync = types.ModuleType("playwright.sync_api")
    sync.sync_playwright = lambda: SimpleNamespace(start=lambda: api)
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    if not matching:
        with pytest.raises(RuntimeError, match="identity mismatch"):
            exec(captured["script"], {})
        assert not any(method in {"Storage.setCookies", "close-owned"} for method, _ in calls)
    else:
        exec(captured["script"], {})
        cookie_calls = [params for method, params in calls if method == "Storage.setCookies"]
        assert len(cookie_calls) == 1 and cookie_calls[0]["browserContextId"] == "owned-context"
        assert calls[-1][0] == "close-owned"
    assert foreign.url == "https://foreign.invalid"
