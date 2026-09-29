from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


PATH = Path(__file__).resolve().parents[1] / "scripts" / "coconala_paid_adapter.py"


def load():
    spec = importlib.util.spec_from_file_location("coconala_paid_adapter_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def item(event: str = "a" * 64) -> dict:
    return {
        "talkroom_id": "18211957", "buyer_feedback_sha256": event,
        "talkroom_state": "取引中", "talkroom_observed_at": "2026-09-07T00:00:00Z",
        "buyer": "buyer", "title": "work", "buyer_feedback_message_identities": ["m1"],
    }


def test_maps_coconala_identity_and_cumulative_context() -> None:
    module = load()
    adapter = module.CoconalaPaidAdapter(
        account_id="seller-1", inventory_reader=lambda: [item()],
        refresh_reader=lambda row: dict(row),
        context_reader=lambda row: {"requirements": ["deliver"], "attachments": []},
        effect_runner=lambda intent: None,
        readback_reader=lambda intent: {"verified": False},
    )
    rows = adapter.observe_active()
    assert rows == [{
        "provider": "coconala", "account_id": "seller-1", "work_id": "18211957",
        "latest_event_id": "a" * 64, "provider_state": "取引中",
        "observed_at": "2026-09-07T00:00:00Z",
    }]
    assert adapter.context("18211957") == {"requirements": ["deliver"], "attachments": []}


def test_refresh_uses_official_targeted_reader() -> None:
    module = load()
    refreshed = item("b" * 64)
    adapter = module.CoconalaPaidAdapter(
        account_id="seller-1", inventory_reader=lambda: [item()],
        refresh_reader=lambda row: refreshed,
        context_reader=lambda row: {}, effect_runner=lambda intent: None,
        readback_reader=lambda intent: {"verified": False},
    )
    adapter.observe_active()
    assert adapter.observe_one("18211957")["latest_event_id"] == "b" * 64


def test_inventory_accepts_the_orders_only_snapshot_before_targeted_readback() -> None:
    module = load()
    preliminary = {
        "talkroom_id": "18211957",
        "status": "paid",
        "snapshot_captured_at": "2026-09-07T00:00:00Z",
    }
    adapter = module.CoconalaPaidAdapter(
        account_id="seller-1", inventory_reader=lambda: [preliminary],
        refresh_reader=lambda row: {**row, **item()},
        context_reader=lambda row: {}, effect_runner=lambda intent: None,
        readback_reader=lambda intent: {"verified": False},
    )

    assert adapter.observe_active() == [{
        "provider": "coconala", "account_id": "seller-1", "work_id": "18211957",
        "latest_event_id": "2026-09-07T00:00:00Z", "provider_state": "paid",
        "observed_at": "2026-09-07T00:00:00Z",
    }]


def test_mutation_and_readback_remain_adapter_owned() -> None:
    module = load()
    effects = []
    adapter = module.CoconalaPaidAdapter(
        account_id="seller-1", inventory_reader=lambda: [item()],
        refresh_reader=lambda row: row, context_reader=lambda row: {},
        effect_runner=lambda intent: effects.append(intent),
        readback_reader=lambda intent: {"verified": True, "provider_receipt_id": "message-9",
                                        "observed_at": "2026-09-07T00:01:00Z"},
    )
    intent = {"effect_key": "key", "work_id": "18211957"}
    adapter.mutate(intent)
    assert effects == [intent]
    assert adapter.readback(intent)["provider_receipt_id"] == "message-9"


def test_shared_decision_preserves_coconala_effect_kind() -> None:
    module = load()
    base = {"context": {"_paid_prepare_status": "prepared",
                        "_bridge_prepared_path": "/tmp/prepared.json"}}
    assert module._decision({**base, "context": {**base["context"],
                              "_paid_mode": "cancellation"}})["action"] == "cancel"
    assert module._decision({**base, "context": {**base["context"],
                              "_paid_mode": "file", "delivery_action": "progress"}})["action"] == "submit"
    formal = {**base, "context": {**base["context"],
                                   "_paid_mode": "file", "delivery_action": "formal"}}
    assert module._decision(formal) == {
        "action": "wait", "reason": "formal_delivery_disabled",
        "remaining_work": ["retain prepared delivery until formal delivery is authorized"],
    }
    assert module._decision(formal, allow_formal_delivery=True)["action"] == "formal_delivery"
    assert module._decision({**base, "context": {**base["context"],
                              "_paid_mode": "answer"}})["action"] == "answer"


def test_shared_decision_maps_existing_terminal_and_wait_states() -> None:
    module = load()
    assert module._decision({"context": {"_paid_prepare_status": "no_effect",
                                         "status": "awaiting_buyer"}}) == {
        "action": "noop", "classification": "awaiting_buyer"
    }
    assert module._decision({"context": {
        "_paid_prepare_status": "pending", "reason": "external_access",
        "remaining_work": ["obtain access"],
    }}) == {"action": "wait", "reason": "external_access",
           "remaining_work": ["obtain access"]}


def test_paid_handoff_maps_only_an_official_funded_order() -> None:
    module = load()
    source = {
        **item(),
        "contract_id": "talkroom:18211957",
        "status": "paid",
        "price_jpy": 1000,
        "price_source": "structured_order_label",
        "talkroom_state": "取引中",
        "talkroom_evidence_sha256": "b" * 64,
    }
    adapter = module.CoconalaPaidAdapter(
        account_id="seller-1", inventory_reader=lambda: [source],
        refresh_reader=lambda row: dict(row), context_reader=lambda row: {
            "_paid_prepare_status": "prepared",
            "buyer_feedback_sha256": "a" * 64,
            "requirements_sha256": "c" * 64,
        }, effect_runner=lambda intent: None,
        readback_reader=lambda intent: {"verified": False},
    )
    adapter.observe_active()

    assert adapter.paid_handoff("18211957", {
        "buyer_feedback_sha256": "a" * 64,
        "requirements_sha256": "c" * 64,
    }) == {
        "contract": {
            "schema_version": 1,
            "record_type": "contract_receipt",
            "platform": "coconala",
            "application_external_id": "direct-order:talkroom:18211957",
            "work_external_id": "18211957",
            "contract_external_id": "talkroom:18211957",
            "status": "accepted",
            "terms_sha256": "b" * 64,
            "observed_at": "2026-09-07T00:00:00Z",
        },
        "handoff": {
            "schema_version": 1,
            "record_type": "paid_handoff_receipt",
            "platform": "coconala",
            "thread_external_id": "18211957",
            "contract_external_id": "talkroom:18211957",
            "funding_external_id": "order:talkroom:18211957",
            "scope_sha256": "a" * 64,
            "artifact_requirement_sha256": "c" * 64,
            "price_minor": 1000,
            "currency": "JPY",
            "status": "funded",
            "observed_at": "2026-09-07T00:00:00Z",
        },
    }


def test_paid_handoff_fails_closed_without_official_funding_or_scope() -> None:
    module = load()
    source = {
        **item(),
        "contract_id": "talkroom:18211957",
        "status": "unknown",
        "price_jpy": 1000,
        "price_source": "structured_order_label",
        "talkroom_evidence_sha256": "b" * 64,
    }
    adapter = module.CoconalaPaidAdapter(
        account_id="seller-1", inventory_reader=lambda: [source],
        refresh_reader=lambda row: dict(row), context_reader=lambda row: {},
        effect_runner=lambda intent: None,
        readback_reader=lambda intent: {"verified": False},
    )
    adapter.observe_active()

    try:
        adapter.paid_handoff("18211957", {})
    except RuntimeError as error:
        assert str(error) == "coconala_paid_handoff_unavailable"
    else:
        raise AssertionError("Coconala handoff was accepted without funded scope proof")


def test_default_build_reuses_paid_direct_runtime_without_copying_owner(tmp_path: Path) -> None:
    module = load()
    adapter, decide = module.build([
        "--account-id", "seller-1",
        "--bridge-root", str(tmp_path / "bridge"),
        "--evidence-dir", str(tmp_path / "evidence"),
        "--projects-root", str(tmp_path / "projects"),
    ])
    assert isinstance(adapter, module.CoconalaPaidAdapter)
    assert adapter.account_id == "seller-1"
    assert decide({"context": {"_paid_prepare_status": "no_effect"}}) == {
        "action": "noop", "classification": "satisfied_noop"
    }
    assert adapter.context_reader.__self__.paid.__file__.endswith("/paid_direct.py")


def test_bridge_maps_only_auth_navigation_failure_to_inventory_wait(tmp_path: Path) -> None:
    module = load()

    class Failure(RuntimeError):
        def __init__(self, step: str, detail: str):
            self.step = step
            self.detail = detail

    class Paid:
        def observe_orders(self, args, evidence_dir):
            raise Failure("orders_observation", "authenticated tab did not finish navigation")

    Paid.Failure = Failure

    bridge = module._CoconalaPaidBridge(Paid(), type("Args", (), {
        "evidence_dir": tmp_path,
    })(), tmp_path)
    try:
        bridge.inventory()
    except module.CoconalaPaidInventoryWait as error:
        assert error.paid_wait_reason == "provider_authentication_required"
        assert error.paid_remaining_work == [
            "restore the authenticated Coconala session and retry official inventory"
        ]
    else:
        raise AssertionError("authentication wait was not classified")


def test_bridge_does_not_hide_non_auth_inventory_failure(tmp_path: Path) -> None:
    module = load()

    class Failure(RuntimeError):
        def __init__(self):
            self.step = "orders_observation"
            self.detail = "selector mismatch"

    class Paid:
        def observe_orders(self, args, evidence_dir):
            raise Failure()

    Paid.Failure = Failure

    bridge = module._CoconalaPaidBridge(Paid(), type("Args", (), {
        "evidence_dir": tmp_path,
    })(), tmp_path)
    try:
        bridge.inventory()
    except Failure:
        pass
    else:
        raise AssertionError("unexpected inventory failure was hidden")
