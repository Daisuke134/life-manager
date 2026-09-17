from __future__ import annotations

import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import time
import json


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "paid_kernel.py"
SPEC = importlib.util.spec_from_file_location("marketplace_paid_kernel", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
paid = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = paid
SPEC.loader.exec_module(paid)


def observation(work_id: str, event_id: str = "message-1") -> dict:
    return {
        "provider": "fixture",
        "account_id": "seller-1",
        "work_id": work_id,
        "latest_event_id": event_id,
        "provider_state": "active",
        "observed_at": "2026-09-07T00:00:00Z",
    }


class Adapter:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.current = {row["work_id"]: dict(row) for row in rows}
        self.effects: list[dict] = []
        self.readbacks: dict[str, dict] = {}

    def observe_active(self) -> list[dict]:
        return [dict(row) for row in self.rows]

    def observe_one(self, work_id: str) -> dict:
        return dict(self.current[work_id])

    def context(self, work_id: str) -> dict:
        return {"requirements": "complete " + work_id, "attachments": []}

    def mutate(self, intent: dict) -> None:
        with getattr(self, "lock", _NullLock()):
            self.effects.append(dict(intent))
            time.sleep(getattr(self, "mutation_delay", 0))
            self.readbacks[intent["effect_key"]] = {
                "verified": True,
                "provider_receipt_id": "receipt-" + intent["work_id"],
                "observed_at": "2026-09-07T00:01:00Z",
            }

    def readback(self, intent: dict) -> dict:
        return dict(self.readbacks.get(intent["effect_key"], {"verified": False}))


class _NullLock:
    def __enter__(self): return self
    def __exit__(self, *_args): return None


def submit(row: dict) -> dict:
    return {"action": "submit", "payload": {"message": "done " + row["work_id"]}}


def test_verified_effect_replays_with_zero_mutations(tmp_path: Path) -> None:
    adapter = Adapter([observation("work-1")])
    first = paid.run_wake(adapter=adapter, decide=submit, state_root=tmp_path)
    second = paid.run_wake(adapter=adapter, decide=submit, state_root=tmp_path)
    assert first["effect"] == 1 and first["readback"] == 1
    assert second["effect"] == 0 and second["readback"] == 1
    assert len(adapter.effects) == 1


def test_verified_effect_replays_zero_when_only_provider_digest_changes(
        tmp_path: Path) -> None:
    row = observation("work-1")
    row["buyer_event_id"] = "buyer-1"
    adapter = Adapter([row])

    def submit_with_buyer_event(source: dict) -> dict:
        return {"action": "submit", "payload": {
            "message": "done " + source["work_id"],
            "buyer_event_id": source["buyer_event_id"],
        }}

    assert paid.run_wake(adapter=adapter, decide=submit_with_buyer_event,
                         state_root=tmp_path)["effect"] == 1
    adapter.current["work-1"]["latest_event_id"] = "seller-message-digest"

    result = paid.run_wake(adapter=adapter, decide=submit_with_buyer_event,
                           state_root=tmp_path)

    assert result["effect"] == 0
    assert result["readback"] == 1
    assert len(adapter.effects) == 1


def test_uncertain_message_effect_never_replays_after_mutation_exception(tmp_path: Path) -> None:
    class FailingAdapter(Adapter):
        def mutate(self, intent: dict) -> None:
            self.effects.append(dict(intent))
            raise RuntimeError("message visibility delayed")

        def readback(self, intent: dict) -> dict:
            return {"authoritative_absent": True}

    adapter = FailingAdapter([observation("work-1")])
    first = paid.run_wake(adapter=adapter, decide=submit, state_root=tmp_path)
    second = paid.run_wake(adapter=adapter, decide=submit, state_root=tmp_path)

    assert first["failed"] == 1
    assert second["items"][0]["reason"] == "reconcile_unknown"
    assert len(adapter.effects) == 1


def test_single_worker_pre_effect_hint_clears_before_first_mutation(
        monkeypatch, tmp_path: Path) -> None:
    hint = tmp_path / "entrypoint-result.json"
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))
    created = paid._prepare_pre_effect_hint(1)
    assert created == hint
    assert json.loads(hint.read_text()) == {"status": "pre_effect_failure", "effect": 0}
    paid._clear_pre_effect_hint(created)
    assert not hint.exists()


