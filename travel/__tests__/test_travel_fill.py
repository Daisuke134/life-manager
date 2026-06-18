"""TDD (RED first) for the search→ask travel fixes.
Pure logic only — no network. Verifies: never guess a fixed travel time; never silently skip
an unknown location — instead enqueue an ASK for the user.
Run: python3 -m pytest skills/life/travel/__tests__/test_travel_fill.py  (or python3 this file)
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import travel_fill as tf  # noqa: E402


def test_plan_action_unknown_location_asks():
    # curr location could not be resolved → must ASK, never silently skip
    assert tf.plan_action(kind="unknown", travel_min=None) == ("ask", "unknown_location")


def test_plan_action_no_route_asks_not_guess():
    # both addresses known but Directions returned nothing → ASK, never guess 45
    assert tf.plan_action(kind="explicit", travel_min=None) == ("ask", "no_route")


def test_plan_action_known_route_inserts():
    assert tf.plan_action(kind="explicit", travel_min=22) == ("insert", 22)
    assert tf.plan_action(kind="geocoded", travel_min=8) == ("insert", 8)


def test_enqueue_ask_writes_jsonl_row():
    with tempfile.TemporaryDirectory() as d:
        q = Path(d) / "life-ask-queue.jsonl"
        ev = {"id": "evt123", "summary": "仕事", "start": None}
        tf.enqueue_ask(ev, "unknown_location", queue_path=q)
        rows = [json.loads(l) for l in q.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        r = rows[0]
        assert r["eventId"] == "evt123"
        assert r["reason"] == "unknown_location"
        assert r["summary"] == "仕事"
        assert "ts" in r


def test_enqueue_ask_dedupes_same_event_reason():
    with tempfile.TemporaryDirectory() as d:
        q = Path(d) / "life-ask-queue.jsonl"
        ev = {"id": "evt123", "summary": "仕事"}
        tf.enqueue_ask(ev, "unknown_location", queue_path=q)
        tf.enqueue_ask(ev, "unknown_location", queue_path=q)  # same → no dup
        rows = [l for l in q.read_text().splitlines() if l.strip()]
        assert len(rows) == 1


def test_pair_decision_unknown_prev_asks_PREV_not_curr():
    # the unknown one is PREV → must ask about prev, not curr (the wrong-event bug)
    assert tf.pair_decision(None, "unknown", "渋谷", "explicit") == ("ask_prev", "unknown_location")


def test_pair_decision_unknown_curr_asks_curr():
    assert tf.pair_decision("自宅", "explicit", None, "unknown") == ("ask_curr", "unknown_location")


def test_pair_decision_both_known_ok():
    assert tf.pair_decision("自宅", "explicit", "渋谷", "geocoded") == ("ok", None)


def test_enqueue_ask_tolerates_corrupt_line():
    with tempfile.TemporaryDirectory() as d:
        q = Path(d) / "life-ask-queue.jsonl"
        q.write_text('{"eventId":"a"  CORRUPT half line\n')  # a crashed half-write
        ev = {"id": "b", "summary": "x"}
        tf.enqueue_ask(ev, "no_route", queue_path=q)  # must not raise on the corrupt line
        rows = [l for l in q.read_text().splitlines() if l.strip()]
        assert any('"eventId": "b"' in l for l in rows)


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
