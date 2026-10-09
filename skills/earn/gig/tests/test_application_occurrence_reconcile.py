import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "application_occurrence_reconcile.py"
sys.path.insert(0, str(SCRIPT.parent))
import application_effect_fence as fence
SPEC = importlib.util.spec_from_file_location("application_occurrence_reconcile_test", SCRIPT)
reconcile = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reconcile)


OWNER = "hf-gig-apply-direct"
OCCURRENCE = "hf-gig-apply-direct:18d6e6e0c10fa690-98578"
REQUEST_ID = "5280157"


def _intent(
    path: Path,
    *,
    state="prepared",
    phase="irreversible_attempt_started",
    request_id=REQUEST_ID,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = fence.intent_payload(
        request_id=request_id,
        snapshot_sha256="a" * 64,
        proposal_text="提案本文です。" * 40,
        price_jpy=8000,
        deliver_date="2026-09-25",
        lease_fence={"task": "historical-reconcile-test", "token": "b" * 32, "generation": 1},
        state=state,
        effect_phase=phase,
    )
    path.write_text(json.dumps(payload), encoding="utf-8")


def _bound_intent(intent_root, request_id, *, occurrence_id=OCCURRENCE, run_id="run-1", state="prepared"):
    path = Path(intent_root) / f"{request_id}.json"
    _intent(path, request_id=request_id, state="prepared", phase="pre_effect")
    store = fence.IntentStore(intent_root)
    current = store.read(request_id)
    with store.locked(request_id):
        started = store.mark_irreversible_attempt_started_locked(
            request_id,
            expected_cas=current["cas"],
            runtime_run_id=run_id,
            runtime_occurrence_id=occurrence_id,
        )
    if state == "confirmed":
        return store.confirm(request_id, expected_cas=started["cas"])
    return started


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
    _bound_intent(intent_root, REQUEST_ID)
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
    retired = json.loads((intent_root / f"{REQUEST_ID}.json").read_text(encoding="utf-8"))
    assert retired["state"] == fence.RETIRED_ABSENT
    archive = list((intent_root / "recovery-history" / REQUEST_ID).glob("*.json"))
    assert len(archive) == 1


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


def test_effect_started_intent_persists_exact_runtime_binding(tmp_path):
    started = _bound_intent(tmp_path, "123")

    assert started["state"] == "prepared"
    assert started["effect_phase"] == "irreversible_attempt_started"
    assert started["runtime_run_id"] == "run-1"
    assert started["runtime_occurrence_id"] == OCCURRENCE
    assert fence.is_pre_effect(started) is False
    assert fence.validate_intent(started) == []


def test_batch_target_groups_all_intents_for_one_exact_occurrence():
    intents = [
        {
            "request_id": "123",
            "state": "prepared",
            "effect_phase": "irreversible_attempt_started",
            "runtime_run_id": "run-1",
            "runtime_occurrence_id": OCCURRENCE,
        },
        {
            "request_id": "456",
            "state": "confirmed",
            "effect_phase": "irreversible_attempt_started",
            "runtime_run_id": "run-1",
            "runtime_occurrence_id": OCCURRENCE,
        },
    ]

    assert reconcile.select_batch_target(
        unknown_occurrences=[OCCURRENCE],
        intents=intents,
    ) == (OCCURRENCE, "run-1", ["123", "456"])
    assert reconcile.select_batch_target(
        unknown_occurrences=[OCCURRENCE, "hf-gig-apply-direct:other"],
        intents=intents,
    ) is None
    assert reconcile.select_batch_target(
        unknown_occurrences=[OCCURRENCE],
        intents=[intents[0], {**intents[1], "runtime_run_id": "other-run"}],
    ) is None
    assert reconcile.select_batch_target(
        unknown_occurrences=[OCCURRENCE],
        intents=[intents[0], {
            **{key: value for key, value in intents[1].items()
               if not key.startswith("runtime_")},
            "state": "prepared",
        }],
    ) is None


def test_batch_reconcile_closes_once_after_every_exact_id_is_official(tmp_path):
    intent_root = tmp_path / "intents"
    _bound_intent(intent_root, "123")
    _bound_intent(intent_root, "456")
    calls = []

    def resolver(owner_id, occurrence_id, *, official_readback, expected_state=None):
        calls.append((owner_id, occurrence_id, official_readback(), expected_state))
        return True

    result = reconcile.reconcile_batch_occurrence(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        runtime_run_id="run-1",
        request_ids=["123", "456"],
        intent_root=intent_root,
        evidence_path=tmp_path / "readback.json",
        readback=lambda: _readback(
            request_ids=["123", "456"],
            expected_ids=["123", "456"],
        ),
        resolver=resolver,
    )

    assert result["status"] == "resolved"
    assert result["request_ids"] == ["123", "456"]
    assert len(calls) == 1
    assert calls[0][0:2] == (OWNER, OCCURRENCE)
    assert calls[0][2]["request_ids"] == ["123", "456"]
    assert calls[0][3] == "claimed"
    assert fence.IntentStore(intent_root).read("123")["state"] == "confirmed"
    assert fence.IntentStore(intent_root).read("456")["state"] == "confirmed"


def test_batch_reconcile_keeps_fence_when_any_id_is_missing(tmp_path):
    intent_root = tmp_path / "intents"
    _bound_intent(intent_root, "123")
    _bound_intent(intent_root, "456")

    result = reconcile.reconcile_batch_occurrence(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        runtime_run_id="run-1",
        request_ids=["123", "456"],
        intent_root=intent_root,
        evidence_path=tmp_path / "readback.json",
        readback=lambda: _readback(
            request_ids=["123"],
            expected_ids=["123", "456"],
        ),
        resolver=lambda *args, **kwargs: pytest.fail("partial readback must not resolve"),
    )

    assert result["status"] == "unresolved"
    assert result["reason"] == "batch_exact_ids_not_observed"
    assert fence.IntentStore(intent_root).read("123")["state"] == "prepared"
    assert fence.IntentStore(intent_root).read("456")["state"] == "prepared"


def test_denied_or_incomplete_readback_never_calls_resolver(tmp_path):
    intent_root = tmp_path / "intents"
    _bound_intent(intent_root, REQUEST_ID)
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
    _bound_intent(intent_root, REQUEST_ID)
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
    _bound_intent(intent_root, REQUEST_ID)
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


def test_confirmed_intent_with_exact_provider_readback_resolves_stale_occurrence(tmp_path):
    """A successful intent may outlive the admission event that fenced it."""
    intent_root = tmp_path / "intents"
    _bound_intent(intent_root, REQUEST_ID, state="confirmed")
    captured = []

    def resolver(owner_id, occurrence_id, *, official_readback, expected_state=None):
        captured.append((owner_id, occurrence_id, official_readback(), expected_state))
        return True

    result = reconcile.reconcile_confirmed_occurrence(
        owner_id=OWNER,
        occurrence_id=OCCURRENCE,
        request_id=REQUEST_ID,
        intent_root=intent_root,
        evidence_path=tmp_path / "readback.json",
        readback=lambda: _readback(),
        resolver=resolver,
    )

    assert result["status"] == "resolved"
    assert result["reason"] == "confirmed_intent_provider_readback_confirmed"
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
