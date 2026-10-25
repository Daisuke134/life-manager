"""The Railway tick is bounded, mounted-state-only, and request-once."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from manager_core.digital_handoff import (
    MAIN_SOURCE_REF, SOURCE_REF, PublisherContext, REPOSITORY, WORKFLOW, prepare_owned_change,
)
from manager_core.digital_environment import build_site, PAGES
from manager_core.owned_platform_host import create_owned_workflow_request
from manager_core.outbox import OwnedEffectJournal
from manager_core.owned_cycle import CycleStore, run_owned_workflow_bridge_once
from test_candidate_verification import NOW


class OwnedWorkflowWorkerTests(unittest.TestCase):
    def runtime_env(self, state_root):
        ids = {
            "PROJECT": "project-123",
            "ENVIRONMENT": "environment-123",
            "SERVICE": "service-123",
            "VOLUME": "manager-owner-state",
        }
        return {
            "RAILWAY_PROJECT_ID": ids["PROJECT"],
            "RAILWAY_ENVIRONMENT_ID": ids["ENVIRONMENT"],
            "RAILWAY_SERVICE_ID": ids["SERVICE"],
            "RAILWAY_SERVICE_NAME": "manager-owned-digital-worker",
            "RAILWAY_DEPLOYMENT_ID": "deployment-123",
            "RAILWAY_VOLUME_NAME": ids["VOLUME"],
            "RAILWAY_VOLUME_MOUNT_PATH": str(state_root),
            "RAILWAY_GIT_REPO_OWNER": "Daisuke134",
            "RAILWAY_GIT_REPO_NAME": "life-manager",
            "RAILWAY_GIT_BRANCH": "main",
            "RAILWAY_GIT_COMMIT_SHA": "b" * 40,
            "MANAGER_OWNER_ENABLED": "true",
            "MANAGER_OWNER_ID": "fixture-owner",
            "MANAGER_INTERVAL_SECONDS": "3600",
            "MANAGER_WORKFLOW_DISPATCH_TOKEN": "fixture-token",
            "MANAGER_EXPECTED_RAILWAY_PROJECT_ID": ids["PROJECT"],
            "MANAGER_EXPECTED_RAILWAY_ENVIRONMENT_ID": ids["ENVIRONMENT"],
            "MANAGER_EXPECTED_RAILWAY_SERVICE_ID": ids["SERVICE"],
            "MANAGER_EXPECTED_RAILWAY_VOLUME_NAME": ids["VOLUME"],
        }

    def reserve_request(self, state_root):
        from test_digital_cycle_acceptance import CycleAcceptanceTests
        _, _, host, _ = CycleAcceptanceTests().prepare(state_root / "fixture")
        prepared = prepare_owned_change(host.context, host.assessment, host.scope, NOW,
                                       source_ref=MAIN_SOURCE_REF)
        packet = prepared.packet
        parent = host.git("rev-parse", "HEAD")
        owner_id = "fixture-owner"
        request = create_owned_workflow_request(packet, owner_id, parent)
        context = PublisherContext(REPOSITORY, MAIN_SOURCE_REF, WORKFLOW,
                                   packet["candidate"]["source_commit"], "1")
        journal = OwnedEffectJournal(state_root / "cycle.sqlite")
        journal.reserve(packet, context, packet["baseline"], packet["candidate"], parent, NOW,
                        workflow_request=request, owner_id=owner_id)
        return request

    def test_worker_requires_verified_runtime_before_opening_state_or_network(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            env = self.runtime_env(state)
            env["RAILWAY_SERVICE_ID"] = "wrong-service"
            calls = []
            result = run_owned_workflow_bridge_once(
                state, env=env, now=datetime.now(timezone.utc),
                get=lambda *args: calls.append(args), post=lambda *args: calls.append(args),
                mount_check=lambda path: True)
            self.assertEqual(result["status"], "DEPLOYMENT_HOST_REQUIRED")
            self.assertEqual(calls, [])
            self.assertFalse((state / "cycle.sqlite").exists())

    def test_worker_processes_one_durable_request_then_never_retries_unknown_send(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            request = self.reserve_request(state)
            env = self.runtime_env(state)
            gets, posts = [], []

            def get(*args):
                gets.append(args)
                return 200, json.dumps({"workflow_runs": []}).encode()

            def post(*args):
                posts.append(args)
                raise TimeoutError("fixture lost response")

            first = run_owned_workflow_bridge_once(
                state, env=env, now=datetime.now(timezone.utc), get=get, post=post,
                mount_check=lambda path: True)
            second = run_owned_workflow_bridge_once(
                state, env=env, now=datetime.now(timezone.utc), get=get, post=post,
                mount_check=lambda path: True)

            self.assertEqual(first["status"], "UNKNOWN")
            self.assertEqual(first["request_id"], request.request_id)
            self.assertTrue(first["sent"])
            self.assertEqual(second["status"], "UNKNOWN")
            self.assertFalse(second["sent"])
            self.assertEqual(len(posts), 1)
            self.assertEqual(len(gets), 3)
            self.assertNotIn("fixture-token", json.dumps(first))

    def test_idle_worker_builds_request_only_for_current_source_and_exact_served_parent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            state.mkdir()
            now = datetime.now(timezone.utc)
            source_sha = "b" * 40
            parent_sha = "c" * 40
            catalog = json.loads((Path(__file__).resolve().parents[1]
                                  / "public_goods/service/catalog.json").read_text())
            baseline_root = root / "baseline"
            baseline_manifest = build_site(catalog, baseline_root, "a" * 40)
            page_bodies = {name: (baseline_root / name).read_bytes() for name in PAGES}
            posts, api_reads, public_reads = [], [], []

            def public_get(url):
                public_reads.append(url)
                if url.endswith("/manifest.json"):
                    return (baseline_root / "manifest.json").read_bytes()
                name = url.rsplit("/", 1)[-1]
                if name in page_bodies:
                    return page_bodies[name]
                raise AssertionError("unexpected public URL")

            def api_get(url, headers, timeout):
                api_reads.append(url)
                if url.endswith("/git/ref/heads/main"):
                    branch, sha = "main", source_sha
                elif url.endswith("/git/ref/heads/gh-pages"):
                    branch, sha = "gh-pages", parent_sha
                elif "/actions/workflows/manager-phase06-service.yml/runs?" in url:
                    return 200, b'{"workflow_runs": []}'
                else:
                    raise AssertionError("unexpected GitHub API URL")
                return 200, json.dumps({
                    "ref": "refs/heads/" + branch,
                    "object": {
                        "sha": sha,
                        "type": "commit",
                        "url": "https://api.github.com/repos/Daisuke134/life-manager/git/commits/" + sha,
                    },
                }).encode()

            result = run_owned_workflow_bridge_once(
                state, env=self.runtime_env(state), now=now,
                get=api_get, post=lambda *args: posts.append(args) or 204,
                public_get=public_get, mount_check=lambda path: True)

            self.assertEqual(result["status"], "ACCEPTED", result)
            self.assertTrue(result["sent"])
            self.assertEqual(len(posts), 1)
            self.assertTrue(any(url.endswith("/git/ref/heads/main") for url in api_reads))
            self.assertTrue(any(url.endswith("/git/ref/heads/gh-pages") for url in api_reads))
            self.assertEqual(len(public_reads), 2 * (len(PAGES) + 1))
            self.assertFalse(result["published"])

    def test_prior_unknown_effect_blocks_new_workflow_request(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            from test_digital_cycle_acceptance import CycleAcceptanceTests
            _, _, host, _ = CycleAcceptanceTests().prepare(state / "fixture")
            old = prepare_owned_change(host.context, host.assessment, host.scope, NOW).packet
            parent = host.git("rev-parse", "HEAD")
            journal = OwnedEffectJournal(state / "cycle.sqlite")
            old_context = PublisherContext(REPOSITORY, SOURCE_REF, WORKFLOW,
                                           old['candidate']['source_commit'], '12345')
            journal.reserve(old, old_context, old["baseline"], old["candidate"], parent, NOW)

            main = prepare_owned_change(host.context, host.assessment, host.scope, NOW,
                                       source_ref=MAIN_SOURCE_REF).packet
            owner_id = "fixture-owner"
            request = create_owned_workflow_request(main, owner_id, parent)
            context = PublisherContext(REPOSITORY, MAIN_SOURCE_REF, WORKFLOW,
                                       main["candidate"]["source_commit"], "1")
            journal.reserve(main, context, main["baseline"], main["candidate"], parent, NOW,
                            workflow_request=request, owner_id=owner_id)

            posts = []

            def public_get(url):
                raise OSError("fixture has no old occurrence")

            result = run_owned_workflow_bridge_once(
                state, env=self.runtime_env(state), now=datetime.now(timezone.utc),
                get=lambda *args: (200, b'{"workflow_runs": []}'),
                post=lambda *args: posts.append(args) or 204,
                public_get=public_get,mount_check=lambda path: True)

            self.assertEqual(result["status"], "RECONCILIATION_REQUIRED")
            self.assertEqual(posts, [])
            self.assertEqual(journal.workflow_dispatch_record(request.request_id).status, "READY")

    def test_prior_unverified_delivery_blocks_new_workflow_request(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            from test_digital_cycle_acceptance import CycleAcceptanceTests
            _, _, host, _ = CycleAcceptanceTests().prepare(state / "fixture")
            old = prepare_owned_change(host.context, host.assessment, host.scope, NOW).packet
            parent = host.git("rev-parse", "HEAD")
            old_context = PublisherContext(REPOSITORY, SOURCE_REF, WORKFLOW,
                                           old['candidate']['source_commit'], '12345')
            journal = OwnedEffectJournal(state / "cycle.sqlite")
            journal.reserve(old, old_context, old["baseline"], old["candidate"], parent, NOW)
            old_receipt = "d" * 40
            journal._present(old["effect_key"], old_receipt)
            journal.save_delivery(old["effect_key"], {
                "status": "PENDING", "effect_key": old["effect_key"],
                "receipt_ref": old_receipt,
                "candidate_sha256": old["candidate_sha256"],
                "observed_at": NOW.isoformat(), "proof_ref": "fixture-public-url",
                "proof_level": "P0", "reason": "FIXTURE_READBACK_PENDING",
            })

            main = prepare_owned_change(host.context, host.assessment, host.scope, NOW,
                                       source_ref=MAIN_SOURCE_REF).packet
            owner_id = "fixture-owner"
            request = create_owned_workflow_request(main, owner_id, parent)
            context = PublisherContext(REPOSITORY, MAIN_SOURCE_REF, WORKFLOW,
                                       main['candidate']['source_commit'], '1')
            journal.reserve(main, context, main['baseline'], main['candidate'], parent, NOW,
                            workflow_request=request, owner_id=owner_id)

            posts = []
            result = run_owned_workflow_bridge_once(
                state, env=self.runtime_env(state), now=datetime.now(timezone.utc),
                get=lambda *args: (200, b'{"workflow_runs": []}'),
                post=lambda *args: posts.append(args) or 204,
                public_get=lambda url: (_ for _ in ()).throw(OSError("read unavailable")),
                mount_check=lambda path: True)

            self.assertEqual(result["status"], "DELIVERY_RECONCILIATION_REQUIRED")
            self.assertEqual(posts, [])
            self.assertEqual(journal.workflow_dispatch_record(request.request_id).status, "READY")


if __name__ == "__main__":
    unittest.main()
