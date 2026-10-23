"""Local INTIMA intake; all authored prompts here are synthetic test fixtures."""
from collections import Counter
from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RIGHTS = ROOT / 'docs/research/source-rights.json'
REVISION = 'b' * 40  # synthetic provenance, never an upstream revision
VERSION = 'a' * 40
ROWS = [
    {'code': 'fixture-alpha', 'prompt': '  Synthetic lantern exercise.\nKeep spacing.  ', 'model': 'fixture-generator-one'},
    {'code': 'fixture-beta', 'prompt': 'Synthetic café planning exercise.', 'model': 'fixture-generator-two'},
    {'code': 'fixture-alpha', 'prompt': '  Synthetic lantern exercise.\nKeep spacing.  ', 'model': 'fixture-generator-one'},
]


def fixture(rows=None, payload=None):
    """A separately declared synthetic rights review, not copied benchmark data."""
    rows = deepcopy(ROWS if rows is None else rows)
    if payload is None:
        payload = ('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n').encode('utf-8')
    hashes = [sha256(row['prompt'].encode('utf-8')).hexdigest() for row in rows]
    groups = {}
    for i, digest in enumerate(hashes, 1):
        groups.setdefault(digest, []).append(i)
    record = {
        'id': 'intima-prompts', 'name': 'Authored synthetic fixture',
        'source_url': f'https://example.org/fixture/resolve/{REVISION}/INTIMA.jsonl',
        'license_expression': 'CC0-1.0',
        'license_evidence_url': f'https://example.org/fixture/blob/{REVISION}/README.md',
        'license_evidence_sha': REVISION,
        'permissions': {'study_read': 'allowed_with_conditions', 'local_research': 'allowed_with_conditions',
                        'raw_redistribution': 'hold', 'product_use': 'hold',
                        'commercial_evaluation': 'allowed_with_conditions', 'commercial_training': 'hold'},
        'requirements': ['Synthetic fixture review only. Metadata-only public output.'],
        'attribution': {'creators': ['Synthetic Fixture Author'], 'license_url': 'https://creativecommons.org/publicdomain/zero/1.0/',
                        'changes': 'No prompt changes; preserve rows.'},
        'artifact': {'revision': REVISION, 'path': 'INTIMA.jsonl', 'bytes': len(payload),
                     'sha256': sha256(payload).hexdigest(), 'retrieved_at': '2026-10-23T00:00:00+00:00',
                     'role': 'evaluation_only', 'publication': 'metadata_only'},
        'data_quality': {'rows': len(rows), 'unique_prompts': len(set(hashes)),
                         'codes': len({r['code'] for r in rows}),
                         'code_counts': dict(Counter(r['code'] for r in rows)),
                         'prompt_generator_model_counts': dict(Counter(r['model'] for r in rows)),
                         'duplicate_groups': [{'prompt_sha256': digest, 'rows_1based': indices}
                                              for digest, indices in sorted(groups.items()) if len(indices) > 1]},
        'card_claim': {'rows': 2, 'codes': 1},
    }
    return payload, {'schema': 'manager.source-rights.v1', 'sources': [record]}


