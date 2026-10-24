import json
import plistlib
import fcntl
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

import runtime.loop.lm_loop_run as lm_loop_run
from runtime.loop.loop_cleanup import cleanup_run_root, gc_releases
from runtime.loop.lm_loop_run import build_loop_command
from runtime.loop.runtime_event import validate_runtime_event
from runtime.loop.central_cleanup import installed_state_roots, loaded_release_roots
from runtime.loop.central_cleanup import no_effect_loop_ids, open_release_roots, release_gc, scratch_gc
from runtime.loop import central_cleanup
from runtime.loop import loop_cleanup


def completed(root: Path, name: str, size: int = 1) -> Path:
    run = root / "runs" / name; run.mkdir(parents=True)
    (run / ".lm-regenerable").write_text("1\n")
    (run / "summary.json").write_text("{}\n")
    (run / "payload.bin").write_bytes(b"x" * size)
    return run


class NativeCodexCompressionTest(unittest.TestCase):
    def fixture(self, home):
        import socket
        root = home / ".codex-acct2"
        sessions = root / "sessions/2026/01/01"
        sessions.mkdir(parents=True)
        history = sessions / "rollout-fixture.jsonl"
        history.write_text("retained original history\n")
        os.utime(history, (1, 1))
        control = root / "app-server-control"
        control.mkdir()
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(control / "app-server-control.sock"))
        os.chmod(control / "app-server-control.sock", 0o600)
        self.addCleanup(sock.close)
        return root, history

    def fake_connection(self, root, sent, **changes):
        class Connection:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): return False
            async def send(self, text): sent.append(json.loads(text))
            async def recv(self):
                request = next(v for v in reversed(sent) if "id" in v)
                result = {"codexHome": str(root), "userAgent": "Codex Desktop/0.160.0 test"}
                result.update(changes)
                return json.dumps({"id": request["id"], "result": result if request["id"] == 1 else {}})
        return lambda *_args, **_kwargs: Connection()

    def test_native_compression_delegates_without_rewriting_history(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            home = Path(directory); root, history = self.fixture(home); sent = []
            result = central_cleanup.codex_history_cleanup(home, connect=self.fake_connection(root, sent))
            self.assertEqual(result["status"], "requested")
            self.assertEqual([v["method"] for v in sent], ["initialize", "initialized", "rollout/compress"])
            self.assertIsNone(sent[-1]["params"])
            self.assertEqual(history.read_text(), "retained original history\n")
            self.assertNotIn("reclaimed_bytes", result)

    def test_native_compression_keeps_unsafe_and_recent_data(self):
        for condition in ["recent", "warm", "temporary", "memory", "outside_link", "capacity", "version", "home"]:
            with self.subTest(condition=condition), tempfile.TemporaryDirectory(dir="/tmp") as directory:
                home = Path(directory); root, history = self.fixture(home); sent = []; changes = {}
                if condition == "recent":
                    (root / ".tmp").mkdir(); (root / ".tmp/rollout-compression.lock").write_text("native marker")
                elif condition == "warm": os.utime(history, None)
                elif condition == "temporary": (history.parent / "unknown.tmp").write_text("keep")
                elif condition == "memory":
                    (history.parent / "memory").mkdir(); (history.parent / "memory/primary.jsonl").write_text("keep")
                elif condition == "outside_link": (history.parent / "foreign.jsonl").symlink_to(history)
                elif condition == "version": changes["userAgent"] = "Codex Desktop/0.999.0"
                elif condition == "home": changes["codexHome"] = str(home / "other")
                connection = self.fake_connection(root, sent, **changes)
                with mock.patch("shutil.disk_usage", return_value=mock.Mock(free=1 if condition == "capacity" else 4 * 1024**3)):
                    result = central_cleanup.codex_history_cleanup(home, connect=connection)
                self.assertNotEqual(result["status"], "requested")
                self.assertTrue(history.exists())
                self.assertNotIn("rollout/compress", [v["method"] for v in sent])


class LoopCleanupTest(unittest.TestCase):
    def setUp(self):
        # The real disk gate reads this host's free space against a 12 GiB floor; keep it
        # out of these tests, as test_lm_loop_run_bounds.py does.
        gate = mock.patch("runtime.loop.lm_loop_run._producer_gate", return_value=None)
        gate.start()
        self.addCleanup(gate.stop)

    def test_main_stdout_keeps_loaded_binding_and_standalone_none(self):
        expected = {"owner_id": "life-manager-disk-cleanup", "run_id": "run-1",
            "occurrence_id": "life-manager-disk-cleanup:run-1",
            "release_sha": "a" * 40}
        env = {"LIFE_MANAGER_RUN_ID": "run-1",
            "LIFE_MANAGER_OCCURRENCE_ID": "life-manager-disk-cleanup:run-1",
            "LIFE_MANAGER_RELEASE_SHA": "b" * 40}
        for context, binding in ((env, expected), ({}, None)):
            with self.subTest(bound=bool(context)), \
                 mock.patch.dict(os.environ, context, clear=True), \
                 mock.patch.object(central_cleanup, "ROOT", Path("/private-binding-fixture")), \
                 mock.patch.object(Path, "read_text", return_value=json.dumps({"sha": "a" * 40})), \
                 mock.patch.object(central_cleanup, "git_duplicate_cleanup", return_value={"errors": 0}), \
                 mock.patch.object(central_cleanup, "codex_history_cleanup", return_value={"status": "fixture"}), \
                 mock.patch.object(central_cleanup, "release_gc", return_value={"errors": 0}), \
                 mock.patch.object(central_cleanup, "scratch_gc", return_value={"errors": 0}), \
                 mock.patch.object(central_cleanup, "installed_state_roots", return_value=[]), \
                 mock.patch.object(central_cleanup, "process_starts", return_value={}), \
                 mock.patch.object(central_cleanup, "no_effect_loop_ids", return_value=set()), \
                 mock.patch.object(central_cleanup, "closed_reconcile_occurrences", return_value={}), \
                 mock.patch.object(central_cleanup.subprocess, "run",
                     side_effect=AssertionError("fixture invoked a native subprocess")), \
                 mock.patch.object(sys, "argv", ["central_cleanup.py"]), \
                 mock.patch("builtins.print") as output:
                self.assertEqual(central_cleanup.main(), 0)
                result = json.loads(output.call_args.args[0])
                self.assertIn("run_binding", result)
                self.assertEqual(result["run_binding"], binding)

    def test_native_git_duplicate_cleanup_preserves_primary_data_and_replays_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args):
                return subprocess.run(["git", "-C", str(repo), *args],
                    check=True, capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            primary = repo / "state" / "receipt.jsonl"
            primary.parent.mkdir()
            primary.write_text("retained primary record\n")
            git("add", "state/receipt.jsonl")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-qm", "primary record")
            head = git("rev-parse", "HEAD")
            branch = git("symbolic-ref", "HEAD")
            git("pack-objects", "--all", str(repo / ".git/objects/pack/pack"))
            primary.write_text("retained primary record\nactive uncommitted update\n")
            untracked = repo / "memory"
            untracked.mkdir()
            (untracked / "kept.txt").write_text("retained memory\n")
            dirty = git("status", "--porcelain")

            result = central_cleanup.git_duplicate_cleanup(repo)
            self.assertEqual(result["errors"], 0)
            self.assertGreater(result["prune_packable_before"], 0)
            self.assertEqual(result["prune_packable_after"], 0)
            self.assertEqual(git("rev-parse", "HEAD"), head)
            self.assertEqual(git("symbolic-ref", "HEAD"), branch)
            self.assertEqual(git("show", "HEAD:state/receipt.jsonl"), "retained primary record")
            self.assertEqual(git("status", "--porcelain"), dirty)
            self.assertTrue(primary.read_text().endswith("active uncommitted update\n"))
            self.assertEqual((untracked / "kept.txt").read_text(), "retained memory\n")
            replay = central_cleanup.git_duplicate_cleanup(repo)
            self.assertEqual(replay["prune_packable_before"], 0)
            self.assertEqual(replay["prune_packable_after"], 0)

    def test_native_git_cleanup_packs_loose_objects_without_losing_work(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args, **kwargs):
                return subprocess.run(["git", "-C", str(repo), *args],
                    check=True, capture_output=True, text=True, **kwargs).stdout.strip()
            git("init", "-q")
            (repo / "source.txt").write_text("committed source\n")
            git("add", "source.txt")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-qm", "source")
            head, branch = git("rev-parse", "HEAD"), git("symbolic-ref", "HEAD")
            objects = [git("hash-object", "-w", "--stdin", input=f"retained blob {i}\n")
                       for i in range(110)]
            (repo / "source.txt").write_text("active source change\n")
            (repo / "memory").mkdir()
            (repo / "memory/keep.txt").write_text("retained memory\n")
            dirty = git("status", "--porcelain")
            result = central_cleanup.git_duplicate_cleanup(repo)
            self.assertEqual(result["errors"], 0)
            counts = dict(line.split(": ", 1) for line in git("count-objects", "-v").splitlines())
            self.assertGreaterEqual(int(counts["in-pack"]), len(objects))
            self.assertEqual(int(counts["count"]), 0)
            for i, oid in enumerate(objects):
                self.assertEqual(git("cat-file", "blob", oid), f"retained blob {i}")
            self.assertEqual(git("rev-parse", "HEAD"), head)
            self.assertEqual(git("symbolic-ref", "HEAD"), branch)
            self.assertEqual(git("status", "--porcelain"), dirty)
            self.assertEqual((repo / "source.txt").read_text(), "active source change\n")
            self.assertEqual((repo / "memory/keep.txt").read_text(), "retained memory\n")
            replay = central_cleanup.git_duplicate_cleanup(repo)
            self.assertEqual(replay["errors"], 0)
            self.assertEqual(replay["prune_packable_after"], 0)

    def test_native_git_duplicate_cleanup_skips_absent_source_checkout(self):
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(central_cleanup.subprocess, "run") as run:
            result = central_cleanup.git_duplicate_cleanup(Path(directory))
            self.assertEqual(result["status"], "not_applicable")
            self.assertEqual(result["errors"], 0)
            run.assert_not_called()

    def test_native_git_cleanup_handles_few_objects_under_byte_pressure_and_replays_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            native_run = subprocess.run
            def git(*args, **kwargs):
                return native_run(["git", "-C", str(repo), *args],
                    check=True, capture_output=True, text=True, **kwargs).stdout.strip()
            git("init", "-q")
            (repo / "source.txt").write_text("committed source\n")
            git("add", "source.txt")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-qm", "source")
            head, branch = git("rev-parse", "HEAD"), git("symbolic-ref", "HEAD")
            objects = [git("hash-object", "-w", "--stdin", input=f"retained blob {i}\n")
                       for i in range(3)]
            (repo / "source.txt").write_text("active source change\n")
            (repo / "memory").mkdir()
            (repo / "memory/keep.txt").write_text("retained memory\n")
            dirty = git("status", "--porcelain")
            commands = []
            native_entrypoint = lm_loop_run._run_entrypoint
            def byte_pressure(command, **kwargs):
                commands.append(command)
                if command[0] == "git":
                    self.assertEqual(kwargs["env"]["LC_ALL"], "C")
                completed = native_run(command, **kwargs)
                if command[-2:] == ["count-objects", "-v"]:
                    counts = dict(line.split(": ", 1) for line in completed.stdout.splitlines())
                    if int(counts["count"]):
                        # Exercise 128 MiB policy without allocating a large disk fixture.
                        completed.stdout = "\n".join(
                            "size: 131072" if line.startswith("size: ") else line
                            for line in completed.stdout.splitlines()) + "\n"
                return completed
            def maintenance(command, **kwargs):
                commands.append(command)
                self.assertEqual(kwargs["env"]["LC_ALL"], "C")
                return native_entrypoint(command, **kwargs)
            with mock.patch.object(central_cleanup.subprocess, "run", side_effect=byte_pressure), \
                 mock.patch.object(lm_loop_run, "_run_entrypoint", side_effect=maintenance):
                result = central_cleanup.git_duplicate_cleanup(repo)
                counts = dict(line.split(": ", 1) for line in git("count-objects", "-v").splitlines())
                self.assertEqual(int(counts["count"]), 0)
                self.assertEqual(result["status"], "pass")
                self.assertEqual(result["loose_bytes_before"], 134217728)
                self.assertEqual(result["loose_bytes_after"], 0)
                packed = {path.name: path.stat().st_mtime_ns for path in (repo / ".git/objects/pack").iterdir()}
                replay = central_cleanup.git_duplicate_cleanup(repo)
            self.assertEqual(replay["status"], "pass")
            self.assertEqual(packed, {path.name: path.stat().st_mtime_ns for path in (repo / ".git/objects/pack").iterdir()})
            maintenance = [command for command in commands if "maintenance" in command]
            self.assertNotIn("--auto", maintenance[0])
            self.assertIn("--auto", maintenance[1])
            for i, oid in enumerate(objects):
                self.assertEqual(git("cat-file", "blob", oid), f"retained blob {i}")
            self.assertEqual(git("rev-parse", "HEAD"), head)
            self.assertEqual(git("symbolic-ref", "HEAD"), branch)
            self.assertEqual(git("status", "--porcelain"), dirty)
            self.assertEqual((repo / "source.txt").read_text(), "active source change\n")
            self.assertEqual((repo / "memory/keep.txt").read_text(), "retained memory\n")

    def test_native_git_cleanup_defers_skipped_maintenance_and_preserves_unknown_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args, **kwargs):
                return subprocess.run(["git", "-C", str(repo), *args],
                    check=True, capture_output=True, text=True, **kwargs).stdout.strip()
            git("init", "-q")
            oid = git("hash-object", "-w", "--stdin", input="retained unreachable blob\n")
            lock = repo / ".git/objects/maintenance.lock"
            lock.write_text("unknown owner\n")
            identity = lock.stat().st_ino
            counts = git("count-objects", "-v")
            result = central_cleanup.git_duplicate_cleanup(repo)
            self.assertEqual(result["status"], "deferred")
            self.assertEqual(result["errors"], 0)
            self.assertEqual(result["error_class"], "NativeMaintenanceSkipped")
            self.assertTrue(result["retryable"])
            self.assertEqual(result["next_action"], "retry_next_natural_pass")
            self.assertIsNone(result["prune_packable_after"])
            self.assertIsNone(result["loose_bytes_after"])
            self.assertEqual(lock.stat().st_ino, identity)
            self.assertEqual(lock.read_text(), "unknown owner\n")
            self.assertEqual(git("count-objects", "-v"), counts)
            self.assertEqual(git("cat-file", "blob", oid), "retained unreachable blob")

    def test_native_git_cleanup_prunes_packed_duplicates_before_deferred_maintenance(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args, **kwargs):
                return subprocess.run(["git", "-C", str(repo), *args],
                    check=True, capture_output=True, text=True, **kwargs).stdout.strip()
            git("init", "-q")
            source = repo / "source.txt"
            source.write_text("committed source\n")
            git("add", "source.txt")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "-qm", "source")
            head, refs = git("rev-parse", "HEAD"), git("show-ref")
            git("pack-objects", "--all", str(repo / ".git/objects/pack/pack"))
            unique = git("hash-object", "-w", "--stdin", input="retained unreachable blob\n")
            source.write_text("active source change\n")
            (repo / "memory").mkdir()
            (repo / "memory/keep.txt").write_text("retained memory\n")
            dirty = git("status", "--porcelain")
            lock = repo / ".git/objects/maintenance.lock"
            lock.write_text("unknown owner\n")
            identity = lock.stat().st_ino

            result = central_cleanup.git_duplicate_cleanup(repo)
            counts = dict(line.split(": ", 1) for line in git("count-objects", "-v").splitlines())
            self.assertGreater(result["prune_packable_before"], 0)
            self.assertEqual(int(counts["prune-packable"]), 0)
            self.assertEqual(int(counts["count"]), 1)
            self.assertEqual(result["status"], "deferred")
            self.assertEqual(result["errors"], 0)
            self.assertEqual(result["error_class"], "NativeMaintenanceSkipped")
            self.assertTrue(result["retryable"])
            self.assertEqual(result["next_action"], "retry_next_natural_pass")
            self.assertIsNone(result["prune_packable_after"])
            self.assertIsNone(result["loose_bytes_after"])
            self.assertEqual(lock.stat().st_ino, identity)
            self.assertEqual(lock.read_text(), "unknown owner\n")
            self.assertEqual(git("cat-file", "blob", unique), "retained unreachable blob")
            self.assertEqual(git("rev-parse", "HEAD"), head)
            self.assertEqual(git("show-ref"), refs)
            self.assertEqual(git("status", "--porcelain"), dirty)
            self.assertEqual(source.read_text(), "active source change\n")
            self.assertEqual((repo / "memory/keep.txt").read_text(), "retained memory\n")

    def test_git_maintenance_timeout_allows_its_private_child_to_clean_its_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".git/objects").mkdir(parents=True)
            lock = repo / ".git/objects/maintenance.lock"
            terminated = repo / "terminated"
            script = (
                "import pathlib,signal,sys,time\n"
                "lock=pathlib.Path(sys.argv[1])\n"
                "def stop(*_):\n"
                " lock.unlink()\n"
                " pathlib.Path(sys.argv[2]).write_text('TERM')\n"
                " sys.exit(0)\n"
                "signal.signal(signal.SIGTERM,stop)\n"
                "lock.write_text('owned by this private child')\n"
                "print('private stdout',flush=True)\n"
                "print('private stderr',file=sys.stderr,flush=True)\n"
                "time.sleep(60)\n"
            )
            child = [sys.executable, "-B", "-c", script, str(lock), str(terminated)]
            native_run, native_popen = subprocess.run, subprocess.Popen
            native_entrypoint = lm_loop_run._run_entrypoint
            children = []
            def start(command, **kwargs):
                process = native_popen(command, **kwargs)
                if script in command:
                    children.append(process)
                return process
            def run(command, **kwargs):
                if command[-2:] == ["count-objects", "-v"]:
                    return subprocess.CompletedProcess(command, 0, "prune-packable: 0\nsize: 0\n", "")
                if command[-3:] == ["rev-parse", "--git-path", "objects/maintenance.lock"]:
                    return subprocess.CompletedProcess(command, 0, str(lock), "")
                if "maintenance" in command:
                    self.assertEqual(kwargs["timeout"], 15)
                    return native_run(child, **{**kwargs, "timeout": .3})
                return native_run(command, **kwargs)
            def owned(command, **kwargs):
                self.assertEqual(kwargs["timeout_seconds"], 15)
                self.assertEqual(kwargs.get("termination_grace_seconds", 15), 15)
                self.assertEqual(kwargs["env"]["LC_ALL"], "C")
                return native_entrypoint(child, **{**kwargs, "timeout_seconds": .3,
                                                    "termination_grace_seconds": .3})
            try:
                with mock.patch.object(subprocess, "run", side_effect=run), \
                     mock.patch.object(subprocess, "Popen", side_effect=start), \
                     mock.patch.object(lm_loop_run, "_run_entrypoint", side_effect=owned):
                    result = central_cleanup.git_duplicate_cleanup(repo)
                self.assertFalse(lock.exists(), "timeout hard-killed the child before its lock cleanup")
                self.assertEqual(terminated.read_text(), "TERM")
                self.assertEqual(result["status"], "deferred")
                self.assertEqual(result["errors"], 0)
                self.assertEqual(result["error_class"], "TimeoutExpired")
                self.assertIsNone(result["prune_packable_after"])
                self.assertIsNone(result["loose_bytes_after"])
            finally:
                for process in children:
                    if process.poll() is None:
                        process.kill()
                    process.wait()

    def test_native_git_duplicate_cleanup_preserves_unknown_after_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".git").mkdir()
            count = subprocess.CompletedProcess([], 0, "prune-packable: 3\nsize: 0\n", "")
            lock_path = subprocess.CompletedProcess([], 0, str(repo / ".git/objects/maintenance.lock"), "")
            with mock.patch.object(central_cleanup.subprocess, "run", side_effect=(
                    count, subprocess.CompletedProcess([], 0, "", ""), lock_path)), \
                 mock.patch.object(lm_loop_run, "_run_entrypoint", return_value=124):
                result = central_cleanup.git_duplicate_cleanup(repo)
            self.assertEqual(result["errors"], 0)
            self.assertEqual(result["status"], "deferred")
            self.assertEqual(result["error_class"], "TimeoutExpired")
            self.assertTrue(result["retryable"])
            self.assertEqual(result["next_action"], "retry_next_natural_pass")
            self.assertEqual(result["prune_packable_before"], 3)
            self.assertIsNone(result["prune_packable_after"])

    def test_source_reference_scan_skips_unrelated_paths_and_keeps_open_roots(self):
        import ast
        import inspect
        import types
        tree = ast.parse(inspect.getsource(central_cleanup.reclaim_unreferenced_source))
        function = next(node for node in tree.body[0].body
                        if isinstance(node, ast.FunctionDef) and node.name == "references")
        scope = ast.parse("def _scope():\n    phase = 'fixture'\n    return references\n").body[0]
        scope.body.insert(1, function)
        module = ast.fix_missing_locations(ast.Module(body=[scope], type_ignores=[]))
        base = Path("/fixture/releases")
        output = "p999999\nf8\n" + "\n".join([
            "n/unrelated/file", "n/fixture/releases-other/code",
            "n/fixture/releases/../sibling/code", "n/fixture/releases/./open/code",
            "n/fixture/releases/held/code"]) + f"\np{os.getpid()}\nf42\nn/fixture/releases/self/code\n"
        parsed = []
        def path(value):
            parsed.append(value)
            return Path(value)
        namespace = {**vars(central_cleanup), "Path": path, "releases": base,
                     "agents": base / "agents", "current": Path("/"),
                     "deadline": time.monotonic() + 15}
        with mock.patch.object(central_cleanup, "loaded_release_roots", return_value=set()), \
             mock.patch.object(central_cleanup, "open_release_roots", return_value=set()), \
             mock.patch.object(central_cleanup.subprocess, "run", return_value=types.SimpleNamespace(
                 stdout=output, stderr="")), \
             mock.patch.dict(os.environ, {"LIFE_MANAGER_PROTECTED_RELEASES": "/fixture/no-protected-file"}):
            namespace.update(loaded_release_roots=central_cleanup.loaded_release_roots,
                             open_release_roots=central_cleanup.open_release_roots)
            exec(compile(module, "references", "exec"), namespace)
            held = namespace["_scope"]()((42,))
        self.assertEqual(held, {Path("/"), base / "..", base / "open", base / "held"})
        self.assertNotIn("/unrelated/file", parsed)
        self.assertNotIn("/fixture/releases-other/code", parsed)

    def test_reclaimed_release_is_not_selected_or_collected(self):
        for marker_kind in ("descriptor", "dangling", "probe_error"):
            with self.subTest(marker_kind=marker_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                release = root / "releases/20260101T000000-aaaaaaaa"
                release.mkdir(parents=True)
                descriptor = json.dumps({"sha": "a" * 40, "release_paths": "ALL"}).encode()
                (release / "RELEASE.json").write_bytes(descriptor)
                self.assertTrue(loop_cleanup._valid_release(release))
                retained = {}
                for relative in ("memory/owner.md", "state/owner.jsonl", "unknown.bin"):
                    item = release / relative
                    item.parent.mkdir(exist_ok=True)
                    item.write_bytes(b"preserve at this path\n")
                    retained[item] = (item.read_bytes(), item.stat().st_ino)
                marker = release / "RECLAIMED-RELEASE.json"
                if marker_kind == "descriptor":
                    marker.write_bytes(descriptor)
                elif marker_kind == "dangling":
                    marker.symlink_to(release / "missing-descriptor")
                original_lstat = Path.lstat

                def probe(path, *args, **kwargs):
                    if marker_kind == "probe_error" and path == marker:
                        raise PermissionError("marker probe unavailable")
                    return original_lstat(path, *args, **kwargs)

                with mock.patch.object(Path, "lstat", autospec=True, side_effect=probe):
                    self.assertFalse(loop_cleanup._valid_release(release))
                    result = gc_releases(root / "releases", root / "current", keep=0,
                                         protected=set(), managed_bytes=0,
                                         closed_releases={release})
                self.assertEqual(result["evaluated_releases"], 0)
                self.assertEqual(result["removed_releases"], 0)
                self.assertEqual(result["protected_deletions"], 0)
                self.assertEqual((release / "RELEASE.json").read_bytes(), descriptor)
                for item, expected in retained.items():
                    self.assertEqual((item.read_bytes(), item.stat().st_ino), expected)

    def test_scratch_gc_keeps_live_log_relay_after_parent_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/example/run-1"; run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps({"pid": 111,
                "process_start": "parent", "effect_class": "none"}))
            relay = run / "stderr-relay"; relay.mkdir(mode=0o700)
            marker = relay / ".stderr-relay.json"
            marker.write_text(json.dumps({"pid": 222, "process_start": "relay-start",
                "binding": {"owner_id": "example", "run_id": "run-1"},
                "role": "diagnostic_only"})); marker.chmod(0o600)
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns()+1,
                                starts={222: "relay-start"})
            self.assertTrue(run.exists())
            self.assertEqual(result["removed"], 0)

    def test_byte_retention_reclaims_only_closed_regenerable_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = completed(root, "old", size=4096)
            new = completed(root, "new", size=64)
            active = completed(root, "active", size=8192)
            protected = completed(root, "protected", size=8192)
            (protected / ".lm-protected").write_text("keep")
            os.utime(old, (1, 1)); os.utime(new, (2, 2))
            result = cleanup_run_root(root, {"max_runs": 100, "max_age_days": 365},
                {"active"}, now=3, managed_bytes=1024, closed_run_ids={"old", "new"})
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())
            self.assertTrue(active.exists())
            self.assertTrue(protected.exists())
            self.assertEqual(result["protected_deletions"], 0)

    def test_byte_retention_without_closed_proof_preserves_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = completed(root, "unknown", size=4096)
            result = cleanup_run_root(root, {"max_runs": 100, "max_age_days": 365},
                set(), now=time.time(), managed_bytes=1)
            self.assertTrue(run.exists())
            self.assertGreater(result["unrecoverable_bytes"], 0)

    def test_byte_retention_preserves_memory_and_state_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory = completed(root, "memory-case", size=1024)
            (memory / "memory").mkdir(); (memory / "memory/item.md").write_text("keep")
            journal = completed(root, "journal-case", size=1024)
            (journal / "state").mkdir(); (journal / "state/item.jsonl").write_text("{}\n")
            cleanup_run_root(root, {"max_runs": 100, "max_age_days": 365}, set(),
                managed_bytes=0, closed_run_ids={"memory-case", "journal-case"})
            self.assertTrue((memory / "memory/item.md").exists())
            self.assertTrue((journal / "state/item.jsonl").exists())

    def test_release_byte_budget_keeps_current_and_removes_only_closed_old_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); releases = root / "releases"; releases.mkdir()
            paths = []
            for index, size in enumerate([4096, 64, 4096]):
                path = releases / f"2026010{index+1}T000000-{index:08x}"; path.mkdir()
                (path / "RELEASE.json").write_text(json.dumps({"sha": f"{index:040x}"}))
                (path / "source.bin").write_bytes(b"x" * size)
                os.utime(path, (index+1, index+1)); paths.append(path)
            current = root / "current"; current.symlink_to(paths[2])
            result = gc_releases(releases, current, keep=100, protected=set(),
                managed_bytes=1024, closed_releases={p.resolve() for p in paths})
            self.assertFalse(paths[0].exists())
            self.assertTrue(paths[1].exists())
            self.assertTrue(paths[2].exists())
            self.assertEqual(result["protected_deletions"], 0)

    def test_cleanup_binding_uses_the_loaded_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
            binding = central_cleanup.cleanup_run_binding({
                "LIFE_MANAGER_RUN_ID": "run-1",
                "LIFE_MANAGER_OCCURRENCE_ID": "life-manager-disk-cleanup:run-1",
                "LIFE_MANAGER_RELEASE_SHA": "b" * 40,
            }, root)
            self.assertEqual(binding, {"owner_id": "life-manager-disk-cleanup",
                "run_id": "run-1", "occurrence_id": "life-manager-disk-cleanup:run-1",
                "release_sha": "a" * 40})
            self.assertIsNone(central_cleanup.cleanup_run_binding({}, root))
    def test_central_cleanup_delegates_host_sweep_to_minute_watchdog(self):
        with mock.patch.object(central_cleanup, "cleanup_run_binding", return_value=None), \
             mock.patch.object(central_cleanup, "git_duplicate_cleanup",
                 return_value={"errors": 0, "status": "pass"}) as git_cleanup, \
             mock.patch.object(central_cleanup, "release_gc",
                 return_value={"errors": 0, "status": "pass"}) as gc, \
             mock.patch.object(central_cleanup, "scratch_gc",
                 return_value={"errors": 0, "status": "pass"}) as scratch, \
             mock.patch.object(central_cleanup, "installed_state_roots", return_value=[]), \
             mock.patch.object(central_cleanup, "process_starts", return_value={}), \
             mock.patch.object(central_cleanup, "no_effect_loop_ids", return_value=set()), \
             mock.patch.object(central_cleanup.subprocess, "run",
                 side_effect=AssertionError("central owner invoked host sweep")), \
             mock.patch.object(sys, "argv", ["central_cleanup.py"]), \
             mock.patch("builtins.print") as output:
            self.assertEqual(central_cleanup.main(), 0)

        git_cleanup.assert_called_once()
        gc.assert_called_once()
        scratch.assert_called_once()
        result = json.loads(output.call_args.args[0])
        self.assertTrue(result["ok"])
        self.assertEqual(result["host_cleanup"], {
            "status": "delegated", "owner_id": "com.anicca.disk-watchdog"})

    def test_no_effect_loop_ids_reads_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "loop-registry.json"
            registry.write_text(json.dumps({"loops": {
                "safe": {"effect_class": "none"},
                "money": {"effect_class": "money"},
            }}))
            self.assertEqual(no_effect_loop_ids(registry), {"safe"})

    def test_loop_cleanup_preserves_active_unmarked_and_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); old = completed(root, "old"); active = completed(root, "active")
            newest = completed(root, "newest")
            unmarked = root / "runs/unmarked"; unmarked.mkdir(); (unmarked / "data").write_text("keep")
            receipt = root / "receipts"; receipt.mkdir(); (receipt / "official.json").write_text("keep")
            for index, path in enumerate((old, active, newest), 1): os.utime(path, (index, index))
            result = cleanup_run_root(root, {"max_runs": 1, "max_age_days": 365}, {"active"}, now=4)
            self.assertFalse(old.exists())
            self.assertTrue(active.exists())
            self.assertTrue(newest.exists())
            self.assertTrue(unmarked.exists())
            self.assertTrue(receipt.exists())
            self.assertEqual(result["protected_deletions"], 0)

    def test_pressure_cleanup_reclaims_completed_bytes_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); completed(root, "old", 1024 * 1024)
            result = cleanup_run_root(root, {"max_runs": 0, "max_age_days": 1}, set(), now=time.time() + 172800)
            self.assertGreaterEqual(result["reclaimed_bytes"], 1024 * 1024)
            self.assertEqual(result["removed_runs"], 1)

    def test_release_gc_preserves_current_and_explicit_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            releases = Path(directory) / "releases"; releases.mkdir()
            paths=[]
            for index in range(4):
                path=releases/f"2026010{index}T000000-{'a'*7}{index}"; path.mkdir()
                (path/"RELEASE.json").write_text(json.dumps({"sha": f"{index:040x}"}))
                os.utime(path,(index,index)); paths.append(path)
            current=Path(directory)/"current"; current.symlink_to(paths[1])
            result=gc_releases(releases,current,keep=1,protected={paths[2].resolve()})
            self.assertTrue(paths[1].exists()); self.assertTrue(paths[2].exists()); self.assertTrue(paths[3].exists())
            self.assertFalse(paths[0].exists())
            self.assertEqual(result["protected_deletions"],0)

    def test_release_gc_removes_selected_read_only_release(self):
        with tempfile.TemporaryDirectory() as directory:
            releases = Path(directory) / "releases"; releases.mkdir()
            stale = releases / ("20260101T000000-" + "a" * 8); stale.mkdir()
            (stale / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
            nested = stale / "nested"; nested.mkdir(); (nested / "code.py").write_text("x")
            for path in (nested / "code.py", stale / "RELEASE.json"):
                path.chmod(0o444)
            nested.chmod(0o555); stale.chmod(0o555)
            current = Path(directory) / "current"

            result = gc_releases(releases, current, keep=0, protected=set())

            self.assertFalse(stale.exists())
            self.assertEqual(result["errors"], 0)

    def test_release_gc_hides_trash_from_finder_metadata_race(self):
        with tempfile.TemporaryDirectory() as directory:
            releases = Path(directory) / "releases"; releases.mkdir()
            stale = releases / ("20260101T000000-" + "a" * 8); stale.mkdir()
            (stale / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
            current = Path(directory) / "current"
            from runtime.loop import loop_cleanup
            original_replace = loop_cleanup.os.replace
            original_rmdir = loop_cleanup.os.rmdir
            trash_names = []

            def capture_trash(src, dst, *args, **kwargs):
                trash_names.append(Path(dst).name)
                return original_replace(src, dst, *args, **kwargs)

            def finder_metadata_rmdir(path, *args, **kwargs):
                name = os.fspath(path)
                if (trash_names and Path(name).name == trash_names[0]
                        and not Path(name).name.startswith(".")):
                    fd = os.open(".DS_Store", os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                 0o644, dir_fd=kwargs.get("dir_fd"))
                    os.close(fd)
                return original_rmdir(path, *args, **kwargs)

            with mock.patch("runtime.loop.loop_cleanup.os.replace",
                            side_effect=capture_trash), \
                 mock.patch("runtime.loop.loop_cleanup.os.rmdir",
                            side_effect=finder_metadata_rmdir):
                result = gc_releases(releases, current, keep=0, protected=set())

            self.assertEqual(result["errors"], 0)
            self.assertTrue(trash_names[0].startswith("."))
            self.assertFalse((releases / trash_names[0]).exists())

    def test_release_gc_preserves_memory_and_state_jsonl_but_removes_plain_release(self):
        with tempfile.TemporaryDirectory() as directory:
            releases = Path(directory) / "releases"
            releases.mkdir()
            memory_release = releases / "20260101T000000-aaaaaaaa"
            state_release = releases / "20260102T000000-bbbbbbbb"
            dangling_memory_release = releases / "20260103T000000-cccccccc"
            dangling_state_release = releases / "20260104T000000-dddddddd"
            dependency_release = releases / "20260105T000000-eeeeeeee"
            plain_release = releases / "20260106T000000-ffffffff"
            for index, path in enumerate((
                memory_release, state_release, dangling_memory_release,
                dangling_state_release, dependency_release, plain_release,
            )):
                path.mkdir()
                (path / "RELEASE.json").write_text(json.dumps({"sha": f"{index:040x}"}))
            (memory_release / "memory").mkdir()
            (memory_release / "memory" / "owner.md").write_text("private memory")
            state = state_release / "nested" / "state"
            state.mkdir(parents=True)
            (state / "events.jsonl").write_text("{}\n")
            (dangling_memory_release / "memory").symlink_to(
                Path(directory) / "missing-memory", target_is_directory=True
            )
            dangling_state = dangling_state_release / "nested"
            dangling_state.mkdir()
            (dangling_state / "state").symlink_to(
                Path(directory) / "missing-state", target_is_directory=True
            )
            outside = Path(directory) / "outside"
            outside.mkdir()
            (outside / "owner.md").write_text("keep target")
            (dependency_release / "node_modules").symlink_to(outside)
            (plain_release / "bin").mkdir()
            (plain_release / "bin" / "loop.sh").write_text("#!/bin/sh\n")
            (plain_release / "memory").write_text("ordinary file")

            agents = Path(directory) / "agents"
            agents.mkdir()
            (agents / "com.example.unrelated.plist").write_bytes(plistlib.dumps({"Label": "com.example.unrelated", "ProgramArguments": ["/usr/bin/true"]}))
            protected_file = Path(directory) / "protected-releases.json"
            protected_file.write_text("[]")
            with (
                mock.patch.dict(os.environ, {
                    "LIFE_MANAGER_PROTECTED_RELEASES": str(protected_file),
                }),
                mock.patch(
                    "runtime.loop.central_cleanup.open_release_roots", return_value=set()
                ),
            ):
                result = release_gc(
                    releases, Path(directory) / "current", agents, keep=0
                )

            self.assertTrue(memory_release.exists())
            self.assertTrue(state_release.exists())
            self.assertTrue(dangling_memory_release.exists())
            self.assertTrue(dangling_state_release.exists())
            self.assertFalse(dependency_release.exists())
            self.assertFalse(plain_release.exists())
            self.assertTrue((outside / "owner.md").exists())
            self.assertEqual(result["removed_releases"], 2)
            self.assertEqual(result["preserved_releases"], 4)
            self.assertEqual(result["errors"], 0)
            self.assertEqual(result["protected_release_count"], 0)

    def test_business_wake_builds_command_without_scanning_run_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = root / "bin/job.sh"
            entry.parent.mkdir()
            entry.write_text("#!/bin/sh\n")
            entry.chmod(0o755)
            value = {"schema_version": 2, "loops": {"job": {
                "label": "ai.anicca.job", "domain": "system", "entrypoint": "bin/job.sh",
                "cadence": {"run_at_load": True}, "effect_class": "none",
                "state_root": "~/state", "log_root": "~/state/logs",
                "cleanup": {"max_runs": 1, "max_age_days": 1},
                "provider_route": "deterministic"}}}
            with mock.patch("runtime.loop.loop_cleanup.cleanup_run_root",
                            side_effect=AssertionError("wake-path cleanup")):
                self.assertEqual(build_loop_command(value, "job", root), [str(entry.resolve())])

    def test_business_wake_reaches_admission_without_run_tree_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = root / "bin/job.sh"
            entry.parent.mkdir()
            entry.write_text("#!/bin/sh\n")
            entry.chmod(0o755)
            home = root / "home"
            home.mkdir()
            value = {"schema_version": 2, "loops": {"job": {
                "label": "ai.anicca.job", "domain": "system", "entrypoint": "bin/job.sh",
                "cadence": {"run_at_load": True}, "effect_class": "none",
                "state_root": "~/state", "log_root": "~/state/logs",
                "cleanup": {"max_runs": 1, "max_age_days": 1},
                "provider_route": "deterministic"}}}
            (root / "config").mkdir()
            (root / "config/loop-registry.json").write_text(json.dumps(value))
            (root / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
            claim = root / "claim.json"
            claim.write_text(json.dumps({"occurrence_id": "job:test-cleanup"}))
            with (
                mock.patch.dict(os.environ, {"HOME": str(home)}),
                mock.patch("runtime.loop.loop_cleanup.cleanup_run_root",
                           side_effect=AssertionError("wake-path cleanup")),
                mock.patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=100),
                mock.patch("runtime.loop.lm_loop_run.durable_protocol_version", return_value=2),
                mock.patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                           return_value=(root / "ticket", "ready")),
                mock.patch("runtime.loop.lm_loop_run.claim_durable_resource",
                           return_value=(claim, "acquired")),
                mock.patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                           return_value=[]),
                mock.patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0),
            ):
                self.assertEqual(lm_loop_run.main(["job", str(root)]), 0)

    def test_unknown_publish_preserves_effect_identity_before_scratch_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "release"
            entrypoint = root / "bin/job.sh"
            entrypoint.parent.mkdir(parents=True)
            entrypoint.write_text("#!/bin/sh\n")
            entrypoint.chmod(0o755)
            (root / "config").mkdir()
            (root / "config/loop-registry.json").write_text(json.dumps({
                "schema_version": 2,
                "loops": {"job": {
                    "label": "ai.anicca.job", "domain": "growth",
                    "entrypoint": "bin/job.sh", "cadence": {"run_at_load": True},
                    "effect_class": "publish", "state_root": "~/state",
                    "log_root": "~/state/logs", "cleanup": {"max_runs": 1, "max_age_days": 1},
                    "provider_route": "deterministic",
                }},
            }))
            (root / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
            home = Path(directory) / "home"
            home.mkdir()
            observed = {}

            def unknown_publish(_command, _entry, _loop_id, env, receipt, *, occurrence_id,
                                on_claimed, on_stderr_tail=lambda _tail: None,
                                on_storage_failure=None, on_terminal_event=None):
                observed.update(env)
                observed["LIFE_MANAGER_OCCURRENCE_ID"] = occurrence_id
                on_claimed(occurrence_id)
                Path(env["LIFE_MANAGER_EFFECT_IDENTITY_PATH"]).write_text(json.dumps({
                    "schema_version": 1,
                    "kind": "life_manager_effect_identity",
                    "runtime_run_id": env["LIFE_MANAGER_RUN_ID"],
                    "occurrence_id": occurrence_id,
                    "loop_id": "job",
                    "job_id": "marketing-video-publication:job-1",
                    "effect_key": "marketing:video:job-product:tiktok:creative:" + "a" * 64 + ":" + "b" * 64,
                    "product_id": "job-product",
                    "format_id": "job-format",
                    "form": "job-form",
                    "locale": "ja",
                    "platform": "tiktok",
                    "creative_id": "creative",
                    "slot": "2026-07-30T12:30:00.000Z",
                    "integration_ref": "integration://postiz/tiktok/job-integration",
                    "account_id": "@job-account",
                    "video_sha256": "a" * 64,
                    "caption_sha256": "b" * 64,
                }) + "\n", encoding="utf-8")
                Path(env["LIFE_MANAGER_EFFECT_IDENTITY_PATH"]).chmod(0o600)
                receipt.write_text('{"status":"pass","effect":0}\n', encoding="utf-8")
                return 1

            with (
                mock.patch.dict(os.environ, {"HOME": str(home)}, clear=False),
                mock.patch("runtime.loop.lm_loop_run._run_admitted", side_effect=unknown_publish),
            ):
                self.assertEqual(lm_loop_run.main(["job", str(root)]), 1)

            self.assertEqual(observed["LIFE_MANAGER_RUN_ID"], observed["LIFE_MANAGER_OCCURRENCE_ID"].split(":", 1)[1])
            identity_files = list((home / "state/effect-identities").glob("*.jsonl"))
            self.assertEqual(len(identity_files), 1)
            self.assertEqual(
                json.loads(identity_files[0].read_text(encoding="utf-8"))["job_id"],
                "marketing-video-publication:job-1",
            )
            event = json.loads((home / "state/events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
            self.assertIn(
                f"lm-effect://job/{observed['LIFE_MANAGER_RUN_ID']}/identity.jsonl",
                event["evidence_refs"],
            )

    def test_terminal_event_failure_preserves_scratch_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = root / "bin/job.sh"
            entry.parent.mkdir()
            entry.write_text("#!/bin/sh\n")
            entry.chmod(0o755)
            home = root / "home"
            home.mkdir()
            value = {"schema_version": 2, "loops": {"job": {
                "label": "ai.anicca.job", "domain": "system", "entrypoint": "bin/job.sh",
                "cadence": {"run_at_load": True}, "effect_class": "none",
                "state_root": "~/state", "log_root": "~/state/logs",
                "cleanup": {"max_runs": 1, "max_age_days": 1},
                "provider_route": "deterministic"}}}
            (root / "config").mkdir()
            (root / "config/loop-registry.json").write_text(json.dumps(value))
            (root / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
            claim = root / "claim.json"
            claim.write_text(json.dumps({"occurrence_id": "job:test-terminal"}))
            with (
                mock.patch.dict(os.environ, {"HOME": str(home)}),
                mock.patch("runtime.loop.lm_loop_run.process_start", return_value="start"),
                mock.patch("runtime.loop.lm_loop_run.memory_free_percent", return_value=100),
                mock.patch("runtime.loop.lm_loop_run.durable_protocol_version", return_value=2),
                mock.patch("runtime.loop.lm_loop_run.enqueue_durable_resource",
                           return_value=(root / "ticket", "ready")),
                mock.patch("runtime.loop.lm_loop_run.claim_durable_resource",
                           return_value=(claim, "acquired")),
                mock.patch("runtime.loop.lm_loop_run.release_and_reserve_resource",
                           return_value=[]),
                mock.patch("runtime.loop.lm_loop_run._run_entrypoint", return_value=0),
                mock.patch("runtime.loop.lm_loop_run.append_runtime_event",
                           side_effect=[None, OSError("receipt write failed")]),
            ):
                self.assertEqual(lm_loop_run.main(["job", str(root)]), 78)
            scratches = list((home / "state/loop-tmp/job").iterdir())
            self.assertEqual(len(scratches), 1)
            self.assertTrue((scratches[0] / ".owner.json").is_file())
            self.assertTrue((scratches[0] / ".terminal-unrecorded").is_file())

    def test_scratch_gc_removes_only_proved_stale_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live = root / "loop-tmp/job/live"
            stale = root / "loop-tmp/job/stale"
            live.mkdir(parents=True)
            stale.mkdir(parents=True)
            (live / ".owner.json").write_text(json.dumps(
                {"pid": 10, "process_start": "live-start"}))
            (stale / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            helper = live.parent / "helper.py"
            helper.write_text("keep")
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={10: "live-start"})
            self.assertEqual(result["errors"], 0)
            self.assertEqual(helper.read_text(), "keep")
            self.assertTrue(live.is_dir())
            self.assertFalse(stale.exists())
            self.assertEqual((result["removed"], result["preserved"]), (1, 1))

    def test_scratch_gc_resumes_a_bounded_scan_without_revisiting_the_first_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live = root / "loop-tmp/job/a-live"
            stale_b = root / "loop-tmp/job/b-stale"
            stale_c = root / "loop-tmp/job/c-stale"
            for run in (live, stale_b, stale_c):
                run.mkdir(parents=True)
            (live / ".owner.json").write_text(json.dumps(
                {"pid": 10, "process_start": "live-start"}))
            for pid, run in ((11, stale_b), (12, stale_c)):
                (run / ".owner.json").write_text(json.dumps(
                    {"pid": pid, "process_start": "old-start"}))
            cursor = root / "state/scratch-gc-cursor.json"
            kwargs = {"snapshot_started_ns": time.time_ns() + 1,
                      "starts": {10: "live-start"}, "cursor_path": cursor,
                      "candidate_budget": 2}

            first = scratch_gc({root}, **kwargs)
            self.assertEqual(first["scanned"], 2)
            self.assertTrue(first["deferred"])
            self.assertTrue(live.is_dir())
            self.assertFalse(stale_b.exists())
            self.assertTrue(stale_c.is_dir())

            second = scratch_gc({root}, **kwargs)
            self.assertEqual(second["scanned"], 2)
            self.assertFalse(second["deferred"])
            self.assertEqual(second["removed"], 1)
            self.assertTrue(live.is_dir())
            self.assertFalse(stale_b.exists())
            self.assertFalse(stale_c.exists())

    def test_scratch_gc_cursor_continues_inside_loop_before_advancing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            starts = {}
            for loop_index, loop_name in enumerate(("a-loop", "b-loop"), start=20):
                for run_index in range(1, 5):
                    run = root / "loop-tmp" / loop_name / f"run-{run_index}"
                    run.mkdir(parents=True)
                    pid = loop_index * 10 + run_index
                    starts[pid] = "same-start"
                    (run / ".owner.json").write_text(json.dumps(
                        {"pid": pid, "process_start": "same-start"}))

            cursor = root / "state/scratch-gc-cursor.json"
            kwargs = {"starts": starts, "cursor_path": cursor, "candidate_budget": 2}

            first = scratch_gc({root}, **kwargs)
            self.assertEqual(first["scanned"], 2)
            self.assertEqual(json.loads(cursor.read_text())["run"], "run-2")

            second = scratch_gc({root}, **kwargs)
            self.assertEqual(second["scanned"], 2)
            self.assertEqual(json.loads(cursor.read_text()), {
                "root": str(root.resolve()), "loop": "a-loop", "run": "run-4",
            })

    def test_scratch_gc_defers_before_deleting_when_total_inventory_exceeds_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            roots = {base / "state-a", base / "state-b"}
            starts = {}
            runs = []
            for root_index, root in enumerate(sorted(roots), start=1):
                for run_index in range(2):
                    run = root / "loop-tmp/job" / f"run-{run_index}"
                    run.mkdir(parents=True)
                    pid = root_index * 10 + run_index
                    starts[pid] = "same-start"
                    (run / ".owner.json").write_text(json.dumps(
                        {"pid": pid, "process_start": "same-start"}))
                    runs.append(run)

            with mock.patch.object(
                    central_cleanup, "SCRATCH_GC_TOTAL_CANDIDATE_LIMIT", 3):
                result = scratch_gc(
                    roots, starts=starts, cursor_path=base / "cursor.json",
                    candidate_budget=10,
                )

            self.assertTrue(result["deferred"])
            self.assertTrue(result["blocking_defer"])
            self.assertEqual(result["budget_reason"], "total_candidate_budget")
            self.assertEqual(result["scanned"], 0)
            self.assertTrue(all(run.is_dir() for run in runs))

    def test_scratch_gc_defers_when_directory_inventory_exceeds_preflight_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = [root / "loop-tmp/job" / name for name in ("a", "b")]
            for index, run in enumerate(runs, start=10):
                run.mkdir(parents=True, exist_ok=True)
                (run / ".owner.json").write_text(json.dumps(
                    {"pid": index, "process_start": "old-start"}))
            cursor = root / "state/scratch-gc-cursor.json"
            with mock.patch.object(central_cleanup, "SCRATCH_GC_DIRECTORY_ENTRY_LIMIT", 1):
                result = scratch_gc({root}, starts={}, cursor_path=cursor,
                                    candidate_budget=10)
            self.assertTrue(result["deferred"])
            self.assertTrue(result["blocking_defer"])
            self.assertEqual(result["budget_reason"], "directory_entry_budget")
            self.assertEqual(result["removed"], 0)
            self.assertTrue(all(run.is_dir() for run in runs))

    def test_scratch_gc_defers_without_deleting_when_event_log_exceeds_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            (root / "events.jsonl").write_text("x" * 128)
            cursor = root / "state/scratch-gc-cursor.json"
            with mock.patch.object(central_cleanup, "SCRATCH_GC_EVENT_LOG_MAX_BYTES", 64):
                result = scratch_gc({root}, starts={}, cursor_path=cursor,
                                    candidate_budget=10)
            self.assertTrue(result["deferred"])
            self.assertTrue(result["blocking_defer"])
            self.assertEqual(result["budget_reason"], "event_file_budget")
            self.assertEqual(result["removed"], 0)
            self.assertTrue(run.is_dir())

    def test_scratch_gc_fails_closed_without_identity_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start", "effect_class": "none"}))
            with mock.patch("runtime.loop.central_cleanup.process_starts", return_value=None):
                result = scratch_gc({root})
            self.assertTrue(run.is_dir())
            self.assertFalse(result["identity_snapshot_available"])

    def test_scratch_gc_preserves_malformed_owner_without_failing_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text("{")
            result = scratch_gc({root}, starts={})
            self.assertTrue(run.is_dir())
            self.assertEqual(result["errors"], 0)
            self.assertEqual(result["owner_metadata_invalid"], 1)

    def test_scratch_gc_records_malformed_owner_before_terminal_preserve(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text("{")
            (run / ".terminal-unrecorded").touch()
            result = scratch_gc({root}, starts={})
            self.assertTrue(run.is_dir())
            self.assertEqual((result["errors"], result["owner_metadata_invalid"]), (0, 1))

    def test_scratch_gc_records_owner_open_oserror(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            original_open = os.open

            def fail_owner(path, flags, *args, **kwargs):
                if path == ".owner.json":
                    raise PermissionError("owner unavailable")
                return original_open(path, flags, *args, **kwargs)

            with mock.patch("runtime.loop.central_cleanup.os.open", side_effect=fail_owner):
                result = scratch_gc({root}, starts={})
            self.assertEqual((result["errors"], result["preserved"]), (1, 1))

    def test_scratch_gc_preserves_invalid_present_effect_class(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/no-effect/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps({
                "pid": 11, "process_start": "old-start", "effect_class": False,
            }))
            (run / ".terminal-unrecorded").touch()
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": "no-effect", "run_id": "run", "effect_class": "none",
            }) + "\n")
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={}, no_effect_loop_ids={"no-effect"})
            self.assertTrue(run.is_dir())
            self.assertEqual((result["removed"], result["preserved"],
                              result["owner_metadata_invalid"]), (0, 1, 1))

    def test_scratch_gc_preserves_unrecorded_terminal_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            (run / ".terminal-unrecorded").touch()
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={})
            self.assertTrue(run.is_dir())
            self.assertEqual((result["removed"], result["preserved"]), (0, 1))

    def test_scratch_gc_reclaims_only_exactly_reconciled_closed_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scratch = root / "loop-tmp/publish"
            runs = {name: scratch / name for name in ("run-1", "run-2", "run-3")}
            events = []
            for name, run in runs.items():
                run.mkdir(parents=True)
                (run / ".owner.json").write_text(json.dumps({
                    "pid": 11, "process_start": "old-start", "effect_class": "publish",
                }))
                (run / ".terminal-unrecorded").touch()
                (run / "agent-browser-profile-test").mkdir()
                events.append({
                    "loop_id": "publish", "run_id": name,
                    "occurrence_id": f"publish:{name}", "effect_class": "publish",
                    "release_sha": "a" * 40,
                })
            (root / "events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events))
            verified = json.dumps({
                "owner_id": "publish", "occurrence_id": "publish:run-1",
                "verified": True, "provider_receipt_id": "official:effect-reconciled",
            })
            closure_proof = {
                "proof_type": "effect_reconcile_closure.v1",
                "owner_id": "publish", "occurrence_id": "publish:run-1",
                "release_sha": "a" * 40, "verified": True,
                "receipt_ref": "official:effect-reconciled",
            }
            calls = root / "reconcile-calls.jsonl"
            calls.write_text("\n".join([
                json.dumps({"owner_id": "publish", "occurrence_id": "publish:run-1",
                            "release_sha": "a" * 40, "exit_code": 0, "closed": True,
                            "stdout_tail": verified, "closure_proof": closure_proof}),
                json.dumps({"owner_id": "publish", "occurrence_id": "publish:run-2",
                            "release_sha": "a" * 40, "exit_code": 0, "closed": False,
                            "stdout_tail": verified}),
                json.dumps({"owner_id": "publish", "occurrence_id": "publish:run-3",
                            "release_sha": "a" * 40, "exit_code": 0, "closed": True,
                            "stdout_tail": '{"verified":false}'}),
            ]) + "\n")
            reconciled = central_cleanup.closed_reconcile_occurrences(calls)
            self.assertEqual(reconciled, {("publish", "publish:run-1", "a" * 40)})

            with mock.patch.object(
                    central_cleanup, "_browser_profiles_live",
                    side_effect=lambda run: run.name == "run-3"):
                result = scratch_gc(
                    {root}, snapshot_started_ns=time.time_ns() + 1,
                    starts={}, reconciled_occurrences=reconciled,
                )

            self.assertFalse(runs["run-1"].exists())
            self.assertTrue(runs["run-2"].is_dir())
            self.assertTrue(runs["run-3"].is_dir())
            self.assertEqual((result["removed"], result["preserved"]), (1, 2))

    def test_scratch_gc_preserves_terminal_recorded_unknown_effect_until_reconciled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/publish/run-unknown"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps({
                "pid": 11, "process_start": "old-start", "effect_class": "publish",
            }))
            (run / "intermediate.png").write_bytes(b"pending provider evidence")
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": "publish", "run_id": "run-unknown", "phase": "report",
                "status": "pass", "effect_class": "publish", "effect_status": "unknown",
                "occurrence_id": "publish:run-unknown", "release_sha": "a" * 40,
            }) + "\n")

            result = scratch_gc(
                {root}, snapshot_started_ns=time.time_ns() + 1, starts={},
                reconciled_occurrences=set(),
            )

            self.assertTrue(run.is_dir())
            self.assertEqual((result["removed"], result["preserved"]), (0, 1))

    def test_scratch_gc_reclaims_exactly_reconciled_terminal_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/publish/run-1"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps({
                "pid": 11, "process_start": "old-start", "effect_class": "publish",
            }))
            (run / ".terminal-unrecorded").touch()
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": "publish", "run_id": "run-1",
                "occurrence_id": "publish:run-1", "effect_class": "publish",
                "release_sha": "c" * 40,
            }) + "\n")
            calls = root / "reconcile-calls.jsonl"
            valid_proof = json.dumps({
                "owner_id": "publish", "occurrence_id": "publish:run-1",
                "verified": True, "provider_receipt_id": "official:no-effect",
            })
            closure_proof = {
                "proof_type": "effect_reconcile_closure.v1",
                "owner_id": "publish", "occurrence_id": "publish:run-1",
                "release_sha": "c" * 40, "verified": True,
                "receipt_ref": "official:no-effect",
            }
            other_closure_proof = {**closure_proof, "occurrence_id": "publish:other"}
            calls.write_text("\n".join([
                json.dumps({"owner_id": "publish", "occurrence_id": "publish:other",
                            "release_sha": "c" * 40, "exit_code": 0, "closed": True,
                            "stdout_tail": valid_proof, "closure_proof": other_closure_proof}),
                json.dumps({"owner_id": "publish", "occurrence_id": "publish:run-1",
                            "release_sha": "c" * 40, "exit_code": 0, "closed": False,
                            "stdout_tail": valid_proof}),
                json.dumps({"owner_id": "publish", "occurrence_id": "publish:run-1",
                            "release_sha": "c" * 40, "exit_code": 0, "closed": True,
                            "stdout_tail": valid_proof, "closure_proof": closure_proof}),
            ]) + "\n")

            reconciled = central_cleanup.closed_reconcile_occurrences(calls)
            self.assertEqual(reconciled, {
                ("publish", "publish:other", "c" * 40),
                ("publish", "publish:run-1", "c" * 40),
            })
            result = scratch_gc(
                {root}, snapshot_started_ns=time.time_ns() + 1, starts={},
                reconciled_occurrences=reconciled,
            )

            self.assertFalse(run.exists())
            self.assertEqual((result["removed"], result["preserved"]), (1, 0))

    def test_scratch_gc_requires_reconcile_for_historical_effect_even_if_loop_is_now_no_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/historical-publish/run-1"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps({
                "pid": 11, "process_start": "old-start", "effect_class": "money",
            }))
            (run / ".terminal-unrecorded").touch()
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": "historical-publish", "run_id": "run-1",
                "occurrence_id": "historical-publish:run-1", "effect_class": "money",
            }) + "\n")

            result = scratch_gc(
                {root}, snapshot_started_ns=time.time_ns() + 1, starts={},
                no_effect_loop_ids={"historical-publish"}, reconciled_occurrences=set(),
            )

            self.assertTrue(run.is_dir())
            self.assertEqual((result["removed"], result["preserved"]), (0, 1))

    def test_closed_reconcile_occurrences_requires_structured_target_bound_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = root / "reconcile-calls.jsonl"
            expected_release = "a" * 40
            proof = {
                "proof_type": "effect_reconcile_closure.v1",
                "owner_id": "publish",
                "occurrence_id": "publish:run-1",
                "release_sha": expected_release,
                "verified": True,
                "receipt_ref": "official:effect-reconciled",
            }
            records = [
                {
                    "owner_id": "publish", "occurrence_id": "publish:run-1",
                    "release_sha": expected_release, "exit_code": 0, "closed": True,
                    "stdout_tail": json.dumps(proof), "closure_proof": proof,
                },
                {
                    "owner_id": "publish", "occurrence_id": "publish:run-2",
                    "release_sha": expected_release, "exit_code": 0, "closed": True,
                    "stdout_tail": json.dumps({**proof, "owner_id": "other"}),
                    "closure_proof": {**proof, "owner_id": "other",
                                      "occurrence_id": "publish:run-2"},
                },
                {
                    "owner_id": "publish", "occurrence_id": "publish:run-3",
                    "release_sha": expected_release, "exit_code": 0, "closed": True,
                    "stdout_tail": json.dumps({**proof, "occurrence_id": "publish:other"}),
                    "closure_proof": {**proof, "occurrence_id": "publish:other"},
                },
                {
                    "owner_id": "publish", "occurrence_id": "publish:run-4",
                    "release_sha": expected_release, "exit_code": 0, "closed": True,
                    "stdout_tail": json.dumps({**proof, "release_sha": "b" * 40}),
                    "closure_proof": {**proof, "release_sha": "b" * 40},
                },
                {
                    "owner_id": "publish", "occurrence_id": "publish:run-5",
                    "release_sha": expected_release, "exit_code": 0, "closed": True,
                    "stdout_tail": 'noise {"verified":true,"provider_receipt_id":"unrelated"}',
                    "closure_proof": 'not-json {"verified":true}',
                },
            ]
            calls.write_text("".join(json.dumps(row) + "\n" for row in records))

            self.assertEqual(
                central_cleanup.closed_reconcile_occurrences(calls),
                {("publish", "publish:run-1", expected_release)},
            )

    def test_scratch_gc_preserves_owner_none_when_event_target_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/no-effect/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start", "effect_class": "none"}))
            (run / ".terminal-unrecorded").touch()
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": "no-effect", "run_id": "other", "effect_class": "none",
            }) + "\n")
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={}, no_effect_loop_ids={"no-effect"})
            self.assertTrue(run.is_dir())
            self.assertEqual(result["removed"], 0)
            self.assertEqual(result["preserved"], 1)

    def test_scratch_gc_removes_stale_unrecorded_no_effect_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/no-effect/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start", "effect_class": "none"}))
            (run / ".terminal-unrecorded").touch()
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": "no-effect", "run_id": "run", "effect_class": "none",
            }) + "\n")
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={}, no_effect_loop_ids={"no-effect"})
            self.assertFalse(run.exists())
            self.assertEqual((result["removed"], result["preserved"]), (1, 0))

    def test_scratch_gc_preserves_live_no_effect_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/no-effect/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 10, "process_start": "live-start", "effect_class": "none"}))
            (run / ".terminal-unrecorded").touch()
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": "no-effect", "run_id": "run", "effect_class": "none",
            }) + "\n")
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={10: "live-start"}, no_effect_loop_ids={"no-effect"})
            self.assertTrue(run.is_dir())
            self.assertEqual((result["removed"], result["preserved"]), (0, 1))

    def test_scratch_gc_preserves_historical_effectful_run_when_registry_is_none(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/no-effect/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start", "effect_class": "money"}))
            (run / ".terminal-unrecorded").touch()
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={}, no_effect_loop_ids={"no-effect"})
            self.assertTrue(run.is_dir())
            self.assertEqual(result["removed"], 0)
            self.assertEqual(result["preserved"], 1)

    def test_scratch_gc_uses_run_bound_event_for_legacy_no_effect_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/no-effect/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            (run / ".terminal-unrecorded").touch()
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": "no-effect", "run_id": "run", "effect_class": "none",
            }) + "\n")
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={}, no_effect_loop_ids={"no-effect"})
            self.assertFalse(run.exists())
            self.assertEqual((result["removed"], result["preserved"]), (1, 0))

    def test_scratch_gc_preserves_conflicting_run_bound_effect_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/no-effect/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            (run / ".terminal-unrecorded").touch()
            (root / "events.jsonl").write_text("\n".join(json.dumps(event) for event in (
                {"loop_id": "no-effect", "run_id": "run", "effect_class": "none"},
                {"loop_id": "no-effect", "run_id": "run", "effect_class": "money"},
            )) + "\n")
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={}, no_effect_loop_ids={"no-effect"})
            self.assertTrue(run.is_dir())
            self.assertEqual((result["removed"], result["preserved"]), (0, 1))

    def test_scratch_gc_preserves_legacy_run_when_event_log_is_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/no-effect/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start", "effect_class": "none"}))
            (run / ".terminal-unrecorded").touch()
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": "no-effect", "run_id": "run", "effect_class": "none",
            }) + "\n{" )
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={}, no_effect_loop_ids={"no-effect"})
            self.assertTrue(run.is_dir())
            self.assertEqual(result["removed"], 0)
            self.assertTrue(result["deferred"])
            self.assertTrue(result["blocking_defer"])
            self.assertEqual(result["budget_reason"], "event_log_invalid")

    def test_scratch_gc_ancestor_swap_cannot_delete_outside_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            loop_dir = root / "loop-tmp/job"
            run = loop_dir / "run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            outside = Path(directory) / "outside"
            outside_run = outside / "run"
            outside_run.mkdir(parents=True)
            sentinel = outside_run / "sentinel"
            sentinel.write_text("keep")
            original_replace = os.replace

            def swap_then_replace(src, dst, **kwargs):
                moved = loop_dir.with_name("job-original")
                original_replace(loop_dir, moved)
                loop_dir.symlink_to(outside, target_is_directory=True)
                return original_replace(src, dst, **kwargs)

            with mock.patch("runtime.loop.loop_cleanup.os.replace",
                            side_effect=swap_then_replace):
                result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                    starts={})
            self.assertTrue(sentinel.is_file())
            self.assertEqual(result["removed"], 1)
            self.assertFalse((root / "loop-tmp/job-original/run").exists())

    def test_scratch_gc_preserves_run_replaced_after_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            original_replace = os.replace
            swapped = False

            def swap_then_replace(src, dst, **kwargs):
                nonlocal swapped
                if src == "run" and not swapped:
                    swapped = True
                    run.rename(run.with_name("inspected-run"))
                    run.mkdir()
                    (run / ".terminal-unrecorded").touch()
                    (run / "sentinel").write_text("keep")
                    result = original_replace(src, dst, **kwargs)
                    run.mkdir()
                    (run / "late-sentinel").write_text("keep")
                    return result
                return original_replace(src, dst, **kwargs)

            with mock.patch("runtime.loop.loop_cleanup.os.replace",
                            side_effect=swap_then_replace):
                result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                    starts={})
            preserved = next(run.parent.glob("run.gc-trash.*"))
            self.assertTrue((preserved / "sentinel").is_file())
            self.assertTrue((run / "late-sentinel").is_file())
            self.assertTrue(run.with_name("inspected-run").is_dir())
            self.assertEqual((result["removed"], result["errors"]), (0, 1))

    def test_scratch_gc_preserves_trash_replaced_after_inode_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            from runtime.loop import loop_cleanup
            original_clear = loop_cleanup._clear_owned_directory
            swapped = False

            def swap_then_clear(directory_fd, **kwargs):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    trash = next(run.parent.glob("run.gc-trash.*"))
                    trash.rename(run.parent / "inspected-trash")
                    trash.mkdir()
                    (trash / "sentinel").write_text("keep")
                return original_clear(directory_fd, **kwargs)

            with mock.patch("runtime.loop.loop_cleanup._clear_owned_directory",
                            side_effect=swap_then_clear):
                result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                    starts={})
            replacement = next(run.parent.glob("run.gc-trash.*"))
            self.assertTrue((replacement / "sentinel").is_file())
            self.assertEqual((result["removed"], result["errors"]), (0, 1))

    def test_scratch_gc_rejects_loop_tmp_swapped_before_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            outside = Path(directory) / "outside"
            outside_run = outside / "job/run"
            outside_run.mkdir(parents=True)
            sentinel = outside_run / "sentinel"
            sentinel.write_text("keep")
            original_open = os.open
            swapped = False

            def swap_then_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "loop-tmp" and kwargs.get("dir_fd") is not None and not swapped:
                    swapped = True
                    loop_tmp = root / "loop-tmp"
                    loop_tmp.rename(root / "loop-tmp-original")
                    loop_tmp.symlink_to(outside, target_is_directory=True)
                return original_open(path, flags, *args, **kwargs)

            with mock.patch("runtime.loop.central_cleanup.os.open",
                            side_effect=swap_then_open):
                result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                    starts={})
            self.assertTrue(sentinel.is_file())
            self.assertEqual(result["removed"], 0)

    def test_scratch_gc_preserves_missing_start_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": None}))
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={})
            self.assertTrue(run.exists())
            self.assertEqual((result["removed"], result["errors"],
                              result["owner_metadata_invalid"]), (0, 0, 1))

    def test_scratch_gc_preserves_owner_created_after_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            owner = run / ".owner.json"
            owner.write_text(json.dumps({"pid": 11, "process_start": "new-start"}))
            result = scratch_gc({root}, snapshot_started_ns=owner.stat().st_mtime_ns,
                                starts={})
            self.assertTrue(run.is_dir())
            self.assertEqual(result["preserved"], 1)

    def test_scratch_gc_never_follows_loop_directory_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            outside = Path(directory) / "outside/run"
            outside.mkdir(parents=True)
            (outside / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old"}))
            scratch = root / "loop-tmp"
            scratch.mkdir(parents=True)
            (scratch / "job").symlink_to(outside.parent, target_is_directory=True)
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={})
            self.assertTrue(outside.is_dir())
            self.assertEqual(result["removed"], 0)

    def test_scratch_gc_preserves_malformed_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, value in enumerate(([], True, {"pid": -1},
                                           {"pid": True, "process_start": "x"},
                                           {"pid": 11, "process_start": ""})):
                run = root / f"loop-tmp/job/run-{index}"
                run.mkdir(parents=True)
                (run / ".owner.json").write_text(json.dumps(value))
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={})
            self.assertEqual(result["removed"], 0)
            self.assertEqual(result["preserved"], 5)
            self.assertEqual((result["errors"], result["owner_metadata_invalid"]), (0, 5))

    def test_installed_state_roots_uses_plist_runtime_override(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory)
            expected = agents / "custom-state"
            with (agents / "ai.anicca.job.plist").open("wb") as handle:
                import plistlib
                plistlib.dump({"EnvironmentVariables": {
                    "LIFE_MANAGER_STATE_ROOT": str(expected),
                }}, handle)
            self.assertEqual(installed_state_roots(agents), {expected.resolve()})

    def test_installed_state_roots_skips_non_object_plist(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory)
            with (agents / "ai.anicca.bad.plist").open("wb") as handle:
                import plistlib
                plistlib.dump([], handle)
            self.assertEqual(installed_state_roots(agents), set())

    def test_installed_state_roots_skips_one_malformed_xml_plist(self):
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory)
            (agents / "ai.anicca.bad.plist").write_text(
                '<?xml version="1.0"?><plist><dict><key>broken</dict></plist>'
            )
            expected = agents / "healthy-state"
            with (agents / "ai.anicca.healthy.plist").open("wb") as handle:
                import plistlib
                plistlib.dump({"EnvironmentVariables": {
                    "LIFE_MANAGER_STATE_ROOT": str(expected),
                }}, handle)

            self.assertEqual(installed_state_roots(agents), {expected.resolve()})

    def test_loop_run_preserves_python_adapter_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entrypoint = root / 'scheduled_runner.py'
            entrypoint.write_text('#!/usr/bin/env python3\n')
            entrypoint.chmod(0o755)
            registry = {"schema_version": 2, "loops": {"job": {
                "label": "ai.anicca.job", "domain": "growth",
                "entrypoint": "scheduled_runner.py", "adapter": "python",
                "command": ["dashboard"], "cadence": {"run_at_load": True},
                "effect_class": "none", "state_root": "~/state",
                "log_root": "~/state/logs",
                "cleanup": {"max_runs": 1, "max_age_days": 1},
                "provider_route": "deterministic"}}}
            with mock.patch.dict(os.environ, {"HOME": str(root / 'home')}):
                argv = build_loop_command(registry, "job", root)
            self.assertEqual(argv, [sys.executable, str(entrypoint.resolve()), "dashboard"])

    def test_loop_run_preserves_empty_python_adapter_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entrypoint = root / 'application_owner.py'
            entrypoint.write_text('#!/usr/bin/env python3\n')
            entrypoint.chmod(0o755)
            registry = {"schema_version": 2, "loops": {"job": {
                "label": "ai.anicca.job", "domain": "earn",
                "entrypoint": "application_owner.py", "adapter": "python",
                "command": [], "cadence": {"run_at_load": True},
                "effect_class": "application", "state_root": "~/state",
                "log_root": "~/state/logs",
                "cleanup": {"max_runs": 1, "max_age_days": 1},
                "provider_route": "deterministic"}}}
            with mock.patch.dict(os.environ, {"HOME": str(root / 'home')}):
                argv = build_loop_command(registry, "job", root)
            self.assertEqual(argv, [sys.executable, str(entrypoint.resolve())])

    def test_loop_run_preserves_exec_adapter_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entrypoint = root / 'affiliate'
            entrypoint.write_text('#!/bin/sh\n')
            entrypoint.chmod(0o755)
            registry = {"schema_version": 2, "loops": {"job": {
                "label": "ai.anicca.job", "domain": "growth",
                "entrypoint": "affiliate", "adapter": "exec",
                "command": ["sources", "wake"], "cadence": {"run_at_load": True},
                "effect_class": "none", "state_root": "~/state",
                "log_root": "~/state/logs",
                "cleanup": {"max_runs": 1, "max_age_days": 1},
                "provider_route": "deterministic"}}}
            with mock.patch.dict(os.environ, {"HOME": str(root / 'home')}):
                argv = build_loop_command(registry, "job", root)
            self.assertEqual(argv, [str(entrypoint.resolve()), "sources", "wake"])

    def test_loaded_plist_release_is_discovered_as_protected(self):
        import plistlib
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); releases=root/'releases'; release=releases/('20260101T000000-'+'a'*8)
            entry=release/'bin/job.sh'; entry.parent.mkdir(parents=True); entry.write_text('x')
            agents=root/'agents'; agents.mkdir()
            (agents/'ai.anicca.job.plist').write_bytes(plistlib.dumps({
                'Label':'ai.anicca.job','ProgramArguments':[str(entry)]}))
            self.assertEqual(loaded_release_roots(agents,releases),{release.resolve()})

    def test_com_disk_watchdog_release_is_discovered_as_protected(self):
        import plistlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            releases = root / "releases"
            release = releases / ("20260101T000000-" + "b" * 8)
            entry = release / "skills/self/disk-cleanup/disk_cleanup.py"
            entry.parent.mkdir(parents=True)
            entry.write_text("x")
            agents = root / "agents"
            agents.mkdir()
            (agents / "com.example.unrelated.plist").write_bytes(plistlib.dumps({"Label": "com.example.unrelated", "ProgramArguments": ["/usr/bin/true"]}))
            (agents / "unrelated.plist").write_bytes(plistlib.dumps([]))
            (agents / "com.anicca.disk-watchdog.plist").write_bytes(plistlib.dumps({
                "Label": "com.anicca.disk-watchdog",
                "ProgramArguments": ["/usr/bin/python3", str(entry), "--home", str(root / "home")],
            }))

            self.assertEqual(loaded_release_roots(agents, releases), {release.resolve()})

    def test_open_process_release_is_discovered_as_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            releases = Path(directory) / "releases"
            entry = releases / ("20260101T000000-" + "a" * 8) / "bin/job.sh"
            entry.parent.mkdir(parents=True)
            entry.write_text("x")

            completed = mock.Mock(returncode=0, stdout=f"p123\nn{entry}\n", stderr="")
            with mock.patch("runtime.loop.central_cleanup.subprocess.run", return_value=completed) as run:
                self.assertEqual(open_release_roots(releases), {entry.parents[1].resolve()})
            run.assert_called_once_with(
                ["ps", "-axo", "command="], capture_output=True, text=True, timeout=15)

    def test_open_process_release_is_discovered_when_ps_takes_six_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            releases = Path(directory) / "releases"
            entry = releases / ("20260101T000000-" + "a" * 8) / "bin/job.sh"
            entry.parent.mkdir(parents=True)
            entry.write_text("x")

            timeouts = []
            def slow_process_inventory(command, **kwargs):
                timeouts.append(kwargs["timeout"])
                if kwargs["timeout"] < 6:
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                return subprocess.CompletedProcess(command, 0, stdout=f"{entry}\n", stderr="")

            with mock.patch("runtime.loop.central_cleanup.subprocess.run", side_effect=slow_process_inventory):
                self.assertEqual(open_release_roots(releases), {entry.parents[1].resolve()})

        self.assertGreaterEqual(timeouts[0], 6)
        self.assertLessEqual(timeouts[0], 15)

    def _run_terminal_event(self, exit_code: int) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); home = root / "home"; home.mkdir()
            entry = root / "bin/job.sh"; entry.parent.mkdir()
            entry.write_text(f"#!/bin/sh\nexit {exit_code}\n"); entry.chmod(0o755)
            registry = {"schema_version": 2, "loops": {"job": {
                "label": "ai.anicca.job", "domain": "system", "entrypoint": "bin/job.sh",
                "cadence": {"run_at_load": True}, "effect_class": "none",
                "state_root": "~/state", "log_root": "~/state/logs",
                "cleanup": {"max_runs": 1, "max_age_days": 1},
                "provider_route": "deterministic"}}}
            (root / "config").mkdir(); (root / "config/loop-registry.json").write_text(json.dumps(registry))
            (root / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
            command = (
                "from runtime.loop import lm_loop_run; "
                "lm_loop_run._producer_gate = lambda *_a, **_k: None; "
                f"raise SystemExit(lm_loop_run.main(['job', {str(root)!r}]))"
            )
            result = subprocess.run(
                [sys.executable, "-c", command],
                cwd=Path(__file__).parents[3], env={**os.environ, "HOME": str(home),
                    "LIFE_MANAGER_MAX_LOAD_PER_CPU": "100000",
                    "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(root / "admission")},
                check=False)
            self.assertEqual(result.returncode, exit_code)
            event = json.loads((home / "state/events.jsonl").read_text().splitlines()[-1])
            return validate_runtime_event(event)

    def test_loop_run_records_success_terminal_event(self):
        event = self._run_terminal_event(0)
        self.assertEqual((event["status"], event["release_sha"], event["provider"]),
                         ("pass", "a" * 40, "deterministic"))
        self.assertEqual(event["effect_status"], "not_applicable")
        self.assertTrue(event["evidence_refs"][0].startswith("lm-loop://job/"))

    def test_loop_run_passes_release_root_to_entrypoint_without_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); home = root / "home"; home.mkdir()
            entry = root / "bin/job.sh"; entry.parent.mkdir()
            observed = home / "release-root.txt"
            entry.write_text(
                f'#!/bin/sh\nprintf "%s\\n%s" "$LIFE_MANAGER_RELEASE_ROOT" '
                f'"$LIFE_MANAGER_REPO" > "{observed}"\n')
            entry.chmod(0o755)
            registry = {"schema_version": 2, "loops": {"job": {
                "label": "ai.anicca.job", "domain": "system", "entrypoint": "bin/job.sh",
                "cadence": {"run_at_load": True}, "effect_class": "none",
                "state_root": "~/state", "log_root": "~/state/logs",
                "cleanup": {"max_runs": 1, "max_age_days": 1},
                "provider_route": "deterministic"}}}
            (root / "config").mkdir()
            (root / "config/loop-registry.json").write_text(json.dumps(registry))
            (root / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
            environment = {
                **os.environ,
                "HOME": str(home),
                "LIFE_MANAGER_MAX_LOAD_PER_CPU": "100000",
                "LIFE_MANAGER_RELEASE_ROOT": "",
                "LIFE_MANAGER_REPO": "source-sentinel",
                "LIFE_MANAGER_RESOURCE_ADMISSION_ROOT": str(root / "admission"),
            }
            command = (
                "from runtime.loop import lm_loop_run; "
                "lm_loop_run._producer_gate = lambda *_a, **_k: None; "
                f"raise SystemExit(lm_loop_run.main(['job', {str(root)!r}]))"
            )
            result = subprocess.run(
                [sys.executable, "-c", command],
                cwd=Path(__file__).parents[3], env=environment, check=False)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(observed.read_text().splitlines(), [str(root.resolve()), "source-sentinel"])

    def test_loop_run_records_failed_terminal_event(self):
        event = self._run_terminal_event(7)
        self.assertEqual((event["status"], event["blocker"]),
                         ("fail", "entrypoint_exit_7"))

    def test_loop_run_terminates_entrypoint_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); home=root/'home'; home.mkdir()
            entry=root/'bin/job.sh'; entry.parent.mkdir()
            pid_file=home/'grandchild.pid'
            entry.write_text(f'#!/bin/sh\nsleep 60 &\necho $! > "{pid_file}"\nwait\n')
            entry.chmod(0o755)
            registry={"schema_version":2,"loops":{"job":{
                "label":"ai.anicca.job","domain":"system","entrypoint":"bin/job.sh",
                "cadence":{"keep_alive":True},"effect_class":"none",
                "state_root":"~/state","log_root":"~/state/logs",
                "cleanup":{"max_runs":1,"max_age_days":1},"provider_route":"deterministic"}}}
            (root/'config').mkdir();(root/'config/loop-registry.json').write_text(json.dumps(registry))
            (root/'RELEASE.json').write_text(json.dumps({'sha':'a'*40}))
            wrapper=subprocess.Popen(
                [sys.executable,'-m','runtime.loop.lm_loop_run','job',str(root)],
                cwd=Path(__file__).parents[3],env={**os.environ,'HOME':str(home),
                                                   'LIFE_MANAGER_MAX_LOAD_PER_CPU':'100000'})
            for _ in range(50):
                if pid_file.exists():break
                time.sleep(0.02)
            grandchild=int(pid_file.read_text())
            start_event=json.loads((home/'state/events.jsonl').read_text().splitlines()[-1])
            self.assertEqual(start_event['status'],'running')
            wrapper.terminate();wrapper.wait(timeout=5);time.sleep(0.1)
            with self.assertRaises(ProcessLookupError):
                os.kill(grandchild,0)

    def test_continuous_loop_releases_apply_lock_after_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); home = root / "home"; home.mkdir()
            entry = root / "bin/job.sh"; entry.parent.mkdir()
            started = home / "started"
            entry.write_text(f'#!/bin/sh\ntouch "{started}"\nsleep 60\n')
            entry.chmod(0o755)
            registry = {"schema_version": 2, "loops": {"job": {
                "label": "ai.anicca.job", "domain": "system", "entrypoint": "bin/job.sh",
                "cadence": {"keep_alive": True}, "effect_class": "none",
                "state_root": "~/state", "log_root": "~/state/logs",
                "cleanup": {"max_runs": 1, "max_age_days": 1},
                "provider_route": "deterministic"}}}
            (root / "config").mkdir()
            (root / "config/loop-registry.json").write_text(json.dumps(registry))
            (root / "RELEASE.json").write_text(json.dumps({"sha": "a" * 40}))
            wrapper = subprocess.Popen(
                [sys.executable, "-m", "runtime.loop.lm_loop_run", "job", str(root)],
                cwd=Path(__file__).parents[3], env={**os.environ, "HOME": str(home),
                                                    "LIFE_MANAGER_MAX_LOAD_PER_CPU": "100000"})
            try:
                for _ in range(100):
                    if started.exists():
                        break
                    time.sleep(0.02)
                self.assertTrue(started.exists())
                lock = home / "loops/.apply-locks/ai.anicca.job.lock"
                with lock.open("a+") as handle:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                wrapper.terminate()
                wrapper.wait(timeout=5)

    def test_release_gc_preserves_release_loaded_by_launchd(self):
        import plistlib
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); releases=root/'releases'; releases.mkdir()
            paths=[]
            for index in range(4):
                path=releases/f"2026010{index}T000000-{'a'*7}{index}"; path.mkdir()
                (path/'RELEASE.json').write_text(json.dumps({'sha':f'{index:040x}'}))
                os.utime(path,(index,index)); paths.append(path)
            entry=paths[0]/'bin/lm-loop-run'; entry.parent.mkdir(); entry.write_text('#!/bin/sh\n')
            current=root/'current'; current.symlink_to(paths[3])
            agents=root/'agents'; agents.mkdir()
            (agents/'ai.anicca.job.plist').write_bytes(plistlib.dumps({
                'Label':'ai.anicca.job',
                'ProgramArguments':[str(paths[0]/'bin/lm-loop-run')],
            }))
            protected_file = root / "protected-releases.json"
            protected_file.write_text("[]")
            with mock.patch.dict(os.environ, {
                "LIFE_MANAGER_PROTECTED_RELEASES": str(protected_file),
            }):
                result=release_gc(releases,current,agents,keep=1)
            self.assertTrue(paths[0].exists())
            self.assertFalse(paths[1].exists())
            self.assertTrue(paths[3].exists())
            self.assertEqual(result['protected_release_count'],1)

    def test_release_gc_preserves_release_used_by_open_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); releases = root / "releases"; releases.mkdir()
            paths = []
            for index in range(4):
                path = releases / f"2026010{index}T000000-{'a' * 7}{index}"
                path.mkdir(); (path / "RELEASE.json").write_text(json.dumps({"sha": f"{index:040x}"}))
                os.utime(path, (index, index)); paths.append(path)
            current = root / "current"; current.symlink_to(paths[3])
            agents = root / "agents"; agents.mkdir(); (agents / "com.example.unrelated.plist").write_bytes(plistlib.dumps({"Label": "com.example.unrelated", "ProgramArguments": ["/usr/bin/true"]}))
            protected_file = root / "protected-releases.json"
            protected_file.write_text("[]")
            with (
                mock.patch.dict(os.environ, {
                    "LIFE_MANAGER_PROTECTED_RELEASES": str(protected_file),
                }),
                mock.patch(
                    "runtime.loop.central_cleanup.open_release_roots",
                    return_value={paths[0].resolve()},
                ),
            ):
                result = release_gc(releases, current, agents, keep=1)
            self.assertTrue(paths[0].exists())
            self.assertFalse(paths[1].exists())
            self.assertTrue(paths[2].exists())
            self.assertTrue(paths[3].exists())
            self.assertEqual(result["protected_release_count"], 1)


