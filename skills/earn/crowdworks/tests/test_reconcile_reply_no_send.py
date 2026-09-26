import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime


ROOT = Path(__file__).resolve().parents[4]
PATH = ROOT / "skills/earn/crowdworks/scripts/reconcile_reply_no_send.py"
OWNER = "crowdworks-revenue-reply"
OCC = f"{OWNER}:run-1"
# Run window 2026-09-20T03:00:00Z .. 03:04:00Z == 12:00..12:04 JST.
START, END = "2026-09-20T03:00:00+00:00", "2026-09-20T03:04:00+00:00"


def load():
    spec = importlib.util.spec_from_file_location("crowdworks_reconcile_reply_no_send_test", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def events(tmp_path, run="run-1", executor="exec-9"):
    """``run`` queued the occurrence; ``executor`` later claimed and ran it."""
    rows = [
        {"loop_id": OWNER, "run_id": run, "event_id": "q", "timestamp": "2026-09-19T00:00:00+00:00",
         "phase": "report", "status": "blocked", "effect_status": "unknown",
         "blocker": "host_admission_deferred:resource_capacity_busy",
         "evidence_refs": [f"lm-loop://{OWNER}/{run}/summary.json"]},
        {"loop_id": OWNER, "run_id": executor, "event_id": "s", "timestamp": START,
         "phase": "execute", "status": "running", "effect_status": "started"},
        {"loop_id": OWNER, "run_id": executor, "event_id": "t", "timestamp": END,
         "phase": "report", "status": "fail", "effect_status": "unknown",
         "blocker": "entrypoint_exit_1",
         "evidence_refs": [f"lm-loop://{OWNER}/{executor}/summary.json",
                           f"lm-occurrence://{OWNER}/{run}/claim"]},
    ]
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def marker(tmp_path, items, occurrence=OCC, written="2026-09-20T03:03:00+00:00"):
    import os
    path = tmp_path / "reply/runs" / (hashlib.sha256(occurrence.encode()).hexdigest() + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "occurrence_id": occurrence,
                                "status": "effect_unknown", "items": items}))
    stamp = datetime.fromisoformat(written).timestamp()
    os.utime(path, (stamp, stamp))


SAFE = {"thread_id": "a", "status": "no_reply", "reason": "replay_zero",
        "effect": 0, "readback": 1, "failed": 0}
FAILED = {"thread_id": "b", "status": "failed", "reason": "RuntimeError",
          "effect": 0, "readback": 0, "failed": 1}


def conversation(*seller_minutes):
    rows = [{"role": "buyer", "sent_at": "2026年09月20日 11:00"}]
    return rows + [{"role": "seller", "sent_at": m} for m in seller_minutes]


def prove(module, tmp_path, conversations):
    return module.evaluate(tmp_path, [OCC], lambda tid: conversations[tid])[OCC]


def test_failed_thread_without_seller_message_in_window_is_no_send(tmp_path):
    module = load()
    events(tmp_path)
    marker(tmp_path, [SAFE, FAILED])
    proof, reason = prove(module, tmp_path, {"b": conversation("2026年09月20日 11:57")})
    assert reason == "ok"
    assert proof["proof_type"] == "pre_effect" and proof["verified"] is True
    assert proof["occurrence_id"] == OCC and proof["risky_threads"] == ["b"]
    assert proof["evidence_ref"].startswith(f"lm-crowdworks-reply-readback://{OWNER}/run-1/")


def test_seller_message_inside_window_keeps_fence(tmp_path):
    module = load()
    events(tmp_path)
    marker(tmp_path, [SAFE, FAILED])
    # 11:59 JST may be a send at 11:59:59, inside the 60s clock-skew slack.
    for minute in ("2026年09月20日 12:02", "2026年09月20日 11:59", "2026年09月20日 12:05"):
        assert prove(module, tmp_path, {"b": conversation(minute)}) == (None, "seller_message_in_window:b")


def test_unreadable_conversation_keeps_fence(tmp_path):
    module = load()
    events(tmp_path)
    marker(tmp_path, [FAILED])
    assert prove(module, tmp_path, {"b": None}) == (None, "official_conversation_unavailable:b")


def test_effect_marked_or_missing_marker_keeps_fence(tmp_path):
    module = load()
    events(tmp_path)
    assert prove(module, tmp_path, {}) == (None, "run_marker_unavailable")
    marker(tmp_path, [{**SAFE, "effect": 1}])
    assert prove(module, tmp_path, {}) == (None, "effect_marked:a")


def test_missing_window_keeps_fence(tmp_path):
    module = load()
    marker(tmp_path, [FAILED])
    assert prove(module, tmp_path, {"b": conversation()}) == (None, "claim_run_unavailable")


def test_queueing_run_is_not_the_executing_run(tmp_path):
    module = load()
    events(tmp_path)
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    (tmp_path / "events.jsonl").write_text("\n".join(lines[:2]) + "\n")  # executor killed
    marker(tmp_path, [FAILED])
    assert prove(module, tmp_path, {"b": conversation()}) == (None, "claim_run_unavailable")


def test_marker_written_outside_claim_run_keeps_fence(tmp_path):
    module = load()
    events(tmp_path)
    marker(tmp_path, [FAILED], written="2026-09-20T05:00:00+00:00")
    assert prove(module, tmp_path, {"b": conversation()}) == (None, "marker_outside_claim_run")


class FakeLocator:
    def __init__(self, text):
        self.text = text

    def count(self):
        return 1 if self.text is not None else 0

    def inner_text(self):
        return self.text


class FakePage:
    def __init__(self, progress=None):
        self.progress = progress

    def locator(self, selector):
        assert selector == "div.progress_detail"
        return FakeLocator(self.progress)


def test_contract_acceptance_trace_keeps_fence(tmp_path):
    module = load()
    proposed = {"proposal_status": "proposed"}
    assert module.contract_blocker(FakePage(), proposed) is None
    assert module.contract_blocker(FakePage(), {"proposal_status": "contracted"}) == "contract_accepted"
    assert module.contract_blocker(FakePage(), None) == "official_thread_unavailable"
    awaiting = FakePage("まだクライアントが契約に同意していません。クライアントが契約に同意すると契約成立")
    assert module.contract_blocker(awaiting, proposed) == "contract_acceptance_awaiting_client"
    events(tmp_path)
    marker(tmp_path, [FAILED])
    assert prove(module, tmp_path, {"b": "contract_acceptance_awaiting_client"}) == (
        None, "contract_acceptance_awaiting_client:b")


def test_accept_contract_intent_threads_are_found(tmp_path):
    module = load()
    for name, action in (("x", "accept_contract"), ("y", "reply")):
        path = tmp_path / "reply/threads" / name / "state.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"version": 1, "intent": {"action": action, "thread_id": name}}))
    assert module.accept_intent_threads(tmp_path) == {"x"}
