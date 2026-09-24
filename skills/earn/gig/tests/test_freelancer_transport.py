"""Selection and official-readback planning tests for Freelancer."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


GIG_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = GIG_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
MODULE = SCRIPTS / "providers" / "freelancer_transport.py"


def _load_module():
    name = "gig_freelancer_transport_test"
    spec = importlib.util.spec_from_file_location(name, MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


transport = _load_module()
from provider_authorization import load_receipts  # noqa: E402
NOW = datetime(2026, 9, 25, 1, 0, tzinfo=timezone.utc)
ACCOUNT = "freelancer-owner:v1:" + "1" * 64


def _receipt(action: str, mode: str, *, expired: bool = False) -> dict[str, object]:
    state = "approved_api" if mode == "official_api" else "approved_browser"
    return {
        "provider": "freelancer", "account": ACCOUNT, "action": action,
        "transport": mode, "state": state, "jurisdiction": "JP",
        "terms_version": "freelancer-v1", "evidence_hash": "a" * 64,
        "issued_at": "2026-09-01T00:00:00+00:00",
        "expires_at": "2026-09-24T00:00:00+00:00" if expired else "2026-10-01T00:00:00+00:00",
    }


def _authorization_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, receipts: list[dict[str, object]],
) -> Path:
    path = tmp_path / "authorizations.json"
    path.write_text(json.dumps({"version": 1, "receipts": receipts}), encoding="utf-8")
    path.chmod(0o600)
    monkeypatch.setenv("GIG_AUTHORIZATION_PATH", str(path))
    return path


def _oauth(path: Path, *, expired: bool = False) -> None:
    path.write_text(json.dumps({
        "version": 1,
        "access_token": "freelancer-access-token-must-never-appear",
        "refresh_token": "freelancer-refresh-token-must-never-appear",
        "token_type": "Bearer",
        "scopes": ["basic"],
        "expires_at": "2026-09-24T00:00:00+00:00" if expired else "2026-09-26T00:00:00+00:00",
    }), encoding="utf-8")
    path.chmod(0o600)


def _profile(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "profiles"
    path = root / "gig-freelancer"
    path.mkdir(parents=True)
    root.chmod(0o700)
    path.chmod(0o700)
    return root, path


def _inventory() -> dict[str, object]:
    return {
        "version": 1,
        "provider": "freelancer",
        "account_id": ACCOUNT,
        "source_complete": True,
        "observed_at": "2026-09-25T00:55:00Z",
        "source_hash": "b" * 64,
        "contracts": [{
            "project_id": "123",
            "contract_id": "contract-1",
            "state": "funded",
            "currency": "USD",
            "amount_minor": 10000,
            "source_url": "https://www.freelancer.com/projects/123",
            "source_hash": "c" * 64,
            "observed_at": "2026-09-25T00:55:00Z",
        }],
    }


def _selector(tmp_path: Path, **overrides: object):
    root, profile = _profile(tmp_path)
    values = {
        "account": ACCOUNT,
        "now": NOW,
        "oauth_path": tmp_path / "freelancer-oauth2.json",
        "profiles_root": root,
        "browser_profile": profile,
        "matrix_path": GIG_ROOT / "config" / "freelancer-actions.public.json",
    }
    values.update(overrides)
    return transport.FreelancerTransport(**values)


def test_approved_api_with_live_token_is_preferred_over_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    _authorization_store(
        tmp_path, monkeypatch,
        [_receipt("inspect", "official_api"), _receipt("inspect", "cloak_browser")],
    )
    oauth_path = tmp_path / "freelancer-oauth2.json"
    _oauth(oauth_path)

    selected = _selector(tmp_path, oauth_path=oauth_path).for_action("inspect")

    assert selected is not None
    assert selected.mode == "official_api"
    assert selected.credential_path == oauth_path
    assert "access-token" not in repr(selected)


def test_browser_fallback_requires_private_profile_and_approved_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    _authorization_store(
        tmp_path, monkeypatch, [_receipt("deliver", "cloak_browser")]
    )
    root, profile = _profile(tmp_path)
    selected = transport.FreelancerTransport(
        account=ACCOUNT, now=NOW, oauth_path=tmp_path / "missing.json",
        profiles_root=root, browser_profile=profile,
        matrix_path=GIG_ROOT / "config" / "freelancer-actions.public.json",
    ).for_action("deliver")

    assert selected is not None
    assert selected.mode == "cloak_browser"
    assert selected.credential_path == profile


def test_expired_auth_and_token_produce_zero_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    _authorization_store(
        tmp_path, monkeypatch,
        [_receipt("read_payments", "official_api"),
         _receipt("read_payments", "cloak_browser", expired=True)],
    )
    oauth_path = tmp_path / "freelancer-oauth2.json"
    _oauth(oauth_path, expired=True)

    assert _selector(tmp_path, oauth_path=oauth_path).for_action("read_payments") is None


def test_unlisted_action_and_missing_receipt_produce_zero_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    _authorization_store(tmp_path, monkeypatch, [])
    selector = _selector(tmp_path)

    assert selector.for_action("inspect") is None
    assert selector.for_action("delete_account") is None


def test_oauth_loader_is_private_and_redacted(tmp_path: Path):
    oauth_path = tmp_path / "freelancer-oauth2.json"
    _oauth(oauth_path)

    token = transport.load_oauth2_token(oauth_path, NOW)

    assert token is not None
    assert token.access_token == "freelancer-access-token-must-never-appear"
    assert "must-never-appear" not in repr(token)
    oauth_path.chmod(0o644)
    with pytest.raises(transport.TransportConfigurationError, match="mode_600"):
        transport.load_oauth2_token(oauth_path, NOW)


def test_inventory_route_plan_matches_documented_official_endpoints(tmp_path: Path):
    plan = _selector(tmp_path).inventory_route_plan(project_ids=("123", "456"))

    assert plan == (
        ("identity", "/users/0.1/users/"),
        ("projects", "/projects/0.1/self/"),
        ("milestones:123", "/projects/0.1/projects/123/milestones/"),
        ("milestones:456", "/projects/0.1/projects/456/milestones/"),
        ("hourly_contracts", "/projects/0.1/hourly_contracts/"),
        ("ip_contract:123", "/projects/0.1/projects/123/ip_contracts/"),
        ("ip_contract:456", "/projects/0.1/projects/456/ip_contracts/"),
    )


def test_inventory_route_plan_rejects_non_numeric_project_ids(tmp_path: Path):
    with pytest.raises(transport.TransportConfigurationError, match="project_id_invalid"):
        _selector(tmp_path).inventory_route_plan(project_ids=("../secret",))


def test_inventory_readback_does_not_call_fetch_without_read_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    _authorization_store(tmp_path, monkeypatch, [])
    calls: list[object] = []

    with pytest.raises(ValueError, match="inventory_authorization_missing"):
        _selector(tmp_path).read_inventory(
            load_receipts(tmp_path / "authorizations.json"),
            account_id=ACCOUNT, project_ids=("123",),
            fetch=lambda selection, plan: calls.append((selection, plan)) or _inventory(),
        )
    assert calls == []


def test_inventory_readback_fetches_only_after_all_read_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    receipts = [_receipt(action, "cloak_browser") for action in (
        "inspect", "read_payments", "read_payouts",
    )]
    _authorization_store(tmp_path, monkeypatch, receipts)
    root, profile = _profile(tmp_path)
    selector = transport.FreelancerTransport(
        account=ACCOUNT, now=NOW, oauth_path=tmp_path / "missing.json",
        profiles_root=root, browser_profile=profile,
        matrix_path=GIG_ROOT / "config" / "freelancer-actions.public.json",
    )
    calls: list[object] = []

    inventory = selector.read_inventory(
        load_receipts(tmp_path / "authorizations.json"),
        account_id=ACCOUNT, project_ids=("123",),
        fetch=lambda selection, plan: calls.append((selection.mode, plan)) or _inventory(),
    )

    assert inventory.account_id == ACCOUNT
    assert calls == [("cloak_browser", (
        ("identity", "/users/0.1/users/"),
        ("projects", "/projects/0.1/self/"),
        ("milestones:123", "/projects/0.1/projects/123/milestones/"),
        ("hourly_contracts", "/projects/0.1/hourly_contracts/"),
        ("ip_contract:123", "/projects/0.1/projects/123/ip_contracts/"),
    ))]
