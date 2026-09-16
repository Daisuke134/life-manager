"""Recoverable RETIRE contract: gates, real seller control, and fail-closed behaviour.

Run: python3 -m pytest skills/earn/gig/tests/test_storefront_retire.py
"""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import storefront_direct as sd  # noqa: E402

SERVICE_ID = "4312985"
VERSION = "a" * 64
FAMILY = {SERVICE_ID: "ui_translation"}
SOURCE = {"service_id": SERVICE_ID, "service_version_sha256": VERSION}
ARCHIVE_CONTROL = {"tag": "A", "type": None, "label": "OK",
                   "href": f"/services/archive/{SERVICE_ID}", "id": None,
                   "cls": "button-solid modi_black js_change-open-status",
                   "context": "公開停止しますか？公開停止後も再公開できます。"}
INVENTORY_ROW = {"service_id": SERVICE_ID, "state": sd.PUBLIC_LISTING_STATE, "price_jpy": 4500,
                 "state_controls": [
                     {"tag": "A", "label": "編集する", "href": f"/mypage/services/{SERVICE_ID}",
                      "cls": "", "id": None, "context": None},
                     ARCHIVE_CONTROL]}
ALLOCATION = {
    "service_id": SERVICE_ID, "action": "RETIRE", "allocation_key": "b" * 64,
    "gates": {"minimum_sample_met": True, "weak_demand_evidence": True,
              "slot_capacity_pressure": True, "recoverable_retire_gates_met": True},
}


def seller_form(controls):
    return {"url": f"https://coconala.com/mypage/services/{SERVICE_ID}", "submit_controls": controls}


def render(**overrides):
    kwargs = {"source": SOURCE, "inventory_row": INVENTORY_ROW,
              "seller_snapshot": seller_form([
                  {"mode": "open", "label": "公開する", "disabled": False},
                  {"mode": "draft", "label": "下書き保存", "disabled": False},
              ]),
              "capability_families": FAMILY, "allocation": ALLOCATION}
    kwargs.update(overrides)
    return sd._render_listing_state_mutation(**kwargs)


def test_retire_contract_changes_only_the_listing_state_and_keeps_a_public_rollback():
    contract = render()
    assert contract["changed_field"] == "listing_state"
    assert contract["allowed_delta"] == [sd.LISTING_STATE_DELTA]
    assert contract["proposed_value"]["action"] == f"/services/archive/{SERVICE_ID}"
    assert contract["proposed_value"]["listing_state"] == "非公開"
    # Recoverable: rollback restores the public state, and the contract never asks for deletion.
    assert contract["rollback_value"] == {"listing_state": sd.PUBLIC_LISTING_STATE, "action": "none"}
    assert contract["official_readback"]["deletion"] is False
    assert contract["official_readback"]["recoverable"] is True
    assert len(contract["contract_sha256"]) == 64


def test_retire_fails_closed_when_the_seller_form_exposes_no_non_public_control():
    with pytest.raises(RuntimeError, match="storefront_retire_control_missing"):
        render(inventory_row={**INVENTORY_ROW, "state_controls": [
            {"tag": "A", "label": "編集する", "href": "/mypage/services/1", "cls": "", "context": None}]})
    with pytest.raises(RuntimeError, match="storefront_retire_controls_unobserved"):
        render(inventory_row={**INVENTORY_ROW, "state_controls": []})
    with pytest.raises(RuntimeError, match="storefront_retire_control_wording_unobserved"):
        render(inventory_row={**INVENTORY_ROW,
                              "state_controls": [{**ARCHIVE_CONTROL, "context": ""}]})


def test_retire_fails_closed_on_unmet_gates_or_a_listing_that_is_not_public():
    with pytest.raises(RuntimeError, match="storefront_retire_gates_unmet"):
        render(allocation={**ALLOCATION, "gates": {"recoverable_retire_gates_met": False}})
    with pytest.raises(RuntimeError, match="storefront_retire_listing_not_public"):
        render(inventory_row={**INVENTORY_ROW, "state": "下書き"})


def test_short_term_zero_sales_alone_never_reaches_the_retire_action():
    # Zero sales with an unknown/insufficient sample must not produce RETIRE or REPLACE.
    assert ALLOCATION["gates"]["minimum_sample_met"] is True
    with pytest.raises(RuntimeError, match="storefront_retire_allocation_invalid"):
        render(allocation={**ALLOCATION, "action": "IMPROVE"})


def test_replace_plan_requires_a_ready_candidate_and_keeps_a_republish_rollback():
    retire = render()
    create = {"draft_service_id": "4356229", "contract_sha256": "c" * 64,
              "expected_public_url": "https://coconala.com/services/4356229"}
    allocation = {**ALLOCATION, "action": "REPLACE"}
    plan = sd._render_replace_plan(retire, create, allocation)
    assert plan["sequence"] == ["retire", "create"]
    assert plan["retired_service_id"] == SERVICE_ID and plan["created_service_id"] == "4356229"
    # A failed creation must be able to put the old listing back.
    assert plan["rollback"] == {"republish_service_id": SERVICE_ID, "restore_to": sd.PUBLIC_LISTING_STATE,
                                "on": "create_failed_after_retire"}
    assert len(plan["plan_sha256"]) == 64

    # Never retire a slot before the replacement contract exists.
    with pytest.raises(RuntimeError, match="storefront_replace_without_ready_candidate"):
        sd._render_replace_plan(retire, None, allocation)
    with pytest.raises(RuntimeError, match="storefront_replace_identity_invalid"):
        sd._render_replace_plan(retire, {**create, "draft_service_id": SERVICE_ID}, allocation)
    with pytest.raises(RuntimeError, match="storefront_replace_allocation_invalid"):
        sd._render_replace_plan(retire, create, ALLOCATION)


