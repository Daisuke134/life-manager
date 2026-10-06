import importlib.util
import json
from pathlib import Path
import threading
import pytest

import pytest


MODULE = Path(__file__).parents[1] / "scripts" / "reply_kernel.py"
SPEC = importlib.util.spec_from_file_location("marketplace_reply_kernel_test", MODULE)
reply_kernel = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(reply_kernel)

PLANNER_MODULE = Path(__file__).parents[1] / "scripts" / "reply_planner.py"
PLANNER_SPEC = importlib.util.spec_from_file_location(
    "marketplace_reply_planner_kernel_test", PLANNER_MODULE
)
planner_module = importlib.util.module_from_spec(PLANNER_SPEC)
assert PLANNER_SPEC and PLANNER_SPEC.loader
PLANNER_SPEC.loader.exec_module(planner_module)


def event(thread="thread-1", latest="buyer-1"):
    return {
        "provider": "test",
        "account_id": "seller-1",
        "thread_id": thread,
        "latest_event_id": latest,
        "observed_at": "2026-09-07T00:00:00Z",
    }


class Adapter:
    def __init__(self, rows=None):
        self.rows = rows or [event()]
        self.effects = []
        self.receipts = {}

    def observe_threads(self):
        return list(self.rows)

    def observe_one(self, thread_id):
        return next(row for row in self.rows if row["thread_id"] == thread_id)

    def context(self, thread_id):
        return {"conversation": [{"role": "buyer", "body": "Hello"}]}

    def mutate(self, intent):
        self.effects.append(intent)
        self.receipts[intent["effect_key"]] = {
            "verified": True,
            "provider_receipt_id": f"message-{len(self.effects)}",
            "observed_at": "2026-09-07T00:00:01Z",
        }

    def readback(self, intent):
        return self.receipts.get(intent["effect_key"], {"authoritative_absent": True})


def test_single_worker_hint_survives_observe_failure_and_clears_before_mutation(
        tmp_path, monkeypatch):
    hint = tmp_path / "entrypoint-result.json"
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))

    class BrowserUnavailable(Adapter):
        def observe_threads(self):
            raise RuntimeError("browser_connect_failed")

    with pytest.raises(RuntimeError, match="browser_connect_failed"):
        reply_kernel.run_wake(
            adapter=BrowserUnavailable(), decide=lambda _context: {},
            state_root=tmp_path / "failed", max_workers=1,
        )
    assert json.loads(hint.read_text()) == {"status": "pre_effect_failure", "effect": 0}

    class Ready(Adapter):
        def mutate(self, intent):
            assert not hint.exists()
            super().mutate(intent)

    result = reply_kernel.run_wake(
        adapter=Ready(),
        decide=lambda _context: {"action": "reply", "payload": {"body": "Thanks"}},
        state_root=tmp_path / "ready", max_workers=1,
    )
    assert result["effect"] == 1
    assert not hint.exists()


def test_classified_inventory_boundary_returns_structured_blocked_result(tmp_path):
    class ProviderInboxUnavailable(Adapter):
        def observe_threads(self):
            raise RuntimeError("collector_unhealthy:inbox_access_forbidden")

        def classify_observation_error(self, error):
            assert str(error) == "collector_unhealthy:inbox_access_forbidden"
            return {
                "reason": "provider_inbox_access_forbidden",
                "remaining_work": ["Retry the authenticated Coconala inbox read"],
            }

    result = reply_kernel.run_wake(
        adapter=ProviderInboxUnavailable(), decide=lambda _context: {}, state_root=tmp_path,
    )

    assert result == {
        "status": "blocked",
        "observed": 0,
        "actionable": 0,
        "effect": 0,
        "readback": 0,
        "failed": 0,
        "pending": 0,
        "blocker": "provider_inbox_access_forbidden",
        "error_detail": "collector_unhealthy:inbox_access_forbidden",
    }


def test_reply_effect_is_fenced_read_back_and_replay_zero(tmp_path):
    adapter = Adapter()

    def decide(_context):
        return {"action": "reply", "payload": {"body": "Thanks"}}

    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert first["effect"] == 1
    assert first["readback"] == 1
    assert first["failed"] == 0
    assert len(adapter.effects) == 1


