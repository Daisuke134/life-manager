"""The platform request is a bounded reference, never a transferable grant."""
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from manager_core.digital_handoff import MAIN_SOURCE_REF, SOURCE_REF, plan_release
from manager_core.owned_platform_host import (
    RuntimeConfigurationError,
    create_owned_workflow_request,
    dispatch_owned_workflow,
    observe_owned_workflow_run,
    parse_owned_workflow_request,
    read_railway_runtime_identity,
    read_github_ref_commit,
    validate_owned_workflow_request,
)
from test_candidate_verification import NOW


class OwnedPlatformRequestTests(unittest.TestCase):
    @staticmethod
    def packet(root):
        from test_digital_cycle_acceptance import CycleAcceptanceTests
        _, _, host, _ = CycleAcceptanceTests().prepare(root)
        from manager_core.digital_handoff import MAIN_SOURCE_REF, prepare_owned_change
        return prepare_owned_change(host.context, host.assessment, host.scope, NOW,
                                    source_ref=MAIN_SOURCE_REF).packet

    def test_request_is_stable_minimal_and_does_not_mint_authority(self):
        with TemporaryDirectory() as tmp:
            packet = self.packet(Path(tmp) / "fixture")
            first = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)
            second = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)
            from manager_core.digital_handoff import plan_release
            rebuilt = plan_release(packet["baseline"], packet["candidate"],
                                   NOW + timedelta(seconds=30), source_ref=MAIN_SOURCE_REF)
            rebuilt_request = create_owned_workflow_request(rebuilt, "manager-owner-1", "a" * 40)
            self.assertEqual(first, second)
            self.assertEqual(first, rebuilt_request)
            parsed = parse_owned_workflow_request(first.to_json())
            self.assertEqual(parsed, first)
            self.assertEqual(
                set(first.to_dict()),
                {"schema_version", "owner_id", "effect_key", "packet_sha256",
                 "source_commit", "expected_parent", "request_id"},
            )
            self.assertFalse(hasattr(first, "token"))
            self.assertFalse(hasattr(first, "authorized_execution"))
            self.assertEqual(
                validate_owned_workflow_request(
                    parsed, packet=packet, expected_owner_id="manager-owner-1",
                    current_parent="a" * 40,
                ),
                first,
            )

    def test_request_rejects_wrong_owner_packet_or_current_parent(self):
        with TemporaryDirectory() as tmp:
            packet = self.packet(Path(tmp) / "fixture")
            request = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)
            with self.assertRaises(PermissionError):
                validate_owned_workflow_request(
                    request, packet=packet, expected_owner_id="some-other-owner",
                    current_parent="a" * 40,
                )
            with self.assertRaises(PermissionError):
                validate_owned_workflow_request(
                    request, packet=packet, expected_owner_id="manager-owner-1",
                    current_parent="b" * 40,
                )
            changed = json.loads(request.to_json())
            changed["packet_sha256"] = "f" * 64
            changed["request_id"] = "0" * 64
            with self.assertRaises(ValueError):
                parse_owned_workflow_request(changed)

    def test_request_creation_rejects_legacy_research_source(self):
        with TemporaryDirectory() as tmp:
            main_packet = self.packet(Path(tmp) / "fixture")
            legacy_packet = plan_release(
                main_packet["baseline"], main_packet["candidate"], NOW,
                source_ref=SOURCE_REF)
            with self.assertRaises(ValueError):
                create_owned_workflow_request(legacy_packet, "manager-owner-1", "a" * 40)

    def test_request_rejects_extra_fields_duplicate_keys_and_malformed_bindings(self):
        with TemporaryDirectory() as tmp:
            packet = self.packet(Path(tmp) / "fixture")
            request = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)
            changed = request.to_dict()
            changed["callback_url"] = "https://attacker.invalid/callback"
            with self.assertRaises(ValueError):
                parse_owned_workflow_request(changed)
            changed = request.to_dict()
            changed["owner_id"] = ""
            with self.assertRaises(ValueError):
                parse_owned_workflow_request(changed)
            raw = request.to_json()
            with self.assertRaises(ValueError):
                parse_owned_workflow_request(raw[:-1] + ',"token":"secret"}')
            duplicate = raw[:-1] + ',"owner_id":"other"}'
            with self.assertRaises(ValueError):
                parse_owned_workflow_request(duplicate)
            for non_object in ('[]', '"text"', 'null', '7'):
                with self.subTest(non_object=non_object), self.assertRaises(ValueError):
                    parse_owned_workflow_request(non_object)
            with self.assertRaises(ValueError):
                parse_owned_workflow_request(' ' * 8193)

    def test_workflow_sender_uses_fixed_main_request_and_never_returns_credential(self):
        with TemporaryDirectory() as tmp:
            packet = self.packet(Path(tmp) / "fixture")
            packet = plan_release(packet["baseline"], packet["candidate"], NOW,
                                 source_ref=MAIN_SOURCE_REF)
            request = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)
            calls = []

            def post(url, headers, body, timeout):
                calls.append((url, headers, json.loads(body), timeout))
                return 204

            token = "fixture-token-never-returned"
            result = dispatch_owned_workflow(request, token=token, post=post)
            self.assertEqual(result.status, "ACCEPTED")
            self.assertEqual(result.request_id, request.request_id)
            self.assertEqual(len(calls), 1)
            url, headers, payload, timeout = calls[0]
            self.assertEqual(url, "https://api.github.com/repos/Daisuke134/life-manager/actions/workflows/manager-phase06-service.yml/dispatches")
            self.assertEqual(payload, {"ref": "main", "inputs": {
                "owned_request": request.to_json(), "request_id": request.request_id,
            }})
            self.assertEqual(headers["Authorization"], "Bearer " + token)
            self.assertEqual(timeout, 10)
            self.assertNotIn(token, repr(result))

    def test_workflow_sender_classifies_timeout_as_unknown_without_retry(self):
        with TemporaryDirectory() as tmp:
            packet = self.packet(Path(tmp) / "fixture")
            request = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)
            calls = []

            def post(*args):
                calls.append(args)
                raise TimeoutError("fixture timeout")

            result = dispatch_owned_workflow(request, token="fixture-token", post=post)
            self.assertEqual(result.status, "UNKNOWN")
            self.assertIsNone(result.http_status)
            self.assertEqual(len(calls), 1)

    def test_workflow_sender_rejects_definitive_http_denial(self):
        with TemporaryDirectory() as tmp:
            packet = self.packet(Path(tmp) / "fixture")
            request = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)
            result = dispatch_owned_workflow(request, token="fixture-token", post=lambda *args: 403)
            self.assertEqual(result.status, "REJECTED")
            self.assertEqual(result.http_status, 403)

    def test_workflow_run_readback_correlates_only_exact_request_sha_event_and_title(self):
        with TemporaryDirectory() as tmp:
            packet = self.packet(Path(tmp) / "fixture")
            from manager_core.digital_handoff import MAIN_SOURCE_REF, plan_release
            packet = plan_release(packet["baseline"], packet["candidate"], NOW,
                                 source_ref=MAIN_SOURCE_REF)
            request = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)
            run = {
                "id": 123456789,
                "status": "in_progress",
                "conclusion": None,
                "head_sha": request.source_commit,
                "head_branch": "main",
                "event": "workflow_dispatch",
                "display_title": "Manager owned request " + request.request_id,
                "html_url": "https://github.com/Daisuke134/life-manager/actions/runs/123456789",
            }
            calls = []

            def get(url, headers, timeout):
                calls.append((url, headers, timeout))
                return 200, json.dumps({"workflow_runs": [run]}).encode()

            result = observe_owned_workflow_run(request, token="fixture-token", get=get)
            self.assertEqual(result.status, "FOUND")
            self.assertEqual(result.run_id, 123456789)
            self.assertEqual(result.run_status, "in_progress")
            self.assertEqual(result.conclusion, None)
            self.assertEqual(len(calls), 1)
            self.assertIn("branch=main", calls[0][0])
            self.assertIn("event=workflow_dispatch", calls[0][0])
            self.assertIn("head_sha=" + request.source_commit, calls[0][0])

            wrong = {**run, "display_title": "Manager owned request " + "f" * 64}
            missing = observe_owned_workflow_run(
                request, token="fixture-token",
                get=lambda *args: (200, json.dumps({"workflow_runs": [wrong]}).encode()),
            )
            self.assertEqual(missing.status, "UNKNOWN")

            duplicate = observe_owned_workflow_run(
                request, token="fixture-token",
                get=lambda *args: (200, json.dumps({"workflow_runs": [run, run]}).encode()),
            )
            self.assertEqual(duplicate.status, "DUPLICATE")
            self.assertEqual(duplicate.matching_runs, 2)

    def test_workflow_run_lookup_timeout_remains_unknown(self):
        with TemporaryDirectory() as tmp:
            packet = self.packet(Path(tmp) / "fixture")
            request = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)

            def get(*args):
                raise TimeoutError("fixture timeout")

            result = observe_owned_workflow_run(request, token="fixture-token", get=get)
            self.assertEqual(result.status, "UNKNOWN")
            self.assertIsNone(result.run_id)

    def test_workflow_run_lookup_scans_bounded_pages_before_claiming_unique_match(self):
        with TemporaryDirectory() as tmp:
            packet = self.packet(Path(tmp) / "fixture")
            request = create_owned_workflow_request(packet, "manager-owner-1", "a" * 40)
            run = {
                "id": 123456789,
                "status": "completed",
                "conclusion": "success",
                "head_sha": request.source_commit,
                "head_branch": "main",
                "event": "workflow_dispatch",
                "display_title": "Manager owned request " + request.request_id,
                "html_url": "https://github.com/Daisuke134/life-manager/actions/runs/123456789",
            }
            filler = {**run, "display_title": "unrelated workflow"}
            calls = []

            def duplicate_on_second_page(url, headers, timeout):
                calls.append(url)
                if "page=1" in url:
                    return 200, json.dumps({"workflow_runs": [run] + [filler] * 99}).encode()
                return 200, json.dumps({"workflow_runs": [run]}).encode()

            duplicate = observe_owned_workflow_run(
                request, token="fixture-token", get=duplicate_on_second_page)
            self.assertEqual(duplicate.status, "DUPLICATE")
            self.assertEqual(duplicate.matching_runs, 2)
            self.assertEqual(len(calls), 2)

            calls.clear()

            def truncated_history(url, headers, timeout):
                calls.append(url)
                rows = ([run] + [filler] * 99) if url.endswith("page=1") else [filler] * 100
                return 200, json.dumps({"workflow_runs": rows}).encode()

            incomplete = observe_owned_workflow_run(
                request, token="fixture-token", get=truncated_history)
            self.assertEqual(incomplete.status, "UNKNOWN")
            self.assertEqual(len(calls), 10)

    def test_github_ref_reader_accepts_only_exact_manager_branches_and_commit_sha(self):
        sha = "c" * 40
        calls = []

        def get(url, headers, timeout):
            calls.append((url, headers, timeout))
            return 200, json.dumps({
                "ref": "refs/heads/gh-pages",
                "object": {
                    "sha": sha,
                    "type": "commit",
                    "url": "https://api.github.com/repos/Daisuke134/life-manager/git/commits/" + sha,
                },
            }).encode()

        observation = read_github_ref_commit("gh-pages", token="fixture-token", get=get)
        self.assertEqual((observation.status, observation.commit_sha), ("FOUND", sha))
        self.assertEqual(calls[0][0], "https://api.github.com/repos/Daisuke134/life-manager/git/ref/heads/gh-pages")
        self.assertEqual(calls[0][1]["Authorization"], "Bearer fixture-token")
        self.assertEqual(calls[0][2], 10)
        for branch in ("feature/other", "main/../../other"):
            with self.subTest(branch=branch), self.assertRaises(ValueError):
                read_github_ref_commit(branch, token="fixture-token")

    def runtime_environment(self, mount):
        return {
            "RAILWAY_PROJECT_ID": "project-123",
            "RAILWAY_ENVIRONMENT_ID": "environment-123",
            "RAILWAY_SERVICE_ID": "service-123",
            "RAILWAY_SERVICE_NAME": "manager-owned-digital-worker",
            "RAILWAY_DEPLOYMENT_ID": "deployment-123",
            "RAILWAY_VOLUME_NAME": "manager-owner-state",
            "RAILWAY_VOLUME_MOUNT_PATH": str(mount),
            "RAILWAY_GIT_REPO_OWNER": "Daisuke134",
            "RAILWAY_GIT_REPO_NAME": "life-manager",
            "RAILWAY_GIT_BRANCH": "main",
            "RAILWAY_GIT_COMMIT_SHA": "b" * 40,
            "MANAGER_OWNER_ENABLED": "true",
            "MANAGER_OWNER_ID": "manager-owner-1",
            "MANAGER_INTERVAL_SECONDS": "3600",
            "MANAGER_WORKFLOW_DISPATCH_TOKEN": "secret-must-not-escape-this-call",
        }

    def test_railway_runtime_identity_binds_main_release_and_persistent_owner(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            mount = root / "volume"
            source.mkdir(); mount.mkdir()
            env = self.runtime_environment(mount)
            identity = read_railway_runtime_identity(
                env, expected_project_id="project-123",
                expected_environment_id="environment-123",
                expected_service_id="service-123", expected_volume_name="manager-owner-state",
                source_root=source, state_root=mount,
                mount_check=lambda path: path == mount,
            )
            self.assertEqual(identity.source_commit, "b" * 40)
            self.assertEqual(identity.owner_id, "manager-owner-1")
            self.assertEqual(identity.interval_seconds, 3600)
            self.assertNotIn(env["MANAGER_WORKFLOW_DISPATCH_TOKEN"], repr(identity))

    def test_railway_runtime_rejects_wrong_branch_service_volume_or_source_path(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            mount = root / "volume"
            source.mkdir(); mount.mkdir()
            expected = dict(
                expected_project_id="project-123", expected_environment_id="environment-123",
                expected_service_id="service-123", expected_volume_name="manager-owner-state",
                source_root=source, state_root=mount, mount_check=lambda path: path == mount,
            )
            for key, value in (("RAILWAY_GIT_BRANCH", "research/branch"),
                               ("RAILWAY_GIT_REPO_OWNER", "attacker"),
                               ("RAILWAY_GIT_COMMIT_SHA", "not-a-commit"),
                               ("RAILWAY_SERVICE_ID", "other-service"),
                               ("RAILWAY_VOLUME_MOUNT_PATH", str(root / "other-volume"))):
                env = self.runtime_environment(mount); env[key] = value
                with self.subTest(key=key), self.assertRaises(RuntimeConfigurationError):
                    read_railway_runtime_identity(env, **expected)
            env = self.runtime_environment(mount)
            with self.assertRaises(RuntimeConfigurationError):
                read_railway_runtime_identity(
                    env, **{**expected, "source_root": mount / "source"}
                )
            env = self.runtime_environment(mount)
            nested = source / "nested-state"
            nested.mkdir()
            env["RAILWAY_VOLUME_MOUNT_PATH"] = str(nested)
            with self.assertRaises(RuntimeConfigurationError):
                read_railway_runtime_identity(
                    env, **{**expected, "state_root": nested, "mount_check": lambda path: path == nested}
                )

    def test_railway_runtime_requires_owner_switch_mount_and_dispatch_credential(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            mount = root / "volume"
            source.mkdir(); mount.mkdir()
            expected = dict(
                expected_project_id="project-123", expected_environment_id="environment-123",
                expected_service_id="service-123", expected_volume_name="manager-owner-state",
                source_root=source, state_root=mount, mount_check=lambda path: path == mount,
            )
            for key, value in (("MANAGER_OWNER_ENABLED", "false"),
                               ("MANAGER_WORKFLOW_DISPATCH_TOKEN", ""),
                               ("MANAGER_INTERVAL_SECONDS", "0")):
                env = self.runtime_environment(mount); env[key] = value
                with self.subTest(key=key), self.assertRaises(RuntimeConfigurationError):
                    read_railway_runtime_identity(env, **expected)
            env = self.runtime_environment(mount)
            with self.assertRaises(RuntimeConfigurationError):
                read_railway_runtime_identity(env, **{**expected, "mount_check": lambda _: False})


if __name__ == "__main__":
    unittest.main()
