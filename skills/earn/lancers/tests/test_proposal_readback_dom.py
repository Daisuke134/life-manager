from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "skills/earn/lancers/scripts/application_tick.py"


def _module():
    spec = importlib.util.spec_from_file_location("lancers_proposal_readback_dom_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Locator:
    def __init__(self, *, items=None, text="", attributes=None, children=None):
        self.items = list(items) if items is not None else [self]
        self.text = text
        self.attributes = attributes or {}
        self.children = children or {}

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]

    def inner_text(self):
        return self.text

    def get_attribute(self, name):
        return self.attributes.get(name)

    def locator(self, selector):
        return self.children[selector]


class _Page:
    def __init__(self, project_id):
        self.project_id = project_id
        self.url = "https://www.lancers.jp/mypage/proposals"
        self._heading = _Locator(
            text="SNS・AI業務設計室 さんの提案",
            attributes={"href": "/work/proposal/27922946"},
        )
        self._profile = _Locator(attributes={"href": "/profile/keiodaisuke"})
        self._card = _Locator(
            attributes={"id": "js-list-item-27922946"},
            children={
                'a.p-proposal-list__heading__title': self._heading,
                'a[href^="/profile/"]': self._profile,
            },
        )

    def goto(self, url, **_kwargs):
        self.url = url

    def locator(self, selector):
        if selector == f'a[href="/work/detail/{self.project_id}"]':
            return _Locator(attributes={"href": f"/work/detail/{self.project_id}"})
        if selector == f'a[href^="/work/proposals/{self.project_id}/"][href$="?ref=mypage_control"]':
            return _Locator(
                text="提案をみる",
                attributes={"href": f"/work/proposals/{self.project_id}/keiodaisuke?ref=mypage_control"},
            )
        if selector == 'meta[property="og:url"]':
            return _Locator(attributes={"content": f"https://www.lancers.jp/work/proposals/{self.project_id}/keiodaisuke"})
        if selector == "a.p-simpleProposal-list__heading-title":
            return _Locator(items=[])
        if selector == "a.p-proposal-list__heading__title":
            return _Locator(items=[self._heading])
        if selector == '[id^="js-list-item-"]':
            return _Locator(items=[self._card])
        if selector == 'div#js-list-item-27922946':
            return self._card
        raise AssertionError(selector)


def test_reader_accepts_current_lancers_proposal_list_dom():
    module = _module()
    project_id = "5601290"

    assert module._default_proposal_reader(_Page(project_id), project_id) == {
        "proposal_id": "27922946",
        "project_id": project_id,
    }
