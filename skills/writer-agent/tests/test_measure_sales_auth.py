from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import os
import stat
import sys
import time
import types
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


NOTE_PAYLOAD = {
    "sales_url": "https://note.com/dashboard/salesmanage",
    "sales_body": "今月の売上\n総額\n¥0",
    "purchases_url": "https://note.com/dashboard/sales",
    "purchases_body": "2026年10月は購入者がいません",
    "stats_url": "https://note.com/sitesettings/stats",
    "stats_pages": [],
}


@pytest.fixture
def note_files(tmp_path, monkeypatch):
    storage = tmp_path / "writer/note-measure-storage.json"
    backoff = tmp_path / "writer/note-measure-login-backoff.json"
    monkeypatch.setattr(measure, "NOTE_STORAGE_STATE", storage)
    monkeypatch.setattr(measure, "NOTE_LOGIN_BACKOFF", backoff)
    return storage, backoff


def test_measurement_source_cannot_reach_any_shared_browser():
    source = SCRIPT.read_text()
    for forbidden in ("92" "22", "interactive:dais", "daily-driver", "connect_over_cdp", "cdp_context_lease"):
        assert forbidden not in source


def test_note_driver_recovers_the_ordinary_login_form(monkeypatch, note_files):
    captured = {}

    def fake(script: str, timeout: int = 90, **kwargs):
        captured["script"] = script
        return completed(NOTE_PAYLOAD)

    monkeypatch.setattr(measure, "run_browser_script", fake)
    assert "payload" in measure.measure_note_pages()
    assert 'input[name="login"]' in captured["script"]
    assert 'input[name="password"]' in captured["script"]
    assert "NOTE_EMAIL" in captured["script"]
    assert "'ログイン'" in captured["script"]
    assert "launch_context(" in captured["script"]


class FakeNotePage:
    def __init__(self, logged_in: bool, login_works: bool):
        self.logged_in, self.login_works = logged_in, login_works
        self.url, self.filled = "about:blank", {}

    def goto(self, url, **_kwargs):
        self.url = url

    def locator(self, selector):
        count = int(selector == 'input[name="login"]' and not self.logged_in)
        return SimpleNamespace(count=lambda: count)

    def fill(self, selector, value):
        self.filled[selector] = value

    def evaluate(self, script):
        if "'ログイン'" in script:
            self.logged_in = self.login_works
            return None
        if "/api/v1/stats/pv" in script:
            return [{"last_page": True, "note_stats": []}]
        return "body"


def run_note_script(monkeypatch, note_files, *, logged_in: bool, login_works: bool = True):
    captured, launches, events = {}, [], []
    monkeypatch.setattr(measure, "run_browser_script",
                        lambda script, **_kw: captured.setdefault("script", script) and completed(NOTE_PAYLOAD))
    measure.measure_note_pages()
    page = FakeNotePage(logged_in, login_works)

    def launch_context(**kwargs):
        launches.append(kwargs)
        return SimpleNamespace(
            new_page=lambda: page,
            storage_state=lambda: {"cookies": [{"name": "_note_session_v5", "value": "synthetic",
                                                "domain": ".note.com", "path": "/"}], "origins": []},
            close=lambda: events.append("closed"),
        )

    module = types.ModuleType("cloakbrowser")
    module.launch_context = launch_context
    monkeypatch.setitem(sys.modules, "cloakbrowser", module)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    monkeypatch.setenv("NOTE_EMAIL", "writer@example.invalid")
    monkeypatch.setenv("NOTE_PASSWORD", "synthetic-password")
    return captured["script"], page, launches, events


def test_successful_login_persists_a_private_note_session(monkeypatch, note_files, capsys):
    storage, _backoff = note_files
    script, page, launches, events = run_note_script(monkeypatch, note_files, logged_in=False)
    exec(script, {})
    assert page.filled['input[name="login"]'] == "writer@example.invalid"
    assert launches == [{"headless": True, "humanize": False}]
    assert json.loads(storage.read_text())["cookies"][0]["name"] == "_note_session_v5"
    assert stat.S_IMODE(storage.stat().st_mode) == 0o600
    assert events == ["closed"]
    assert "PAYLOAD_B64:" in capsys.readouterr().out


def test_saved_note_session_is_reused_without_logging_in(monkeypatch, note_files):
    storage, _backoff = note_files
    storage.parent.mkdir(parents=True)
    storage.write_text(json.dumps({"cookies": [], "origins": []}))
    script, page, launches, events = run_note_script(monkeypatch, note_files, logged_in=True)
    exec(script, {})
    assert launches == [{"headless": True, "humanize": False, "storage_state": str(storage)}]
    assert page.filled == {}
    assert events == ["closed"]


def test_failed_login_keeps_the_old_session_and_closes_the_browser(monkeypatch, note_files, capsys):
    storage, _backoff = note_files
    script, _page, _launches, events = run_note_script(
        monkeypatch, note_files, logged_in=False, login_works=False)
    with pytest.raises(SystemExit):
        exec(script, {})
    assert "NOTE_LOGIN_FAILED" in capsys.readouterr().out
    assert not storage.exists()
    assert events == ["closed"]


