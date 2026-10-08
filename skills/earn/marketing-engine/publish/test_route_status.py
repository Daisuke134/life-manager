import pathlib
import json
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from route_status import evaluate_route


ACCOUNT = {
    "account_id": "tiktok.obou_anicca", "status": "approved_active",
    "native_handle": "obou_anicca", "publisher_integration_id": "integration-1",
    "publisher_provider": "tiktok",
}


def test_exact_active_integration_is_ready():
    result = evaluate_route(ACCOUNT, [{
        "id": "integration-1", "identifier": "tiktok", "profile": "@obou_anicca",
        "disabled": False,
    }])
    assert result["route_ready"] is True
    assert result["blockers"] == []


def test_live_english_monk_tiktok_registry_matches_enabled_postiz_identity():
    account_path = HERE.parent / "registry" / "accounts" / "tiktok.monk_anicca.json"
    account = json.loads(account_path.read_text(encoding="utf-8"))
    result = evaluate_route(account, [{
        "id": "cmo5rwq2p00twn10yrsdglng3", "identifier": "tiktok",
        "profile": "monk_anicca", "disabled": False,
    }])
    assert result["route_ready"] is True
    assert result["blockers"] == []


def test_disabled_remote_and_local_state_are_explicit_blockers():
    result = evaluate_route(ACCOUNT | {"status": "disabled_verified"}, [{
        "id": "integration-1", "identifier": "tiktok", "profile": "obou_anicca",
        "disabled": True,
    }])
    assert result["route_ready"] is False
    assert result["blockers"] == ["local account status is disabled_verified",
                                   "Postiz integration is disabled"]


def test_missing_duplicate_or_wrong_identity_fails_closed():
    assert "expected integration not found" in evaluate_route(ACCOUNT, [])["blockers"]
    duplicate = {"id": "integration-1", "identifier": "tiktok",
                 "profile": "obou_anicca", "disabled": False}
    assert "expected integration is not unique" in evaluate_route(
        ACCOUNT, [duplicate, duplicate])["blockers"]
    wrong = duplicate | {"identifier": "youtube", "profile": "someone_else"}
    blockers = evaluate_route(ACCOUNT, [wrong])["blockers"]
    assert "provider identifier mismatch" in blockers
    assert "native profile mismatch" in blockers
