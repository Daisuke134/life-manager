"""R008: a vendor description or simulation must not be rendered as a human RCT."""
import copy
import importlib.util
import unittest
from test_evidence_registry import sample_record


class EvidenceTypeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('manager_core.evidence_types'),
                             'R008 is not implemented: evidence type module absent')
        from manager_core import evidence_types
        self.api=evidence_types
        self.record=sample_record()

    def test_primary_human_trial_is_tagged_rct_not_manager_impact(self):
        self.assertEqual(self.api.evidence_type(self.record),'rct')
        self.assertIn('not Manager',self.api.label(self.record))

    def test_vendor_cannot_be_promoted_to_rct_even_if_it_mentions_randomization(self):
        self.record['source']['kind']='company_page'
        self.assertEqual(self.api.evidence_type(self.record),'company_claim')
        with self.assertRaises(ValueError): self.api.require_type(self.record,'rct')

    def test_simulation_does_not_become_rct(self):
        self.record['study']['design']='simulation'
        self.assertEqual(self.api.evidence_type(self.record),'simulation')
        with self.assertRaises(ValueError): self.api.require_type(self.record,'rct')

    def test_survey_is_not_an_experiment(self):
        self.record['study']['design']='observational_survey'
        self.assertEqual(self.api.evidence_type(self.record),'survey')
        with self.assertRaises(ValueError): self.api.require_type(self.record,'rct')

    def test_review_not_counted_as_extra_trial(self):
        self.record['source']['kind']='review_paper'; self.record['study']['design']='review'
        self.assertEqual(self.api.evidence_type(self.record),'review')

    def test_official_tool_docs_are_not_effect_estimates(self):
        self.record['source']['kind']='official_docs'; self.record['study']['design']='software_documentation'
        self.assertEqual(self.api.evidence_type(self.record),'tool_documentation')

    def test_benchmark_on_human_trial_data_is_not_new_human_trial(self):
        self.record['study']['design']='benchmark'
        self.assertEqual(self.api.evidence_type(self.record),'benchmark')

    def test_invalid_cross_field_types_rejected(self):
        self.record['source']['kind']='review_paper'
        with self.assertRaises(ValueError):self.api.evidence_type(self.record)

    def test_unknown_requested_label_rejected(self):
        with self.assertRaises(ValueError):self.api.require_type(self.record,'proven_blessing')

    def test_labels_preserve_limited_reading_status(self):
        self.record['review']['status']='abstract_only'
        self.assertIn('abstract_only',self.api.label(self.record))

    def test_structural_validation_is_not_scientific_independence(self):
        label=self.api.label(self.record)
        self.assertNotIn('independently verified',label.lower())
        self.assertNotIn('proven benefit',label.lower())

    def test_all_stored_records_classify_and_do_not_grant_execution(self):
        from pathlib import Path
        from manager_core.evidence import load_registry
        r=load_registry(Path(__file__).resolve().parents[1]/'evidence')
        counts=self.api.count_by_type(r)
        self.assertEqual(sum(counts.values()),len(r))
        self.assertGreaterEqual(counts.get('rct',0),1)
        self.assertGreaterEqual(counts.get('company_claim',0),1)
        self.assertNotIn('blessings',counts)

if __name__=='__main__': unittest.main()
