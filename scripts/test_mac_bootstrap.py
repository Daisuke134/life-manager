"""Exercise the downloaded Mac entrypoint without network or host mutation."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MacBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.log = self.root / "commands"
        self.git = shutil.which("git")
        for args in (["init", "-b", "main"], ["config", "user.name", "Fixture"],
                     ["config", "user.email", "fixture@example.test"],
                     ["remote", "add", "origin", "https://github.com/Daisuke134/life-manager.git"]):
            self.run_git(*args)
        scripts = self.checkout / "scripts"
        scripts.mkdir()
        (scripts / "macos-runtime.sh").write_text(
            'lm_ensure_python() { LM_PYTHON="${BOOTSTRAP_SELECTED_PYTHON:-$(command -v python3)}"; }\n'
            'lm_ensure_homebrew() { echo unexpected-brew >> "$BOOTSTRAP_TEST_LOG"; return 91; }\n'
        )
        installer = self.checkout / "install.sh"
        installer.write_text('#!/bin/bash\nprintf "dispatch:%s\\n" "$@"\n')
        installer.chmod(0o755)
        self.run_git("add", ".")
        self.run_git("commit", "-m", "fixture")
        self.run_git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.env_file = self.root / "bash-env"
        self.env_file.write_text(f'''
git() {{
  case " $* " in
    " clone "*)
      "{self.git}" clone --branch main "$BOOTSTRAP_TEST_SOURCE" "${{@: -1}}" >/dev/null 2>&1
      "{self.git}" -C "${{@: -1}}" remote set-url origin https://github.com/Daisuke134/life-manager.git
      ;;
    *" fetch "*|*" merge "*) printf '%s\\n' "$*" >> "$BOOTSTRAP_TEST_LOG" ;;
    *) "{self.git}" "$@" ;;
  esac
}}
brew() {{ echo unexpected-brew >> "$BOOTSTRAP_TEST_LOG"; return 91; }}
uname() {{ echo Darwin; }}
curl() {{ cat "$BOOTSTRAP_TEST_ENTRY"; }}
''')

    def run_git(self, *args):
        return subprocess.run([self.git, "-C", str(self.checkout), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def bootstrap(self, *args, script="bootstrap.sh", extra_env=None):
        return subprocess.run(
            ["/bin/bash", str(ROOT / "scripts" / script), *args],
            env={**os.environ, "HOME": str(self.root / "home"),
                 "LIFE_MANAGER_CHECKOUT": str(self.checkout),
                 "BOOTSTRAP_TEST_SOURCE": str(self.root / "checkout"),
                 "BOOTSTRAP_TEST_ENTRY": str(ROOT / "scripts/bootstrap.sh"),
                 "BASH_ENV": str(self.env_file), "BOOTSTRAP_TEST_LOG": str(self.log),
                 **(extra_env or {})},
            capture_output=True, text=True, timeout=15,
        )

    def assert_refused_without_update(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.log.exists(), self.log.read_text() if self.log.exists() else "")

    def test_foreign_repository_is_refused_before_fetch_or_dependencies(self):
        self.run_git("remote", "set-url", "origin", "https://example.test/another.git")
        self.assert_refused_without_update(self.bootstrap("list"))

    def test_feature_branch_is_not_fast_forwarded_into_main(self):
        self.run_git("checkout", "-b", "friends-work")
        self.assert_refused_without_update(self.bootstrap("list"))
        self.assertEqual(self.run_git("branch", "--show-current"), "friends-work")

    def test_uncommitted_user_changes_are_preserved(self):
        marker = self.checkout / "private-note"
        marker.write_text("owner data")
        self.assert_refused_without_update(self.bootstrap("list"))
        self.assertEqual(marker.read_text(), "owner data")

    def test_main_with_unpublished_commits_is_not_executed(self):
        (self.checkout / "local-code").write_text("unpublished")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "local-only")
        result = self.bootstrap("list")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("fetch origin main", self.log.read_text())
        self.assertNotIn("merge", self.log.read_text())
        self.assertNotIn("dispatch", result.stdout)

    def test_git_worktree_file_is_accepted_and_arguments_reach_installer(self):
        linked = self.root / "linked"
        self.run_git("branch", "-m", "source")
        self.run_git("worktree", "add", "-b", "linked", str(linked))
        subprocess.run([self.git, "-C", str(linked), "branch", "-m", "main"], check=True,
                       capture_output=True)
        self.checkout = linked
        result = self.bootstrap("coconala", "preflight")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dispatch:coconala\ndispatch:preflight", result.stdout)
        self.assertIn("fetch origin main", self.log.read_text())
        self.assertNotIn("unexpected-brew", self.log.read_text())

    def test_new_mac_checkout_reaches_selected_installer(self):
        self.checkout = self.root / "fresh"
        result = self.bootstrap("coconala", "preflight")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dispatch:coconala\ndispatch:preflight", result.stdout)
        self.assertTrue((self.checkout / ".git").is_dir())
        self.assertFalse((self.root / "home/Library/LaunchAgents").exists())

    def test_crowdworks_bootstrap_reaches_real_dispatch_with_profile_arguments(self):
        shutil.copyfile(ROOT / "install.sh", self.checkout / "install.sh")
        wrapper = self.checkout / "skills/earn/crowdworks/install.sh"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('#!/bin/bash\nprintf "crowdworks:%s\\n" "$@"\n')
        self.run_git("add", ".")
        self.run_git("commit", "-m", "CrowdWorks dispatch fixture")
        self.run_git("update-ref", "refs/remotes/origin/main", "HEAD")
        profile = self.root / "own profile.json"

        result = self.bootstrap("crowdworks", "plan", "--provider-profile", str(profile))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"crowdworks:plan\ncrowdworks:--provider-profile\ncrowdworks:{profile}",
                      result.stdout)
        self.assertNotIn("unexpected-brew", self.log.read_text())
        self.assertFalse((self.root / "home/Library/LaunchAgents").exists())

    def test_published_product_wrappers_preserve_command_arguments(self):
        for product in ("coconala", "job-hunter"):
            with self.subTest(product=product):
                result = self.bootstrap("preflight", script=f"bootstrap-{product}.sh")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"dispatch:{product}\ndispatch:preflight", result.stdout)

    @unittest.skipUnless(shutil.which("zsh"), "Job Hunter uses zsh")
    def test_job_hunter_runtime_receives_selected_python_and_preserves_override(self):
        runtime = self.checkout / "apps/job-search-loop/scripts/runtime-paths.sh"
        runtime.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / "apps/job-search-loop/scripts/runtime-paths.sh", runtime)
        (self.checkout / "install.sh").write_text(
            '#!/bin/bash\nexec ' + shutil.which("zsh") + ' -c \'source "$LIFE_MANAGER_CHECKOUT/apps/job-search-loop/scripts/runtime-paths.sh"; printf "%s" "$JOB_SEARCH_PYTHON"\'\n'
        )
        self.run_git("add", ".")
        self.run_git("commit", "-m", "job-hunter runtime fixture")
        self.run_git("update-ref", "refs/remotes/origin/main", "HEAD")
        for override in ("", "/owner/chosen-python"):
            with self.subTest(override=override):
                result = self.bootstrap("job-hunter", "preflight", extra_env={
                    "BOOTSTRAP_SELECTED_PYTHON": sys.executable, "JOB_SEARCH_PYTHON": override,
                })
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, override or sys.executable)

    def test_default_setup_replaces_an_incompatible_existing_venv(self):
        (self.checkout / "requirements-runtime.txt").write_text("")
        (self.checkout / "scripts/life-manager-onboarding-server.py").write_text(
            'print("onboarding-ready")\n'
        )
        self.run_git("add", ".")
        self.run_git("commit", "-m", "setup screen fixture")
        self.run_git("update-ref", "refs/remotes/origin/main", "HEAD")
        venv_python = self.root / "home/.local/share/life-manager/venv/bin/python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text('#!/bin/bash\nexit 95\n')
        venv_python.chmod(0o755)
        result = self.bootstrap(extra_env={"BOOTSTRAP_SELECTED_PYTHON": sys.executable})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "onboarding-ready\n")

    def test_repeated_job_hunter_setup_keeps_its_installed_dependencies(self):
        helper = self.checkout / "scripts/macos-runtime.sh"
        with helper.open("a") as handle:
            handle.write('_lm_select_python() { [ -x "$1" ] || return 1; LM_PYTHON="$1"; }\n')
        (self.checkout / "install.sh").write_text('#!/bin/bash\nprintf "%s" "$JOB_SEARCH_PYTHON"\n')
        self.run_git("add", ".")
        self.run_git("commit", "-m", "resume fixture")
        self.run_git("update-ref", "refs/remotes/origin/main", "HEAD")
        venv = self.root / "home/.local/share/anicca/job-search/venv/bin/python"
        venv.parent.mkdir(parents=True)
        venv.write_text('#!/bin/sh\nexit 0\n')
        venv.chmod(0o755)
        result = self.bootstrap("job-hunter", "finished", extra_env={"JOB_SEARCH_PYTHON": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(venv))


if __name__ == "__main__":
    unittest.main()
