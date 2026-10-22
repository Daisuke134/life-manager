"""E05: persist intents before API side effects; no blind creation retry."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from manager_core.provider_sessions import SessionJournal, SessionConflict
from manager_core.ampersand_api import read_completed_turn, SessionFailure


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
            turns=SimpleNamespace(retrieve=lambda sid,tid:page)))))
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