def test_run_marker_persists_pre_effect_status(tmp_path: Path) -> None:
    marker = paid._prepare_run_marker(tmp_path, "fixture-paid:run-marker")
    assert marker is not None
    assert json.loads(marker.read_text()) == {
        "version": 1, "occurrence_id": "fixture-paid:run-marker",
        "status": "pre_effect",
    }


def test_run_marker_preserves_effect_started_after_zero_effect_failure(
        monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-paid:run-marker-failed")

    class MutatingFailureAdapter(Adapter):
        def mutate(self, intent: dict) -> None:
            raise RuntimeError("mutation failed after fence")

    result = paid.run_wake(
        adapter=MutatingFailureAdapter([observation("work-1")]),
        decide=submit,
        state_root=tmp_path,
    )

    assert result["effect"] == 0
    marker = paid._run_marker_path(tmp_path, "fixture-paid:run-marker-failed")
    assert json.loads(marker.read_text()) == {
        "version": 1,
        "occurrence_id": "fixture-paid:run-marker-failed",
        "status": "effect_started",
        "effect": 0,
    }


def test_state_records_the_runtime_occurrence_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-paid:run-1")
    adapter = Adapter([observation("work-1")])
    assert paid.run_wake(adapter=adapter, decide=submit, state_root=tmp_path)["effect"] == 1
    state = json.loads(next(tmp_path.glob("items/*/state.json")).read_text())
    assert state["occurrence_id"] == "fixture-paid:run-1"


def test_new_buyer_event_invalidates_verified_receipt_before_decision(tmp_path: Path) -> None:
    adapter = Adapter([observation("work-1")])
    assert paid.run_wake(adapter=adapter, decide=submit, state_root=tmp_path)["effect"] == 1
    adapter.current["work-1"]["latest_event_id"] = "message-2"
    received = []

    def noop(row: dict) -> dict:
        received.append(row["latest_event_id"])
        return {"action": "noop"}

    result = paid.run_wake(adapter=adapter, decide=noop, state_root=tmp_path)
    assert received == ["message-2"]
    assert result["items"][0]["status"] == "noop"
    assert len(adapter.effects) == 1


def test_new_buyer_event_invalidates_intent_before_mutation(tmp_path: Path) -> None:
    adapter = Adapter([observation("work-1")])

    def decide(row: dict) -> dict:
        adapter.current[row["work_id"]]["latest_event_id"] = "message-2"
        return submit(row)

    result = paid.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert result["effect"] == 0
    assert result["pending"] == 1
    assert result["items"][0]["reason"] == "newer_provider_event"


def test_blocked_item_does_not_prevent_sibling_effect(tmp_path: Path) -> None:
    adapter = Adapter([observation("blocked"), observation("ready")])

    def decide(row: dict) -> dict:
        if row["work_id"] == "blocked":
            return {"action": "wait", "reason": "external_access", "remaining_work": ["obtain access"]}
        return submit(row)

    result = paid.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert result["observed"] == 2
    assert result["effect"] == 1
    assert result["pending"] == 1
    assert result["failed"] == 0
    assert [row["work_id"] for row in adapter.effects] == ["ready"]


def test_state_survives_a_new_adapter_process_boundary(tmp_path: Path) -> None:
    first_adapter = Adapter([observation("work-1")])
    assert paid.run_wake(adapter=first_adapter, decide=submit, state_root=tmp_path)["effect"] == 1
    second_adapter = Adapter([observation("work-1")])
    second_adapter.readbacks = dict(first_adapter.readbacks)
    result = paid.run_wake(adapter=second_adapter, decide=submit, state_root=tmp_path)
    assert result["effect"] == 0
    assert result["readback"] == 1
    assert second_adapter.effects == []


def test_two_overlapping_wakes_mutate_same_effect_once(tmp_path: Path) -> None:
    adapter = Adapter([observation("work-1")])
    adapter.lock = threading.Lock()
    adapter.mutation_delay = 0.05
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: paid.run_wake(
            adapter=adapter, decide=submit, state_root=tmp_path
        ), range(2)))
    assert len(adapter.effects) == 1
    assert sorted(result["effect"] for result in results) == [0, 1]


