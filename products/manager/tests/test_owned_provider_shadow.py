"""Offline public catalog shadow contract tests over the existing owner components."""
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from dataclasses import replace
from time import monotonic
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from manager_core.digital_environment import PAGES, build_site
from manager_core.collaboration import PlannerContext, PublicFact
from manager_core.candidate_verification import TechnicalCriteria, verify_candidate
from manager_core.digital_handoff import OwnedChangeContext
from manager_core.models.source import Source
from manager_core import owned_catalog_planner as planner
from manager_core.owned_checkpoint import PrivateCheckpoint, CheckpointUnavailable
from test_owned_checkpoint import MemoryGateway, snapshot

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "c" * 40


def make_catalog_fixture(root, shape="link"):
    """Real planner fixture with only source/browser network seams replaced."""
    checkout = root / "checkout"
    bundle = checkout / "manager-support"
    catalog = json.loads((ROOT / "public_goods/service/catalog.json").read_text())
    build_site(catalog, bundle, SOURCE_COMMIT)
    page = bundle / "finance.html"
    body = page.read_text()
    row = next(r for r in catalog["resources"] if r["id"] == "livelihood")
    if shape == "link":
        body = body.replace(row["url"], "https://www.mhlw.go.jp/old-route", 1)
    elif shape == "label":
        body = body.replace(f'>{row["title"]}</a>', '></a>', 1)
    page.write_text(body)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["finance.html"] = sha256(page.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    served = (manifest, {p: (bundle / p).read_bytes() for p in PAGES}, manifest_path.read_bytes())
    observed = datetime.now(timezone.utc).isoformat()
    rows = [{"id": r["id"], "url": r["url"], "final_url": r["url"],
             "status": "REACHABLE_NOT_OUTCOME", "http_status": 200,
             "sha256": sha256(r["id"].encode()).hexdigest(), "observed_at": observed}
            for r in catalog["resources"]]
    patches = [patch.object(planner, "_read_served_bundle", return_value=served),
               patch.object(planner, "audit_sources", return_value={"sources": rows}),
               patch.object(planner, "verify_candidate_in_browser", return_value={"status": "P0_BROWSER_FIXTURE"}),
               patch.dict("os.environ", {"MANAGER_RELEASE_ENABLED": "true"})]
    return checkout, root / "private", patches


def client_for(output='{"decision":"PROPOSE","reason":"Repair the cited link.","source_ids":["official:livelihood"]}',
               on_create=None, create_error=None):
    class Stream:
        def with_result_collection(self): return self
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def __iter__(self):
            yield SimpleNamespace(type="agent.session.created", session_id="sess_12345678")
            yield SimpleNamespace(type="agent.session.idle")
        def get_final_result(self): return SimpleNamespace(session_id="sess_12345678", output_text=output,
                                                           turn_id="turn_12345678")
    class Sessions:
        create_count = 0
        def create(self, **kwargs):
            self.create_count += 1
            if on_create: on_create()
            if create_error: raise create_error
            return Stream()
        class turns:
            @staticmethod
            def list(*args, **kwargs):
                return SimpleNamespace(data=[SimpleNamespace(id="turn_12345678", status="completed",
                    usage=SimpleNamespace(input_tokens=10, output_tokens=20,
                        input_tokens_details=None, output_tokens_details=None))])
    sessions = Sessions()
    return SimpleNamespace(beta=SimpleNamespace(agents=SimpleNamespace(sessions=sessions))), sessions


class OwnedProviderShadowTests(unittest.TestCase):
    def prepared_fixture(self, root):
        checkout, workspace, patches = make_catalog_fixture(root)
        now = datetime.now(timezone.utc)
        with patches[0], patches[1], patches[2], patches[3]:
            prepared = planner.plan_catalog_change(checkout, workspace, SOURCE_COMMIT,
                                                  now, run_id="123")
        self.assertIsNotNone(prepared)
        return prepared, workspace, datetime.now(timezone.utc)

    def test_prepared_shadow_never_replans(self):
        from manager_core import owned_provider_shadow as shadow
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, workspace, now = self.prepared_fixture(root)
            before = {str(p.relative_to(workspace)): p.read_bytes()
                      for name in ("baseline", "candidate")
                      for p in (workspace / name).iterdir() if p.is_file()}
            _, checkpoint = self.owner(root)
            client, sessions = client_for()
            with patch.object(planner, "plan_catalog_change", side_effect=AssertionError("replanned")):
                result = shadow.compare_prepared_catalog_shadow(checkpoint, prepared,
                    now=now, run_id="123", enabled=True, client_factory=lambda: client,
                    cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertEqual(result["status"], "COMPARED_P0")
            self.assertEqual(sessions.create_count, 1)
            self.assertEqual(before, {str(p.relative_to(workspace)): p.read_bytes()
                for name in ("baseline", "candidate")
                for p in (workspace / name).iterdir() if p.is_file()})
            compared_at = datetime.fromisoformat(result["compared_at"])
            self.assertEqual(compared_at.utcoffset(), timedelta(0))
            self.assertLessEqual(now, compared_at)

    def test_initial_request_hash_preserves_existing_journal_identity(self):
        from manager_core import ampersand_api as api
        from manager_core.provider_sessions import SessionJournal
        prompt = "公開資料を比較してください。"
        canonical = json.dumps({"model": api.MODEL, "instructions": api.DEFAULT_INSTRUCTIONS,
            "input": prompt, "environment": {"type": "none"}}, ensure_ascii=False,
            sort_keys=True, separators=(",", ":")).encode("utf8")
        with TemporaryDirectory() as tmp:
            journal = SessionJournal(Path(tmp) / "journal.sqlite")
            client, sessions = client_for()
            api.read_initial_turn(client, prompt, journal=journal, request_id="hash_test")
            self.assertEqual(api.initial_request_body_hash(prompt), sha256(canonical).hexdigest())
            self.assertEqual(journal.get("hash_test").body_hash, api.initial_request_body_hash(prompt))
            self.assertNotEqual(api.initial_request_body_hash(prompt, "Other instructions"),
                                api.initial_request_body_hash(prompt))
            self.assertEqual(sessions.create_count, 1)

    def test_prepared_disabled_invalid_scope_deadline_and_unsupported_do_not_initialize_provider(self):
        from manager_core import owned_provider_shadow as shadow
        with patch.object(shadow, "CheckpointedProvider", side_effect=AssertionError("provider initialized")):
            result = shadow.compare_prepared_catalog_shadow(None, object(), now=None,
                run_id=None, enabled=False, client_factory=object(), cap_usd="bad",
                upper_usd="bad", deadline_monotonic=None)
            self.assertEqual((result["status"], result["reason"]), ("SKIPPED", "DISABLED"))
            with self.assertRaises(ValueError):
                shadow.compare_prepared_catalog_shadow(None, None, now=None, run_id="123",
                    enabled=1, deadline_monotonic=monotonic()+10)
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                prepared, _, now = self.prepared_fixture(root)
                context, assessment, scope = prepared
                _, checkpoint = self.owner(root)
                client, sessions = client_for()
                factory_calls = []
                def factory():
                    factory_calls.append(True)
                    return client
                kwargs = dict(now=now, run_id="123", enabled=True, client_factory=factory,
                    cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
                cases = [(None, {}, "NO_CANDIDATE"), ("cue", {}, "UNSUPPORTED_CONTEXT"),
                    ((context, assessment, object()), {}, "UNSUPPORTED_CONTEXT"),
                    ((replace(context, criteria=object()), assessment, scope), {}, "UNSUPPORTED_ACTION"),
                    (prepared, {"now": scope.expires_at}, "CONTEXT_REVALIDATION_FAILED"),
                    (prepared, {"deadline_monotonic": monotonic()-1}, "DEADLINE_EXPIRED")]
                for value, changes, reason in cases:
                    with self.subTest(reason=reason):
                        result = shadow.compare_prepared_catalog_shadow(checkpoint, value, **(kwargs | changes))
                        self.assertEqual((result["status"], result["reason"]), ("SKIPPED", reason))
                invalid = [{"enabled": 1}, {"run_id": "0"}, {"run_id": 123},
                    {"now": now.replace(tzinfo=None)}, {"deadline_monotonic": float("nan")},
                    {"deadline_monotonic": True}, {"cap_usd": Decimal("NaN")},
                    {"upper_usd": Decimal("Infinity")}, {"cap_usd": 1},
                    {"upper_usd": Decimal("0")}, {"cap_usd": Decimal("100.000001")},
                    {"upper_usd": Decimal("0.0000001")}, {"client_factory": "bad"}]
                for changes in invalid:
                    with self.subTest(changes=changes), self.assertRaises(ValueError):
                        shadow.compare_prepared_catalog_shadow(checkpoint, prepared, **(kwargs | changes))
                result = shadow.compare_prepared_catalog_shadow(checkpoint, prepared,
                    **(kwargs | {"client_factory": None, "cap_usd": None, "upper_usd": None}))
                self.assertEqual(result["reason"], "PROVIDER_NOT_CONFIGURED")
                with self.assertRaises(CheckpointUnavailable):
                    shadow.compare_prepared_catalog_shadow(None, prepared, **kwargs)
                self.assertEqual(factory_calls, [])
                self.assertEqual(sessions.create_count, 0)

    def test_prepared_prior_intent_does_not_initialize_provider_or_require_send_configuration(self):
        from manager_core import owned_provider_shadow as shadow
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, _, now = self.prepared_fixture(root)
            _, checkpoint = self.owner(root)
            client, sessions = client_for()
            kwargs = dict(now=now, run_id="123", enabled=True, deadline_monotonic=monotonic()+10)
            first = shadow.compare_prepared_catalog_shadow(checkpoint, prepared,
                client_factory=lambda: client, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"), **kwargs)
            calls = []
            with patch.object(shadow, "CheckpointedProvider", side_effect=AssertionError("initialized")):
                prior = shadow.compare_prepared_catalog_shadow(checkpoint, prepared,
                    client_factory=lambda: calls.append(True), **kwargs)
            self.assertEqual(prior["reason"], "PRIOR_INTENT_RECONCILIATION_REQUIRED")
            self.assertEqual(prior["operation_id"], first["operation_id"])
            self.assertEqual(calls, [])
            self.assertEqual(sessions.create_count, 1)

    def test_prepared_provider_state_read_failure_fences_without_repair_or_create(self):
        from manager_core import owned_provider_shadow as shadow
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, _, now = self.prepared_fixture(root)
            _, checkpoint = self.owner(root)
            with sqlite3.connect(checkpoint.db) as db:
                db.execute("CREATE TABLE amp_sessions (private_marker TEXT)")
            client, sessions = client_for()
            calls = []
            with patch.object(shadow, "CheckpointedProvider", side_effect=AssertionError("initialized")), \
                    self.assertRaisesRegex(CheckpointUnavailable,
                        "^invalid private provider state; reconcile only$"):
                shadow.compare_prepared_catalog_shadow(checkpoint, prepared, now=now, run_id="123",
                    enabled=True, client_factory=lambda: calls.append(True) or client,
                    cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertTrue(checkpoint.broken)
            with sqlite3.connect(checkpoint.db) as db:
                self.assertEqual([row[1] for row in db.execute("PRAGMA table_info(amp_sessions)")],
                                 ["private_marker"])
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='budget_policy'").fetchone())
            self.assertEqual(calls, [])
            self.assertEqual(sessions.create_count, 0)

    def test_prepared_factory_failure_is_static_and_creates_no_provider_state(self):
        from manager_core import owned_provider_shadow as shadow
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepared, _, now = self.prepared_fixture(root)
            _, checkpoint = self.owner(root)
            def factory():
                raise OSError("PRIVATE_FACTORY_ERROR")
            with patch.object(shadow, "CheckpointedProvider", side_effect=AssertionError("initialized")):
                result = shadow.compare_prepared_catalog_shadow(checkpoint, prepared, now=now,
                    run_id="123", enabled=True, client_factory=factory, cap_usd=Decimal("0.05"),
                    upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            self.assertEqual((result["status"], result["reason"]), ("UNKNOWN", "PROVIDER_TRANSPORT_UNKNOWN"))
            self.assertNotIn("PRIVATE_FACTORY_ERROR", json.dumps(result))
            with sqlite3.connect(checkpoint.db) as db:
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='amp_sessions'").fetchone())

    def test_public_projection_is_fixed_and_never_echoes_private_fields(self):
        from manager_core import owned_provider_shadow as shadow
        keys = {"schema", "status", "reason", "run_id", "compared_at", "operation_id",
            "context_sha256", "baseline_digest", "candidate_digest", "baseline_decisions",
            "model_status", "model_decision", "model_comparison", "proof_level",
            "authorized_execution", "causal_support", "human_outcome", "action_writes", "settled_cost_usd"}
        with TemporaryDirectory() as tmp:
            result, _, _, _, _ = self.run_shadow(Path(tmp))
            result["model_advice"]["reason"] = "PRIVATE_REASON_MARKER"
            result["provider"]["session_id"] = "PRIVATE_PROVIDER_MARKER"
            result["unknown"] = "PRIVATE_UNKNOWN_MARKER"
            public = shadow.public_catalog_shadow_summary(result)
            self.assertEqual(set(public), keys)
            self.assertNotIn("PRIVATE_", json.dumps(public))
            self.assertEqual(public["baseline_decisions"], {"no_action": "PASS", "rules": "PROPOSE"})
            self.assertEqual(public["model_decision"], "PROPOSE")
            for changes in ({"reason": "PRIVATE_REASON"}, {"authorized_execution": True},
                    {"action_writes": False}, {"settled_cost_usd": 0},
                    {"context_sha256": "PRIVATE_HASH"}, {"run_id": "0"},
                    {"compared_at": "PRIVATE_TIME"}, {"model_status": "PASS"},
                    {"model_comparison": {"rules_same_decision": 1}}):
                with self.subTest(changes=changes), self.assertRaisesRegex(
                        ValueError, "^invalid catalog shadow record$"):
                    shadow.public_catalog_shadow_summary(result | changes)
            invalid = result | {"model_status": "INVALID_MODEL_OUTPUT"}
            invalid.pop("model_advice")
            invalid["model_comparison"] = None
            public = shadow.public_catalog_shadow_summary(invalid)
            self.assertEqual(public["model_status"], "INVALID_MODEL_OUTPUT")
            self.assertIsNone(public["model_decision"])
            self.assertEqual(public["model_comparison"],
                {"no_action_same_decision": None, "rules_same_decision": None})
            skipped = shadow.public_catalog_shadow_summary(shadow._record("SKIPPED", "DISABLED", "123"))
            self.assertEqual(set(skipped), keys)
            self.assertIsNone(skipped["compared_at"])
            self.assertEqual(skipped["baseline_decisions"], {"no_action": None, "rules": None})

    def owner(self, root, cap=Decimal("0.05")):
        raw, _ = snapshot(root / "seed")
        gateway = MemoryGateway(raw)
        checkpoint = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
        checkpoint.acquire(root / "run")
        return gateway, checkpoint

    def run_shadow(self, root, **kwargs):
        from manager_core.owned_provider_shadow import run_catalog_shadow
        checkout, default_workspace, fixture_patches = make_catalog_fixture(root)
        workspace = kwargs.pop("workspace", default_workspace)
        gateway, checkpoint = self.owner(root)
        output = kwargs.pop("output", None)
        if output is None:
            output = '{"decision":"PROPOSE","reason":"Repair the cited link.","source_ids":["official:livelihood"]}'
        client, sessions = client_for(output, on_create=kwargs.pop("on_create", None), create_error=kwargs.pop("create_error", None))
        with fixture_patches[0], fixture_patches[1], fixture_patches[2], fixture_patches[3]:
            result = run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                run_id=kwargs.pop("run_id", "123"), enabled=kwargs.pop("enabled", True),
                cap_usd=kwargs.pop("cap_usd", Decimal("0.05")), upper_usd=kwargs.pop("upper_usd", Decimal("0.03")),
                deadline_monotonic=kwargs.pop("deadline_monotonic", monotonic()+10), **kwargs)
        return result, gateway, checkpoint, sessions, workspace

    def test_disabled_is_cheap_noop_and_exact_boolean_is_required(self):
        from manager_core.owned_provider_shadow import run_catalog_shadow
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            client, sessions = client_for()
            result = run_catalog_shadow(None, client, None, None, None, run_id="1", enabled=False,
                cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
            self.assertEqual(result["status"], "SKIPPED")
            self.assertEqual(sessions.create_count, 0)
            with self.assertRaises(ValueError):
                run_catalog_shadow(None, client, None, None, None, run_id="1", enabled=1,
                    cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)

    def test_eligible_legacy_link_comparison_is_p0_and_non_executable(self):
        with TemporaryDirectory() as tmp:
            result, gateway, checkpoint, sessions, _ = self.run_shadow(Path(tmp))
            self.assertEqual(result["status"], "COMPARED_P0")
            self.assertEqual(result["candidate"]["action"], "CORRECT_LINK")
            self.assertEqual(result["model_advice"]["decision"], "PROPOSE")
            self.assertEqual(result["proof_level"], "P0")
            self.assertFalse(result["authorized_execution"])
            self.assertFalse(result["causal_support"])
            self.assertEqual(result["human_outcome"], "NOT_MEASURED")
            self.assertEqual(result["action_writes"], 0)
            self.assertIsNone(result["settled_cost_usd"])
            self.assertEqual(sessions.create_count, 1)
            self.assertGreaterEqual(gateway.calls.count("checkpoint"), 5)

    def test_operation_id_reused_across_run_ids_and_observation_times(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, gateway, checkpoint, sessions, _ = self.run_shadow(root, run_id="123")
            checkpoint.release()
            next_cp = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
            next_cp.acquire(root / "run2")
            checkout, workspace, fixture_patches = make_catalog_fixture(root / "other")
            client2, sessions2 = client_for()
            from manager_core.owned_provider_shadow import run_catalog_shadow
            with fixture_patches[0], fixture_patches[1], fixture_patches[2], fixture_patches[3]:
                second = run_catalog_shadow(next_cp, client2, checkout, workspace, SOURCE_COMMIT,
                    run_id="999", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertEqual(first["operation_id"], second["operation_id"])
            self.assertEqual(second["status"], "SKIPPED")
            self.assertIn("PRIOR_INTENT", second["reason"])
            self.assertEqual(sessions.create_count, 1)
            self.assertEqual(sessions2.create_count, 0)

    def test_elapsed_deadline_and_budget_exhaustion_do_not_send(self):
        with TemporaryDirectory() as tmp:
            result, _, _, sessions, _ = self.run_shadow(Path(tmp), deadline_monotonic=monotonic()-1)
            self.assertEqual(result["status"], "SKIPPED")
            self.assertEqual(sessions.create_count, 0)
        with TemporaryDirectory() as tmp:
            result, _, _, sessions, _ = self.run_shadow(Path(tmp), cap_usd=Decimal("0.01"), upper_usd=Decimal("0.03"))
            self.assertEqual(result["status"], "SKIPPED")
            self.assertEqual(sessions.create_count, 0)

    def test_invalid_json_stays_invalid_model_output_and_transport_is_unknown(self):
        with TemporaryDirectory() as tmp:
            result, _, _, _, _ = self.run_shadow(Path(tmp), output="not json")
            self.assertEqual(result["status"], "COMPARED_P0")
            self.assertEqual(result["model_status"], "INVALID_MODEL_OUTPUT")
        with TemporaryDirectory() as tmp:
            result, _, _, _, _ = self.run_shadow(Path(tmp), output="")
            # The provider adapter classifies an empty turn as transport uncertainty.
            self.assertEqual(result["status"], "UNKNOWN")

    def test_planner_failure_is_unknown_and_never_calls_provider(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout, workspace, fixture_patches = make_catalog_fixture(root)
            gateway, checkpoint = self.owner(root)
            client, sessions = client_for()
            from manager_core import owned_provider_shadow as shadow
            with patch.object(shadow.owned_catalog_planner, "plan_catalog_change", side_effect=planner.CatalogPlanningUnavailable):
                result = shadow.run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                    run_id="123", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(sessions.create_count, 0)

    def test_checkpoint_ack_loss_propagates_and_fences_before_provider(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway, checkpoint = self.owner(root)
            gateway.lose_ack = True
            checkout, workspace, fixture_patches = make_catalog_fixture(root)
            client, sessions = client_for()
            from manager_core.owned_provider_shadow import run_catalog_shadow
            with fixture_patches[0], fixture_patches[1], fixture_patches[2], fixture_patches[3], self.assertRaises(CheckpointUnavailable):
                run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                    run_id="123", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertTrue(checkpoint.broken)
            self.assertEqual(sessions.create_count, 0)

    def test_no_candidate_and_current_page_cue_are_never_sent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout, workspace, patches = make_catalog_fixture(root)
            gateway, checkpoint = self.owner(root)
            client, sessions = client_for()
            from manager_core import owned_provider_shadow as shadow
            with patch.object(shadow.owned_catalog_planner, "plan_catalog_change", return_value=None):
                result = shadow.run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                    run_id="123", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertEqual(result["status"], "SKIPPED")
            self.assertEqual(sessions.create_count, 0)
            with patch.object(shadow.owned_catalog_planner, "plan_catalog_change", return_value="current-page cue"):
                result = shadow.run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                    run_id="123", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertEqual(result["status"], "SKIPPED")
            self.assertEqual(sessions.create_count, 0)


    def test_first_send_is_after_unknown_intent_and_budget_ack(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout, workspace, fixture_patches = make_catalog_fixture(root)
            gateway, checkpoint = self.owner(root)
            seen = []
            def on_create():
                raw = base64.b64decode(gateway.value["snapshot"])
                db_path = root / "checkpoint-at-create.sqlite"
                db_path.write_bytes(raw)
                with sqlite3.connect(db_path) as db:
                    seen.append((db.execute("SELECT status FROM amp_sessions").fetchone()[0],
                                 db.execute("SELECT status FROM budget_reservations").fetchone()[0]))
            client, sessions = client_for(on_create=on_create)
            from manager_core.owned_provider_shadow import run_catalog_shadow
            with fixture_patches[0], fixture_patches[1], fixture_patches[2], fixture_patches[3]:
                result = run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                    run_id="123", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertEqual(result["status"], "COMPARED_P0")
            self.assertEqual(seen, [("UNKNOWN", "RESERVED")])
            self.assertEqual(sessions.create_count, 1)

    def test_accessibility_candidate_is_supported_and_source_audit_failure_stays_unknown(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout, workspace, fixture_patches = make_catalog_fixture(root, shape="label")
            gateway, checkpoint = self.owner(root)
            client, sessions = client_for()
            from manager_core.owned_provider_shadow import run_catalog_shadow
            with fixture_patches[0], fixture_patches[1], fixture_patches[2], fixture_patches[3]:
                result = run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                    run_id="123", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertEqual(result["status"], "COMPARED_P0")
            self.assertEqual(result["candidate"]["action"], "IMPROVE_ACCESSIBILITY")
            self.assertEqual(sessions.create_count, 1)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout, workspace, fixture_patches = make_catalog_fixture(root)
            gateway, checkpoint = self.owner(root)
            client, sessions = client_for()
            from manager_core.owned_provider_shadow import run_catalog_shadow
            with fixture_patches[0], patch.object(planner, "audit_sources", side_effect=OSError("private raw error")):
                result = run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                    run_id="123", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=monotonic()+10)
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["reason"], "PLANNER_UNCERTAIN")
            self.assertNotIn("private raw error", json.dumps(result))
            self.assertEqual(sessions.create_count, 0)

    def test_transport_uncertainty_is_unknown_and_never_echoes_provider_error(self):
        with TemporaryDirectory() as tmp:
            result, gateway, checkpoint, sessions, _ = self.run_shadow(
                Path(tmp), create_error=OSError("private provider response body"))
            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["provider"]["status"], "UNKNOWN")
            self.assertIsNone(result["settled_cost_usd"])
            self.assertNotIn("private provider response body", json.dumps(result))
            self.assertEqual(sessions.create_count, 1)
            self.assertTrue(any(call == "checkpoint" for call in gateway.calls))

    def test_model_response_does_not_change_candidate_or_baseline_bytes(self):
        from manager_core import owned_provider_shadow as shadow

        def snapshot_bundle(path):
            self.assertTrue(path.is_dir(), f"missing live bundle: {path}")
            actual = {item.name: item.read_bytes() for item in path.iterdir() if item.is_file()}
            expected = set(PAGES) | {"manifest.json"}
            self.assertEqual(set(actual), expected)
            return actual

        def stable_publisher_intent(packet):
            keys = ("schema", "repository", "ref", "workflow", "target", "candidate",
                    "allowed_paths", "baseline", "baseline_sha256", "candidate_sha256",
                    "decision", "changed_pages", "money_budget", "max_changed_files",
                    "external_authority", "revocation_control", "human_outcome",
                    "causal_effect_verified")
            return {key: packet[key] for key in keys}

        with TemporaryDirectory() as first_tmp, TemporaryDirectory() as second_tmp:
            first_root, second_root = Path(first_tmp), Path(second_tmp)
            first_workspace, second_workspace = first_root / "private", second_root / "private"
            observations = []
            first_packet = []
            second_packet = []

            def run_observed(root, workspace, output, packet_capture):
                before_model = []
                packet_at_model = []
                def capture_prepare(*args, **kwargs):
                    prepared = original_prepare(*args, **kwargs)
                    packet_capture.append(stable_publisher_intent(prepared.packet))
                    return prepared
                def on_create():
                    prepared_packet = packet_capture[-1]
                    baseline = snapshot_bundle(workspace / "baseline")
                    candidate = snapshot_bundle(workspace / "candidate")
                    baseline_manifest = json.loads(baseline["manifest.json"])
                    candidate_manifest = json.loads(candidate["manifest.json"])
                    packet_at_model.append((baseline_manifest, candidate_manifest, prepared_packet))
                    before_model.append((baseline, candidate))
                with patch.object(shadow, "prepare_owned_change", side_effect=capture_prepare):
                    result, _, _, sessions, _ = self.run_shadow(
                        root, workspace=workspace, output=output, on_create=on_create)
                after_model = (snapshot_bundle(workspace / "baseline"),
                               snapshot_bundle(workspace / "candidate"))
                observations.append((before_model[0], after_model, packet_at_model[0], sessions))
                return result

            original_prepare = shadow.prepare_owned_change
            pass_result = run_observed(first_root, first_workspace,
                '{"decision":"PASS","reason":"No further change.","source_ids":[]}', first_packet)
            propose_result = run_observed(second_root, second_workspace,
                '{"decision":"PROPOSE","reason":"Repair the cited link.","source_ids":["official:livelihood"]}', second_packet)

            self.assertEqual(len(observations), 2)
            for index, (before, after, (packet_baseline, packet_candidate, publisher_at_model), sessions) in enumerate(observations):
                self.assertEqual(before, after)
                self.assertEqual(packet_baseline, json.loads(after[0]["manifest.json"]))
                self.assertEqual(packet_candidate, json.loads(after[1]["manifest.json"]))
                self.assertEqual(publisher_at_model,
                                 (first_packet if index == 0 else second_packet)[0])
                self.assertEqual(sessions.create_count, 1)

            self.assertEqual(pass_result["operation_id"], propose_result["operation_id"])
            self.assertEqual(pass_result["baseline_digest"], propose_result["baseline_digest"])
            self.assertEqual(pass_result["candidate_digest"], propose_result["candidate_digest"])
            self.assertEqual(first_packet, second_packet)
            self.assertEqual(pass_result["model_advice"]["decision"], "PASS")
            self.assertEqual(propose_result["model_advice"]["decision"], "PROPOSE")

            # Negative control: changing one byte in a test-local copy is detected
            # while both source fixture trees are still alive.
            mutated = dict(observations[0][0][1])
            first_page = sorted(PAGES)[0]
            mutated[first_page] = mutated[first_page] + b"x"
            self.assertNotEqual(observations[0][0][1], mutated)
            self.assertTrue(first_workspace.exists())
            self.assertTrue(second_workspace.exists())

    def test_deadline_is_rechecked_after_planning(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout, workspace, fixture_patches = make_catalog_fixture(root)
            gateway, checkpoint = self.owner(root)
            client, sessions = client_for()
            from manager_core import owned_provider_shadow as shadow
            with fixture_patches[0], fixture_patches[1], fixture_patches[2], fixture_patches[3], \
                 patch.object(shadow.time, "monotonic", side_effect=[1.0, 100.0]):
                result = shadow.run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                    run_id="123", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                    deadline_monotonic=50.0)
            self.assertEqual(result["status"], "SKIPPED")
            self.assertEqual(sessions.create_count, 0)


    def test_real_current_page_cue_context_is_skipped(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout, workspace, fixture_patches = make_catalog_fixture(root, shape="cue")
            reference_bytes = b"W3C aria-current page token: the current page in a set of pages."
            observed = datetime.now(timezone.utc)
            reference = Source("w3c:aria-current-1.2", planner.CURRENT_PAGE_W3C_URL,
                "W3C Document License", "allowed_with_conditions", sha256(reference_bytes).hexdigest(),
                observed, "public_nonpersonal")
            with patch.object(planner, "_read_owned_baseline_page",
                              return_value=((checkout / "manager-support/finance.html").read_bytes(), observed)), \
                 patch.object(planner, "_read_current_page_reference", return_value=(reference, reference_bytes)):
                gateway, checkpoint = self.owner(root)
                client, sessions = client_for()
                from manager_core.owned_provider_shadow import run_catalog_shadow, compare_prepared_catalog_shadow
                with fixture_patches[0], fixture_patches[1], fixture_patches[2], fixture_patches[3]:
                    prepared = planner.plan_catalog_change(checkout, workspace, SOURCE_COMMIT,
                        datetime.now(timezone.utc), run_id="123")
                    calls = []
                    direct = compare_prepared_catalog_shadow(checkpoint, prepared,
                        now=datetime.now(timezone.utc), run_id="123", enabled=True,
                        client_factory=lambda: calls.append(True) or client,
                        cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                        deadline_monotonic=monotonic()+10)
                    self.assertEqual(direct["reason"], "UNSUPPORTED_ACTION")
                    self.assertEqual(calls, [])
                    with patch.object(planner, "plan_catalog_change", return_value=prepared):
                        result = run_catalog_shadow(checkpoint, client, checkout, workspace, SOURCE_COMMIT,
                            run_id="123", enabled=True, cap_usd=Decimal("0.05"), upper_usd=Decimal("0.03"),
                            deadline_monotonic=monotonic()+10)
            self.assertEqual(result["status"], "SKIPPED")
            self.assertEqual(result["reason"], "UNSUPPORTED_ACTION")
            self.assertEqual(sessions.create_count, 0)

    def test_stale_and_synthetic_planner_contexts_cannot_reach_model(self):
        for kind in ("stale", "synthetic"):
            with self.subTest(kind=kind), TemporaryDirectory() as tmp:
                root = Path(tmp)
                checkout, workspace, fixture_patches = make_catalog_fixture(root)
                original_plan = planner.plan_catalog_change
                def altered(*args, **kwargs):
                    planned = original_plan(*args, **kwargs)
                    context, assessment, scope = planned
                    if kind == "stale":
                        old = datetime.now(timezone.utc)-timedelta(hours=60)
                        sources = tuple(replace(source, retrieved_at=old)
                                        for source in context.criteria.official_sources)
                        facts = tuple(PublicFact(source, fact.summary)
                                      for source, fact in zip(sources, context.planner.facts))
                        planner_context = PlannerContext(context.planner.goal, facts, old)
                        criteria = replace(context.criteria, official_sources=sources, at=old)
                        context = OwnedChangeContext(context.run_id, planner_context,
                            context.baseline_bundle, context.candidate_bundle, criteria)
                    else:
                        original = context.criteria.official_sources[0]
                        synthetic = Source("synthetic:catalog", original.url, original.license_id,
                            original.rights, original.content_sha256, original.retrieved_at,
                            original.privacy_class)
                        candidate = replace(context.criteria.candidate,
                                            source_refs=(synthetic.source_id,))
                        criteria = replace(context.criteria, candidate=candidate,
                                           official_sources=(synthetic,))
                        planner_context = PlannerContext(context.planner.goal,
                            (PublicFact(synthetic, context.planner.facts[0].summary,
                                        "SYNTHETIC_SCENARIO"),), context.planner.observed_at)
                        assessment = verify_candidate(context.baseline_bundle,
                            context.candidate_bundle, criteria)
                        context = OwnedChangeContext(context.run_id, planner_context,
                            context.baseline_bundle, context.candidate_bundle, criteria)
                    return context, assessment, scope
                gateway, checkpoint = self.owner(root)
                client, sessions = client_for()
                from manager_core import owned_provider_shadow as shadow
                with fixture_patches[0], fixture_patches[1], fixture_patches[2], fixture_patches[3], \
                     patch.object(planner, "plan_catalog_change", side_effect=altered):
                    result = shadow.run_catalog_shadow(checkpoint, client, checkout, workspace,
                        SOURCE_COMMIT, run_id="123", enabled=True, cap_usd=Decimal("0.05"),
                        upper_usd=Decimal("0.03"), deadline_monotonic=monotonic()+10)
                self.assertEqual(result["status"], "SKIPPED")
                self.assertEqual(sessions.create_count, 0)

    def test_result_never_contains_publisher_packet_or_raw_errors(self):
        with TemporaryDirectory() as tmp:
            result, _, _, _, _ = self.run_shadow(Path(tmp))
            serialized = json.dumps(result)
            self.assertNotIn("changed_pages", serialized)
            self.assertNotIn("exception", serialized.lower())
            self.assertNotIn("packet", serialized.lower())
