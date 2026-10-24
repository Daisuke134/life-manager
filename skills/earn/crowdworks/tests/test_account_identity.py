"""Account identity comes from the authenticated dashboard's own profile card."""
from __future__ import annotations

import html
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from bs4 import BeautifulSoup
import pytest


@pytest.fixture
def account(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for key in ("AI_BROWSER_REGISTRY", "CDP", "CDP_PORT", "CLOAK_CDP_BASE_URL",
                "LIFE_MANAGER_BROWSER_LEASE_IDENTITY", "LIFE_MANAGER_BROWSER_IDENTITY",
                "LIFE_MANAGER_LOOP_ID"):
        monkeypatch.delenv(key, raising=False)
    source = Path(__file__).resolve().parents[1] / "scripts/account.py"
    spec = importlib.util.spec_from_file_location("crowdworks_account_identity_test", source)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


class Locator:
    def __init__(self, nodes):
        self.nodes = nodes

    def count(self):
        return len(self.nodes)

    def nth(self, index):
        return Locator([self.nodes[index]])

    def get_attribute(self, name):
        return self.nodes[0].get(name)


class Page:
    def __init__(self, body, redirect=None):
        self.soup = BeautifulSoup(body, "html.parser")
        self.redirect = redirect
        self.url = "about:blank"
        self.closed = False

    def locator(self, selector):
        return Locator(self.soup.select(selector))

    def goto(self, url):
        self.url = self.redirect or url

    def wait_for_load_state(self, **_kwargs):
        pass

    def close(self):
        self.closed = True


def dashboard(*, employee="543210", avatar=None, logged_in=True, own_card=True):
    header = html.escape(json.dumps({"headerMenuProps": {
        "isLogin": logged_in, "userRole": "employee", "username": "other-user"}}), quote=True)
    card = ""
    if own_card:
        name_url = f"https://crowdworks.jp/public/employees/{employee}"
        avatar_url = avatar or name_url
        card = f'''<div class="sidebar"><section class="profiles cw-section">
          <div class="profile_data_area">
            <a class="user_avatar" href="{html.escape(avatar_url, quote=True)}"><img></a>
            <div class="profile_data"><a class="profile_name" href="{name_url}">Other user</a></div>
          </div></section></div>'''
    return f'''<div id="norman-header-section" data="{header}"></div>{card}
      <main><a href="https://crowdworks.jp/public/employees/999999">Another seller</a></main>'''


def browser(page):
    return SimpleNamespace(contexts=[SimpleNamespace(new_page=lambda: page)])


def status(account, page):
    result = account.run_status(ownership_checker=lambda: True,
                                browser_factory=lambda _url: browser(page))
    assert page.closed
    return result.to_dict()


@pytest.mark.parametrize("employee", ["543210", "87654321"])
def test_status_returns_the_observed_other_users_account_id(account, employee):
    result = status(account, Page(dashboard(employee=employee)))
    assert result["authenticated"] is True
    assert result.get("account_id") == employee


@pytest.mark.parametrize("body,redirect", [
    (dashboard(logged_in=False), None),
    (dashboard() + '<form action="/login"></form>', None),
    (dashboard(), "https://crowdworks.jp/public/employees/543210"),
    (dashboard(), "https://elsewhere.example/dashboard"),
    (dashboard(), "http://crowdworks.jp/dashboard"),
    (dashboard(own_card=False), None),
    (dashboard(avatar="https://elsewhere.example/public/employees/543210"), None),
    (dashboard(avatar="https://crowdworks.jp/public/employees/123456"), None),
    (dashboard(employee="not-an-id"), None),
])
def test_status_does_not_invent_account_identity(account, body, redirect):
    result = status(account, Page(body, redirect))
    assert "account_id" not in result


def test_ensure_returns_identity_without_requesting_credentials(account, tmp_path):
    page = Page(dashboard(employee="87654321"))
    forbidden = lambda *_args: pytest.fail("authenticated identity must not request input")
    result = account.run_ensure(
        state_path=tmp_path / "account.json", allow_signup=False,
        ownership_checker=lambda: True, browser_factory=lambda _url: browser(page),
        vault_restorer=lambda: None, vault_dumper=lambda: {"ok": True},
        credential_loader=forbidden, notifier=forbidden, now="fixture",
    ).to_dict()
    assert result["authenticated"] is True
    assert result.get("account_id") == "87654321"
    assert page.closed
    assert not (tmp_path / "account.json").exists()


def test_ownership_conflict_does_not_open_a_browser(account):
    result = account.run_status(
        ownership_checker=lambda: False,
        browser_factory=lambda _url: pytest.fail("browser ownership is required"),
    ).to_dict()
    assert result["status"] == "browser_ownership_conflict"
    assert "account_id" not in result