def test_state_records_runtime_occurrence_and_run_marker(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-reply:run-1")
    result = reply_kernel.run_wake(
        adapter=Adapter(),
        decide=lambda _context: {"action": "accept_contract",
                                 "payload": {"condition_id": "condition-1"}},
        state_root=tmp_path,
    )
    assert result["effect"] == 1
    state = json.loads(next(tmp_path.glob("threads/*/state.json")).read_text())
    assert state["occurrence_id"] == "fixture-reply:run-1"
    marker = reply_kernel._run_marker_path(tmp_path, "fixture-reply:run-1")
    assert json.loads(marker.read_text())["occurrence_id"] == "fixture-reply:run-1"


def test_reconcile_preserves_original_occurrence_binding(monkeypatch, tmp_path):
    adapter = Adapter()
    decide = lambda _context: {"action": "accept_contract",
                               "payload": {"condition_id": "condition-1"}}
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-reply:run-a")
    assert reply_kernel.run_wake(adapter=adapter, decide=decide,
                                 state_root=tmp_path)["effect"] == 1
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-reply:run-b")
    assert reply_kernel.run_wake(adapter=adapter, decide=decide,
                                 state_root=tmp_path)["effect"] == 0
    state = json.loads(next(tmp_path.glob("threads/*/state.json")).read_text())
    assert state["occurrence_id"] == "fixture-reply:run-a"


def test_new_intent_after_authoritatively_absent_rebinds_to_current_wake(
        monkeypatch, tmp_path):
    adapter = Adapter()
    row = event()
    legacy = reply_kernel._intent(row, {
        "action": "accept_contract", "payload": {"condition_id": "old"}
    })
    path = reply_kernel._state_path(tmp_path, row)
    reply_kernel._write(path, {
        "version": 1, "inventory_event_id": row["latest_event_id"],
        "observation": row, "intent": legacy, "status": "reconcile_unknown",
    })
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-reply:run-b")
    result = reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda _context: {"action": "accept_contract",
                                 "payload": {"condition_id": "new"}},
        state_root=tmp_path,
    )
    assert result["effect"] == 1
    assert json.loads(path.read_text())["occurrence_id"] == "fixture-reply:run-b"

def test_contract_acceptance_uses_same_fence_readback_and_replay_zero(tmp_path):
    adapter = Adapter()
    decide = lambda _context: {
        "action": "accept_contract",
        "payload": {"condition_id": "condition-1", "amount": "12円"},
    }

    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    replay = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)

    assert first["effect"] == 1
    assert first["readback"] == 1
    assert adapter.effects[0]["action"] == "accept_contract"
    assert replay["effect"] == 0
    assert replay["items"][0]["reason"] == "replay_zero"
    assert len(adapter.effects) == 1


def test_terminated_readback_closes_uncertain_intent_without_model_or_context(tmp_path):
    row = event(thread="terminated-thread", latest="buyer-terminated")
    adapter = Adapter([row])
    intent = reply_kernel._intent(row, {
        "action": "accept_contract",
        "payload": {"condition_id": "condition-1", "amount": "12円"},
    })
    path = reply_kernel._state_path(tmp_path, row)
    reply_kernel._write(path, {
        "version": 1,
        "inventory_event_id": row["latest_event_id"],
        "observation": row,
        "intent": intent,
        "status": "reconcile_unknown",
    })

    class Terminated(Adapter):
        def context(self, _thread_id):
            raise AssertionError("terminated readback must not call model context")

        def readback(self, _intent):
            return {
                "verified": True,
                "provider_receipt_id": "contract:63570481:terminated",
                "termination_state": "terminated",
                "observed_at": "2026-10-01T12:00:00Z",
            }

    result = reply_kernel.run_wake(
        adapter=Terminated([row]),
        decide=lambda _context: (_ for _ in ()).throw(
            AssertionError("terminated readback must not call decide")
        ),
        state_root=tmp_path,
    )

    assert result["failed"] == 0
    assert result["effect"] == 0
    assert result["readback"] == 1
    assert result["items"][0]["status"] == "verified"
    saved = reply_kernel._load(path)
    assert saved["status"] == "verified"
    assert saved["receipt"]["provider_receipt_id"] == "contract:63570481:terminated"
    assert saved["receipt"]["termination_state"] == "terminated"


def test_partial_external_action_resumes_only_after_authoritative_readback(tmp_path, monkeypatch):
    hint = tmp_path / "entrypoint-result.json"
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))

    class Partial(Adapter):
        def __init__(self):
            super().__init__()
            self.stage = "absent"

        def mutate(self, intent):
            assert not hint.exists()
            self.effects.append(intent)
            self.stage = "partial" if self.stage == "absent" else "complete"

        def readback(self, _intent):
            if self.stage == "absent":
                return {"authoritative_absent": True}
            if self.stage == "partial":
                return {"resume_required": True}
            return {"verified": True, "provider_receipt_id": "external-1",
                    "observed_at": "2026-09-10T00:00:00Z"}

    adapter = Partial()
    decide = lambda _context: {
        "action": "external_action",
        "payload": {"kind": "schedule_meeting", "url": "https://example.com"},
    }
    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path,
                                  max_workers=1)
    replay = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path,
                                   max_workers=1)
    final = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path,
                                  max_workers=1)

    assert first["pending"] == 1
    assert first["effect"] == 1
    assert replay["failed"] == 0
    assert replay["readback"] == 1
    assert replay["items"][0]["reason"] == "resumed"
    assert final["effect"] == 0
    assert final["items"][0]["reason"] == "replay_zero"
    assert len(adapter.effects) == 2



def test_decision_version_reopens_old_no_effect_state_once(tmp_path):
    adapter = Adapter()
    reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda _context: {"action": "noop", "classification": "awaiting_buyer"},
        state_root=tmp_path,
    )
    adapter.rows[0]["decision_version"] = "official-actions-v1"

    result = reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda _context: {
            "action": "accept_contract", "payload": {"condition_id": "condition-1"}
        },
        state_root=tmp_path,
    )

    assert result["effect"] == 1
    assert len(adapter.effects) == 1


