from __future__ import annotations

import importlib.util
import json
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
            return {"url": self.url, "title": "TikTok", "profiles": []}
        return {
            "url": self.url,
            "title": "TikTok",
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
    assert fake.reads == 2
    assert fake.closed == [("search-tab", "paid-search")]
    assert "q=%E7%A4%BE%E4%BC%9A%E4%BA%BA%20%E6%97%A5%E5%B8%B8" in fake.url


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