def test_refresh_one_is_used_only_before_mutation(tmp_path: Path) -> None:
    class RefreshingAdapter(Adapter):
        def __init__(self):
            super().__init__([observation("work-1")])
            self.observation_calls = []

        def observe_one(self, work_id: str) -> dict:
            self.observation_calls.append(("observe", work_id))
            return super().observe_one(work_id)

        def refresh_one(self, work_id: str) -> dict:
            self.observation_calls.append(("refresh", work_id))
            return super().observe_one(work_id)

    adapter = RefreshingAdapter()
    result = paid.run_wake(adapter=adapter, decide=submit, state_root=tmp_path)

    assert result["effect"] == 1
    assert adapter.observation_calls == [("observe", "work-1"), ("refresh", "work-1")]


def test_one_failed_decision_does_not_stop_ready_sibling(tmp_path: Path) -> None:
    adapter = Adapter([observation("bad"), observation("ready")])

    def decide(row: dict) -> dict:
        if row["work_id"] == "bad":
            raise RuntimeError("private detail must not enter aggregate")
        return submit(row)

    result = paid.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert result["observed"] == 2
    assert result["effect"] == 1
    assert result["readback"] == 1
    assert result["failed"] == 1
    assert result["items"][0] == {
        "work_id": "bad", "status": "failed", "reason": "RuntimeError",
        "error_detail": "private detail must not enter aggregate",
        "effect": 0, "readback": 0, "failed": 1, "pre_effect": True,
    }


def test_pre_effect_item_failure_is_marked_without_mutation(tmp_path: Path) -> None:
    class ContextFailureAdapter(Adapter):
        def context(self, work_id: str) -> dict:
            raise RuntimeError("provider task surface unavailable")

    adapter = ContextFailureAdapter([observation("blocked")])
    result = paid.run_wake(adapter=adapter, decide=submit, state_root=tmp_path)

    assert result["effect"] == 0
    assert result["failed"] == 1
    assert result["items"][0]["pre_effect"] is True
    assert adapter.effects == []


def test_cli_marks_all_pre_effect_item_failures_for_runtime_hint(tmp_path: Path, monkeypatch) -> None:
    provider = tmp_path / "provider.py"
    provider.write_text(f'''
class Adapter:
    def observe_active(self):
        return [{observation("blocked")!r}]
    def observe_one(self, work_id):
        return {observation("blocked")!r}
    def context(self, work_id):
        raise RuntimeError("provider task surface unavailable")
    def mutate(self, intent):
        raise AssertionError("mutation must not start")
    def readback(self, intent):
        return {{"verified": False}}
def decide(row):
    return {{"action": "submit", "payload": {{"message": "done"}}}}
def build(argv): return Adapter(), decide
''', encoding="utf-8")
    output = tmp_path / "result.json"
    hint = tmp_path / "entrypoint-result.json"
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))

    assert paid.main([
        "--provider-adapter", str(provider), "--state-root", str(tmp_path / "state"),
        "--output", str(output),
    ]) == 1

    assert json.loads(hint.read_text(encoding="utf-8")) == {
        "status": "pre_effect_failure", "effect": 0,
    }


