"""E06: fail-closed budget, exact token units, cancellation and silence."""
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from manager_core.provider_budget import (
    BudgetLedger, BudgetExceeded, Usage, estimate_cost_usd,
    cancel_and_reconcile,
)
from manager_core.provider_sessions import SessionJournal
from manager_core.ampersand_api import read_initial_turn, read_followup_turn, SessionFailure


class BudgetContract(unittest.TestCase):
    def test_concurrent_reservations_cannot_exceed_total_cap(self):
        with TemporaryDirectory() as tmp:
            db=Path(tmp)/"budget.sqlite"
            ledger=BudgetLedger(db,cap_usd=Decimal("0.050000"))
            a=ledger.reserve("run_A",Decimal("0.035000"))
            self.assertEqual(a.reserved_usd,Decimal("0.035000"))
            with self.assertRaises(BudgetExceeded):
                BudgetLedger(db,cap_usd=Decimal("0.050000")).reserve(
                    "run_B",Decimal("0.020000"))
            self.assertEqual(ledger.available_usd(),Decimal("0.015000"))
            self.assertEqual(ledger.reserve("run_A",Decimal("0.035000")),a)
            with self.assertRaises(BudgetExceeded):
                ledger.reserve("run_A",Decimal("0.001000"))

    def test_unknown_usage_is_not_zero_and_keeps_reservation(self):
        with TemporaryDirectory() as tmp:
            ledger=BudgetLedger(Path(tmp)/"budget.sqlite",cap_usd=Decimal("0.100000"))
            r=ledger.reserve("case_A",Decimal("0.050000"))
            settled=ledger.settle(r,None)
            self.assertEqual(settled.status,"UNKNOWN_USAGE")
            self.assertIsNone(settled.usage)
            self.assertIsNone(settled.settled_usd)
            self.assertEqual(ledger.available_usd(),Decimal("0.050000"))

    def test_token_estimate_excludes_cache_and_no_double_reasoning(self):
        u=Usage(input_tokens=1_000_000,cached_input_tokens=200_000,
                output_tokens=1_000_000,reasoning_output_tokens=300_000)
        self.assertEqual(estimate_cost_usd(u),Decimal("6.040000"))
        with TemporaryDirectory() as tmp:
            ledger=BudgetLedger(Path(tmp)/"budget.sqlite",cap_usd=Decimal("10"))
            r=ledger.reserve("case_B",Decimal("7"))
            state=ledger.settle(r,u)
            self.assertEqual(state.status,"TOKENS_OBSERVED_COST_UNSETTLED")
            self.assertIsNone(state.settled_usd)
            self.assertEqual(state.estimated_usage_usd,Decimal("6.040000"))

    def test_missing_cached_input_uses_conservative_uncached_estimate(self):
        self.assertEqual(
            estimate_cost_usd(Usage(input_tokens=1_000_000,output_tokens=0)),
            Decimal("1.000000"))

    def test_usage_validates_nonnegative_and_doubly_counted_tokens(self):
        for values in (
            dict(input_tokens=-1,output_tokens=5),
            dict(input_tokens=10,output_tokens=2,cached_input_tokens=11),
            dict(input_tokens=10,output_tokens=2,reasoning_output_tokens=3),
            dict(input_tokens=True,output_tokens=2),
        ):
            with self.subTest(values=values),self.assertRaises(ValueError):
                Usage(**values)

    def test_unverified_billing_never_creates_settled_cost(self):
        with TemporaryDirectory() as tmp:
            ledger=BudgetLedger(Path(tmp)/"budget.sqlite",cap_usd=Decimal("0.10"))
            r=ledger.reserve("caseA",Decimal("0.03"))
            known=ledger.settle(r,Usage(input_tokens=1000,output_tokens=100))
            self.assertIsNone(known.settled_usd)
            self.assertEqual(ledger.available_usd(),Decimal("0.070000"))

    def test_reservation_is_made_before_new_session(self):
        class Dummy:
            calls=0
            def create(self,**kwargs):
                self.calls+=1
                raise AssertionError("model should not receive this request")
        with TemporaryDirectory() as tmp:
            ledger=BudgetLedger(Path(tmp)/"budget.sqlite",cap_usd=Decimal("0.01"))
            sessions=Dummy()
            client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
            with self.assertRaises(BudgetExceeded):
                read_initial_turn(client,"fictional",
                    budget_ledger=ledger,budget_run_id="run_over",
                    upper_usd=Decimal("0.02"))
            self.assertEqual(sessions.calls,0)

    def test_elapsed_deadline_blocks_before_new_session(self):
        class NeverSend:
            def create(self,**kw):
                raise AssertionError("deadline must be checked before HTTP")
        client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=NeverSend())))
        with self.assertRaises(SessionFailure):
            read_initial_turn(client,"fictional",deadline_monotonic=0.0)

    def test_valid_silent_turn_remains_silent_not_failure(self):
        class Stream:
            def __enter__(self): return self
            def __exit__(self,*x): return False
            def __iter__(self):
                yield SimpleNamespace(type="agent.session.idle")
            def get_final_result(self):
                return SimpleNamespace(session_id="sess_abcdefgh",output_text="")
        turn=SimpleNamespace(id="turn_abcdefgh",status="completed",usage=None)
        sessions=SimpleNamespace(
            create=lambda **kw:SimpleNamespace(with_result_collection=lambda:Stream()),
            turns=SimpleNamespace(list=lambda *args,**kw:SimpleNamespace(data=[turn])))
        client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
        r=read_initial_turn(client,"fictional",allow_silent_completion=True)
        self.assertEqual(r.status,"SILENT_COMPLETED")
        self.assertEqual(r.output_text,"")
        self.assertEqual(r.proof_level,"P0")

    def test_followup_reserves_budget_before_api_event_submit(self):
        class NoEvents:
            calls=0
            def stream(self,*args): return self
            def create(self,*args,**kwargs):
                self.calls+=1
                raise AssertionError("should not post when budget exhausted")
        with TemporaryDirectory() as tmp:
            ledger=BudgetLedger(Path(tmp)/"b.sqlite",cap_usd=Decimal("0.010000"))
            events=NoEvents()
            client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(
                sessions=SimpleNamespace(events=events))))
            with self.assertRaises(BudgetExceeded):
                read_followup_turn(client,"sess_abcdefgh","any short fictional update",
                    key="budget-01",budget_ledger=ledger,
                    budget_run_id="turn_A",upper_usd=Decimal("0.020000"))
            self.assertEqual(events.calls,0)

    def test_followup_silent_completion_is_not_invalid_provider_output(self):
        class Stream:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def __iter__(self):
                yield SimpleNamespace(type="agent.session.turn.completed",
                                     turn_id="turn_abcdefgh")
        calls=[]
        turn=SimpleNamespace(id="turn_abcdefgh",status="completed",usage=None)
        sessions=SimpleNamespace(
            events=SimpleNamespace(stream=lambda sid:Stream(),
                                   create=lambda sid,**kwargs:calls.append(kwargs)),
            turns=SimpleNamespace(list=lambda sid,**kwargs:
                                  SimpleNamespace(data=[turn])))
        client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
        res=read_followup_turn(client,"sess_abcdefgh","No extra help needed",
            key="silent-01",allow_silent_completion=True)
        self.assertEqual(res.status,"SILENT_COMPLETED")
        self.assertEqual(res.output_text,"")
        self.assertEqual(len(calls),1)

    def test_live_lab_fails_before_network_without_budget_limit(self):
        import os
        from unittest.mock import patch
        from scripts.phase_ampersand_lab import run_lab
        with TemporaryDirectory(dir=Path.home()) as d:
            journal_path=Path(d)/"journal.sqlite"
            with patch.dict(os.environ,{
                "AMPERSAND_API_KEY":"hak_ExampleValidASCII123",
                "MANAGER_AMPERSAND_RUN_ID":"test_budget_01",
                "MANAGER_AMPERSAND_JOURNAL_PATH":str(journal_path),
            },clear=True):
                with patch("scripts.phase_ampersand_lab.make_client",
                           side_effect=AssertionError("provider must not be called")):
                    with self.assertRaisesRegex(SessionFailure,"budget"):
                        run_lab(live=True,max_sessions=1,output=Path(d)/"result.json")

    def test_followup_deadline_sends_cancel_and_reconciles(self):
        from hashlib import sha256
        from unittest.mock import patch
        clock=[100.0]
        class Stream:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def __iter__(self):
                clock[0]=200.0
                yield SimpleNamespace(type="agent.session.turn.output_text.delta",
                                      turn_id="turn_abcdefgh",delta="partial")
        posted=[]
        sessions=SimpleNamespace(
            events=SimpleNamespace(
                stream=lambda sid:Stream(),
                create=lambda sid,**kwargs:posted.append(kwargs)),
            turns=SimpleNamespace(retrieve=lambda turn_id,*,session_id:
                                  SimpleNamespace(id=turn_id,status="cancelled")))
        client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
        with TemporaryDirectory() as d:
            journal=SessionJournal(Path(d)/"journal.sqlite")
            journal.begin("req_deadline",sha256(b"fictional").hexdigest())
            journal.bind("req_deadline","sess_abcdefgh")
            with patch("time.monotonic",side_effect=lambda:clock[0]):
                with self.assertRaises(SessionFailure):
                    read_followup_turn(client,"sess_abcdefgh","fictional",
                        key="case-01",journal=journal,writer_id="writer-01",
                        deadline_monotonic=120.0)
            self.assertEqual(len(posted),2)
            self.assertEqual(posted[1]["events"],
                             [{"type":"agent.session.input.cancel"}])

    def test_cancellation_request_requires_actual_status_readback(self):
        from hashlib import sha256
        with TemporaryDirectory() as tmp:
            journal=SessionJournal(Path(tmp)/"journal.sqlite")
            journal.begin("req_a",sha256(b"test").hexdigest())
            journal.bind("req_a","sess_abcdefgh")
            calls=[]
            saved=SimpleNamespace(id="turn_abcdefgh",status="in_progress")
            sessions=SimpleNamespace(
                turns=SimpleNamespace(retrieve=lambda tid,*,session_id:saved),
                events=SimpleNamespace(create=lambda sid,**kw:calls.append((sid,kw))))
            client=SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
            receipt=cancel_and_reconcile(client,journal,"sess_abcdefgh","turn_abcdefgh",
                                         event_key="cancel-01",writer_id="owner-a")
            self.assertEqual(receipt.status,"CANCEL_REQUESTED_UNCONFIRMED")
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][1]["events"],[{"type":"agent.session.input.cancel"}])
            saved.status="cancelled"
            reread=cancel_and_reconcile(client,journal,"sess_abcdefgh","turn_abcdefgh",
                                         event_key="cancel-01",writer_id="owner-a")
            self.assertEqual(reread.status,"CANCELLED_VERIFIED")
            self.assertEqual(len(calls),1)


if __name__=="__main__":
    unittest.main()