def test_removed_decision_version_does_not_reopen_ordinary_no_effect_state(tmp_path):
    adapter = Adapter([{**event(), "decision_version": "official-actions-v1"}])
    reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda _context: {"action": "noop", "classification": "awaiting_buyer"},
        state_root=tmp_path,
    )
    adapter.rows[0].pop("decision_version")
    decisions = []

    replay = reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda context: decisions.append(context),
        state_root=tmp_path,
    )

    assert replay["effect"] == 0
    assert replay["items"][0]["reason"] == "replay_zero"
    assert decisions == []


def test_contract_intent_reconciles_after_provider_event_advances(tmp_path):
    class AcceptedThenInterrupted(Adapter):
        def mutate(self, intent):
            super().mutate(intent)
            self.rows[0] = event(latest="contract-event-2")
            raise RuntimeError("connection_lost_after_acceptance")

    adapter = AcceptedThenInterrupted()
    decide = lambda _context: {
        "action": "accept_contract", "payload": {"condition_id": "condition-1"}
    }
    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    replay = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)

    assert first["failed"] == 1
    assert replay["effect"] == 0
    assert replay["readback"] == 1
    assert replay["items"][0]["reason"] == "replay_zero"
    assert len(adapter.effects) == 1


def test_authoritatively_absent_contract_replans_legacy_uncertain_intent(tmp_path):
    adapter = Adapter()
    row = event()
    legacy = reply_kernel._intent(row, {
        "action": "accept_contract",
        "payload": {"condition_id": "41883371", "terms_sha256": "a" * 64,
                    "title": "対象案件", "amount": "110円"},
    })
    path = reply_kernel._state_path(tmp_path, row)
    reply_kernel._write(path, {
        "version": 1, "inventory_event_id": row["latest_event_id"],
        "observation": row, "intent": legacy, "status": "reconcile_unknown",
    })
    enriched = {
        "action": "accept_contract",
        "payload": {**legacy["payload"], "client": "発注者", "worker": "Kaito"},
    }

    first = reply_kernel.run_wake(
        adapter=adapter, decide=lambda _context: enriched, state_root=tmp_path
    )
    replay = reply_kernel.run_wake(
        adapter=adapter, decide=lambda _context: enriched, state_root=tmp_path
    )

    assert first["effect"] == 1
    assert adapter.effects[0]["payload"] == enriched["payload"]
    assert replay["effect"] == 0
    assert replay["items"][0]["reason"] == "replay_zero"
    assert len(adapter.effects) == 1


def test_provider_source_gap_is_pending_without_model_or_effect(tmp_path):
    row = {**event(thread="source:gmail", latest="stale-1"),
           "pending_reason": "provider_source_stale"}
    adapter = Adapter([row])
    decisions = []

    result = reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda context: decisions.append(context),
        state_root=tmp_path,
    )

    assert result["pending"] == 1
    assert result["actionable"] == 1
    assert result["items"] == [{
        "thread_id": "source:gmail", "status": "pending",
        "reason": "provider_source_stale", "effect": 0, "readback": 0, "failed": 0,
    }]
    assert decisions == []
    assert adapter.effects == []

def test_verified_effect_notifies_once_and_replay_does_not_duplicate(tmp_path):
    adapter = Adapter()
    reports = []

    def notify(intent, receipt):
        reports.append((intent["effect_key"], receipt["provider_receipt_id"]))
        return {"delivery": "delivered", "provider_message_id": "tg-1"}

    arguments = dict(
        adapter=adapter,
        decide=lambda _context: {"action": "reply", "payload": {"body": "Thanks"}},
        state_root=tmp_path,
        notify=notify,
    )
    first = reply_kernel.run_wake(**arguments)
    replay = reply_kernel.run_wake(**arguments)

    assert first["items"][0]["notification"]["delivery"] == "delivered"
    assert replay["effect"] == 0
    assert reports == [(adapter.effects[0]["effect_key"], "message-1")]

def test_new_buyer_event_gets_a_distinct_reply(tmp_path):
    adapter = Adapter()
    bodies = iter(("first", "second"))
    decide = lambda _context: {"action": "reply", "payload": {"body": next(bodies)}}
    reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    adapter.rows[0] = event(latest="buyer-2")
    result = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert result["effect"] == 1
    assert len(adapter.effects) == 2


def test_private_identity_is_hidden_from_model_and_rejected_before_provider_effect(tmp_path):
    class PrivateContext(Adapter):
        def context(self, _thread_id):
            return {
                "title": "Question for Private Legal Name",
                "conversation": [{"role": "buyer", "body": "Hello private@example.com"}],
                "grounding": {
                    "prompt_facts": [{"id": "role", "claim": "Python developer"}],
                    "private_identity_values": ["Private Legal Name", "private@example.com"],
                    "provider_public_facts": {"display_name": "Kaito｜AI自動化"},
                },
            }

    adapter = PrivateContext()
    seen = []

    def decide(row):
        seen.append(row["context"])
        return {"action": "reply", "payload": {"body": "Private Legal Nameと申します"}}

    result = reply_kernel.run_wake(
        adapter=adapter, decide=decide, state_root=tmp_path,
    )

    assert "private_identity_values" not in seen[0]["grounding"]
    assert "Private Legal Name" not in seen[0]["title"]
    assert "private@example.com" not in seen[0]["conversation"][0]["body"]
    assert result["failed"] == 1
    assert result["items"][0]["error_detail"] == "reply_private_identity_leak"
    assert adapter.effects == []


