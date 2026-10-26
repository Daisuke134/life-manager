"""Authored MCQ fixtures only; no benchmark rows or model execution.

Each test catches a named boundary break: altered provenance, lost assignments,
coerced labels, inferred refusal, hidden denominators, or row-content leakage.
The test fixture patches only frozen hashes so real Source intake can run on
small authored bytes. Production pin/rehashed-substitution tests are unpatched.
"""
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import importlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'experiments/behavior-model/safetybench-mcq-protocol-v1.json'
RIGHTS = ROOT / 'docs/research/source-rights.json'
VERSION = 'a' * 40
STATES = ('VALID', 'INVALID_PARSE', 'REFUSAL', 'FAILED', 'UNKNOWN', 'NOT_RUN', 'ABSTAIN')
CATEGORIES = ('Offensiveness', 'Unfairness and Bias', 'Physical Health', 'Mental Health',
              'Illegal Activities', 'Ethics and Morality', 'Privacy and Property')
QHASH = '517648d44a68c79e5d46a284837d673c578fa53a45785c83407cd8358602c547'
AHASH = 'a26ec13deeb551d68f71d61dd269d05dd43c24e6b22d8be3b93788ee10cf8615'
ERROR = 'SAFETYBENCH_MCQ_UNAVAILABLE'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def authored(n=7):
    questions = [{'id': i, 'category': CATEGORIES[i % 7], 'question': '  Authored café lantern\n  ',
                  'options': [' synthetic α ', 'synthetic β', 'synthetic γ', 'synthetic δ'][:2 + i % 3]}
                 for i in range(n)]
    answers = {str(i): {'answer': i % 2, 'category': CATEGORIES[i % 7]} for i in range(n)}
    return questions, answers


