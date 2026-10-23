"""Durable P0 replay boundaries, using real SQLite and offline provider fixtures."""
import base64
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic
import unittest
from unittest.mock import patch

from manager_core import owned_provider_shadow as shadow
from manager_core.ampersand_api import initial_request_body_hash
from manager_core.collaboration import PublicFact
from manager_core.owned_checkpoint import PrivateCheckpoint, CheckpointUnavailable, _database_bytes
from manager_core.owned_provider import CheckpointedProvider
from test_owned_checkpoint import MemoryGateway, snapshot
import test_owned_provider_shadow as fixtures


def raw_database_bytes(path):
    """Include committed WAL mutations without validating deliberately bad fixtures."""
    with TemporaryDirectory() as tmp:
        target = Path(tmp) / "copy.sqlite"
        with sqlite3.connect(path) as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        return target.read_bytes()


def snapshot_rows(raw):
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "snapshot.sqlite"
        path.write_bytes(raw)
        with sqlite3.connect(path) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            def rows(table):
                return db.execute("SELECT * FROM " + table).fetchall() if table in tables else []
            return {name: rows(name) for name in
                    ("catalog_shadow_results", "amp_sessions", "budget_reservations")}


class ResultGateway(MemoryGateway):
    """Lose only the result save ACK, before or after applying remote state."""
    def __init__(self, raw, fail_result=None):
        super().__init__(raw)
        self.fail_result = fail_result
        self.checkpoints = []

    def __call__(self, payload):
        if payload["operation"] == "checkpoint":
            rows = snapshot_rows(base64.b64decode(payload["snapshot"]))
            self.checkpoints.append(rows)
            if rows["catalog_shadow_results"] and self.fail_result == "unapplied":
                raise OSError("test result save not applied")
            result = super().__call__(payload)
            if rows["catalog_shadow_results"] and self.fail_result == "applied":
                raise OSError("test result save ACK lost")
            return result
        return super().__call__(payload)