def test_verified_provider_public_name_is_allowed(tmp_path):
    class PublicContext(Adapter):
        def context(self, _thread_id):
            return {
                "conversation": [{"role": "buyer", "body": "Hello"}],
                "grounding": {
                    "private_identity_values": ["Private Legal Name"],
                    "provider_public_facts": {"display_name": "Kaito｜AI自動化"},
                },
            }

    adapter = PublicContext()
    result = reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda _row: {
            "action": "reply", "payload": {"body": "Kaito｜AI自動化です"},
        },
        state_root=tmp_path,
    )

    assert result["failed"] == 0
    assert result["effect"] == 1


def test_no_effect_classification_is_replay_zero_until_source_event_changes(tmp_path):
    adapter = Adapter()
    decisions = []

    def decide(_context):
        decisions.append(True)
        return {"action": "noop", "classification": "no_reply"}

    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    replay = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    adapter.rows[0] = event(latest="buyer-2")
    changed = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)

    assert first["items"][0]["reason"] == "no_effect_required"
    assert replay["items"][0]["reason"] == "replay_zero"
    assert changed["items"][0]["reason"] == "no_effect_required"
    assert len(decisions) == 2


def test_no_effect_replay_uses_inventory_fingerprint_when_official_id_differs(tmp_path):
    class DifferentOfficialId(Adapter):
        def observe_one(self, thread_id):
            row = super().observe_one(thread_id)
            return {**row, "latest_event_id": f"official-{row['latest_event_id']}"}

    adapter = DifferentOfficialId()
    decisions = []

    def decide(_context):
        decisions.append(True)
        return {"action": "noop", "classification": "no_reply"}

    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    replay = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    adapter.rows[0] = event(latest="buyer-2")
    changed = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)

    assert first["items"][0]["reason"] == "no_effect_required"
    assert replay["items"][0]["reason"] == "replay_zero"
    assert changed["items"][0]["reason"] == "no_effect_required"
    assert len(decisions) == 2


def test_failure_backoff_uses_inventory_fingerprint_when_official_id_differs(tmp_path):
    class DifferentOfficialId(Adapter):
        def observe_one(self, thread_id):
            row = super().observe_one(thread_id)
            return {**row, "latest_event_id": f"official-{row['latest_event_id']}"}

    adapter = DifferentOfficialId()
    decisions = []

    def decide(_context):
        decisions.append(True)
        raise RuntimeError("temporary")

    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    replay = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)

    assert first["failed"] == 1
    assert replay["failed"] == 0
    assert replay["items"][0]["reason"] == "retry_backoff"
    assert len(decisions) == 1


def test_human_gate_is_durable_pending_and_does_not_block_another_thread(tmp_path):
    adapter = Adapter([event("human", "buyer-1"), event("ready", "buyer-2")])

    def decide(context):
        if context["thread_id"] == "human":
            return {
                "action": "human",
                "reason": "person_bound_interview",
                "remaining_work": ["Complete the official interview"],
            }
        return {"action": "reply", "payload": {"body": "Ready"}}

    result = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert result["pending"] == 1
    assert result["effect"] == 1
    assert result["failed"] == 0
    assert [effect["thread_id"] for effect in adapter.effects] == ["ready"]


def test_planner_missing_facts_waits_without_effect_or_human_notification(tmp_path):
    class MissingFacts(RuntimeError):
        remaining_work = ["本人の回答"]

    def compose(_context):
        raise MissingFacts()

    adapter = Adapter()
    notices = []
    planner = planner_module.ReplyPlanner(compose)
    result = reply_kernel.run_wake(
        adapter=adapter,
        decide=planner,
        state_root=tmp_path,
        max_workers=1,
        human_notify=lambda row, decision: notices.append((row, decision)),
    )

    assert result["pending"] == 1
    assert result["failed"] == 0
    assert result["effect"] == 0
    assert result["items"][0]["reason"] == "reply_facts_required"
    assert adapter.effects == []
    assert notices == []


def test_human_gate_notification_is_durable_deduplicated_and_keeps_scanning(tmp_path,
                                                                            monkeypatch):
    adapter = Adapter([event("human", "buyer-1"), event("ready", "buyer-2")])
    hint = tmp_path / "entrypoint-result.json"
    monkeypatch.setenv("LIFE_MANAGER_RESULT_HINT_PATH", str(hint))
    notices = []

    def decide(context):
        if context["thread_id"] == "human":
            return {
                "action": "human",
                "reason": "person_bound_interview",
                "remaining_work": ["Complete the official interview"],
                "handoff": {
                    "title": "Japanese evaluator",
                    "url": "https://work.mercor.com/jobs/list_1",
                    "deadline": "公式期限表示なし",
                },
            }
        return {"action": "reply", "payload": {"body": "Ready"}}

    def human_notify(row, decision):
        assert not hint.exists()
        notices.append((row["thread_id"], decision["handoff"]["url"]))
        return {"delivery": "delivered", "provider_message_id": "tg-1"}

    arguments = {
        "adapter": adapter,
        "decide": decide,
        "state_root": tmp_path,
        "human_notify": human_notify,
        "max_workers": 1,
    }
    first = reply_kernel.run_wake(**arguments)
    replay = reply_kernel.run_wake(**arguments)

    assert first["pending"] == replay["pending"] == 1
    assert first["effect"] == 1
    assert replay["effect"] == 0
    assert notices == [("human", "https://work.mercor.com/jobs/list_1")]
    state = reply_kernel._load(next(
        path for path in tmp_path.glob("threads/*/state.json")
        if reply_kernel._load(path).get("status") == "waiting_human"
    ))
    assert state["human_notification"]["provider_message_id"] == "tg-1"


