"""Reply/Paid bind private input and browser readback to the same account."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from skills.earn.crowdworks.tests.test_account_identity import Page, dashboard
from skills.earn.crowdworks.tests.test_profile_private_identity import (
    CANDIDATE, provider, write_json,
)


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def private_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIFE_MANAGER_STATE_ROOT", str(tmp_path / "state"))
    registry = tmp_path / "browsers.toml"
    registry.write_text("", encoding="utf-8")
    monkeypatch.setenv("AI_BROWSER_REGISTRY", str(registry))
    for key in ("CDP", "CDP_PORT", "CLOAK_CDP_BASE_URL", "LIFE_MANAGER_LOOP_ID",
                "LIFE_MANAGER_BROWSER_IDENTITY", "LIFE_MANAGER_BROWSER_TARGET_OWNER",
                "LIFE_MANAGER_BROWSER_LEASE_IDENTITY"):
        monkeypatch.delenv(key, raising=False)
    return home


def load(kind):
    spec = importlib.util.spec_from_file_location(
        f"crowdworks_private_{kind}_adapter_test", SCRIPTS / f"{kind}_adapter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def inputs(home):
    candidate = write_json(home / ".config/anicca/job-search/profile.json", CANDIDATE)
    local_provider = write_json(home / ".config/anicca/crowdworks/public-profile.json", provider())
    return candidate, local_provider


def arguments(kind, state, candidate=None, local_provider=None, account_id="5432107"):
    argv = ["--state-path", str(state)]
    if kind == "paid":
        argv += ["--account-id", account_id]
    if candidate is not None:
        argv += ["--candidate-profile", str(candidate)]
    if local_provider is not None:
        argv += ["--provider-profile", str(local_provider)]
    return argv


@pytest.mark.parametrize("kind", ["reply", "paid"])
@pytest.mark.parametrize("candidate_value", [None, {"version": 1, "facts": []}])
def test_build_validates_candidate_before_grounding_planner_or_state(
        private_home, tmp_path, monkeypatch, kind, candidate_value):
    module = load(kind)
    candidate = tmp_path / "candidate.json"
    if candidate_value is not None:
        write_json(candidate, candidate_value)
    local_provider = write_json(tmp_path / "provider.json", provider())
    state = tmp_path / "state.json"
    state.write_bytes(b'{"fence":"held","receipt":"existing"}')
    before = state.read_bytes()
    forbidden = lambda *_args, **_kwargs: pytest.fail("identity must precede planning/browser")
    monkeypatch.setattr(module.account, "_browser", forbidden)
    monkeypatch.setattr(module.grounding_module, "build_reply_grounding", forbidden)
    if kind == "reply":
        monkeypatch.setattr(module.planner, "ReplyPlanner", forbidden)

    with pytest.raises(module.profile_module.SetupRequired) as caught:
        module.build(arguments(kind, state, candidate, local_provider))

    assert caught.value.missing == ["candidate_profile"]
    assert state.read_bytes() == before


@pytest.mark.parametrize("kind", ["reply", "paid"])
def test_build_with_empty_home_reports_both_inputs_without_creating_them(private_home, tmp_path, kind):
    module = load(kind)
    with pytest.raises(module.profile_module.SetupRequired) as caught:
        module.build(arguments(kind, tmp_path / "state.json"))
    assert set(caught.value.missing) == {"candidate_profile", "provider_profile"}
    assert list(private_home.iterdir()) == []


@pytest.mark.parametrize("kind", ["reply", "paid"])
def test_build_uses_explicit_private_paths_and_validated_provider(
        private_home, tmp_path, monkeypatch, kind):
    module = load(kind)
    candidate = write_json(tmp_path / "custom-candidate.json", CANDIDATE)
    local_provider = write_json(tmp_path / "custom-provider.json", provider())
    adapter, _ = module.build(arguments(kind, tmp_path / "state.json", candidate, local_provider))
    assert adapter.candidate_profile == candidate.resolve()
    assert adapter.provider_profile == provider()
    if kind == "reply":
        observed = adapter._observation({"thread_id": 123, "id": 456})
        assert observed["account_id"] == "5432107"
        assert adapter.grounding["provider_public_facts"]["display_name"] == "別の利用者"
    else:
        assert adapter.account_id == "5432107"
    assert list(private_home.iterdir()) == []


def test_paid_cli_account_must_exactly_match_private_provider(private_home, tmp_path):
    module = load("paid")
    candidate, local_provider = inputs(private_home)
    for account_id in ("7145638", " 5432107", "5432107 "):
        with pytest.raises(module.profile_module.SetupRequired) as caught:
            module.build(arguments("paid", tmp_path / "state.json", candidate, local_provider, account_id))
        assert caught.value.missing == ["provider_account_binding"]


@pytest.mark.parametrize("sender,href,role", [
    ("別の利用者", "/public/employees/5432107", "seller"),
    ("別の利用者", "/public/employers/7777777", "buyer"),
    ("改名後の表示名", "https://crowdworks.jp/public/employees/5432107", "seller"),
    ("別の利用者", "/public/employers/5432107", "buyer"),
    ("別の利用者", "/public/employees/7145638", "buyer"),
    ("別の利用者", None, None),
    ("別の利用者", "https://elsewhere.example/public/employees/5432107", None),
    ("別の利用者", "/public/employees/5432107x", None),
])
def test_reply_sender_role_is_bound_to_provider_profile_link(
        private_home, tmp_path, sender, href, role):
    module = load("reply")
    candidate, local_provider = inputs(private_home)
    adapter, _ = module.build(arguments("reply", tmp_path / "state.json", candidate, local_provider))
    adapter.rows = {"thread": {"thread_id": "thread", "id": "message", "proposal_status": "proposed"}}

    class Locator:
        def count(self): return 1
        def evaluate_all(self, _script):
            assert "getAttribute('href')" in _script
            return [{"sender": sender, "sender_href": href,
                     "time": "fixture-time", "body": "対象の返信", "links": []}]

    # The parser receives an already opened synthetic provider page; _open is tested below.
    adapter.page = SimpleNamespace(locator=lambda _selector: Locator(), url="https://crowdworks.jp/proposals/1")
    adapter._open_thread_page = lambda _thread: None
    adapter._contract_action = lambda _thread: None
    adapter._external_form_action = lambda _thread: None
    if role is None:
        with pytest.raises(RuntimeError, match="crowdworks_conversation_invalid"):
            adapter.context("thread")
    else:
        context = adapter.context("thread")
        assert context["conversation"][-1]["role"] == role
        assert context["reply_required"] is (role == "buyer")


@pytest.mark.parametrize("kind", ["reply", "paid"])
def test_direct_constructor_without_private_inputs_stops_before_browser(
        private_home, monkeypatch, kind):
    module = load(kind)
    forbidden = lambda *_args, **_kwargs: pytest.fail("private input must precede browser")
    if kind == "reply":
        monkeypatch.setattr(module.account, "_cdp_alive", forbidden)
        adapter = module.CrowdWorksReplyAdapter({})
    else:
        adapter = module.CrowdWorksPaidAdapter(account_id="5432107", connection_factory=forbidden)
    with pytest.raises(module.profile_module.SetupRequired) as caught:
        adapter._open()
    assert set(caught.value.missing) == {"candidate_profile", "provider_profile"}


class BoundPage(Page):
    def __init__(self, identifier):
        super().__init__(dashboard(employee=identifier))
        self.urls = []

    def set_default_timeout(self, _timeout): pass
    def goto(self, url, **_kwargs):
        self.urls.append(url)
        super().goto(url)


@pytest.mark.parametrize("kind", ["reply", "paid"])
@pytest.mark.parametrize("observed_id", ["5432107", "7145638"])
def test_open_binds_new_page_before_provider_reads(
        private_home, tmp_path, monkeypatch, kind, observed_id):
    module = load(kind)
    candidate, local_provider = inputs(private_home)
    adapter, _ = module.build(arguments(kind, tmp_path / "state.json", candidate, local_provider))
    page = BoundPage(observed_id)
    source_pages, stopped, closed = [], [], []
    source = SimpleNamespace(new_page=lambda: source_pages.append(True))
    context = SimpleNamespace(new_page=lambda: page, close=lambda: closed.append(True))
    browser = SimpleNamespace(contexts=[source])
    if kind == "reply":
        browser.contexts = [context]
        monkeypatch.setattr(module.account, "_cdp_alive", lambda: True)
        monkeypatch.setattr(module.account, "_browser", lambda _url: browser)
    else:
        adapter.connection_factory = lambda: (SimpleNamespace(stop=lambda: stopped.append(True)), browser)
        adapter.context_factory = lambda _browser, _source: context
        adapter.prune_blank_source_pages = False
    if observed_id == "5432107":
        adapter._open()
        assert page.urls == ["https://crowdworks.jp/dashboard"]
        adapter.close()
    else:
        with pytest.raises(module.profile_module.SetupRequired) as caught:
            adapter._open()
        assert caught.value.missing == ["provider_account_binding"]
        assert page.closed
        assert adapter.page is None
        assert source_pages == []
        if kind == "paid":
            assert stopped == [True]
            assert closed == [True]


def test_paid_clone_creation_fallback_also_checks_identity(private_home, tmp_path):
    module = load("paid")
    candidate, local_provider = inputs(private_home)
    adapter, _ = module.build(arguments("paid", tmp_path / "state.json", candidate, local_provider))
    page, stopped = BoundPage("7145638"), []
    source = SimpleNamespace(new_page=lambda: page)
    adapter.connection_factory = lambda: (SimpleNamespace(stop=lambda: stopped.append(True)),
                                          SimpleNamespace(contexts=[source]))
    adapter.context_factory = lambda *_args: (_ for _ in ()).throw(RuntimeError("clone unavailable"))
    adapter.prune_blank_source_pages = False

    with pytest.raises(module.profile_module.SetupRequired) as caught:
        adapter._open()

    assert caught.value.missing == ["provider_account_binding"]
    assert page.urls == ["https://crowdworks.jp/dashboard"]
    assert page.closed
    assert adapter.page is None
    assert stopped == [True]


@pytest.mark.parametrize("clone_failed", [False, True])
def test_paid_account_navigation_error_is_not_swallowed_by_context_fallback(
        private_home, tmp_path, clone_failed):
    module = load("paid")
    candidate, local_provider = inputs(private_home)
    adapter, _ = module.build(arguments("paid", tmp_path / "state.json", candidate, local_provider))
    page, source_pages, stopped, closed = BoundPage("5432107"), [], [], []
    page.goto = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("navigation unavailable"))
    source = SimpleNamespace(new_page=lambda: source_pages.append(True) or page)
    context = SimpleNamespace(new_page=lambda: page, close=lambda: closed.append(True))
    adapter.connection_factory = lambda: (SimpleNamespace(stop=lambda: stopped.append(True)),
                                          SimpleNamespace(contexts=[source]))
    adapter.context_factory = (lambda *_args: (_ for _ in ()).throw(RuntimeError("clone unavailable"))) \
        if clone_failed else lambda *_args: context
    adapter.prune_blank_source_pages = False

    with pytest.raises(module.profile_module.ProfileError) as caught:
        adapter._open()

    assert caught.value.code == "profile_navigation_failed"
    assert source_pages == ([True] if clone_failed else [])
    assert stopped == [True]
    assert page.closed
    assert adapter.page is None
    assert closed == ([] if clone_failed else [True])


def test_paid_detail_retry_binds_the_replacement_page(private_home, tmp_path):
    module = load("paid")
    candidate, local_provider = inputs(private_home)
    adapter, _ = module.build(arguments("paid", tmp_path / "state.json", candidate, local_provider))
    first, replacement = BoundPage("5432107"), BoundPage("7145638")
    adapter.page = first
    adapter.owned_context = SimpleNamespace(new_page=lambda: replacement)
    calls = []

    def detail(_basic):
        calls.append(True)
        if len(calls) == 1:
            raise module.PlaywrightTimeoutError("retry")
        return {"unverified": True}

    adapter._detail_once = detail
    with pytest.raises(module.profile_module.SetupRequired) as caught:
        adapter._detail({"work_id": "123"})
    assert caught.value.missing == ["provider_account_binding"]
    assert calls == [True]
    assert first.closed and replacement.closed
    assert adapter.page is None


def test_paid_proposal_page_is_bound_before_application_date_read(private_home, tmp_path):
    module = load("paid")
    candidate, local_provider = inputs(private_home)
    adapter, _ = module.build(arguments("paid", tmp_path / "state.json", candidate, local_provider))
    page = BoundPage("7145638")
    locator = page.locator
    page.locator = lambda selector: (SimpleNamespace(inner_text=lambda: "応募日 2026年10月1日")
                                     if selector == "body" else locator(selector))
    adapter.owned_context = SimpleNamespace(new_page=lambda: page)
    with pytest.raises(module.profile_module.SetupRequired) as caught:
        adapter._proposal_application_date("123")
    assert caught.value.missing == ["provider_account_binding"]
    assert page.urls == ["https://crowdworks.jp/dashboard"]
    assert page.closed


def test_paid_late_source_fallback_cannot_return_an_unbound_page(private_home, tmp_path):
    module = load("paid")
    candidate, local_provider = inputs(private_home)
    adapter, _ = module.build(arguments("paid", tmp_path / "state.json", candidate, local_provider))
    old_page, replacement = BoundPage("5432107"), BoundPage("7145638")
    adapter.page = old_page
    adapter.owned_context = SimpleNamespace(close=lambda: None)
    adapter.owns_context = True
    adapter.source_context = SimpleNamespace(new_page=lambda: replacement)
    with pytest.raises(module.profile_module.SetupRequired) as caught:
        adapter._fallback_to_source_context()
    assert caught.value.missing == ["provider_account_binding"]
    assert old_page.closed and replacement.closed
    assert adapter.page is None


def test_read_only_inventory_passes_default_identity_without_creating_state(
        private_home, monkeypatch):
    module = load("paid")
    candidate, _ = inputs(private_home)
    received = []

    class Adapter:
        def __init__(self, **kwargs): received.append(kwargs)
        def observe_active(self): return []
        def close(self): received.append("closed")

    monkeypatch.setattr(module, "CrowdWorksPaidAdapter", Adapter)
    result = module.read_only_inventory()
    assert result["ok"] is True
    assert received == [{"account_id": "5432107", "candidate_profile": candidate,
                         "provider_profile": provider(), "prune_blank_source_pages": False}, "closed"]
    assert not (private_home / ".local").exists()