class SafetyBenchTests(unittest.TestCase):
    def setUp(self):
        try:
            self.m = importlib.import_module('manager_core.safetybench_mcq')
        except ModuleNotFoundError:
            self.fail('SafetyBench MCQ implementation missing (intended RED)')

    def reject(self, fn, *args, **kwargs):
        with self.assertRaises(ValueError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(str(caught.exception), ERROR)

    @contextmanager
    def fixture(self, n=7, answers_override=None, questions_payload_override=None, answers_payload_override=None):
        questions, answers = authored(n)
        if answers_override is not None:
            answers = answers_override
        q = canonical(questions) if questions_payload_override is None else questions_payload_override
        a = canonical(answers) if answers_payload_override is None else answers_payload_override
        protocol = json.loads(PROTOCOL.read_bytes())
        manifest = json.loads(RIGHTS.read_bytes())
        review = deepcopy(next(r for r in manifest['sources'] if r['id'] == 'safetybench-mcq-private-evaluation-v1'))
        for key, payload in (('questions', q), ('answers', a)):
            protocol['artifacts'][key]['sha256'] = sha256(payload).hexdigest()
            protocol['artifacts'][key]['bytes'] = len(payload)
        protocol['assignment']['count'] = n
        protocol['assignment']['category_counts'] = {c: sum(r['category'] == c for r in questions) for c in CATEGORIES}
        protocol['assignment']['option_counts'] = {str(k): sum(len(r['options']) == k for r in questions) for k in (2, 3, 4)}
        review['artifact']['artifacts'] = deepcopy(protocol['artifacts'])
        protocol['rights_record_sha256'] = sha256(canonical(review)).hexdigest()
        p = canonical(protocol)
        manifest['sources'][-1] = review
        with patch.object(self.m, 'PROTOCOL_SHA256', sha256(p).hexdigest()), patch.object(
                self.m, 'RIGHTS_RECORD_SHA256', sha256(canonical(review)).hexdigest()):
            dataset = self.m.load_safetybench(q, a, protocol_payload=p, expected_sha256=sha256(p).hexdigest(),
                                             rights_manifest=manifest, retrieved_at=datetime(2026, 10, 23, tzinfo=timezone.utc))
            yield dataset, q, a, p, manifest

    def envelope(self, dataset, rows=None):
        return {'schema': 'manager.safetybench-recorded-predictions.v1',
                'questions_sha256': dataset.questions_source.content_sha256,
                'answers_sha256': dataset.answers_source.content_sha256,
                'membership_sha256': dataset.membership_sha256,
                'producer': {'kind': 'MODEL', 'name': 'private fixture producer', 'version': None, 'run_receipt_sha256': None},
                'rows': [] if rows is None else rows}

    def evaluate(self, dataset, envelope=None):
        return self.m.evaluate_recorded(dataset, None if envelope is None else canonical(envelope), code_version=VERSION)

    def test_all_denominators(self):
        with self.fixture() as (dataset, *_):
            env = self.envelope(dataset, [{'id': str(i), 'status': state, 'prediction': 0 if state == 'VALID' else None}
                                          for i, state in enumerate(STATES)])
            r = self.evaluate(dataset, env)['policies']['recorded']
            self.assertEqual((r['assigned'], r['correct'], r['valid_scored'], r['conditional_accuracy']), (7, 1, 1, 1.0))
            self.assertEqual(r['state_counts'], {s: 1 for s in STATES})
            self.assertAlmostEqual(r['native_accuracy_percent']['Avg.'], 100 / 7)
            self.assertAlmostEqual(r['valid_coverage'], 1 / 7)
            self.assertEqual(r['categories']['Offensiveness']['native_accuracy_percent'], 100.0)
            self.assertIsNone(r['categories']['Mental Health']['conditional_accuracy'])
        with self.fixture(3) as (dataset, *_):
            env = self.envelope(dataset, [{'id': '0', 'status': 'VALID', 'prediction': 0},
                                          {'id': '1', 'status': 'VALID', 'prediction': 0}])
            r = self.evaluate(dataset, env)['policies']['recorded']
            self.assertEqual(r['state_counts']['NOT_RUN'], 1)
            self.assertEqual(r['conditional_accuracy'], 0.5)
            self.assertAlmostEqual(r['native_accuracy_percent']['Avg.'], 100 / 3)
            self.assertEqual(r['categories']['Privacy and Property']['native_accuracy_percent'], 0.0)
            self.assertIsNone(r['categories']['Privacy and Property']['conditional_accuracy'])

    def test_native_and_no_action(self):
        with self.fixture() as (dataset, *_):
            result = self.evaluate(dataset)
            recorded, no_action = (result['policies'][k] for k in ('recorded', 'no_action'))
            self.assertEqual(recorded['state_counts']['NOT_RUN'], 7)
            self.assertEqual(no_action['state_counts']['ABSTAIN'], 7)
            self.assertEqual(no_action['state_counts']['REFUSAL'], 0)
            self.assertIsNone(no_action['conditional_accuracy'])
            self.assertEqual(no_action['native_accuracy_percent']['Avg.'], 0.0)
            self.assertEqual(self.m._native_accuracy(dataset.cases, {'0': 0, '1': 0})['UB'], 0.0)
            self.assertNotIn('mae', json.dumps(result))
            self.assertNotIn('likelihood', json.dumps(result))
            self.assertEqual(self.evaluate(dataset, self.envelope(dataset))['policies']['recorded']['state_counts'], recorded['state_counts'])

    def test_first_option_rule(self):
        maps = []
        native = self.m._native_accuracy
        def observe(cases, predictions):
            maps.append(dict(predictions))
            return native(cases, predictions)
        with self.fixture() as (dataset, *_), patch.object(self.m, '_native_accuracy', side_effect=observe):
            r = self.evaluate(dataset)['policies']['first_option_rule']
            self.assertEqual(r['state_counts'], dict(zip(STATES, (7, 0, 0, 0, 0, 0, 0))))
            self.assertEqual((r['correct'], r['conditional_accuracy']), (4, 4 / 7))
            self.assertEqual(r['prediction_origin'], 'DETERMINISTIC_FIRST_OPTION_RULE')
            self.assertIn({str(i): 0 for i in range(7)}, maps)
        _, answers = authored()
        for answer in answers.values():
            answer['answer'] = 1
        maps.clear()
        with self.fixture(answers_override=answers) as (dataset, *_), patch.object(self.m, '_native_accuracy', side_effect=observe):
            self.assertEqual(self.evaluate(dataset)['policies']['first_option_rule']['correct'], 0)
            self.assertIn({str(i): 0 for i in range(7)}, maps)

    def test_strict_join(self):
        questions, answers = authored()
        cases = self.m._reconstruct_cases(questions, answers, expected_count=7)
        self.assertEqual([c.case_id for c in cases], list(map(str, range(7))))
        self.assertEqual(cases[0].question_sha256, sha256(questions[0]['question'].encode()).hexdigest())
        self.assertEqual(cases[0].option_sha256, tuple(sha256(v.encode()).hexdigest() for v in questions[0]['options']))
        # Identical rows with different IDs survive unchanged.
        questions[1] = dict(deepcopy(questions[0]), id=1)
        answers['1'] = deepcopy(answers['0'])
        self.assertEqual(len(self.m._reconstruct_cases(questions, answers, expected_count=7)), 7)
        self.reject(self.m._reconstruct_cases, [], {}, expected_count=0)
        mutations = [('id', x) for x in (True, 1.0, '0', -1)] + [('category', 'Unknown'), ('options', ['one']),
            ('options', ['a'] * 5), ('options', ['a', ' ']), ('question', ' '), ('extra', 'x')]
        for key, value in mutations:
            q, a = authored()
            q[0][key] = value
            self.reject(self.m._reconstruct_cases, q, a, expected_count=7)
        for change in ('duplicate', 'missing', 'extra', 'collision', 'mismatch', 'extra-gold', 'missing-gold'):
            q, a = authored()
            if change == 'duplicate': q[1]['id'] = 0
            elif change == 'missing': del a['0']
            elif change == 'extra': a['99'] = a['0']
            elif change == 'collision': a['00'] = a.pop('0')
            elif change == 'mismatch': a['0']['category'] = CATEGORIES[1]
            elif change == 'extra-gold': a['0']['extra'] = 1
            else: del a['0']['answer']
            self.reject(self.m._reconstruct_cases, q, a, expected_count=7)
        for value in (True, 0.0, '0', -1, 2, None):
            q, a = authored()
            a['0']['answer'] = value
            self.reject(self.m._reconstruct_cases, q, a, expected_count=7)

    def test_strict_json_and_source_bytes(self):
        with self.fixture() as (dataset, q, a, p, rights):
            args = dict(protocol_payload=p, expected_sha256=sha256(p).hexdigest(), rights_manifest=rights,
                        retrieved_at=dataset.questions_source.retrieved_at)
            for bad in (q + b' ', q[:-1], q.replace(b'lantern', b'letters'), b'[]', b'NaN', b'{"x":1,"x":2}'):
                self.reject(self.m.load_safetybench, bad, a, **args)
            for bad in (b'{"x":1,"x":2}', b'NaN', b'{"producer":{"name":"a","name":"b"}}'):
                self.reject(self.m.evaluate_recorded, dataset, bad, code_version=VERSION)
            self.reject(self.m.load_safetybench, q, a, **dict(args, retrieved_at=datetime(2026, 10, 23)))
            # Matching fixture pins must not make duplicate keys/NaN acceptable JSON.
            for bad in (b'{"x":1,"x":2}', b'NaN'):
                self.reject(self.m.validate_protocol, bad, sha256(bad).hexdigest())

    def test_duplicate_keys_and_nan_rejected_after_matching_source_hash(self):
        q, a = authored()
        for bad in (canonical(q).replace(b'"id":0', b'"id":0,"id":0'),
                    canonical(q).replace(b'"id":0', b'"id":NaN')):
            with self.assertRaises(ValueError) as caught:
                with self.fixture(questions_payload_override=bad):
                    self.fail('duplicate key or NaN accepted')
            self.assertEqual(str(caught.exception), ERROR)
        for bad in (canonical(a).replace(b'"answer":0', b'"answer":0,"answer":0', 1),
                    canonical(a).replace(b'"answer":0', b'"answer":NaN', 1)):
            with self.assertRaises(ValueError) as caught:
                with self.fixture(answers_payload_override=bad):
                    self.fail('duplicate key or NaN accepted')
            self.assertEqual(str(caught.exception), ERROR)

    def test_native_upstream_percentage_operation_order(self):
        with self.fixture(3) as (dataset, *_):
            # Upstream divides counts, then multiplies by100. Hand-checked IEEE result.
            self.assertEqual(self.m._native_accuracy(dataset.cases, {'0': 0})['Avg.'], 33.33333333333333)

    def test_category_all_gold_denominator(self):
        with self.fixture(14) as (dataset, *_):
            env = self.envelope(dataset, [{'id': '0', 'status': 'VALID', 'prediction': 0}])
            category = self.evaluate(dataset, env)['policies']['recorded']['categories']['Offensiveness']
            self.assertEqual((category['assigned'], category['valid_scored'], category['conditional_accuracy']), (2, 1, 1.0))
            self.assertEqual(category['native_accuracy_percent'], 50.0)

    def test_prediction_integrity(self):
        with self.fixture() as (dataset, *_):
            base = self.envelope(dataset, [{'id': '0', 'status': 'VALID', 'prediction': 0}])
            variants = []
            for key in ('questions_sha256', 'answers_sha256', 'membership_sha256', 'schema'):
                env = deepcopy(base); env[key] = '0' * 64; variants.append(env)
            for row in ({'id': '99', 'status': 'VALID', 'prediction': 0}, {'id': '00', 'status': 'ABSTAIN', 'prediction': None},
                        {'id': 0, 'status': 'ABSTAIN', 'prediction': None}, {'id': '0', 'status': 'NEW', 'prediction': None},
                        {'id': '0', 'status': 'VALID', 'prediction': 2}):
                env = deepcopy(base); env['rows'] = [row]; variants.append(env)
            env = deepcopy(base); env['rows'] *= 2; variants.append(env)
            for value in (None, True, 0.0, '0', -1):
                env = deepcopy(base); env['rows'][0]['prediction'] = value; variants.append(env)
            for status in STATES[1:]:
                env = deepcopy(base); env['rows'][0]['status'] = status; variants.append(env)
            for producer in ({}, {'kind': 'MODEL', 'name': 'x'}, dict(base['producer'], kind='OTHER_KIND'),
                             dict(base['producer'], name=' '), dict(base['producer'], name='x' * 257),
                             dict(base['producer'], version='x' * 257), dict(base['producer'], run_receipt_sha256='private prose')):
                env = deepcopy(base); env['producer'] = producer; variants.append(env)
            for env in variants:
                self.reject(self.m.evaluate_recorded, dataset, canonical(env), code_version=VERSION)
            env = self.envelope(dataset, [{'id': '0', 'status': 'INVALID_PARSE', 'prediction': None}])
            self.assertEqual(self.evaluate(dataset, env)['policies']['recorded']['state_counts']['INVALID_PARSE'], 1)
            self.assertEqual(self.evaluate(dataset, env)['policies']['recorded']['state_counts']['REFUSAL'], 0)

    def test_dataset_mutation_rejected(self):
        with self.fixture() as (dataset, *_):
            mutations = [replace(dataset, membership_sha256='0' * 64), replace(dataset, cases=dataset.cases[:-1]),
                         replace(dataset, questions_source=replace(dataset.questions_source, content_sha256='0' * 64)),
                         replace(dataset, _protocol_json='{}'), replace(dataset, _review_json='{}'),
                         replace(dataset, cases=(replace(dataset.cases[0], answer=1),) + dataset.cases[1:])]
            for changed in mutations:
                self.reject(self.m.evaluate_recorded, changed, None, code_version=VERSION)
            self.reject(self.m.evaluate_recorded, {}, None, code_version=VERSION)
            for version in ('main', 'A' * 40, None):
                self.reject(self.m.evaluate_recorded, dataset, None, code_version=version)

    def test_coherent_case_substitution_rejected_against_verified_sources(self):
        # A self-rehashed valid profile must not rebind gold/order/content to old source hashes.
        with self.fixture() as (dataset, *_):
            substitutions = {
                'gold': tuple(replace(case, answer=0) for case in dataset.cases),
                'source_order': tuple(reversed(dataset.cases)),
                'id': (replace(dataset.cases[0], case_id='99'),) + dataset.cases[1:],
                'question_hash': (replace(dataset.cases[0], question_sha256='0' * 64),) + dataset.cases[1:],
                'option_order': (replace(dataset.cases[0], option_sha256=tuple(reversed(dataset.cases[0].option_sha256))),) + dataset.cases[1:],
            }
            self.assertEqual(self.evaluate(dataset)['policies']['first_option_rule']['correct'], 4)
            for name, cases in substitutions.items():
                with self.subTest(substitution=name):
                    forged = replace(dataset, cases=cases, membership_sha256=self.m._membership(cases))
                    self.reject(self.m.evaluate_recorded, forged, None, code_version=VERSION)

    def test_private_source_snapshots_reverified_and_never_exported(self):
        with self.fixture() as (dataset, q, a, *_):
            self.assertEqual(getattr(dataset, '_questions_payload', None), q, 'retain original verified question bytes')
            self.assertEqual(getattr(dataset, '_answers_payload', None), a, 'retain original verified answer bytes')
            substitutions = {
                'question_same_length': {'_questions_payload': q.replace(b'lantern', b'letters')},
                'answer_same_length': {'_answers_payload': a.replace(b'"answer":1', b'"answer":0')},
                'question_length': {'_questions_payload': q + b' '},
                'answer_length': {'_answers_payload': a + b' '},
                'mutable_questions': {'_questions_payload': bytearray(q)},
                'mutable_answers': {'_answers_payload': bytearray(a)},
            }
            for name, fields in substitutions.items():
                with self.subTest(substitution=name):
                    self.reject(self.m.evaluate_recorded, replace(dataset, **fields), None, code_version=VERSION)
            changed_cases = tuple(replace(case, answer=0) for case in dataset.cases)
            # Replacing both derived cases and their matching answer bytes still fails the pinned hash.
            forged = replace(dataset, cases=changed_cases, membership_sha256=self.m._membership(changed_cases),
                             _answers_payload=a.replace(b'"answer":1', b'"answer":0'))
            self.reject(self.m.evaluate_recorded, forged, None, code_version=VERSION)
            exported = json.dumps(self.evaluate(dataset))
            for private in (q, a):
                self.assertNotIn(repr(private), repr(dataset))
                self.assertNotIn(private.decode(), exported)
            self.assertNotIn('_questions_payload', exported + repr(dataset))
            self.assertNotIn('_answers_payload', exported + repr(dataset))

    def test_metadata_and_cli(self):
        spec = importlib.util.spec_from_file_location('fixture_safetybench_cli', ROOT / 'scripts/evaluate_safetybench_mcq.py')
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        with self.fixture() as (dataset, q, a, p, rights):
            env = self.envelope(dataset)
            result = self.evaluate(dataset, env)
            self.assertEqual((result['proof_level'], result['human_welfare_status'], result['can_execute'], result['adoption']),
                             ('P0', 'NOT_MEASURED', False, 'HOLD'))
            self.assertEqual(result['evidence']['references'], [])
            for key in ('pressure', 'dependency', 'response_harm', 'clinical_validity', 'behavior_change'):
                self.assertIsNone(result[key])
            self.assertEqual(result['sources']['questions']['sha256'], sha256(q).hexdigest())
            self.assertEqual(result['sources']['answers']['sha256'], sha256(a).hexdigest())
            self.assertEqual(result['sources']['questions']['retrieved_at'], result['sources']['answers']['retrieved_at'])
            self.assertTrue(result['sources']['questions']['retrieved_at_basis'].startswith('LOCAL_BYTES_VERIFIED_AT'))
            self.assertEqual(result['protocol_sha256'], sha256(p).hexdigest())
            self.assertEqual(result['rights_record_sha256'], sha256(canonical(rights['sources'][-1])).hexdigest())
            self.assertEqual(result['predictions_sha256'], sha256(canonical(env)).hexdigest())
            self.assertEqual(result['producer']['name_sha256'], sha256(b'private fixture producer').hexdigest())
            self.assertIsNone(result['producer']['version_sha256'])
            self.assertIsNone(result['producer']['run_receipt_sha256'])
            self.assertEqual(result['producer']['provenance'], 'DECLARED_NOT_AUTHENTICATED')
            exported = json.dumps(result) + repr(dataset)
            self.assertNotIn('Authored café', exported)
            self.assertNotIn('synthetic α', exported)
            self.assertNotIn('private fixture producer', exported)
            self.assertNotIn('case_id=', repr(dataset.cases))
            self.assertNotIn('answer=', repr(dataset.cases))
            self.assertNotIn('rows', result)
            with tempfile.TemporaryDirectory() as tmp:
                paths = [Path(tmp) / name for name in ('q.json', 'a.json', 'p.json', 'r.json')]
                for path, payload in zip(paths, (q, a, p, canonical(rights))): path.write_bytes(payload)
                args = ['--questions-path', str(paths[0]), '--answers-path', str(paths[1]), '--protocol-path', str(paths[2]),
                        '--rights-path', str(paths[3]), '--expected-sha256', sha256(p).hexdigest(), '--code-version', VERSION]
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr): code = cli.main(args)
                self.assertEqual((code, stderr.getvalue()), (0, ''))
                self.assertEqual(json.loads(stdout.getvalue())['policies']['recorded']['state_counts']['NOT_RUN'], 7)
                self.assertIn('rights_manifest_sha256', json.loads(stdout.getvalue()), 'CLI must audit its exact rights input bytes')
                self.assertEqual(json.loads(stdout.getvalue())['rights_manifest_sha256'], sha256(canonical(rights)).hexdigest())
                for bad_args in ([], args + ['--private-unknown'], args[:-1] + ['private-version']):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with redirect_stdout(stdout), redirect_stderr(stderr): code = cli.main(bad_args)
                    self.assertEqual((code, stdout.getvalue(), stderr.getvalue()), (2, '', ERROR + '\n'))
                process = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/evaluate_safetybench_mcq.py'),
                                          '--private-fixture-argument'], capture_output=True, text=True, cwd=tmp)
                self.assertEqual((process.returncode, process.stdout, process.stderr), (2, '', ERROR + '\n'))
                paths[0].write_bytes(b'private malformed content')
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr): code = cli.main(args)
                self.assertEqual((code, stdout.getvalue(), stderr.getvalue()), (2, '', ERROR + '\n'))
        self.assertNotIn('torch', sys.modules)
        self.assertNotIn('transformers', sys.modules)

    def test_original_four_canonical_records_unchanged(self):
        baseline = {'helpsteer2-candidates': '0b76b970e877dc17a6fc21c18979c9c7efaf4e1e6053c01a9c13577ee2920a41', 'xstest-mistral-refusal-private': 'e3f0f0d53269eb52d54ebd8b2feccf8654cf433dce0fbc746a875fbbdabf434d', 'helpsteer2-private-exploratory-sft-train27-v1': 'f41063b9ae281bc5bc1677655cb5a5997b1c9b5de8857ac180480176d71a1be5', 'helpsteer2-private-fixed-adapter-eval24-v1': '088f6cc5a17f8ff3c83dfc10b44bca70dbd0855d3dd0c8b1063727ff2271225d'}
        records = json.loads(RIGHTS.read_bytes())['sources']
        self.assertEqual(len(records), 13)
        self.assertEqual({r['id']: sha256(canonical(r)).hexdigest() for r in records[:4]}, baseline)
        self.assertEqual(records[-1]['id'], 'safetybench-mcq-private-evaluation-v1')
        self.assertEqual(sha256(canonical(records[-1])).hexdigest(), '07e6beea0bf5570a9b1fab8153c80306dde7a1f29159125109b6b03e16648fd4')
        self.assertEqual(
            {r['id'] for r in records[4:-1]},
            {f'eba-code-{name}' for name in ('inspect-ai', 'concordia', 'oasis', 'tau2bench', 'dowhy', 'econml', 'ai-economist', 'omni-behavior')},
        )

    def test_frozen_bindings(self):
        p = PROTOCOL.read_bytes()
        protocol = self.m.validate_protocol(p, sha256(p).hexdigest())
        self.assertEqual(protocol['artifacts']['questions']['sha256'], QHASH)
        self.assertEqual(protocol['artifacts']['questions']['bytes'], 5110687)
        self.assertEqual(protocol['artifacts']['answers']['sha256'], AHASH)
        self.assertEqual(protocol['artifacts']['answers']['bytes'], 729736)
        self.assertEqual(protocol['assignment']['count'], 11435)
        self.assertEqual(protocol['source_revision'], '960833692a1ec82b191ff3e902daca7993c35cc1')
        self.assertEqual(protocol['dataset_card_revision'], '70538631943dc1517ae9bb0733251809f4445d0e')
        changed = canonical(dict(protocol, source_revision='a' * 40))
        self.reject(self.m.validate_protocol, changed, sha256(changed).hexdigest())
        self.reject(self.m.validate_protocol, p, '0' * 64)
        manifest = json.loads(RIGHTS.read_bytes())
        review = self.m.validate_rights(manifest, protocol)
        self.assertEqual(review['artifact']['role'], 'mcq_evaluation_only')
        self.assertEqual(review['artifact']['publication'], 'metadata_only')
        self.assertEqual(review['permissions'], dict(study_read='allowed_with_conditions', local_research='allowed_with_conditions',
            commercial_evaluation='allowed_with_conditions', commercial_training='hold', product_use='hold', raw_redistribution='hold'))
        for field, value in (('role', 'training'), ('revision', 'a' * 40), ('publication', 'raw')):
            altered = deepcopy(manifest); altered['sources'][-1]['artifact'][field] = value
            self.reject(self.m.validate_rights, altered, protocol)
        for action in ('absent', 'duplicate', 'held', 'license'):
            altered = deepcopy(manifest)
            if action == 'absent': altered['sources'].pop()
            elif action == 'duplicate': altered['sources'].append(deepcopy(altered['sources'][-1]))
            elif action == 'held': altered['sources'][-1]['permissions']['commercial_evaluation'] = 'hold'
            else: altered['sources'][-1]['license_expression'] = 'invented'
            self.reject(self.m.validate_rights, altered, protocol)
        review['permissions']['commercial_training'] = 'allowed_with_conditions'
        self.assertEqual(self.m.validate_rights(manifest, protocol)['permissions']['commercial_training'], 'hold')


if __name__ == '__main__':
    unittest.main()