def test_one_thread_failure_is_isolated(tmp_path):
    adapter = Adapter([event("bad", "buyer-1"), event("good", "buyer-2")])

    def decide(context):
        if context["thread_id"] == "bad":
            raise RuntimeError("model failed")
        return {"action": "estimate", "payload": {"body": "Estimate", "amount": 100}}

    result = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert result["failed"] == 1
    assert result["items"][0]["error_detail"] == "model failed"
    assert result["effect"] == 1
    assert result["items"][1]["status"] == "verified"

    replay = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert replay["items"][0]["reason"] == "retry_backoff"
    assert replay["items"][0]["failed"] == 0


def test_authoritative_provider_rejection_becomes_durable_external_wait(tmp_path):
    class Restricted(Adapter):
        def mutate(self, _intent):
            raise RuntimeError("submit_rejected_sending_unavailable")

        def classify_mutation_error(self, error):
            assert str(error) == "submit_rejected_sending_unavailable"
            return {
                "reason": "provider_sending_unavailable",
                "remaining_work": ["Wait for the provider message control to become available"],
            }

    result = reply_kernel.run_wake(
        adapter=Restricted(),
        decide=lambda _context: {"action": "reply", "payload": {"body": "Thanks"}},
        state_root=tmp_path,
    )

    assert result["failed"] == 0
    assert result["pending"] == 1
    assert result["effect"] == 0
    assert result["items"][0]["reason"] == "provider_sending_unavailable"


def test_duplicate_thread_inventory_is_rejected(tmp_path):
    adapter = Adapter([event(), event()])
    try:
        reply_kernel.run_wake(adapter=adapter, decide=lambda _: {}, state_root=tmp_path)
    except ValueError as error:
        assert str(error) == "reply_inventory_duplicate"
    else:
        raise AssertionError("duplicate inventory was accepted")


def test_single_worker_keeps_thread_affine_adapter_on_calling_thread(tmp_path):
    owner = threading.get_ident()

    class ThreadAffine(Adapter):
        def _same(self):
            if threading.get_ident() != owner:
                raise RuntimeError("wrong_thread")

        def observe_threads(self):
            self._same()
            return super().observe_threads()

        def observe_one(self, thread_id):
            self._same()
            return super().observe_one(thread_id)

        def context(self, thread_id):
            self._same()
            return super().context(thread_id)

    result = reply_kernel.run_wake(
        adapter=ThreadAffine(),
        decide=lambda _row: {"action": "noop", "classification": "no_reply"},
        state_root=tmp_path,
        max_workers=1,
    )
    assert result["failed"] == 0
    assert result["items"][0]["status"] == "no_reply"


def test_delivery_unknown_never_blindly_replays_same_intent(tmp_path):
    class Unknown(Adapter):
        def mutate(self, intent):
            self.effects.append(intent)

        def readback(self, _intent):
            return {"authoritative_absent": True}

    adapter = Unknown()
    decide = lambda _row: {"action": "reply", "payload": {"body": "one"}}
    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert first["effect"] == 1
    assert first["items"][0]["reason"] == "reconcile_unknown"
    second = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert second["effect"] == 0
    assert second["items"][0]["reason"] == "reconcile_unknown"
    assert len(adapter.effects) == 1


@pytest.mark.parametrize("scenario", ["same_reply", "different_estimate", "noop"])
def test_reconcile_unknown_reply_or_estimate_fences_new_event_until_old_readback(
        tmp_path, scenario):
    old_row = event(latest="event-A")
    new_row = event(latest="event-B")
    if scenario == "same_reply":
        old_action, old_payload = "reply", {"body": "same"}
        decision = {"action": "reply", "payload": {"body": "same"}}
        readback = {"authoritative_absent": True}
    elif scenario == "different_estimate":
        old_action, old_payload = "estimate", {"quote": "old"}
        decision = {"action": "estimate", "payload": {"quote": "new"}}
        readback = {"authoritative_absent": False}
    else:
        old_action, old_payload = "reply", {"body": "old"}
        decision = {"action": "noop", "classification": "no_reply"}
        readback = {"authoritative_absent": True}
    old_intent = reply_kernel._intent(old_row, {
        "action": old_action, "payload": old_payload,
    })
    path = reply_kernel._state_path(tmp_path, old_row)
    reply_kernel._write(path, {
        "version": 1,
        "inventory_event_id": "event-A",
        "observation": old_row,
        "intent": old_intent,
        "status": "reconcile_unknown",
        "occurrence_id": "fixture-reply:run-A",
    })
    before = path.read_bytes()

    class UnknownOldIntent(Adapter):
        def __init__(self):
            super().__init__([new_row])
            self.readbacks = []
            self.context_calls = 0

        def context(self, thread_id):
            self.context_calls += 1
            return super().context(thread_id)

        def readback(self, intent):
            self.readbacks.append(dict(intent))
            return dict(readback)

    adapter = UnknownOldIntent()
    decisions = []

    def decide(context):
        decisions.append(context)
        return decision

    result = reply_kernel.run_wake(
        adapter=adapter, decide=decide, state_root=tmp_path,
    )

    assert result["items"][0]["reason"] == "reconcile_unknown"
    assert result["items"][0]["status"] == "pending"
    assert result["effect"] == 0
    assert adapter.readbacks == [old_intent]
    assert adapter.context_calls == 0
    assert decisions == []
    assert adapter.effects == []
    assert path.read_bytes() == before