class CatalogShadowResultTests(unittest.TestCase):
    prepared_fixture = fixtures.OwnedProviderShadowTests.prepared_fixture

    def setup_owner(self, root, fail_result=None):
        prepared, _, now = self.prepared_fixture(root)
        raw, _ = snapshot(root / "seed")
        gateway = ResultGateway(raw, fail_result)
        cp = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
        cp.acquire(root / "run")
        return prepared, now, gateway, cp

    def compare(self, cp, prepared, comparison_now, **changes):
        kwargs = dict(now=comparison_now, run_id="123", enabled=True, deadline_monotonic=monotonic()+10)
        return shadow.compare_prepared_catalog_shadow(cp, prepared, **(kwargs | changes))

    def complete(self, cp, prepared, now, **client_kwargs):
        client, sessions = fixtures.client_for(**client_kwargs)
        first = self.compare(cp, prepared, now, client_factory=lambda: client,
            cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"))
        self.assertEqual(first["status"], "COMPARED_P0")
        return first, sessions

    def restore(self, root, gateway):
        gateway.value["owner"] = None  # Fixture lease expiry, never a production reset.
        cp = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
        cp.acquire(root)
        return cp

    def no_initialization(self):
        from contextlib import ExitStack
        stack = ExitStack()
        for target in ("manager_core.owned_provider.CheckpointedProvider.__init__",
                       "manager_core.owned_provider.BudgetLedger.__init__",
                       "manager_core.owned_provider_shadow.owned_catalog_planner.plan_catalog_change"):
            stack.enter_context(patch(target, side_effect=AssertionError("unexpected initialization")))
        return stack

    def test_completed_result_is_remote_acked_before_return(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, now, gateway, cp = self.setup_owner(root)
            def on_create():
                rows = snapshot_rows(base64.b64decode(gateway.value["snapshot"]))
                self.assertEqual(rows["amp_sessions"][0][2], "UNKNOWN")
                self.assertEqual(rows["budget_reservations"][0][2], "RESERVED")
                self.assertEqual(rows["catalog_shadow_results"], [])
            first, sessions = self.complete(cp, prepared, now, on_create=on_create)
            rows = snapshot_rows(base64.b64decode(gateway.value["snapshot"]))
            self.assertEqual(json.loads(rows["catalog_shadow_results"][0][2]), first)
            self.assertEqual(rows["amp_sessions"][0][2], "BOUND")
            self.assertEqual(rows["budget_reservations"][0][2], "TOKENS_OBSERVED_COST_UNSETTLED")
            self.assertFalse(gateway.checkpoints[-2]["catalog_shadow_results"])
            self.assertEqual(gateway.checkpoints[-2]["amp_sessions"][0][2], "BOUND")
            self.assertEqual(gateway.checkpoints[-2]["budget_reservations"][0][2],
                             "TOKENS_OBSERVED_COST_UNSETTLED")
            self.assertEqual(sessions.create_count, 1)

    def test_fresh_restore_replays_original_comparison_without_initialization(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, now, gateway, cp = self.setup_owner(root)
            first, sessions = self.complete(cp, prepared, now)
            restored = self.restore(root / "restored", gateway)
            before = deepcopy(gateway.value), list(gateway.calls)
            with self.no_initialization():
                replayed = self.compare(restored, prepared, now, run_id="999",
                    client_factory=lambda: self.fail("factory invoked"), cap_usd=None, upper_usd=None)
            self.assertEqual(replayed, first)
            self.assertEqual((replayed["run_id"], replayed["compared_at"]),
                             (first["run_id"], first["compared_at"]))
            self.assertEqual((gateway.value, gateway.calls), before)
            rows = snapshot_rows(_database_bytes(restored.db))
            self.assertEqual(len(rows["catalog_shadow_results"]), 1)
            self.assertEqual(len(rows["budget_reservations"]), 1)
            self.assertEqual(sessions.create_count, 1)

    def changed_prompt(self, prepared):
        context, assessment, scope = prepared
        sources = tuple(replace(source, retrieved_at=source.retrieved_at+timedelta(microseconds=1))
                        for source in context.criteria.official_sources)
        facts = tuple(PublicFact(source, fact.summary) for source, fact in zip(sources, context.planner.facts))
        changed = replace(context, criteria=replace(context.criteria, official_sources=sources),
                          planner=replace(context.planner, facts=facts))
        self.assertEqual(shadow._canonical_operation(context, assessment),
                         shadow._canonical_operation(changed, assessment))
        self.assertNotEqual(initial_request_body_hash(shadow.render_prompt(context.planner, fictional=False)),
                            initial_request_body_hash(shadow.render_prompt(changed.planner, fictional=False)))
        return changed, assessment, scope

    def test_changed_prompt_same_operation_is_unknown_without_create(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, now, gateway, cp = self.setup_owner(root)
            first, sessions = self.complete(cp, prepared, now)
            before = _database_bytes(cp.db), deepcopy(gateway.value)
            changed = self.changed_prompt(prepared)
            with self.no_initialization():
                result = self.compare(cp, changed, now, run_id="999",
                    client_factory=lambda: self.fail("factory invoked"))
            self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "INPUT_BINDING_MISMATCH"))
            self.assertNotIn("model_advice", result)
            self.assertNotIn("compared_at", result)
            self.assertEqual((_database_bytes(cp.db), gateway.value), before)
            self.assertEqual(self.compare(cp, prepared, now), first)
            self.assertEqual(sessions.create_count, 1)

    def test_intent_without_result_is_unknown_for_reserved_unknown_and_bound(self):
        for status in ("RESERVED", "UNKNOWN", "BOUND"):
            with self.subTest(status=status), TemporaryDirectory() as tmp:
                root = Path(tmp)
                prepared, now, gateway, cp = self.setup_owner(root)
                context, assessment, _ = prepared
                operation = shadow._canonical_operation(context, assessment)
                body = initial_request_body_hash(shadow.render_prompt(context.planner, fictional=False))
                owner = CheckpointedProvider(cp, cap_usd=Decimal("0.05"))
                owner.journal.begin(operation, body)
                with sqlite3.connect(cp.db) as db:
                    db.execute("UPDATE amp_sessions SET status=?,session_id=?",
                               (status, "sess_12345678" if status == "BOUND" else None))
                cp.save()
                before = _database_bytes(cp.db), deepcopy(gateway.value), list(gateway.calls)
                with self.no_initialization():
                    for value, reason in ((prepared, "PRIOR_INTENT_RECONCILIATION_REQUIRED"),
                                          (self.changed_prompt(prepared), "INPUT_BINDING_MISMATCH")):
                        result = self.compare(cp, value, now,
                            client_factory=lambda: self.fail("factory invoked"))
                        self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", reason))
                self.assertEqual((_database_bytes(cp.db), gateway.value, gateway.calls), before)
                self.assertEqual(snapshot_rows(_database_bytes(cp.db))["catalog_shadow_results"], [])

    def test_result_ack_loss_permanently_fences_without_success_or_retry(self):
        for mode in ("unapplied", "applied"):
            with self.subTest(mode=mode), TemporaryDirectory() as tmp:
                root = Path(tmp)
                prepared, now, gateway, cp = self.setup_owner(root, mode)
                client, sessions = fixtures.client_for()
                with self.assertRaises(CheckpointUnavailable):
                    self.compare(cp, prepared, now, client_factory=lambda: client,
                        cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"))
                self.assertTrue(cp.broken)
                local_rows = snapshot_rows(raw_database_bytes(cp.db))["catalog_shadow_results"]
                self.assertEqual(len(local_rows), 1)
                before = list(gateway.calls)
                for operation in (lambda: self.compare(cp, prepared, now), cp.save, cp.release):
                    with self.assertRaises(CheckpointUnavailable):
                        operation()
                self.assertEqual(gateway.calls, before)
                remote_rows = snapshot_rows(base64.b64decode(gateway.value["snapshot"]))
                self.assertEqual(len(remote_rows["catalog_shadow_results"]), int(mode == "applied"))
                restored = self.restore(root / "restored", gateway)
                with self.no_initialization():
                    replayed = self.compare(restored, prepared, now,
                        client_factory=lambda: self.fail("factory invoked"))
                if mode == "applied":
                    self.assertEqual(replayed, json.loads(local_rows[0][2]))
                else:
                    self.assertEqual((replayed["status"], replayed["reason"]),
                                     ("UNKNOWN", "PRIOR_INTENT_RECONCILIATION_REQUIRED"))
                self.assertEqual(sessions.create_count, 1)

    def test_old_snapshot_and_complete_optional_result_schema(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, now, gateway, cp = self.setup_owner(root)
            self.assertEqual(snapshot_rows(_database_bytes(cp.db))["catalog_shadow_results"], [])
            first, _ = self.complete(cp, prepared, now)
            restored = self.restore(root / "restored", gateway)
            self.assertEqual(self.compare(restored, prepared, now), first)
        for order in (("owned_checkpoint", "owned_provider_shadow"),
                      ("owned_provider_shadow", "owned_checkpoint")):
            with self.subTest(order=order):
                code = ("import importlib, sys\n"
                        "for name in " + repr(order) + ": importlib.import_module('manager_core.'+name)\n"
                        "assert not any(n == 'ampersand' or n.startswith('ampersand.') for n in sys.modules)\n")
                completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_corrupt_result_restore_fences_before_any_factory(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, now, gateway, cp = self.setup_owner(root)
            first, sessions = self.complete(cp, prepared, now)
            valid = _database_bytes(cp.db)
            json_changes = {
                "unknown_key": lambda r: r.update(raw_response="PRIVATE"),
                "operation": lambda r: r.update(operation_id="catalog_shadow_"+"a"*64),
                "session": lambda r: r["provider"].update(session_id="sess_different"),
                "turn": lambda r: r["provider"].update(turn_id="wrong"),
                "tokens": lambda r: r["provider"].update(input_tokens=11),
                "bool_tokens": lambda r: r["provider"].update(input_tokens=True),
                "oversized_tokens": lambda r: r["provider"].update(output_tokens=10**10+1),
                "unknown_tokens": lambda r: r["provider"].update(input_tokens=None),
                "decision": lambda r: r["model_comparison"].update(no_action_same_decision=True),
                "flags": lambda r: r.update(authorized_execution=True),
                "nested_flags": lambda r: r["model_advice"].update(causal_support=True),
                "numeric_flag": lambda r: r["model_advice"].update(authorized_execution=0),
                "nested_unknown_key": lambda r: r["model_advice"].update(raw_output="PRIVATE"),
                "candidate": lambda r: r["candidate"].update(packet={}),
                "source": lambda r: r["sources"][0].update(url="https://evil.example/"),
                "source_duplicate": lambda r: r["sources"].append(deepcopy(r["sources"][0])),
                "hash": lambda r: r.update(context_sha256="A"*64),
                "timestamp": lambda r: r.update(compared_at="2026-10-23T00:00:00"),
                "baseline_key": lambda r: r["baseline"].update(extra={}),
                "model_status": lambda r: r.update(model_status="INVALID_MODEL_OUTPUT"),
                "escaped_high_surrogate": lambda r: r["model_advice"].update(reason=chr(0xD800)),
                "escaped_low_surrogate": lambda r: r["model_advice"].update(reason=chr(0xDFFF)),
            }
            sql_changes = {
                "body": "UPDATE catalog_shadow_results SET body_hash='"+"a"*64+"'",
                "row_operation": "UPDATE catalog_shadow_results SET operation_id='catalog_shadow_"+"a"*64+"'",
                "intent_status": "UPDATE amp_sessions SET status='UNKNOWN',session_id=NULL",
                "budget_missing": "DELETE FROM budget_reservations",
                "budget_reserved": "UPDATE budget_reservations SET status='RESERVED',usage_json=NULL,measured_cost_units=NULL",
                "budget_settled": "UPDATE budget_reservations SET settled_units=0",
                "budget_unknown_complete_tokens": "UPDATE budget_reservations SET status='UNKNOWN_USAGE',usage_json=NULL,measured_cost_units=NULL",
                "provider_missing": "DROP TABLE amp_events",
            }
            schema_changes = {
                "missing_column": "operation_id TEXT PRIMARY KEY NOT NULL, body_hash TEXT NOT NULL",
                "missing_pk": "operation_id TEXT NOT NULL, body_hash TEXT NOT NULL, result_json TEXT NOT NULL, FOREIGN KEY(operation_id) REFERENCES amp_sessions(request_id)",
                "missing_fk": "operation_id TEXT PRIMARY KEY NOT NULL, body_hash TEXT NOT NULL, result_json TEXT NOT NULL",
                "nullable": "operation_id TEXT PRIMARY KEY, body_hash TEXT NOT NULL, result_json TEXT NOT NULL, FOREIGN KEY(operation_id) REFERENCES amp_sessions(request_id)",
                "wrong_type": "operation_id TEXT PRIMARY KEY NOT NULL, body_hash TEXT NOT NULL, result_json BLOB NOT NULL, FOREIGN KEY(operation_id) REFERENCES amp_sessions(request_id)",
                "wrong_fk": "operation_id TEXT PRIMARY KEY NOT NULL, body_hash TEXT NOT NULL, result_json TEXT NOT NULL, FOREIGN KEY(operation_id) REFERENCES amp_sessions(session_id)",
                "generated_column": "operation_id TEXT PRIMARY KEY NOT NULL, body_hash TEXT NOT NULL, result_json TEXT NOT NULL, extra TEXT GENERATED ALWAYS AS (result_json) VIRTUAL, FOREIGN KEY(operation_id) REFERENCES amp_sessions(request_id)",
            }
            kinds = list(json_changes) + list(sql_changes) + list(schema_changes) + ["duplicate_json", "nan", "oversize", "empty_without_provider"]
            for index, kind in enumerate(kinds):
                with self.subTest(kind=kind):
                    path = root / (str(index)+".sqlite")
                    path.write_bytes(valid)
                    with sqlite3.connect(path) as db:
                        if kind in json_changes:
                            changed = deepcopy(first)
                            json_changes[kind](changed)
                            db.execute("UPDATE catalog_shadow_results SET result_json=?", (json.dumps(changed),))
                        elif kind in sql_changes:
                            db.execute(sql_changes[kind])
                        elif kind in schema_changes:
                            db.execute("DROP TABLE catalog_shadow_results")
                            db.execute("CREATE TABLE catalog_shadow_results ("+schema_changes[kind]+")")
                        elif kind == "empty_without_provider":
                            db.execute("DELETE FROM catalog_shadow_results")
                            for table in ("amp_events", "amp_sessions", "budget_policy", "budget_reservations"):
                                db.execute("DROP TABLE "+table)
                        else:
                            text = json.dumps(first)
                            if kind == "duplicate_json": text = '{"status":"COMPARED_P0",'+text[1:]
                            elif kind == "nan": text = text.replace('"action_writes": 0', '"action_writes": NaN')
                            else: text = ' '*32769
                            db.execute("UPDATE catalog_shadow_results SET result_json=?", (text,))
                    bad_gateway = MemoryGateway(raw_database_bytes(path))
                    bad = PrivateCheckpoint(bad_gateway, run_id="123", run_attempt="1")
                    with self.no_initialization(), self.assertRaises(CheckpointUnavailable):
                        bad.acquire(root / ("bad"+str(index)))
                    self.assertTrue(bad.broken)
                    self.assertIsNone(bad.db)
            self.assertEqual(sessions.create_count, 1)


    def test_saved_input_binding_checks_all_six_fields_without_writes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, now, gateway, cp = self.setup_owner(root)
            first, sessions = self.complete(cp, prepared, now)
            fields = {key: deepcopy(first[key]) for key in (
                "operation_id", "context_sha256", "baseline_digest", "candidate_digest", "candidate", "sources")}
            body = initial_request_body_hash(shadow.render_prompt(prepared[0].planner, fictional=False))
            before = _database_bytes(cp.db), deepcopy(gateway.value), list(gateway.calls)
            for key in fields:
                expected = deepcopy(fields)
                if key == "candidate":
                    expected[key]["action"] = "IMPROVE_ACCESSIBILITY"
                elif key == "sources":
                    expected[key][0]["content_sha256"] = "a"*64
                elif key == "operation_id":
                    expected[key] = "catalog_shadow_"+"a"*64
                else:
                    expected[key] = "a"*64
                with self.subTest(key=key), self.no_initialization():
                    result = shadow._read_saved_comparison(cp, operation_id=first["operation_id"],
                        body_hash=body, expected_fields=expected)
                    self.assertEqual((result["status"], result["reason"]),
                                     ("UNKNOWN", "INPUT_BINDING_MISMATCH"))
            self.assertEqual((_database_bytes(cp.db), gateway.value, gateway.calls), before)
            self.assertEqual(sessions.create_count, 1)

    def test_result_json_byte_limit_and_canonical_storage(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, now, gateway, cp = self.setup_owner(root)
            first, sessions = self.complete(cp, prepared, now,
                output='{"decision":"PROPOSE","reason":"公式リンクを修正。","source_ids":["official:livelihood"]}')
            with sqlite3.connect(cp.db) as db:
                body, text = db.execute("SELECT body_hash,result_json FROM catalog_shadow_results").fetchone()
            self.assertEqual(text, json.dumps(first, sort_keys=True, separators=(",", ":"),
                                              ensure_ascii=False, allow_nan=False))
            self.assertIn("公式", text)
            self.assertLess(len(text), len(text.encode("utf-8")))
            padded = text + " "*(32768-len(text.encode("utf-8")))
            self.assertEqual(len(padded.encode("utf-8")), 32768)
            with sqlite3.connect(cp.db) as db:
                db.execute("UPDATE catalog_shadow_results SET result_json=?", (padded,))
            self.assertEqual(self.compare(cp, prepared, now), first)
            with sqlite3.connect(cp.db) as db:
                db.execute("UPDATE catalog_shadow_results SET result_json=?", (padded+" ",))
            with self.no_initialization(), self.assertRaises(CheckpointUnavailable):
                self.compare(cp, prepared, now)
            self.assertTrue(cp.broken)
            self.assertEqual(sessions.create_count, 1)

    def test_reserved_result_name_non_table_objects_fence_restore_and_local_read(self):
        statements = {
            "view": "CREATE VIEW catalog_shadow_results AS SELECT 1 AS operation_id",
            "uppercase_view": "CREATE VIEW CATALOG_SHADOW_RESULTS AS SELECT 1 AS operation_id",
            "index": "CREATE INDEX catalog_shadow_results ON control(stopped)",
            "trigger": "CREATE TRIGGER catalog_shadow_results AFTER UPDATE ON control BEGIN SELECT 1; END",
        }
        for kind, statement in statements.items():
            with self.subTest(kind=kind), TemporaryDirectory() as tmp:
                root = Path(tmp)
                prepared, now, gateway, cp = self.setup_owner(root)
                client, sessions = fixtures.client_for()
                with sqlite3.connect(cp.db) as db:
                    db.execute(statement)
                # An already acquired checkpoint must not classify this as a cache miss.
                with self.no_initialization(), self.assertRaisesRegex(
                        CheckpointUnavailable, "^invalid private provider state; reconcile only$"):
                    self.compare(cp, prepared, now, client_factory=lambda: self.fail("factory invoked"),
                                 cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"))
                self.assertTrue(cp.broken)
                bad_gateway = MemoryGateway(raw_database_bytes(cp.db))
                restored = PrivateCheckpoint(bad_gateway, run_id="123", run_attempt="1")
                with self.no_initialization(), self.assertRaisesRegex(
                        CheckpointUnavailable, "^checkpoint restore refused; reconcile only$"):
                    restored.acquire(root / "bad_restore")
                self.assertTrue(restored.broken)
                self.assertIsNone(restored.db)
                self.assertEqual(sessions.create_count, 0)
                self.assertNotIn("checkpoint", gateway.calls)

    def test_corrupt_local_saved_result_fences_instead_of_cache_miss(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, now, _, cp = self.setup_owner(root)
            self.complete(cp, prepared, now)
            with sqlite3.connect(cp.db) as db:
                db.execute("UPDATE catalog_shadow_results SET result_json='{}'")
            with self.no_initialization(), self.assertRaises(CheckpointUnavailable):
                self.compare(cp, prepared, now, client_factory=lambda: self.fail("factory invoked"))
            self.assertTrue(cp.broken)

    def test_expired_scope_or_deadline_cannot_turn_cached_propose_into_authority(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, now, gateway, cp = self.setup_owner(root)
            first, sessions = self.complete(cp, prepared, now)
            self.assertEqual(first["model_advice"]["decision"], "PROPOSE")
            before = deepcopy(gateway.value), list(gateway.calls)
            with self.no_initialization():
                for changes, reason in (({"now": prepared[2].expires_at}, "CONTEXT_REVALIDATION_FAILED"),
                                        ({"deadline_monotonic": monotonic()-1}, "DEADLINE_EXPIRED")):
                    result = self.compare(cp, prepared, now,
                        **(dict(client_factory=lambda: self.fail("factory invoked")) | changes))
                    self.assertEqual((result["status"], result["reason"]), ("SKIPPED", reason))
                    self.assertFalse(result["authorized_execution"])
                    self.assertEqual(result["action_writes"], 0)
                    self.assertNotIn("packet", result)
                public = shadow.public_catalog_shadow_summary(self.compare(cp, prepared, now))
                self.assertEqual(public["run_id"], first["run_id"])
                self.assertEqual(public["proof_level"], "P0")
                self.assertFalse(public["authorized_execution"])
                self.assertEqual(public["action_writes"], 0)
                for secret in ("Repair the cited link.", "sess_", "turn_", "model_advice"):
                    self.assertNotIn(secret, json.dumps(public))
            self.assertEqual((gateway.value, gateway.calls), before)
            self.assertEqual(sessions.create_count, 1)

    def test_partial_token_usage_is_durable_without_invented_cost(self):
        from types import SimpleNamespace
        for input_tokens, output_tokens in ((10, None), (None, 20), (0, None), (None, 0)):
            with self.subTest(tokens=(input_tokens, output_tokens)), TemporaryDirectory() as tmp:
                root = Path(tmp)
                prepared, now, gateway, cp = self.setup_owner(root)
                client, sessions = fixtures.client_for()
                usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                                        input_tokens_details=None, output_tokens_details=None)
                client.beta.agents.sessions.turns = SimpleNamespace(list=lambda *a, **k:
                    SimpleNamespace(data=[SimpleNamespace(id="turn_12345678", status="completed", usage=usage)]))
                try:
                    first = self.compare(cp, prepared, now, client_factory=lambda: client,
                        cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"))
                except CheckpointUnavailable:
                    self.fail("legitimate partial token evidence fenced the checkpoint")
                self.assertEqual(first["status"], "COMPARED_P0")
                self.assertFalse(cp.broken)
                self.assertEqual((first["provider"]["input_tokens"], first["provider"]["output_tokens"]),
                                 (input_tokens, output_tokens))
                self.assertIsNone(first["settled_cost_usd"])
                rows = snapshot_rows(base64.b64decode(gateway.value["snapshot"]))
                self.assertEqual(json.loads(rows["catalog_shadow_results"][0][2]), first)
                self.assertEqual(rows["budget_reservations"][0][2:],
                                 ("UNKNOWN_USAGE", None, None, None))
                restored = self.restore(root / "restored", gateway)
                before = deepcopy(gateway.value), list(gateway.calls), _database_bytes(restored.db)
                with self.no_initialization():
                    replayed = self.compare(restored, prepared, now, run_id="999",
                        client_factory=lambda: self.fail("factory invoked"))
                self.assertEqual(replayed, first)
                self.assertEqual((replayed["run_id"], replayed["compared_at"]),
                                 (first["run_id"], first["compared_at"]))
                self.assertEqual((gateway.value, gateway.calls, _database_bytes(restored.db)), before)
                self.assertEqual(len(snapshot_rows(_database_bytes(restored.db))["budget_reservations"]), 1)
                self.assertEqual(sessions.create_count, 1)

    def test_unencodable_model_advice_is_durable_invalid_output(self):
        for name, reason, model_status in (
                ("high", chr(0xD800), "INVALID_MODEL_OUTPUT"),
                ("low", chr(0xDFFF), "INVALID_MODEL_OUTPUT"),
                ("valid_unicode", "公式リンクを修正します。😀", "MODEL_ADVICE_P0")):
            with self.subTest(kind=name), TemporaryDirectory() as tmp:
                root = Path(tmp)
                prepared, now, gateway, cp = self.setup_owner(root)
                output = json.dumps({"decision": "PROPOSE", "reason": reason,
                                     "source_ids": ["official:livelihood"]}, ensure_ascii=True)
                client, sessions = fixtures.client_for(output=output)
                try:
                    first = self.compare(cp, prepared, now, client_factory=lambda: client,
                        cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"))
                except CheckpointUnavailable:
                    self.fail("unencodable model advice fenced instead of saving INVALID_MODEL_OUTPUT")
                self.assertEqual(first["status"], "COMPARED_P0")
                self.assertEqual(first["model_status"], model_status)
                self.assertFalse(cp.broken)
                rows = snapshot_rows(base64.b64decode(gateway.value["snapshot"]))
                saved = rows["catalog_shadow_results"][0][2]
                self.assertEqual(json.loads(saved), first)
                self.assertEqual(rows["budget_reservations"][0][2], "TOKENS_OBSERVED_COST_UNSETTLED")
                public = shadow.public_catalog_shadow_summary(first)
                self.assertNotIn("model_advice", public)
                self.assertNotIn(reason, json.dumps(public, ensure_ascii=False))
                if model_status == "INVALID_MODEL_OUTPUT":
                    self.assertIsNone(first["model_comparison"])
                    self.assertNotIn("model_advice", first)
                    self.assertNotIn(reason, saved)
                    self.assertNotIn(json.dumps(reason)[1:-1], saved)
                else:
                    self.assertEqual(first["model_advice"]["reason"], reason)
                    self.assertIn(reason, saved)
                restored = self.restore(root / "restored", gateway)
                before = deepcopy(gateway.value), list(gateway.calls)
                with self.no_initialization():
                    self.assertEqual(self.compare(restored, prepared, now, run_id="999",
                        client_factory=lambda: self.fail("factory invoked")), first)
                self.assertEqual((gateway.value, gateway.calls), before)
                self.assertEqual(sessions.create_count, 1)

    def test_invalid_model_output_and_unknown_usage_are_durable_p0(self):
        for unknown_usage in (False, True):
            with self.subTest(unknown_usage=unknown_usage), TemporaryDirectory() as tmp:
                root = Path(tmp)
                prepared, now, gateway, cp = self.setup_owner(root)
                client, sessions = fixtures.client_for(output='PRIVATE invalid raw output')
                if unknown_usage:
                    from types import SimpleNamespace
                    client.beta.agents.sessions.turns = SimpleNamespace(list=lambda *a, **k:
                        SimpleNamespace(data=[SimpleNamespace(id="turn_12345678",status="completed",usage=None)]))
                first = self.compare(cp, prepared, now, client_factory=lambda: client,
                    cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"))
                self.assertEqual(first["model_status"], "INVALID_MODEL_OUTPUT")
                self.assertIsNone(first["model_comparison"])
                self.assertNotIn("model_advice", first)
                self.assertNotIn("PRIVATE", json.dumps(first))
                if unknown_usage:
                    self.assertIsNone(first["provider"]["input_tokens"])
                    self.assertIsNone(first["provider"]["output_tokens"])
                restored = self.restore(root / "restored", gateway)
                with self.no_initialization():
                    self.assertEqual(self.compare(restored, prepared, now), first)
                self.assertEqual(sessions.create_count, 1)
