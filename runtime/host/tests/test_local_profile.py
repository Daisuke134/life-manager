import json
import os
import stat
import plistlib
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.host.local_profile import prepare_host, load_host_profile, host_environment


ROOT = Path(__file__).resolve().parents[3]


class LocalProfileTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "Another Person"
        self.home.mkdir()
        self.repo = ROOT
        self.python = self.home / "venv/bin/python"
        subprocess.run([os.sys.executable, "-m", "venv", "--without-pip", str(self.python.parent.parent)],
                       check=True, capture_output=True)
        self.node = self.home / "tools/node"
        self.node.parent.mkdir()
        self.node.write_text("#!/bin/sh\nexit 0\n")
        self.node.chmod(0o755)

    def prepare(self):
        return prepare_host(self.repo, home=self.home, python=self.python, node=self.node)

    def test_own_home_paths_venv_identity_and_permissions(self):
        profile = self.prepare()
        self.assertEqual(profile["runtime"]["python"], str(self.python))
        self.assertEqual(profile["owner_home"], str(self.home))
        self.assertNotEqual(profile["tenant_id"], "dais-local")
        for key in ("browser_registry", "agent_runner_config", "environment_file"):
            target = Path(profile[key])
            self.assertTrue(target.is_relative_to(self.home))
            self.assertTrue(target.is_file())
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        path = self.home / ".config/life-manager/host.json"
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(load_host_profile(home=self.home), profile)

    def test_only_existing_auth_seats_are_used_without_reading_auth(self):
        auth = self.home / ".codex/auth.json"
        auth.parent.mkdir()
        auth.write_text("DO NOT READ OR COPY THIS SECRET")
        profile = self.prepare()
        runner_text = Path(profile["agent_runner_config"]).read_text()
        runner = json.loads(runner_text)
        self.assertEqual(runner["providers"]["codex"]["account_profile_order"], ["acct1"])
        self.assertEqual(set(runner["providers"]["codex"]["profiles"]), {"acct1"})
        self.assertNotIn("DO NOT READ", runner_text)
        self.assertNotIn(".codex-acct2", runner_text)

    def test_existing_private_configuration_is_preserved(self):
        first = self.prepare()
        registry = Path(first["browser_registry"])
        registry.write_text("# owner configuration\n")
        self.assertEqual(self.prepare(), first)
        self.assertEqual(registry.read_text(), "# owner configuration\n")

    def test_generated_browser_bindings_reach_existing_idle_recycler(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "local_profile_recycler", ROOT / "skills/browser/recycle_idle_browsers.py")
        recycler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(recycler)
        profile = self.prepare()
        bindings = tomllib.loads(Path(profile["browser_registry"]).read_text())
        targets = {row["id"]: row for row in recycler.recycle_targets(bindings)}
        for identity, label in (
                ("lancers:dais", "ai.anicca.lancers-revenue-browser"),
                ("coconala:kosuke", "ai.anicca.hf-gig-browser"),
                ("mercor:dais", "ai.anicca.job-search-mercor-browser")):
            with self.subTest(identity=identity):
                self.assertIn(identity, targets)
                self.assertEqual(targets[identity]["launched_by"], label)
                self.assertTrue(Path(targets[identity]["profile"]).is_relative_to(self.home))
        self.assertNotIn("interactive:dais", targets)
        self.assertNotIn("promptbase:dais", targets)

    def test_explicit_profile_path_survives_into_child_environment(self):
        self.prepare()
        original = self.home / ".config/life-manager/host.json"
        selected = original.with_name("selected-host.json")
        original.rename(selected)
        with patch.dict(os.environ, {"LIFE_MANAGER_HOST_PROFILE": str(selected)}):
            self.assertEqual(host_environment(home=self.home)["LIFE_MANAGER_HOST_PROFILE"], str(selected))

    def test_absent_profile_does_not_mutate_legacy_host(self):
        self.assertIsNone(load_host_profile(home=self.home))
        self.assertEqual(host_environment(home=self.home), {})
        self.assertFalse((self.home / ".config").exists())

    def test_system_home_parent_alias_is_normalized(self):
        raw_home = Path(self.temp.name) / "Another Person"
        self.assertIsNone(load_host_profile(home=raw_home))
        profile = prepare_host(ROOT, home=raw_home, python=self.python, node=self.node)
        self.assertEqual(profile["owner_home"], str(raw_home.resolve()))

    def test_reprepare_preserves_explicit_profile_under_system_home_alias(self):
        profile = self.prepare()
        raw_home = Path(self.temp.name) / "Another Person"
        with patch.dict(os.environ, {"LIFE_MANAGER_HOST_PROFILE": str(raw_home / ".config/life-manager/host.json")}):
            self.assertEqual(load_host_profile(home=raw_home), profile)
            self.assertEqual(prepare_host(ROOT, home=raw_home, python=self.python, node=self.node), profile)

    def test_foreign_home_and_symlink_profile_are_rejected(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "owner_home"):
            load_host_profile(home=Path(self.temp.name), profile_path=self.home / ".config/life-manager/host.json")
        profile = self.home / ".config/life-manager/host.json"
        copy = profile.with_suffix(".copy")
        profile.rename(copy)
        profile.symlink_to(copy)
        with self.assertRaisesRegex(ValueError, "symlink"):
            load_host_profile(home=self.home)

    def test_managed_environment_binds_every_owner_to_actual_tools(self):
        profile = self.prepare()
        env = host_environment(home=self.home)
        self.assertEqual(env["LIFE_MANAGER_RUNTIME_PYTHON"], str(self.python))
        self.assertEqual(env["LIFE_MANAGER_PYTHON"], str(self.python))
        self.assertEqual(env["LIFE_MANAGER_LEASE_PYTHON"], str(self.python))
        self.assertEqual(env["LIFE_MANAGER_RUNTIME_NODE"], str(self.node))
        self.assertEqual(env["LM_SELFBUILD_SOURCE_REPO"], str(ROOT))
        self.assertEqual(env["LIFE_MANAGER_SOURCE_REPO"], str(ROOT))
        self.assertEqual(env["LIFE_MANAGER_HOME"], str(self.home / ".local/state/life-manager"))
        self.assertEqual(env["AI_BROWSER_REGISTRY"], profile["browser_registry"])
        self.assertIn(str(self.node.parent), env["PATH"].split(os.pathsep))

    def test_all_registered_plists_receive_host_binding(self):
        from runtime.loop.lm_loop_apply import _plist
        profile = self.prepare()
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        with patch.dict(os.environ, {"HOME": str(self.home)}, clear=False):
            for owner, row in registry["loops"].items():
                with self.subTest(owner=owner):
                    env = plistlib.loads(_plist(owner, row, ROOT, "a" * 40))["EnvironmentVariables"]
                    self.assertEqual(env["LIFE_MANAGER_RUNTIME_PYTHON"], str(self.python))
                    self.assertEqual(env["LIFE_MANAGER_LEASE_PYTHON"], str(self.python))
                    self.assertEqual(env["AGENT_RUNNER_CONFIG"], profile["agent_runner_config"])
                    self.assertEqual(env["AI_BROWSER_REGISTRY"], profile["browser_registry"])
                    self.assertEqual(env["LIFE_MANAGER_HOME"], str(self.home / ".local/state/life-manager"))
                    if owner in {"agent-economy-loop", "compute-proxy"}:
                        self.assertEqual(env["ANICCA_HOME"], str(self.home / ".local/state/life-manager/agent-economy/instance"))

    def test_ebook_tenant_comes_from_validated_owner_profile(self):
        from runtime.loop.lm_loop_run import _child_environment_for_owner
        profile = self.prepare()
        child = _child_environment_for_owner("ebook-ja-instagram-daily", {"LM_EBOOK_PUBLISHING_ENABLED": "false"}, home=self.home)
        self.assertEqual(child["LM_RUNTIME_TENANT_ID"], profile["tenant_id"])

    def test_release_python_identity_preserves_venv_path(self):
        source = (ROOT / "bin/cut-loop-release.sh").read_text()
        start = source.index('RUNTIME_PYTHON="$("$RUNTIME_PYTHON" -c')
        identity = source[start:source.index('\n[ -x "$RUNTIME_PYTHON" ]', start)]
        completed = subprocess.run(["bash", "-c", identity + '\nprintf "%s" "$RUNTIME_PYTHON"'],
            env={**os.environ, "RUNTIME_PYTHON": str(self.python)}, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, str(self.python))

    def test_individual_coconala_install_passes_venv_to_shell_owners(self):
        from runtime.loop.lm_loop_apply import _plist
        registry = json.loads((ROOT / "config/loop-registry.json").read_text())
        with patch.dict(os.environ, {"HOME": str(self.home)}):
            for owner in ("hf-gig-paid-direct", "hf-gig-reply-detector"):
                row = plistlib.loads(_plist(owner, registry["loops"][owner], ROOT, "a" * 40,
                                           runtime_python=self.python))
                env = row["EnvironmentVariables"]
                self.assertEqual(env["HF_GIG_PYTHON"], str(self.python))
                self.assertEqual(env["PATH"].split(os.pathsep)[0], str(self.python.parent))


if __name__ == "__main__":
    unittest.main()
