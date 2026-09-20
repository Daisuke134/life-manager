import errno
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_runner import (
    CODEX_INVOCATION_HOME_MARKER,
    _OWNED_CODEX_INVOCATION_HOMES,
    ProviderLeaseBusy,
    provider_process_env,
    remove_incompatible_codex_model_cache,
    run_provider_process,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "agent_runner.py"


class ProviderLeaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _wait_for(self, path: Path, process: subprocess.Popen[str] | None = None) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if path.exists():
                return
            if process is not None and process.poll() is not None:
                self.fail(f"intermediate runtime exited rc={process.returncode}")
            time.sleep(0.02)
        self.fail(f"timed out waiting for {path}")

    def _lease_is_busy(self, lock_path: Path) -> bool:
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EACCES, errno.EAGAIN):
                    return True
                raise
            return False
        finally:
            os.close(descriptor)

    def test_provider_retains_lease_after_intermediate_runtime_is_killed(self):
        """Removing pass_fds must fail after the intermediate runtime is SIGKILLed."""
        lock_path = self.root / "mercor.lock"
        provider_started = self.root / "provider-started"
        provider_pid = self.root / "provider-pid"
        release = self.root / "release-provider"
        provider = self.root / "provider.py"
        provider.write_text(
            "import os, sys, time\n"
            "from pathlib import Path\n"
            "Path(sys.argv[1]).write_text(str(os.getpid()))\n"
            "Path(sys.argv[2]).touch()\n"
            "while not Path(sys.argv[3]).exists():\n"
            "    time.sleep(0.02)\n",
            encoding="utf-8",
        )
        runtime = self.root / "intermediate_runtime.py"
        runtime.write_text(
            "import fcntl, os, subprocess, sys\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from agent_runner import run_provider_process\n"
            "lock, provider, started, pid, release = map(Path, sys.argv[1:])\n"
            "fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)\n"
            "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "run_provider_process([sys.executable, str(provider), str(pid), str(started), str(release)], "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, cwd=str(lock.parent), "
            "input_bytes=None, stdin=subprocess.DEVNULL, env=os.environ.copy(), lease_fd=fd)\n",
            encoding="utf-8",
        )
        process = subprocess.Popen(
            [sys.executable, str(runtime), str(lock_path), str(provider), str(provider_started), str(provider_pid), str(release)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())
        self._wait_for(provider_started, process)
        self.assertTrue(self._lease_is_busy(lock_path), "provider holder was not exclusive")
        process.send_signal(signal.SIGKILL)
        process.wait(timeout=5)
        self.assertTrue(self._lease_is_busy(lock_path), "lease escaped when runtime was killed")
        release.touch()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self._lease_is_busy(lock_path):
            time.sleep(0.02)
        self.assertFalse(self._lease_is_busy(lock_path), "lease remained busy after provider exit")

    def test_shared_codex_home_queues_provider_processes_without_overlap(self):
        events = self.root / "events.jsonl"
        provider = self.root / "provider.py"
        provider.write_text(
            "import json, os, sys, time\n"
            "from pathlib import Path\n"
            "path = Path(sys.argv[1])\n"
            "with path.open('a') as handle: handle.write(json.dumps(['start', os.getpid()]) + '\\n')\n"
            "time.sleep(0.1)\n"
            "with path.open('a') as handle: handle.write(json.dumps(['end', os.getpid()]) + '\\n')\n",
            encoding="utf-8",
        )
        codex_home = self.root / "codex-home"
        codex_home.mkdir()
        env = {**os.environ, "CODEX_HOME": str(codex_home)}

        def run():
            try:
                return run_provider_process(
                    [sys.executable, str(provider), str(events)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5, cwd=str(self.root), input_bytes=None,
                    stdin=subprocess.DEVNULL, env=env,
                )
            except ProviderLeaseBusy:
                return "busy"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [future.result() for future in (executor.submit(run), executor.submit(run))]

        rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(results, [0, 0])
        self.assertEqual([row[0] for row in rows], ["start", "end", "start", "end"])

    def test_stable_provider_completion_fallback_is_sealed_to_result_path(self):
        fallback = self.root / "pass-result.json"
        result = self.root / "attempt-01.result.json"
        provider = self.root / "provider.py"
        provider.write_text(
            "import sys, time\n"
            "from pathlib import Path\n"
            "Path(sys.argv[1]).write_text('{\"status\":\"needs_human\"}\\n')\n"
            "while True:\n"
            "    time.sleep(1)\n",
            encoding="utf-8",
        )

        rc = run_provider_process(
            [sys.executable, str(provider), str(fallback)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            cwd=str(self.root),
            input_bytes=None,
            stdin=subprocess.DEVNULL,
            env=os.environ.copy(),
            completion_path=result,
            completion_paths=(fallback,),
        )

        self.assertEqual(rc, 0)
        self.assertEqual(result.read_text(encoding="utf-8"), fallback.read_text(encoding="utf-8"))

    def test_codex_invocations_use_isolated_homes_and_cleanup(self):
        automation_home = self.root / "codex-profile"
        auth_file = self.root / "profile-auth.json"
        auth_file.write_text("{}\n", encoding="utf-8")
        provider = self.root / "provider.py"
        provider.write_text(
            "import sys, time\n"
            "from pathlib import Path\n"
            "own, peer = map(Path, sys.argv[1:3])\n"
            "own.touch()\n"
            "while not peer.exists():\n"
            "    time.sleep(0.01)\n",
            encoding="utf-8",
        )
        base_env = {"PATH": os.environ.get("PATH", "")}
        provider_config = {
            "automation_home": str(automation_home),
            "auth_file": str(auth_file),
        }
        invocation_ids = ("invocation-a", "invocation-b")
        envs = [
            provider_process_env(
                "codex", provider_config, base_env, invocation_id=invocation_id,
            )
            for invocation_id in invocation_ids
        ]
        homes = [Path(env["CODEX_HOME"]) for env in envs]
        self.assertEqual(
            homes,
            [automation_home / "invocations" / invocation_id for invocation_id in invocation_ids],
        )
        for home in homes:
            self.assertEqual((home / "auth.json").resolve(), auth_file.resolve())

        markers = [self.root / "provider-a", self.root / "provider-b"]

        def run(env, own, peer):
            try:
                return run_provider_process(
                    [sys.executable, str(provider), str(own), str(peer)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1,
                    cwd=str(self.root),
                    input_bytes=None,
                    stdin=subprocess.DEVNULL,
                    env=env,
                )
            except Exception as error:
                return f"{type(error).__name__}: {error}"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result()
                for future in (
                    executor.submit(run, envs[0], markers[0], markers[1]),
                    executor.submit(run, envs[1], markers[1], markers[0]),
                )
            ]

        self.assertEqual(results, [0, 0])
        self.assertTrue(all(marker.exists() for marker in markers))
        self.assertTrue(automation_home.is_dir())
        self.assertTrue(auth_file.is_file())
        self.assertTrue(all(not home.exists() for home in homes))

    def test_codex_invocation_leaf_must_be_new_and_preserves_existing_paths(self):
        automation_home = self.root / "codex-profile"
        automation_home.mkdir()
        auth_file = self.root / "profile-auth.json"
        auth_file.write_text("{}\n", encoding="utf-8")
        invocations_home = automation_home / "invocations"
        invocations_home.mkdir()

        existing_dir = invocations_home / "existing-dir"
        existing_dir.mkdir()
        dir_sentinel = existing_dir / "sentinel"
        dir_sentinel.write_text("directory\n", encoding="utf-8")

        existing_file = invocations_home / "existing-file"
        existing_file.write_text("file\n", encoding="utf-8")

        symlink_target = self.root / "symlink-target"
        symlink_target.mkdir()
        symlink_sentinel = symlink_target / "sentinel"
        symlink_sentinel.write_text("symlink\n", encoding="utf-8")
        existing_symlink = invocations_home / "existing-symlink"
        existing_symlink.symlink_to(symlink_target, target_is_directory=True)

        provider_config = {
            "automation_home": str(automation_home),
            "auth_file": str(auth_file),
        }
        for invocation_id, sentinel in (
            ("existing-dir", dir_sentinel),
            ("existing-file", existing_file),
            ("existing-symlink", symlink_sentinel),
        ):
            with self.subTest(invocation_id=invocation_id):
                with self.assertRaisesRegex(ValueError, "invocation_id"):
                    provider_process_env(
                        "codex", provider_config, {"PATH": os.environ.get("PATH", "")},
                        invocation_id=invocation_id,
                    )
                self.assertTrue(sentinel.exists())
                self.assertNotIn(
                    (invocations_home / invocation_id).resolve(),
                    _OWNED_CODEX_INVOCATION_HOMES,
                )
        self.assertTrue(existing_symlink.is_symlink())
        self.assertTrue(symlink_sentinel.is_file())

    def test_unregistered_codex_home_marker_preserves_caller_home(self):
        caller_home = self.root / "caller-codex-home"
        caller_home.mkdir()
        sentinel = caller_home / "sentinel"
        sentinel.write_text("keep\n", encoding="utf-8")
        provider = self.root / "provider.py"
        provider.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "Path(sys.argv[1]).touch()\n",
            encoding="utf-8",
        )
        result = run_provider_process(
            [sys.executable, str(provider), str(self.root / "provider-ran")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            cwd=str(self.root),
            input_bytes=None,
            stdin=subprocess.DEVNULL,
            env={
                **os.environ,
                "CODEX_HOME": str(caller_home),
                CODEX_INVOCATION_HOME_MARKER: str(caller_home),
            },
        )
        self.assertEqual(result, 0)
        self.assertTrue(sentinel.is_file())
        self.assertTrue(caller_home.is_dir())

    def test_shared_codex_home_busy_until_deadline_raises_without_launching_provider(self):
        lock_path = self.root / "codex-home" / ".agent-runner-provider.lock"
        lock_path.parent.mkdir()
        holder = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(lambda: os.close(holder))
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker = self.root / "provider-launched"
        provider = self.root / "provider.py"
        provider.write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).touch()\n",
            encoding="utf-8",
        )
        started = time.monotonic()
        with self.assertRaises(ProviderLeaseBusy):
            run_provider_process(
                [sys.executable, str(provider)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                deadline=started + 0.2, cwd=str(self.root), input_bytes=None,
                stdin=subprocess.DEVNULL, env={**os.environ, "CODEX_HOME": str(lock_path.parent)},
            )
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 0.15)
        self.assertLess(elapsed, 1)
        self.assertFalse(marker.exists(), "timed-out lock wait launched a provider")

    def test_shared_codex_home_late_lock_acquisition_is_busy_without_launching_provider(self):
        lock_path = self.root / "codex-home" / ".agent-runner-provider.lock"
        lock_path.parent.mkdir()
        holder = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(lambda: os.close(holder))
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker = self.root / "provider-launched"
        provider = self.root / "provider.py"
        provider.write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).touch()\n",
            encoding="utf-8",
        )
        deadline = 1.0
        now = 0.0
        released = False

        def monotonic():
            return now

        def release_after_deadline(_duration):
            nonlocal now, released
            now = deadline + 0.01
            fcntl.flock(holder, fcntl.LOCK_UN)
            released = True

        with mock.patch("agent_runner.time.monotonic", side_effect=monotonic):
            with mock.patch("agent_runner.time.sleep", side_effect=release_after_deadline):
                with self.assertRaises(ProviderLeaseBusy):
                    run_provider_process(
                        [sys.executable, str(provider)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                        deadline=deadline, cwd=str(self.root), input_bytes=None,
                        stdin=subprocess.DEVNULL, env={"CODEX_HOME": str(lock_path.parent)},
                    )
        self.assertTrue(released)
        self.assertFalse(marker.exists(), "late lock acquisition launched a provider")

    def test_expired_deadline_after_preflight_does_not_launch_provider(self):
        codex_home = self.root / "codex-home"
        codex_home.mkdir()
        marker = self.root / "provider-launched"
        provider = self.root / "provider.py"
        provider.write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).touch()\n",
            encoding="utf-8",
        )
        env = {**os.environ, "CODEX_HOME": str(codex_home)}

        with mock.patch(
            "agent_runner.remove_incompatible_codex_model_cache",
            side_effect=lambda _path: time.sleep(0.1),
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                run_provider_process(
                    [sys.executable, str(provider)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                    deadline=time.monotonic() + 0.02, cwd=str(self.root),
                    input_bytes=None, stdin=subprocess.DEVNULL, env=env,
                )
        self.assertFalse(marker.exists(), "expired total deadline launched a provider")

    def test_incompatible_codex_model_cache_is_removed_for_regeneration(self):
        codex_home = self.root / "codex-home"
        codex_home.mkdir()
        cache = codex_home / "models_cache.json"
        cache.write_text(json.dumps({"models": [{"slug": "gpt", "description": "stale"}]}), encoding="utf-8")

        self.assertTrue(remove_incompatible_codex_model_cache(codex_home))
        self.assertFalse(cache.exists())

    def test_compatible_codex_model_cache_is_preserved(self):
        codex_home = self.root / "codex-home"
        codex_home.mkdir()
        cache = codex_home / "models_cache.json"
        cache.write_text(json.dumps({"models": [{"slug": "gpt", "base_instructions": ""}]}), encoding="utf-8")

        self.assertFalse(remove_incompatible_codex_model_cache(codex_home))
        self.assertTrue(cache.exists())

    def test_contended_provider_lease_returns_75_without_launching_provider(self):
        """Removing the rc 75 boundary must launch the stub provider and fail this test."""
        lock_path = self.root / "mercor.lock"
        holder = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(lambda: os.close(holder))
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker = self.root / "provider-launched"
        provider = self.root / "claude"
        provider.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).touch()\n"
            "print('{\"result\": \"{\\\"status\\\":\\\"ok\\\"}\"}')\n",
            encoding="utf-8",
        )
        provider.chmod(0o755)
        schema = self.root / "schema.json"
        schema.write_text('{"type":"object","required":["status"]}', encoding="utf-8")
        prompt = self.root / "prompt.txt"
        prompt.write_text("Return the bounded contract JSON only.\n", encoding="utf-8")
        config = self.root / "config.json"
        config.write_text(json.dumps({
            "version": 1,
            "timeout_seconds": 5,
            "providers": {"claude-direct": {"executable": str(provider)}},
            "task_classes": {"tool-agent": {"candidates": [
                {"provider": "claude-direct", "model": "sonnet"}
            ]}},
        }), encoding="utf-8")
        env = {
            **os.environ,
            "AGENT_RUNNER_CONFIG": str(config),
            "ANICCA_USAGE_LEDGER": str(self.root / "usage.jsonl"),
            "LIFE_MANAGER_PROVIDER_LEASE_PATH": str(lock_path),
        }
        result = subprocess.run([
            sys.executable, str(RUNNER), "--task-class", "tool-agent",
            "--prompt-file", str(prompt), "--schema", str(schema),
            "--evidence-dir", str(self.root / "evidence"), "--task-label", "mercor",
            "--loop", "job-search", "--workdir", str(self.root),
        ], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 75, result.stderr)
        self.assertEqual(result.stderr, "LIFE_MANAGER_PROVIDER_LEASE_BUSY\n")
        self.assertFalse(marker.exists(), "contended lease launched a provider")


if __name__ == "__main__":
    unittest.main()
