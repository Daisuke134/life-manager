import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/crowdworks/scripts/reconcile_reply_accept_contract.py"


def load():
    spec = importlib.util.spec_from_file_location("crowdworks_reconcile_reply_accept_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def state(occurrence="crowdworks-revenue-reply:run-1"):
    return {
        "occurrence_id": occurrence,
        "intent": {"action": "accept_contract", "thread_id": "305271360"},
    }


def test_pending_client_consent_is_not_an_effect_receipt():
    module = load()
    assert module.official_accept_proof(
        owner="crowdworks-revenue-reply", occurrence="crowdworks-revenue-reply:run-1",
        state=state(), readback={},
    ) is None


def test_verified_provider_receipt_is_bound_to_exact_occurrence():
    module = load()
    proof = module.official_accept_proof(
        owner="crowdworks-revenue-reply", occurrence="crowdworks-revenue-reply:run-1",
        state=state(), readback={
            "verified": True, "provider_receipt_id": "condition-accepted:42075801",
            "observed_at": "2026-09-18T00:00:00Z",
        },
    )
    assert proof["proof_type"] == "official_effect"
    assert proof["provider_receipt_id"] == "condition-accepted:42075801"


def test_mismatched_occurrence_cannot_use_another_intent_receipt():
    module = load()
    assert module.official_accept_proof(
        owner="crowdworks-revenue-reply", occurrence="crowdworks-revenue-reply:other",
        state=state(), readback={"verified": True, "provider_receipt_id": "x"},
    ) is None


def test_one_uncertain_sibling_blocks_occurrence_resolution(tmp_path):
    module = load()
    occurrence = "crowdworks-revenue-reply:run-1"
    first = tmp_path / "threads" / "first" / "state.json"
    second = tmp_path / "threads" / "second" / "state.json"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text(json.dumps({
        **state(occurrence), "status": "reconcile_unknown",
    }), encoding="utf-8")
    second.write_text(json.dumps({
        "version": 1, "occurrence_id": occurrence, "status": "reconcile_unknown",
        "intent": {"action": "reply", "thread_id": "other-thread"},
    }), encoding="utf-8")
    assert module.occurrence_effects_accounted(tmp_path, occurrence, "305271360") is False


def test_target_uncertain_state_can_be_accounted_by_its_receipt(tmp_path):
    module = load()
    occurrence = "crowdworks-revenue-reply:run-1"
    path = tmp_path / "threads" / "first" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        **state(occurrence), "status": "reconcile_unknown",
    }), encoding="utf-8")
    assert module.occurrence_effects_accounted(tmp_path, occurrence, "305271360") is True


def test_reconcile_is_read_only_without_resolve(tmp_path, monkeypatch):
    module = load()
    state_path = tmp_path / "threads" / "item" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({**state(), "status": "reconcile_unknown"}),
                          encoding="utf-8")
    monkeypatch.setattr(module, "read_provider_state", lambda *_args, **_kwargs: {
        "state": state(),
        "readback": {"verified": True, "provider_receipt_id": "condition-accepted:1"},
    })
    monkeypatch.setattr(module, "resolve_unknown_occurrence",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("resolve must be opt-in")))
    result = module.reconcile(
        state_root=tmp_path, owner="crowdworks-revenue-reply",
        occurrence="crowdworks-revenue-reply:run-1", thread_id="305271360",
        resolve=False,
    )
    assert result["resolved"] is False
    assert result["proof_type"] == "official_effect"
