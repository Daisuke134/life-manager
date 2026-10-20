"""MGR-001 objective acceptance tests for standalone scaffold."""
from pathlib import Path
import subprocess
import sys
import unittest
from manager_core.config import DEFAULTS, RuntimeDefaults

ROOT = Path(__file__).resolve().parents[1]


class RepoIsolationTests(unittest.TestCase):
    def test_product_exists_as_package(self):
        self.assertTrue((ROOT / "manager_core/__init__.py").is_file())
        self.assertTrue((ROOT / "pyproject.toml").is_file())

    def test_doc_and_ci_exist(self):
        self.assertTrue((ROOT / ".github/workflows/ci.yml").is_file())
        self.assertTrue((ROOT / "docs/architecture/ARCHITECTURE.md").is_file())

    def test_live_external_effects_disabled_by_default(self):
        self.assertFalse(any(vars(DEFAULTS).values()))

    def test_scaffold_cannot_enable_external_effects(self):
        with self.assertRaises(ValueError):
            RuntimeDefaults(money_transfer=True)

    def test_scaffold_cannot_enable_private_person_data(self):
        with self.assertRaises(ValueError):
            RuntimeDefaults(private_person_data=True)

    def test_isolation_imports(self):
        result = subprocess.run([sys.executable, "scripts/check_boundaries.py"],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertIn("PASS", result.stdout)

    def test_doctor_reports_zero_real_impact(self):
        result = subprocess.run([sys.executable, "-m", "manager_core"],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertIn('"real_world_interventions": 0', result.stdout)
        self.assertIn('"human_impact_claims": 0', result.stdout)

    def test_no_life_manager_submodule(self):
        self.assertFalse((ROOT / "apps/life-manager").exists())

    def test_ignore_secrets(self):
        txt = (ROOT / ".gitignore").read_text()
        self.assertIn(".env", txt)
        self.assertIn("*.key", txt)
