"""Real blocking-read deadline and durable UNKNOWN/cancellation boundaries."""
import math
import time
import threading
import unittest
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import patch
from manager_core.ampersand_api import read_initial_turn, read_followup_turn, SessionFailure
from manager_core.provider_sessions import SessionJournal, SessionConflict
from manager_core.provider_budget import BudgetLedger, BudgetExceeded, Usage, cancel_and_reconcile


class Stream:
    def __init__(self, events): self.events=events
    def with_result_collection(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def __iter__(self): return iter(self.events())
    def get_final_result(self):
        return NS(session_id='sess_abcdefgh',output_text='advice')


def client_for(events, posted, saved_status='cancelled'):
    def post(sid, **kwargs): posted.append(kwargs)
    saved=NS(id='turn_abcdefgh',status=saved_status,usage=None)
    sessions=NS(create=lambda **kwargs:Stream(events),
                events=NS(create=post),
                turns=NS(retrieve=lambda tid,**kwargs:saved,
                         list=lambda *args,**kw:NS(data=[saved])))
    return NS(beta=NS(agents=NS(sessions=sessions)))


class ProviderDeadlineTests(unittest.TestCase):
    def test_initial_stream_deadline_cancels_known_turn(self):
        clock=[100.0];posted=[]
        def events():
            yield NS(type='agent.session.created',session_id='sess_abcdefgh')
            yield NS(type='agent.session.turn.started',turn_id='turn_abcdefgh')
            clock[0]=200.0
            yield NS(type='agent.session.idle')
        with TemporaryDirectory() as tmp:
            journal=SessionJournal(Path(tmp)/'journal.sqlite')
            with patch('time.monotonic',side_effect=lambda:clock[0]):
                with self.assertRaises(SessionFailure):
                    read_initial_turn(client_for(events,posted),'fictional',journal=journal,
                                      request_id='initial_deadline',deadline_monotonic=120.0)
            self.assertEqual(len(posted),1)
            self.assertEqual(posted[0]['events'],[{'type':'agent.session.input.cancel'}])

    def test_created_ids_at_deadline_are_bound_before_cancel(self):
        clock=[100.0];posted=[]
        def events():
            clock[0]=200.0
            yield NS(type='agent.session.created',session_id='sess_abcdefgh',turn_id='turn_abcdefgh')
        with TemporaryDirectory() as tmp:
            journal=SessionJournal(Path(tmp)/'journal.sqlite')
            with patch('time.monotonic',side_effect=lambda:clock[0]),self.assertRaises(SessionFailure):
                read_initial_turn(client_for(events,posted),'fictional',journal=journal,
                                  request_id='initial_edge',deadline_monotonic=120.0)
            self.assertEqual(journal.get('initial_edge').session_id,'sess_abcdefgh')
            self.assertEqual(len(posted),1)

    def test_alarm_during_initial_bind_recovers_known_ids_for_cancel(self):
        posted=[]
        def events():
            yield NS(type='agent.session.created',session_id='sess_abcdefgh',turn_id='turn_abcdefgh')
        with TemporaryDirectory() as tmp:
            journal=SessionJournal(Path(tmp)/'journal.sqlite');bind=journal.bind;calls=[]
            def interrupted_bind(*args):
                calls.append(args)
                if len(calls)==1:threading.Event().wait(3)
                return bind(*args)
            start=time.monotonic()
            with patch.object(journal,'bind',side_effect=interrupted_bind),self.assertRaises(SessionFailure):
                read_initial_turn(client_for(events,posted),'fictional',journal=journal,
                                  request_id='initial_bind_alarm',deadline_monotonic=start+.05)
            self.assertLess(time.monotonic()-start,.75)
            self.assertEqual(journal.get('initial_bind_alarm').session_id,'sess_abcdefgh')
            self.assertEqual(len(posted),1)

    def test_stream_without_events_has_bounded_transport_wait(self):
        posted=[]
        def blocked():
            threading.Event().wait(3)
            yield NS(type='agent.session.idle')
        with TemporaryDirectory() as tmp:
            journal=SessionJournal(Path(tmp)/'journal.sqlite')
            start=time.monotonic()
            with self.assertRaises(SessionFailure):
                read_initial_turn(client_for(blocked,posted),'fictional',journal=journal,
                                  request_id='blocked_initial',deadline_monotonic=start+.05)
            self.assertLess(time.monotonic()-start,.75)
            self.assertEqual(posted,[])
            # An interrupted creation cannot be submitted again.
            with self.assertRaises(SessionFailure):
                read_initial_turn(client_for(blocked,posted),'fictional',journal=journal,
                                  request_id='blocked_initial')

    def test_transport_timeout_cancels_without_claiming_terminal_status(self):
        posted=[]
        def events():
            yield NS(type='agent.session.created',session_id='sess_abcdefgh')
            yield NS(type='agent.session.turn.started',turn_id='turn_abcdefgh')
            raise TimeoutError('sensitive transport body must not become report')
        with TemporaryDirectory() as tmp:
            journal=SessionJournal(Path(tmp)/'journal.sqlite')
            with self.assertRaises(SessionFailure):
                read_initial_turn(client_for(events,posted,'in_progress'),'fictional',
                                  journal=journal,request_id='timeout_initial',
                                  deadline_monotonic=time.monotonic()+10)
            self.assertEqual(len(posted),1)
            with self.assertRaises(SessionConflict):
                journal.claim_writer('sess_abcdefgh','another_writer')

    def test_followup_without_events_has_absolute_deadline(self):
        posted=[]
        def blocked():
            threading.Event().wait(3)
            yield NS(type='agent.session.idle')
        with TemporaryDirectory() as tmp:
            journal=SessionJournal(Path(tmp)/'journal.sqlite')
            journal.begin('req_followup',sha256(b'fictional').hexdigest())
            journal.bind('req_followup','sess_abcdefgh')
            client=client_for(blocked,posted)
            client.beta.agents.sessions.events.stream=lambda sid:Stream(blocked)
            start=time.monotonic()
            with self.assertRaises(SessionFailure):
                read_followup_turn(client,'sess_abcdefgh','fictional',key='event_blocked',
                    journal=journal,writer_id='owner',deadline_monotonic=start+.05)
            self.assertLess(time.monotonic()-start,.75)
            self.assertEqual(len(posted),1)
            with self.assertRaises(SessionConflict):
                journal.claim_writer('sess_abcdefgh','another_writer')

    def test_model_probe_is_also_bounded_without_session_creation(self):
        from manager_core.provider_deadline import provider_deadline
        start=time.monotonic()
        with self.assertRaises(SessionFailure):
            with provider_deadline(start+.05):
                threading.Event().wait(3)
        self.assertLess(time.monotonic()-start,.75)

    def test_existing_process_alarm_is_preserved_and_no_request_sent(self):
        import signal
        calls=[]
        old_handler=signal.getsignal(signal.SIGALRM)
        signal.setitimer(signal.ITIMER_REAL,10)
        try:
            sessions=NS(create=lambda **kw:calls.append(kw))
            with self.assertRaises(SessionFailure):
                read_initial_turn(NS(beta=NS(agents=NS(sessions=sessions))),
                    'fictional',deadline_monotonic=time.monotonic()+5)
            self.assertEqual(calls,[])
            self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],5)
            self.assertEqual(signal.getsignal(signal.SIGALRM),old_handler)
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)

    def test_nonfinite_or_boolean_deadline_denied_before_creation(self):
        for value in (math.nan,math.inf,-math.inf,True):
            calls=[]
            sessions=NS(create=lambda **kwargs:calls.append(kwargs))
            client=NS(beta=NS(agents=NS(sessions=sessions)))
            with self.subTest(value=value),self.assertRaises((ValueError,SessionFailure)):
                read_initial_turn(client,'fictional',deadline_monotonic=value)
            self.assertEqual(calls,[])

    def test_cancellation_wrong_turn_readback_remains_unknown(self):
        with TemporaryDirectory() as tmp:
            journal=SessionJournal(Path(tmp)/'journal.sqlite')
            journal.begin('req_cancel',sha256(b'fictional').hexdigest())
            journal.bind('req_cancel','sess_abcdefgh')
            sessions=NS(events=NS(create=lambda *args,**kwargs:None),
                        turns=NS(retrieve=lambda *args,**kwargs:
                                 NS(id='turn_wrongone',status='cancelled')))
            receipt=cancel_and_reconcile(NS(beta=NS(agents=NS(sessions=sessions))),
                journal,'sess_abcdefgh','turn_abcdefgh',event_key='cancel_wrong',writer_id='owner')
            self.assertNotEqual(receipt.status,'CANCELLED_VERIFIED')
            with self.assertRaises(SessionConflict):
                journal.claim_writer('sess_abcdefgh','another_writer')

    def test_observed_exposure_above_reservation_stops_new_requests(self):
        with TemporaryDirectory() as tmp:
            ledger=BudgetLedger(Path(tmp)/'budget.sqlite',cap_usd=Decimal('.1'))
            r=ledger.reserve('case_A',Decimal('.01'))
            ledger.settle(r,Usage(100_000,0))
            with self.assertRaises(BudgetExceeded):
                ledger.reserve('case_B',Decimal('.01'))

    def test_later_missing_usage_does_not_erase_observed_usage_status(self):
        with TemporaryDirectory() as tmp:
            ledger=BudgetLedger(Path(tmp)/'budget.sqlite',cap_usd=Decimal('.1'))
            r=ledger.reserve('case_A',Decimal('.05'))
            known=ledger.settle(r,Usage(100,10))
            reread=ledger.settle(r,None)
            self.assertEqual(reread.status,known.status)
            self.assertEqual(reread.usage,known.usage)


if __name__=='__main__': unittest.main()
