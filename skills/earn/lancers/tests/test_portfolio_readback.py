import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/storefront_offer.py"
TITLE_STEM = "AI・API連携の自動運用システムを設計・実装し"


def _module():
    spec = importlib.util.spec_from_file_location("lancers_portfolio_readback_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Link:
    def __init__(self, text, href):
        self.text, self.href = text, href

    def inner_text(self):
        return self.text

    def get_attribute(self, name):
        return self.href if name == "href" else None


class Page:
    def __init__(self, links):
        self.links = links

    @contextmanager
    def expect_response(self, _predicate, **_kwargs):
        yield SimpleNamespace(value=SimpleNamespace(status=200))

    def goto(self, *_args, **_kwargs):
        return None

    def locator(self, _selector):
        return SimpleNamespace(all=lambda: self.links)


def _links(*ids):
    return [Link(TITLE_STEM + "ました", f"/profile/keiodaisuke/portfolio_popup/{i}") for i in ids]


def test_pinned_portfolio_is_found_when_a_same_title_duplicate_exists():
    # 2026-10-18: a second public portfolio (757333) with the same title appeared on
    # /myportfolio; the pinned 743987 is still there, so the readback must pick it.
    module = _module()
    found = module._portfolio(Page(_links("757333", "743987")), {"title_stem": TITLE_STEM, "external_id": "743987"})
    assert found == {
        "portfolio_external_id": "743987",
        "portfolio_url": "https://www.lancers.jp/profile/keiodaisuke/portfolio_popup/743987",
        "portfolio_duplicate_external_ids": ["757333"],
    }


def test_pinned_portfolio_missing_among_same_title_rows_stays_invalid():
    module = _module()
    with pytest.raises(module.OfferError, match="portfolio_readback_invalid"):
        module._portfolio(Page(_links("757333")), {"title_stem": TITLE_STEM, "external_id": "743987"})


def test_unpinned_duplicate_titles_stay_ambiguous():
    module = _module()
    with pytest.raises(module.OfferError, match="portfolio_readback_invalid"):
        module._portfolio(Page(_links("757333", "743987")), {"title_stem": TITLE_STEM, "external_id": ""})


def test_pinned_portfolio_absent_never_reads_as_create_me():
    # None makes _ensure_portfolio create a new portfolio: a pinned row that did not render
    # is the likely origin of duplicate 757333. A pin with zero title matches is invalid.
    module = _module()
    with pytest.raises(module.OfferError, match="portfolio_readback_invalid"):
        module._portfolio(Page([]), {"title_stem": TITLE_STEM, "external_id": "743987"})
    assert module._portfolio(Page([]), {"title_stem": TITLE_STEM, "external_id": ""}) is None


def test_same_title_duplicates_are_surfaced():
    module = _module()
    found = module._portfolio(Page(_links("757333", "743987")), {"title_stem": TITLE_STEM, "external_id": "743987"})
    assert found["portfolio_duplicate_external_ids"] == ["757333"]


def test_roster_reports_same_title_duplicates():
    module = _module()
    item = {"title_stem": TITLE_STEM, "external_id": "743987"}
    module._portfolio = lambda page, value: (
        {"portfolio_external_id": "743987", "portfolio_duplicate_external_ids": ["757333"]}
        if value is item else {"portfolio_external_id": "743964"})
    page = SimpleNamespace(goto=lambda *a, **k: None, url="https://www.lancers.jp/myplan",
                           locator=lambda _s: SimpleNamespace(all=lambda: []))
    roster = module._roster(page, {"superseded_listing_ids": [], "portfolio": {"external_id": "743964"},
                                   "software_portfolio": item})
    assert roster["portfolio_duplicate_external_ids"] == {"portfolio": [], "software_portfolio": ["757333"]}


def test_query_string_on_a_duplicate_href_is_not_part_of_its_id():
    module = _module()
    links = _links("743987") + [Link(TITLE_STEM + "ました", "/profile/keiodaisuke/portfolio_popup/757333?ref=x")]
    found = module._portfolio(Page(links), {"title_stem": TITLE_STEM, "external_id": "743987"})
    assert found["portfolio_duplicate_external_ids"] == ["757333"]