def test_verified_old_unknown_receipt_keeps_event_binding_then_processes_new_event(
        tmp_path, monkeypatch):
    old_row = event(latest="event-A")
    new_row = event(latest="event-B")
    old_intent = reply_kernel._intent(old_row, {
        "action": "reply", "payload": {"body": "same semantic content"},
    })
    path = reply_kernel._state_path(tmp_path, old_row)
    reply_kernel._write(path, {
        "version": 1,
        "inventory_event_id": "event-A",
        "observation": old_row,
        "intent": old_intent,
        "status": "reconcile_unknown",
        "occurrence_id": "fixture-reply:run-A",
    })
    monkeypatch.delenv("LIFE_MANAGER_RESULT_HINT_PATH", raising=False)
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-reply:run-B")

    class OldReceiptThenNewEffect(Adapter):
        def __init__(self):
            super().__init__([new_row])
            self.readbacks = []

        def readback(self, intent):
            self.readbacks.append(dict(intent))
            if intent["latest_event_id"] == "event-A":
                return {
                    "verified": True,
                    "provider_receipt_id": "provider-receipt-A",
                    "observed_at": "2026-10-05T00:00:01Z",
                }
            return super().readback(intent)

    adapter = OldReceiptThenNewEffect()
    decisions = []
    notifications = []

    def decide(context):
        decisions.append(context)
        return {"action": "reply", "payload": {"body": "same semantic content"}}

    def notify(intent, receipt):
        notifications.append((intent["latest_event_id"], receipt["provider_receipt_id"]))
        return {"delivery": "delivered"}

    first = reply_kernel.run_wake(
        adapter=adapter, decide=decide, state_root=tmp_path, notify=notify,
    )
    saved_old = reply_kernel._load(path)
    assert first["items"][0]["reason"] == "replay_zero"
    assert first["effect"] == 0
    assert decisions == []
    assert adapter.effects == []
    assert saved_old["inventory_event_id"] == "event-A"
    assert saved_old["observation"]["latest_event_id"] == "event-A"
    assert saved_old["intent"]["latest_event_id"] == "event-A"
    assert saved_old["occurrence_id"] == "fixture-reply:run-A"
    assert saved_old["receipt"]["provider_receipt_id"] == "provider-receipt-A"
    assert notifications == [("event-A", "provider-receipt-A")]

    second = reply_kernel.run_wake(
        adapter=adapter, decide=decide, state_root=tmp_path, notify=notify,
    )
    saved_new = reply_kernel._load(path)
    assert second["items"][0]["reason"] == "submitted"
    assert second["effect"] == 1
    assert len(adapter.effects) == 1
    new_intent = adapter.effects[0]
    assert new_intent["latest_event_id"] == "event-B"
    assert new_intent["content_sha256"] == old_intent["content_sha256"]
    assert new_intent["effect_key"] != old_intent["effect_key"]
    assert saved_new["inventory_event_id"] == "event-B"
    assert saved_new["observation"]["latest_event_id"] == "event-B"
    assert saved_new["occurrence_id"] == "fixture-reply:run-B"
    assert notifications == [
        ("event-A", "provider-receipt-A"),
        ("event-B", "message-1"),
    ]

    replay = reply_kernel.run_wake(
        adapter=adapter, decide=decide, state_root=tmp_path, notify=notify,
    )
    assert replay["items"][0]["reason"] == "replay_zero"
    assert replay["effect"] == 0
    assert len(adapter.effects) == 1
    assert len(decisions) == 1
    assert len(notifications) == 2


def test_readback_exception_after_intent_preserves_reconcile_fence(tmp_path):
    class ReadbackBreaksAfterEffect(Adapter):
        def __init__(self):
            super().__init__()
            self.broken = True

        def readback(self, intent):
            if self.effects and self.broken:
                raise RuntimeError("provider_dom_changed")
            return super().readback(intent)

    adapter = ReadbackBreaksAfterEffect()
    decide = lambda _row: {"action": "reply", "payload": {"body": "one"}}
    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert first["failed"] == 1
    assert len(adapter.effects) == 1
    state_path = next(tmp_path.glob("threads/*/state.json"))
    state = reply_kernel._load(state_path)
    assert state["status"] == "reconcile_unknown"
    assert state["intent"]["payload"]["body"] == "one"

    adapter.broken = False
    replay = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert replay["failed"] == 0
    assert replay["effect"] == 0
    assert replay["items"][0]["reason"] == "replay_zero"
    assert len(adapter.effects) == 1


