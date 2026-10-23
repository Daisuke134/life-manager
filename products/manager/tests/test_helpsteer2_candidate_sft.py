"""Fictional data and native boundary fakes only; never imports an ML package."""
import copy
import gzip
from hashlib import sha256
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json'
MANIFEST = ROOT / 'experiments/behavior-model/helpsteer2-train27-manifest-v1.json'
VERSION = 'a' * 40


def module():
    assert importlib.util.find_spec('manager_core.helpsteer2_candidate_sft'), 'native SFT entry missing'
    return importlib.import_module('manager_core.helpsteer2_candidate_sft')


def digest(value):
    return sha256(value.encode()).hexdigest()


def fixture():
    """27 selected fictional pairs plus distinct metadata-only dev/final membership."""
    prefs, quality = {}, {}
    manifest = dict(train27=[], development8=[], final16=[],
        excluded_train_preference_rows_1based=list(range(60, 65)),
        exposure=dict(final_content_qc_exposed=True, fully_blind_or_pristine=False,
            final_model_scoring='NOT_RUN_PER_RECORDED_METADATA',
            final_optimizer_use='NOT_RUN_PER_RECORDED_METADATA',
            paraphrase_pretraining_contamination='UNKNOWN'))
    for n in range(1, 52):
        prompt, a, b = f'fictional query {n}', f'fictional first {n}', f'fictional second {n}'
        strength = -1 if n % 2 else 2
        spec = dict(source_preference_row_1based=n, raw_preference_split='train' if n <= 35 else 'val',
            native_split='train' if n <= 35 else 'validation',
            proposed_split='train' if n <= 27 else 'dev' if n <= 35 else 'final_test',
            quality_rows_1based=[2*n-1, 2*n], prompt_exact_sha256=digest(prompt),
            prompt_canonical_sha256=digest(prompt), response_exact_sha256=[digest(a), digest(b)],
            response_canonical_sha256=[digest(a), digest(b)], full_sequence_token_counts=[6, 6],
            completion_mask_token_lengths_by_candidate=[2, 2])
        if n <= 27:
            spec.update(preference_strength=strength, human_choice=1 if strength < 0 else 2,
                chosen_original_response_sha256=digest(a if strength < 0 else b))
            prefs[n] = dict(prompt=prompt, response_1=a, response_2=b, split='train',
                            preference_strength=strength)
            for index, response in zip(spec['quality_rows_1based'], (a, b)):
                quality[index] = dict(prompt=prompt, response=response, helpfulness=3, correctness=4,
                    coherence=4, complexity=1, verbosity=2)
        manifest['train27' if n <= 27 else 'development8' if n <= 35 else 'final16'].append(spec)
    return manifest, prefs, quality


class Tokenizer:
    def __init__(self, full=None, prefix=None):
        self.calls = []
        self.full = [1, 2, 3, 4, 5, 151645] if full is None else full
        self.prefix = [1, 2, 3, 4] if prefix is None else prefix

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.prefix if len(messages) == 1 else self.full


