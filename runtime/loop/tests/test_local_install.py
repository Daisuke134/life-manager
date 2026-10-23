import json
import os
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.loop.local_install import installation_plan, apply_targets, apply_host_owners, cut_release, validate_release


ROOT = Path(__file__).resolve().parents[3]


class LocalInstallTest(unittest.TestCase):
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

    def test_cut_uses_existing_builder_without_switching_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary).resolve()
            def run(command, **kwargs):
                self.assertEqual(command, ["bash", str(ROOT / "bin/cut-loop-release.sh"), "HEAD"])
                self.assertEqual(kwargs["env"]["LOOPS_ACTIVATE_CURRENT"], "0")
                self.assertEqual(kwargs["env"]["LOOPS_RELEASE_PATHS"], "")
                return subprocess.CompletedProcess(command, 0,
                    f"release -> {release}  (ancestor-of-origin-main; current unchanged)\n", "")
            self.assertEqual(cut_release(ROOT, {"LIFE_MANAGER_RUNTIME_PYTHON": os.sys.executable}, runner=run), release)

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
