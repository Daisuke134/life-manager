import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import heartsteps_phase3_probe as probe


class ProbeTests(unittest.TestCase):
    def row(self, index="0", available="True", send="False", active="False", sedentary="False"):
        return {
            "user.index": "u",
            "decision.index.nogap": index,
            "avail": available,
            "send": send,
            "send.active": active,
            "send.sedentary": sedentary,
            "jbsteps30": "0",
            "jbsteps30.zero": "0",
            "jbsteps30pre.zero": "0",
        }

    def test_reports_missing_send_without_rows(self):
        report = probe.aggregate([
            self.row(send=""),
            self.row(index="", send=""),
            self.row(index="211", send=""),
        ])
        self.assertEqual(report["missing_send"]["total"], 3)
        self.assertEqual(report["missing_send"]["by_nogap_missing"], 1)
        self.assertIn("offset0_keep_missing_send_true", report["selection_variants"])
        self.assertNotIn("user.index", str(report))

    def test_offsets_change_only_boundary_assignment(self):
        report = probe.aggregate([self.row(index="209"), self.row(index="210")])
        self.assertEqual(
            report["selection_variants"]["offset0_keep_missing_send_true"]["included"], 1
        )
        self.assertEqual(
            report["selection_variants"]["offset1_keep_missing_send_true"]["included"], 2
        )


if __name__ == "__main__":
    unittest.main()
