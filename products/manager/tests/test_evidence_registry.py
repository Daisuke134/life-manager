"""R007 contract tests. Fixtures are artificial; they are not research findings."""
import copy
import importlib
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]


def sample_record():
    return {
        'schema_version': 1, 'id': 'fixture-only',
        'source': {'kind': 'primary_paper', 'title': 'Synthetic test paper',
                   'authors': ['Test author'], 'url': 'https://example.org/paper',
                   'version': 'test-fixture', 'accessed': '2026-10-20'},
        'study': {'design': 'randomized_trial', 'population': 'Synthetic fixture',
                  'sample_size': 20, 'sample_unit': 'synthetic participants',
                  'locator': 'Methods'},
        'claim': 'A test fixture, not a real result.',
        'outcome': {'name': 'synthetic outcome', 'window': '1 day'},
        'findings': [{'name': 'test effect', 'value': 1.2, 'unit': 'ratio',
                      'source_url': 'https://example.org/paper', 'locator': 'Results',
                      'analysis': 'secondary',
                      'uncertainty': {'status': 'reported', 'kind': 'confidence_interval',
                                      'level': 0.95, 'lower': 1.0, 'upper': 1.4}}],
        'limitations': ['Synthetic data cannot show benefit.'],
        'rights': {'use': 'metadata_and_original_summary_only',
                   'raw_data_use': 'hold', 'basis_url': 'https://example.org/terms'},
        'review': {'status': 'source_read', 'locator': 'Methods; Results',
                   'reproduced_by_manager': False},
    }


class EvidenceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('manager_core.evidence'),
                             'R007 is not implemented: evidence module is absent')
        self.api = importlib.import_module('manager_core.evidence')
        self.r = sample_record()

    def test_accepts_valid_record_without_network(self):
        self.assertEqual(self.api.validate_record(self.r), self.r)

    def test_validation_does_not_mutate_input(self):
        before = copy.deepcopy(self.r)
        self.api.validate_record(self.r)
        self.assertEqual(self.r, before)

    def test_rejects_unsourced_number(self):
        del self.r['findings'][0]['locator']
        with self.assertRaises(ValueError): self.api.validate_record(self.r)

    def test_rejects_nonfinite_and_boolean_numbers(self):
        for value in [float('nan'), float('inf'), True, '24%']:
            with self.subTest(value=value):
                r = copy.deepcopy(self.r); r['findings'][0]['value'] = value
                with self.assertRaises(ValueError): self.api.validate_record(r)

    def test_rejects_missing_uncertainty_not_silent_zero(self):
        del self.r['findings'][0]['uncertainty']
        with self.assertRaises(ValueError): self.api.validate_record(self.r)

    def test_allows_explicit_unreported_uncertainty(self):
        self.r['findings'][0]['uncertainty'] = {'status':'not_reported'}
        self.api.validate_record(self.r)

    def test_rejects_invalid_intervals(self):
        for lo, hi, level in [(2, 1, .95), (1, 2, 1.5), (float('nan'),2,.95)]:
            r = copy.deepcopy(self.r)
            r['findings'][0]['uncertainty'].update(lower=lo,upper=hi,level=level)
            with self.assertRaises(ValueError): self.api.validate_record(r)

    def test_requires_outcome_window_and_limitations(self):
        for path in ['window','limitations']:
            r = copy.deepcopy(self.r)
            if path=='window': r['outcome'][path]=''
            else: r[path]=[]
            with self.assertRaises(ValueError): self.api.validate_record(r)

    def test_public_url_does_not_grant_raw_data_rights(self):
        self.r['rights']['raw_data_use'] = 'hold'
        self.api.validate_record(self.r)
        self.assertEqual(self.r['rights']['raw_data_use'],'hold')
        self.r['rights']['raw_data_use'] = 'public_so_allowed'
        with self.assertRaises(ValueError): self.api.validate_record(self.r)

    def test_rejects_credentialed_or_local_source_urls(self):
        for url in ['file:///tmp/a','https://u:pw@example.org/a','https://localhost/a',
                    'https://127.0.0.1/a','javascript:alert(1)','https:///paper']:
            r=copy.deepcopy(self.r); r['source']['url']=url
            with self.assertRaises(ValueError): self.api.validate_record(r)

    def test_rejects_unknown_fields_and_versions(self):
        for change in [{'schema_version':2},{'success':True}]:
            r=copy.deepcopy(self.r);r.update(change)
            with self.assertRaises(ValueError): self.api.validate_record(r)

    def test_qualitative_result_is_not_zero_effect(self):
        self.r['findings']=[]
        self.api.validate_record(self.r)
        self.assertEqual(self.r['findings'],[])

    def test_rejects_duplicate_ids(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)
            for name in ['a','b']: (p/f'{name}.json').write_text(json.dumps(self.r))
            with self.assertRaises(ValueError): self.api.load_registry(p)

    def test_rejects_duplicate_json_keys(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'a.json').write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaises(ValueError): self.api.load_registry(p)

    def test_at_least_five_distinct_primary_papers(self):
        records=self.api.load_registry(ROOT/'evidence')
        primary={r['source']['url'] for r in records if r['source']['kind']=='primary_paper'}
        self.assertGreaterEqual(len(primary),5)
        self.assertTrue(all(not r['review']['reproduced_by_manager'] for r in records))

if __name__=='__main__': unittest.main()