class SFTInputsTests(unittest.TestCase):
    def test_builtin_protocol_rejects_caller_reapproval(self):
        m = module()
        protocol = m.validate_protocol(PROTOCOL.read_bytes(), m.PROTOCOL_SHA256)
        self.assertEqual(protocol['recipe']['training']['expected_optimizer_opportunities'], 7)
        self.assertEqual(m.PROTOCOL_SHA256, 'eb2e585321d954d507af52b1bf71db9eb3b7ae3150273484909b6aeeae48a53d')
        for raw, expected in ((b'{}', digest('{}')), (PROTOCOL.read_bytes(), '0'*64),
                               (PROTOCOL.read_bytes()+b' ', m.PROTOCOL_SHA256)):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                m.validate_protocol(raw, expected)

    def test_pinned_rights_record_is_purpose_specific(self):
        m = module()
        protocol = json.loads(PROTOCOL.read_bytes())
        rights = json.loads((ROOT / 'docs/research/source-rights.json').read_bytes())
        record = m.validate_rights(rights, protocol)
        self.assertEqual(record['id'], 'helpsteer2-private-exploratory-sft-train27-v1')
        for mutate in ('permission', 'missing', 'duplicate'):
            bad = copy.deepcopy(rights)
            selected = next(x for x in bad['sources'] if x['id'] == record['id'])
            if mutate == 'permission': selected['permissions']['private_exploratory_sft'] = 'hold'
            if mutate == 'missing': bad['sources'].remove(selected)
            if mutate == 'duplicate': bad['sources'].append(selected)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                m.validate_rights(bad, protocol)

    def test_selected_original_gold_and_54_quality_joins(self):
        manifest, prefs, quality = fixture()
        cases = module().reconstruct_cases(manifest, prefs, quality)
        self.assertEqual(len(cases), 27)
        self.assertEqual([c.human_choice for c in cases], [1,2]*13+[1])
        self.assertEqual(cases[0].quality_rows, (1,2))
        self.assertNotIn('fictional', repr(cases))

    def test_membership_choice_split_hash_quality_and_isolation_fail_closed(self):
        for edit in ('choice', 'zero', 'bool', 'split', 'text', 'quality', 'join', 'duplicate',
                     'canonical', 'dev_overlap', 'final_overlap', 'excluded', 'exposure'):
            manifest, prefs, quality = fixture()
            s = manifest['train27'][0]
            if edit == 'choice': s['human_choice'] = 2
            if edit == 'zero': prefs[1]['preference_strength'] = 0
            if edit == 'bool': prefs[1]['preference_strength'] = True
            if edit == 'split': prefs[1]['split'] = 'val'
            if edit == 'text': prefs[1]['response_1'] += ' alteration'
            if edit == 'quality': quality[1]['correctness'] = 5
            if edit == 'join': quality[1]['response'] = quality[2]['response']
            if edit == 'duplicate': manifest['train27'][1] = copy.deepcopy(s)
            if edit == 'canonical': s['prompt_canonical_sha256'] = '0'*64
            if edit == 'dev_overlap': manifest['development8'][0]['response_exact_sha256'][0] = s['response_exact_sha256'][0]
            if edit == 'final_overlap': manifest['final16'][0]['prompt_canonical_sha256'] = s['prompt_canonical_sha256']
            if edit == 'excluded': manifest['excluded_train_preference_rows_1based'][0] = 1
            if edit == 'exposure': manifest['exposure']['fully_blind_or_pristine'] = True
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                module().reconstruct_cases(manifest, prefs, quality)

    def test_parse_only_selected_lines_and_reverify_bytes(self):
        m = module()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'fictional.gz'
            path.write_bytes(gzip.compress(b'not-json-unselected\n{"selected":true}\n{bad final labels}\n'))
            source = m._verify_file(path, dict(bytes=path.stat().st_size,
                sha256=sha256(path.read_bytes()).hexdigest()), source_id='fixture', url='https://example.org/source')
            self.assertEqual(m.read_selected_rows(path, source, {2}, expected_lines=3), {2:{'selected':True}})
            with self.assertRaises(ValueError): m.read_selected_rows(path, source, {1}, expected_lines=3)
            with self.assertRaises(ValueError): m.read_selected_rows(path, source, {2}, expected_lines=4)
            path.write_bytes(gzip.compress(b'{"selected":false}\n'))
            with self.assertRaises(ValueError): m.read_selected_rows(path, source, {1}, expected_lines=1)

    def test_invalid_preimport_never_imports_optional_ml(self):
        import builtins
        m = module()
        imported = []
        original = builtins.__import__
        def guard(name, *args, **kwargs):
            if name.split('.')[0] in ('torch','transformers','peft','trl','datasets','accelerate','safetensors'):
                imported.append(name)
                raise AssertionError('ML import forbidden')
            return original(name,*args,**kwargs)
        with patch('builtins.__import__', side_effect=guard):
            with self.assertRaisesRegex(ValueError, '^HELPSTEER2_SFT_UNAVAILABLE$'):
                m.run_local(protocol_path=PROTOCOL, expected_sha256=m.PROTOCOL_SHA256,
                    manifest_path=MANIFEST, data_dir='/nonexistent', model_dir='/nonexistent',
                    rights_path=ROOT/'docs/research/source-rights.json', code_version=VERSION,
                    execution_config_path='/nonexistent', adapter_dir='/nonexistent')
        self.assertEqual(imported, [])

    def test_chosen_only_native_template_and_exact_masks(self):
        m = module()
        cases = m.reconstruct_cases(*fixture())
        for case in (cases[0], cases[1]):
            tok = Tokenizer()
            example = m.build_selected_example(case, tok)
            self.assertEqual(set(example), {'input_ids','completion_mask'})
            self.assertEqual(example['completion_mask'], [0,0,0,0,1,1])
            self.assertEqual(tok.calls[1][0][-1]['content'], case.responses[case.human_choice-1])
            for _, kwargs in tok.calls:
                self.assertEqual({k:kwargs[k] for k in ('tokenize','enable_thinking','truncation')},
                    dict(tokenize=True,enable_thinking=False,truncation=False))
            self.assertTrue(tok.calls[0][1]['add_generation_prompt'])
            self.assertFalse(tok.calls[1][1]['add_generation_prompt'])

    def test_prefix_eos_length_recorded_counts_and_post_eos(self):
        m = module()
        case = m.reconstruct_cases(*fixture())[0]
        for tok in (Tokenizer(prefix=[9]), Tokenizer(full=[1,2,3,4,5,6]),
                    Tokenizer(full=[1,2,3,4,151645,151645]),
                    Tokenizer(full=[1,2,3,4]+[5]*252+[151645]),
                    Tokenizer(full=[1,2,3,4,5,6,151645])):
            with self.assertRaises(ValueError): m.build_selected_example(case,tok)
        case = copy.copy(case)
        object.__setattr__(case, 'full_sequence_token_counts', (7,7))
        example = m.build_selected_example(case, Tokenizer(full=[1,2,3,4,5,151645,10]))
        self.assertEqual(example['completion_mask'], [0,0,0,0,1,1,0])
        mask = m.completion_mask([1], [1]+[2]*254+[151645])
        self.assertEqual(len(mask.input_ids),256)

    def test_native_recipe_one_epoch_no_repeats_and_tail(self):
        m = module()
        protocol = json.loads(PROTOCOL.read_bytes())
        cfg = m.native_sft_kwargs(protocol, '/fictional-private-output')
        self.assertEqual((cfg['num_train_epochs'],cfg['max_steps'],cfg['gradient_accumulation_steps']), (1,-1,4))
        self.assertEqual(cfg['dataset_kwargs'], {'skip_prepare_dataset':True})
        self.assertEqual(cfg['completion_only_loss'],True)
        for key in ('assistant_only_loss','packing','padding_free','dataloader_drop_last'):
            self.assertIs(cfg[key],False)
        self.assertNotIn('expected_optimizer_opportunities',cfg)
        self.assertNotIn('sampler',cfg)
        self.assertEqual(m.planned_windows(27,4), (4,4,4,4,4,4,3))
        self.assertEqual(cfg['loss_type'],'nll')
        bad = copy.deepcopy(protocol)
        bad['recipe']['training']['max_steps'] = 8
        with self.assertRaises(ValueError): m.native_sft_kwargs(bad,'/fictional')


