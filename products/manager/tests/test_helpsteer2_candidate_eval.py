"""Fictional fixtures only; no optional ML dependencies or model execution."""
import copy
import importlib
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from hashlib import sha256


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'experiments/behavior-model/helpsteer2-dev-protocol-v1.json'
VERSION = 'a' * 40


def module():
    assert importlib.util.find_spec('manager_core.helpsteer2_candidate_eval'), 'evaluator missing'
    return importlib.import_module('manager_core.helpsteer2_candidate_eval')


def digest(text):
    return sha256(text.encode()).hexdigest()


def fixture():
    preferences, quality, specs = [], [], []
    for n in range(1, 9):
        prompt, a, b = f'fictional query {n}', f'fictional first {n}', f'fictional second {n}'
        preferences.append(dict(split='train', prompt=prompt, response_1=a, response_2=b,
                                preference_strength=-1 if n % 2 else 2))
        for response in (a, b):
            quality.append(dict(prompt=prompt, response=response, helpfulness=3, correctness=4,
                                coherence=4, complexity=1, verbosity=2))
        specs.append(dict(preference_row_1based=n, native_preference_split='train',
                          prompt_sha256=digest(prompt), response_sha256=[digest(a), digest(b)],
                          full_sequence_token_counts=[6, 7]))
    return preferences, quality, specs


def encode(case):
    m = module()
    return (m.completion_mask([1, 2, 3, 4], [1, 2, 3, 4, 5, 151645]),
            m.completion_mask([1, 2, 3, 4], [1, 2, 3, 4, 5, 6, 151645]))


