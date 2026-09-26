import hashlib
import importlib.util
import json
from pathlib import Path
import sys


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


def events(tmp_path, run="run-1"):
    rows = [
        {"loop_id": OWNER, "run_id": run, "event_id": "s", "timestamp": START,
         "phase": "execute", "status": "running", "effect_status": "started"},
        {"loop_id": OWNER, "run_id": run, "event_id": "t", "timestamp": END,
         "phase": "report", "status": "fail", "effect_status": "unknown",
         "blocker": "entrypoint_exit_1"},
    ]
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def marker(tmp_path, items, occurrence=OCC):
    path = tmp_path / "reply/runs" / (hashlib.sha256(occurrence.encode()).hexdigest() + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "occurrence_id": occurrence,
                                "status": "effect_unknown", "items": items}))


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
    assert prove(module, tmp_path, {"b": conversation()}) == (None, "run_window_unavailable")


def test_killed_run_is_bounded_by_marker_write(tmp_path):
    import os
    module = load()
    events(tmp_path)
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    (tmp_path / "events.jsonl").write_text(lines[0] + "\n")  # start only
    marker(tmp_path, [FAILED])
    written = module._epoch("2026-09-20T03:10:00+00:00")
    os.utime(module._marker_path(tmp_path, OCC), (written, written))
    assert prove(module, tmp_path, {"b": conversation("2026年09月20日 11:57")})[1] == "ok"
    assert prove(module, tmp_path, {"b": conversation("2026年09月20日 12:09")}) == (
        None, "seller_message_in_window:b")


def test_form_fence_written_in_window_keeps_fence(tmp_path):
    module = load()
    events(tmp_path)
    marker(tmp_path, [FAILED])
    fence = tmp_path / "reply/external-actions/x.json"
    fence.parent.mkdir(parents=True)
    fence.write_text(json.dumps({"status": "prepared", "prepared_at": "2026-09-20T03:02:00Z"}))
    assert prove(module, tmp_path, {"b": conversation()}) == (None, "form_fence_in_window")
