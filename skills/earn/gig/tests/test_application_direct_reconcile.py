import importlib.util
import inspect
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "application_direct.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("application_direct_reconcile_test", SCRIPT)
application_direct = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(application_direct)

PARENT_SPEC = importlib.util.spec_from_file_location(
    "application_parent_full_history_test", SCRIPT.parent / "application_parent.py"
)
application_parent = importlib.util.module_from_spec(PARENT_SPEC)
assert PARENT_SPEC.loader is not None
PARENT_SPEC.loader.exec_module(application_parent)
fence = application_parent.fence


def test_same_wake_reconcile_reuses_durable_parent_after_delay():
    source = inspect.getsource(application_direct.main)
    block = source[source.index("awaiting_exact_readback ="):source.index("if phase == \"refresh\"")]

    assert application_direct.SAME_WAKE_RECONCILE_DELAY_SECONDS == 60
    assert block.index("time.sleep(SAME_WAKE_RECONCILE_DELAY_SECONDS)") < block.index(
        "reconcile = _run_parent("
    )
    assert "attempt_budget_path=attempt_budget_path" in block
    assert 'lease_task=f"{lease_task}-reconcile"' in block
    assert "click_submit" not in block


def _started_intent(store, request_id):
    payload = fence.intent_payload(
        request_id=request_id, snapshot_sha256="a" * 64,
        proposal_text="提案本文です。" * 40, price_jpy=10_000,
        deliver_date="2026-10-01",
        lease_fence={"task": "full-history-test", "token": "b" * 32, "generation": 1},
    )
    with store.locked(request_id):
        fence._durable_replace(store.intent_path(request_id), payload)
        return store.mark_irreversible_attempt_started_locked(
            request_id, expected_cas=payload["cas"],
        )


def test_full_history_reconcile_confirms_present_and_retires_absent(tmp_path, monkeypatch):
    store = fence.IntentStore(tmp_path / "intents")
    present = _started_intent(store, "123")
    absent = _started_intent(store, "456")
    targets = application_parent._durable_uncertain_intents(store)
    ledger = tmp_path / "applied.jsonl"
    original_confirm = application_parent._confirm_locked

    def ledger_first(store_arg, request_id, intent):
        assert '"requestId":"123"' in ledger.read_text(encoding="utf-8")
        return original_confirm(store_arg, request_id, intent)

    monkeypatch.setattr(application_parent, "_confirm_locked", ledger_first)

    result = application_parent.reconcile_durable_intents_from_full_history(
        store=store, targets=targets, observed_ids={"123"},
        evidence_path=tmp_path / "history.json", ledger_path=ledger,
        evidence_dir=tmp_path / "evidence", pass_id="pass",
    )

    assert result == {"checked": 2, "confirmed": 1, "retired_absent": 1}
    assert store.read("123")["state"] == fence.CONFIRMED
    assert store.read("456")["state"] == fence.RETIRED_ABSENT
    assert present["cas"] == store.read("123")["cas"]
    assert absent["cas"] == store.read("456")["cas"]
    ledger_row = json.loads(ledger.read_text(encoding="utf-8"))
    assert ledger_row["recorded_by"] == "application_report_intent_recovery"
    assert ledger_row["applied_page_evidence"] == str((tmp_path / "history.json").resolve())
    recovery = json.loads((
        tmp_path / "evidence/gig-pass-B2-123-submitted.intent.json"
    ).read_text(encoding="utf-8"))
    assert recovery["state"] == fence.CONFIRMED
    assert recovery["cas"] == present["cas"]
    assert recovery["official_readback"] == str((tmp_path / "history.json").resolve())


def test_full_history_reconcile_does_not_touch_non_started_intent(tmp_path):
    store = fence.IntentStore(tmp_path / "intents")
    payload = fence.intent_payload(
        request_id="789", snapshot_sha256="a" * 64,
        proposal_text="提案本文です。" * 40, price_jpy=10_000,
        deliver_date="2026-10-01",
        lease_fence={"task": "full-history-test", "token": "b" * 32, "generation": 1},
    )
    fence._durable_replace(store.intent_path("789"), payload)
    targets = application_parent._durable_uncertain_intents(store)

    result = application_parent.reconcile_durable_intents_from_full_history(
        store=store, targets=targets, observed_ids=set(),
        evidence_path=tmp_path / "history.json",
        ledger_path=tmp_path / "applied.jsonl", evidence_dir=tmp_path / "evidence",
        pass_id="pass",
    )

    assert result == {"checked": 0, "confirmed": 0, "retired_absent": 0}
    assert store.read("789")["state"] == fence.PREPARED


def test_full_history_reconcile_ignores_intent_created_after_target_snapshot(tmp_path):
    store = fence.IntentStore(tmp_path / "intents")
    _started_intent(store, "111")
    targets = application_parent._durable_uncertain_intents(store)
    _started_intent(store, "222")

    result = application_parent.reconcile_durable_intents_from_full_history(
        store=store, targets=targets, observed_ids=set(),
        evidence_path=tmp_path / "history.json",
        ledger_path=tmp_path / "applied.jsonl", evidence_dir=tmp_path / "evidence",
        pass_id="pass",
    )

    assert result == {"checked": 1, "confirmed": 0, "retired_absent": 1}
    assert store.read("111")["state"] == fence.RETIRED_ABSENT
    assert store.read("222")["state"] == fence.PREPARED


def test_full_history_reconcile_runs_before_fresh_snapshot_collection():
    source = inspect.getsource(application_parent.run_parent)

    assert source.index("uncertain_intents = _durable_uncertain_intents") < source.index(
        "snapshot = collect_snapshot_with_readonly_retry"
    )
    assert "max_pages=_APPLIED_OFFERS_RECONCILE_MAX_PAGES" in source

    wrapper_source = inspect.getsource(application_direct._validate_parent_result)
    assert 'rglob("parent-B2-applied-full-history.json")' in wrapper_source
