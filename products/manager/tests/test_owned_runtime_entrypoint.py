"""The Railway cron entry validates its mount before dropping root privileges."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import os
import unittest
from unittest.mock import patch

from manager_core.owned_platform_host import RuntimeConfigurationError
from scripts import owned_runtime_entrypoint as entrypoint


class OwnedRuntimeEntrypointTests(unittest.TestCase):
    def env(self):
        return {
            "RAILWAY_PROJECT_ID": "project-123",
            "RAILWAY_ENVIRONMENT_ID": "environment-123",
            "RAILWAY_SERVICE_ID": "service-123",
            "RAILWAY_SERVICE_NAME": "manager-owned-digital-worker",
            "RAILWAY_DEPLOYMENT_ID": "deployment-123",
            "RAILWAY_VOLUME_NAME": "manager-owner-state",
            "RAILWAY_VOLUME_MOUNT_PATH": "/data/manager",
            "RAILWAY_GIT_REPO_OWNER": "Daisuke134",
            "RAILWAY_GIT_REPO_NAME": "life-manager",
            "RAILWAY_GIT_BRANCH": "main",
            "RAILWAY_GIT_COMMIT_SHA": "b" * 40,
            "MANAGER_OWNER_ENABLED": "true",
            "MANAGER_OWNER_ID": "manager-owner-1",
            "MANAGER_INTERVAL_SECONDS": "3600",
            "MANAGER_WORKFLOW_DISPATCH_TOKEN": "private-test-token",
            "MANAGER_EXPECTED_RAILWAY_PROJECT_ID": "project-123",
            "MANAGER_EXPECTED_RAILWAY_ENVIRONMENT_ID": "environment-123",
            "MANAGER_EXPECTED_RAILWAY_SERVICE_ID": "service-123",
            "MANAGER_EXPECTED_RAILWAY_VOLUME_NAME": "manager-owner-state",
            "MANAGER_STATE_ROOT": "/data/manager",
        }

    def test_host_preflight_failure_never_chowns_volume_or_executes_worker(self):
        output = StringIO()
        with TemporaryDirectory() as tmp, \
             patch.object(entrypoint, "STATE_ROOT", Path(tmp)), \
             patch.dict(os.environ, self.env(), clear=True), \
             patch.object(entrypoint, "read_railway_runtime_identity",
                          side_effect=RuntimeConfigurationError("private-test-token invalid")), \
             patch.object(entrypoint.os, "geteuid", return_value=0), \
             patch.object(entrypoint.os, "chown") as chown, \
             patch.object(entrypoint.os, "execve") as execve, \
             patch("sys.stdout", output):
            self.assertEqual(entrypoint.main(), 2)
        self.assertEqual(chown.call_count, 0)
        self.assertEqual(execve.call_count, 0)
        self.assertNotIn("private-test-token", output.getvalue())
        self.assertIn('"status": "DEPLOYMENT_HOST_REQUIRED"', output.getvalue())

    def test_valid_mount_drops_privileges_before_execing_finite_worker(self):
        calls = []
        account = SimpleNamespace(pw_uid=10001, pw_gid=10001)

        def record(name):
            return lambda *args: calls.append((name, *args))

        with TemporaryDirectory() as tmp, \
             patch.object(entrypoint, "STATE_ROOT", Path(tmp)), \
             patch.dict(os.environ, self.env(), clear=True), \
             patch.object(entrypoint, "read_railway_runtime_identity",
                          return_value=SimpleNamespace(owner_enabled=True,
                                                       dispatch_token_available=True)) as preflight, \
             patch.object(entrypoint.os, "geteuid", return_value=0), \
             patch.object(entrypoint.pwd, "getpwnam", return_value=account), \
             patch.object(entrypoint.os, "chown", side_effect=record("chown")), \
             patch.object(entrypoint.os, "setgroups", side_effect=record("setgroups")), \
             patch.object(entrypoint.os, "setgid", side_effect=record("setgid")), \
             patch.object(entrypoint.os, "setuid", side_effect=record("setuid")), \
             patch.object(entrypoint.os, "execve", side_effect=RuntimeError("exec boundary")) as execve:
            with self.assertRaisesRegex(RuntimeError, "exec boundary"):
                entrypoint.main()

        preflight.assert_called_once()
        self.assertEqual([call[0] for call in calls],
                         ["chown", "setgroups", "setgid", "setuid"])
        argv = execve.call_args.args[1]
        self.assertEqual(argv[-2:], ["--state-store", str(Path(tmp))])
        self.assertEqual(execve.call_args.args[0], argv[0])
        self.assertEqual(execve.call_args.args[2]["MANAGER_WORKFLOW_DISPATCH_TOKEN"],
                         "private-test-token")

    def test_disabled_owner_drops_privileges_without_chown_then_runs_read_only_worker(self):
        calls = []
        account = SimpleNamespace(pw_uid=10001, pw_gid=10001)
        env = self.env()
        env["MANAGER_OWNER_ENABLED"] = "false"
        env.pop("MANAGER_WORKFLOW_DISPATCH_TOKEN")

        def record(name):
            return lambda *args: calls.append((name, *args))

        identity = SimpleNamespace(owner_enabled=False, dispatch_token_available=False)
        with TemporaryDirectory() as tmp, \
             patch.object(entrypoint, "STATE_ROOT", Path(tmp)), \
             patch.dict(os.environ, env, clear=True), \
             patch.object(entrypoint, "read_railway_runtime_identity", return_value=identity) as preflight, \
             patch.object(entrypoint.os, "geteuid", return_value=0), \
             patch.object(entrypoint.pwd, "getpwnam", return_value=account), \
             patch.object(entrypoint.os, "chown", side_effect=record("chown")) as chown, \
             patch.object(entrypoint.os, "setgroups", side_effect=record("setgroups")), \
             patch.object(entrypoint.os, "setgid", side_effect=record("setgid")), \
             patch.object(entrypoint.os, "setuid", side_effect=record("setuid")), \
             patch.object(entrypoint.os, "execve", side_effect=RuntimeError("exec boundary")) as execve:
            with self.assertRaisesRegex(RuntimeError, "exec boundary"):
                entrypoint.main()

        self.assertTrue(preflight.call_args.kwargs["allow_read_only_recovery"])
        chown.assert_not_called()
        self.assertEqual([call[0] for call in calls], ["setgroups", "setgid", "setuid"])
        self.assertNotIn("MANAGER_WORKFLOW_DISPATCH_TOKEN", execve.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
