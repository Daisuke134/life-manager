from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from provider_authorization import (  # noqa: E402
    AuthorizationError,
    AuthorizationState,
    authorize,
    load_receipts,
)


NOW = datetime(2026, 8, 22, 8, 30, tzinfo=timezone.utc)
EVIDENCE_HASH = "a" * 64


def _receipt(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "provider": "upwork",
        "account": "owner-account",
        "action": "submit_proposal",
        "transport": "cloak_browser",
        "state": "approved_browser",
        "jurisdiction": "JP",
        "terms_version": "special-approval-v1",
        "evidence_hash": EVIDENCE_HASH,
        "issued_at": "2026-08-01T00:00:00Z",
        "expires_at": "2026-09-01T00:00:00Z",
    }
    value.update(overrides)
    return value


def _store(path: Path, receipts: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps({"version": 1, "receipts": receipts}), encoding="utf-8")
    path.chmod(0o600)
    return path


def _authorize(monkeypatch: pytest.MonkeyPatch, path: Path, **overrides: object):
    monkeypatch.setenv("GIG_AUTHORIZATION_PATH", str(path))
    query = {
        "provider": "upwork",
        "account": "owner-account",
        "action": "submit_proposal",
        "transport": "cloak_browser",
        "now": NOW,
    }
    query.update(overrides)
    return authorize(**query)


def test_missing_store_is_unknown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    decision = _authorize(monkeypatch, tmp_path / "missing.json")
    assert decision.state is AuthorizationState.UNKNOWN
    assert decision.reason == "receipt_store_missing"


@pytest.mark.parametrize(
    ("query_override", "reason"),
    [
        ({"account": "different-account"}, "no_matching_receipt"),
        ({"action": "send_message"}, "no_matching_receipt"),
        ({"transport": "official_api"}, "no_matching_receipt"),
    ],
)
def test_wrong_scope_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    query_override: dict[str, str],
    reason: str,
):
    store = _store(tmp_path / "authorizations.json", [_receipt()])
    decision = _authorize(monkeypatch, store, **query_override)
    assert decision.state is AuthorizationState.UNKNOWN
    assert decision.reason == reason


def test_expired_receipt_is_unknown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    store = _store(
        tmp_path / "authorizations.json",
        [_receipt(expires_at="2026-08-22T08:29:59Z")],
    )
    decision = _authorize(monkeypatch, store)
    assert decision.state is AuthorizationState.UNKNOWN
    assert decision.reason == "matching_receipt_expired"


def test_exact_unexpired_special_approval_is_approved_browser(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    store = _store(tmp_path / "authorizations.json", [_receipt()])
    decision = _authorize(monkeypatch, store)
    assert decision.state is AuthorizationState.APPROVED_BROWSER
    assert decision.reason == "matching_receipt"
    assert decision.evidence_hash == EVIDENCE_HASH
    assert decision.receipt_hash is not None


@pytest.mark.parametrize(
    "mutation",
    [
        {"unexpected": True},
        {"issued_at": "not-a-timestamp"},
        {"expires_at": "2026-07-01T00:00:00Z"},
        {"evidence_hash": "not-a-sha256"},
    ],
)
def test_malformed_receipt_fails_closed(tmp_path: Path, mutation: dict[str, object]):
    store = _store(tmp_path / "authorizations.json", [_receipt(**mutation)])
    with pytest.raises(AuthorizationError):
        load_receipts(store)


def test_private_store_must_be_mode_600(tmp_path: Path):
    store = _store(tmp_path / "authorizations.json", [_receipt()])
    store.chmod(0o644)
    with pytest.raises(AuthorizationError, match="mode_600"):
        load_receipts(store)


@pytest.mark.parametrize(
    ("state", "transport"),
    [
        ("approved_api", "cloak_browser"),
        ("approved_browser", "official_api"),
        ("approved_assisted", "official_api"),
        ("approved_api", "unregistered_transport"),
    ],
)
def test_approved_state_must_match_its_transport(
    tmp_path: Path,
    state: str,
    transport: str,
):
    store = _store(
        tmp_path / "authorizations.json",
        [_receipt(state=state, transport=transport)],
    )
    with pytest.raises(AuthorizationError, match="state_transport_mismatch"):
        load_receipts(store)


def test_public_catalogue_defaults_every_action_to_unknown():
    catalogue_path = Path(__file__).resolve().parents[1] / "config" / "provider-capabilities.public.json"
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    assert catalogue["version"] == 1
    assert catalogue["default_state"] == "unknown"
    assert set(catalogue["providers"]) == {
        "coconala",
        "upwork",
        "fiverr",
        "linkedin",
        "mercor",
        "welocalize",
        "telus",
        "utest",
        "prolific",
        "outlier",
        "babel_audio",
        "lancers",
        "freelancer",
    }
    for provider in catalogue["providers"].values():
        assert provider["actions"]
        assert provider["state"] == "unknown"
    assert catalogue["providers"]["lancers"] == {
        "state": "unknown",
        "actions": ["submit_proposal"],
        "capability": {
            "id": "marketplace.application",
            "action": "submit_proposal",
            "transport": "cloak_browser",
            "authorization": {
                "receipt_required": True,
                "required_state": "approved_browser",
            },
            "human_only_when_required": ["captcha", "identity", "tax", "payout"],
            "readback": {"record_type": "application_receipt"},
        },
    }


def test_public_marketplace_example_is_reference_only_and_provider_neutral():
    path = Path(__file__).resolve().parents[1] / "config" / "provider-capability.example.json"
    example = json.loads(path.read_text(encoding="utf-8"))
    assert example == {
        "version": 1,
        "default_state": "unknown",
        "capability": "marketplace.application",
        "transport": "cloak_browser",
        "authorization": {
            "receipt_required": True,
            "required_state": "approved_browser",
        },
        "input_refs": {
            "goal_ref": "intent-entry://{tenant_id}/{goal_id}",
            "capability_ref": "provider-capability://{provider}/marketplace.application",
            "opportunity_ref": "marketplace-opportunity://{provider}/{opportunity_id}",
            "intent_ref": "application-intent://sha256/{intent_sha256}",
            "authorization_ref": "authorization-receipt://sha256/{receipt_sha256}",
        },
        "effect": {
            "class": "publish",
            "max_attempts": 1,
            "unknown_state": "reconcile_without_resend",
            "replay": "zero",
        },
        "readback": {
            "record_type": "application_receipt",
            "required_status": "verified",
        },
    }
    encoded = json.dumps(example, sort_keys=True).lower()
    for forbidden in ("http://", "https://", "password", "token", "selector", "xpath", "human"):
        assert forbidden not in encoded
