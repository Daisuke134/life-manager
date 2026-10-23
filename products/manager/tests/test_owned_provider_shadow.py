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
        def get_final_result(self): return SimpleNamespace(session_id="sess_12345678", output_text=output)
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
    def owner(self, root, cap=Decimal("0.05")):
        raw, _ = snapshot(root / "seed")
        gateway = MemoryGateway(raw)
        checkpoint = PrivateCheckpoint(gateway, run_id="123", run_attempt="1")
        checkpoint.acquire(root / "run")
        return gateway, checkpoint

    def run_shadow(self, root, **kwargs):
        from manager_core.owned_provider_shadow import run_catalog_shadow
        checkout, workspace, fixture_patches = make_catalog_fixture(root)
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
        with TemporaryDirectory() as first_tmp:
            first, _, _, _, first_workspace = self.run_shadow(Path(first_tmp), output='{"decision":"PASS","reason":"No further change.","source_ids":[]}')
        with TemporaryDirectory() as second_tmp:
            second, _, _, _, second_workspace = self.run_shadow(Path(second_tmp), output='{"decision":"PROPOSE","reason":"Repair the cited link.","source_ids":["official:livelihood"]}')
        for key in ("operation_id", "baseline_digest", "candidate_digest", "candidate", "sources", "baseline"):
            self.assertEqual(first[key], second[key])
        def tree(path):
            return {str(item.relative_to(path)): item.read_bytes()
                    for item in path.rglob("*") if item.is_file()}
        for name in ("baseline", "candidate"):
            self.assertEqual(tree(first_workspace / name), tree(second_workspace / name))
        self.assertEqual(first["model_advice"]["decision"], "PASS")
        self.assertEqual(second["model_advice"]["decision"], "PROPOSE")

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
                from manager_core.owned_provider_shadow import run_catalog_shadow
                with fixture_patches[0], fixture_patches[1], fixture_patches[2], fixture_patches[3]:
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
