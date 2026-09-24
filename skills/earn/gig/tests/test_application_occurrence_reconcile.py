import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "application_occurrence_reconcile.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("application_occurrence_reconcile_test", SCRIPT)
reconcile = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reconcile)


OWNER = "hf-gig-apply-direct"
OCCURRENCE = "hf-gig-apply-direct:18d6e6e0c10fa690-98578"
REQUEST_ID = "5280157"


def _intent(path: Path, *, state="prepared", phase="irreversible_attempt_started"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": 2,
        "state": state,
        "effect_phase": phase,
        "request_id": REQUEST_ID,
        "cas": "a" * 64,
        "price_jpy": 8000,
        "deliver_date": "2026-09-25",
        "proposal_sha256": "b" * 64,
    }), encoding="utf-8")


def _readback(**overrides):
    value = {
        "source": "code_owned_cdp_readback",
        "observed": True,
        "not_found": False,
        "request_ids": [REQUEST_ID],
        "expected_ids": [REQUEST_ID],
        "pages_walked": 1,
        "cards_seen": 20,
        "urls": ["https://coconala.com/mypage/job_matching/applied/offers"],
        "truncated": False,
        "access_denied": False,
    }
    value.update(overrides)
    return value


def _historical_no_dispatch_proof(evidence_ref="historical-proof.json", **overrides):
    value = {
        "source": "code_owned_cdp_historical_identity_reconcile",
        "provider": "coconala",
        "proof_type": "historical_account_bound_no_dispatch",
        "historical_pass_id": "gig-apply-direct-1789863656491097000-13326",
        "historical_account": {
            "account_id": "2564121",
            "profile_url": "https://coconala.com/users/2564121",
        },
        "account_binding": {
            "sibling_request_id": "5281717",
            "sibling_pass_id": "gig-apply-direct-1789863656491097000-13326-commit-5281717",
            "official_profile_url": "https://coconala.com/users/2564121",
            "local_receipt_verified": True,
        },
        "target_roster": {
            "request_id": REQUEST_ID,
            "official_url": "https://coconala.com/requests/5280157",
            "complete": True,
            "truncated": False,
            "access_denied": False,
            "applicants_count": 9,
            "contracted_count": 0,
            "applicant_ids": [
                "6130185", "6299295", "412998", "4288437", "6200620",
                "4766238", "4197088", "4479825", "3406932",
            ],
            "historical_account_absent": True,
        },
        "evidence_ref": evidence_ref,
    }
    value.update(overrides)
    return value


def test_build_provider_proof_requires_exact_positive_id(tmp_path):
    proof = reconcile.build_provider_proof(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        request_id=REQUEST_ID,
        readback=_readback(),
        evidence_path=tmp_path / "readback.json",
    )
    assert proof["verified"] is True
    assert proof["provider_receipt_id"].endswith("#request-5280157")
    assert proof["evidence_ref"].endswith("readback.json")

    with pytest.raises(reconcile.ReconcileContractError, match="exact_id_not_observed"):
        reconcile.build_provider_proof(
            owner_id=OWNER,
            occurrence_id=OCCURRENCE,
            request_id=REQUEST_ID,
            readback=_readback(request_ids=[]),
            evidence_path=tmp_path / "readback.json",
        )


def test_build_historical_no_dispatch_proof_requires_bound_account_and_complete_roster(tmp_path):
    proof = reconcile.build_historical_no_dispatch_proof(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        request_id=REQUEST_ID,
        readback=_historical_no_dispatch_proof(),
    )
    assert proof["verified"] is True
    assert proof["proof_type"] == "historical_account_bound_no_dispatch"
    assert proof["historical_account_id"] == "2564121"

    for field, value in (
        ("historical_account_absent", False),
        ("complete", False),
        ("truncated", True),
        ("access_denied", True),
    ):
        candidate = _historical_no_dispatch_proof()
        candidate["target_roster"][field] = value
        with pytest.raises(reconcile.ReconcileContractError):
            reconcile.build_historical_no_dispatch_proof(
                owner_id=OWNER,
                occurrence_id=OCCURRENCE,
                request_id=REQUEST_ID,
                readback=candidate,
            )


