"""Tests for aggregate-only, privacy-preserving mapping diagnostics."""
import csv
import importlib.util
import sys
import unittest
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

class JoinProbeTests(unittest.TestCase):
    def get_module(self):
        spec = importlib.util.find_spec('heartsteps_phase3_day_join_probe')
        self.assertIsNotNone(spec, 'H005 day-join probe is not implemented')
        return __import__('heartsteps_phase3_day_join_probe')

    def read(self, data):
        return csv.DictReader(StringIO(data))

    def test_step_lookup_preserves_unique_day_and_marks_ambiguous(self):
        m = self.get_module()
        steps=self.read('user.index,decision.index,study.day.nogap,steps\na,1,5,10\na,1,5,20\na,2,8,10\na,2,9,40\na,3,,8\n')
        lookup, counts = m.build_day_lookup(steps)
        self.assertEqual(lookup[('a','1')],5)
        self.assertIsNone(lookup[('a','2')])
        self.assertNotIn(('a','3'),lookup)
        self.assertEqual(counts['ambiguous_keys'],1)
        self.assertEqual(counts['unique_day_keys'],1)

    def test_summary_emits_only_aggregate_counts(self):
        m=self.get_module()
        suggestions=self.read('user.index,decision.index,avail,send,send.active\na,1,TRUE,TRUE,TRUE\na,2,TRUE,FALSE,FALSE\nb,1,FALSE,,FALSE\n')
        lookup={('a','1'):5,('a','2'):None}
        counts=m.aggregate_coverage(suggestions,lookup)
        self.assertEqual(counts['source_rows'],3)
        self.assertEqual(counts['join_unique'],1)
        self.assertEqual(counts['join_ambiguous'],1)
        self.assertEqual(counts['join_absent'],1)
        self.assertEqual(counts['unique_available'],1)
        self.assertNotIn("'a'",str(counts))
        self.assertNotIn("'b'",str(counts))

    def test_out_of_study_window_counted_without_data_rows(self):
        m=self.get_module()
        s=self.read('user.index,decision.index,avail,send\na,1,TRUE,TRUE\na,2,FALSE,FALSE\n')
        c=m.aggregate_coverage(s,{('a','1'):42,('a','2'):41})
        self.assertEqual(c['join_unique'],2)
        self.assertEqual(c['day_gt_41'],1)
        self.assertEqual(c['join_unique_in_study_window'],1)

    def test_bad_or_missing_required_columns_rejected(self):
        m=self.get_module()
        with self.assertRaises(ValueError):
            m.build_day_lookup(self.read('user.index,decision.index,steps\na,1,10\n'))
        with self.assertRaises(ValueError):
            m.aggregate_coverage(self.read('decision.index,avail\n1,TRUE\n'),{})

    def test_numeric_identifier_representation_does_not_destroy_public_join(self):
        m=self.get_module()
        step=self.read('user.index,decision.index,study.day.nogap\n1.0,10.0,5\n')
        lookup,counts=m.build_day_lookup(step)
        self.assertEqual(lookup[('1','10')],5)
        sugg=self.read('user.index,decision.index,avail\n1,10,TRUE\n')
        self.assertEqual(m.aggregate_coverage(sugg,lookup)['join_unique'],1)

    def test_key_alignment_reports_counts_only(self):
        m=self.get_module()
        sugg=self.read('user.index,decision.index,avail\n1,10,TRUE\n2,11,FALSE\n')
        lookup={('1','10'):5,('3','12'):8}
        report=m.summarize_key_alignment(sugg,lookup)
        self.assertEqual(report['user_overlap'],1)
        self.assertEqual(report['decision_overlap'],1)
        self.assertEqual(report['pair_overlap'],1)
        self.assertNotIn("'1'",str(report))

    def test_combine_past_and_following_decision_day_evidence_without_guessing(self):
        m=self.get_module()
        result, audit=m.merge_day_lookups(
            {('a','1'):4,('a','2'):5,('a','3'):None},
            {('a','1'):4,('a','2'):7,('b','1'):5}
        )
        self.assertEqual(result[('a','1')],4)
        self.assertIsNone(result[('a','2')])
        self.assertIsNone(result[('a','3')])
        self.assertEqual(result[('b','1')],5)
        self.assertEqual(audit['conflicting_keys'],1)
        self.assertEqual(audit['new_nonconflicting_keys'],1)

    def test_known_day_against_proxy_is_descriptive_not_a_causal_effect(self):
        m=self.get_module()
        rows=self.read('user.index,decision.index,decision.index.nogap,avail\na,1,10,TRUE\na,2,19,TRUE\n')
        audit=m.compare_proxy_days(rows,{('a','1'):2,('a','2'):8})
        self.assertEqual(audit['matched'],2)
        self.assertEqual(audit['agree'],1)
        self.assertEqual(audit['disagree'],1)
        self.assertEqual(audit['missing_proxy'],0)

    def test_following_decision_day_can_fill_missing_previous_day(self):
        m=self.get_module()
        steps=self.read('user.index,decision.index.following.dec,study.day.nogap.following.dec\na,7,3\na,8,4\n')
        lookup, report=m.build_following_day_lookup(steps)
        self.assertEqual(lookup[('a','7')],3)
        self.assertEqual(lookup[('a','8')],4)
        self.assertEqual(report['unique_day_keys'],2)

if __name__=='__main__':unittest.main()

class CrossDeviceJoinTests(unittest.TestCase):
    def test_four_independent_mappings_can_add_coverage_without_subject_outputs(self):
        import heartsteps_phase3_day_join_probe as p
        mappings=[
          {('a','1'):3,('a','2'):4},
          {('a','2'):4,('a','3'):5},
          {('a','4'):6},
          {('a','5'):7},
        ]
        combined,audit=p.merge_device_evidence(mappings)
        self.assertEqual(len(combined),5)
        self.assertEqual(audit['merged_unique_keys'],5)
        self.assertEqual(audit['conflicting_keys'],0)
        self.assertNotIn("('a',", str(audit))

    def test_cross_device_conflict_never_silently_selects_first(self):
        import heartsteps_phase3_day_join_probe as p
        combined,audit=p.merge_device_evidence([
          {('a','1'):3}, {('a','1'):4}
        ])
        self.assertIsNone(combined[('a','1')])
        self.assertEqual(audit['conflicting_keys'],1)