class SFTLifecycleTests(unittest.TestCase):
    def observer(self, progress=None):
        return module().Lifecycle(progress=progress, code_version=VERSION)

    def complete_training(self, observer, skipped=None):
        observer.observe('TRAIN_BEGIN',global_step=0)
        for step, window in enumerate((4,4,4,4,4,4,3)):
            observer.observe('STEP_BEGIN',global_step=step)
            for _ in range(window-1): observer.observe('SUBSTEP_END',global_step=step)
            observer.observe('PRE_OPTIMIZER_STEP',global_step=step,finite_gradients=True)
            observer.observe('OPTIMIZER_STEP_RETURNED',global_step=step,step_was_skipped=skipped)
            observer.observe('STEP_END',global_step=step+1)
        observer.observe('TRAIN_RETURNED',global_step=7)

    def test_lifecycle_known_lower_bounds_and_no_callback_only_completion(self):
        seen=[]
        obs=self.observer(lambda report:seen.append(copy.deepcopy(report)))
        self.complete_training(obs, skipped=True)
        receipt=obs.snapshot()
        self.assertEqual(receipt['optimizer_opportunities_observed'],7)
        self.assertEqual(receipt['optimizer_step_returns_observed'],7)
        self.assertEqual(receipt['optimizer_skips_observed'],7)
        self.assertEqual(receipt['backward_microbatches_completed_lower_bound'],27)
        self.assertEqual(receipt['status'],'IN_PROGRESS')
        self.assertIsNone(receipt['changed_adapter_tensors'])
        self.assertEqual(receipt['actual_consumed_row_order'],'NOT_OBSERVED')
        self.assertTrue(all('fictional' not in json.dumps(r) for r in seen))

    def test_preoptimizer_failure_and_optimizer_exception_keep_unknown(self):
        obs=self.observer()
        obs.observe('TRAIN_BEGIN',global_step=0)
        obs.observe('STEP_BEGIN',global_step=0)
        obs.observe('SUBSTEP_END',global_step=0)
        with self.assertRaises(ValueError):
            obs.observe('PRE_OPTIMIZER_STEP',global_step=0,finite_gradients=False)
        obs.fail()
        receipt=obs.snapshot()
        self.assertEqual(receipt['status'],'FAILED')
        self.assertTrue(receipt['backward_may_have_begun'])
        self.assertEqual(receipt['optimizer_step_returns_observed'],0)
        obs=self.observer()
        obs.observe('TRAIN_BEGIN',global_step=0)
        obs.observe('STEP_BEGIN',global_step=0)
        obs.observe('PRE_OPTIMIZER_STEP',global_step=0,finite_gradients=True)
        obs.fail()
        self.assertEqual(obs.snapshot()['optimizer_opportunities_observed'],1)
        self.assertEqual(obs.snapshot()['optimizer_step_returns_observed'],0)
        self.assertIsNone(obs.snapshot()['changed_adapter_tensors'])

    def test_step_counter_is_not_parameter_change_or_skip_proof(self):
        obs=self.observer()
        self.complete_training(obs)
        r=obs.snapshot()
        self.assertEqual(r['global_step'],7)
        self.assertEqual(r['optimizer_skip_unknown_returns'],7)
        self.assertIsNone(r['changed_adapter_tensors'])
        self.assertEqual(r['base_numeric_in_memory_unchanged'],'NOT_MEASURED')
        with self.assertRaises(ValueError): obs.freeze(inventory={},changed_adapter_tensors=0)

    def test_save_failure_and_no_change_negative_result(self):
        obs=self.observer()
        self.complete_training(obs)
        obs.observe('SAVE_STARTED')
        obs.fail()
        self.assertEqual(obs.snapshot()['status'],'FAILED')
        obs=self.observer()
        self.complete_training(obs)
        obs.observe('SAVE_STARTED')
        obs.observe('SAVE_RETURNED')
        obs.freeze(inventory={name:{'sha256':'0'*64,'bytes':1} for name in module().REQUIRED_NATIVE_FILES},changed_adapter_tensors=0)
        r=obs.snapshot()
        self.assertEqual(r['status'],'COMPLETED')
        self.assertEqual(r['parameter_change'],'NO_CHANGE_OBSERVED')
        self.assertEqual(r['changed_adapter_tensors'],0)

    def test_partial_train_return_and_writer_fault_never_complete(self):
        obs=self.observer()
        obs.observe('TRAIN_BEGIN',global_step=0)
        with self.assertRaises(ValueError): obs.observe('TRAIN_RETURNED',global_step=0)
        def broken(_): raise OSError('private raw error')
        with self.assertRaises(OSError): self.observer(broken)

    def test_optimizer_membership_exact_no_duplicates_or_base(self):
        m=module()
        a,b,base=object(),object(),object()
        m.verify_optimizer_membership({'a':a,'b':b},SimpleNamespace(param_groups=[{'params':[a,b]}]))
        for params in ([a],[a,b,b],[a,b,base]):
            with self.assertRaises(ValueError):
                m.verify_optimizer_membership({'a':a,'b':b},SimpleNamespace(param_groups=[{'params':params}]))