@pytest.mark.parametrize(("failure_phase", "expected_phase"), [
    ("observe_after_intent", "observe_after_intent"),
    ("readback_before_mutate", "readback_before_mutate"),
    ("mutate", "mutate"),
    ("readback_after_mutate", "readback_after_mutate"),
])
def test_intent_boundary_errors_persist_safe_phase_provenance(
    tmp_path, monkeypatch, failure_phase, expected_phase,
):
    class BoundaryFails(Adapter):
        def __init__(self):
            row = event()
            row.update({"provider": "coconala", "account_id": "default"})
            super().__init__([row])
            self.observe_count = 0
            self.readback_count = 0

        def observe_one(self, thread_id):
            self.observe_count += 1
            if failure_phase == "observe_after_intent" and self.observe_count == 2:
                raise RuntimeError(
                    "PRIVATE_BODY_SENTINEL https://private.invalid/thread/private-thread"
                )
            return super().observe_one(thread_id)

        def readback(self, intent):
            self.readback_count += 1
            if failure_phase == "readback_before_mutate" and self.readback_count == 1:
                raise RuntimeError("PRIVATE_READBACK_SENTINEL")
            if failure_phase == "readback_after_mutate" and self.effects:
                raise RuntimeError("PRIVATE_POST_READBACK_SENTINEL")
            return super().readback(intent)

        def mutate(self, intent):
            if failure_phase == "mutate":
                raise RuntimeError("private_body_secret_42")
            return super().mutate(intent)

    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", "fixture-run-current")
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-occurrence-current")
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", "d" * 40)
    monkeypatch.delenv("LIFE_MANAGER_RESULT_HINT_PATH", raising=False)
    adapter = BoundaryFails()

    result = reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda _context: {
            "action": "reply", "payload": {"body": "PRIVATE_INTENT_BODY"},
        },
        state_root=tmp_path,
        max_workers=1,
    )

    assert result["failed"] == 1
    state_path = next(tmp_path.glob("threads/*/state.json"))
    state = reply_kernel._load(state_path)
    diagnostic = state["send_diagnostic"]
    assert state["status"] == "reconcile_unknown"
    assert diagnostic["kernel_phase"] == expected_phase
    assert diagnostic["effect_key"] == state["intent"]["effect_key"]
    assert diagnostic["effect_status"] == "unknown"
    assert diagnostic["current_wake_id"] == "fixture-run-current"
    assert diagnostic["current_claimed_occurrence_id"] == "fixture-occurrence-current"
    assert diagnostic["stored_intent_occurrence_id"] == "fixture-occurrence-current"
    assert diagnostic["release_sha"] == "d" * 40
    assert "PRIVATE_" not in json.dumps(diagnostic)
    assert "https://private.invalid" not in json.dumps(diagnostic)
    assert "private-thread" not in json.dumps(diagnostic)
    assert "PRIVATE_" not in state["last_error_detail"]
    assert len(adapter.effects) == (1 if failure_phase == "readback_after_mutate" else 0)


def test_prior_unknown_observation_error_is_bound_to_old_intent_without_mutating(tmp_path, monkeypatch):
    row = event(thread="77100999", latest="buyer-event-old")
    row.update({"provider": "coconala", "account_id": "default"})
    intent = reply_kernel._intent(row, {
        "action": "reply", "payload": {"body": "old intent body"},
    })
    state_path = reply_kernel._state_path(tmp_path, row)
    reply_kernel._write(state_path, {
        "version": 1, "inventory_event_id": row["latest_event_id"],
        "observation": row, "intent": intent,
        "occurrence_id": "fixture-admission-old", "status": "reconcile_unknown",
    })

    class PriorUnknownUnavailable(Adapter):
        def observe_one(self, _thread_id):
            raise RuntimeError("collector_unhealthy:unexpected_title")

        def readback(self, _intent):
            raise AssertionError("unreadable old unknown must not advance to readback")

        def context(self, _thread_id):
            raise AssertionError("old unknown must not call the decision callback")

        def classify_observation_error(self, error):
            if str(error) == "collector_unhealthy:unexpected_title":
                return {"reason": "provider_inbox_observation_unavailable"}
            return None

    monkeypatch.setenv("LIFE_MANAGER_RUN_ID", "fixture-run-new")
    monkeypatch.setenv("LIFE_MANAGER_OCCURRENCE_ID", "fixture-occurrence-new")
    monkeypatch.setenv("LIFE_MANAGER_RELEASE_SHA", "e" * 40)
    monkeypatch.delenv("LIFE_MANAGER_RESULT_HINT_PATH", raising=False)
    adapter = PriorUnknownUnavailable([row])

    result = reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda _context: (_ for _ in ()).throw(
            AssertionError("old unknown must not be reconsidered")
        ),
        state_root=tmp_path,
        max_workers=1,
    )

    saved = reply_kernel._load(state_path)
    diagnostic = saved["send_diagnostic"]
    assert saved["status"] == "reconcile_unknown"
    assert diagnostic["kernel_phase"] == "observe_prior_intent"
    assert diagnostic["effect_key"] == intent["effect_key"]
    assert diagnostic["effect_status"] == "unknown"
    assert diagnostic["stored_intent_occurrence_id"] == "fixture-admission-old"
    assert diagnostic["current_claimed_occurrence_id"] == "fixture-occurrence-new"
    assert diagnostic["current_wake_id"] == "fixture-run-new"
    assert diagnostic["error_code"] == "collector_unhealthy:unexpected_title"
    assert adapter.effects == []
    assert result["items"][0]["reason"] == "provider_inbox_observation_unavailable"


