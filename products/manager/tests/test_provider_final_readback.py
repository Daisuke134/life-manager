"""Contracts for final text and provider Turn states in OpenAI 3.24.0 shapes."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from manager_core.ampersand_api import (
    SessionFailure, read_followup_turn, read_initial_turn,
    read_saved_assistant_items,
)
from manager_core.provider_budget import cancel_and_reconcile
from manager_core.provider_sessions import SessionJournal


def turn(ident="turn_abcdefgh", status="completed"):
    return SimpleNamespace(id=ident, status=status,
                           usage=SimpleNamespace(input_tokens=2, output_tokens=3))


def message(ident, text, *, turn_id="turn_abcdefgh", role="assistant",
            phase="final_answer", status="completed", kind="output_text"):
    row = dict(id=ident, type="message", turn_id=turn_id, role=role,
               phase=phase, status=status,
               content=[dict(type=kind, text=text)])
    return SimpleNamespace(**row)


class FakeStream:
    def __init__(self, events):
        self.events = events

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def __iter__(self): return iter(self.events)


def followup_client(items, *, output_event="misleading SSE text", turns=None,
                    advance_after_items=None):
    state = {"item_reads": 0, "posts": 0}
    rows = list(items)
    latest = turns or [turn()]

    def list_turns(*args, **kwargs):
        if advance_after_items is not None and state["item_reads"]:
            return SimpleNamespace(data=[advance_after_items])
        return SimpleNamespace(data=[latest[0]])

    def list_items(session_id, **kwargs):
        state["item_reads"] += 1
        return SimpleNamespace(data=rows, has_more=False)

    def create(*args, **kwargs): state["posts"] += 1
    sessions = SimpleNamespace(
        events=SimpleNamespace(
            stream=lambda sid: FakeStream([
                SimpleNamespace(type="agent.session.turn.output_text.done",
                               text=output_event),
                SimpleNamespace(type="agent.session.turn.completed",
                               turn_id="turn_abcdefgh")]),
            create=create),
        turns=SimpleNamespace(
            list=list_turns,
            retrieve=lambda tid, *, session_id: latest[0]),
        items=SimpleNamespace(list=list_items))
    return SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions))), state


class FinalReadbackContracts(unittest.TestCase):
    def test_saved_text_joins_all_final_messages_and_blocks_excluding_other_content(self):
        items = [
            message("item_00000001", "first", phase="commentary"),
            message("item_00000002", "A", phase="final_answer"),
            message("item_00000003", "foreign", turn_id="turn_other"),
            message("item_00000004", "user", role="user"),
            message("item_00000005", "B", phase=None),
            SimpleNamespace(id="item_00000006", type="message", turn_id="turn_abcdefgh",
                            role="assistant", phase="final_answer", status="completed",
                            content=[{"type":"output_text","text":"C"},
                                     {"type":"output_text","text":"D"}]),
        ]
        client, _ = followup_client(items, output_event="SSE-last-part-only")
        result = read_followup_turn(client, "sess_abcdefgh", "prompt", key="evt-0001",
                                    allow_silent_completion=False)
        self.assertEqual(result.output_text, "ABCD")
        self.assertEqual(result.turn_id, "turn_abcdefgh")

    def test_saved_text_wins_when_sse_contains_no_text_and_empty_requires_opt_in(self):
        client, _ = followup_client([message("item_00000001", "saved")], output_event=None)
        self.assertEqual(read_followup_turn(client, "sess_abcdefgh", "p", key="evt-0002").output_text,
                         "saved")
        empty, _ = followup_client([], output_event=None)
        with self.assertRaises(SessionFailure):
            read_followup_turn(empty, "sess_abcdefgh", "p", key="evt-0003")
        silent, _ = followup_client([], output_event=None)
        evidence = read_followup_turn(silent, "sess_abcdefgh", "p", key="evt-0004",
                                      allow_silent_completion=True)
        self.assertEqual((evidence.output_text, evidence.status), ("", "SILENT_COMPLETED"))

    def test_incomplete_malformed_or_ambiguous_saved_items_never_become_silence(self):
        cases = [
            lambda: SimpleNamespace(data=[message("item_00000001", "partial")], has_more=True),
            lambda: SimpleNamespace(data=[], has_more=None),
            lambda: SimpleNamespace(data=[message("item_00000001", "x", status="incomplete")], has_more=False),
            lambda: SimpleNamespace(data=[SimpleNamespace(id="item_00000001", type="message",
                turn_id="turn_abcdefgh", role="assistant", phase="new_phase", status="completed",
                content=[{"type":"output_text","text":"x"}])], has_more=False),
            lambda: SimpleNamespace(data=[SimpleNamespace(id="item_00000001", type="message",
                turn_id="turn_abcdefgh", role="assistant", phase="final_answer",
                content=[{"type":"output_text","text":"x"}])], has_more=False),
            lambda: SimpleNamespace(data=[SimpleNamespace(id="item_00000001", type="message",
                turn_id="turn_abcdefgh", role="assistant", phase="final_answer", status="completed",
                content=[{"type":"output_text","text":3}])], has_more=False),
        ]
        for index, page_factory in enumerate(cases):
            with self.subTest(index=index):
                client, _ = followup_client([])
                sessions = client.beta.agents.sessions
                sessions.items.list = lambda sid, **kw: page_factory()
                with self.assertRaises(SessionFailure):
                    read_followup_turn(client, "sess_abcdefgh", "p", key=f"evt-{index:04d}",
                                       allow_silent_completion=True)

    def test_over_limit_is_rejected_while_scanning_intermediate_page(self):
        client, _ = followup_client([])
        calls = []
        pages = iter([
            SimpleNamespace(data=[message("item_00000001", "x" * 16001)], has_more=True),
            SimpleNamespace(data=[message("item_00000002", "")], has_more=False),
        ])
        def get_page(sid, **kw):
            calls.append(kw.get("after"))
            return next(pages)
        client.beta.agents.sessions.items.list = get_page
        with self.assertRaises(SessionFailure):
            read_saved_assistant_items(client, "sess_abcdefgh", "turn_abcdefgh")
        self.assertEqual(len(calls), 1)

    def test_latest_turn_advancing_during_scan_retains_writer(self):
        client, _ = followup_client([message("item_00000001", "answer")],
                                    advance_after_items=turn("turn_ijklmnop"))
        with TemporaryDirectory() as directory:
            journal = SessionJournal(Path(directory) / "journal.sqlite")
            journal.begin("req_writer", sha256(b"request").hexdigest())
            journal.bind("req_writer", "sess_abcdefgh")
            with self.assertRaises(SessionFailure):
                read_followup_turn(client, "sess_abcdefgh", "p", key="evt-adv1",
                                   journal=journal, writer_id="writer-1")
            from manager_core.provider_sessions import SessionConflict
            with self.assertRaises(SessionConflict):
                journal.claim_writer("sess_abcdefgh", "writer-2")

    def test_initial_result_requires_and_matches_saved_result_turn_id(self):
        def initial(result, saved_turn):
            sessions = SimpleNamespace(
                create=lambda **kw: SimpleNamespace(with_result_collection=lambda:
                    FakeInitial(result)),
                turns=SimpleNamespace(list=lambda *a, **kw: SimpleNamespace(data=[saved_turn])))
            return SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
        class FakeInitial:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self):
                return iter([SimpleNamespace(type="agent.session.idle")])
            def get_final_result(self): return self.result
            def __init__(self, result): self.result = result
        result = SimpleNamespace(session_id="sess_abcdefgh", output_text="answer",
                                 turn_id="turn_abcdefgh")
        with self.assertRaises(SessionFailure):
            read_initial_turn(initial(result, turn("turn_ijklmnop")), "p")
        missing = SimpleNamespace(session_id="sess_abcdefgh", output_text="answer")
        with self.assertRaises(SessionFailure):
            read_initial_turn(initial(missing, turn()), "p")


class CancelTurnStateContracts(unittest.TestCase):
    def _cancel(self, before, retrieved, after=None):
        with TemporaryDirectory() as directory:
            journal = SessionJournal(Path(directory) / "journal.sqlite")
            journal.begin("req_cancel", sha256(b"cancel").hexdigest())
            journal.bind("req_cancel", "sess_abcdefgh")
            posted = []
            latest = iter((before, after or before))
            sessions = SimpleNamespace(
                turns=SimpleNamespace(
                    list=lambda *a, **kw: SimpleNamespace(data=[SimpleNamespace(
                        id="turn_abcdefgh", status=next(latest))]),
                    retrieve=lambda tid, *, session_id: SimpleNamespace(
                        id=tid, status=retrieved)),
                events=SimpleNamespace(create=lambda *a, **kw: posted.append(kw)))
            receipt = cancel_and_reconcile(
                SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions))),
                journal, "sess_abcdefgh", "turn_abcdefgh", event_key="cancel-01", writer_id="owner-1")
            return receipt, posted

    def test_queued_and_waiting_cancel_and_read_back_exact_target(self):
        for state in ("queued", "waiting"):
            with self.subTest(state=state):
                receipt, posted = self._cancel(state, "cancelled", "cancelled")
                self.assertEqual(receipt.status, "CANCELLED_VERIFIED")
                self.assertEqual(len(posted), 1)

    def test_requires_action_is_unknown_and_not_cancelled_as_turn_state(self):
        receipt, posted = self._cancel("requires_action", "requires_action")
        self.assertEqual((receipt.status, receipt.provider_turn_status),
                         ("CANCEL_REQUEST_UNKNOWN", "UNKNOWN"))
        self.assertEqual(posted, [])

    def test_contradictory_cancel_readback_remains_unknown(self):
        receipt, posted = self._cancel("queued", "cancelled", "queued")
        self.assertEqual((receipt.status, receipt.provider_turn_status),
                         ("CANCEL_REQUEST_UNKNOWN", "UNKNOWN"))
        self.assertEqual(len(posted), 1)


if __name__ == "__main__":
    unittest.main()