if __name__ == "__main__": unittest.main()


class PruneToEvidenceTest(unittest.TestCase):
    def test_keeps_small_evidence_and_removes_bulk_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            (root / "set-001" / "images").mkdir(parents=True)
            (root / "profile" / "Default").mkdir(parents=True)
            (root / "effect-identity.jsonl").write_text('{"id":"x"}\n')
            (root / "set-001" / "submit-response.json").write_text("{}")
            (root / "set-001" / "images" / "01.png").write_bytes(b"p" * 4096)
            (root / "profile" / "Default" / "Cookies").write_bytes(b"c" * 128)
            (root / "huge.log").write_bytes(b"l" * (1024 * 1024 + 1))
            (root / "link.json").symlink_to(root / "effect-identity.jsonl")

            removed = loop_cleanup.prune_to_evidence(root)

            self.assertTrue((root / "effect-identity.jsonl").exists())
            self.assertTrue((root / "set-001" / "submit-response.json").exists())
            self.assertFalse((root / "set-001" / "images").exists())
            self.assertFalse((root / "profile").exists())
            self.assertFalse((root / "huge.log").exists())
            self.assertFalse((root / "link.json").is_symlink())
            self.assertGreaterEqual(removed, 4096 + 128 + 1024 * 1024 + 1)

    def test_total_evidence_budget_keeps_smallest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            root.mkdir()
            for index in range(10):
                (root / f"e{index}.json").write_bytes(b"j" * (1024 * 1024 - 10 + index))
            loop_cleanup.prune_to_evidence(root)
            kept = sorted(p.name for p in root.iterdir())
            self.assertEqual(kept, [f"e{index}.json" for index in range(8)])

    def test_preserves_markers_and_protected_subtrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            (root / "keep").mkdir(parents=True)
            (root / ".terminal-unrecorded").write_bytes(b"")
            (root / "keep" / ".lm-protected").write_bytes(b"")
            (root / "keep" / "asset.png").write_bytes(b"p" * 64)
            loop_cleanup.prune_to_evidence(root)
            self.assertTrue((root / ".terminal-unrecorded").exists())
            self.assertTrue((root / "keep" / "asset.png").exists())
