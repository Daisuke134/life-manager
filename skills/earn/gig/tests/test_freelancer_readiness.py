from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from provider_authorization import AuthorizationReceipt, AuthorizationState  # noqa: E402
from freelancer_readiness import (  # noqa: E402
    REQUIRED_ACTIONS,
    ReadinessError,
    evaluate_registration,
    parse_inventory,
    plan_effect,
    replay_zero,
)


NOW = datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc)
HASH = "a" * 64


def _receipt(action: str, *, state: AuthorizationState = AuthorizationState.APPROVED_BROWSER):
    return AuthorizationReceipt(
        provider="freelancer",
        account="account-94117802",
        action=action,
        transport="cloak_browser" if state is AuthorizationState.APPROVED_BROWSER else "official_api",
        state=state,
        jurisdiction="JP",
        terms_version="freelancer-v1",
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
    }


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