class SFTPrivatePathsTests(unittest.TestCase):
    def test_atomic_private_checkpoint_and_adapter_no_overwrite(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            writer=m.PrivateCheckpoint(root/'receipt.json')
            writer({'status':'NOT_RUN'})
            writer({'status':'IN_PROGRESS'})
            self.assertEqual(json.loads((root/'receipt.json').read_text())['status'],'IN_PROGRESS')
            self.assertEqual(stat.S_IMODE((root/'receipt.json').stat().st_mode),0o600)
            with self.assertRaises(ValueError): m.PrivateCheckpoint(root/'receipt.json')
            m.create_adapter_dir(root/'adapter')
            self.assertEqual(stat.S_IMODE((root/'adapter').stat().st_mode),0o700)
            with self.assertRaises(ValueError): m.create_adapter_dir(root/'adapter')
            link=root/'link'
            link.symlink_to(root,target_is_directory=True)
            for path in (Path('relative'),link/'receipt2.json'):
                with self.assertRaises(ValueError): m.PrivateCheckpoint(path)

    def test_inventory_actual_files_permissions_fsync_and_partial_reject(self):
        m=module()
        names=('adapter_model.safetensors','adapter_config.json','tokenizer.json','tokenizer_config.json','training_args.bin')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name in names:
                (root/name).write_bytes(b'fictional-native-save')
            inventory=m.freeze_inventory(root)
            self.assertEqual(set(inventory),set(names))
            self.assertTrue(all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in root.iterdir()))
            (root/'training_args.bin').unlink()
            with self.assertRaises(ValueError): m.freeze_inventory(root)
            (root/'training_args.bin').symlink_to(root/'tokenizer.json')
            with self.assertRaises(ValueError): m.freeze_inventory(root)

    def test_cli_static_error_and_required_paths(self):
        spec=importlib.util.spec_from_file_location('train_sft_cli',ROOT/'scripts/train_helpsteer2_candidate_sft.py')
        self.assertIsNotNone(spec)
        self.assertTrue(spec.origin and Path(spec.origin).is_file(),'training CLI missing')
        cli=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        output=io.StringIO()
        with redirect_stdout(output): status=cli.main(['--help'])
        self.assertEqual(status,2)
        self.assertEqual(output.getvalue(),'HELPSTEER2_SFT_UNAVAILABLE\n')


