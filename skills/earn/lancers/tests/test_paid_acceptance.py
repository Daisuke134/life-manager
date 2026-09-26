"""Life Manager accepts a won Lancers order by itself (SSOT §5.2 item 7-0a).

Fixture-driven against an injected fake provider double (never a real browser):
terms match -> exactly one accept effect + readback closes; mismatch -> no
click, typed ``acceptance_terms_mismatch``; an uncertain post-click readback
never replays the click and only closes once official readback confirms it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
KERNEL_PATH = ROOT / "skills/_shared/marketplace-core/scripts/paid_kernel.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


paid_kernel = _load("lancers_test_paid_kernel_for_acceptance", KERNEL_PATH)
paid_adapter = _load("lancers_test_paid_adapter_for_acceptance", SCRIPTS / "paid_adapter.py")

CANDIDATE = {
    "source_kind": "project_acceptance",
    "provider_id": "5605912",
    "proposal_id": "27969614",
    "board_id": None,
    "detail_path": "/project/approval/start/5605912",
    "funding_status": "awaiting_acceptance",
}


def _snapshot(candidates: list[dict]) -> dict:
    return {"ok": True, "source_complete": True, "boards": [], "finance": {},
            "contract_candidates": candidates}


class FakeAcceptanceProvider:
    """Stands in for the real browser driver: no click ever reaches Lancers."""

    def __init__(self, *, verified_price: int = 300, verified_due: str = "2026-09-30",
                 order_amount: int = 300, order_due: str = "2026-09-30",
                 milestone_count: int = 1):
        self.verified_price = verified_price
        self.verified_due = verified_due
        self.order_amount = order_amount
        self.order_due = order_due
        self.milestone_count = milestone_count
        self.confirmed = False
        self.accept_calls: list[dict] = []

    def read_detail(self, candidate: dict) -> dict:
        project_id, proposal_id = candidate["provider_id"], candidate["proposal_id"]
        if self.confirmed:
            return {"provider_state": "accepted_confirmed",
                    "project_id": project_id, "proposal_id": proposal_id}
        return {
            "provider_state": "awaiting_acceptance",
            "project_id": project_id, "proposal_id": proposal_id,
            "verified_price_jpy": self.verified_price,
            "verified_delivery_due_on": self.verified_due,
            "order_amount_jpy": self.order_amount,
            "order_delivery_due_on": self.order_due,
            "order_milestone_count": self.milestone_count,
            "accept_form_action": f"/project/approval/finish_yes/{project_id}",
            "accept_fields": {"_method": "POST", "data[Work][agree]": "1"},
        }

    def accept_order(self, intent: dict, detail: dict) -> None:
        self.accept_calls.append(dict(intent))

    def readback(self, intent: dict, detail: dict) -> dict:
        if intent.get("action") != "accept":
            return {"verified": False, "authoritative_absent": False}
        if self.confirmed:
            return {"verified": True, "provider_receipt_id": "receipt-5605912",
                    "observed_at": "2026-09-26T00:00:00Z"}
        return {"verified": False, "authoritative_absent": False}


def _adapter(tmp_path: Path, provider: FakeAcceptanceProvider) -> "paid_adapter.LancersPaidAdapter":
    return paid_adapter.LancersPaidAdapter(
        account_id="keiodaisuke",
        inventory_reader=lambda: _snapshot([CANDIDATE]),
        provider=provider,
        state_path=tmp_path / "application.json",
    )


def test_decide_accepts_when_order_matches_the_verified_proposal():
    contract = {
        "project_id": "5605912", "proposal_id": "27969614",
        "verified_price_jpy": 300, "verified_delivery_due_on": "2026-09-30",
        "order_amount_jpy": 300, "order_delivery_due_on": "2026-09-30",
        "order_milestone_count": 1,
    }
    decision = paid_adapter.decide({"context": {"contract": {
        **contract, "provider_state": "awaiting_acceptance"}}})
    assert decision == {"action": "accept", "payload": {
        "project_id": "5605912", "proposal_id": "27969614",
        "order_amount_jpy": 300, "order_delivery_due_on": "2026-09-30",
    }}


def test_decide_never_accepts_when_amount_or_deadline_differs():
    contract = {
        "provider_state": "awaiting_acceptance",
        "project_id": "5605912", "proposal_id": "27969614",
        "verified_price_jpy": 300, "verified_delivery_due_on": "2026-09-30",
        "order_amount_jpy": 500, "order_delivery_due_on": "2026-10-05",
        "order_milestone_count": 1,
    }
    decision = paid_adapter.decide({"context": {"contract": contract}})
    assert decision["action"] == "wait"
    assert decision["reason"] == "acceptance_terms_mismatch"
    assert any("amount mismatch" in line for line in decision["remaining_work"])
    assert any("deadline mismatch" in line for line in decision["remaining_work"])


def test_terms_match_issues_exactly_one_accept_and_readback_closes(tmp_path: Path) -> None:
    provider = FakeAcceptanceProvider()

    def accept_then_confirm(intent: dict, detail: dict) -> None:
        provider.accept_calls.append(dict(intent))
        provider.confirmed = True

    provider.accept_order = accept_then_confirm
    adapter = _adapter(tmp_path, provider)

    result = paid_kernel.run_wake(adapter=adapter, decide=paid_adapter.decide,
                                  state_root=tmp_path / "state")

    assert len(provider.accept_calls) == 1
    assert result["effect"] == 1
    assert result["readback"] == 1
    assert result["items"][0]["status"] == "verified"


def test_terms_mismatch_never_clicks_accept(tmp_path: Path) -> None:
    provider = FakeAcceptanceProvider(order_amount=999)
    adapter = _adapter(tmp_path, provider)

    result = paid_kernel.run_wake(adapter=adapter, decide=paid_adapter.decide,
                                  state_root=tmp_path / "state")

    assert provider.accept_calls == []
    assert result["effect"] == 0
    assert result["items"][0]["reason"] == "acceptance_terms_mismatch"


def test_uncertain_readback_after_the_click_never_replays_until_confirmed(
        tmp_path: Path) -> None:
    provider = FakeAcceptanceProvider()
    state_root = tmp_path / "state"
    adapter = _adapter(tmp_path, provider)

    first = paid_kernel.run_wake(adapter=adapter, decide=paid_adapter.decide,
                                 state_root=state_root)
    assert len(provider.accept_calls) == 1
    assert first["effect"] == 1
    assert first["readback"] == 0
    assert first["items"][0]["reason"] == "reconcile_unknown"

    second = paid_kernel.run_wake(adapter=adapter, decide=paid_adapter.decide,
                                  state_root=state_root)
    assert len(provider.accept_calls) == 1, "no second click while the effect is unknown"
    assert second["effect"] == 0
    assert second["items"][0]["reason"] == "reconcile_unknown"

    provider.confirmed = True
    third = paid_kernel.run_wake(adapter=adapter, decide=paid_adapter.decide,
                                 state_root=state_root)
    assert len(provider.accept_calls) == 1, "official readback closes it, no extra click"
    assert third["effect"] == 0
    assert third["readback"] == 1
    assert third["items"][0]["status"] == "completed"
