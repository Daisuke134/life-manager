import json
import os
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.loop.local_install import installation_plan, apply_targets, apply_host_owners, cut_release, validate_release, prepare_product_state


ROOT = Path(__file__).resolve().parents[3]
SHA = "a" * 40


def release_fixture(root, *, sha=SHA):
    root.mkdir(parents=True)
    registry = json.loads((ROOT / "config/loop-registry.json").read_text())
    owner = "life-manager-daily-driver"
    entry = registry["loops"][owner]
    for relative in ("bin/lm-loop", "bin/lm-loop-run", entry["entrypoint"]):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o700)
    config = root / "config/loop-registry.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"schema_version": 2, "loops": {owner: entry}}))
    tag = os.sys.implementation.cache_tag
    cache = root / "runtime/loop/__pycache__" / f"lm_loop_run.{tag}.pyc"
    cache.parent.mkdir(parents=True)
    cache.touch()
    (root / "RELEASE.json").write_text(json.dumps({
        "sha": sha, "provenance": "ancestor-of-origin-main", "release_paths": "ALL",
        "runtime_python": os.sys.executable, "runtime_python_cache_tag": tag,
    }))
    return root


def git_read_result(command):
    if command[0] != "git":
        return None
    return subprocess.CompletedProcess(command, 0, SHA + "\n" if "rev-parse" in command else "", "")