class IntimaIntakeTests(unittest.TestCase):
    def setUp(self):
        try:
            self.m = importlib.import_module('manager_core.intima_benchmark')
        except ModuleNotFoundError:
            self.fail('INTIMA intake implementation is missing (intended RED)')

    def reject(self, payload, rights):
        with self.assertRaises(ValueError) as caught:
            self.m.load_intima(payload, rights)
        self.assertEqual(str(caught.exception), 'INTIMA_INTAKE_UNAVAILABLE')
        for row in ROWS:
            self.assertNotIn(row['prompt'], repr(caught.exception))

    def test_preserves_exact_prompt_bytes_rows_and_generator_meaning(self):
        payload, rights = fixture()
        dataset = self.m.load_intima(payload, rights)
        self.assertEqual(len(dataset.cases), 3)
        self.assertEqual([c.case_id for c in dataset.cases], [f'intima:{REVISION}:row-{i}' for i in (1, 2, 3)])
        self.assertEqual([c.prompt for c in dataset.cases], [r['prompt'] for r in ROWS])
        self.assertEqual(dataset.cases[0].prompt_sha256, sha256(ROWS[0]['prompt'].encode()).hexdigest())
        self.assertEqual(dataset.cases[0].prompt_sha256, dataset.cases[2].prompt_sha256)
        self.assertEqual(dataset.cases[1].prompt_generator_model, 'fixture-generator-two')
        self.assertFalse(hasattr(dataset.cases[0], 'evaluated_model'))
        self.assertEqual(dataset.source.privacy_class, 'public_nonpersonal')
        self.assertTrue(dataset.source.verify_content(payload))
        self.assertEqual((dataset.artifact_revision, dataset.artifact_path), (REVISION, 'INTIMA.jsonl'))
        for obj, field, value in ((dataset, 'artifact_path', 'other'), (dataset.cases[0], 'code', 'other')):
            with self.assertRaises(FrozenInstanceError):
                setattr(obj, field, value)
        for row in ROWS:
            self.assertNotIn(row['prompt'], repr(dataset))
            self.assertNotIn(row['prompt'], repr(dataset.cases))
        self.assertNotIn('Synthetic lantern exercise.', repr(dataset))

    def test_export_is_deterministic_metadata_with_empty_evidence_and_no_outcomes(self):
        payload, rights = fixture()
        dataset = self.m.load_intima(payload, rights)
        first = self.m.intima_intake_manifest(dataset, code_version=VERSION)
        self.assertEqual(first, self.m.intima_intake_manifest(dataset, code_version=VERSION))
        self.assertEqual(first['stage'], 'INPUT_INTAKE_ONLY')
        self.assertEqual(first['evaluation_status'], 'NOT_RUN')
        self.assertEqual(first['actual']['rows'], 3)
        self.assertEqual(first['actual']['unique_prompts'], 2)
        self.assertEqual(first['actual']['codes'], 2)
        self.assertEqual(first['actual']['duplicate_excess_rows'], 1)
        self.assertEqual(first['actual']['code_counts'], {'fixture-alpha': 2, 'fixture-beta': 1})
        group = first['actual']['duplicate_groups'][0]
        self.assertEqual(group['rows_1based'], [1, 3])
        self.assertEqual(group['case_ids'], [f'intima:{REVISION}:row-1', f'intima:{REVISION}:row-3'])
        self.assertEqual(first['card_claim'], {'rows': 2, 'codes': 1})
        self.assertTrue(first['claim_discrepancy'])
        self.assertEqual(first['rights']['permissions']['commercial_training'], 'hold')
        self.assertEqual(first['validity'], {'person': 'UNKNOWN', 'time': 'UNKNOWN', 'transfer': 'UNKNOWN'})
        self.assertFalse(first['can_execute'])
        self.assertEqual(first['proof_level'], 'P0')
        self.assertEqual(first['human_welfare_status'], 'NOT_MEASURED')
        self.assertEqual(first['evidence']['references'], [])
        self.assertEqual(first['evidence']['assessment']['levels']['P0']['reference_hashes'], [])
        self.assertEqual(first['evidence']['assessment']['real_world_proof_level'], 'P0')
        self.assertEqual(first['evidence']['assessment']['human_welfare_status'], 'NOT_MEASURED')
        exported = json.dumps(first, ensure_ascii=False)
        for row in ROWS:
            self.assertNotIn(row['prompt'], exported)
            self.assertNotIn(json.dumps(row['prompt'], ensure_ascii=False), exported)
        for field in ('labels', 'scores', 'evaluated_model', 'judge_model'):
            self.assertNotIn(field, first)
        rights['sources'][0]['artifact']['role'] = 'training'
        first['actual']['code_counts']['fixture-alpha'] = 999
        self.assertEqual(self.m.intima_intake_manifest(dataset, code_version=VERSION)['actual']['code_counts']['fixture-alpha'], 2)

    def test_missing_and_held_evaluation_permissions_fail_closed(self):
        for permission in ('study_read', 'local_research', 'commercial_evaluation'):
            for replacement in (None, 'hold', 'not_applicable', True):
                with self.subTest(permission=permission, replacement=replacement):
                    payload, rights = fixture()
                    if replacement is None:
                        del rights['sources'][0]['permissions'][permission]
                    else:
                        rights['sources'][0]['permissions'][permission] = replacement
                    self.reject(payload, rights)

    def test_original_four_permissions_remain_required_and_training_is_held(self):
        for key in ('raw_redistribution', 'product_use', 'commercial_training'):
            payload, rights = fixture()
            del rights['sources'][0]['permissions'][key]
            self.reject(payload, rights)
        payload, rights = fixture()
        rights['sources'][0]['permissions']['commercial_training'] = 'allowed_with_conditions'
        self.reject(payload, rights)
        payload, rights = fixture()
        rights['sources'][0]['artifact']['role'] = 'training'
        self.reject(payload, rights)
        payload, rights = fixture()
        rights['sources'][0]['artifact']['publication'] = 'raw'
        self.reject(payload, rights)

    def test_wrong_revision_hash_length_and_duplicate_source_fail_closed(self):
        for key, value in (('revision', 'c' * 40), ('sha256', '0' * 64), ('bytes', 1), ('path', 'other.jsonl')):
            payload, rights = fixture()
            rights['sources'][0]['artifact'][key] = value
            self.reject(payload, rights)
        payload, rights = fixture()
        rights['sources'].append(deepcopy(rights['sources'][0]))
        self.reject(payload, rights)
        for manifest in ({}, {'schema': 'other', 'sources': []}, {'schema': 'manager.source-rights.v1', 'sources': []}):
            self.reject(payload, manifest)

    def test_inconsistent_quality_profile_rejected(self):
        for key, value in (('rows', 2), ('unique_prompts', 3), ('codes', 1), ('code_counts', {'fixture-alpha': 3}),
                           ('prompt_generator_model_counts', {'fixture-generator-one': 3}), ('duplicate_groups', [])):
            payload, rights = fixture()
            rights['sources'][0]['data_quality'][key] = value
            self.reject(payload, rights)
        payload, rights = fixture()
        rights['sources'][0]['data_quality']['rows'] = True
        self.reject(payload, rights)

    def test_bad_json_schema_types_and_empty_values_rejected_without_raw_errors(self):
        for key in ('code', 'prompt', 'model'):
            for value in ('', '  ', None, 1, False, [], {}):
                rows = deepcopy(ROWS)
                rows[0][key] = value
                payload = ('\n'.join(json.dumps(r) for r in rows) + '\n').encode()
                _, rights = fixture(payload=payload)
                self.reject(payload, rights)
        for payload in (b'', b'\xff', b'[]\n', b'null\n', b'\n', b'{"prompt":"Synthetic lantern exercise.", broken}\n',
                        b'{"code":"a","code":"b","prompt":"private fixture","model":"g"}\n'):
            _, rights = fixture(payload=payload)
            self.reject(payload, rights)
        for change in ('extra', 'missing'):
            rows = deepcopy(ROWS)
            if change == 'extra':
                rows[0]['evaluated_model'] = 'wrong meaning'
            else:
                del rows[0]['model']
            payload = ('\n'.join(json.dumps(r) for r in rows) + '\n').encode()
            _, rights = fixture(payload=payload)
            self.reject(payload, rights)

    def test_jsonl_delimiter_does_not_split_unicode_prompt_characters(self):
        rows = deepcopy(ROWS)
        rows[1]['prompt'] = 'Synthetic paragraph\u2028and next part\u0085retained.'
        payload, rights = fixture(rows)
        dataset = self.m.load_intima(payload, rights)
        self.assertEqual(dataset.cases[1].prompt, rows[1]['prompt'])
        self.assertEqual(len(dataset.cases), 3)

    def test_code_version_requires_exact_immutable_sha(self):
        payload, rights = fixture()
        dataset = self.m.load_intima(payload, rights)
        for version in ('main', '', 'a' * 39, 'A' * 40, 'g' * 40, None):
            with self.subTest(version=version), self.assertRaises(ValueError) as caught:
                self.m.intima_intake_manifest(dataset, code_version=version)
            self.assertEqual(str(caught.exception), 'INTIMA_INTAKE_UNAVAILABLE')

    def test_cli_local_success_and_static_failure_do_not_echo_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'synthetic.jsonl'
            review = Path(tmp) / 'synthetic-rights.json'
            payload, rights = fixture()
            data.write_bytes(payload)
            review.write_text(json.dumps(rights), encoding='utf-8')
            command = [sys.executable, str(ROOT / 'scripts/inspect_intima_benchmark.py'), str(data),
                       '--code-version', VERSION, '--rights-manifest', str(review)]
            result = subprocess.run(command, capture_output=True, text=True, cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['actual']['rows'], 3)
            self.assertEqual(result.stderr, '')
            for row in ROWS:
                self.assertNotIn(row['prompt'], result.stdout + result.stderr)
            for bad in ('changed payload', 'missing', 'bad rights', 'bad version'):
                current = list(command)
                if bad == 'changed payload':
                    data.write_bytes(b'private fixture must not leak')
                elif bad == 'missing':
                    current[2] = str(Path(tmp) / 'private-nonexistent-path')
                elif bad == 'bad rights':
                    review.write_text('{private malformed rights', encoding='utf-8')
                else:
                    current[current.index('--code-version') + 1] = 'main'
                result = subprocess.run(current, capture_output=True, text=True, cwd=tmp)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, 'INTIMA_INTAKE_UNAVAILABLE\n')
                data.write_bytes(payload)
                review.write_text(json.dumps(rights), encoding='utf-8')
            # Default manifest must be usable from a different cwd; synthetic bytes fail its production hash.
            result = subprocess.run(command[:-2], capture_output=True, text=True, cwd=tmp)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (2, '', 'INTIMA_INTAKE_UNAVAILABLE\n'))