def test_provenance_write_failure_keeps_existing_intent_fence_and_raises(tmp_path, monkeypatch):
    class ReadbackBreaksAfterEffect(Adapter):
        def __init__(self):
            rows = []
            for thread_id in ("thread-A", "thread-B"):
                row = event(thread=thread_id, latest=f"buyer-{thread_id}")
                row.update({"provider": "coconala", "account_id": "default"})
                rows.append(row)
            super().__init__(rows)

        def readback(self, intent):
            if (intent["thread_id"] == "thread-A" and any(
                item["effect_key"] == intent["effect_key"] for item in self.effects
            )):
                raise RuntimeError("PRIVATE_AFTER_EFFECT_SENTINEL")
            return super().readback(intent)

    adapter = ReadbackBreaksAfterEffect()
    original_write = reply_kernel._write

    def fail_send_diagnostic(path, value):
        if "send_diagnostic" in value:
            raise OSError("diagnostic_storage_failed")
        return original_write(path, value)

    monkeypatch.setattr(reply_kernel, "_write", fail_send_diagnostic)
    with pytest.raises(OSError, match="diagnostic_storage_failed"):
        reply_kernel.run_wake(
            adapter=adapter,
            decide=lambda _context: {
                "action": "reply", "payload": {"body": "PRIVATE_INTENT_BODY"},
            },
            state_root=tmp_path,
            max_workers=2,
        )

    assert len(adapter.effects) == 2
    states = {
        state["intent"]["thread_id"]: state
        for state in (reply_kernel._load(path) for path in tmp_path.glob("threads/*/state.json"))
    }
    assert states["thread-A"]["status"] == "intent_persisted"
    assert states["thread-A"]["intent"]["effect_key"] in {
        item["effect_key"] for item in adapter.effects
    }
    assert states["thread-B"]["status"] == "verified"


def test_classified_observation_error_before_intent_is_pending_with_backoff(tmp_path):
    class TemporarilyUnreadable(Adapter):
        def observe_one(self, _thread_id):
            raise RuntimeError("navigation_timeout")

        def classify_observation_error(self, error):
            if str(error) == "navigation_timeout":
                return {"reason": "provider_readback_temporarily_unavailable"}
            return None

    result = reply_kernel.run_wake(
        adapter=TemporarilyUnreadable(),
        decide=lambda _row: {"action": "noop", "classification": "no_reply"},
        state_root=tmp_path,
    )

    assert result["failed"] == 0
    assert result["pending"] == 1
    assert result["items"][0]["reason"] == "provider_readback_temporarily_unavailable"
    state = reply_kernel._load(next(tmp_path.glob("threads/*/state.json")))
    assert state["status"] == "retry_wait"
    assert state["retry_count"] == 1


def test_classified_readback_error_after_effect_stays_pending_and_never_replays(tmp_path):
    class TemporarilyUnreadableAfterEffect(Adapter):
        def __init__(self):
            super().__init__()
            self.broken = True

        def readback(self, intent):
            if self.effects and self.broken:
                raise RuntimeError("navigation_timeout")
            return super().readback(intent)

        def classify_observation_error(self, error):
            if str(error) == "navigation_timeout":
                return {"reason": "provider_readback_temporarily_unavailable"}
            return None

    adapter = TemporarilyUnreadableAfterEffect()
    decide = lambda _row: {"action": "reply", "payload": {"body": "one"}}
    first = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)

    assert first["failed"] == 0
    assert first["pending"] == 1
    assert first["items"][0]["reason"] == "provider_readback_temporarily_unavailable"
    assert len(adapter.effects) == 1
    state_path = next(tmp_path.glob("threads/*/state.json"))
    assert reply_kernel._load(state_path)["status"] == "reconcile_unknown"

    adapter.broken = False
    replay = reply_kernel.run_wake(adapter=adapter, decide=decide, state_root=tmp_path)
    assert replay["failed"] == 0
    assert replay["effect"] == 0
    assert replay["items"][0]["reason"] == "replay_zero"
    assert len(adapter.effects) == 1


def test_chat_id_reads_declared_provider_config_without_repo_literal(tmp_path):
    config = tmp_path / "telegram.env"
    config.write_text("CROWDWORKS_REPORT_CHAT=operator-chat\n", encoding="utf-8")
    assert reply_kernel._chat_id("", config) == "operator-chat"
    assert reply_kernel._chat_id("explicit", config) == "explicit"


def test_pre_effect_readback_must_prove_authoritative_absence(tmp_path):
    class UnknownBeforeEffect(Adapter):
        def readback(self, _intent):
            return {"authoritative_absent": False}

    adapter = UnknownBeforeEffect()
    result = reply_kernel.run_wake(
        adapter=adapter,
        decide=lambda _row: {"action": "reply", "payload": {"body": "one"}},
        state_root=tmp_path,
    )
    assert result["effect"] == 0
    assert result["pending"] == 1
    assert result["items"][0]["reason"] == "pre_effect_reconcile_unknown"
    assert adapter.effects == []
