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
    }


def test_pinned_portfolio_missing_among_same_title_rows_stays_invalid():
    module = _module()
    with pytest.raises(module.OfferError, match="portfolio_readback_invalid"):
        module._portfolio(Page(_links("757333")), {"title_stem": TITLE_STEM, "external_id": "743987"})


def test_unpinned_duplicate_titles_stay_ambiguous():
    module = _module()
    with pytest.raises(module.OfferError, match="portfolio_readback_invalid"):
        module._portfolio(Page(_links("757333", "743987")), {"title_stem": TITLE_STEM, "external_id": ""})
