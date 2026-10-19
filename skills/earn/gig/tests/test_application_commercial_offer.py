from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import inspect
import sys
import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("application_parent", SCRIPTS / "application_parent.py")
assert SPEC and SPEC.loader
application_parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(application_parent)
gig_disk_guard = importlib.import_module("gig_disk_guard")


@pytest.fixture(autouse=True)
def _runtime_occurrence(monkeypatch):
    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", "test-run")
    monkeypatch.setenv(
        "LIFE_MANAGER_OCCURRENCE_ID",
        "hf-gig-apply-direct:test-run",
    )


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


AB_EXPERIMENT = {
    "id": "coconala-bid-budget-lower-bound-v1", "mode": "ab", "policy": "budget_lower_bound",
}


def _ab_contract(request_ids, *, experiment=AB_EXPERIMENT, adopted=None, budget=(3_000, 10_000)):
    snapshot = {"request_details": [
        {"request_id": rid, "budget_min_jpy": budget[0], "budget_max_jpy": budget[1],
         "visible_text": "募集内容"}
        for rid in request_ids
    ]}
    decisions = {"decisions": [
        {"request_id": rid, "business_class": "submit_required", "price_jpy": 8_000,
         "proposal_text": "要件に沿って業務自動化の仕組みを8,000円で構築します。", "deliver_date": "2026-11-01"}
        for rid in request_ids
    ]}
    rows = application_parent.apply_commercial_offer_contract(
        snapshot, decisions, experiment=experiment, adopted_bid_policy=adopted,
    )["decisions"]
    return {row["request_id"]: row for row in rows}


def _ids_by_arm():
    arms = {}
    for number in range(5_000_000, 5_000_100):
        arms.setdefault(
            application_parent.assign_arm(AB_EXPERIMENT["id"], str(number)), str(number)
        )
    return arms["A"], arms["B"]


def test_ab_experiment_records_arm_and_prices_b_at_budget_lower_bound() -> None:
    a_id, b_id = _ids_by_arm()
    rows = _ab_contract([a_id, b_id])

    assert rows[a_id]["price_jpy"] == 8_000
    assert rows[b_id]["price_jpy"] == 3_000
    assert "3,000円で対応" in rows[b_id]["proposal_text"]
    assert "8,000円" not in rows[b_id]["proposal_text"]
    assert "8,000円で構築" in rows[a_id]["proposal_text"]
    for rid, arm in ((a_id, "A"), (b_id, "B")):
        assert rows[rid]["experiment_id"] == AB_EXPERIMENT["id"]
        assert rows[rid]["experiment_arm"] == arm


def test_b_price_rewrites_the_planner_amount_in_the_proposal_body() -> None:
    text = application_parent._restate_price(
        "8,000円で対応します。8000円の範囲で、¥8,000以内。別件18,000円は対象外です。", 8_000, 3_000,
    )
    assert text == "3,000円で対応します。3,000円の範囲で、¥3,000以内。別件18,000円は対象外です。"


def test_requests_without_a_budget_range_stay_outside_the_experiment() -> None:
    _, b_id = _ids_by_arm()
    row = _ab_contract([b_id], budget=(None, None))[b_id]

    assert row["price_jpy"] == 8_000
    assert "experiment_arm" not in row and "experiment_id" not in row


def test_adopted_policy_prices_every_ranged_request_at_the_lower_bound() -> None:
    a_id, _ = _ids_by_arm()
    row = _ab_contract([a_id], experiment=None, adopted="budget_lower_bound")[a_id]

    assert row["price_jpy"] == 3_000
    assert "experiment_arm" not in row


def test_application_and_ledger_rows_carry_experiment_arm(tmp_path) -> None:
    detail = {
        "request_id": "123", "category": "IT・プログラミング", "title": "自動化",
        "canonical_url": "https://coconala.com/requests/123", "visible_text": "募集内容",
    }
    decision = {"price_jpy": 3_000, "deliver_date": "2026-08-20",
                "experiment_id": AB_EXPERIMENT["id"], "experiment_arm": "B"}
    row = application_parent._application_row(detail, decision)
    assert (row["experiment_id"], row["experiment_arm"]) == (AB_EXPERIMENT["id"], "B")

    effects = object.__new__(application_parent.CdpParentEffects)
    effects._fresh_details = {"123": detail}
    effects._submitted_paths = {}
    effects._readback_paths = {}
    effects.ledger_path = tmp_path / "applied.jsonl"
    effects.pass_id = "pass-1"
    effects.instant_work_event_publisher = None
    effects.canonical_ledger_append(row)
    written = application_parent.json.loads(effects.ledger_path.read_text(encoding="utf-8"))
    assert (written["experiment_id"], written["experiment_arm"]) == (AB_EXPERIMENT["id"], "B")


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


def test_explicit_disk_policy_is_rechecked_before_irreversible_submit(tmp_path, monkeypatch) -> None:
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
        "work_frequency": None,
        "weekly_hours_min": None,
        "weekly_hours_max": None,
        "screening_answers": [],
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
    assert results[0]["status"] == "pre_submit_aborted:pre_submit_disk_policy:ParentContractError"
    assert results[0]["error"] == "disk_policy_stop_or_unavailable"


