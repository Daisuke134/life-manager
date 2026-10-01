from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


PATH = Path(__file__).resolve().parents[1] / "scripts" / "application_tick.py"


def load():
    spec = importlib.util.spec_from_file_location("crowdworks_application_history_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Locator:
    def __init__(self, *, items=None, text="", attrs=None, children=None):
        self.items = list(items or [])
        self.text = text
        self.attrs = dict(attrs or {})
        self.children = dict(children or {})

    def count(self):
        return len(self.items) if self.items else 1

    def nth(self, index):
        return self.items[index]

    def get_attribute(self, name):
        return self.attrs.get(name)

    def inner_text(self):
        return self.text

    def locator(self, selector):
        return self.children.get(selector, _Locator(items=[]))


class _Page:
    def __init__(self, module):
        self.module = module
        self.url = "about:blank"
        self.goto_log = []
        self.page_rows = {
            1: ["101", "102"],
            2: ["103"],
        }
        self.details = {
            "101": ("9001", "7001", "2026年09月29日 10:11"),
            "102": ("9002", "7002", "2026年09月28日 09:10"),
            "103": ("9003", "7001", "2026年09月27日 08:09"),
        }

    def goto(self, url):
        self.goto_log.append(url)
        self.url = url

    def _page_number(self):
        if "?page=" not in self.url:
            return 1
        return int(self.url.rsplit("?page=", 1)[1])

    def locator(self, selector):
        if selector == self.module._TABLE_SELECTOR:
            links = [
                _Locator(attrs={"href": f"/proposals/{proposal_id}"})
                for proposal_id in self.page_rows[self._page_number()]
            ]
            return _Locator(
                children={
                    'a[href^="/proposals/"]': _Locator(items=links),
                }
            )
        if selector == 'a[href*="/e/proposals?page="]':
            return _Locator(
                items=[
                    _Locator(attrs={"href": "/e/proposals?page=2"}),
                ]
            )
        if selector == self.module._HISTORY_JOB_SELECTOR:
            proposal_id = self.url.rsplit("/", 1)[1]
            job_id, _buyer_id, _created_at = self.details[proposal_id]
            return _Locator(items=[_Locator(attrs={"href": f"/public/jobs/{job_id}"})])
        if selector == self.module._HISTORY_EMPLOYER_SELECTOR:
            proposal_id = self.url.rsplit("/", 1)[1]
            _job_id, buyer_id, _created_at = self.details[proposal_id]
            return _Locator(items=[_Locator(attrs={"href": f"/public/employers/{buyer_id}"})])
        if selector == self.module._HISTORY_CREATED_AT_SELECTOR:
            proposal_id = self.url.rsplit("/", 1)[1]
            _job_id, _buyer_id, created_at = self.details[proposal_id]
            return _Locator(text=created_at)
        return _Locator(items=[])


class _ContractLocator:
    def __init__(self, *, items=None, attrs=None, children=None):
        self.items = list(items or [])
        self.attrs = dict(attrs or {})
        self.children = dict(children or {})

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]

    def get_attribute(self, name):
        return self.attrs.get(name)

    def locator(self, selector):
        return self.children.get(selector, _ContractLocator())


class _ContractPage(_Page):
    def goto(self, url):
        super().goto(url)
        if url.endswith("/proposals/104"):
            self.url = "https://crowdworks.jp/contracts/9004"

    def locator(self, selector):
        if selector == self.module._HISTORY_CONTRACT_TABLE_SELECTOR:
            return _ContractLocator(
                items=[object()],
                children={
                    self.module._HISTORY_JOB_SELECTOR: _ContractLocator(
                        items=[_ContractLocator(attrs={"href": "/public/jobs/904"})]
                    ),
                    self.module._HISTORY_EMPLOYER_SELECTOR: _ContractLocator(
                        items=[_ContractLocator(attrs={"href": "/public/employers/704"})]
                    ),
                },
            )
        if selector == self.module._HISTORY_THREAD_SELECTOR:
            def message(timestamp):
                return _ContractLocator(
                    children={
                        self.module._HISTORY_THREAD_SENT_SELECTOR: _ContractLocator(items=[object()]),
                        self.module._HISTORY_THREAD_TIME_SELECTOR: _ContractLocator(
                            items=[_ContractLocator(attrs={"datetime": timestamp})]
                        ),
                    }
                )

            return _ContractLocator(
                items=[object()],
                attrs={
                    "data": json.dumps(
                        {"messageableType": "Contract", "proposalId": 104},
                        separators=(",", ":"),
                    )
                },
                children={
                    self.module._HISTORY_THREAD_MESSAGE_SELECTOR: _ContractLocator(
                        items=[
                            message("2026年09月27日 15:55"),
                            message("2026年09月28日 16:56"),
                        ]
                    )
                },
            )
        return super().locator(selector)


