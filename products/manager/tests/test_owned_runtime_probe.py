"""The offline comparison CLI runs real isolated processes without DBOS required."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/compare_owned_runtime.py'


class RuntimeProbeCLITests(unittest.TestCase):
    def test_current_checkpoint_crash_restarts_without_optional_dbos(self):
        with TemporaryDirectory() as tmp:
            state = Path(tmp) / 'private-probe'
            result = subprocess.run([sys.executable, str(SCRIPT), '--backend', 'current',
                '--case', 'checkpoint_loss', '--state-dir', str(state)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((state / 'results.json').read_text())
            self.assertEqual(report['failure_count'], 0)
            receipt = report['receipts'][0]
            self.assertEqual(receipt['dispatch_count'], 1)
            self.assertEqual(receipt['target_advance_count'], 1)
            self.assertEqual(receipt['after_restart']['journal']['status'], 'PRESENT')
            self.assertFalse(report['production_evidence'])

    def test_source_tree_cannot_be_used_as_probe_state(self):
        state = ROOT / ('probe-must-not-create-' + uuid4().hex)
        result = subprocess.run([sys.executable, str(SCRIPT), '--backend', 'current',
            '--case', 'checkpoint_loss', '--state-dir', str(state)],
            capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('outside source', result.stderr)
        self.assertFalse(state.exists())
