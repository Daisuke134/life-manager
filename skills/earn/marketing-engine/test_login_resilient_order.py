"""login_resilient tier ordering: browser-leased accounts try the browser sessionid
before the (possibly stale) saved instagrapi settings file; instagrapi-only accounts
are unaffected.

Root cause this covers (2026-09-27, capafy-ig-marketing-daily): a fresh browser login
was performed, but the next run still hit tier1 LoginRequired because the saved
instagrapi settings file was tried first and never re-derived from the live browser
session until it too failed. The fix makes the browser the source of truth for any
account that has one leased (session_owner != "instagrapi"), and falls back to the
saved settings file only if the browser attempt is unavailable or fails. Accounts
explicitly marked session_owner="instagrapi" keep the exact original order (settings
file only; tier2 never runs), and a saved-session-dead account never falls through to
a tier3 password login (unchanged from before).
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def load_poster(monkeypatch):
    cdp = types.ModuleType("cdp")
    cdp.page_ws = lambda _tid: "ws://unused"
    monkeypatch.setitem(sys.modules, "cdp", cdp)

    websocket = types.ModuleType("websocket")
    websocket.create_connection = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, "websocket", websocket)

    exceptions = types.ModuleType("instagrapi.exceptions")
    exceptions.ChallengeRequired = type("ChallengeRequired", (Exception,), {})
    exceptions.LoginRequired = type("LoginRequired", (Exception,), {})
    instagrapi = types.ModuleType("instagrapi")
    instagrapi.exceptions = exceptions
    monkeypatch.setitem(sys.modules, "instagrapi", instagrapi)
    monkeypatch.setitem(sys.modules, "instagrapi.exceptions", exceptions)

    spec = importlib.util.spec_from_file_location("poster_under_test_order", ROOT / "poster.py")
    poster = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(poster)
    return poster, exceptions


def write_accounts(tmp_path, *, session_owner):
    path = tmp_path / "accounts.json"
    account = {"handle": "capafy.skills8m4q2z", "started_warming": "2026-07-17"}
    if session_owner is not None:
        account["session_owner"] = session_owner
    path.write_text(json.dumps([account]))
    return path


class FakeClient:
    """Records call order; simulates a saved-settings tier that is dead and a browser
    sessionid tier that is alive (or vice versa depending on the test)."""

    def __init__(self, *, settings_ok, sessionid_ok, handle):
        self.settings_ok = settings_ok
        self.sessionid_ok = sessionid_ok
        self.handle = handle
        self.calls = []
        self.username = None
        self.last_response = types.SimpleNamespace(json=lambda: {})
        self.dumped = []

    def load_settings(self, _path):
        self.calls.append("load_settings")
        if not self.settings_ok:
            raise RuntimeError("settings dead")

    def get_timeline_feed(self):
        self.calls.append("get_timeline_feed")
        if not self.settings_ok:
            raise RuntimeError("settings dead")

    def account_info(self):
        return types.SimpleNamespace(username=self.handle)

    def login_by_sessionid(self, _sid):
        self.calls.append("login_by_sessionid")
        if not self.sessionid_ok:
            raise RuntimeError("sessionid dead")
        self.username = self.handle

    def dump_settings(self, path):
        self.dumped.append(path)


def test_browser_leased_account_tries_sessionid_before_settings_file(monkeypatch, tmp_path):
    poster, _ = load_poster(monkeypatch)
    accounts_path = write_accounts(tmp_path, session_owner="browser")
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")  # a saved (but, per the bug, possibly-stale) session exists

    monkeypatch.setattr(poster, "get_sessionid", lambda _port: (None, "fresh-sid"))
    cl = FakeClient(settings_ok=True, sessionid_ok=True, handle="capafy.skills8m4q2z")
    res = {}

    ok = poster.login_resilient(
        cl, "capafy.skills8m4q2z", 1234, res,
        settings_path=str(settings_path), accounts_path=str(accounts_path),
    )

    assert ok is True
    assert cl.calls[0] == "login_by_sessionid", (
        "browser sessionid must be tried before the saved settings file for a leased account"
    )
    assert "load_settings" not in cl.calls, "settings-file tier must not run once the browser tier succeeds"


def test_browser_leased_account_falls_back_to_settings_when_browser_fails(monkeypatch, tmp_path):
    poster, _ = load_poster(monkeypatch)
    accounts_path = write_accounts(tmp_path, session_owner="browser")
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    monkeypatch.setattr(poster, "get_sessionid", lambda _port: (None, "dead-sid"))
    cl = FakeClient(settings_ok=True, sessionid_ok=False, handle="capafy.skills8m4q2z")
    res = {}

    ok = poster.login_resilient(
        cl, "capafy.skills8m4q2z", 1234, res,
        settings_path=str(settings_path), accounts_path=str(accounts_path),
    )

    assert ok is True
    assert cl.calls[0] == "login_by_sessionid"
    assert "load_settings" in cl.calls, "a dead browser tier must fall back to the saved settings file"
    assert "tier2_dead" in res


def test_instagrapi_only_account_never_tries_browser_and_order_is_unchanged(monkeypatch, tmp_path):
    poster, _ = load_poster(monkeypatch)
    accounts_path = write_accounts(tmp_path, session_owner="instagrapi")
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    def fail_get_sessionid(_port):
        raise AssertionError("get_sessionid must never be called for session_owner=instagrapi")

    monkeypatch.setattr(poster, "get_sessionid", fail_get_sessionid)
    cl = FakeClient(settings_ok=True, sessionid_ok=True, handle="capafy.skills8m4q2z")
    res = {}

    ok = poster.login_resilient(
        cl, "capafy.skills8m4q2z", 1234, res,
        settings_path=str(settings_path), accounts_path=str(accounts_path),
    )

    assert ok is True
    assert cl.calls == ["load_settings", "get_timeline_feed"]
    assert res.get("tier2_skipped")


def test_dead_settings_and_dead_browser_never_falls_through_to_password_login(monkeypatch, tmp_path):
    poster, _ = load_poster(monkeypatch)
    accounts_path = write_accounts(tmp_path, session_owner="browser")
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    monkeypatch.setattr(poster, "get_sessionid", lambda _port: (None, "dead-sid"))

    def fail_login(_username, _password):
        raise AssertionError("private-API password login must never run for a leased-browser account")

    cl = FakeClient(settings_ok=False, sessionid_ok=False, handle="capafy.skills8m4q2z")
    cl.login = fail_login
    res = {}

    ok = poster.login_resilient(
        cl, "capafy.skills8m4q2z", 1234, res,
        settings_path=str(settings_path), accounts_path=str(accounts_path),
    )

    assert ok is False
    assert "browser authorization is required" in res.get("error", "")