class LocalInstallTest(unittest.TestCase):
    def test_agent_economy_prepares_own_state_with_existing_release_installer(self):
        calls = []
        def run(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, "private output", "")
        profile = {"tenant_id": "local-owner", "environment_file": "/owner/.local/state/life-manager/.env"}
        env = {"LIFE_MANAGER_HOME": "/owner/.local/state/life-manager", "PATH": "/owner/tools:/usr/bin"}
        result = prepare_product_state(ROOT, ["agent-economy-loop"], profile, env, runner=run)
        self.assertEqual(calls[0][0], ["bash", str(ROOT / "install.sh")])
        self.assertEqual(calls[0][1]["cwd"], ROOT)
        child = calls[0][1]["env"]
        self.assertEqual(child["LIFE_MANAGER_INSTALL_DAEMON"], "0")
        self.assertEqual(child["LIFE_MANAGER_INSTALL_DEPS"], "0")
        self.assertEqual(child["LIFE_MANAGER_HOME"], env["LIFE_MANAGER_HOME"])
        self.assertEqual(child["LIFE_MANAGER_TENANT_ID"], "local-owner")
        self.assertEqual(result, [{"agent": "agent-economy", "state": "prepared"}])

    def test_product_state_is_not_prepared_for_other_agents_and_failure_is_propagated(self):
        def fail(command, **kwargs):
            return subprocess.CompletedProcess(command, 2, "private output", "private error")
        self.assertEqual(prepare_product_state(ROOT, ["hf-gig-browser"], {}, {}, runner=fail), [])
        with self.assertRaisesRegex(RuntimeError, "state preparation failed"):
            prepare_product_state(ROOT, ["agent-economy-loop"], {"tenant_id": "local-owner"}, {}, runner=fail)

    def test_plan_covers_every_owner_and_keeps_external_owners_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            result = installation_plan(ROOT, home=home)
            self.assertEqual(len(result["jobs"]), 191)
            self.assertEqual(len(result["external_labels"]), 15)
            self.assertEqual(result["host_owners"][0]["label"], "com.anicca.disk-watchdog")
            self.assertEqual(result["host_state"], "setup_required")
            self.assertFalse((home / ".config").exists())
            self.assertFalse(result["business_outcomes_verified"])

    def test_public_local_plan_dispatch_does_not_prepare_the_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            completed = subprocess.run(["bash", str(ROOT / "install.sh"), "local", "plan"],
                env={**os.environ, "HOME": str(home), "LIFE_MANAGER_PYTHON": os.sys.executable},
                capture_output=True, text=True, timeout=15)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["coverage"]["registered_jobs"], 191)
            self.assertEqual(list(home.iterdir()), [])

    def test_apply_checks_gui_before_label_probe_and_preserves_loaded_owners(self):
        calls = []
        def run(command, **kwargs):
            calls.append((command, kwargs))
            if command[1:] == ["preflight"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if command[1:2] == ["print"]:
                if command[-1].endswith(".hf-gig-browser"):
                    return subprocess.CompletedProcess(command, 113, "", "Could not find service")
                return subprocess.CompletedProcess(command, 0, "state = running", "")
            owner = kwargs["env"]["LIFE_MANAGER_APPLY_TARGET"]
            registry = json.loads((ROOT / "config/loop-registry.json").read_text())
            return subprocess.CompletedProcess(command, 0, json.dumps([{"ok": True,
                "label": registry["loops"][owner]["label"]}]), "")
        result = apply_targets(ROOT, ["hf-gig-browser", "hf-gig-paid-direct"], {"TEST": "own"}, runner=run)
        self.assertEqual(calls[0][0][1:], ["preflight"])
        apply_calls = [(cmd, kw) for cmd, kw in calls if "apply" in cmd]
        self.assertEqual(len(apply_calls), 2)
        self.assertNotIn("--loaded-idle-only", apply_calls[0][0])
        self.assertIn("--loaded-idle-only", apply_calls[1][0])
        self.assertEqual(apply_calls[0][1]["env"]["LIFE_MANAGER_RELEASE_ROOT"], str(ROOT))
        self.assertEqual(len(result), 2)

    def test_preflight_or_unknown_label_readback_never_applies(self):
        for fail_preflight in (True, False):
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                code = 75 if fail_preflight or command[1:2] == ["print"] else 0
                return subprocess.CompletedProcess(command, code, "", "permission denied")
            with self.assertRaisesRegex(RuntimeError, "preflight|readback"):
                apply_targets(ROOT, ["hf-gig-browser"], {}, runner=run)
            self.assertFalse(any("apply" in command for command in calls))
            if fail_preflight:
                self.assertEqual(len(calls), 1)

    def test_apply_propagates_failed_owner_result_even_on_zero_exit(self):
        def run(command, **kwargs):
            if "apply" in command:
                return subprocess.CompletedProcess(command, 0, '[{"ok":false,"error":"fixture"}]', "")
            return subprocess.CompletedProcess(command, 0, "state = running", "")
        with self.assertRaisesRegex(RuntimeError, "owner apply"):
            apply_targets(ROOT, ["hf-gig-browser"], {}, runner=run)

    def test_matching_release_with_different_host_binding_is_not_accepted(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if "apply" in command:
                return subprocess.CompletedProcess(command, 0, json.dumps([{
                    "ok": True, "label": "ai.anicca.hf-gig-browser", "skipped": "loaded-running"}]), "")
            text = f"arguments = {{\n{ROOT}/bin/lm-loop-run\nhf-gig-browser\n{ROOT}\n}}\n"
            return subprocess.CompletedProcess(command, 0, text, "")
        result = apply_targets(ROOT, ["hf-gig-browser"], {"LIFE_MANAGER_HOST_PROFILE": "/own/host.json"}, runner=run)
        self.assertTrue(any("--loaded-idle-only" in command for command in calls))
        self.assertEqual(result[0]["skipped"], "loaded-running")

    def test_installer_control_variables_do_not_make_exact_plist_wait_forever(self):
        from runtime.host.local_profile import prepare_host, host_environment
        from runtime.loop.lm_loop_apply import _plist
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"HOME": str(Path(temporary).resolve())}):
            prepare_host(ROOT, python=Path(os.sys.executable), node=Path(os.sys.executable))
            registry = json.loads((ROOT / "config/loop-registry.json").read_text())
            row = plistlib.loads(_plist("hf-gig-browser", registry["loops"]["hf-gig-browser"], ROOT, "a" * 40))
            text = "arguments = {\n" + "\n".join(row["ProgramArguments"]) + "\n}\nenvironment = {\n"
            text += "\n".join(f"{key} => {value}" for key, value in row["EnvironmentVariables"].items()) + "\n}\n"
            def run(command, **kwargs):
                self.assertNotIn("apply", command)
                return subprocess.CompletedProcess(command, 0, text, "")
            env = {**host_environment(), "LIFE_MANAGER_SOURCE_REPO": str(ROOT), "LIFE_MANAGER_APPLY_REQUIRE_CURRENT": "0"}
            result = apply_targets(ROOT, ["hf-gig-browser"], env, runner=run)
            self.assertEqual(result[0]["readback"], "exact_release_loaded")

    def test_additional_owner_is_installed_only_after_confirmed_absence(self):
        owner = {"label": "com.anicca.disk-watchdog", "installer": "skills/self/disk-cleanup/install-launchd.sh",
                 "program": "bin/disk-watchdog.sh"}
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if command[1:2] == ["print"]:
                probes = sum(call[1:2] == ["print"] for call in calls)
                if probes == 1:
                    return subprocess.CompletedProcess(command, 113, "", "Could not find service")
                return subprocess.CompletedProcess(command, 0,
                    f"arguments = {{\n{ROOT}/bin/disk-watchdog.sh\n}}", "")
            return subprocess.CompletedProcess(command, 0, "", "")
        result = apply_host_owners(ROOT, [owner], {"LIFE_MANAGER_RUNTIME_PYTHON": os.sys.executable}, runner=run)
        self.assertEqual(calls[0][1:], ["preflight"])
        self.assertTrue(result[0]["changed"])
        self.assertEqual(sum(command[0] == "bash" for command in calls), 1)

    def test_cut_is_idempotent_between_initial_friend_setup_and_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            release = home / "loops/releases/20261023T000000-aaaaaaaa"
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                read = git_read_result(command)
                if read is not None:
                    return read
                self.assertEqual(command, ["bash", str(ROOT / "bin/cut-loop-release.sh"), "HEAD"])
                self.assertEqual(kwargs["env"]["LOOPS_ACTIVATE_CURRENT"], "0")
                self.assertEqual(kwargs["env"]["LOOPS_RELEASE_PATHS"], "")
                built = release if sum(call[0] == "bash" for call in calls) == 1 else release_fixture(
                    home / "loops/releases/20261023T010000-aaaaaaaa")
                if not built.exists():
                    release_fixture(built)
                return subprocess.CompletedProcess(command, 0,
                    f"release -> {built}  (ancestor-of-origin-main; current unchanged)\n", "")
            environment = {"LIFE_MANAGER_RUNTIME_PYTHON": os.sys.executable}
            with patch.dict(os.environ, {"HOME": str(home), "LOOPS_ROOT": str(home / "loops"), "LIFE_MANAGER_HOST_PROFILE": ""}), \
                    patch("runtime.loop.lm_loop_apply._managed_node", return_value=os.sys.executable):
                self.assertEqual(cut_release(ROOT, environment, runner=run), release)
                self.assertEqual(cut_release(ROOT, environment, runner=run), release)
            self.assertEqual(sum(command[0] == "bash" for command in calls), 1)
            self.assertFalse((home / "loops/current").exists())

    def test_reuse_rejects_invalid_complete_release_candidates(self):
        for invalid in ("cache-tag", "reclaimed", "missing-runner", "missing-entrypoint",
                        "foreign-runtime", "different-sha", "non-main", "sparse"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary).resolve()
                stale = release_fixture(home / "loops/releases/20261023T000000-aaaaaaaa")
                receipt = json.loads((stale / "RELEASE.json").read_text())
                if invalid == "cache-tag":
                    receipt["runtime_python_cache_tag"] = "wrong-cache-tag"
                elif invalid == "reclaimed":
                    (stale / "RECLAIMED-RELEASE.json").write_text("{}")
                elif invalid == "missing-runner":
                    (stale / "bin/lm-loop-run").unlink()
                elif invalid == "missing-entrypoint":
                    registry = json.loads((stale / "config/loop-registry.json").read_text())
                    (stale / registry["loops"]["life-manager-daily-driver"]["entrypoint"]).unlink()
                elif invalid == "foreign-runtime":
                    receipt["runtime_python"] = "/another/owner/python"
                elif invalid == "different-sha":
                    receipt["sha"] = "b" * 40
                elif invalid == "non-main":
                    receipt["provenance"] = "pushed-not-yet-on-main"
                else:
                    receipt["release_paths"] = "runtime"
                (stale / "RELEASE.json").write_text(json.dumps(receipt))
                fresh = home / "loops/releases/20261023T010000-aaaaaaaa"
                def run(command, **kwargs):
                    read = git_read_result(command)
                    if read is not None:
                        return read
                    release_fixture(fresh)
                    return subprocess.CompletedProcess(command, 0,
                        f"release -> {fresh}  (ancestor-of-origin-main; current unchanged)\n", "")
                with patch.dict(os.environ, {"HOME": str(home), "LOOPS_ROOT": str(home / "loops"), "LIFE_MANAGER_HOST_PROFILE": ""}), \
                        patch("runtime.loop.lm_loop_apply._managed_node", return_value=os.sys.executable):
                    self.assertEqual(cut_release(ROOT, {"LIFE_MANAGER_RUNTIME_PYTHON": os.sys.executable}, runner=run), fresh)

    def test_cut_refuses_a_source_commit_outside_main_without_building(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            self.assertEqual(command[0], "git")
            return subprocess.CompletedProcess(command, 1 if "merge-base" in command else 0, SHA, "")
        with self.assertRaisesRegex(RuntimeError, "main"):
            cut_release(ROOT, {"LIFE_MANAGER_RUNTIME_PYTHON": os.sys.executable}, runner=run)
        self.assertFalse(any(command[0] == "bash" for command in calls))

    def test_valid_same_sha_current_is_preferred_over_another_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            current = release_fixture(home / "loops/releases/20261023T000000-aaaaaaaa")
            release_fixture(home / "loops/releases/20261023T010000-aaaaaaaa")
            (home / "loops/current").symlink_to(current)
            def run(command, **kwargs):
                result = git_read_result(command)
                self.assertIsNotNone(result, "existing release must not be rebuilt")
                return result
            with patch.dict(os.environ, {"HOME": str(home), "LOOPS_ROOT": str(home / "loops"), "LIFE_MANAGER_HOST_PROFILE": ""}), \
                    patch("runtime.loop.lm_loop_apply._managed_node", return_value=os.sys.executable):
                result = cut_release(ROOT, {"LIFE_MANAGER_RUNTIME_PYTHON": os.sys.executable}, runner=run)
            self.assertEqual(result, current)
            self.assertEqual((home / "loops/current").resolve(), current)

    def test_same_sha_running_browser_can_keep_its_actual_other_release_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary).resolve()
            loaded = release_fixture(home / "loops/releases/20261023T000000-aaaaaaaa")
            requested = release_fixture(home / "loops/releases/20261023T010000-aaaaaaaa")
            (home / "loops/current").symlink_to(requested)
            environment = {"LIFE_MANAGER_RUNTIME_PYTHON": os.sys.executable,
                           "LIFE_MANAGER_HOST_PROFILE": str(home / "host.json")}
            text = f"arguments = {{\n{loaded}/bin/lm-loop-run\nlife-manager-daily-driver\n{loaded}\n}}\nenvironment = {{\n"
            text += "\n".join(f"{key} => {value}" for key, value in {
                **environment, "LIFE_MANAGER_LOOP_ID": "life-manager-daily-driver",
                "LIFE_MANAGER_RELEASE_SHA": SHA, "LIFE_MANAGER_REPO": str(loaded),
            }.items()) + "\n}\n"
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                read = git_read_result(command)
                if read is not None:
                    return read
                if "apply" in command:
                    return subprocess.CompletedProcess(command, 0, json.dumps([{
                        "ok": True, "label": "ai.anicca.life-manager-daily-driver", "skipped": "loaded-running"}]), "")
                return subprocess.CompletedProcess(command, 0, text, "")
            with patch.dict(os.environ, {"HOME": str(home), "LOOPS_ROOT": str(home / "loops"), "LIFE_MANAGER_HOST_PROFILE": ""}), \
                    patch("runtime.loop.lm_loop_apply._managed_node", return_value=os.sys.executable):
                selected = cut_release(ROOT, environment, runner=run)
                self.assertEqual(selected, requested)
                result = apply_targets(selected, ["life-manager-daily-driver"], environment, runner=run)
            self.assertEqual(result[0].get("readback"), "same_sha_release_loaded")
            self.assertEqual(result[0]["loaded_root"], str(loaded))
            self.assertEqual(result[0]["loaded_arguments"], [str(loaded / "bin/lm-loop-run"), "life-manager-daily-driver", str(loaded)])
            self.assertFalse(any("apply" in command for command in calls))
            self.assertEqual(sum(command[1:2] == ["print"] for command in calls), 1)

    def test_incompatible_loaded_release_or_owner_environment_stays_waiting(self):
        for invalid in ("different-sha", "foreign-runtime", "cache-tag", "reclaimed",
                        "missing-runner", "host-binding", "owner-environment"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary).resolve()
                loaded = release_fixture(home / "loops/releases/20261023T000000-aaaaaaaa")
                requested = release_fixture(home / "loops/releases/20261023T010000-aaaaaaaa")
                environment = {"LIFE_MANAGER_RUNTIME_PYTHON": os.sys.executable,
                               "LIFE_MANAGER_HOST_PROFILE": str(home / "host.json")}
                receipt = json.loads((loaded / "RELEASE.json").read_text())
                observed = {**environment, "LIFE_MANAGER_LOOP_ID": "life-manager-daily-driver",
                            "LIFE_MANAGER_RELEASE_SHA": SHA, "LIFE_MANAGER_REPO": str(loaded)}
                if invalid == "different-sha":
                    receipt["sha"] = "b" * 40
                elif invalid == "foreign-runtime":
                    receipt["runtime_python"] = "/another/owner/python"
                elif invalid == "cache-tag":
                    receipt["runtime_python_cache_tag"] = "wrong-cache-tag"
                elif invalid == "reclaimed":
                    (loaded / "RECLAIMED-RELEASE.json").write_text("{}")
                elif invalid == "missing-runner":
                    (loaded / "bin/lm-loop-run").unlink()
                elif invalid == "host-binding":
                    observed["LIFE_MANAGER_HOST_PROFILE"] = "/another/owner/host.json"
                else:
                    observed["LIFE_MANAGER_LOOP_ID"] = "another-owner"
                (loaded / "RELEASE.json").write_text(json.dumps(receipt))
                text = f"arguments = {{\n{loaded}/bin/lm-loop-run\nlife-manager-daily-driver\n{loaded}\n}}\nenvironment = {{\n"
                text += "\n".join(f"{key} => {value}" for key, value in observed.items()) + "\n}\n"
                calls = []
                def run(command, **kwargs):
                    calls.append(command)
                    if "apply" in command:
                        return subprocess.CompletedProcess(command, 0, json.dumps([{
                            "ok": True, "label": "ai.anicca.life-manager-daily-driver", "skipped": "loaded-running"}]), "")
                    return subprocess.CompletedProcess(command, 0, text, "")
                with patch.dict(os.environ, {"HOME": str(home), "LIFE_MANAGER_HOST_PROFILE": ""}), \
                        patch("runtime.loop.lm_loop_apply._managed_node", return_value=os.sys.executable):
                    result = apply_targets(requested, ["life-manager-daily-driver"], environment, runner=run)
                self.assertEqual(result[0]["skipped"], "loaded-running")
                self.assertTrue(any("--loaded-idle-only" in command for command in calls))

    def test_non_main_sparse_and_foreign_python_releases_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for key, value in (("provenance", "pushed-not-yet-on-main"), ("release_paths", "runtime"),
                               ("runtime_python", "/someone/else/python")):
                manifest = {"sha": "a" * 40, "provenance": "ancestor-of-origin-main",
                            "release_paths": "ALL", "runtime_python": os.sys.executable}
                manifest[key] = value
                (root / "RELEASE.json").write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    validate_release(root, {"runtime": {"python": os.sys.executable}})


if __name__ == "__main__":
    unittest.main()
