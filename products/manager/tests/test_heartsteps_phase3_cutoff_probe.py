import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import heartsteps_phase3_cutoff_probe as probe


class CutoffProbeTests(unittest.TestCase):
    def row(self, index, available="True", send="False"):
        return {
            "user.index": "u",
            "decision.index.nogap": str(index),
            "avail": available,
            "send": send,
            "send.active": "False",
            "send.sedentary": "False",
            "jbsteps30": "0",
            "jbsteps30.zero": "0",
            "jbsteps30pre.zero": "0",
        }

    def test_scan_is_aggregate_and_cutoff_is_exclusive(self):
        report = probe.scan([self.row(204), self.row(205)], cutoffs=[205, 206])
        self.assertEqual(report["scan"]["205"]["included"], 1)
        self.assertEqual(report["scan"]["206"]["included"], 2)
        self.assertNotIn("user.index", str(report))


if __name__ == "__main__":
    unittest.main()