def test_historical_no_dispatch_reconcile_uses_dedicated_resolver(tmp_path):
    intent_root = tmp_path / "intents"
    _intent(intent_root / f"{REQUEST_ID}.json")
    captured = []

    def resolver(owner_id, occurrence_id, *, no_dispatch_proof, expected_state=None):
        captured.append((owner_id, occurrence_id, no_dispatch_proof(), expected_state))
        return True

    result = reconcile.reconcile_historical_no_dispatch_occurrence(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        request_id=REQUEST_ID,
        intent_root=intent_root,
        readback=lambda: _historical_no_dispatch_proof(),
        resolver=resolver,
    )
    assert result["status"] == "resolved"
    assert captured[0][0:2] == (OWNER, OCCURRENCE)
    assert captured[0][2]["historical_account_id"] == "2564121"
    assert captured[0][3] == "claimed"


def test_discovery_requires_a_single_occurrence_and_single_intent():
    assert reconcile.select_single_target(
        unknown_occurrences=[OCCURRENCE],
        uncertain_request_ids=[REQUEST_ID],
    ) == (OCCURRENCE, REQUEST_ID)
    assert reconcile.select_single_target(
        unknown_occurrences=[OCCURRENCE, "hf-gig-apply-direct:other"],
        uncertain_request_ids=[REQUEST_ID],
    ) is None
    assert reconcile.select_single_target(
        unknown_occurrences=[OCCURRENCE],
        uncertain_request_ids=[REQUEST_ID, "5280158"],
    ) is None


def test_denied_or_incomplete_readback_never_calls_resolver(tmp_path):
    intent_root = tmp_path / "intents"
    _intent(intent_root / f"{REQUEST_ID}.json")
    calls = []

    result = reconcile.reconcile_occurrence(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        request_id=REQUEST_ID,
        intent_root=intent_root,
        evidence_path=tmp_path / "readback.json",
        readback=lambda: _readback(
            request_ids=[],
            access_denied=True,
            truncated=True,
            pages_walked=0,
        ),
        resolver=lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )

    assert result["status"] == "unresolved"
    assert result["reason"] == "official_readback_access_denied"
    assert calls == []


def test_readback_exception_keeps_stable_provider_reason(tmp_path):
    intent_root = tmp_path / "intents"
    _intent(intent_root / f"{REQUEST_ID}.json")
    result = reconcile.reconcile_occurrence(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        request_id=REQUEST_ID,
        intent_root=intent_root,
        evidence_path=tmp_path / "readback.json",
        readback=lambda: (_ for _ in ()).throw(
            reconcile.parent.ParentContractError("official_readback_access_denied")
        ),
        resolver=lambda *args, **kwargs: pytest.fail("resolver must not run"),
    )
    assert result["reason"] == "official_readback_access_denied"
    assert result["error_class"] == "ParentContractError"


def test_exact_positive_readback_resolves_matching_occurrence(tmp_path):
    intent_root = tmp_path / "intents"
    _intent(intent_root / f"{REQUEST_ID}.json")
    captured = []

    def resolver(owner_id, occurrence_id, *, official_readback, expected_state=None):
        captured.append((owner_id, occurrence_id, official_readback(), expected_state))
        return True

    result = reconcile.reconcile_occurrence(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        request_id=REQUEST_ID,
        intent_root=intent_root,
        evidence_path=tmp_path / "readback.json",
        readback=lambda: _readback(),
        resolver=resolver,
    )

    assert result["status"] == "resolved"
    assert captured[0][0:2] == (OWNER, OCCURRENCE)
    assert captured[0][2]["request_id"] == REQUEST_ID
    assert captured[0][3] == "claimed"


@pytest.mark.parametrize(
    ("state", "phase"),
    [("confirmed", "irreversible_attempt_started"),
     ("prepared", "pre_effect")],
)
def test_reconcile_rejects_non_uncertain_intent(tmp_path, state, phase):
    intent_root = tmp_path / "intents"
    _intent(intent_root / f"{REQUEST_ID}.json", state=state, phase=phase)
    result = reconcile.reconcile_occurrence(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        request_id=REQUEST_ID,
        intent_root=intent_root,
        evidence_path=tmp_path / "readback.json",
        readback=lambda: pytest.fail("provider readback must not run"),
        resolver=lambda *args, **kwargs: pytest.fail("resolver must not run"),
    )
    assert result["status"] == "unresolved"
    assert result["reason"] == "intent_not_effect_started"