class HelpSteer2Tests(unittest.TestCase):
    def cases(self):
        p, q, s = fixture()
        return module()._reconstruct_cases(s, p, q)

    def test_frozen_protocol_and_all_pins(self):
        m = module()
        protocol = m.validate_protocol(PROTOCOL.read_bytes(), m.PROTOCOL_SHA256)
        self.assertEqual(len(protocol['dev_cases']), 8)
        for key in ('model_revision', 'dataset_revision', 'template', 'computation', 'dev_cases'):
            changed = copy.deepcopy(protocol)
            changed[key] = None
            raw = json.dumps(changed).encode()
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, '^HELPSTEER2_DEV_UNAVAILABLE$'):
                m.validate_protocol(raw, sha256(raw).hexdigest())

    def test_protocol_missing_tampered_or_wrong_expected_hash(self):
        m = module()
        for raw, expected in ((b'{}', m.PROTOCOL_SHA256), (PROTOCOL.read_bytes(), '0' * 64),
                              (PROTOCOL.read_bytes() + b' ', m.PROTOCOL_SHA256)):
            with self.assertRaisesRegex(ValueError, '^HELPSTEER2_DEV_UNAVAILABLE$'):
                m.validate_protocol(raw, expected)

    def test_rights_hold_missing_permission_and_card_pin_fail_closed(self):
        m = module()
        manifest = json.loads((ROOT / 'docs/research/source-rights.json').read_text())
        protocol = json.loads(PROTOCOL.read_text())
        record = m.validate_rights(manifest, protocol)
        self.assertEqual(record['permissions']['commercial_training'], 'hold')
        for key in ('commercial_evaluation', 'raw_redistribution', 'product_use', 'commercial_training'):
            bad = copy.deepcopy(manifest)
            r = next(x for x in bad['sources'] if x['id'] == 'helpsteer2-candidates')
            r['permissions'].pop(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_rights(bad, protocol)
        bad = copy.deepcopy(manifest)
        next(x for x in bad['sources'] if x['id'] == record['id'])['license_evidence_sha'] = '0' * 40
        with self.assertRaises(ValueError):
            m.validate_rights(bad, protocol)

    def test_source_verification_reuses_source_and_rejects_tamper(self):
        m = module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fictional'
            path.write_bytes(b'synthetic bytes')
            pin = dict(bytes=15, sha256=sha256(path.read_bytes()).hexdigest())
            source = m._verify_file(path, pin, source_id='fixture', url='https://example.org/source')
            self.assertEqual(source.content_sha256, pin['sha256'])
            path.write_bytes(b'changed private data')
            with self.assertRaisesRegex(ValueError, '^HELPSTEER2_DEV_UNAVAILABLE$'):
                m._verify_file(path, pin, source_id='fixture', url='https://example.org/source')

    def test_local_model_missing_modified_extra_and_symlink_files_rejected(self):
        m = module()
        for edit in ('missing', 'modified', 'extra', 'symlink'):
            with self.subTest(edit=edit), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'model.safetensors'
                path.write_bytes(b'fictional weight bytes')
                pins = {path.name: dict(bytes=path.stat().st_size, sha256=sha256(path.read_bytes()).hexdigest())}
                m._verify_model(directory, pins)
                if edit == 'missing': path.unlink()
                if edit == 'modified': path.write_bytes(b'fictional altered byte')
                if edit == 'extra': (path.parent / 'remote_code.py').write_text('fictional')
                if edit == 'symlink':
                    path.rename(path.parent / 'target')
                    path.symlink_to(path.parent / 'target')
                with self.assertRaises(ValueError): m._verify_model(directory, pins)

    def test_invalid_local_configuration_never_imports_optional_packages(self):
        m = module()
        import builtins
        original = builtins.__import__
        imported = []
        def guarded(name, *args, **kwargs):
            if name.split('.')[0] in ('torch', 'transformers'):
                imported.append(name)
                raise AssertionError('optional import forbidden')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=guarded):
            for version, expected in (('working-tree', m.PROTOCOL_SHA256), (VERSION, '0' * 64),
                                      (VERSION, m.PROTOCOL_SHA256)):
                with self.assertRaisesRegex(ValueError, '^HELPSTEER2_DEV_UNAVAILABLE$'):
                    m.run_local(protocol_path=PROTOCOL, expected_sha256=expected,
                        data_dir='/nonexistent-fictional', model_dir='/nonexistent-fictional',
                        rights_path=ROOT / 'docs/research/source-rights.json', code_version=version)
        self.assertEqual(imported, [])

    def test_original_preference_sign_and_quality_provenance(self):
        cases = self.cases()
        self.assertEqual([c.human_choice for c in cases], [1, 2] * 4)
        self.assertEqual(cases[0].quality_rows, (1, 2))
        self.assertEqual(cases[0].quality_labels[0]['helpfulness'], 3)
        self.assertEqual(cases[0].semantic_split, 'train')

    def test_raw_split_semantic_split_and_zero_strength_rejected(self):
        for field, value in (('split', 'val'), ('split', 'validation'), ('preference_strength', 0),
                             ('preference_strength', True), ('preference_strength', 4)):
            p, q, s = fixture()
            p[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                module()._reconstruct_cases(s, p, q)

    def test_duplicate_extra_and_nondev_membership_rejected(self):
        for edit in ('duplicate', 'extra', 'missing', 'nondev'):
            p, q, s = fixture()
            if edit == 'duplicate': s[-1] = copy.deepcopy(s[0])
            if edit == 'extra': s.append(copy.deepcopy(s[0]))
            if edit == 'missing': s.pop()
            if edit == 'nondev': s[0]['native_preference_split'] = 'validation'
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                module()._reconstruct_cases(s, p, q)

    def test_modified_candidate_and_missing_or_nonunique_quality_rejected(self):
        for edit in ('prompt', 'response_1', 'missing_quality', 'duplicate_quality', 'quality_range'):
            p, q, s = fixture()
            if edit in ('prompt', 'response_1'): p[0][edit] += ' private'
            if edit == 'missing_quality': q.pop(0)
            if edit == 'duplicate_quality': q.append(copy.deepcopy(q[0]))
            if edit == 'quality_range': q[0]['helpfulness'] = 5
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                module()._reconstruct_cases(s, p, q)

    def test_mask_includes_eos_excludes_prompt_suffix_and_native_shift_count(self):
        result = module().completion_mask([10, 11], [10, 11, 12, 13, 151645, 99])
        self.assertEqual(result.labels, (-100, -100, 12, 13, 151645, -100))
        self.assertEqual(result.scored_tokens, 3)

    def test_user_turn_eos_is_masked_and_only_assistant_eos_counted(self):
        result = module().completion_mask([10, 151645, 11], [10, 151645, 11, 12, 151645, 99])
        self.assertEqual(result.labels, (-100, -100, -100, 12, 151645, -100))
        self.assertEqual(result.scored_tokens, 2)

    def test_fixed_length_drift_fails_without_any_model_call(self):
        calls = []
        def wrong_length(case):
            return (module().completion_mask([1], [1, 2, 151645]),) * 2
        result = module().evaluate_cases(self.cases(), wrong_length, lambda t: calls.append(t))
        self.assertEqual(calls, [])
        self.assertEqual(result['policies']['BASE_QWEN']['failed'], 1)
        self.assertEqual(result['policies']['SHORTER_CANDIDATE_RULE']['failed'], 8)

    def test_invalid_prefix_eos_length_and_token_types(self):
        for prefix, full in (([1], [2, 3, 151645]), ([], [1, 151645]),
                             ([1], [1, 2]), ([1], [1, 151645, 151645]),
                             ([1], [1] + [2] * 255 + [151645]),
                             ([1], [1, True, 151645]), ([151645], [151645, 2])):
            with self.subTest(full_length=len(full)), self.assertRaises(ValueError):
                module().completion_mask(prefix, full)

    def test_hash_ties_and_no_action_null_denominator(self):
        m = module()
        self.assertEqual(m._choose((2., 2.), ('b' * 64, 'a' * 64)), (2, True))
        result = m.evaluate_cases(self.cases(), encode, lambda tokens: 1.)
        no_action = result['policies']['NO_ACTION']
        self.assertEqual((no_action['assigned'], no_action['completed'], no_action['abstained']), (8, 8, 8))
        self.assertEqual(no_action['coverage'], 0)
        self.assertIsNone(no_action['conditional_accuracy'])
        self.assertIsNone(no_action['nll'])
        self.assertIsNone(result['policies']['SHORTER_CANDIDATE_RULE']['nll'])

    def test_partial_failures_preserve_attempts_unknown_and_denominators(self):
        m = module()
        calls = []
        def runner(tokens):
            calls.append(tokens)
            if len(calls) == 3: raise RuntimeError('fictional private failure')
            return 1.
        result = m.evaluate_cases(self.cases(), encode, runner)
        base = result['policies']['BASE_QWEN']
        self.assertEqual((base['assigned'], base['attempted'], base['completed'], base['failed'],
                          base['unattempted'], base['unknown']), (8, 2, 1, 1, 6, 0))
        self.assertEqual(base['coverage'], 1 / 8)
        self.assertEqual(result['model_requests'], dict(assigned=16, attempted=3, completed=2, failed=1,
                                                      unknown=0, unattempted=13))
        self.assertEqual(result['policies']['SHORTER_CANDIDATE_RULE']['completed'], 8)
        self.assertNotIn('fictional', json.dumps(result))

    def test_nonfinite_loss_fails_without_retry(self):
        result = module().evaluate_cases(self.cases(), encode, lambda t: float('nan'))
        self.assertEqual(result['policies']['BASE_QWEN']['failed'], 1)
        self.assertEqual(result['model_requests']['attempted'], 1)

    def test_checkpoint_marks_inflight_unknown_before_each_forward(self):
        snapshots = []
        def progress(result): snapshots.append(json.loads(json.dumps(result)))
        def loss(mask):
            last = snapshots[-1]
            self.assertEqual(last['model_requests']['unknown'], 1)
            self.assertEqual(last['policies']['BASE_QWEN']['unknown'], 1)
            self.assertEqual(last['policies']['BASE_QWEN']['groups'][0]['status'], 'UNKNOWN')
            raise RuntimeError('fictional private source')
        result = module().evaluate_cases(self.cases(), encode, loss, progress=progress)
        self.assertEqual(result['model_requests']['unknown'], 0)
        self.assertEqual(snapshots[-1], result)

    def test_export_rejects_raw_extra_fields_and_malformed_numeric_metadata(self):
        m = module()
        good = m.evaluate_cases(self.cases(), encode, lambda t: 1.)
        for mutate in ('top', 'row', 'numeric', 'hash'):
            bad = copy.deepcopy(good)
            row = bad['policies']['BASE_QWEN']['groups'][0]
            if mutate == 'top': bad['prompt'] = 'fictional private query'
            if mutate == 'row': row['response'] = 'fictional private response'
            if mutate == 'numeric': row['human_choice'] = 'fictional private label'
            if mutate == 'hash': row['prompt_sha256'] = 'fictional private query'
            with self.subTest(mutate=mutate), self.assertRaisesRegex(ValueError, '^HELPSTEER2_DEV_UNAVAILABLE$'):
                m.result_manifest(bad, code_version=VERSION)

    def test_metadata_privacy_no_promotion_and_immutable_version(self):
        m = module()
        cases = self.cases()
        self.assertNotIn('fictional', repr(cases))
        report = m.result_manifest(m.evaluate_cases(cases, encode, lambda t: 1.),
                                   code_version=VERSION)
        self.assertNotIn('fictional', json.dumps(report))
        self.assertFalse(report['can_execute'])
        self.assertEqual(report['proof_level'], 'P0')
        self.assertEqual(report['human_benefit'], 'NOT_MEASURED')
        for key in ('pressure', 'dependency', 'harms', 'behavior_change', 'new_response_human_quality'):
            self.assertIsNone(report[key])
        with self.assertRaises(ValueError): m.result_manifest({}, code_version='working-tree')

    def test_invalid_cli_initializes_zero_optional_models_and_static_errors(self):
        script = ROOT / 'scripts/evaluate_helpsteer2_dev.py'
        self.assertTrue(script.exists())
        spec = importlib.util.spec_from_file_location('helpsteer2_cli_test', script)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch.object(cli, 'run_local', side_effect=AssertionError('must not initialize')):
            with patch('builtins.print') as output:
                self.assertEqual(cli.main([]), 2)
            self.assertEqual(output.call_args.args, ('HELPSTEER2_DEV_UNAVAILABLE',))

    def test_cli_atomic_private_checkpoint_survives_simulated_interruption(self):
        m = module()
        spec = importlib.util.spec_from_file_location('helpsteer2_cli_checkpoint', ROOT / 'scripts/evaluate_helpsteer2_dev.py')
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        snapshots = []
        def interrupted_loss(mask): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            m.evaluate_cases(self.cases(), encode, interrupted_loss,
                             progress=lambda r: snapshots.append(json.loads(json.dumps(r))))
        report = m.result_manifest(snapshots[-1], code_version=VERSION)
        def interrupted_run(**kwargs):
            kwargs['progress'](report)
            print('fictional private diagnostics')
            raise KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'private.json'
            args = [arg for name, value in dict(protocol_path=str(PROTOCOL), expected_sha256=m.PROTOCOL_SHA256,
                data_dir=directory, model_dir=directory, rights_path=directory, code_version=VERSION,
                output=str(output)).items() for arg in ('--' + name.replace('_', '-'), value)]
            with patch.object(cli, 'run_local', side_effect=interrupted_run), redirect_stdout(io.StringIO()) as stdout:
                with self.assertRaises(KeyboardInterrupt): cli.main(args)
            self.assertEqual(stdout.getvalue(), '')
            self.assertEqual(json.loads(output.read_text())['model_requests']['unknown'], 1)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(directory).iterdir()), [output])


if __name__ == '__main__':
    unittest.main()
