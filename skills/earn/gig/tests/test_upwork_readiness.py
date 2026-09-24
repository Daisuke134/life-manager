from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from provider_authorization import AuthorizationReceipt, AuthorizationState  # noqa: E402
from upwork_readiness import (  # noqa: E402
    INVENTORY_READ_ACTIONS,
    REQUIRED_ACTIONS,
    ReadinessError,
    evaluate_registration,
    parse_inventory,
    plan_effect,
    read_authenticated_inventory,
    replay_zero,
)


NOW = datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc)
HASH = "a" * 64


def _receipt(action: str, *, state: AuthorizationState = AuthorizationState.APPROVED_BROWSER):
    return AuthorizationReceipt(
        provider="upwork",
        account="upwork-account-1",
        action=action,
        transport="cloak_browser" if state is AuthorizationState.APPROVED_BROWSER else "official_api",
        state=state,
        jurisdiction="JP",
        terms_version="upwork-v1",
        evidence_hash=HASH,
        issued_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        expires_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        receipt_hash=HASH,
    )


def _inventory(*, source_complete: bool = True, contracts: list[dict] | None = None):
    return {
        "version": 1,
        "provider": "upwork",
        "account_id": "upwork-account-1",
        "source_complete": source_complete,
        "observed_at": "2026-09-24T13:55:00Z",
        "source_hash": HASH,
        "contracts": contracts if contracts is not None else [{
            "contract_id": "contract-1",
            "state": "funded",
            "funded_milestone_minor": 50000,
            "source_url": "https://www.upwork.com/ab/workroom/contract-1",
            "source_hash": HASH,
            "observed_at": "2026-09-24T13:55:00Z",
        }],
    }


def test_upwork_owner_gate_stays_closed_for_current_zero_contract_state():
    snapshot = parse_inventory(_inventory(source_complete=True, contracts=[]))
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS)]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    assert report.ready is False
    assert report.reasons == ("funded_contract_missing",)


def test_inventory_readback_does_not_call_transport_without_approved_receipts():
    calls = []

    def readback(_receipts):
        calls.append(True)
        return _inventory()

    with pytest.raises(ReadinessError, match="inventory_authorization_missing"):
        read_authenticated_inventory(
            [], account_id="upwork-account-1", now=NOW, readback=readback,
        )
    assert calls == []


def test_inventory_readback_requires_all_read_receipts_and_binds_account():
    receipts = [_receipt(action) for action in sorted(INVENTORY_READ_ACTIONS)]
    seen = []

    def readback(receipts):
        seen.extend(sorted(receipts))
        return _inventory()

    inventory = read_authenticated_inventory(
        receipts, account_id="upwork-account-1", now=NOW, readback=readback,
    )

    assert inventory.account_id == "upwork-account-1"
    assert seen == sorted(INVENTORY_READ_ACTIONS)


def test_inventory_readback_rejects_provider_account_mismatch():
    receipts = [_receipt(action) for action in sorted(INVENTORY_READ_ACTIONS)]

    with pytest.raises(ReadinessError, match="inventory_account_mismatch"):
        read_authenticated_inventory(
            receipts, account_id="upwork-account-1", now=NOW,
            readback=lambda _receipts: {**_inventory(), "account_id": "other"},
        )


def test_upwork_owner_gate_requires_all_current_authorizations():
    snapshot = parse_inventory(_inventory())
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS - {"deliver_milestone"})]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    assert report.ready is False
    assert report.missing_actions == ("deliver_milestone",)


def test_upwork_owner_gate_opens_only_for_fresh_funded_readback():
    snapshot = parse_inventory(_inventory())
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS)]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    assert report.ready is True
    assert report.funded_contract_ids == ("contract-1",)


def test_upwork_effect_is_contract_bound_and_replay_safe():
    snapshot = parse_inventory(_inventory())
    receipts = [_receipt(action) for action in sorted(REQUIRED_ACTIONS)]
    report = evaluate_registration(receipts, snapshot, now=NOW)
    intent = plan_effect(
        report, receipts, contract_id="contract-1", action="deliver_milestone",
        payload_hash="b" * 64, now=NOW,
    )
    assert intent.provider == "upwork"
    assert intent.resource_id == "contract-1"
    assert replay_zero([intent, intent]) is False
    with pytest.raises(ReadinessError, match="contract_not_funded"):
        plan_effect(
            report, receipts, contract_id="contract-unknown", action="deliver_milestone",
            payload_hash="b" * 64, now=NOW,
        )


@pytest.mark.parametrize("field", ["source_hash", "source_url", "observed_at"])
def test_upwork_inventory_rejects_bad_contract_evidence(field: str):
    value = _inventory()
    value["contracts"][0][field] = "bad"
    with pytest.raises(ReadinessError):
        parse_inventory(value)