class SFTExecutionBindingTests(unittest.TestCase):
    def config_fixture(self, root):
        m = module()
        evidence = root/'accepted-metadata.json'
        evidence.write_text('{"fixture":"synthetic operator assertion, no runtime authority"}')
        evidence.chmod(0o400)
        pin = dict(path=str(evidence),sha256=sha256(evidence.read_bytes()).hexdigest())
        self.input_paths=dict(protocol_path=str(PROTOCOL),manifest_path=str(MANIFEST),
            data_dir=str(root),model_dir=str(root),rights_path=str(ROOT/'docs/research/source-rights.json'))
        config = dict(input_paths=dict(self.input_paths),adapter_dir=str(root/'adapter'),output=str(root/'output.json'),
            kind='manager.helpsteer2-private-sft-execution.v1',
            acceptance_status='ACCEPTED_ONE_OFFLINE_TRAINING_ATTEMPT',can_execute=False,
            scientific_protocol_sha256=m.PROTOCOL_SHA256,manifest_sha256=m.MANIFEST_SHA256,
            rights_record_sha256=m.RIGHTS_SHA256,code_version=VERSION,cwd=str(ROOT),
            max_cumulative_wall_seconds=900,max_process_group_rss_bytes=6442450944,
            accepted_gates=['G0','G1','G2','G3','G4','G5','G6'],
            source_files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in m.SOURCE_FILES},
            acceptance_evidence={name:dict(pin) for name in m.EVIDENCE_KEYS},watchdog=dict(pin))
        path = root/'execution.json'
        return config,path

    def write_config(self, path, config):
        if path.exists(): path.chmod(0o600)
        path.write_text(json.dumps(config))
        path.chmod(0o400)

    def test_execution_config_accepts_file_bindings_without_claiming_remote_authority(self):
        m = module()
        protocol=json.loads(PROTOCOL.read_bytes())
        with tempfile.TemporaryDirectory() as td:
            config,path=self.config_fixture(Path(td))
            self.write_config(path,config)
            verified=m.validate_execution_config(path,protocol=protocol,code_version=VERSION,input_paths=self.input_paths)
            self.assertFalse(verified['can_execute'])
            self.assertEqual(verified['acceptance_evidence']['G0'],verified['acceptance_evidence']['G6'])

    def test_missing_gate_hash_source_status_mode_cwd_evidence_fail_closed(self):
        m=module()
        protocol=json.loads(PROTOCOL.read_bytes())
        for edit in ('status','gate','protocol','manifest','rights','version','cwd','source',
                     'source_missing','source_extra','evidence','evidence_missing','watchdog',
                     'writable','production','budget','rss','circular','input_path'):
            with self.subTest(edit=edit),tempfile.TemporaryDirectory() as td:
                config,path=self.config_fixture(Path(td))
                if edit=='status': config['acceptance_status']='PENDING'
                if edit=='gate': config['accepted_gates'].pop()
                if edit=='protocol': config['scientific_protocol_sha256']='0'*64
                if edit=='manifest': config['manifest_sha256']='0'*64
                if edit=='rights': config['rights_record_sha256']='0'*64
                if edit=='version': config['code_version']='b'*40
                if edit=='cwd': config['cwd']=str(Path(td))
                if edit=='source': config['source_files'][next(iter(m.SOURCE_FILES))]='0'*64
                if edit=='source_missing': config['source_files'].pop(next(iter(m.SOURCE_FILES)))
                if edit=='source_extra': config['source_files']['unreviewed.py']='0'*64
                if edit=='evidence': config['acceptance_evidence']['official_ci']['sha256']='0'*64
                if edit=='evidence_missing': config['acceptance_evidence'].pop('G6')
                if edit=='watchdog': config['watchdog']['path']=str(Path(td)/'missing')
                if edit=='production': config['can_execute']=True
                if edit=='budget': config['max_cumulative_wall_seconds']=901
                if edit=='rss': config['max_process_group_rss_bytes']=6442450945
                if edit=='input_path': config['input_paths']['data_dir']=str(ROOT)
                if edit=='circular': config['watchdog']['path']=str(path)
                self.write_config(path,config)
                if edit=='writable': path.chmod(0o600)
                with self.assertRaises((ValueError,KeyError,FileNotFoundError)):
                    m.validate_execution_config(path,protocol=protocol,code_version=VERSION,input_paths=self.input_paths)

    def test_package_versions_metadata_checked_without_import(self):
        m=module()
        protocol=json.loads(PROTOCOL.read_bytes())
        seen=[]
        def version(name):
            seen.append(name)
            return protocol['packages'][name]
        with patch.object(m.importlib.metadata,'version',side_effect=version):
            m.verify_package_versions(protocol)
        self.assertEqual(set(seen),set(protocol['packages']))
        with patch.object(m.importlib.metadata,'version',return_value='unaccepted-version'):
            with self.assertRaises(ValueError): m.verify_package_versions(protocol)

    def test_callback_order_and_unknown_progress_cannot_create_complete_artifact(self):
        m=module()
        for event in ('STEP_BEGIN','SUBSTEP_END','PRE_OPTIMIZER_STEP','OPTIMIZER_STEP_RETURNED','STEP_END','SAVE_STARTED'):
            obs=m.Lifecycle(progress=None,code_version=VERSION)
            with self.subTest(event=event),self.assertRaises(ValueError): obs.observe(event,global_step=0)
        obs=m.Lifecycle(progress=None,code_version=VERSION)
        obs.observe('TRAIN_BEGIN',global_step=0)
        with self.assertRaises(ValueError): obs.observe('TRAIN_BEGIN',global_step=0)

    def test_inventory_rejects_unexpected_and_empty_native_files(self):
        m=module()
        for kind in ('empty','unexpected'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                root=Path(td)
                for name in m.REQUIRED_NATIVE_FILES: (root/name).write_bytes(b'fictional-native-save')
                if kind=='empty': (root/'training_args.bin').write_bytes(b'')
                if kind=='unexpected': (root/'raw-private-prompts.txt').write_bytes(b'fictional')
                with self.assertRaises(ValueError): m.freeze_inventory(root)

    def test_fsync_fault_preserves_prior_durable_observation(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'receipt.json'
            writer=m.PrivateCheckpoint(path)
            writer({'status':'IN_PROGRESS','event':'SAVE_STARTED'})
            with patch.object(m.os,'fsync',side_effect=OSError('synthetic private I/O error')):
                with self.assertRaises(OSError): writer({'status':'COMPLETED','event':'ARTIFACT_FROZEN'})
            self.assertEqual(json.loads(path.read_text())['event'],'SAVE_STARTED')

    def test_initial_checkpoint_rejects_unvalidated_code_metadata(self):
        m=module()
        observed=[]
        for version in ('private source text', 'working-tree', None, 'A'*40):
            with self.subTest(version=version),self.assertRaises(ValueError):
                m.Lifecycle(progress=observed.append,code_version=version)
        self.assertEqual(observed,[])

    def test_invalid_adapter_path_fails_before_input_loading(self):
        m=module()
        with patch.object(m,'load_verified_inputs') as load:
            with self.assertRaisesRegex(ValueError,'^HELPSTEER2_SFT_UNAVAILABLE$'):
                m.run_local(code_version=VERSION,adapter_dir='relative')
        load.assert_not_called()

    def test_saved_native_config_preserves_recipe_and_base_binding(self):
        m=module()
        good=dict(r=8,lora_alpha=8,lora_dropout=0.0,target_modules=['q_proj','v_proj'],
            bias='none',task_type='CAUSAL_LM',inference_mode=True,peft_type='LORA',
            init_lora_weights=True,modules_to_save=None,base_model_name_or_path='/fictional/base')
        m.validate_saved_config(good,'/fictional/base')
        for key,value in (('r',16),('lora_alpha',16),('target_modules',['q_proj']),
            ('inference_mode',False),('modules_to_save',['lm_head']),('init_lora_weights',False),
            ('base_model_name_or_path','/different/base')):
            bad=dict(good)
            bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                m.validate_saved_config(bad,'/fictional/base')

    def test_execution_output_destinations_are_fixed_private_and_canonical(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            config=dict(adapter_dir=str(root/'adapter'),output=str(root/'output.json'))
            m.validate_execution_paths(config,adapter_dir=root/'adapter',metadata_output_path=root/'output.json')
            for adapter,output in ((root/'different',root/'output.json'),(root/'adapter',root/'different.json')):
                with self.assertRaises(ValueError):
                    m.validate_execution_paths(config,adapter_dir=adapter,metadata_output_path=output)
            link=root/'linked'
            link.symlink_to(root,target_is_directory=True)
            with self.assertRaises(ValueError):
                m.validate_execution_paths(config,adapter_dir=link/'adapter',metadata_output_path=root/'output.json')
            with self.assertRaises(ValueError):
                m.validate_execution_paths(config,adapter_dir=str(root)+'/../'+root.name+'/adapter',
                    metadata_output_path=root/'output.json')

    def test_run_checkpoint_precedes_load_and_native_boundary_failure_remains_failed(self):
        m=module()
        observed=[]
        protocol=json.loads(PROTOCOL.read_bytes())
        rights={'attribution':{'creators':['fictional']}}
        cases=m.reconstruct_cases(*fixture())
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            external=root/'execution.json'
            external.write_text('synthetic')
            def load(**configuration):
                self.assertEqual(observed[0]['event'],'PREIMPORT')
                return protocol,rights,{},cases,dict(adapter_dir=str(root/'adapter'),output=str(root/'receipt.json'))
            def native(*args):
                self.assertEqual(observed[-1]['event'],'IMPORT_LOAD_START')
                raise RuntimeError('fictional private source text must not escape')
            with patch.object(m,'load_verified_inputs',side_effect=load),patch.object(m,'_native_train',side_effect=native):
                with self.assertRaisesRegex(ValueError,'^HELPSTEER2_SFT_UNAVAILABLE$'):
                    m.run_local(progress=lambda r:observed.append(r),code_version=VERSION,
                        metadata_output_path=root/'receipt.json',adapter_dir=root/'adapter',
                        model_dir=root/'model',execution_config_path=external)
            self.assertEqual(observed[-1]['status'],'FAILED')
            self.assertNotIn('fictional private source text',json.dumps(observed))


class SFTCheckpointPostReplaceFaultTests(unittest.TestCase):
    def test_post_replace_failure_updates_owner_and_allows_failed_recovery(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'receipt.json'
            writer=m.PrivateCheckpoint(path)
            writer({'status':'IN_PROGRESS','event':'SAVE_RETURNED'})
            with patch.object(m,'_fsync_directory',side_effect=OSError('synthetic directory fsync fault')):
                with self.assertRaises(OSError):
                    writer({'status':'COMPLETED','event':'ARTIFACT_FROZEN'})
            current=path.stat()
            self.assertEqual(writer.inode,(current.st_dev,current.st_ino))
            self.assertFalse(writer.durability_confirmed)
            writer({'status':'FAILED','event':'FAILED'})
            self.assertTrue(writer.durability_confirmed)
            self.assertEqual(json.loads(path.read_text())['status'],'FAILED')

    def test_initial_publication_directory_failure_also_retains_owned_inode(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'receipt.json'
            writer=m.PrivateCheckpoint(path)
            with patch.object(m,'_fsync_directory',side_effect=OSError('synthetic directory fsync fault')):
                with self.assertRaises(OSError): writer({'status':'NOT_RUN','event':'PREIMPORT'})
            writer({'status':'FAILED','event':'FAILED'})
            self.assertEqual(json.loads(path.read_text())['status'],'FAILED')

    def test_unconfirmed_completion_invalidation_preserves_a_foreign_inode(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);path=root/'receipt.json'
            writer=m.PrivateCheckpoint(path)
            writer({'status':'IN_PROGRESS','event':'SAVE_RETURNED'})
            with patch.object(m,'_fsync_directory',side_effect=OSError('synthetic post-replace fault')):
                with self.assertRaises(OSError): writer({'status':'COMPLETED','event':'ARTIFACT_FROZEN'})
            foreign=root/'foreign.json';foreign.write_text('{"owner":"foreign"}');foreign.chmod(0o600)
            os.replace(foreign,path)
            with self.assertRaises(ValueError): writer.discard_unconfirmed_completion()
            self.assertEqual(json.loads(path.read_text()),{'owner':'foreign'})

    def run_cli_fault(self, kind):
        m=module()
        spec=importlib.util.spec_from_file_location('sft_post_replace_fault_cli',ROOT/'scripts/train_helpsteer2_candidate_sft.py')
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        protocol=json.loads(PROTOCOL.read_bytes())
        cases=m.reconstruct_cases(*fixture())
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            output=root/'receipt.json';adapter=root/'adapter';external=root/'execution.json'
            external.write_text('synthetic boundary assertion, no native execution authority')
            config=dict(adapter_dir=str(adapter),output=str(output))
            state=dict(armed=False,directory_failures=0)
            real_dir_fsync=m._fsync_directory
            real_fsync=m.os.fsync
            def dir_fsync(path):
                if output.exists() and json.loads(output.read_text())['status']=='COMPLETED': state['armed']=True
                if state['armed']:
                    state['directory_failures']+=1
                    if kind!='transient' or state['directory_failures']==1:
                        raise OSError('synthetic post-replace directory fsync failure')
                return real_dir_fsync(path)
            def file_fsync(fd):
                if kind=='persistent_all_fsync' and state['armed']:
                    raise OSError('synthetic failure-record file fsync failure')
                return real_fsync(fd)
            def native(protocol,cases,model_dir,adapter_dir,observer):
                SFTLifecycleTests().complete_training(observer)
                observer.observe('SAVE_STARTED')
                observer.observe('SAVE_RETURNED')
                observer.freeze(inventory={name:{'bytes':1,'sha256':'0'*64} for name in m.REQUIRED_NATIVE_FILES},
                    changed_adapter_tensors=0)
            argv=[]
            for name,value in dict(protocol_path=PROTOCOL,expected_sha256=m.PROTOCOL_SHA256,
                manifest_path=MANIFEST,data_dir=root,model_dir=root,rights_path=ROOT/'docs/research/source-rights.json',
                code_version=VERSION,execution_config_path=external,adapter_dir=adapter,output=output).items():
                argv.extend(['--'+name.replace('_','-'),str(value)])
            stdout=io.StringIO()
            with patch.object(m,'load_verified_inputs',return_value=(protocol,{'attribution':{}},{},cases,config)), \
                 patch.object(m,'_native_train',side_effect=native), \
                 patch.object(m,'_fsync_directory',side_effect=dir_fsync), \
                 patch.object(m.os,'fsync',side_effect=file_fsync),redirect_stdout(stdout):
                status=cli.main(argv)
            self.assertTrue(state['armed'],'fault must occur after COMPLETED replacement, not temporary fsync')
            self.assertEqual(status,2)
            self.assertEqual(stdout.getvalue(),'HELPSTEER2_SFT_UNAVAILABLE\n')
            if output.exists():
                report=json.loads(output.read_text())
                self.assertEqual(report['status'],'FAILED')
                self.assertTrue(report['metadata_write_failure_observed'])
                self.assertTrue(report['completion_requires_successful_process_exit'])
                self.assertEqual(stat.S_IMODE(output.stat().st_mode),0o600)
            else:
                self.assertEqual(kind,'persistent_all_fsync')

    def test_cli_transient_directory_failure_recovers_failed_receipt(self):
        self.run_cli_fault('transient')

    def test_cli_persistent_directory_failure_never_leaves_completed(self):
        self.run_cli_fault('persistent_directory')

    def test_cli_persistent_fsync_failure_invalidates_unconfirmed_completion(self):
        self.run_cli_fault('persistent_all_fsync')


if __name__ == '__main__': unittest.main()
