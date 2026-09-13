"""Unit tests for session_vault's logged_out detection.

Bug fixed: keepalive/logged_out previously judged purely by whether the final URL redirected to
/login or /signin (session_vault.py:210, pre-fix). Instagram does NOT redirect to /login for a
half-dead session — ds_user_id survives after sessionid expires, and IG just serves the feed as
if nothing happened. So the old logic returned logged_out:false forever even though the session
was dead ("session was dead for 3 days and nobody noticed"). The negative test below reproduces
exactly that: an instagram.com page, no redirect, sessionid cookie absent -> must report
logged_out:true. Non-instagram domains (coconala etc) must keep the old URL-only behavior.

Run: python3 -m pytest test_session_vault.py -v
"""
import os
import sys
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_vault as sv  # noqa: E402


def test_dump_keeps_prior_vault_present_until_atomic_replacement(monkeypatch, tmp_path):
    vault = tmp_path / "auth-state.json"
    vault.write_text(json.dumps({"cookies": [_cookie("old", ".coconala.com")]}), encoding="utf-8")
    monkeypatch.setattr(sv, "VAULT_DIR", str(tmp_path))
    monkeypatch.setattr(sv, "VAULT", str(vault))
    calls = 0

    def run(coro):
        nonlocal calls
        coro.close()
        calls += 1
        return {"cookies": [_cookie("new", ".coconala.com")]} if calls == 1 else {}

    original_replace = os.replace
    destinations = []

    def replace(source, destination):
        destinations.append(destination)
        assert destination == str(vault)
        assert vault.exists()
        original_replace(source, destination)

    monkeypatch.setattr(sv, "_run", run)
    monkeypatch.setattr(sv.os, "replace", replace)

    assert sv.dump()["ok"] is True
    assert destinations == [str(vault)]
    assert json.loads(vault.read_text())["cookies"][0]["name"] == "new"
    assert list(tmp_path.glob("auth-state.*.json"))


def _cookie(name, domain):
    return {"name": name, "domain": domain, "value": "x"}


def test_instagram_no_sessionid_no_redirect_is_logged_out():
    """THE false-positive bug: IG keeps ds_user_id after sessionid dies, never redirects to /login."""
    url = "https://www.instagram.com/"
    final = "https://www.instagram.com/"  # no redirect at all
    cookies = [_cookie("ds_user_id", ".instagram.com"), _cookie("csrftoken", ".instagram.com")]
    assert sv._logged_out_for(url, final, cookies) is True


def test_instagram_with_sessionid_no_redirect_is_logged_in():
    url = "https://www.instagram.com/"
    final = "https://www.instagram.com/"
    cookies = [_cookie("sessionid", ".instagram.com"), _cookie("ds_user_id", ".instagram.com")]
    assert sv._logged_out_for(url, final, cookies) is False


def test_instagram_redirected_to_login_is_logged_out_even_without_cookie_check():
    url = "https://www.instagram.com/"
    final = "https://www.instagram.com/accounts/login/"
    cookies = [_cookie("sessionid", ".instagram.com")]  # even a live-looking cookie can't save it
    assert sv._logged_out_for(url, final, cookies) is True


def test_non_instagram_domain_uses_url_redirect_only_sessionid_irrelevant():
    """coconala etc keep the old behavior: sessionid check must not fire off-instagram."""
    url = "https://coconala.com/mypage"
    final = "https://coconala.com/mypage"
    cookies = []  # no sessionid cookie anywhere -- must not matter off-instagram
    assert sv._logged_out_for(url, final, cookies) is False


def test_non_instagram_domain_redirected_to_login_is_logged_out():
    url = "https://coconala.com/mypage"
    final = "https://coconala.com/login"
    cookies = [_cookie("sessionid", ".instagram.com")]  # unrelated cookie present, irrelevant
    assert sv._logged_out_for(url, final, cookies) is True


def test_instagram_sessionid_on_wrong_domain_does_not_count():
    """A sessionid cookie scoped to a different domain must not satisfy the instagram check."""
    url = "https://www.instagram.com/"
    final = "https://www.instagram.com/"
    cookies = [_cookie("sessionid", ".some-other-site.com")]
    assert sv._logged_out_for(url, final, cookies) is True


def test_localstorage_attach_failure_still_closes_and_releases_target(monkeypatch):
    events = []

    class Socket:
        last = None

        async def send(self, payload):
            self.last = json.loads(payload)
            events.append(("send", self.last["method"]))

        async def recv(self):
            if self.last["method"] == "Target.createTarget":
                return json.dumps({"id": self.last["id"], "result": {"targetId": "vault-tab"}})
            if self.last["method"] == "Target.attachToTarget":
                return json.dumps({"id": self.last["id"], "error": {"message": "attach failed"}})
            return json.dumps({"id": self.last["id"], "result": {"success": True}})

    class Connection:
        async def __aenter__(self):
            return Socket()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(sv, "LS_ORIGINS", ["https://coconala.com"])
    monkeypatch.setattr(sv, "_browser_ws", lambda: "ws://browser")
    monkeypatch.setattr(sv.websockets, "connect", lambda *_a, **_k: Connection())
    monkeypatch.setattr(
        sv.target_ownership,
        "claim_target",
        lambda target, owner: events.append(("claim", target, owner)),
    )
    monkeypatch.setattr(
        sv.target_ownership,
        "release_target",
        lambda target, owner: events.append(("release", target, owner)),
    )

    assert asyncio.run(sv._localstorage("read")) == {}
    assert events == [
        ("send", "Target.createTarget"),
        ("claim", "vault-tab", "session-vault-localstorage"),
        ("send", "Target.attachToTarget"),
        ("send", "Target.closeTarget"),
        ("release", "vault-tab", "session-vault-localstorage"),
    ]


def test_keepalive_attach_failure_still_closes_and_releases_target(monkeypatch):
    events = []

    class Socket:
        last = None

        async def send(self, payload):
            self.last = json.loads(payload)
            events.append(("send", self.last["method"]))

        async def recv(self):
            if self.last["method"] == "Target.createTarget":
                return json.dumps({"id": self.last["id"], "result": {"targetId": "keepalive-tab"}})
            if self.last["method"] == "Target.attachToTarget":
                return json.dumps({"id": self.last["id"], "error": {"message": "attach failed"}})
            return json.dumps({"id": self.last["id"], "result": {"success": True}})

    class Connection:
        async def __aenter__(self):
            return Socket()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(sv, "_browser_ws", lambda: "ws://browser")
    monkeypatch.setattr(sv.websockets, "connect", lambda *_a, **_k: Connection())
    monkeypatch.setattr(
        sv.target_ownership,
        "claim_target",
        lambda target, owner: events.append(("claim", target, owner)),
    )
    monkeypatch.setattr(
        sv.target_ownership,
        "release_target",
        lambda target, owner: events.append(("release", target, owner)),
    )

    try:
        asyncio.run(sv._keepalive(["https://coconala.com"]))
    except RuntimeError:
        pass
    assert events == [
        ("send", "Target.createTarget"),
        ("claim", "keepalive-tab", "session-vault-keepalive"),
        ("send", "Target.attachToTarget"),
        ("send", "Target.closeTarget"),
        ("release", "keepalive-tab", "session-vault-keepalive"),
    ]
