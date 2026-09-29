from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "platform_enrollment.py"


def _module():
    spec = importlib.util.spec_from_file_location("marketplace_platform_enrollment_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate(**overrides):
    value = {
        "version": 1,
        "provider": "example-market",
        "policy": {
            "status": "allowed",
            "source_url": "https://example.test/automation-policy",
            "observed_at": "2026-09-29T00:00:00Z",
        },
        "adapter": {
            "contract": "marketplace-core-v1",
            "actions": [
                "discover",
                "inspect",
                "propose",
                "message",
                "accept_offer",
                "deliver",
                "read_payments",
                "read_payouts",
            ],
            "source_sha256": "a" * 64,
        },
        "funded_work": {
            "status": "funded",
            "receipt_ref": "provider-receipt://example-market/funding-1",
            "observed_at": "2026-09-29T00:01:00Z",
        },
        "canary": {
            "status": "verified",
            "official_receipt_ref": "provider-receipt://example-market/canary-1",
            "replay_zero": True,
            "observed_at": "2026-09-29T00:02:00Z",
        },
        "unit_economics": {
            "status": "measured",
            "net_amount_minor": 100,
            "currency": "USD",
            "evidence_refs": ["ledger://example-market/canary-1"],
        },
    }
    for key, value_override in overrides.items():
        value[key] = value_override
    return value


def test_fully_evidenced_candidate_is_promotable():
    result = _module().evaluate_platform_candidate(_candidate())

    assert result["decision"] == "promote"
    assert result["owner_registration_allowed"] is True
    assert result["reasons"] == []
    assert all(status == "pass" for status in result["gates"].values())


def test_unknown_policy_holds_even_when_every_other_gate_is_ready():
    result = _module().evaluate_platform_candidate(_candidate(
        policy={
            "status": "unknown",
            "source_url": "https://example.test/automation-policy",
            "observed_at": "2026-09-29T00:00:00Z",
        },
    ))

    assert result["decision"] == "hold"
    assert result["owner_registration_allowed"] is False
    assert result["reasons"] == ["policy_not_allowed"]
    assert result["gates"]["policy"] == "fail"


def test_missing_canary_readback_and_non_positive_net_hold_promotion():
    result = _module().evaluate_platform_candidate(_candidate(
        canary={
            "status": "verified",
            "official_receipt_ref": None,
            "replay_zero": False,
            "observed_at": "2026-09-29T00:02:00Z",
        },
        unit_economics={
            "status": "measured",
            "net_amount_minor": 0,
            "currency": "USD",
            "evidence_refs": ["ledger://example-market/canary-1"],
        },
    ))

    assert result["decision"] == "hold"
    assert result["owner_registration_allowed"] is False
    assert result["reasons"] == [
        "canary_receipt_missing",
        "replay_not_zero",
        "net_not_positive",
    ]


def test_malformed_candidate_fails_closed():
    module = _module()
    with pytest.raises(module.EnrollmentError, match="candidate_fields_invalid"):
        module.evaluate_platform_candidate({"version": 1, "provider": "example-market"})


def test_receipts_must_be_bound_to_the_candidate_provider():
    module = _module()
    with pytest.raises(module.EnrollmentError, match="receipt_provider_mismatch"):
        module.evaluate_platform_candidate(_candidate(
            funded_work={
                "status": "funded",
                "receipt_ref": "provider-receipt://other-market/funding-1",
                "observed_at": "2026-09-29T00:01:00Z",
            },
        ))
