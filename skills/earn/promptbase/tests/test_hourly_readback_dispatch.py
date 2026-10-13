import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "skills" / "earn" / "promptbase" / "hourly_readback.sh"
ENDPOINT = "http://127.0.0.1:51416"


class HourlyReadbackDispatchTest(unittest.TestCase):
    def test_registry_has_one_borrowed_hourly_promptbase_readback(self):
        registry = json.loads((REPO_ROOT / "config" / "loop-registry.json").read_text())
        loops = registry["loops"]
        hourly = [key for key in loops if key.startswith("promptbase-") and "hourly" in key]
        self.assertEqual(hourly, ["promptbase-sales-readback-hourly"])
        row = loops[hourly[0]]
        self.assertEqual(row["cadence"], {"calendar_interval": {"Minute": 37}})
        self.assertEqual(row["effect_class"], "none")
        self.assertEqual(row["resource_class"], "browser")
        self.assertEqual(row["admission_class"], "borrow")
        self.assertEqual(row["browser_identity"], "promptbase:dais")
        self.assertEqual(row["browser_target_owner"], "promptbase-loop-daily")
        self.assertEqual(row["entrypoint"], "skills/earn/promptbase/hourly_readback.sh")
        product_catalog = json.loads(
            (REPO_ROOT / "apps" / "life-manager" / "config" / "product-loop-catalog.json").read_text()
        )
        promptbase = next(x for x in product_catalog["loops"] if x["id"] == "promptbase")
        self.assertIn("promptbase-sales-readback-hourly", promptbase["job_ids"])
        self.assertIn("browser", promptbase["recovery_classes"])

    def _run(self, tmp_path: Path, *, acquire_rc: int = 0, readback_rc: int = 0):
        guard = tmp_path / "browser-guard.sh"
        guard.write_text(
            "#!/usr/bin/env bash\n"
            "set -u\n"
            "printf '%s %s\\n' \"$1\" \"$2\" >> \"$GUARD_LOG\"\n"
            "if [ \"$1\" = acquire ]; then\n"
            "  [ \"$FAKE_ACQUIRE_RC\" -eq 0 ] || exit \"$FAKE_ACQUIRE_RC\"\n"
            "  printf '%s\\n' \"$FAKE_ENDPOINT\"\n"
            "  exit 0\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        guard.chmod(0o755)
        python = tmp_path / "python"
        python.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$PY_LOG\"\n"
            "exit \"$FAKE_READBACK_RC\"\n",
            encoding="utf-8",
        )
        python.chmod(0o755)
        guard_log = tmp_path / "guard.log"
        python_log = tmp_path / "python.log"
        env = {
            **os.environ,
            "AI_BROWSER_GUARD": str(guard),
            "PY": str(python),
            "GUARD_LOG": str(guard_log),
            "PY_LOG": str(python_log),
            "FAKE_ACQUIRE_RC": str(acquire_rc),
            "FAKE_READBACK_RC": str(readback_rc),
            "FAKE_ENDPOINT": ENDPOINT,
        }
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=tmp_path, env=env,
            capture_output=True, text=True, timeout=10,
        )
        return result, guard_log, python_log

    def test_busy_browser_lease_skips_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, guard_log, python_log = self._run(Path(tmp), acquire_rc=9)
            self.assertEqual(result.returncode, 75)
            self.assertEqual(guard_log.read_text().splitlines(), ["acquire promptbase:dais"])
            self.assertFalse(python_log.exists())

    def test_readback_runs_once_and_lease_releases_even_on_failure(self):
        for readback_rc in (0, 17):
            with self.subTest(readback_rc=readback_rc), tempfile.TemporaryDirectory() as tmp:
                result, guard_log, python_log = self._run(Path(tmp), readback_rc=readback_rc)
                self.assertEqual(result.returncode, readback_rc)
                self.assertEqual(
                    guard_log.read_text().splitlines(),
                    ["acquire promptbase:dais", "release promptbase:dais"],
                )
                calls = python_log.read_text().splitlines()
                self.assertEqual(len(calls), 1)
                self.assertIn("readback.py", calls[0])
                self.assertTrue(calls[0].endswith(f"--endpoint {ENDPOINT} --sales-only"))
                self.assertNotIn("publish.py", calls[0])


if __name__ == "__main__":
    unittest.main()
