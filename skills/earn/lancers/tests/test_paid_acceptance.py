"""Life Manager accepts a won Lancers order by itself (SSOT §5.2 item 7-0a).

Fixture-driven against an injected fake provider double (never a real browser):
terms match -> exactly one accept effect + readback closes; mismatch -> no
click, typed ``acceptance_terms_mismatch``; an uncertain post-click readback
never replays the click and only closes once official readback confirms it.

Amounts are compared as parsed structures, never raw digit-joins: a per-unit,
recurring, or range price (e.g. "1件2,000円〜") must never collapse to a bare
integer that could accidentally equal an unrelated order total.
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
work_sync = _load("lancers_test_work_sync_for_acceptance", SCRIPTS / "work_sync.py")

FIXED_300 = {"kind": "fixed", "amount_jpy": 300}
EXCLUSIVE = {"basis": "exclusive"}

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

    def __init__(self, *, verified_price: dict = None, verified_due: str = "2026-09-30",
                 order_amount: dict = None, order_tax_basis: dict = EXCLUSIVE,
                 order_due: str = "2026-09-30", milestone_count: int = 1):
        self.verified_price = verified_price if verified_price is not None else dict(FIXED_300)
        self.verified_due = verified_due
        self.order_amount = order_amount if order_amount is not None else dict(FIXED_300)
        self.order_tax_basis = order_tax_basis
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
            "verified_price": self.verified_price,
            "verified_delivery_due_on": self.verified_due,
            "order_amount": self.order_amount,
            "order_tax_basis": self.order_tax_basis,
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


# -- strict amount / tax-basis parsing -------------------------------------------------


def test_parse_amount_text_reads_a_plain_fixed_amount():
    assert work_sync._parse_amount_text("300円") == {"kind": "fixed", "amount_jpy": 300}


def test_parse_amount_text_never_collapses_a_per_unit_range_string_to_a_bare_integer():
    # "1件2,000円〜" carries both a per-unit marker (件) and a range marker (〜): too
    # ambiguous to trust as a single number, so it must not become amount_jpy=12000
    # (joining "1", "2,000" digit-wise) or amount_jpy=2000 (silently picking one marker).
    parsed = work_sync._parse_amount_text("1件2,000円〜")
    assert parsed["kind"] == "unparsed"
    assert "amount_jpy" not in parsed


def test_parse_amount_text_classifies_a_single_per_unit_amount():
    assert work_sync._parse_amount_text("1件500円") == {"kind": "per_unit", "amount_jpy": 500}


def test_parse_amount_text_classifies_a_single_recurring_amount():
    assert work_sync._parse_amount_text("毎月5,000円") == {"kind": "recurring", "amount_jpy": 5000}


def test_parse_amount_text_rejects_multiple_unrelated_amounts():
    parsed = work_sync._parse_amount_text("2,000円と3,000円のいずれか")
    assert parsed["kind"] == "unparsed"


def test_parse_tax_basis_reads_exclusive_label():
    assert work_sync._parse_tax_basis("契約金額（税抜）300円") == {"basis": "exclusive"}


def test_parse_tax_basis_reads_inclusive_label_with_rate():
    assert work_sync._parse_tax_basis("お支払い金額（税込）330円 消費税(10%)") == {
        "basis": "inclusive", "rate_percent": 10,
    }


def test_parse_tax_basis_unknown_without_a_label():
    assert work_sync._parse_tax_basis("お支払い金額 330円") is None


def test_parse_tax_basis_unknown_when_inclusive_without_a_rate():
    assert work_sync._parse_tax_basis("お支払い金額（税込）330円") is None


# -- decide() -----------------------------------------------------------------------


def test_decide_accepts_when_order_matches_the_verified_proposal():
    contract = {
        "project_id": "5605912", "proposal_id": "27969614",
        "verified_price": FIXED_300, "verified_delivery_due_on": "2026-09-30",
        "order_amount": FIXED_300, "order_tax_basis": EXCLUSIVE,
        "order_delivery_due_on": "2026-09-30", "order_milestone_count": 1,
    }
    decision = paid_adapter.decide({"context": {"contract": {
        **contract, "provider_state": "awaiting_acceptance"}}})
    assert decision == {"action": "accept", "payload": {
        "project_id": "5605912", "proposal_id": "27969614",
        "order_amount": FIXED_300, "order_delivery_due_on": "2026-09-30",
    }}


def test_decide_never_accepts_when_amount_or_deadline_differs():
    contract = {
        "provider_state": "awaiting_acceptance",
        "project_id": "5605912", "proposal_id": "27969614",
        "verified_price": FIXED_300, "verified_delivery_due_on": "2026-09-30",
        "order_amount": {"kind": "fixed", "amount_jpy": 500}, "order_tax_basis": EXCLUSIVE,
        "order_delivery_due_on": "2026-10-05", "order_milestone_count": 1,
    }
    decision = paid_adapter.decide({"context": {"contract": contract}})
    assert decision["action"] == "wait"
    assert decision["reason"] == "acceptance_terms_mismatch"
    assert any("amount mismatch" in line for line in decision["remaining_work"])
    assert any("deadline mismatch" in line for line in decision["remaining_work"])


def test_decide_never_accepts_an_ambiguous_per_unit_range_proposal_against_a_fixed_order():
    # "1件2,000円〜" (per-unit + range wording) vs a plain 12,000円 order: even though
    # digit-joining "1" + "2,000" would produce 12000 and wrongly look equal, the strict
    # parser marks the proposal side "unparsed" so no accept ever happens.
    contract = {
        "provider_state": "awaiting_acceptance",
        "project_id": "5605912", "proposal_id": "27969614",
        "verified_price": work_sync._parse_amount_text("1件2,000円〜"),
        "verified_delivery_due_on": "2026-09-30",
        "order_amount": {"kind": "fixed", "amount_jpy": 12000}, "order_tax_basis": EXCLUSIVE,
        "order_delivery_due_on": "2026-09-30", "order_milestone_count": 1,
    }
    decision = paid_adapter.decide({"context": {"contract": contract}})
    assert decision["action"] == "wait"
    assert decision["reason"] == "acceptance_terms_unparsed"


def test_decide_accepts_a_matching_per_unit_proposal_and_order():
    per_unit = {"kind": "per_unit", "amount_jpy": 500}
    contract = {
        "provider_state": "awaiting_acceptance",
        "project_id": "5605912", "proposal_id": "27969614",
        "verified_price": per_unit, "verified_delivery_due_on": "2026-09-30",
        "order_amount": dict(per_unit), "order_tax_basis": EXCLUSIVE,
        "order_delivery_due_on": "2026-09-30", "order_milestone_count": 1,
    }
    decision = paid_adapter.decide({"context": {"contract": contract}})
    assert decision["action"] == "accept"


def test_decide_accepts_an_inclusive_tax_order_equal_to_proposal_times_rate():
    contract = {
        "provider_state": "awaiting_acceptance",
        "project_id": "5605912", "proposal_id": "27969614",
        "verified_price": FIXED_300, "verified_delivery_due_on": "2026-09-30",
        "order_amount": {"kind": "fixed", "amount_jpy": 330},
        "order_tax_basis": {"basis": "inclusive", "rate_percent": 10},
        "order_delivery_due_on": "2026-09-30", "order_milestone_count": 1,
    }
    decision = paid_adapter.decide({"context": {"contract": contract}})
    assert decision["action"] == "accept"


def test_decide_never_accepts_when_tax_basis_is_unknown():
    contract = {
        "provider_state": "awaiting_acceptance",
        "project_id": "5605912", "proposal_id": "27969614",
        "verified_price": FIXED_300, "verified_delivery_due_on": "2026-09-30",
        "order_amount": FIXED_300, "order_tax_basis": None,
        "order_delivery_due_on": "2026-09-30", "order_milestone_count": 1,
    }
    decision = paid_adapter.decide({"context": {"contract": contract}})
    assert decision["action"] == "wait"
    assert decision["reason"] == "acceptance_tax_basis_unknown"


def test_decide_never_accepts_when_either_side_has_multiple_unrelated_amounts():
    contract = {
        "provider_state": "awaiting_acceptance",
        "project_id": "5605912", "proposal_id": "27969614",
        "verified_price": work_sync._parse_amount_text("2,000円と3,000円"),
        "verified_delivery_due_on": "2026-09-30",
        "order_amount": FIXED_300, "order_tax_basis": EXCLUSIVE,
        "order_delivery_due_on": "2026-09-30", "order_milestone_count": 1,
    }
    decision = paid_adapter.decide({"context": {"contract": contract}})
    assert decision["action"] == "wait"
    assert decision["reason"] == "acceptance_terms_unparsed"


# -- end-to-end kernel wake -----------------------------------------------------------


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
    provider = FakeAcceptanceProvider(order_amount={"kind": "fixed", "amount_jpy": 999})
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


def test_unparsed_amount_text_is_written_to_stderr_as_a_probe(capsys):
    import pytest
    with pytest.raises(work_sync.SourceFailure):
        work_sync._parse_amount_text("¥2,000")
    assert "lancers_amount_unparsed:'¥2,000'" in capsys.readouterr().err


def test_proposal_terms_wait_for_client_rendered_contract_amount():
    calls = []

    class Page:
        def goto(self, url, **_):
            calls.append(("goto", url))

        def wait_for_function(self, expression, **kwargs):
            calls.append(("wait", expression))

        def evaluate(self, script, *args):
            calls.append(("evaluate",))
            return {"path": "/work/proposal/27969614", "amount": "2,000円",
                    "due": "2026/10/10", "project_id": "5605912", "proposal_text": "提案本文"}

    terms = work_sync._read_proposal_terms(Page(), "27969614", "5605912")
    kinds = [c[0] for c in calls]
    assert kinds.index("wait") < kinds.index("evaluate")
    assert "契約金額" in [c for c in calls if c[0] == "wait"][0][1]
    assert terms["price"] == {"kind": "fixed", "amount_jpy": 2000}


def test_acceptance_candidates_skip_a_proposal_page_that_is_404():
    class Response:
        def __init__(self, status):
            self.status = status

    class Page:
        def __init__(self):
            self.current = None

        def goto(self, url, **_):
            self.current = url
            return Response(404 if url.endswith("/27810811") else 200)

        def wait_for_function(self, *_args, **_kwargs):
            if self.current.endswith("/27810811"):
                raise TimeoutError("never rendered")

        def evaluate(self, script, *args):
            if self.current.endswith("/27810811"):
                return {"path": "/work/proposal/27810811", "amount": None, "due": None,
                        "project_id": None, "proposal_text": None, "notFound": True}
            return {"path": "/work/proposal/27969614", "amount": "2,000円", "due": "2026/10/10",
                    "project_id": "5605912", "proposal_text": "提案本文", "notFound": False}

    candidates = work_sync._acceptance_candidates(Page(), {"27810811", "27969614"})
    assert [c["provider_id"] for c in candidates] == ["5605912"]


def test_recent_verified_proposals_are_newest_first_bounded_and_windowed(tmp_path):
    import sqlite3
    state = tmp_path / "state.json"
    db = tmp_path / "marketplace-ledger.sqlite3"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE marketplace_events (platform TEXT, event_type TEXT, external_id TEXT, occurred_at TEXT)")
        rows = [("lancers", "application_verified", str(1000 + i), f"2026-09-{10 + i:02d}T00:00:00Z") for i in range(15)]
        rows.append(("lancers", "application_verified", "27810811", "2026-07-01T00:00:00Z"))
        c.executemany("INSERT INTO marketplace_events VALUES (?,?,?,?)", rows)
    recent = work_sync._recent_verified_proposals(
        state, now="2026-09-26T00:00:00Z", days=30, limit=10)
    assert recent == [str(1000 + i) for i in range(14, 4, -1)]
    assert "27810811" not in recent
