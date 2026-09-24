import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location(
    "application_parent_identity_test", SCRIPT_DIR / "application_parent.py"
)
application_parent = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.path.insert(0, str(SCRIPT_DIR))
SPEC.loader.exec_module(application_parent)


def test_authenticated_identity_requires_provider_owned_numeric_profile_path():
    identity = application_parent._validated_authenticated_identity(
        "5280157",
        {
            "url": "https://coconala.com/offers/add/5280157",
            "title": "応募する",
            "own_user_path": "/users/2564121",
            "selection": "header",
            "candidate_user_paths": ["/users/2564121"],
        },
    )

    assert identity["provider"] == "coconala"
    assert identity["request_id"] == "5280157"
    assert identity["account_id"] == "2564121"
    assert identity["profile_url"] == "https://coconala.com/users/2564121"
    assert identity["source"] == "code_owned_cdp_authenticated_identity"


@pytest.mark.parametrize(
    "raw,error",
    [
        ({"url": "https://coconala.com/offers/add/5280157", "own_user_path": None}, "authenticated_identity_readback_missing"),
        ({"url": "https://coconala.com/offers/add/5280157", "own_user_path": "/users/not-a-number"}, "authenticated_identity_readback_missing"),
        ({"url": "https://evil.example/offers/add/5280157", "own_user_path": "/users/2564121"}, "authenticated_identity_provider_route_invalid"),
    ],
)
def test_authenticated_identity_rejects_unbound_or_wrong_provider(raw, error):
    with pytest.raises(application_parent.ParentContractError, match=error):
        application_parent._validated_authenticated_identity("5280157", raw)


def test_fixture_capture_uses_exact_profile_identity():
    snapshot = {
        "request_details": [{
            "request_id": "5280157",
            "canonical_url": "https://coconala.com/requests/5280157",
            "title": "target",
            "category": "category",
            "visible_text": "target",
            "accepting_applications": True,
            "budget_min_jpy": 1,
            "budget_max_jpy": 2,
            "applicants_count": 0,
            "contracted_count": 0,
            "applicants": [],
            "application_questions": [],
            "observed_at": "2026-09-24T00:00:00Z",
            "client_order_rate": 0,
        }],
        "already_applied_ids": [],
    }
    effects = application_parent.FixtureEffects(snapshot, {
        "authenticated_identity": {
            "url": "https://coconala.com/offers/add/5280157",
            "title": "応募する",
            "own_user_path": "/users/2564121",
            "selection": "header",
            "candidate_user_paths": ["/users/2564121"],
        },
    })

    captured = effects.capture_authenticated_identity("5280157")

    assert captured["account_id"] == "2564121"
    assert captured["request_id"] == "5280157"


def test_fixture_capture_fails_closed_when_identity_is_missing():
    snapshot = {
        "request_details": [],
        "already_applied_ids": [],
    }
    effects = application_parent.FixtureEffects(snapshot, {
        "authenticated_identity": {
            "url": "https://coconala.com/offers/add/5280157",
            "title": "応募する",
            "own_user_path": None,
        },
    })

    with pytest.raises(application_parent.ParentContractError, match="authenticated_identity_readback_missing"):
        effects.capture_authenticated_identity("5280157")
