"""Synthetic behavioral fixtures only; never import ML or read benchmark text."""
import builtins
import copy
import csv
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from hashlib import sha256
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROTOCOL = ROOT / 'experiments/behavior-model/xstest-qwen3guard-binary-protocol-v1.json'
RIGHTS = ROOT / 'docs/research/source-rights.json'
VERSION = 'a' * 40
LABELS = ('1_full_compliance', '2_full_refusal', '3_partial_refusal')


def module():
    assert importlib.util.find_spec('manager_core.xstest_binary_refusal_eval'), 'native binary adapter missing'
    return importlib.import_module('manager_core.xstest_binary_refusal_eval')


def cases(n=5):
    from manager_core.xstest_refusal_eval import _reconstruct_cases
    human = [dict(id=str(i), type='fictional', prompt=f'fictional question {i}',
        completion=f'fictional answer {i}', annotation_1=LABELS[i % 3],
        annotation_2=LABELS[i % 3], agreement='TRUE', final_label=LABELS[i % 3]) for i in range(n)]
    released = [dict(r, strmatch_label=LABELS[(i + 1) % 3]) for i, r in enumerate(human)]
    return _reconstruct_cases(human, released, expected_count=n)


def generation(label='Yes', safety='Safe', category='None', ids=(12, 151645)):
    return module().Generation(f'Safety: {safety}\nCategories: {category}\nRefusal: {label}', ids)


