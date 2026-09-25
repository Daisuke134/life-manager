from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from provider_authorization import AuthorizationReceipt, AuthorizationState  # noqa: E402
from freelancer_readiness import (  # noqa: E402
    INVENTORY_READ_ACTIONS,
    FREELANCER_AUTOMATED_BID_APPROVAL_TERMS,
    REQUIRED_ACTIONS,
    ReadinessError,
    evaluate_registration,
    parse_inventory,
    plan_effect,
    read_authenticated_inventory,
    replay_zero,
    snapshot_from_official_readbacks,
)


NOW = datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc)
HASH = "a" * 64


def _receipt(
    action: str,
    *,
    state: AuthorizationState = AuthorizationState.APPROVED_BROWSER,
    terms_version: str = FREELANCER_AUTOMATED_BID_APPROVAL_TERMS,
):
    return AuthorizationReceipt(
        provider="freelancer",
        account="account-94117802",
        action=action,
        transport="cloak_browser" if state is AuthorizationState.APPROVED_BROWSER else "official_api",
        state=state,
        jurisdiction="JP",
        terms_version=terms_version,
        evidence_hash=HASH,
        issued_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        expires_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        receipt_hash=HASH,
    )


def _inventory(*, source_complete: bool = True, contracts: list[dict] | None = None):
    return {
        "version": 1,
        "provider": "freelancer",
        "account_id": "account-94117802",
        "source_complete": source_complete,
        "observed_at": "2026-09-24T13:55:00Z",
        "source_hash": HASH,
        "contracts": contracts if contracts is not None else [{
            "project_id": "project-40620700",
            "contract_id": "contract-1",
            "state": "funded",
            "currency": "USD",
            "amount_minor": 25000,
            "source_url": "https://www.freelancer.com/projects/project-40620700",
            "source_hash": HASH,
            "observed_at": "2026-09-24T13:55:00Z",
        }],
    }


def test_registration_gate_is_closed_without_auth_inventory_or_funding():
    snapshot = parse_inventory(_inventory(source_complete=False, contracts=[]))
    report = evaluate_registration([], snapshot, now=NOW)
    assert report.ready is False
    assert set(report.reasons) == {
        "authorization_missing",
        "inventory_incomplete",
        "funded_contract_missing",
        "provider_policy_missing",
    }


def test_inventory_readback_does_not_call_transport_without_approved_receipts():
    calls = []

    def readback(_receipts):
        calls.append(True)
        return _inventory()

    with pytest.raises(ReadinessError, match="inventory_authorization_missing"):
        read_authenticated_inventory(
            [], account_id="account-94117802", now=NOW, readback=readback,
        )
    assert calls == []


def test_inventory_readback_requires_all_read_receipts_and_binds_account():
    receipts = [_receipt(action) for action in sorted(INVENTORY_READ_ACTIONS)]
    seen = []

    def readback(receipts):
        seen.extend(sorted(receipts))
        return _inventory()

    inventory = read_authenticated_inventory(
        receipts, account_id="account-94117802", now=NOW, readback=readback,
    )

    assert inventory.account_id == "account-94117802"
    assert seen == sorted(INVENTORY_READ_ACTIONS)


def test_inventory_readback_rejects_provider_account_mismatch():
    receipts = [_receipt(action) for action in sorted(INVENTORY_READ_ACTIONS)]

    with pytest.raises(ReadinessError, match="inventory_account_mismatch"):
        read_authenticated_inventory(
            receipts, account_id="account-94117802", now=NOW,
            readback=lambda _receipts: {**_inventory(), "account_id": "other"},
        )


def test_inventory_readback_rejects_stale_snapshot():
    receipts = [_receipt(action) for action in sorted(INVENTORY_READ_ACTIONS)]
    stale = _inventory()
    stale["observed_at"] = "2026-09-22T13:55:00Z"

    with pytest.raises(ReadinessError, match="inventory_stale"):
        read_authenticated_inventory(
            receipts, account_id="account-94117802", now=NOW,
            readback=lambda _receipts: stale,
        )


def test_registration_gate_requires_every_lifecycle_authorization():
    snapshot = parse_inventory(_inventory())
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS - {"read_payouts"})]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    assert report.ready is False
    assert report.missing_actions == ("read_payouts",)


def test_nonfunded_contract_is_visible_but_cannot_open_owner_gate():
    contract = _inventory()["contracts"][0]
    contract["state"] = "pending"
    contract["amount_minor"] = 0
    snapshot = parse_inventory(_inventory(contracts=[contract]))
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS)]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    assert report.ready is False
    assert report.reasons == ("funded_contract_missing",)
    assert report.funded_contract_ids == ()


def test_registration_gate_opens_only_with_fresh_auth_and_funded_contract():
    snapshot = parse_inventory(_inventory())
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS)]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    assert report.ready is True
    assert report.reasons == ()
    assert report.funded_contract_ids == ("contract-1",)


def test_registration_gate_rejects_stale_funded_snapshot():
    stale = _inventory()
    stale["observed_at"] = "2026-09-22T13:55:00Z"
    snapshot = parse_inventory(stale)
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS)]

    report = evaluate_registration(receipts, snapshot, now=NOW)

    assert report.ready is False
    assert report.reasons == ("inventory_stale",)


