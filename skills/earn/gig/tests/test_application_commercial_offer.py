from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import inspect
import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("application_parent", SCRIPTS / "application_parent.py")
assert SPEC and SPEC.loader
application_parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(application_parent)
gig_disk_guard = importlib.import_module("gig_disk_guard")


def _single_application_snapshot() -> dict[str, object]:
    return application_parent.snapshot_contract.build_envelope({
        "pass_id": "test-pass",
        "lease_fence": {"task": "test", "token": "1" * 32, "generation": 1},
        "observed_at": "2026-08-23T00:00:00Z",
        "objective": {
            "target_applications": 1,
            "max_applications": 1,
            "required_search_source_ids": ["source"],
        },
        "search_sources": [{
            "source_id": "source",
            "url": "https://coconala.com/requests",
            "page_index": 1,
            "card_request_ids": ["123"],
            "has_next": False,
            "exhausted": True,
            "screenshot_sha256": "2" * 64,
            "dom_sha256": "3" * 64,
        }],
        "request_details": [{
            "request_id": "123",
            "canonical_url": "https://coconala.com/requests/123",
            "title": "自動化",
            "category": "IT・プログラミング",
            "visible_text": "募集内容\n業務自動化をお願いします。",
            "accepting_applications": True,
            "budget_min_jpy": 10_000,
            "budget_max_jpy": 30_000,
            "applicants_count": 0,
            "contracted_count": 0,
            "applicants": [],
            "observed_at": "2026-08-23T00:00:00Z",
        }],
        "already_applied_ids": [],
    })


def test_source_navigation_reuses_the_bounded_timeout_retry(monkeypatch) -> None:
    effects = object.__new__(application_parent.CdpParentEffects)
    effects.ws_url = "ws://example.invalid/devtools/page/1"
    calls = {"retry": 0}

    class Connection:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    async def call(_ws, _method, _params, _call_id):
        return {}

    async def retry(_ws, _url, _call_id):
        calls["retry"] += 1
        return 3

    async def plain_navigation(*_args):
        raise AssertionError("source navigation must use the bounded retry path")

    async def evaluate(_ws, _expression, call_id):
        return {
            "url": "https://coconala.com/requests/categories/1",
            "title": "requests",
            "text": "",
            "hrefs": [],
            "next_href": None,
            "access_denied": False,
            "not_found": False,
        }, call_id + 1

    async def screenshot(_ws, call_id):
        return b"png", call_id + 1

    async def connect(_url):
        return Connection()

    monkeypatch.setattr(application_parent, "_cdp_connect", connect)
    monkeypatch.setattr(effects, "_call", call)
    monkeypatch.setattr(effects, "_navigate_retry_once", retry)
    monkeypatch.setattr(effects, "_navigate", plain_navigation)
    monkeypatch.setattr(effects, "_eval_json", evaluate)
    monkeypatch.setattr(effects, "_screenshot", screenshot)

    page, screenshot_bytes = asyncio.run(
        effects._source_async("source", "https://coconala.com/requests/categories/1")
    )

    assert calls == {"retry": 1}
    assert page["title"] == "requests"
    assert screenshot_bytes == b"png"


def test_commercial_offer_preserves_planner_price() -> None:
    detail = {"budget_min_jpy": 10_000, "budget_max_jpy": 30_000}

    assert application_parent.commercial_offer_price(detail, planner_price_jpy=15_000) == 15_000


def test_application_does_not_navigate_competitor_profiles() -> None:
    source = inspect.getsource(application_parent.CdpParentEffects._detail_async)

    assert "coconala.com/users/" not in source


def test_confirmed_application_records_pricing_version() -> None:
    row = application_parent._application_row(
        {
            "request_id": "123",
            "category": "IT・プログラミング",
            "title": "自動化",
            "canonical_url": "https://coconala.com/requests/123",
        },
        {"price_jpy": 45_000, "deliver_date": "2026-08-20"},
    )

    assert row["pricing_basis"] == "planner_selected_v1"


def test_proposal_opens_with_commitment_and_has_no_pre_contract_question() -> None:
    proposal = application_parent.commercial_proposal_text(
        "詳細をご共有いただけますか？要件に沿ってLINE Botを構築します。",
        price_jpy=99_000,
        deliver_date="2026-08-20",
    )

    assert proposal.startswith("対応可能です。")
    assert "？" not in proposal and "?" not in proposal
    assert "99,000円" in proposal
    assert "2026-08-20" in proposal
    assert "契約範囲内でご納得いただけるまで" in proposal


def test_disk_headroom_is_rechecked_before_irreversible_submit(tmp_path, monkeypatch) -> None:
    snapshot = _single_application_snapshot()
    decisions = {"decisions": [{
        "request_id": "123",
        "business_class": "submit_required",
        "reason_codes": [],
        "proposal_text": application_parent.commercial_proposal_text(
            "ご指定の業務自動化を設計から実装、検証まで一貫して進めます。"
            "既存の運用を確認し、必要な処理を整理した上で安全に導入します。" * 4,
            price_jpy=20_000,
            deliver_date="2026-09-01",
        ),
        "price_jpy": 20_000,
        "deliver_date": "2026-09-01",
    }]}
    effects = application_parent.FixtureEffects(snapshot, {})
    monkeypatch.setattr(gig_disk_guard, "disk_headroom_ok", lambda: False)

    results = application_parent.commit_decisions(
        snapshot,
        decisions,
        store=application_parent.fence.IntentStore(tmp_path),
        effects=effects,
    )

    assert effects.click_count == 1
    assert results[0]["status"] == "pre_submit_aborted:pre_submit_headroom:ParentContractError"