def cli_module():
    path = ROOT / 'scripts/evaluate_xstest_binary_refusal.py'
    assert path.is_file(), 'private binary CLI missing'
    spec = importlib.util.spec_from_file_location('binary_refusal_cli', path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def args():
    return [x for key in ('protocol-path', 'expected-sha256', 'data-dir', 'model-dir', 'rights-path', 'code-version')
            for x in ('--' + key, 'fictional')]


class BinaryRefusalTests(unittest.TestCase):
    def test_native_two_messages_preserve_text_without_host_gold(self):
        m = module()
        self.assertEqual(m.build_messages('fictional "question"\n', 'fictional answer'),
            [{'role': 'user', 'content': 'fictional "question"\n'}, {'role': 'assistant', 'content': 'fictional answer'}])
        with self.assertRaises(TypeError): m.build_messages('q', 'r', gold='Yes')

    def test_protocol_mutation_cannot_be_reauthorized_with_caller_hash(self):
        m = module()
        protocol = m.validate_protocol(PROTOCOL.read_bytes(), m.PROTOCOL_SHA256)
        self.assertEqual(protocol['assigned_rows'], 450)
        for key in ('native_template', 'parser', 'binary_target', 'computation', 'model_files', 'packages'):
            changed = dict(protocol, **{key: None})
            raw = json.dumps(changed).encode()
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_protocol(raw, sha256(raw).hexdigest())

    def test_parser_projects_only_refusal_and_accepts_native_categories(self):
        m = module()
        for label, safety, category in [('Yes', 'Safe', 'None'), ('No', 'Unsafe', 'Violent, PII'),
                                         ('Yes', 'Controversial', 'Copyright Violation,PII')]:
            status, prediction, fields = m.parse_generation(generation(label, safety, category))
            self.assertEqual((status, prediction), ('VALID', label))
            self.assertEqual(fields, {'safety': safety, 'categories': category.split(', ') if ', ' in category else category.split(','), 'refusal': label})
        g = generation('No')
        self.assertEqual(m.parse_generation(m.Generation(' \r\n' + g.text.replace('\n', '\r\n') + '\t', g.token_ids))[0], 'VALID')

    def test_parser_rejects_whole_schema_and_eos_errors(self):
        m = module()
        text = generation().text
        bad = [text + '\nexplanation', text.replace('Refusal:', 'Safety:'), text.replace('None', 'Unknown'),
               text.replace('None', 'Violent'), text.replace('Safe', 'Unsafe').replace('None', 'PII,PII'),
               text.replace('Safe', 'Unsafe').replace('None', 'PII,  Violent'), '"' + text + '"',
               text.replace('Yes', 'yes'), text.replace('\n', '\n\n', 1), text.replace('Safe', 'safe')]
        for value in bad:
            with self.subTest(value=value): self.assertEqual(m.parse_generation(m.Generation(value, (12, 151645))), ('INVALID_LABEL', None, None))
        for ids in [(), (12,), (151645, 12), (151645, 151643), (True, 151645)]:
            with self.subTest(ids=ids): self.assertEqual(m.parse_generation(m.Generation(text, ids)), ('INVALID_LABEL', None, None))
        self.assertEqual(m.parse_generation(m.Generation(text, tuple(range(128))))[0], 'LENGTH_LIMIT')
        self.assertEqual(m.parse_generation(m.Generation(text, tuple(range(128)) + (151645,)))[0], 'LENGTH_LIMIT')
        self.assertEqual(m.parse_generation(m.Generation(text, tuple(range(127)) + (151643,)))[0], 'VALID')

    def test_metrics_separate_partial_and_primary_with_null_denominators(self):
        m = module()
        cs = [replace(c, gold=g) for c, g in zip(cases(3), LABELS)]
        predictions = iter(['No', 'Yes', 'Yes'])
        result = m.evaluate_cases(cs, lambda c: (1,), lambda ids: generation(next(predictions)))
        base = result['policies']['QWEN3GUARD_NATIVE_BINARY']
        self.assertEqual((base['assigned'], base['primary_eligible'], base['primary_valid'], base['all_valid']), (3, 2, 2, 3))
        self.assertEqual(base['confusion'], [[1, 0], [0, 1]])
        self.assertEqual((base['conditional_agreement'], base['balanced_accuracy']), (1, 1))
        self.assertEqual(base['partial'], {'assigned': 1, 'Yes': 1, 'No': 0, 'nonvalid': 0})
        self.assertEqual(result['rows'][2]['eligibility'], 'GOLD_NOT_BINARY')
        self.assertIsNone(result['rows'][2]['binary_gold'])
        for cs in ((), [replace(cases(1)[0], gold=LABELS[2])]):
            base = m.evaluate_cases(cs, lambda c: (1,), lambda ids: generation())['policies']['QWEN3GUARD_NATIVE_BINARY']
            self.assertIsNone(base['conditional_agreement'])
            self.assertIsNone(base['primary_valid_coverage'])
            self.assertIsNone(base['balanced_accuracy'])
        one = m.evaluate_cases([replace(cases(1)[0], gold=LABELS[0])], lambda c: (1,), lambda ids: generation('Yes'))['policies']['QWEN3GUARD_NATIVE_BINARY']
        self.assertEqual(one['per_label']['No']['recall'], 0)
        self.assertIsNone(one['per_label']['Yes']['recall'])
        self.assertIsNone(one['balanced_accuracy'])

    def test_rule_full_matched_ids_and_paired_four_counts(self):
        m = module()
        cs = [replace(c, gold=LABELS[1], rule_label=r) for c, r in zip(cases(5), [LABELS[1], LABELS[0], LABELS[1], LABELS[0], LABELS[1]])]
        outputs = iter(['Yes', 'Yes', 'No', 'No', 'bad'])
        result = m.evaluate_cases(cs, lambda c: (1,), lambda ids: generation(next(outputs)))
        self.assertEqual(result['policies']['RELEASED_STRING_RULE']['primary_valid'], 5)
        self.assertEqual(result['rule_matched_model_valid']['primary_valid'], 4)
        self.assertEqual(result['paired']['counts'], {'both_correct': 1, 'new_only_correct': 1, 'rule_only_correct': 1, 'neither_correct': 1})
        self.assertEqual(result['paired']['agreement_difference_new_minus_rule'], 0)
        self.assertEqual(result['paired']['id_sha256'], [r['id_sha256'] for r in result['rows'][:4]])
        self.assertEqual(result['policies']['NO_ACTION']['statuses']['ABSTAIN'], 5)
        self.assertIsNone(result['policies']['NO_ACTION']['conditional_agreement'])

    def test_encode_overflow_counts_attempt_without_generation(self):
        m = module()
        cs = cases(2)
        result = m.evaluate_cases(cs, lambda c: range(3969 if c == cs[0] else 3968), lambda ids: generation('No'))
        base = result['policies']['QWEN3GUARD_NATIVE_BINARY']
        self.assertEqual((base['attempted'], base['generation_started'], base['generation_completed']), (2, 1, 1))
        self.assertEqual(result['rows'][0]['status'], 'CONTEXT_OVERFLOW')
        self.assertEqual(result['rows'][1]['input_tokens'], 3968)

    def test_encode_and_generation_fail_stop_and_durable_unknown(self):
        m = module()
        for phase in ('encode', 'generate'):
            snapshots = []
            def fail(*_): raise RuntimeError('fictional private failure')
            result = m.evaluate_cases(cases(3), fail if phase == 'encode' else lambda c: (1,),
                fail, progress=lambda r: snapshots.append(copy.deepcopy(r)))
            base = result['policies']['QWEN3GUARD_NATIVE_BINARY']
            self.assertEqual((base['attempted'], base['statuses']['FAILED'], base['statuses']['NOT_RUN']), (1, 1, 2))
            self.assertEqual(base['generation_started'], int(phase == 'generate'))
            self.assertEqual(snapshots[1]['rows'][0]['status'], 'UNKNOWN')
            self.assertTrue(snapshots[1]['rows'][0]['attempted'])
            m.result_manifest(result, code_version=VERSION)
        snapshots = []
        def interrupt(ids): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            m.evaluate_cases(cases(2), lambda c: (1,), interrupt, progress=lambda r: snapshots.append(r))
        self.assertEqual(snapshots[-1]['rows'][0]['stage'], 'GENERATING')
        self.assertTrue(snapshots[-1]['rows'][0]['generation_started'])
        m.result_manifest(snapshots[-1], code_version=VERSION)

    def test_manifest_private_audit_and_rejects_inconsistent_rows_metrics_pairing(self):
        m = module()
        result = m.evaluate_cases(cases(), lambda c: (1,), lambda ids: generation())
        report = m.result_manifest(result, code_version=VERSION)
        self.assertEqual(report['rows'][0]['raw_suffix'], generation().text)
        self.assertEqual(report['rows'][0]['token_ids'], [12, 151645])
        self.assertFalse(report['evaluation_contract']['can_execute'])
        self.assertNotIn('fictional question', json.dumps(report))
        for edit in ('metric', 'boolean_count', 'prediction', 'counter', 'paired', 'gold', 'membership', 'native', 'lane', 'extra'):
            bad = copy.deepcopy(result)
            if edit == 'metric': bad['policies']['QWEN3GUARD_NATIVE_BINARY']['conditional_agreement'] = 42
            if edit == 'boolean_count': bad['policies']['QWEN3GUARD_NATIVE_BINARY']['statuses']['FAILED'] = False
            if edit == 'prediction': bad['rows'][0]['prediction'] = 'No'
            if edit == 'counter': bad['rows'][0]['generation_started'] = False
            if edit == 'paired': bad['paired']['id_sha256'] = []
            if edit == 'gold': bad['rows'][0]['binary_gold'] = 'bad'
            if edit == 'membership': bad['rows'][0]['id_sha256'] = '0' * 64
            if edit == 'native': bad['rows'][0]['native_fields']['refusal'] = 'No'
            if edit == 'lane': bad['lane_status'] = 'NOT_RUN'
            if edit == 'extra': bad['rows'][0]['prompt'] = 'fictional private source'
            with self.subTest(edit=edit), self.assertRaises(ValueError): m.result_manifest(bad, code_version=VERSION)

    def test_checkpoint_before_optional_import_load_failure_keeps_all450_not_run(self):
        m, events = module(), []
        original = builtins.__import__
        protocol = json.loads(PROTOCOL.read_bytes())
        rights = next(r for r in json.loads(RIGHTS.read_bytes())['sources'] if r['id'] == protocol['rights_record_id'])
        def guarded(name, *a, **kw):
            if name.split('.')[0] in ('torch', 'transformers'):
                events.append('blocked import')
                raise RuntimeError('fictional diagnostics')
            return original(name, *a, **kw)
        with patch.object(m, 'load_verified_inputs', return_value=(protocol, rights, {}, cases(450))), patch('builtins.__import__', side_effect=guarded):
            result = m.run_local(code_version=VERSION, progress=lambda r: events.append(r))
        self.assertEqual(events[0]['policies']['QWEN3GUARD_NATIVE_BINARY']['statuses']['NOT_RUN'], 450)
        self.assertEqual(events[1], 'blocked import')
        self.assertEqual(result['lane_status'], 'FAILED')
        self.assertEqual(result['policies']['QWEN3GUARD_NATIVE_BINARY']['attempted'], 0)

    def test_invalid_configuration_rejects_before_optional_import(self):
        m = module()
        with self.assertRaises(ValueError):
            m.run_local(protocol_path=PROTOCOL, expected_sha256='0' * 64, data_dir='/missing', model_dir='/missing', rights_path=RIGHTS, code_version=VERSION)

    def test_verified_input_wiring_preserves_exact_membership_and_rejects_packages(self):
        m = module()
        protocol = json.loads(PROTOCOL.read_bytes())
        human = []
        for i in range(450):
            label = LABELS[0] if i < 374 else LABELS[1] if i < 423 else LABELS[2]
            human.append(dict(id=str(i), type='fictional', prompt=f'fictional query {i}',
                completion=f'fictional completion {i}', annotation_1=label,
                annotation_2=label, agreement='TRUE', final_label=label))
        released = [dict(r, strmatch_label=r['final_label']) for r in human]
        expected = m.source._reconstruct_cases(human, released)
        protocol['source_membership_sha256'] = m.source._membership_sha256(expected)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, model = root / 'data', root / 'model'
            data.mkdir()
            model.mkdir()
            for name, rows in zip(protocol['source_artifacts'], (human, released)):
                stream = io.StringIO(newline='')
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)
                payload = stream.getvalue().encode()
                path = data / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                protocol['source_artifacts'][name] = dict(bytes=len(payload), sha256=sha256(payload).hexdigest())
            for name in protocol['model_files']:
                payload = ('fictional asset ' + name).encode()
                (model / name).write_bytes(payload)
                protocol['model_files'][name] = dict(bytes=len(payload), sha256=sha256(payload).hexdigest())
            rights = json.loads(RIGHTS.read_bytes())
            record = next(r for r in rights['sources'] if r['id'] == protocol['rights_record_id'])
            record['artifact']['files'] = protocol['source_artifacts']
            rights_hash = sha256(m.source._canonical(record)).hexdigest()
            protocol['rights_record_sha256'] = rights_hash
            rights_path, protocol_path = root / 'rights.json', root / 'protocol.json'
            rights_path.write_text(json.dumps(rights))
            protocol_path.write_text(json.dumps(protocol))
            pin = sha256(protocol_path.read_bytes()).hexdigest()
            configuration = dict(protocol_path=protocol_path, expected_sha256=pin, data_dir=data,
                model_dir=model, rights_path=rights_path, code_version=VERSION)
            with patch.object(m, 'PROTOCOL_SHA256', pin), patch.object(m.source, '_RIGHTS_SHA256', rights_hash), \
                    patch.object(m.source.importlib.metadata, 'version', side_effect=protocol['packages'].__getitem__):
                loaded = m.load_verified_inputs(**configuration)
                self.assertEqual(loaded[3], expected)
                self.assertEqual(len(loaded[2]), 2)
                with patch.object(m.source.importlib.metadata, 'version', return_value='wrong'):
                    with self.assertRaises(ValueError): m.load_verified_inputs(**configuration)
                (data / next(iter(protocol['source_artifacts']))).write_bytes(b'fictional changed source')
                with self.assertRaises(ValueError): m.load_verified_inputs(**configuration)

    def test_malformed_generator_return_is_completed_failure_without_retry(self):
        m = module()
        for returned in (None, m.Generation('fictional malformed', (object(),))):
            result = m.evaluate_cases(cases(2), lambda c: (1,), lambda ids: returned)
            self.assertEqual(result['lane_status'], 'FAILED')
            self.assertEqual(result['rows'][0]['status'], 'FAILED')
            self.assertTrue(result['rows'][0]['generation_completed'])
            self.assertEqual(result['rows'][1]['status'], 'NOT_RUN')
            m.result_manifest(result, code_version=VERSION)

    def test_cli_private_atomic0600_metadata_only_native_silence(self):
        cli, snapshots = cli_module(), []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'private.json'
            private = dict(lane_status='RUNNING', code_version=VERSION, protocol_sha256='b' * 64, rows=[{'raw_suffix': 'fictional secret'}], policies={'aggregate': 1})
            def run(*, progress, **configuration):
                os.write(1, b'fictional native secret')
                os.write(2, b'fictional native secret')
                progress(private)
                snapshots.append((output.stat().st_mode & 0o777, json.loads(output.read_text())))
                return dict(private, lane_status='COMPLETED')
            with patch.object(cli, 'run_local', side_effect=run), redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(cli.main(args() + ['--output', str(output)]), 0)
            self.assertEqual(snapshots, [(0o600, private)])
            public = json.loads(stdout.getvalue())
            self.assertEqual(set(public), {'lane_status', 'code_version', 'protocol_sha256', 'policies'})
            self.assertNotIn('fictional', stdout.getvalue())
            self.assertEqual(json.loads(output.read_text())['rows'], private['rows'])
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_cli_rejects_missing_existing_symlink_and_parent_before_run(self):
        cli = cli_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / 'exists'
            existing.write_text('unchanged')
            link = root / 'link'
            link.symlink_to(existing)
            parent = root / 'parent'
            parent.symlink_to(root, target_is_directory=True)
            for tail in ([], ['--output', 'relative'], ['--output', str(existing)], ['--output', str(link)], ['--output', str(parent / 'new')], ['--help']):
                with self.subTest(tail=tail), patch.object(cli, 'run_local', side_effect=AssertionError('must not run')), redirect_stdout(io.StringIO()) as stdout:
                    self.assertEqual(cli.main(args() + tail), 2)
                    self.assertEqual(stdout.getvalue(), cli.UNAVAILABLE + '\n')
            self.assertEqual(existing.read_text(), 'unchanged')

    def test_cli_interrupt_keeps_private_unknown_without_exception(self):
        cli = cli_module()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'private.json'
            def run(*, progress, **configuration):
                progress({'status': 'UNKNOWN'})
                raise KeyboardInterrupt('fictional secret')
            with patch.object(cli, 'run_local', side_effect=run), redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(cli.main(args() + ['--output', str(output)]), 2)
            self.assertEqual(json.loads(output.read_text()), {'status': 'UNKNOWN'})
            self.assertEqual(stdout.getvalue(), cli.UNAVAILABLE + '\n')

    def test_standalone_cli_static_failures_and_no_abbreviations(self):
        script = ROOT / 'scripts/evaluate_xstest_binary_refusal.py'
        with tempfile.TemporaryDirectory() as directory:
            abbreviated = args() + ['--output', str(Path(directory) / 'new')]
            abbreviated[0] = '--protocol-p'
            for argv in ([], ['--help'], abbreviated):
                result = subprocess.run([sys.executable, str(script), *argv], capture_output=True, text=True)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                    (2, 'XSTEST_BINARY_REFUSAL_UNAVAILABLE\n', ''))


if __name__ == '__main__': unittest.main()
