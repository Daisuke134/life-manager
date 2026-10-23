"""Checkpoint-bound provider regressions use only SQLite and injected fakes."""
import unittest
import sqlite3
from decimal import Decimal
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from time import monotonic
import base64


class OwnedProviderRegressions(unittest.TestCase):
    def test_public_checkpointed_owner_interface_exists(self):
        from manager_core.owned_provider import CheckpointedProvider, ProviderAdvice
        self.assertTrue(callable(CheckpointedProvider))
        self.assertTrue(callable(ProviderAdvice))

    def test_store_hooks_are_optional_post_commit_interfaces(self):
        import inspect
        from manager_core.provider_sessions import SessionJournal
        from manager_core.provider_budget import BudgetLedger
        self.assertIn("after_commit", inspect.signature(SessionJournal).parameters)
        self.assertIn("after_commit", inspect.signature(BudgetLedger).parameters)

    def test_store_hook_runs_after_commit_and_connection_close(self):
        from manager_core.provider_sessions import SessionJournal
        from manager_core.provider_budget import BudgetLedger
        import hashlib
        with TemporaryDirectory() as tmp:
            path = tmp + "/provider.sqlite"
            calls = []
            def saved():
                with sqlite3.connect(path, timeout=0.1) as db:
                    row = db.execute("SELECT status FROM amp_sessions WHERE request_id='req1'").fetchone()
                    if row is not None:
                        calls.append((row[0], db.in_transaction))
            journal = SessionJournal(path, after_commit=saved)
            calls.clear()
            journal.begin("req1", hashlib.sha256(b"body").hexdigest())
            self.assertEqual(calls, [("RESERVED", False)])

            budget_calls = []
            ledger = BudgetLedger(path, cap_usd=Decimal("0.05"),
                                  after_commit=lambda: budget_calls.append(
                                      sqlite3.connect(path).execute(
                                          "SELECT status FROM budget_reservations WHERE run_id='run1'").fetchone()))
            budget_calls.clear()
            ledger.reserve("run1", Decimal("0.03"))
            self.assertEqual(budget_calls, [("RESERVED",)])

    def test_checkpoint_hook_failure_propagates_after_committed_write(self):
        from manager_core.provider_sessions import SessionJournal
        import hashlib
        with TemporaryDirectory() as tmp:
            path = tmp + "/provider.sqlite"
            failed = [False]
            def failed_save():
                if failed[0]:
                    raise RuntimeError("checkpoint unavailable")
            journal = SessionJournal(path, after_commit=failed_save)
            failed[0] = True
            with self.assertRaisesRegex(RuntimeError, "checkpoint unavailable"):
                journal.begin("req2", hashlib.sha256(b"body").hexdigest())
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("SELECT status FROM amp_sessions WHERE request_id='req2'").fetchone()[0],
                                 "RESERVED")

    def test_checkpoint_fences_on_baseexception_and_preserves_interrupt(self):
        from manager_core.owned_checkpoint import PrivateCheckpoint
        class StopNow(BaseException):
            pass
        def transport(payload):
            if payload["operation"] == "acquire":
                return {"revision": 0, "sha256": "0" * 64,
                        "snapshot": "", "owner": "123:1:" + payload["nonce"]}
            raise StopNow("interrupt")
        checkpoint = PrivateCheckpoint(transport, run_id="123", run_attempt="1")
        checkpoint.db = "fixture"
        with self.assertRaises(StopNow):
            checkpoint._transition("checkpoint")
        self.assertTrue(checkpoint.broken)

    def test_remote_write_then_baseexception_fences_without_replacing_interrupt(self):
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from test_owned_checkpoint import MemoryGateway, snapshot
        class Alarm(BaseException):
            pass
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, _ = snapshot(root / "seed")
            gateway = MemoryGateway(raw)
            calls = []
            def transport(payload):
                result = gateway(payload)
                calls.append(payload["operation"])
                if payload["operation"] == "checkpoint":
                    raise Alarm("original interrupt")
                return result
            checkpoint = PrivateCheckpoint(transport, run_id="123", run_attempt="1")
            checkpoint.acquire(root / "run")
            with self.assertRaisesRegex(Alarm, "original interrupt"):
                checkpoint.save()
            self.assertTrue(checkpoint.broken)
            before = list(calls)
            with self.assertRaises(Exception):
                checkpoint.save()
            self.assertEqual(calls, before)
            self.assertEqual(gateway.value["revision"], 1)

    def _owner(self, root, cap=Decimal("0.05")):
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from test_owned_checkpoint import MemoryGateway, snapshot
        raw, _ = snapshot(root / "seed")
        gateway = MemoryGateway(raw)
        checkpoint = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
        checkpoint.acquire(root / "run")
        from manager_core.owned_provider import CheckpointedProvider
        return gateway, checkpoint, CheckpointedProvider(checkpoint, cap_usd=cap)

    def _context(self, synthetic=False):
        from manager_core.collaboration import PlannerContext, PublicFact
        from manager_core.models.source import Source
        now = datetime.now(timezone.utc)
        source = Source(
            "synthetic:case" if synthetic else "public:case",
            "https://example.org/report", "cc-by", "allowed_with_conditions",
            "a" * 64, now, "public_nonpersonal")
        kind = "SYNTHETIC_SCENARIO" if synthetic else "PUBLIC_SOURCE_CLAIM"
        return PlannerContext("Assess the public report", (PublicFact(source, "Claim from report", kind),), now)

    def _client(self, snapshot_check=None, after_created=None):
        class Stream:
            def __init__(self):
                self.events = [SimpleNamespace(type="agent.session.created", session_id="sess_12345678"),
                               SimpleNamespace(type="agent.session.idle")]
            def with_result_collection(self): return self
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self):
                yield self.events[0]
                if after_created:
                    after_created()
                yield self.events[1]
            def get_final_result(self):
                return SimpleNamespace(session_id="sess_12345678", output_text=
                    '{"decision":"PROPOSE","reason":"Review the cited claim.","source_ids":["public:case"]}')
        class Sessions:
            def __init__(self): self.create_count = 0
            def create(inner, **kwargs):
                inner.create_count += 1
                if snapshot_check: snapshot_check()
                return Stream()
            class turns:
                @staticmethod
                def list(*args, **kwargs):
                    turn = SimpleNamespace(id="turn_12345678", status="completed",
                        usage=SimpleNamespace(input_tokens=10, output_tokens=20,
                            input_tokens_details=None, output_tokens_details=None))
                    return SimpleNamespace(data=[turn])
        sessions = Sessions()
        client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions)))
        return client, sessions

    def test_public_prompt_mode_omits_fictional_claim_and_rejects_synthetic(self):
        from manager_core.collaboration import render_prompt
        prompt = render_prompt(self._context(), fictional=False)
        self.assertNotIn("fictional advisory exercise", prompt)
        self.assertIn("public:case", prompt)
        with self.assertRaises(ValueError):
            render_prompt(self._context(synthetic=True), fictional=False)

    def test_create_sees_acknowledged_unknown_intent_and_reserved_exposure(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway, checkpoint, owner = self._owner(root)
            seen = []
            def read_snapshot():
                raw = base64.b64decode(gateway.value["snapshot"])
                snap = root / "remote.sqlite"
                snap.write_bytes(raw)
                with sqlite3.connect(snap) as db:
                    seen.append((db.execute("SELECT status FROM amp_sessions WHERE request_id='req1'").fetchone()[0],
                                 db.execute("SELECT reserved_units FROM budget_reservations").fetchone()[0]))
            def check_snapshot():
                read_snapshot()
            client, sessions = self._client(check_snapshot, read_snapshot)
            result = owner.initial(client, self._context(), request_id="req1",
                                   upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            self.assertEqual(seen, [("UNKNOWN", 30000), ("BOUND", 30000)])
            self.assertEqual(Decimal(seen[0][1]) * Decimal("0.000001"), Decimal("0.030000"))
            self.assertEqual(sessions.create_count, 1)
            self.assertFalse(result.advice.authorized_execution)
            self.assertFalse(result.advice.causal_support)
            self.assertEqual(result.advice.human_outcome, "NOT_MEASURED")

    def test_distinct_operations_cannot_reuse_budget_under_same_caller_label(self):
        with TemporaryDirectory() as tmp:
            _, _, owner = self._owner(Path(tmp))
            client, sessions = self._client()
            owner.initial(client, self._context(), request_id="req1",
                          upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            with self.assertRaises(Exception):
                owner.initial(client, self._context(), request_id="req2",
                              upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            self.assertEqual(sessions.create_count, 1)

    def test_lost_checkpoint_ack_fences_before_provider_send(self):
        with TemporaryDirectory() as tmp:
            gateway, checkpoint, owner = self._owner(Path(tmp))
            gateway.lose_ack = True
            client, sessions = self._client()
            with self.assertRaises(Exception):
                owner.initial(client, self._context(), request_id="req1",
                              upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            self.assertTrue(checkpoint.broken)
            self.assertEqual(sessions.create_count, 0)

    def test_followup_checkpoints_writer_event_reservation_usage_and_release(self):
        import hashlib
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway, checkpoint, owner = self._owner(root)
            owner.journal.begin("first", hashlib.sha256(b"body").hexdigest())
            owner.journal.bind("first", "sess_12345678")
            observed = []
            class Events:
                @staticmethod
                def stream(*args):
                    class Stream:
                        def __enter__(self): return iter([
                            SimpleNamespace(type="agent.session.turn.output_text.done", text=
                                '{"decision":"ASK","reason":"Which claim?","source_ids":["public:case"]}'),
                            SimpleNamespace(type="agent.session.turn.completed", turn_id="turn_12345678")])
                        def __exit__(self, *args): return False
                    return Stream()
                @staticmethod
                def create(session_id, *, events, idempotency_key):
                    snap = root / "before-followup.sqlite"
                    snap.write_bytes(base64.b64decode(gateway.value["snapshot"]))
                    with sqlite3.connect(snap) as db:
                        observed.append((db.execute("SELECT writer_id FROM amp_sessions WHERE session_id=?", (session_id,)).fetchone()[0],
                                         db.execute("SELECT event_key FROM amp_events WHERE session_id=?", (session_id,)).fetchone()[0],
                                         db.execute("SELECT reserved_units FROM budget_reservations").fetchone()[0]))
            agents = SimpleNamespace(sessions=SimpleNamespace(events=Events,
                turns=SimpleNamespace(list=lambda *a, **k: SimpleNamespace(data=[SimpleNamespace(
                    id="turn_12345678", status="completed", usage=SimpleNamespace(
                        input_tokens=10, output_tokens=20, input_tokens_details=None,
                        output_tokens_details=None))]))))
            client = SimpleNamespace(beta=SimpleNamespace(agents=agents))
            result = owner.followup(client, "sess_12345678", self._context(), key="fup1",
                upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            self.assertEqual(result.advice.decision, "ASK")
            self.assertEqual(observed, [("followup_" + hashlib.sha256(b"sess_12345678\0fup1").hexdigest(),
                                         "fup1", 30000)])
            checkpoint.release()
            from manager_core.owned_checkpoint import PrivateCheckpoint
            restored = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
            restored.acquire(root / "next")
            with sqlite3.connect(restored.db) as db:
                self.assertIsNone(db.execute("SELECT writer_id FROM amp_sessions WHERE session_id='sess_12345678'").fetchone()[0])
                self.assertEqual(db.execute("SELECT status FROM budget_reservations").fetchone()[0],
                                 "TOKENS_OBSERVED_COST_UNSETTLED")

    def test_cancel_event_and_writer_are_acknowledged_before_provider_http(self):
        import hashlib
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway, checkpoint, owner = self._owner(root)
            owner.journal.begin("first", hashlib.sha256(b"body").hexdigest())
            owner.journal.bind("first", "sess_12345678")
            observed = []
            class Events:
                @staticmethod
                def create(session_id, *, events, idempotency_key):
                    snap = root / "before-cancel.sqlite"
                    snap.write_bytes(base64.b64decode(gateway.value["snapshot"]))
                    with sqlite3.connect(snap) as db:
                        observed.append((db.execute("SELECT writer_id FROM amp_sessions WHERE session_id=?", (session_id,)).fetchone()[0],
                                         db.execute("SELECT event_key FROM amp_events WHERE session_id=?", (session_id,)).fetchone()[0]))
            turns = SimpleNamespace(retrieve=lambda turn_id, *, session_id:
                SimpleNamespace(id=turn_id, status="cancelled"))
            client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(
                sessions=SimpleNamespace(events=Events, turns=turns))))
            receipt = owner.cancel(client, "sess_12345678", "turn_12345678", key="cancel1")
            self.assertEqual(receipt.status, "CANCELLED_VERIFIED")
            self.assertEqual(observed, [("cancel_" + hashlib.sha256(b"sess_12345678\0turn_12345678\0cancel1").hexdigest(),
                                         "cancel1")])

    def test_lost_event_checkpoint_ack_fences_before_event_http(self):
        import hashlib
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from manager_core.owned_provider import CheckpointedProvider
        from test_owned_checkpoint import MemoryGateway, snapshot
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, _ = snapshot(root / "seed")
            base = MemoryGateway(raw)
            class LoseEventAck:
                def __call__(self, payload):
                    result = base(payload)
                    if payload["operation"] == "checkpoint":
                        snap = root / "payload.sqlite"
                        snap.write_bytes(base64.b64decode(payload["snapshot"]))
                        with sqlite3.connect(snap) as db:
                            found = db.execute("SELECT 1 FROM amp_events WHERE event_key='fup3'").fetchone()
                        if found:
                            raise OSError("event checkpoint response lost after write")
                    return result
            checkpoint = PrivateCheckpoint(LoseEventAck(), run_id="123", run_attempt="1")
            checkpoint.acquire(root / "run")
            owner = CheckpointedProvider(checkpoint, cap_usd=Decimal("0.05"))
            owner.journal.begin("first", hashlib.sha256(b"body").hexdigest())
            owner.journal.bind("first", "sess_12345678")
            class Events:
                create_count = 0
                @classmethod
                def create(cls, *args, **kwargs): cls.create_count += 1
                @staticmethod
                def stream(*args):
                    class Stream:
                        def __enter__(self): return iter(())
                        def __exit__(self, *args): return False
                    return Stream()
            client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(
                sessions=SimpleNamespace(events=Events, turns=SimpleNamespace(list=lambda *a, **k: None)))))
            with self.assertRaises(Exception):
                owner.followup(client, "sess_12345678", self._context(), key="fup3",
                    upper_usd=Decimal("0.01"), deadline_monotonic=monotonic()+10)
            self.assertTrue(checkpoint.broken)
            self.assertEqual(Events.create_count, 0)

    def test_uncertain_create_is_not_recreated_after_fresh_restore(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway, checkpoint, owner = self._owner(root)
            def lost_after_provider_entry():
                raise OSError("provider response lost")
            failed_client, failed_sessions = self._client(lost_after_provider_entry)
            with self.assertRaises(Exception):
                owner.initial(failed_client, self._context(), request_id="req1",
                    upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            self.assertEqual(failed_sessions.create_count, 1)
            checkpoint.release()
            from manager_core.owned_checkpoint import PrivateCheckpoint
            fresh = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
            fresh.acquire(root / "next")
            from manager_core.owned_provider import CheckpointedProvider
            restored = CheckpointedProvider(fresh, cap_usd=Decimal("0.05"))
            retry_client, retry_sessions = self._client()
            with self.assertRaises(Exception):
                restored.initial(retry_client, self._context(), request_id="req1",
                    upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            self.assertEqual(retry_sessions.create_count, 0)
            with sqlite3.connect(fresh.db) as db:
                self.assertEqual(db.execute("SELECT status FROM amp_sessions WHERE request_id='req1'").fetchone()[0], "UNKNOWN")

    def test_uncertain_followup_event_is_not_recreated_after_fresh_restore(self):
        import hashlib
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from manager_core.owned_provider import CheckpointedProvider
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway, checkpoint, owner = self._owner(root)
            owner.journal.begin("first", hashlib.sha256(b"body").hexdigest())
            owner.journal.bind("first", "sess_12345678")
            class Events:
                create_count = 0
                @classmethod
                def create(cls, session_id, *, events, idempotency_key):
                    cls.create_count += 1
                    snap = root / "followup-remote.sqlite"
                    snap.write_bytes(base64.b64decode(gateway.value["snapshot"]))
                    with sqlite3.connect(snap) as db:
                        assert db.execute("SELECT event_key FROM amp_events WHERE session_id=?", (session_id,)).fetchone()[0] == "fup2"
                    raise OSError("event response lost")
                @staticmethod
                def stream(*args):
                    class Stream:
                        def __enter__(self): return iter(())
                        def __exit__(self, *args): return False
                    return Stream()
            client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(
                sessions=SimpleNamespace(events=Events, turns=SimpleNamespace(list=lambda *a, **k: None)))))
            with self.assertRaises(Exception):
                owner.followup(client, "sess_12345678", self._context(), key="fup2",
                    upper_usd=Decimal("0.01"), deadline_monotonic=monotonic()+10)
            self.assertEqual(Events.create_count, 1)
            checkpoint.release()
            fresh = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
            fresh.acquire(root / "next")
            restored = CheckpointedProvider(fresh, cap_usd=Decimal("0.05"))
            with self.assertRaises(Exception):
                restored.followup(client, "sess_12345678", self._context(), key="fup2",
                    upper_usd=Decimal("0.01"), deadline_monotonic=monotonic()+10)
            self.assertEqual(Events.create_count, 1)

    def test_reserved_cap_survives_fresh_checkpoint_restore(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway, checkpoint, owner = self._owner(root)
            client, sessions = self._client()
            owner.initial(client, self._context(), request_id="req1",
                upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            checkpoint.release()
            from manager_core.owned_checkpoint import PrivateCheckpoint
            fresh = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
            fresh.acquire(root / "next")
            from manager_core.owned_provider import CheckpointedProvider
            restored = CheckpointedProvider(fresh, cap_usd=Decimal("0.05"))
            second_client, second_sessions = self._client()
            with self.assertRaises(Exception):
                restored.initial(second_client, self._context(), request_id="req2",
                    upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            self.assertEqual(sessions.create_count, 1)
            self.assertEqual(second_sessions.create_count, 0)

    def test_reconcile_absent_ambiguous_or_incomplete_pages_never_send(self):
        import hashlib
        from manager_core.owned_checkpoint import PrivateCheckpoint
        from manager_core.owned_provider import CheckpointedProvider
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for mode in ("absent", "ambiguous", "incomplete"):
                with self.subTest(mode=mode):
                    gateway, checkpoint, owner = self._owner(root / mode)
                    owner.journal.begin("req1", hashlib.sha256(b"body").hexdigest())
                    owner.journal.reserve_for_send("req1")
                    checkpoint.release()
                    fresh = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
                    fresh.acquire(root / mode / "next")
                    restored = CheckpointedProvider(fresh, cap_usd=Decimal("0.05"))
                    if mode == "absent":
                        rows = []
                        more = False
                    elif mode == "ambiguous":
                        rows = [SimpleNamespace(id="sess_abcdefgh", metadata={"manager_request_id":"req1"}),
                                SimpleNamespace(id="sess_ijklmnop", metadata={"manager_request_id":"req1"})]
                        more = False
                    else:
                        rows = []
                        more = True
                    class Sessions:
                        create_count = 0
                        @staticmethod
                        def list(**kwargs): return SimpleNamespace(data=rows, has_more=more)
                        @staticmethod
                        def create(**kwargs): Sessions.create_count += 1
                    client = SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=Sessions)))
                    if mode == "absent":
                        self.assertEqual(restored.reconcile(client, "req1", deadline_monotonic=monotonic()+10).status, "UNKNOWN")
                    else:
                        with self.assertRaises(Exception):
                            restored.reconcile(client, "req1", deadline_monotonic=monotonic()+10)
                    self.assertEqual(Sessions.create_count, 0)

    def test_malformed_model_output_stays_p0_no_execution(self):
        from manager_core.collaboration import safe_advisory
        result = safe_advisory('{"decision":"EXECUTE","reason":"run it","source_ids":[]}', self._context())
        self.assertEqual(result.decision, "PASS")
        self.assertFalse(result.authorized_execution)
        self.assertFalse(result.causal_support)
        self.assertEqual(result.human_outcome, "NOT_MEASURED")

    def test_old_snapshots_remain_valid_but_partial_and_invalid_provider_state_is_rejected(self):
        from manager_core.owned_checkpoint import _validate_database
        from test_owned_checkpoint import snapshot
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, _ = snapshot(root / "seed")
            old = root / "old.sqlite"
            old.write_bytes(raw)
            _validate_database(old)
            partial = root / "partial.sqlite"
            partial.write_bytes(raw)
            with sqlite3.connect(partial) as db:
                db.execute("CREATE TABLE amp_sessions(request_id TEXT)")
            with self.assertRaises(ValueError):
                _validate_database(partial)
            invalid = root / "invalid.sqlite"
            invalid.write_bytes(raw)
            with sqlite3.connect(invalid) as db:
                db.executescript("""
                    CREATE TABLE amp_sessions(request_id TEXT, body_hash TEXT, status TEXT, session_id TEXT, writer_id TEXT, created_at TEXT);
                    CREATE TABLE amp_events(session_id TEXT, event_key TEXT, body_hash TEXT);
                    CREATE TABLE budget_policy(id INTEGER, cap_units INTEGER);
                    CREATE TABLE budget_reservations(run_id TEXT, reserved_units INTEGER, status TEXT, usage_json TEXT, measured_cost_units INTEGER, settled_units INTEGER);
                    INSERT INTO budget_policy VALUES(1,0);
                """)
            with self.assertRaises(ValueError):
                _validate_database(invalid)

    def test_invalid_usage_and_session_references_are_rejected_but_measured_overage_is_preserved(self):
        from manager_core.owned_checkpoint import _validate_database
        from manager_core.provider_budget import BudgetLedger, estimate_cost_usd, Usage
        from manager_core.provider_sessions import SessionJournal
        from test_owned_checkpoint import snapshot
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, _ = snapshot(root / "seed")
            invalid_usage = root / "usage.sqlite"
            invalid_usage.write_bytes(raw)
            SessionJournal(invalid_usage)
            BudgetLedger(invalid_usage, cap_usd=Decimal("0.05"))
            with sqlite3.connect(invalid_usage) as db:
                db.execute("INSERT INTO budget_reservations VALUES (?,?,?,?,?,?)",
                           ("initial_bad", 30000, "TOKENS_OBSERVED_COST_UNSETTLED", "{}", 0, None))
            with self.assertRaises(ValueError):
                _validate_database(invalid_usage)

            invalid_ref = root / "reference.sqlite"
            invalid_ref.write_bytes(raw)
            SessionJournal(invalid_ref)
            BudgetLedger(invalid_ref, cap_usd=Decimal("0.05"))
            with sqlite3.connect(invalid_ref) as db:
                db.execute("INSERT INTO amp_sessions VALUES (?,?,?,?,?,?)",
                           ("req1", "a"*64, "BOUND", "not-a-session", None, "now"))
            with self.assertRaises(ValueError):
                _validate_database(invalid_ref)

            invalid_writer = root / "writer.sqlite"
            invalid_writer.write_bytes(raw)
            SessionJournal(invalid_writer)
            BudgetLedger(invalid_writer, cap_usd=Decimal("0.05"))
            with sqlite3.connect(invalid_writer) as db:
                db.execute("INSERT INTO amp_sessions VALUES (?,?,?,?,?,?)",
                           ("req1", "a"*64, "UNKNOWN", None, "writer1", "now"))
            with self.assertRaises(ValueError):
                _validate_database(invalid_writer)

            overage = root / "overage.sqlite"
            overage.write_bytes(raw)
            SessionJournal(overage)
            BudgetLedger(overage, cap_usd=Decimal("0.05"))
            usage = Usage(0, 100000)
            estimate = int(estimate_cost_usd(usage) * 1_000_000)
            usage_json = '{"cached_input_tokens":null,"input_tokens":0,"output_tokens":100000,"reasoning_output_tokens":null}'
            with sqlite3.connect(overage) as db:
                db.execute("INSERT INTO budget_reservations VALUES (?,?,?,?,?,?)",
                           ("initial_over", 30000, "TOKENS_OBSERVED_COST_UNSETTLED", usage_json, estimate, None))
            _validate_database(overage)


if __name__ == "__main__":
    unittest.main()