def test_note_login_failure_backs_off_for_a_day(monkeypatch, note_files):
    _storage, backoff = note_files
    calls = []

    def failed(script, **_kwargs):
        calls.append(script)
        return subprocess.CompletedProcess([], 1, stdout="NOTE_LOGIN_FAILED\n", stderr="")

    monkeypatch.setattr(measure, "run_browser_script", failed)
    assert "did not reach" in measure.measure_note_pages()["error"]
    assert stat.S_IMODE(backoff.stat().st_mode) == 0o600
    skipped = measure.measure_note_pages()
    assert "backoff" in skipped["error"] and len(calls) == 1
    stale = time.time() - measure.NOTE_LOGIN_BACKOFF_SECONDS - 60
    os.utime(backoff, (stale, stale))
    monkeypatch.setattr(measure, "run_browser_script", lambda script, **_kw: completed(NOTE_PAYLOAD))
    assert "payload" in measure.measure_note_pages()
    assert not backoff.exists()


def substack_script(monkeypatch, lang="ja"):
    captured = {}

    def fake(script: str, timeout: int = 90, **kwargs):
        captured["script"] = script
        return completed({"home_url": "", "home_body": "", "earnings_url": "", "earnings_body": ""})

    monkeypatch.setenv("SUBSTACK_PUBLICATION_JA", "aniccabuddha.substack.com")
    monkeypatch.setenv("SUBSTACK_PUBLICATION_EN", "aniccaai2026.substack.com")
    monkeypatch.setattr(measure, "run_browser_script", fake)
    assert "payload" in measure.measure_substack_pages(lang)
    return captured["script"]


@pytest.mark.parametrize("cookie", ("session=synthetic-fixture", ""))
def test_substack_cookie_goes_only_into_its_own_ephemeral_context(monkeypatch, cookie, capsys):
    script = substack_script(monkeypatch)
    monkeypatch.setenv("SUBSTACK_SESSION_COOKIE_JA", cookie)
    monkeypatch.delenv("SUBSTACK_SESSION_COOKIE", raising=False)
    events = []
    page = SimpleNamespace(url="about:blank", goto=lambda url, **kw: setattr(page, "url", url),
                           evaluate=lambda *_: "-")

    def launch_context(**kwargs):
        events.append(("launch", kwargs))
        return SimpleNamespace(add_cookies=lambda cookies: events.append(("cookies", cookies)),
                               new_page=lambda: page, close=lambda: events.append(("close", None)))

    module = types.ModuleType("cloakbrowser")
    module.launch_context = launch_context
    monkeypatch.setitem(sys.modules, "cloakbrowser", module)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    if not cookie:
        with pytest.raises(SystemExit):
            exec(script, {})
        assert "SUBSTACK_COOKIE_MISSING" in capsys.readouterr().out
        assert events == []
        return
    exec(script, {})
    assert events[0] == ("launch", {"headless": True, "humanize": False})
    assert events[1] == ("cookies", [{"name": "session", "value": "synthetic-fixture",
                                      "domain": ".substack.com", "path": "/"}])
    assert events[-1] == ("close", None)
    assert page.url == "https://aniccabuddha.substack.com/publish/stats/earnings"


def test_en_substack_driver_uses_only_its_own_publication_and_session(monkeypatch):
    script = substack_script(monkeypatch, "en")
    assert "https://aniccaai2026.substack.com/publish/home" in script
    assert "aniccabuddha" not in script
    assert "'SUBSTACK_SESSION_COOKIE_EN'" in script
    assert "'SUBSTACK_SESSION_COOKIE_JA'" not in script and "'SUBSTACK_SESSION_COOKIE'" not in script


@pytest.mark.parametrize("en_configured", (True, False))
def test_main_measures_en_substack_only_when_its_publication_is_configured(tmp_path, monkeypatch, en_configured):
    monkeypatch.setenv("SUBSTACK_PUBLICATION_JA", "aniccabuddha.substack.com")
    if en_configured:
        monkeypatch.setenv("SUBSTACK_PUBLICATION_EN", "aniccaai2026.substack.com")
    else:
        monkeypatch.delenv("SUBSTACK_PUBLICATION_EN", raising=False)
    monkeypatch.setattr(measure, "measure_note_pages", lambda: {"error": "fixture"})
    langs = []

    def substack(lang="ja"):
        langs.append(lang)
        return {"error": f"fixture {lang}"}

    monkeypatch.setattr(measure, "measure_substack_pages", substack)
    out = tmp_path / "sales-ledger.jsonl"
    assert measure.main(["--out", str(out), "--articles", str(tmp_path / "articles.jsonl")]) == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    substack_rows = [row for row in rows if row["platform"] == "substack"]
    assert langs == (["ja", "en"] if en_configured else ["ja"])
    # Each Substack row names its publication, so JA and EN never mix downstream.
    assert all(row["publication"] == row["source_url"].split("/")[2] for row in substack_rows)
    assert {row["publication"] for row in substack_rows} == (
        {"aniccabuddha.substack.com", "aniccaai2026.substack.com"} if en_configured
        else {"aniccabuddha.substack.com"})
