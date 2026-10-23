"""Discovery must read the board through the leased, logged-in Lancers page.

Measured 2026-10-15: Lancers' AWS WAF answers the cookieless urllib GET of /work/search with
405 and x-amzn-waf-action: captcha, so every wake ended lancers_http_error/405 with nothing
discovered, while work-sync read /mypage through the leased browser with 200 at the same time.
"""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from skills.earn.lancers.tests.identity_fixture import write_identity
import sys
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SEARCH_HTML = """
<div class="p-search-job-media"><a class="p-search-job-media__title" href="/work/detail/1000001">業務自動化ツール開発</a><div class="js-job-show-description">teaser</div><div class="p-search-job__division">システム開発</div><div class="p-search-job-media__price"><span class="c-badge__text">プロジェクト</span><span class="p-search-job-media__number">98,000</span></div></div>
"""
DETAIL_HTML = "<dl><dt>依頼概要</dt><dd>業務自動化ツールを開発してください。</dd></dl>"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakePage:
    def __init__(self, status=200):
        self.status = status
        self.urls = []
        self.scripts = []

    def evaluate(self, script, arg=None):
        self.scripts.append(script)
        url = arg[0]
        self.urls.append(url)
        body = DETAIL_HTML if "/work/detail/" in url else SEARCH_HTML
        return {"status": self.status, "url": url, "body": body}


def _no_urllib(*_args, **_kwargs):
    raise AssertionError("discovery must not use cookieless urllib when a page is given")


def test_page_discovery_reads_search_and_detail_in_page_with_session_cookies():
    status = _load("lancers_status_browser_fetch", "status.py")
    page = FakePage()
    with patch.object(status.urllib.request, "urlopen", side_effect=_no_urllib):
        result = status.run_discovery(query="自動化", limit=20, timeout=5, page=page,
                                      observed_at="2026-10-15T00:00:00Z")

    assert result["ok"] is True
    assert result["detail_enriched_count"] == 1
    assert page.urls[0].startswith("https://www.lancers.jp/work/search?")
    assert page.urls[1] == "https://www.lancers.jp/work/detail/1000001"
    assert all('credentials: "same-origin"' in script for script in page.scripts)


def test_page_discovery_reports_the_waf_status_instead_of_an_empty_board():
    status = _load("lancers_status_browser_405", "status.py")
    with patch.object(status.urllib.request, "urlopen", side_effect=_no_urllib):
        result = status.run_discovery(query="自動化", limit=20, timeout=5, page=FakePage(status=405))

    assert result["ok"] is False
    assert result["error"] == "lancers_http_error"
    assert result["http_status"] == 405


def _patched_browser(loop, *, ready=True):
    page = FakePage()
    closed = []
    return page, closed, (
        patch.object(loop, "_capacity_reason", return_value=None),
        patch.object(loop.application_tick, "_open_owned_page", return_value=(object(), page)),
        patch.object(loop.application_tick, "_production_account_ready", return_value=ready),
        patch.object(loop.application_tick, "_close_owned_page", side_effect=lambda value: closed.append(value) or True),
        patch.object(loop.application_tick, "_stop_playwright_runtime", return_value=None),
    )


def test_default_wake_discovers_through_the_leased_page_and_releases_it(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_identity(home)
    monkeypatch.setenv("HOME", str(home))
    loop = _load("lancers_application_loop_browser_discovery", "application_loop.py")
    page, closed, patches = _patched_browser(loop)
    seen = []

    def discover(**kwargs):
        seen.append(kwargs)
        return {"ok": False, "error": "no_normalized_opportunities", "provider_count": 0, "opportunities": []}

    with patches[0], patches[1], patches[2], patches[3], patches[4], \
            patch.object(loop.status, "run_discovery", side_effect=discover):
        result = loop.run_loop(state_path=tmp_path / "application.json", evidence_root=tmp_path / "evidence",
                               clock=lambda: datetime(2026, 10, 15, tzinfo=timezone.utc))

    assert result["ok"] is True and result["reason"] == "no_eligible_project"
    assert [call["page"] for call in seen] == [page]
    assert closed == [page]


def test_default_wake_names_a_logged_out_browser_and_does_not_discover(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_identity(home)
    monkeypatch.setenv("HOME", str(home))
    loop = _load("lancers_application_loop_browser_logged_out", "application_loop.py")
    page, closed, patches = _patched_browser(loop, ready=False)

    with patches[0], patches[1], patches[2], patches[3], patches[4], \
            patch.object(loop.status, "run_discovery", side_effect=AssertionError("discovered while logged out")):
        result = loop.run_loop(state_path=tmp_path / "application.json", evidence_root=tmp_path / "evidence",
                               clock=lambda: datetime(2026, 10, 15, tzinfo=timezone.utc))

    assert result["ok"] is False
    assert result["error"] == "account_unavailable"
    assert closed == [page]