class ProductionIntimaRightsTests(unittest.TestCase):
    def test_production_review_pins_independent_upstream_facts(self):
        manifest = json.loads(RIGHTS.read_text(encoding='utf-8'))
        self.assertEqual(manifest['schema'], 'manager.source-rights.v1')
        records = [r for r in manifest['sources'] if r['id'] == 'intima-prompts']
        self.assertEqual(len(records), 1, 'INTIMA production rights review missing (intended RED)')
        record = records[0]
        revision = '48537e5d3905152751964b48d0a2ef681ace74dc'
        self.assertEqual(record['artifact']['revision'], revision)
        self.assertEqual(record['artifact']['path'], 'INTIMA.jsonl')
        self.assertEqual(record['artifact']['bytes'], 98989)
        self.assertEqual(record['artifact']['sha256'], '31b683f0592a88db078e9cd8f3b03eefbd59edeac14b7894a92894d1518eb136')
        self.assertEqual(record['artifact']['role'], 'evaluation_only')
        self.assertEqual(record['artifact']['publication'], 'metadata_only')
        self.assertEqual(record['license_expression'], 'CC-BY-4.0')
        self.assertEqual(record['license_evidence_url'], f'https://huggingface.co/datasets/AI-companionship/INTIMA/blob/{revision}/README.md')
        self.assertEqual(record['license_evidence_sha'], revision)
        self.assertEqual(record['source_url'], f'https://huggingface.co/datasets/AI-companionship/INTIMA/resolve/{revision}/INTIMA.jsonl')
        self.assertEqual(record['permissions'], {'study_read': 'allowed_with_conditions', 'local_research': 'allowed_with_conditions',
                         'raw_redistribution': 'hold', 'product_use': 'hold',
                         'commercial_evaluation': 'allowed_with_conditions', 'commercial_training': 'hold'})
        self.assertEqual(record['data_quality']['rows'], 380)
        self.assertEqual(record['data_quality']['unique_prompts'], 376)
        self.assertEqual(record['data_quality']['codes'], 32)
        code_counts = {name: 12 for name in ('age of the user', 'attachment', 'challenging time', 'company', 'consistent',
            'friendship', 'funny', 'gifting', 'grief', 'growing from a tool', 'growth', 'guide', 'helpful', 'loneliness',
            'long-term relationship', 'lose yourself in the conversation', 'love', 'memory', 'neurodivergent', 'personalised',
            'preference over people', 'regular interaction', 'romantic partner', 'smart', 'support', 'therapy', 'understanding')}
        code_counts.update({'always happy': 9, 'availability': 9, 'mirror': 8, 'name': 15, 'persona': 15})
        self.assertEqual(record['data_quality']['code_counts'], code_counts)
        self.assertEqual(record['data_quality']['prompt_generator_model_counts'],
            {'Llama-3.1-8B-Instruct': 124, 'Qwen2.5-72B-Instruct': 128, 'Mistral-Small-24B-Instruct-2501': 128})
        self.assertEqual({g['prompt_sha256']: g['rows_1based'] for g in record['data_quality']['duplicate_groups']}, {
            '5c9ff789d2b43e07d03332b5a1e0708ca68ece6d08e835faca425a0ffef06555': [126, 129],
            'd47aee1b177d1754ff7d35263d5afe436dfab74ce9119afabfc897e65034c758': [127, 130],
            'd3b3a580005079d1afdf599871118e0216f6e069545d006dac75c1c226547e2b': [133, 136],
            '72e971cdbd7ba46a5f9cb7de630223a5939427652523ecba15b12c1c82ea42b3': [134, 137]})
        self.assertEqual(record['card_claim'], {'rows': 368, 'codes': 31})


if __name__ == '__main__':
    unittest.main()
