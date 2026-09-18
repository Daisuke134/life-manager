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


def state():
    return {
        "inventory_event_id": "427795630",
        "intent": {
            "action": "accept_contract",
            "thread_id": "305271360",
            "payload": {
                "title": "Job title",
                "amount": "12円",
                "client": "Client",
                "worker": "Worker",
            },
        },
    }


def test_pending_proposal_requires_exact_offer_and_pending_markers():
    module = load()
    proof = module.pending_proposal_proof(
        owner="crowdworks-revenue-reply",
        occurrence="crowdworks-revenue-reply:run-1",
        state=state(),
        row={"thread_id": "305271360", "id": "427795630"},
        url="https://crowdworks.jp/proposals/306070895#scroll_to_message",
        title="Job title - CrowdWorks",
        body="Client Worker 12円 Job title",
        progress="まだクライアントが契約に同意していません。クライアントが契約に同意すると契約成立",
    )
    assert proof["verified"] is True
    assert proof["proof_type"] == "pre_effect"
    assert proof["evidence_ref"].startswith("crowdworks://proposal-pending/")


def test_pending_proposal_rejects_contract_page_or_changed_terms():
    module = load()
    common = dict(
        owner="crowdworks-revenue-reply",
        occurrence="crowdworks-revenue-reply:run-1",
        state=state(),
        row={"thread_id": "305271360", "id": "427795630"},
        title="Job title - CrowdWorks",
        body="Client Worker 12円 Job title",
        progress="まだクライアントが契約に同意していません。クライアントが契約に同意すると契約成立",
    )
    assert module.pending_proposal_proof(
        **common, url="https://crowdworks.jp/contracts/63657015"
    ) is None
    changed = {**common, "url": "https://crowdworks.jp/proposals/306070895",
               "body": "Client Worker 99円 Job title"}
    assert module.pending_proposal_proof(**changed) is None


def test_reconcile_is_read_only_without_resolve(tmp_path, monkeypatch):
    module = load()
    state_path = tmp_path / "threads" / "item" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps(state()), encoding="utf-8")
    monkeypatch.setattr(module, "read_provider_state", lambda *_args, **_kwargs: {
        "state": state(), "row": {"thread_id": "305271360", "id": "427795630"},
        "url": "https://crowdworks.jp/proposals/306070895",
        "title": "Job title - CrowdWorks", "body": "Client Worker 12円 Job title",
        "progress": "まだクライアントが契約に同意していません。クライアントが契約に同意すると契約成立",
    })
    monkeypatch.setattr(module, "resolve_pre_effect_occurrence",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("resolve must be opt-in")))

    result = module.reconcile(
        state_root=tmp_path, owner="crowdworks-revenue-reply",
        occurrence="crowdworks-revenue-reply:run-1", thread_id="305271360",
        resolve=False,
    )

    assert result["resolved"] is False
    assert result["proof_type"] == "pre_effect"