def test_missing_runtime_occurrence_identity_stops_before_browser_effect(tmp_path, monkeypatch):
    snapshot = _single_application_snapshot()
    decisions = {"decisions": [{
        "request_id": "123",
        "business_class": "submit_required",
        "reason_codes": [],
        "proposal_text": application_parent.commercial_proposal_text(
            "既存業務の自動化を設計から検証まで担当します。" * 8,
            price_jpy=20_000,
            deliver_date="2026-09-01",
        ),
        "price_jpy": 20_000,
        "deliver_date": "2026-09-01",
        "work_frequency": None,
        "weekly_hours_min": None,
        "weekly_hours_max": None,
        "screening_answers": [],
    }]}
    effects = application_parent.FixtureEffects(snapshot, {})
    monkeypatch.delenv("LIFE_MANAGER_RUN_ID")
    monkeypatch.delenv("LIFE_MANAGER_OCCURRENCE_ID")

    with pytest.raises(
        application_parent.ParentContractError,
        match="runtime_occurrence_binding_required",
    ):
        application_parent.commit_decisions(
            snapshot,
            decisions,
            store=application_parent.fence.IntentStore(tmp_path),
            effects=effects,
        )

    assert effects.open_count == 0
    assert effects.click_count == 0


def test_missing_authenticated_identity_stops_before_irreversible_marker(
    tmp_path, monkeypatch
) -> None:
    class MissingIdentity(application_parent.FixtureEffects):
        def capture_authenticated_identity(self, request_id: str) -> dict[str, object]:
            raise application_parent.ParentContractError("authenticated_identity_readback_missing")

    snapshot = _single_application_snapshot()
    decisions = {"decisions": [{
        "request_id": "123",
        "business_class": "submit_required",
        "reason_codes": [],
        "proposal_text": application_parent.commercial_proposal_text(
            "既存業務の自動化を設計から検証まで担当します。" * 8,
            price_jpy=20_000,
            deliver_date="2026-09-01",
        ),
        "price_jpy": 20_000,
        "deliver_date": "2026-09-01",
        "work_frequency": None,
        "weekly_hours_min": None,
        "weekly_hours_max": None,
        "screening_answers": [],
    }]}
    effects = MissingIdentity(snapshot, {})
    monkeypatch.setattr(gig_disk_guard, "disk_headroom_ok", lambda: True)
    store = application_parent.fence.IntentStore(tmp_path)

    results = application_parent.commit_decisions(
        snapshot, decisions, store=store, effects=effects,
    )

    assert results[0]["status"] == (
        "pre_submit_aborted:authenticated_identity_capture:ParentContractError"
    )
    assert effects.click_count == 1  # confirmation only; final submit was never clicked
    intent = store.read("123")
    assert intent["effect_phase"] == application_parent.fence.PRE_EFFECT
    assert intent["state"] == application_parent.fence.RETIRED_ABSENT


def test_old_effect_started_intent_stays_fenced_out_of_foreground_apply(tmp_path) -> None:
    snapshot = _single_application_snapshot()
    proposal = application_parent.commercial_proposal_text(
        "既存業務の自動化を設計から検証まで担当します。" * 8,
        price_jpy=20_000, deliver_date="2026-09-01",
    )
    decisions = {"decisions": [{
        "request_id": "123", "business_class": "submit_required", "reason_codes": [],
        "proposal_text": proposal, "price_jpy": 20_000,
        "deliver_date": "2026-09-01", "work_frequency": None,
        "weekly_hours_min": None, "weekly_hours_max": None,
        "screening_answers": [],
    }]}
    store = application_parent.fence.IntentStore(tmp_path)
    payload = application_parent.fence.intent_payload(
        request_id="123", snapshot_sha256="a" * 64,
        proposal_text=proposal, price_jpy=20_000,
        deliver_date="2026-09-01",
        lease_fence={"task": "prior-run", "token": "b" * 32, "generation": 1},
    )
    with store.locked("123"):
        application_parent.fence._durable_replace(store.intent_path("123"), payload)
        store.mark_irreversible_attempt_started_locked(
            "123",
            expected_cas=payload["cas"],
            runtime_run_id="test-run",
            runtime_occurrence_id="hf-gig-apply-direct:test-run",
        )
    effects = application_parent.FixtureEffects(snapshot, {})

    result = application_parent.commit_decisions(snapshot, decisions, store=store, effects=effects)

    assert result[0]["status"] == "background_reconcile_pending"
    assert effects.exact_id_readback_ids == []
    assert effects.click_count == 0
    assert store.read("123")["state"] == application_parent.fence.PREPARED


def test_same_wake_effect_started_intent_gets_exact_readback(tmp_path) -> None:
    snapshot = _single_application_snapshot()
    proposal = application_parent.commercial_proposal_text(
        "既存業務の自動化を設計から検証まで担当します。" * 8,
        price_jpy=20_000, deliver_date="2026-09-01",
    )
    decision = {"decisions": [{
        "request_id": "123", "business_class": "submit_required", "reason_codes": [],
        "proposal_text": proposal, "price_jpy": 20_000,
        "deliver_date": "2026-09-01", "work_frequency": None,
        "weekly_hours_min": None, "weekly_hours_max": None,
        "screening_answers": [],
    }]}
    store = application_parent.fence.IntentStore(tmp_path)
    payload = application_parent.fence.intent_payload(
        request_id="123", snapshot_sha256="a" * 64,
        proposal_text=proposal, price_jpy=20_000,
        deliver_date="2026-09-01",
        lease_fence={"task": "test-pass-commit-123", "token": "b" * 32, "generation": 1},
    )
    with store.locked("123"):
        application_parent.fence._durable_replace(store.intent_path("123"), payload)
        store.mark_irreversible_attempt_started_locked(
            "123",
            expected_cas=payload["cas"],
            runtime_run_id="test-run",
            runtime_occurrence_id="hf-gig-apply-direct:test-run",
        )
    effects = application_parent.FixtureEffects(snapshot, {"official_applied_ids": ["123"]})

    result = application_parent.commit_decisions(snapshot, decision, store=store, effects=effects)

    assert result[0]["status"] == "reconciled_confirmed"
    assert effects.exact_id_readback_ids == ["123"]
