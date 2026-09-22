from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


def load_module():
    path = Path(__file__).with_name("tiktok_user_search.py")
    spec = importlib.util.spec_from_file_location("tiktok_user_search", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCDP:
    def __init__(self):
        self.reads = 0
        self.closed = []

    def new_target(self, url, owner):
        self.url = url
        self.owner = owner
        return "search-tab"

    def evaluate(self, target, _expression):
        assert target == "search-tab"
        self.reads += 1
        if self.reads == 1:
            return {"url": self.url, "title": "TikTok", "ready": False, "profiles": []}
        return {
            "url": self.url,
            "title": "TikTok",
            "ready": True,
            "profiles": [
                "https://www.tiktok.com/@candidate?lang=ja-JP",
                "https://www.tiktok.com/@candidate?lang=ja-JP",
                "https://example.com/@wrong",
            ],
        }

    def close_target(self, target, owner):
        self.closed.append((target, owner))


def test_search_retries_dedupes_and_atomically_writes(tmp_path):
    search = load_module()
    fake = FakeCDP()
    output = tmp_path / "search.json"

    result = search.search_users(
        "社会人 日常", "paid-search", output,
        cdp_client=fake, wait=lambda _seconds: None, attempts=3,
    )

    assert result["profiles"] == ["https://www.tiktok.com/@candidate?lang=ja-JP"]
    assert json.loads(output.read_text()) == result
    assert fake.reads == 3
    assert fake.closed == [("search-tab", "paid-search")]
    assert "q=%E7%A4%BE%E4%BC%9A%E4%BA%BA%20%E6%97%A5%E5%B8%B8" in fake.url


def test_search_does_not_finish_on_navigation_profile_before_results_load(tmp_path):
    search = load_module()

    class NavigationFirst(FakeCDP):
        def evaluate(self, target, _expression):
            assert target == "search-tab"
            self.reads += 1
            profiles = []
            if self.reads > 2:
                profiles.append("https://www.tiktok.com/@candidate?lang=ja-JP")
            return {"url": self.url, "title": "TikTok", "ready": self.reads > 2,
                    "profiles": profiles}

    fake = NavigationFirst()
    result = search.search_users(
        "美容 vlog", "paid-search", tmp_path / "search.json",
        cdp_client=fake, wait=lambda _seconds: None, attempts=4,
    )

    assert fake.reads == 4
    assert result["profiles"] == [
        "https://www.tiktok.com/@candidate?lang=ja-JP",
    ]


def test_search_requires_two_ready_samples_after_readiness_transition(tmp_path):
    search = load_module()

    class ReadyTransition(FakeCDP):
        def evaluate(self, target, _expression):
            self.reads += 1
            if self.reads == 1:
                return {"url": self.url, "title": "TikTok", "ready": False,
                        "profiles": []}
            profiles = (["https://www.tiktok.com/@early"] if self.reads == 2 else
                        ["https://www.tiktok.com/@candidate"])
            return {"url": self.url, "title": "TikTok", "ready": True,
                    "profiles": profiles}

    fake = ReadyTransition()
    result = search.search_users(
        "美容 vlog", "paid-search", tmp_path / "search.json",
        cdp_client=fake, wait=lambda _seconds: None, attempts=4,
    )

    assert fake.reads == 4
    assert result["profiles"] == ["https://www.tiktok.com/@candidate"]


def test_search_timeout_is_incomplete_when_results_never_become_ready(tmp_path):
    search = load_module()

    class NavigationOnly(FakeCDP):
        def evaluate(self, target, _expression):
            self.reads += 1
            return {"url": self.url, "title": "TikTok", "ready": False,
                    "profiles": ["https://www.tiktok.com/@anicca.jp?lang=ja-JP"]}

    fake = NavigationOnly()
    output = tmp_path / "search.json"
    result = search.search_users(
        "美容 vlog", "paid-search", output,
        cdp_client=fake, wait=lambda _seconds: None, attempts=3,
    )

    assert fake.reads == 3
    assert result["complete"] is False
    assert result["ready"] is False
    assert result["reason"] == "search_results_not_stable"
    assert json.loads(output.read_text()) == result


def test_search_timeout_is_incomplete_while_ready_results_keep_changing(tmp_path):
    search = load_module()

    class Changing(FakeCDP):
        def evaluate(self, target, _expression):
            self.reads += 1
            return {"url": self.url, "title": "TikTok", "ready": True,
                    "profiles": [f"https://www.tiktok.com/@candidate{self.reads}"]}

    fake = Changing()
    result = search.search_users(
        "美容 vlog", "paid-search", tmp_path / "search.json",
        cdp_client=fake, wait=lambda _seconds: None, attempts=3,
    )

    assert result["complete"] is False
    assert result["ready"] is True


def test_ready_empty_results_complete_only_after_stable_empty_sample(tmp_path):
    search = load_module()

    class Empty(FakeCDP):
        def evaluate(self, target, _expression):
            self.reads += 1
            return {"url": self.url, "title": "TikTok", "ready": True,
                    "profiles": []}

    fake = Empty()
    result = search.search_users(
        "not-found", "paid-search", tmp_path / "search.json",
        cdp_client=fake, wait=lambda _seconds: None, attempts=3,
    )

    assert fake.reads == 2
    assert result["complete"] is True
    assert result["profiles"] == []


def test_readback_ignores_hidden_or_linkless_result_items():
    search = load_module()

    assert ")].filter(visible);" in search.READBACK
    assert "ready: resultLinks.length > 0 || empty" in search.READBACK


def test_readback_uses_current_search_result_container_not_sidebar_links():
    search = load_module()
    fixture = r"""
const link = href => ({
  href, innerText: href, matches: () => false, querySelectorAll: () => [],
  getBoundingClientRect: () => ({width: 100, height: 20})
});
const nav = link('https://www.tiktok.com/@anicca.jp?lang=ja-JP');
const result = link('https://www.tiktok.com/@candidate?lang=ja-JP');
const root = {querySelectorAll: selector =>
  selector.includes('DivPanelContainer') ? [result] : []};
globalThis.getComputedStyle = () => ({display: 'block', visibility: 'visible'});
globalThis.location = {href: 'https://www.tiktok.com/search/user?q=test'};
globalThis.document = {
  title: 'TikTok', nav,
  querySelector: () => WITH_RESULTS ? root : null,
  querySelectorAll: () => []
};
"""

    def run(with_results: bool) -> dict:
        source = fixture.replace("WITH_RESULTS", json.dumps(with_results))
        source += f"\nconsole.log(JSON.stringify(eval({json.dumps(search.READBACK)})));"
        completed = subprocess.run(
            ["node", "-e", source], check=True, text=True, capture_output=True,
        )
        return json.loads(completed.stdout)

    assert run(False) == {
        "url": "https://www.tiktok.com/search/user?q=test",
        "title": "TikTok", "ready": False, "empty": False, "profiles": [],
    }
    assert run(True)["profiles"] == [
        "https://www.tiktok.com/@candidate?lang=ja-JP"
    ]


def test_search_closes_owned_target_on_read_failure(tmp_path):
    search = load_module()

    class Broken(FakeCDP):
        def evaluate(self, target, expression):
            raise RuntimeError("read failed")

    fake = Broken()
    try:
        search.search_users(
            "社会人", "paid-search", tmp_path / "search.json",
            cdp_client=fake, wait=lambda _seconds: None, attempts=1,
        )
    except RuntimeError as error:
        assert str(error) == "read failed"
    else:
        raise AssertionError("expected read failure")
    assert fake.closed == [("search-tab", "paid-search")]
