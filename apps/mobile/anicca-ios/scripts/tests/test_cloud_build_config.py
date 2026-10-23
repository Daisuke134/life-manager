"""Run the real Xcode Cloud post-clone hook against isolated build inputs."""

import base64
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "ci_scripts/ci_post_clone.sh"
VARIABLE = "ANICCA_PRODUCTION_XCCONFIG_B64"


class CloudBuildConfigTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "Xcode Cloud needs a post-clone hook")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "checkout/apps/mobile/anicca-ios"
        self.hook = self.app / "ci_scripts/ci_post_clone.sh"
        self.hook.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, self.hook)
        self.target = self.app / "Configs/Production.xcconfig"
        self.target.parent.mkdir()
        self.target.write_text("existing production config\n")

    def run_hook(self, encoded):
        env = dict(os.environ)
        env.pop(VARIABLE, None)
        if encoded is not None:
            env[VARIABLE] = encoded
        return subprocess.run(
            [str(self.hook)], cwd=self.root, env=env,
            capture_output=True, text=True, check=False,
        )

    def assert_preserved(self):
        self.assertEqual(self.target.read_text(), "existing production config\n")
        self.assertEqual(list(self.target.parent.glob(".Production.xcconfig.*")), [])

    def test_valid_config_is_exact_private_and_not_logged_from_another_cwd(self):
        config = b"REVENUECAT_API_KEY = fixture-only-key\nRESET_ON_LAUNCH = NO\n"
        result = self.run_hook(base64.b64encode(config).decode())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), config)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("fixture-only-key", result.stdout + result.stderr)
        self.assertEqual(list(self.target.parent.glob(".Production.xcconfig.*")), [])

    def test_missing_secret_fails_and_preserves_existing_config(self):
        result = self.run_hook(None)
        self.assertNotEqual(result.returncode, 0)
        self.assert_preserved()

    def test_empty_secret_fails_and_preserves_existing_config(self):
        result = self.run_hook("")
        self.assertNotEqual(result.returncode, 0)
        self.assert_preserved()

    def test_malformed_base64_cannot_replace_config_with_partial_output(self):
        result = self.run_hook(base64.b64encode(b"fixture-only-key").decode() + "!")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("fixture-only-key", result.stdout + result.stderr)
        self.assert_preserved()

    def test_empty_decoded_input_fails_and_preserves_existing_config(self):
        result = self.run_hook(" \n")
        self.assertNotEqual(result.returncode, 0)
        self.assert_preserved()


if __name__ == "__main__":
    unittest.main()
