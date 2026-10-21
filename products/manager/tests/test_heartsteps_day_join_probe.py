"""Aggregate-only HeartSteps pinned step-data join: fixture tests."""
import csv
import importlib.util
import sys
import unittest
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

class JoinProbeTests(unittest.TestCase):
    def get_module(self):
        spec = importlib.util.find_spec("heartsteps_phase3_day_join_probe")
        self.assertIsNotNone(spec, "H005 day join probe is not implemented")
        return __import__("heartsteps_phase3_day_join_probe")

    def read(self, data):
        return csv.DictReader(StringIO(data))

    def test_step_lookup_preserves_unique_day_and_marks_ambiguous(self):
        m = self.get_module()
        steps = self.read(
            "user.index,decision.index,study.day.nogap,steps\n"
            "a,1,5,10\na,1,5,20\na,2,8,10\na,2,9,40\na,3,,8\n"
        )
        lookup, counts = m.build_day_lookup(steps)
        self.assertEqual(lookup[("a", "1")], 5)
        self.assertIsNone(lookup[("a", "2")])
        self.assertNotIn(("a", "3"), lookup)
        self.assertEqual(counts["ambiguous_keys"], 1)
        self.assertEqual(counts["unique_day_keys"], 1)

    def test_summary_emits_only_aggregate_counts(self):
        m = self.get_module()
        suggestions = self.read(
            "user.index,decision.index,avail,send,send.active\n"
            "a,1,TRUE,TRUE,TRUE\na,2,TRUE,FALSE,FALSE\nb,1,FALSE,,FALSE\n"
        )
        counts = m.aggregate_coverage(suggestions, {("a","1"):5, ("a","2"):None})
        self.assertEqual(counts["source_rows"], 3)
        self.assertEqual(counts["join_unique"], 1)
        self.assertEqual(counts["join_ambiguous"], 1)
        self.assertEqual(counts["join_absent"], 1)
        self.assertEqual(counts["unique_available"], 1)
        self.assertNotIn("'a'", str(counts))
        self.assertNotIn("'b'", str(counts))

    def test_out_of_study_window_counted_without_data_rows(self):
        m = self.get_module()
        suggestions = self.read(
            "user.index,decision.index,avail,send\n"
            "a,1,TRUE,TRUE\na,2,FALSE,FALSE\n"
        )
        counts = m.aggregate_coverage(suggestions, {("a","1"):42, ("a","2"):41})
        self.assertEqual(counts["join_unique"], 2)
        self.assertEqual(counts["day_gt_41"], 1)
        self.assertEqual(counts["join_unique_in_study_window"], 1)

    def test_bad_or_missing_required_columns_rejected(self):
        m = self.get_module()
        with self.assertRaises(ValueError):
            m.build_day_lookup(self.read("user.index,decision.index,steps\na,1,10\n"))
        with self.assertRaises(ValueError):
            m.aggregate_coverage(self.read("decision.index,avail\n1,TRUE\n"), {})


    def test_numeric_identifier_representation_does_not_destroy_join(self):
        m = self.get_module()
        steps = self.read(
            "user.index,decision.index,study.day.nogap\n1.0,10.0,5\n"
        )
        lookup, _ = m.build_day_lookup(steps)
        self.assertEqual(lookup[("1", "10")], 5)
        suggestions = self.read("user.index,decision.index,avail\n1,10,TRUE\n")
        self.assertEqual(m.aggregate_coverage(suggestions, lookup)["join_unique"], 1)

    def test_key_alignment_reports_counts_without_identifiers(self):
        m = self.get_module()
        suggestions = self.read(
            "user.index,decision.index,avail\n1,10,TRUE\n2,11,FALSE\n"
        )
        report = m.summarize_key_alignment(suggestions, {("1", "10"): 5, ("3", "12"): 8})
        self.assertEqual(report["user_overlap"], 1)
        self.assertEqual(report["decision_overlap"], 1)
        self.assertEqual(report["pair_overlap"], 1)
        self.assertNotIn("'1'", str(report))


    def test_combine_past_and_following_decision_day_evidence_without_guessing(self):
        m = self.get_module()
        merged, audit = m.merge_day_lookups(
            {("a", "1"): 4, ("a", "2"): 5, ("a", "3"): None},
            {("a", "1"): 4, ("a", "2"): 7, ("b", "1"): 5},
        )
        self.assertEqual(merged[("a", "1")], 4)
        self.assertIsNone(merged[("a", "2")])
        self.assertIsNone(merged[("a", "3")])
        self.assertEqual(merged[("b", "1")], 5)
        self.assertEqual(audit["conflicting_keys"], 1)
        self.assertEqual(audit["new_nonconflicting_keys"], 1)

    def test_following_decision_day_can_fill_missing_previous_day(self):
        m = self.get_module()
        steps = self.read(
            "user.index,decision.index.following.dec,study.day.nogap.following.dec\n"
            "a,7,3\na,8,4\n"
        )
        lookup, report = m.build_following_day_lookup(steps)
        self.assertEqual(lookup[("a", "7")], 3)
        self.assertEqual(lookup[("a", "8")], 4)
        self.assertEqual(report["unique_day_keys"], 2)

    def test_observed_study_days_reject_unverified_index_division(self):
        m = self.get_module()
        rows = self.read(
            "user.index,decision.index,decision.index.nogap,avail\n"
            "a,1,10,TRUE\na,2,19,TRUE\n"
        )
        audit = m.compare_proxy_days(rows, {("a", "1"): 2, ("a", "2"): 8})
        self.assertEqual(audit["matched"], 2)
        self.assertEqual(audit["agree"], 1)
        self.assertEqual(audit["disagree"], 1)
        self.assertEqual(audit["missing_proxy"], 0)

if __name__ == "__main__":
    unittest.main()
