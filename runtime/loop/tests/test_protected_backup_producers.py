import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(shutil.which("rsync"), "rsync is required by existing backup scripts")
class ProtectedBackupProducerTest(unittest.TestCase):
    def test_generations_are_preserved_and_diagnostics_use_inherited_stderr(self):
        for name in ("browser-state-backup", "claude-projects-backup"):
            with self.subTest(producer=name), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                source = home / ".claude/projects/example/memory/sentinel.md"
                source.parent.mkdir(parents=True)
                source.write_text("original memory")
                old = home / ".cloak/state-backups/2001-01-01/claude-projects/example/memory/sentinel.md"
                old.parent.mkdir(parents=True)
                old.write_text("historical memory")
                for day in range(2, 17):
                    (home / f".cloak/state-backups/2001-01-{day:02}/claude-projects").mkdir(parents=True)
                (home / ".cloak/profiles").mkdir(parents=True)
                env = {**os.environ, "HOME": str(home)}
                script = ROOT / f"skills/_shared/{name}.sh"
                result = subprocess.run(["bash", str(script)], env=env,
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(json.loads(result.stdout)["ok"])
                self.assertTrue(old.is_file(), "protected historical generation was deleted")
                self.assertEqual(old.read_text(), "historical memory")
                self.assertIn(name, result.stderr)
                self.assertFalse((home / f".local/state/life-manager/logs/{name}.log").exists())
                if name == "claude-projects-backup":
                    backup = Path(json.loads(result.stdout)["dest"]) / "example/memory/sentinel.md"
                    self.assertEqual(backup.read_text(), "original memory")
                    self.assertNotEqual(backup.stat().st_ino, source.stat().st_ino)
                    source.write_text("updated memory")
                    # --update must see a later source mtime even on coarse filesystems.
                    os.utime(source, (source.stat().st_atime, backup.stat().st_mtime + 2))
                    again = subprocess.run(["bash", str(script)], env=env,
                                           capture_output=True, text=True, timeout=15)
                    self.assertEqual(again.returncode, 0, again.stderr)
                    self.assertEqual(backup.read_text(), "updated memory")
                    self.assertEqual(old.read_text(), "historical memory")


if __name__ == "__main__":
    unittest.main()
