"""E05: persist intents before API side effects; no blind creation retry."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from manager_core.provider_sessions import SessionJournal, SessionConflict, reconcile_session_pages, reconcile_provider_sessions
from manager_core.ampersand_api import read_completed_turn, read_saved_assistant_items, SessionFailure


def digest(x):
    return sha256(x.encode()).hexdigest()


class DurableSessionIntent(unittest.TestCase):
    def test_reservation_survives_restart_and_duplicate_is_same_intent(self):
        with TemporaryDirectory() as d:
            path=Path(d)/"provider.sqlite"
            first=SessionJournal(path).begin("req-001",digest("body-v1"))
            self.assertEqual(first.status,"RESERVED")
            reopened=SessionJournal(path)
            second=reopened.begin("req-001",digest("body-v1"))
            self.assertEqual(second.status,"RESERVED")
            with self.assertRaises(SessionConflict):
                reopened.begin("req-001",digest("different-body"))
            reopened.mark_unknown("req-001")
            self.assertEqual(SessionJournal(path).begin("req-001",digest("body-v1")).status,"UNKNOWN")

    def test_unknown_create_reconciles_one_matching_session_not_two(self):
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            j.begin("req-a",digest("prompt"));j.mark_unknown("req-a")
            self.assertEqual(j.reconcile("req-a",[]).status,"UNKNOWN")
            session={"id":"sess_abcdefgh","metadata":{"manager_request_id":"req-a"}}
            self.assertEqual(j.reconcile("req-a",[session]).session_id,"sess_abcdefgh")
            self.assertEqual(j.begin("req-a",digest("prompt")).status,"BOUND")
            with self.assertRaises(SessionConflict):
                j.reconcile("req-a",[session,{"id":"sess_second","metadata":{"manager_request_id":"req-a"}}])

    def test_idempotent_event_body_cannot_change(self):
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            j.begin("req-a",digest("prompt"));j.bind("req-a","sess_abcdefgh")
            self.assertTrue(j.reserve_event("sess_abcdefgh","followup-01",digest("hello")))
            self.assertFalse(SessionJournal(Path(d)/"state.sqlite").reserve_event(
                "sess_abcdefgh","followup-01",digest("hello")))
            with self.assertRaises(SessionConflict):
                j.reserve_event("sess_abcdefgh","followup-01",digest("changed!"))

    def test_one_writer_must_be_explicitly_released(self):
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            j.begin("req-a",digest("x"));j.bind("req-a","sess_abcdefgh")
            j.claim_writer("sess_abcdefgh","owner-A")
            with self.assertRaises(SessionConflict):
                SessionJournal(Path(d)/"state.sqlite").claim_writer("sess_abcdefgh","owner-B")
            j.release_writer("sess_abcdefgh","owner-A")
            j.claim_writer("sess_abcdefgh","owner-B")

    def test_same_external_session_cannot_attach_to_two_intents(self):
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            j.begin("req-a",digest("x"));j.begin("req-b",digest("y"))
            j.bind("req-a","sess_abcdefgh")
            with self.assertRaises(SessionConflict):
                j.bind("req-b","sess_abcdefgh")

    def test_exact_completed_turn_rejects_other_or_failed(self):
        page=SimpleNamespace(id="turn_actual",status="completed",usage=SimpleNamespace(
            input_tokens=10,output_tokens=4))
        client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=SimpleNamespace(
            turns=SimpleNamespace(retrieve=lambda tid,*,session_id:page)))))
        with self.assertRaises(SessionFailure):
            read_completed_turn(client,"sess_abcdefgh","turn_other")
        page.id="turn_actual";page.status="failed"
        with self.assertRaises(SessionFailure):
            read_completed_turn(client,"sess_abcdefgh","turn_actual")
        page.status="completed"
        result=read_completed_turn(client,"sess_abcdefgh","turn_actual")
        self.assertEqual(result.turn_id,"turn_actual")
        self.assertEqual(result.input_tokens,10)
        self.assertEqual(result.status,"completed")

    def test_create_journal_claimed_before_network_and_never_blind_retried(self):
        from manager_core.ampersand_api import read_initial_turn
        with TemporaryDirectory() as d:
            j = SessionJournal(Path(d) / "state.sqlite")
            calls = []
            def broken_create(**kwargs):
                calls.append(kwargs)
                raise RuntimeError("simulated lost response after possible create")
            sessions = SimpleNamespace(create=broken_create)
            client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
            with self.assertRaises(SessionFailure):
                read_initial_turn(client, "fictional test", journal=j, request_id="req_lost")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["metadata"]["manager_request_id"], "req_lost")
            self.assertEqual(j.get("req_lost").status, "UNKNOWN")

    def test_unknown_provider_creation_is_not_repeated(self):
        from manager_core.ampersand_api import read_initial_turn
        with TemporaryDirectory() as d:
            j = SessionJournal(Path(d) / "state.sqlite")
            calls = []
            def broken_create(**kwargs):
                calls.append(kwargs)
                raise RuntimeError("simulated network lost")
            client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=
                SimpleNamespace(create=broken_create))))
            with self.assertRaises(SessionFailure):
                read_initial_turn(client, "fictional test", journal=j, request_id="req_retry")
            with self.assertRaises(SessionFailure):
                read_initial_turn(client, "fictional test", journal=j, request_id="req_retry")
            self.assertEqual(len(calls), 1)

    def test_successful_provider_creation_binds_exact_returned_id(self):
        from manager_core.ampersand_api import read_initial_turn
        class Stream:
            def __enter__(self): return self
            def __exit__(self, *x): return None
            def __iter__(self):
                yield SimpleNamespace(type="agent.session.idle")
            def get_final_result(self):
                return SimpleNamespace(session_id="sess_12345678", output_text="ok")
        calls=[]
        def create(**kw):
            calls.append(kw)
            return SimpleNamespace(with_result_collection=lambda: Stream())
        turn=SimpleNamespace(id="turn_12345678",status="completed",usage=SimpleNamespace(
            input_tokens=11,output_tokens=4))
        sessions=SimpleNamespace(
            create=create,
            turns=SimpleNamespace(list=lambda *args,**kwargs: SimpleNamespace(data=[turn])))
        client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            result=read_initial_turn(client,"fictional test",journal=j,request_id="req_success")
            self.assertEqual(result.session_id,"sess_12345678")
            self.assertEqual(j.get("req_success").status,"BOUND")
            self.assertEqual(j.get("req_success").session_id,"sess_12345678")
            self.assertEqual(calls[0]["metadata"]["manager_request_id"],"req_success")

    def test_live_lab_requires_persistent_journal_before_provider_network(self):
        import os
        from unittest.mock import patch
        from scripts.phase_ampersand_lab import run_lab
        with TemporaryDirectory() as d:
            with patch.dict(os.environ,
                            {"AMPERSAND_API_KEY": "hak_ExampleValidASCII123",
                             "MANAGER_AMPERSAND_RUN_ID": "trial-01"},
                            clear=True):
                with self.assertRaisesRegex(SessionFailure,"journal"):
                    run_lab(live=True, max_sessions=1,
                            output=Path(d)/"report.json")

    def test_followup_requires_writer_identity_when_journal_present(self):
        from manager_core.ampersand_api import read_followup_turn
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            j.begin("req-a",digest("body"));j.bind("req-a","sess_abcdefgh")
            with self.assertRaises(ValueError):
                read_followup_turn(None,"sess_abcdefgh","Hi",key="next-01",
                                   journal=j,writer_id=None)

    def test_reconciliation_fetches_all_pages_before_binding(self):
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            j.begin("req_page",digest("prompt"));j.mark_unknown("req_page")
            cursors=[]
            def fetch_page(after,limit):
                cursors.append(after)
                if after is None:
                    return {"data":[{"id":"sess_11111111","metadata":{"other":"value"}}],
                            "has_more":True}
                if after=="sess_11111111":
                    return {"data":[{"id":"sess_abcdefgh",
                                     "metadata":{"manager_request_id":"req_page"}}],
                            "has_more":False}
                raise AssertionError("unexpected page cursor")
            result=reconcile_session_pages(j,"req_page",fetch_page)
            self.assertEqual(result.session_id,"sess_abcdefgh")
            self.assertEqual(cursors,[None,"sess_11111111"])
            self.assertEqual(j.get("req_page").status,"BOUND")

    def test_reconciliation_rejects_incomplete_page_scan(self):
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            j.begin("req_unknown",digest("prompt"));j.mark_unknown("req_unknown")
            def looping(after,limit):
                return {"data":[{"id":"sess_abcdefgh",
                                 "metadata":{"other":"value"}}],"has_more":True}
            with self.assertRaises(SessionConflict):
                reconcile_session_pages(j,"req_unknown",looping,max_pages=3)
            self.assertEqual(j.get("req_unknown").status,"UNKNOWN")

    def test_two_matching_sessions_across_pages_quarantined(self):
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            j.begin("req_duplicate",digest("prompt"));j.mark_unknown("req_duplicate")
            def fetch(after,limit):
                if after is None:
                    return {"data":[{"id":"sess_aaaaaaaa","metadata":{
                        "manager_request_id":"req_duplicate"}}],"has_more":True}
                return {"data":[{"id":"sess_bbbbbbbb","metadata":{
                    "manager_request_id":"req_duplicate"}}],"has_more":False}
            with self.assertRaises(SessionConflict):
                reconcile_session_pages(j,"req_duplicate",fetch)
            self.assertEqual(j.get("req_duplicate").status,"UNKNOWN")

    def test_sdk_list_paginator_reconciles_exact_matching_session_metadata(self):
        requested=[]
        class Page:
            def __init__(self, rows, more):
                self.data=rows
                self.has_more=more
        def list_pages(*,limit,order,after=None):
            requested.append((limit,order,after))
            if after is None:
                return Page([SimpleNamespace(id="sess_aaaaaaaa",
                    metadata={"manager_request_id":"other"})],True)
            return Page([SimpleNamespace(id="sess_bbbbbbbb",
                metadata={"manager_request_id":"req_actual"})],False)
        with TemporaryDirectory() as d:
            journal=SessionJournal(Path(d)/"s.sqlite")
            journal.begin("req_actual",digest("original body"))
            journal.mark_unknown("req_actual")
            client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(
                sessions=SimpleNamespace(list=list_pages))))
            status=reconcile_provider_sessions(client,journal,"req_actual")
            self.assertEqual(status.session_id,"sess_bbbbbbbb")
            self.assertEqual(requested,[(100,"desc",None),(100,"desc","sess_aaaaaaaa")])

    def test_absent_session_never_causes_another_create(self):
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            j.begin("req_absent",digest("prompt"));j.mark_unknown("req_absent")
            status=reconcile_session_pages(j,"req_absent",lambda after,limit:{
                "data":[],"has_more":False})
            self.assertEqual(status.status,"UNKNOWN")
            with self.assertRaises(SessionConflict):
                j.reserve_for_send("req_absent")

    def test_created_session_id_is_persisted_before_long_stream_finishes(self):
        from manager_core.ampersand_api import read_initial_turn
        with TemporaryDirectory() as d:
            journal=SessionJournal(Path(d)/"evidence.sqlite")
            class CreatedThenLost:
                def __enter__(self): return self
                def __exit__(self,*a): return False
                def __iter__(self):
                    yield SimpleNamespace(type="agent.session.created",
                                          session=SimpleNamespace(id="sess_created01"))
                    # Immediately after this event, session identity must be
                    # safely durable even if generation/stream now disconnects.
                    self_instance=journal.get("req_early")
                    if self_instance.status != "BOUND":
                        raise AssertionError("session id not persisted before stream loss")
                    raise RuntimeError("lost stream after creation")
            client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(
                sessions=SimpleNamespace(
                    create=lambda **kw:SimpleNamespace(
                        with_result_collection=lambda:CreatedThenLost())))))
            with self.assertRaises(SessionFailure):
                read_initial_turn(client,"fictional",journal=journal,request_id="req_early")
            self.assertEqual(journal.get("req_early").status,"BOUND")
            self.assertEqual(journal.get("req_early").session_id,"sess_created01")

    def test_actual_sdk_retrieve_signature_is_keyword_session_id(self):
        # Official openai==3.24.0: turns.retrieve(turn_id, *, session_id=...).
        # A two-positional-argument call must fail this test.
        recorded = []
        def retrieve(turn_id, *, session_id):
            recorded.append((turn_id, session_id))
            return SimpleNamespace(id=turn_id,status="completed",usage=None)
        client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(
            sessions=SimpleNamespace(turns=SimpleNamespace(retrieve=retrieve)))))
        result=read_completed_turn(client,"sess_abcdefgh","turn_abcdefgh")
        self.assertEqual(result.turn_id,"turn_abcdefgh")
        self.assertEqual(recorded,[("turn_abcdefgh","sess_abcdefgh")])

    def test_read_saved_assistant_items_exact_turn_and_paginated(self):
        calls=[]
        def get_page(sid, **kwargs):
            after=kwargs.get("after")
            calls.append(after)
            if after is None:
                return SimpleNamespace(data=[SimpleNamespace(
                    id="item_11111111",type="message",turn_id="turn_other",
                    role="assistant",content=[{"type":"output_text","text":"wrong"}])],
                    has_more=True)
            return SimpleNamespace(data=[SimpleNamespace(
                id="item_22222222",type="message",turn_id="turn_abcdefgh",
                role="assistant",content=[{"type":"output_text","text":"correct"}])],
                has_more=False)
        turn=SimpleNamespace(id="turn_abcdefgh",status="completed",
                             usage=SimpleNamespace(input_tokens=2,output_tokens=3))
        sessions=SimpleNamespace(
            turns=SimpleNamespace(retrieve=lambda tid,*,session_id:turn),
            items=SimpleNamespace(list=get_page))
        client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
        result=read_saved_assistant_items(client,"sess_abcdefgh","turn_abcdefgh")
        self.assertEqual(result,("correct",))
        self.assertEqual(calls,[None,"item_11111111"])

    def test_saved_items_incomplete_pagination_keeps_unknown(self):
        turn=SimpleNamespace(id="turn_abcdefgh",status="completed",
                             usage=None)
        item=SimpleNamespace(id="item_abcdefgh",type="message",
                             turn_id="turn_abcdefgh",role="assistant",
                             content=[{"type":"output_text","text":"partial"}])
        sessions=SimpleNamespace(
            turns=SimpleNamespace(retrieve=lambda tid,*,session_id:turn),
            items=SimpleNamespace(list=lambda sid,**kw:
                SimpleNamespace(data=[item],has_more=True)))
        client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
        with self.assertRaises(SessionFailure):
            read_saved_assistant_items(client,"sess_abcdefgh","turn_abcdefgh",max_pages=2)

    def test_missing_session_and_invalid_ids_fail_closed(self):
        with TemporaryDirectory() as d:
            j=SessionJournal(Path(d)/"state.sqlite")
            with self.assertRaises(SessionConflict):
                j.bind("missing","sess_abcdefgh")
            for invalid in ("", "credential?", "a"*180):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    j.begin(invalid,digest("x"))


if __name__=="__main__":
    unittest.main()