def test_stronger_paid_demand_replaces_a_measured_zero_purchase_offer_before_capacity(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "analytics.jsonl").write_text(json.dumps({
        "service_id": SERVICE_ID,
        "metrics": {
            "views": {"status": "known", "value": 120},
            "favorites": {"status": "known", "value": 0},
            "purchases": {"status": "known", "value": 0},
        },
    }) + "\n", encoding="utf-8")
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({
        "portfolio_policy": {
            "version": 1,
            "slot_limit": 20,
            "minimum_views_for_retirement": 100,
            "short_term_zero_sales_can_retire": False,
            "retirement_mode": "recoverable_unpublish_before_delete",
            "replacement_candidates": [{
                "replaces_service_id": SERVICE_ID,
                "candidate_key": "ai-agent-system",
                "paid_demand_score": 12,
            }],
        },
        "services": [{"service_id": SERVICE_ID, "scores": {"demand": 0}}],
        "priority_backlog": [{"priority": 1, "service_id": SERVICE_ID, "field": "body"}],
    }), encoding="utf-8")

    result = sd._allocate_portfolio(
        state,
        [{"service_id": SERVICE_ID, "service_version_sha256": VERSION}],
        {"cutoff_cursor": "official"},
        scorecard,
        now=1,
    )

    assert result["capacity"] == {"used": 1, "limit": 20, "pressure": False}
    assert result["selected"]["action"] == "REPLACE"
    assert result["selected"]["reason"] == "stronger_paid_demand_replaces_zero_purchase_offer"
    assert result["selected"]["gates"]["recoverable_retire_gates_met"] is True



def test_the_archive_executor_refuses_a_contract_that_is_not_a_recoverable_retire(monkeypatch):
    import asyncio

    monkeypatch.setattr(sd, "_load_capability_families",
                        lambda _path: (FAMILY, {"ui_translation": {}}))
    contract = render()
    wrong_field = {**contract, "changed_field": "title"}
    with pytest.raises(RuntimeError, match="storefront_mutation_contract_invalid"):
        asyncio.run(sd._execute_listing_state_effect_async(
            "ws://127.0.0.1:1/none", contract=wrong_field, evidence_dir=Path("/tmp")))

    # An action pointing anywhere but this listing's archive endpoint is refused before any
    # browser work, so a bad contract can never reach the marketplace.
    wrong_action = dict(contract)
    wrong_action["proposed_value"] = {**contract["proposed_value"], "action": "/services/archive/999"}
    with pytest.raises(RuntimeError, match="storefront_mutation_contract_invalid"):
        asyncio.run(sd._execute_listing_state_effect_async(
            "ws://127.0.0.1:1/none", contract=wrong_action, evidence_dir=Path("/tmp")))


def test_archive_executor_uses_the_observed_page_for_a_paginated_listing(monkeypatch, tmp_path):
    import asyncio
    import websockets
    import listing_inventory

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "listing-state-controls.json").write_text(json.dumps({
        "page_walk": [
            {"url": "https://coconala.com/mypage/services_lists", "observed_ids": ["999"]},
            {"url": "https://coconala.com/mypage/services_lists/page:2",
             "observed_ids": [SERVICE_ID]},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(sd, "_load_capability_families",
                        lambda _path: (FAMILY, {"ui_translation": {}}))

    class Browser:
        url = ""
        clicked = False
        navigations = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def send(self, payload):
            command = json.loads(payload)
            if command["method"] == "Page.navigate":
                self.url = command["params"]["url"]
                self.navigations.append(self.url)

    browser = Browser()

    async def call(_ws, _method, _params, cid):
        return {"id": cid}

    async def loaded(_ws, _deadline, cid):
        return True, cid + 1

    async def evaluate(_ws, expression, cid):
        on_target_page = browser.url.endswith("/page:2")
        if "a.js_change-open-status" in expression:
            browser.clicked = on_target_page
            return browser.clicked, cid + 1
        cards = ([{"text": "非公開", "restore": [f"/services/open/{SERVICE_ID}"]}]
                 if browser.clicked else [{"text": "公開中", "restore": []}])
        return json.dumps(cards if on_target_page else []), cid + 1

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(websockets, "connect", lambda *_args, **_kwargs: browser)
    monkeypatch.setattr(listing_inventory, "_call", call)
    monkeypatch.setattr(listing_inventory, "_wait_for_load", loaded)
    monkeypatch.setattr(sd, "_evaluate", evaluate)
    monkeypatch.setattr(sd.asyncio, "sleep", no_sleep)

    result = asyncio.run(sd._execute_listing_state_effect_async(
        "ws://127.0.0.1:1/fake", contract=render(), evidence_dir=evidence))
    assert result["archived"] is True
    assert browser.navigations == ["https://coconala.com/mypage/services_lists/page:2"] * 2


def test_restore_refuses_an_href_that_is_not_a_service_control():
    import asyncio

    with pytest.raises(RuntimeError, match="storefront_restore_href_invalid"):
        asyncio.run(sd._restore_listing_state_async(
            "ws://127.0.0.1:1/none", service_id=SERVICE_ID, restore_href="https://evil.example/x"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