def test_model_decision_receives_provider_neutral_cumulative_context(tmp_path: Path) -> None:
    adapter = Adapter([observation("work-1")])
    received = []

    def decide(row: dict) -> dict:
        received.append(row)
        return {"action": "noop"}

    paid.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert received == [{**observation("work-1"), "context": {
        "requirements": "complete work-1", "attachments": []
    }}]


def test_one_cli_loads_provider_without_provider_branching(tmp_path: Path) -> None:
    provider = tmp_path / "provider.py"
    provider.write_text("""
class Adapter:
    def observe_active(self): return []
    def observe_one(self, work_id): raise AssertionError
    def context(self, work_id): raise AssertionError
    def mutate(self, intent): raise AssertionError
    def readback(self, intent): raise AssertionError
def decide(row): raise AssertionError
def build(argv):
    assert argv == ["--account", "seller-1"]
    return Adapter(), decide
""", encoding="utf-8")
    output = tmp_path / "result.json"
    rc = paid.main([
        "--provider-adapter", str(provider), "--state-root", str(tmp_path / "state"),
        "--output", str(output), "--", "--account", "seller-1",
    ])
    assert rc == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "actionable": 0, "effect": 0, "failed": 0, "items": [], "observed": 0,
        "pending": 0, "readback": 0, "status": "ok",
    }


def test_cli_persists_terminal_aggregate_when_provider_inventory_fails(tmp_path: Path) -> None:
    provider = tmp_path / "provider.py"
    provider.write_text("""
class Adapter:
    def observe_active(self): raise RuntimeError("private provider detail")
    def observe_one(self, work_id): raise AssertionError
    def context(self, work_id): raise AssertionError
    def mutate(self, intent): raise AssertionError
    def readback(self, intent): raise AssertionError
def decide(row): raise AssertionError
def build(argv): return Adapter(), decide
""", encoding="utf-8")
    output = tmp_path / "result.json"
    assert paid.main([
        "--provider-adapter", str(provider), "--state-root", str(tmp_path / "state"),
        "--output", str(output),
    ]) == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "status": "failed", "observed": 0, "actionable": 0, "effect": 0, "readback": 0,
        "failed": 1, "pending": 0, "failed_step": "provider_inventory",
        "error_type": "RuntimeError", "items": [],
    }


def test_cli_marks_provider_inventory_failure_as_pre_effect_failure(tmp_path: Path, monkeypatch) -> None:
    provider = tmp_path / "provider.py"
    provider.write_text("""
class Adapter:
    def observe_active(self): raise RuntimeError("inventory unavailable")
    def observe_one(self, work_id): raise AssertionError
    def context(self, work_id): raise AssertionError
    def mutate(self, intent): raise AssertionError
    def readback(self, intent): raise AssertionError
def decide(row): raise AssertionError
def build(argv): return Adapter(), decide
""", encoding="utf-8")
    output = tmp_path / "result.json"
    hint = tmp_path / "entrypoint-result.json"
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))

    assert paid.main([
        "--provider-adapter", str(provider), "--state-root", str(tmp_path / "state"),
        "--output", str(output),
    ]) == 1

    assert json.loads(hint.read_text(encoding="utf-8")) == {
        "status": "pre_effect_failure", "effect": 0,
    }


def test_cli_inventory_failure_persists_completed_zero_effect_run_marker(tmp_path: Path, monkeypatch) -> None:
    provider = tmp_path / "provider.py"
    provider.write_text("""
class Adapter:
    def observe_active(self): raise RuntimeError("inventory unavailable")
    def observe_one(self, work_id): raise AssertionError
    def context(self, work_id): raise AssertionError
    def mutate(self, intent): raise AssertionError
    def readback(self, intent): raise AssertionError
def decide(row): raise AssertionError
def build(argv): return Adapter(), decide
""", encoding="utf-8")
    output = tmp_path / "result.json"
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-paid:inventory-failure")

    assert paid.main([
        "--provider-adapter", str(provider), "--state-root", str(tmp_path / "state"),
        "--output", str(output),
    ]) == 1

    marker = paid._run_marker_path(tmp_path / "state", "fixture-paid:inventory-failure")
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "version": 1, "occurrence_id": "fixture-paid:inventory-failure",
        "status": "completed", "effect": 0,
    }


