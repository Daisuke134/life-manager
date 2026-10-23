"""Fixed catalog selection must preserve NO_ACTION and bind any change to live bytes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import functools
import unittest
from unittest.mock import patch

from manager_core.digital_environment import PAGES, build_site
from manager_core.digital_handoff import OwnedChangeContext, prepare_owned_change
from manager_core.models.source import Source
from manager_core.models.intervention import Candidate
from manager_core.candidate_verification import TechnicalCriteria, verify_candidate
from manager_core import owned_catalog_planner as planner

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)
SHA = "a" * 40


def catalog():
    return json.loads((ROOT / "public_goods/service/catalog.json").read_text())


def bodies_from(site):
    return {name: (site / name).read_bytes() for name in PAGES}


class OwnedCatalogPlannerTests(unittest.TestCase):
    def test_current_live_shaped_site_plans_only_the_versioned_navigation_cue(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            bundle = checkout / "manager-support"
            build_site(catalog(), bundle, SHA)
            before = {p.name: p.read_bytes() for p in bundle.iterdir()}
            workspace = root / "private"
            now = datetime.now(timezone.utc)
            rows = [{"id": row["id"], "url": row["url"], "final_url": row["url"],
                     "status": "REACHABLE_NOT_OUTCOME", "http_status": 200,
                     "sha256": sha256(row["id"].encode()).hexdigest(), "observed_at": now.isoformat()}
                    for row in catalog()["resources"]]
            reference_bytes = b"W3C aria-current page token: the current page in a set of pages."
            reference = Source("w3c:aria-current-1.2", planner.CURRENT_PAGE_W3C_URL,
                               "W3C Document License", "allowed_with_conditions",
                               sha256(reference_bytes).hexdigest(), now, "public_nonpersonal")
            served = (json.loads((bundle / "manifest.json").read_text()), bodies_from(bundle),
                      (bundle / "manifest.json").read_bytes())
            with patch.object(planner, "_read_served_bundle", return_value=served), \
                 patch.object(planner, "audit_sources", return_value={"sources": rows}), \
                 patch.object(planner, "_read_owned_baseline_page",
                              return_value=(bodies_from(bundle)["finance.html"], now)), \
                 patch.object(planner, "_read_current_page_reference", return_value=(reference, reference_bytes)), \
                 patch.object(planner, "verify_candidate_in_browser", return_value={"status": "P0_BROWSER_FIXTURE"}), \
                 patch.dict("os.environ", {"MANAGER_RELEASE_ENABLED": "true"}):
                result = planner.plan_catalog_change(checkout, workspace, "c" * 40, now, run_id="123")
                self.assertEqual(result[0].criteria.version, "owned-digital-technical-v2")
                self.assertEqual(result[0].criteria.candidate.action, "ADD_CURRENT_PAGE_CUE")
                self.assertEqual(result[0].criteria.candidate.target, "manager-support/finance.html")
                prepared = prepare_owned_change(*result, datetime.now(timezone.utc), schema="manager.digital-handoff.v2")
            self.assertEqual(prepared.status, "PREPARED_PLATFORM_AUTHORITY_REQUIRED")
            self.assertEqual(prepared.packet["changed_pages"], sorted(PAGES))
            self.assertEqual(before, {p.name: p.read_bytes() for p in bundle.iterdir()})
            candidate = workspace / "candidate"
            self.assertIn(b'aria-current="page"', (candidate / "finance.html").read_bytes())
            self.assertNotIn(b"aria-current", (candidate / "mental.html").read_bytes())

    def test_selector_uses_exact_catalog_title_and_reviewed_url_observation(self):
        c = catalog()
        rows = [{"id": "livelihood", "url": c["resources"][0]["url"], "status": "REACHABLE_NOT_OUTCOME",
                 "http_status": 200, "sha256": "b" * 64, "final_url": c["resources"][0]["url"],
                 "observed_at": NOW.isoformat()}]
        baseline = {name: b"" for name in PAGES}
        baseline["finance.html"] = (f'<a data-official href="{c["resources"][0]["url"]}"></a>'.encode())
        # Empty labels are eligible only when the anchor has no accessible name or child content.
        opportunity = planner.find_catalog_opportunity(baseline, c, rows)
        self.assertEqual(opportunity.action, "IMPROVE_ACCESSIBILITY")
        self.assertEqual(opportunity.required_label, c["resources"][0]["title"])

    def test_current_page_cue_selects_finance_then_mental_then_no_action(self):
        with TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "manager-support"
            build_site(catalog(), bundle, SHA)
            bodies = bodies_from(bundle)

            opportunity = planner.find_current_page_opportunity(bodies)
            self.assertEqual(opportunity.action, "ADD_CURRENT_PAGE_CUE")
            self.assertEqual(opportunity.target_path, "finance.html")

            finance = bodies["finance.html"].decode("utf-8")
            finance = finance.replace('<a href="finance.html">', '<a href="finance.html" aria-current="page">', 1)
            bodies["finance.html"] = finance.encode("utf-8")
            opportunity = planner.find_current_page_opportunity(bodies)
            self.assertEqual(opportunity.action, "ADD_CURRENT_PAGE_CUE")
            self.assertEqual(opportunity.target_path, "mental.html")

            mental = bodies["mental.html"].decode("utf-8")
            mental = mental.replace('<a href="mental.html">', '<a href="mental.html" aria-current="page">', 1)
            bodies["mental.html"] = mental.encode("utf-8")
            self.assertIsNone(planner.find_current_page_opportunity(bodies))

    def test_current_page_selector_fails_closed_on_ambiguous_or_wrong_navigation(self):
        with TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "manager-support"
            build_site(catalog(), bundle, SHA)
            original = bodies_from(bundle)
            mutations = {
                "duplicate_self_link": lambda text: text.replace(
                    '<a href="finance.html">', '<a href="finance.html">', 1
                ).replace('</nav>', '<a href="finance.html">duplicate</a></nav>', 1),
                "wrong_nav": lambda text: text.replace('aria-label="主な案内"', 'aria-label="別の案内"', 1),
                "nav_outside_header": lambda text: text.replace('<header>', '<header></header>', 1),
                "wrong_current_value": lambda text: text.replace(
                    '<a href="finance.html">', '<a href="finance.html" aria-current="step">', 1
                ),
                "foreign_current": lambda text: text.replace(
                    '<a href="index.html">', '<a href="index.html" aria-current="page">', 1
                ),
                "duplicate_current_attribute": lambda text: text.replace(
                    '<a href="finance.html">',
                    '<a href="finance.html" aria-current="page" aria-current="page">', 1
                ),
                "missing_self_link": lambda text: text.replace(
                    '<a href="finance.html">生活費・仕事・借入</a>', '', 1
                ),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    bodies = dict(original)
                    bodies["finance.html"] = mutate(bodies["finance.html"].decode("utf-8")).encode("utf-8")
                    self.assertIsNone(planner.find_current_page_opportunity(bodies))

    def test_positive_plan_returns_bound_context_accepted_by_existing_prepare_api(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            bundle = checkout / "manager-support"
            build_site(catalog(), bundle, SHA)
            path = bundle / "finance.html"
            body = path.read_bytes()
            import re
            match = re.search(rb'(<a data-official href="[^"]+"[^>]*>)[^<]+</a>', body)
            body = body.replace(match.group(0), match.group(1) + b"</a>", 1)
            path.write_bytes(body)
            manifest = json.loads((bundle / "manifest.json").read_text())
            manifest["files"]["finance.html"] = sha256(body).hexdigest()
            (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
            now = datetime.now(timezone.utc)
            rows = [{"id": row["id"], "url": row["url"], "final_url": row["url"],
                     "status": "REACHABLE_NOT_OUTCOME", "http_status": 200,
                     "sha256": sha256(row["id"].encode()).hexdigest(), "observed_at": now.isoformat()}
                    for row in catalog()["resources"]]
            served = (manifest, bodies_from(bundle), (bundle / "manifest.json").read_bytes())
            with patch.object(planner, "_read_served_bundle", return_value=served), \
                 patch.object(planner, "audit_sources", return_value={"sources": rows}), \
                 patch.object(planner, "verify_candidate_in_browser", return_value={"status": "P0_BROWSER_FIXTURE"}), \
                 patch.dict("os.environ", {"MANAGER_RELEASE_ENABLED": "true"}):
                result = planner.plan_catalog_change(checkout, root / "private", "c" * 40, now, run_id="12345")
                self.assertIs(type(result[0]), OwnedChangeContext)
                self.assertEqual(result[0].criteria.version, "owned-digital-technical-v1")
                self.assertEqual(result[0].criteria.candidate.action, "IMPROVE_ACCESSIBILITY")
                self.assertEqual(result[0].run_id, "12345")
                self.assertEqual(result[0].baseline_bundle.name, "baseline")
                self.assertEqual(result[0].candidate_bundle.name, "candidate")
                self.assertEqual(result[0].criteria.candidate.target, "manager-support/finance.html")
                prepared = prepare_owned_change(*result, datetime.now(timezone.utc), schema="manager.digital-handoff.v2")
            self.assertEqual(prepared.status, "PREPARED_PLATFORM_AUTHORITY_REQUIRED")
            self.assertEqual(prepared.run_id, "12345")

    def test_reviewed_catalog_discrepancy_is_selected_only_for_exact_identity(self):
        c = catalog()
        row = c["resources"][0]
        observation = {"id": row["id"], "url": row["url"], "status": "REACHABLE_NOT_OUTCOME",
                       "http_status": 200, "sha256": "d" * 64, "final_url": row["url"],
                       "observed_at": NOW.isoformat()}
        baseline = {name: b"" for name in PAGES}
        baseline["finance.html"] = (f'<a data-official href="https://www.mhlw.go.jp/old-route">{row["title"]}</a>'.encode())
        selected = planner.find_catalog_opportunity(baseline, c, [observation])
        self.assertEqual(selected.action, "CORRECT_LINK")
        self.assertEqual(selected.old_url, "https://www.mhlw.go.jp/old-route")
        baseline["finance.html"] = b'<a data-official href="https://www.mhlw.go.jp/old-route">unrelated</a>'
        self.assertIsNone(planner.find_catalog_opportunity(baseline, c, [observation]))

    def test_ambiguous_identity_and_unknown_physical_rights_are_not_guessed(self):
        c = catalog()
        row = c["resources"][3]
        obs = [{"id": row["id"], "url": row["url"], "status": "REACHABLE_NOT_OUTCOME",
                "http_status": 200, "sha256": "c" * 64, "final_url": row["url"],
                "observed_at": NOW.isoformat()}]
        baseline = {name: b"" for name in PAGES}
        baseline["physical.html"] = f'<a data-official href="https://kennet.mhlw.go.jp/old">{row["title"]}</a>'.encode()
        self.assertIsNone(planner.find_catalog_opportunity(baseline, c, obs))

        baseline["physical.html"] = f'<a data-official href="{row["url"]}"></a>'.encode()
        self.assertIsNone(planner.find_catalog_opportunity(baseline, c, obs))

    def test_checkout_and_independent_served_seven_file_bytes_must_match(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            bundle = checkout / "manager-support"
            build_site(catalog(), bundle, SHA)
            remote = bodies_from(bundle)
            remote["proof.html"] += b"stale"
            with patch.object(planner, "_read_served_bundle", return_value=(json.loads((bundle / "manifest.json").read_text()), remote, (bundle / "manifest.json").read_bytes())):
                with self.assertRaisesRegex(ValueError, "served.*checkout"):
                    planner.plan_catalog_change(checkout, root / "private", SHA, NOW, run_id="123")

    def test_exact_empty_label_candidate_updates_only_target_and_source_footers(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before"
            candidate_dir = root / "candidate"
            manifest = build_site(catalog(), before, SHA)
            path = before / "finance.html"
            body = path.read_bytes()
            import re
            match = re.search(rb'(<a data-official href="[^"]+"[^>]*>)[^<]+</a>', body)
            self.assertIsNotNone(match)
            body = body.replace(match.group(0), match.group(1) + b"</a>", 1)
            path.write_bytes(body)
            manifest["files"]["finance.html"] = sha256(body).hexdigest()
            (before / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
            row = catalog()["resources"][0]
            opportunity = planner.CatalogOpportunity("IMPROVE_ACCESSIBILITY", "finance.html", row["id"], row["url"], row["url"], row["title"])
            new_manifest = planner._materialize(before, opportunity, "b" * 40, candidate_dir, manifest)
            source = Source("official:livelihood", row["url"], "PDL-1.0", "allowed_with_conditions", "c" * 64, NOW, "public_nonpersonal")
            candidate = Candidate("catalog-livelihood", "IMPROVE_ACCESSIBILITY", "manager-support/finance.html", (source.source_id,), "accessible_link_label")
            criteria = TechnicalCriteria(candidate, row["url"], row["url"], row["title"], (source,), NOW)
            result = verify_candidate(before, candidate_dir, criteria)
            self.assertEqual(result.status, "VERIFIED_TECHNICAL")
            self.assertEqual(new_manifest["source_commit"], "b" * 40)
            self.assertIn("manager-support/finance.html", result.changed_paths)
            self.assertTrue(all((candidate_dir / name).is_file() for name in PAGES | {"manifest.json"}))

    def test_browser_report_requires_exact_projects_and_all_16_passes(self):
        report = {"suites": [{"suites": [
            {"specs": [{"tests": [{"projectName": project, "expectedStatus": "passed", "results": [{"status": "passed"}]} for _ in range(8)]} for project in ("desktop", "mobile")]
        }]}]}
        counts = planner._report_counts(report)
        self.assertEqual(counts, {"total": 16, "by_project": {"desktop": 8, "mobile": 8}, "passed": 16, "skipped": 0, "unexpected": 0})
        report["suites"][0]["suites"][0]["specs"][0]["tests"][0]["results"][0]["status"] = "skipped"
        self.assertGreater(planner._report_counts(report)["skipped"], 0)

    def test_browser_runner_removes_stale_report_and_rejects_missing_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            suite = root / "tests/e2e"
            suite.mkdir(parents=True)
            candidate = root / "candidate"
            build_site(catalog(), candidate, SHA)
            output = root / "output/service"
            output.mkdir(parents=True)
            stale = output / "browser-results.json"
            stale.write_text('{"old":true}')
            class Server:
                def shutdown(self): pass
                def server_close(self): pass
            class ServerThread:
                def join(self, timeout=None): pass
            with patch.object(planner, "_start_candidate_server", return_value=(Server(), ServerThread())), \
                 patch.object(planner.subprocess, "run", return_value=type("Run", (), {"returncode": 0})()):
                with self.assertRaisesRegex(ValueError, "fresh report missing"):
                    planner._verify_candidate_in_browser(candidate, SHA, planner._candidate_tree_digest(candidate), root)
            self.assertFalse(stale.exists())

    def test_browser_runner_refuses_wrong_report_and_candidate_mutation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests/e2e").mkdir(parents=True)
            candidate = root / "candidate"
            build_site(catalog(), candidate, SHA)
            class Server:
                def shutdown(self): pass
                def server_close(self): pass
            class ServerThread:
                def join(self, timeout=None): pass
            report_path = root / "output/service/browser-results.json"
            def make_report(count=16):
                tests = [{"projectName": "desktop" if n < 8 else "mobile", "expectedStatus": "passed", "results": [{"status": "passed"}]} for n in range(count)]
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps({"suites": [{"specs": [{"tests": tests}]}]}))
            with patch.object(planner, "_start_candidate_server", return_value=(Server(), ServerThread())), \
                 patch.object(planner.subprocess, "run", side_effect=lambda *a, **k: (make_report(15), type("Run", (), {"returncode": 0})())[1]):
                with self.assertRaisesRegex(ValueError, "exact expected passing suite"):
                    planner._verify_candidate_in_browser(candidate, SHA, planner._candidate_tree_digest(candidate), root)
            def mutate_candidate(*args, **kwargs):
                make_report()
                (candidate / "proof.html").write_bytes((candidate / "proof.html").read_bytes() + b"changed")
                return type("Run", (), {"returncode": 0})()
            with patch.object(planner, "_start_candidate_server", return_value=(Server(), ServerThread())), \
                 patch.object(planner.subprocess, "run", side_effect=mutate_candidate):
                with self.assertRaisesRegex(ValueError, "candidate bytes changed"):
                    planner._verify_candidate_in_browser(candidate, SHA, planner._candidate_tree_digest(candidate), root)

    def test_browser_adapter_refuses_an_incumbent_8765_even_when_manifest_matches(self):
        # The incumbent serves a candidate-shaped manifest but a different page body.
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = root / "manager"
            (manager / "tests/e2e").mkdir(parents=True)
            candidate = root / "candidate"
            incumbent = root / "incumbent"
            build_site(catalog(), candidate, SHA)
            build_site(catalog(), incumbent, SHA)
            (incumbent / "proof.html").write_bytes(b"WRONG_SERVER_BYTES")
            class Quiet(SimpleHTTPRequestHandler):
                def log_message(self, *args):
                    pass
            try:
                server = ThreadingHTTPServer(("127.0.0.1", 8765), functools.partial(Quiet, directory=str(incumbent)))
            except OSError as exc:
                self.skipTest(f"fixed browser port is already occupied: {type(exc).__name__}")
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            npm = unittest.mock.Mock()
            try:
                with patch.object(planner.subprocess, "run", npm):
                    with self.assertRaisesRegex(ValueError, "port unavailable"):
                        planner._verify_candidate_in_browser(candidate, SHA, planner._candidate_tree_digest(candidate), manager)
                npm.assert_not_called()
                self.assertTrue(thread.is_alive())
                self.assertEqual((incumbent / "proof.html").read_bytes(), b"WRONG_SERVER_BYTES")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_browser_child_environment_strips_credentials_and_keeps_network_tls(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "private", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "private",
                                      "SUPABASE_SERVICE_ROLE_KEY": "private", "MANAGER_STATE_GATEWAY_KEY": "private", "HTTPS_PROXY": "http://proxy.invalid",
                                      "SSL_CERT_FILE": "/tmp/ca.pem"}, clear=True):
            env = planner._sanitized_environment()
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", env)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", env)
        self.assertNotIn("MANAGER_STATE_GATEWAY_KEY", env)
        self.assertEqual(env["HTTPS_PROXY"], "http://proxy.invalid")
        self.assertEqual(env["SSL_CERT_FILE"], "/tmp/ca.pem")
        self.assertEqual(env["MANAGER_BASE_URL"], "http://127.0.0.1:8765/")

    def test_fixed_scope_is_bounded_and_revocation_fails_closed(self):
        with patch.dict("os.environ", {"MANAGER_RELEASE_ENABLED": "true"}):
            scope = planner._freshness_scope(NOW)
        self.assertEqual(scope.expires_at - scope.not_before, __import__("datetime").timedelta(minutes=10))
        self.assertEqual(scope.max_changed_files, 7)
        self.assertFalse(scope.revoked)
        with patch.dict("os.environ", {"MANAGER_RELEASE_ENABLED": "false"}):
            self.assertTrue(planner._freshness_scope(NOW).revoked)

    def test_failed_or_incomplete_source_audit_fails_closed_without_candidate(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkout = root / "checkout"
            bundle = checkout / "manager-support"
            build_site(catalog(), bundle, SHA)
            # An empty-label target makes the path eligible, so a source audit is required.
            body = (bundle / "finance.html").read_bytes()
            import re
            body = re.sub(rb'(<a data-official href="[^"]+"[^>]*>)[^<]+</a>', rb'\1</a>', body, count=1)
            (bundle / "finance.html").write_bytes(body)
            manifest = json.loads((bundle / "manifest.json").read_text())
            manifest["files"]["finance.html"] = sha256(body).hexdigest()
            (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
            served = (manifest, bodies_from(bundle))
            failed = {"sources": [], "content_rights": "LINK_ONLY", "human_outcome": "NOT_MEASURED"}
            workspace = root / "private"
            with patch.object(planner, "_read_served_bundle", return_value=(served[0], served[1], (bundle / "manifest.json").read_bytes())), patch.object(planner, "audit_sources", return_value=failed):
                with self.assertRaisesRegex(RuntimeError, "UNKNOWN.*SOURCE_AUDIT_UNAVAILABLE"):
                    planner.plan_catalog_change(checkout, workspace, SHA, NOW, run_id="123")
            self.assertTrue((workspace / "source-audit.json").is_file())


if __name__ == "__main__":
    unittest.main()
