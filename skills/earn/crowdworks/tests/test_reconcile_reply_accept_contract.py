import importlib.util
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


def test_reconcile_is_read_only_without_resolve(tmp_path, monkeypatch):
    module = load()
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