def test_cli_preserves_only_secret_free_provider_inventory_error_code(tmp_path: Path) -> None:
    provider = tmp_path / "provider.py"
    provider.write_text("""
class Adapter:
    def observe_active(self):
        error = RuntimeError("crowdworks_paid_browser_unavailable")
        error.paid_error_code = "crowdworks_paid_browser_unavailable"
        raise error
    def observe_one(self, work_id): raise AssertionError
    def context(self, work_id): raise AssertionError
    def mutate(self, intent): raise AssertionError
    def readback(self, intent): raise AssertionError
def decide(row): raise AssertionError
def build(argv): return Adapter(), decide
""", encoding="utf-8")
    output = tmp_path / "result.json"
    assert paid.main([
        "--provider-adapter", str(provider), "--state-root", str(tmp_path / "state"),
        "--output", str(output),
    ]) == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["error_detail"] == "crowdworks_paid_browser_unavailable"


def test_cli_omits_untrusted_snake_case_provider_inventory_detail(tmp_path: Path) -> None:
    provider = tmp_path / "provider.py"
    provider.write_text("""
class Adapter:
    def observe_active(self): raise RuntimeError("private_client_secret")
    def observe_one(self, work_id): raise AssertionError
    def context(self, work_id): raise AssertionError
    def mutate(self, intent): raise AssertionError
    def readback(self, intent): raise AssertionError
def decide(row): raise AssertionError
def build(argv): return Adapter(), decide
""", encoding="utf-8")
    output = tmp_path / "result.json"
    assert paid.main([
        "--provider-adapter", str(provider), "--state-root", str(tmp_path / "state"),
        "--output", str(output),
    ]) == 1
    assert "error_detail" not in json.loads(output.read_text(encoding="utf-8"))


def test_cli_persists_provider_inventory_wait_as_durable_pending(tmp_path: Path) -> None:
    provider = tmp_path / "provider.py"
    provider.write_text("""
class InventoryWait(RuntimeError):
    paid_wait_reason = "provider_authentication_required"
    paid_remaining_work = ["restore provider session and retry official inventory"]
class Adapter:
    def observe_active(self): raise InventoryWait()
    def observe_one(self, work_id): raise AssertionError
    def context(self, work_id): raise AssertionError
    def mutate(self, intent): raise AssertionError
    def readback(self, intent): raise AssertionError
def decide(row): raise AssertionError
def build(argv): return Adapter(), decide
""", encoding="utf-8")
    output = tmp_path / "result.json"
    assert paid.main([
        "--provider-adapter", str(provider), "--state-root", str(tmp_path / "state"),
        "--output", str(output),
    ]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "status": "pending", "observed": 0, "actionable": 0, "effect": 0,
        "readback": 0, "failed": 0, "pending": 1,
        "items": [{
            "work_id": "__provider_inventory__", "status": "pending",
            "reason": "provider_authentication_required",
            "remaining_work": ["restore provider session and retry official inventory"],
            "effect": 0, "readback": 0, "failed": 0,
        }],
    }


def test_no_effect_preserves_shared_lifecycle_classification(tmp_path: Path) -> None:
    adapter = Adapter([observation("done"), observation("buyer")])

    def classify(row: dict) -> dict:
        return {"action": "noop", "classification": (
            "completed" if row["work_id"] == "done" else "awaiting_buyer"
        )}

    result = paid.run_wake(adapter=adapter, decide=classify, state_root=tmp_path)
    assert [item["status"] for item in result["items"]] == ["completed", "awaiting_buyer"]
    assert result["observed"] == 2
    assert result["actionable"] == result["effect"] == result["failed"] == 0
    assert result["readback"] == 2
