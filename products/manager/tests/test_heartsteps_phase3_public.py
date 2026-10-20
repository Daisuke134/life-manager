import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import heartsteps_phase3_public as public


class PublicSelectionTests(unittest.TestCase):
    def row(self, **updates):
        row = {
            "user.index": "u1",
            "decision.index.nogap": "10",
            "avail": "True",
            "send": "False",
            "send.active": "False",
            "send.sedentary": "False",
            "jbsteps30": "0",
            "jbsteps30.zero": "0",
            "jbsteps30pre.zero": "0",
        }
        row.update(updates)
        return row

    def test_missing_send_is_excluded_not_imputed_to_no_action(self):
        selected, available, audit = public.select_public_analysis_rows([
            self.row(send=""), self.row(**{"decision.index.nogap": "11"})
        ])
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(available), 1)
        self.assertEqual(audit["missing_send"], 1)
        self.assertEqual(selected[0]["send"], False)

    def test_filter_order_preserves_distinct_reasons(self):
        _, _, audit = public.select_public_analysis_rows([
            self.row(**{"decision.index.nogap": "", "send": ""}),
            self.row(**{"decision.index.nogap": "211", "send": ""}),
            self.row(send=""),
        ])
        self.assertEqual(audit["missing_nogap_index"], 1)
        self.assertEqual(audit["beyond_day_41"], 1)
        self.assertEqual(audit["missing_send"], 1)


if __name__ == "__main__":
    unittest.main()