def test_history_detail_reads_redirected_contract_thread_without_sidebar_ids():
    module = load()
    page = _ContractPage(module)

    assert module._read_history_detail(page, "104") == {
        "application_external_id": "104",
        "external_id": "904",
        "buyer_external_id": "704",
        "submitted_at": "2026-09-27T15:55:00+09:00",
    }


def test_history_walk_reads_every_official_page_and_normalizes_japanese_timestamp():
    module = load()
    page = _Page(module)

    snapshot = module.read_application_history(page, max_pages=10)

    assert snapshot == {
        "history": [
            {
                "application_external_id": "101",
                "external_id": "9001",
                "buyer_external_id": "7001",
                "submitted_at": "2026-09-29T10:11:00+09:00",
            },
            {
                "application_external_id": "102",
                "external_id": "9002",
                "buyer_external_id": "7002",
                "submitted_at": "2026-09-28T09:10:00+09:00",
            },
            {
                "application_external_id": "103",
                "external_id": "9003",
                "buyer_external_id": "7001",
                "submitted_at": "2026-09-27T08:09:00+09:00",
            },
        ],
        "complete": True,
        "pages_read": 2,
        "page_count": 2,
    }
    assert page.goto_log == [
        "https://crowdworks.jp/e/proposals",
        "https://crowdworks.jp/proposals/101",
        "https://crowdworks.jp/proposals/102",
        "https://crowdworks.jp/e/proposals?page=2",
        "https://crowdworks.jp/proposals/103",
    ]


def test_history_detail_gets_one_bounded_retry_for_transient_read_failure():
    module = load()
    page = _Page(module)
    original = module._read_history_detail
    attempts = {"102": 0}

    def flaky(current_page, proposal_id):
        if proposal_id == "102" and attempts[proposal_id] == 0:
            attempts[proposal_id] += 1
            raise ValueError("transient_dom_read")
        return original(current_page, proposal_id)

    module._read_history_detail = flaky
    snapshot = module.read_application_history(page, max_pages=10)

    assert snapshot["complete"] is True
    assert attempts["102"] == 1


def test_history_walk_fails_closed_when_a_detail_cannot_be_read():
    module = load()
    page = _Page(module)
    page.details.pop("102")

    snapshot = module.read_application_history(page, max_pages=10)

    assert snapshot["complete"] is False
    assert snapshot["pages_read"] == 2
    assert [row["application_external_id"] for row in snapshot["history"]] == ["101", "103"]


def test_incremental_history_cache_advances_one_page_then_reads_without_detail_navigation(tmp_path):
    module = load()
    cache_path = tmp_path / "application-history.json"

    first_page = _Page(module)
    first = module.read_application_history(
        first_page, max_pages=10, cache_path=cache_path, page_budget=1
    )
    assert first["complete"] is False
    assert first["pages_read"] == 1
    assert first["cache_hit"] is False

    second_page = _Page(module)
    second = module.read_application_history(
        second_page, max_pages=10, cache_path=cache_path, page_budget=1
    )
    assert second["complete"] is True
    assert second["pages_read"] == 2
    assert second["cache_hit"] is False

    cached_page = _Page(module)
    cached = module.read_application_history(
        cached_page, max_pages=10, cache_path=cache_path, page_budget=1
    )
    assert cached["complete"] is True
    assert cached["cache_hit"] is True
    assert cached_page.goto_log == ["https://crowdworks.jp/e/proposals"]


def test_history_cache_status_is_bounded_and_distinguishes_missing_syncing_complete(tmp_path):
    module = load()
    cache_path = tmp_path / "application-history.json"

    assert module.history_cache_status(cache_path) == {
        "status": "missing",
        "complete": False,
        "pages_read": 0,
        "page_count": None,
        "next_page": 1,
    }

    page = _Page(module)
    module.read_application_history(
        page, max_pages=10, cache_path=cache_path, page_budget=1
    )
    syncing = module.history_cache_status(cache_path)
    assert syncing["status"] == "syncing"
    assert syncing["complete"] is False
    assert syncing["pages_read"] == 1
    assert set(syncing) == {"status", "complete", "pages_read", "page_count", "next_page"}