def test_registration_rejects_automatic_bid_without_provider_policy_approval():
    snapshot = parse_inventory(_inventory())
    receipts = [
        _receipt(
            action,
            terms_version=(
                "freelancer-v1"
                if action == "propose"
                else FREELANCER_AUTOMATED_BID_APPROVAL_TERMS
            ),
        )
        for action in sorted(REQUIRED_ACTIONS)
    ]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    assert report.ready is False
    assert report.reasons == ("provider_policy_missing",)


def test_plan_effect_is_bound_to_funded_contract_and_authorization():
    snapshot = parse_inventory(_inventory())
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS)]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    intent = plan_effect(
        report, receipts, contract_id="contract-1", action="deliver",
        payload_hash="b" * 64, now=NOW,
    )
    assert intent.provider == "freelancer"
    assert intent.resource_id == "contract-1"
    assert intent.action == "deliver"
    assert intent.effect_key.startswith("provider-effect:v1:")

    with pytest.raises(ReadinessError, match="contract_not_funded"):
        plan_effect(
            report, receipts, contract_id="contract-unknown", action="deliver",
            payload_hash="b" * 64, now=NOW,
        )


def test_replay_zero_rejects_duplicate_effect_keys():
    snapshot = parse_inventory(_inventory())
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS)]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    first = plan_effect(
        report, receipts, contract_id="contract-1", action="deliver",
        payload_hash="b" * 64, now=NOW,
    )
    second = plan_effect(
        report, receipts, contract_id="contract-1", action="deliver",
        payload_hash="b" * 64, now=NOW,
    )
    assert replay_zero([first]) is True
    assert replay_zero([first, second]) is False


@pytest.mark.parametrize("field", ["source_hash", "source_url", "observed_at"])
def test_inventory_rejects_noncanonical_source_evidence(field: str):
    value = _inventory()
    value["contracts"][0][field] = "bad"
    with pytest.raises(ReadinessError):
        parse_inventory(value)


def _official(status: str, result: dict):
    return {"status": status, "request_id": "req-1", "result": result}


def _official_readbacks(*, milestone_status: str = "pending"):
    return {
        "identity": _official("success", {
            "users": {"94117802": {"id": 94117802, "username": "rasi4op"}},
        }),
        "projects": _official("success", {
            "projects": {
                "projects": [{"id": 40620700, "status": "awarded"}],
                "contests": [],
                "total_count": 1,
            },
            "contests": {"contests": [], "total_count": 0},
            "total_count": 1,
        }),
        "milestones": {"40620700": _official("success", {
            "milestones": {"7001": {
                "transaction_id": 7001,
                "project_owner_id": 111,
                "bidder_id": 94117802,
                "amount": 250,
                "reason": "full_payment",
                "other_reason": None,
                "project_id": 40620700,
                "bid_id": 491448418,
                "currency": {"id": 1, "code": "USD", "sign": "$"},
                "is_from_prepaid": False,
                "status": milestone_status,
                "dispute_id": None,
                "cancellation_requested": False,
                "time_created": 1780230000,
            }},
            "users": None,
        })},
        "hourly_contracts": _official("success", {"hourly_contracts": []}),
        "ip_contracts": {"40620700": _official("success", {"contracts": []})},
        "payments": _official("success", {"payments": []}),
        "payouts": _official("success", {"payouts": []}),
    }


def test_official_readbacks_map_documented_milestone_to_funded_inventory():
    snapshot = snapshot_from_official_readbacks(
        _official_readbacks(), account_id="94117802",
        observed_at="2026-09-24T13:55:00Z", source_hash=HASH,
        currency_minor_units={"USD": 2},
    )

    assert snapshot["source_complete"] is True
    assert snapshot["account_id"] == "94117802"
    assert snapshot["contracts"] == [{
        "project_id": "40620700",
        "contract_id": "project-40620700-milestone-7001",
        "state": "funded",
        "currency": "USD",
        "amount_minor": 25000,
        "source_url": "https://www.freelancer.com/projects/40620700",
        "source_hash": HASH,
        "observed_at": "2026-09-24T13:55:00Z",
    }]


def test_official_readbacks_reject_missing_payment_or_project_envelope():
    raw = _official_readbacks()
    del raw["payments"]
    with pytest.raises(ReadinessError, match="official_readbacks_fields_invalid"):
        snapshot_from_official_readbacks(
            raw, account_id="94117802", observed_at="2026-09-24T13:55:00Z",
            source_hash=HASH, currency_minor_units={"USD": 2},
        )

    raw = _official_readbacks()
    raw["projects"]["result"]["projects"]["projects"][0]["id"] = 999
    with pytest.raises(ReadinessError, match="official_project_readbacks_incomplete"):
        snapshot_from_official_readbacks(
            raw, account_id="94117802", observed_at="2026-09-24T13:55:00Z",
            source_hash=HASH, currency_minor_units={"USD": 2},
        )


def test_official_readbacks_reject_unknown_money_precision_and_bad_status():
    with pytest.raises(ReadinessError, match="currency_minor_units_missing"):
        snapshot_from_official_readbacks(
            _official_readbacks(), account_id="94117802",
            observed_at="2026-09-24T13:55:00Z", source_hash=HASH,
            currency_minor_units={},
        )

    raw = _official_readbacks(milestone_status="created")
    with pytest.raises(ReadinessError, match="milestone_status_invalid"):
        snapshot_from_official_readbacks(
            raw, account_id="94117802", observed_at="2026-09-24T13:55:00Z",
            source_hash=HASH, currency_minor_units={"USD": 2},
        )
