import json
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
from runtime.loop.central_cleanup import open_release_roots, release_gc, scratch_gc
from runtime.loop.central_cleanup import host_cleanup_command, host_cleanup_ok


def completed(root: Path, name: str, size: int = 1) -> Path:
    run = root / "runs" / name; run.mkdir(parents=True)
    (run / ".lm-regenerable").write_text("1\n")
    (run / "summary.json").write_text("{}\n")
    (run / "payload.bin").write_bytes(b"x" * size)
    return run


class LoopCleanupTest(unittest.TestCase):
    def test_host_cleanup_uses_durable_shared_pressure_state(self):
        command = host_cleanup_command(Path('/release'), Path('/home'))
        self.assertEqual(command[-4:], [
            '--home', '/home', '--state-dir',
            '/home/.local/state/life-manager/state',
        ])

    def test_host_cleanup_accepts_registry_projected_state_root(self):
        command = host_cleanup_command(
            Path('/release'), Path('/home'), Path('/state/life-manager')
        )
        self.assertEqual(command[-1], '/state/life-manager')

    def test_host_cleanup_error_cannot_be_reported_as_success(self):
        self.assertFalse(host_cleanup_ok(0, {"errors": 1, "protected_deletions": 0}))
        self.assertFalse(host_cleanup_ok(0, {"errors": 0, "protected_deletions": 1}))
        self.assertTrue(host_cleanup_ok(0, {"errors": 0, "protected_deletions": 0}))
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

            def unknown_publish(_command, _entry, _loop_id, env, receipt, *, occurrence_id, on_claimed):
                observed.update(env)
                observed["LIFE_MANAGER_OCCURRENCE_ID"] = occurrence_id
                on_claimed(occurrence_id)
                Path(env["LIFE_MANAGER_EFFECT_IDENTITY_PATH"]).write_text(
                    '{"job_id":"marketing-video-publication:job-1"}\n', encoding="utf-8",
                )
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
                identity_files[0].read_text(encoding="utf-8"),
                '{"job_id":"marketing-video-publication:job-1"}\n',
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
                self.assertEqual(lm_loop_run.main(["job", str(root)]), 0)
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
            result = scratch_gc({root}, snapshot_started_ns=time.time_ns() + 1,
                                starts={10: "live-start"})
            self.assertTrue(live.is_dir())
            self.assertFalse(stale.exists())
            self.assertEqual((result["removed"], result["preserved"]), (1, 1))

    def test_scratch_gc_fails_closed_without_identity_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "loop-tmp/job/run"
            run.mkdir(parents=True)
            (run / ".owner.json").write_text(json.dumps(
                {"pid": 11, "process_start": "old-start"}))
            with mock.patch("runtime.loop.central_cleanup.process_starts", return_value=None):
                result = scratch_gc({root})
            self.assertTrue(run.is_dir())
            self.assertFalse(result["identity_snapshot_available"])

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

            def swap_then_clear(directory_fd):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    trash = next(run.parent.glob("run.gc-trash.*"))
                    trash.rename(run.parent / "inspected-trash")
                    trash.mkdir()
                    (trash / "sentinel").write_text("keep")
                return original_clear(directory_fd)

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
            self.assertEqual((result["removed"], result["errors"]), (0, 1))

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
            self.assertEqual(result["errors"], 5)

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
            ["ps", "-axo", "command="], capture_output=True, text=True, timeout=120)

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
            result = subprocess.run(
                [sys.executable, "-m", "runtime.loop.lm_loop_run", "job", str(root)],
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
            result = subprocess.run(
                [sys.executable, "-m", "runtime.loop.lm_loop_run", "job", str(root)],
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
            agents = root / "agents"; agents.mkdir()
            with mock.patch(
                "runtime.loop.central_cleanup.open_release_roots",
                return_value={paths[0].resolve()},
            ):
                result = release_gc(releases, current, agents, keep=1)
            self.assertTrue(paths[0].exists())
            self.assertFalse(paths[1].exists())
            self.assertTrue(paths[2].exists())
            self.assertTrue(paths[3].exists())
            self.assertEqual(result["protected_release_count"], 1)


if __name__ == "__main__": unittest.main()
