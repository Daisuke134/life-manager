"""Fictional original pairs; stdlib only, no actual adapter/data/ML imports."""
import copy
from contextlib import contextmanager,redirect_stdout
import gzip
from hashlib import sha256
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SCI=ROOT/'experiments/behavior-model/helpsteer2-fixed-adapter-eval-protocol-v1.json'
VERSION='a'*40


def module():
    assert importlib.util.find_spec('manager_core.helpsteer2_fixed_adapter_eval'),'fixed evaluator missing'
    return importlib.import_module('manager_core.helpsteer2_fixed_adapter_eval')


def digest(text): return sha256(text.encode()).hexdigest()


def fixture(size=2,split='development8'):
    specs=[];preferences={};quality={}
    final=split=='final16'
    for n in range(1,size+1):
        row_id=n+(100 if final else 0)
        prompt=f'fictional prompt {row_id}';a=f'fictional a {row_id}';b=f'fictional b {row_id}'
        specs.append(dict(source_preference_row_1based=row_id,raw_preference_split='val' if final else 'train',
            native_split='validation' if final else 'train',proposed_split='final_test' if final else 'dev',
            quality_rows_1based=[2*n-1,2*n],prompt_exact_sha256=digest(prompt),prompt_canonical_sha256=digest(prompt),
            response_exact_sha256=[digest(a),digest(b)],response_canonical_sha256=[digest(a),digest(b)],
            full_sequence_token_counts=[6,7],completion_mask_token_lengths_by_candidate=[2,3]))
        preferences[row_id]=dict(split='val' if final else 'train',prompt=prompt,response_1=a,response_2=b,
            preference_strength=-1 if n%2 else 2)
        for index,response in zip((2*n-1,2*n),(a,b)):
            quality[index]=dict(prompt=prompt,response=response,helpfulness=3,correctness=4,coherence=4,complexity=1,verbosity=2)
    return specs,preferences,quality,split


def cases(size=2,split='development8'): return module().reconstruct_cases(*fixture(size,split))


def encode(case):
    m=module()
    return (m.completion_mask([1,2,3,4],[1,2,3,4,5,151645]),
            m.completion_mask([1,2,3,4],[1,2,3,4,5,6,151645]))


class FixedAdapterInputTests(unittest.TestCase):
    def test_builtin_science_reapproval_cannot_replace_bytes(self):
        m=module();raw=SCI.read_bytes()
        p=m.validate_protocol(raw,m.PROTOCOL_SHA256)
        self.assertEqual(p['candidate_forward_requests']['total'],96)
        for payload,expected in ((raw+b' ',m.PROTOCOL_SHA256),(b'{}',digest('{}')),(raw,'0'*64)):
            with self.assertRaises(ValueError): m.validate_protocol(payload,expected)

    def test_specific_new_rights_and_frozen_parent(self):
        m=module();p=json.loads(SCI.read_bytes())
        r=json.loads((ROOT/'docs/research/source-rights.json').read_bytes())
        selected=m.validate_rights(r,p)
        self.assertEqual(selected['id'],'helpsteer2-private-fixed-adapter-eval24-v1')
        bad=copy.deepcopy(r)
        next(x for x in bad['sources'] if x['id']==selected['id'])['permissions']['private_fixed_adapter_evaluation']='hold'
        with self.assertRaises(ValueError): m.validate_rights(bad,p)
        parent=ROOT/'experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json'
        m.validate_parent(parent.read_bytes(),p)
        with self.assertRaises(ValueError): m.validate_parent(parent.read_bytes()+b' ',p)

    def test_original_sign_native_validation_quality_join_and_private_repr(self):
        for split in ('development8','final16'):
            got=cases(split=split)
            self.assertEqual([c.human_choice for c in got],[1,2])
            self.assertEqual(got[0].native_split,'validation' if split=='final16' else 'train')
            self.assertNotIn('fictional',repr(got))

    def test_raw_split_choice_hash_canonical_and_quality_corruption_fail(self):
        for edit in ('split','sign','bool','prompt','response','canonical','quality','join','duplicate'):
            specs,prefs,quality,split=fixture(split='final16');row=prefs[101]
            if edit=='split':row['split']='train'
            if edit=='sign':row['preference_strength']=0
            if edit=='bool':row['preference_strength']=True
            if edit=='prompt':row['prompt']+=' changed'
            if edit=='response':row['response_2']+=' changed'
            if edit=='canonical':specs[0]['response_canonical_sha256'][0]='0'*64
            if edit=='quality':quality[1]['correctness']=5
            if edit=='join':quality[1]['response']=quality[2]['response']
            if edit=='duplicate':specs[1]=copy.deepcopy(specs[0])
            with self.subTest(edit=edit),self.assertRaises(ValueError):module().reconstruct_cases(specs,prefs,quality,split)

    def test_unselected_json_is_not_parsed_including_final_gold(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'fictional.gz'
            path.write_bytes(gzip.compress(b'{malformed unselected gold}\n{"selected":true}\nnot JSON\n'))
            source=m._verify_file(path,dict(bytes=path.stat().st_size,sha256=sha256(path.read_bytes()).hexdigest()),
                source_id='fictional',url='https://example.org/source')
            self.assertEqual(m.read_selected_rows(path,source,{2}),{2:{'selected':True}})
            with self.assertRaises(ValueError):m.read_selected_rows(path,source,{1})
            path.write_bytes(b'tamper')
            with self.assertRaises(ValueError):m.read_selected_rows(path,source,{2})

    def test_all_native_template_masks_validate_before_scoring(self):
        m=module();calls=[]
        class Tokenizer:
            def apply_chat_template(self,messages,**kwargs):
                calls.append((messages,kwargs))
                if len(messages)==1:return [1,2,3,4]
                return [1,2,3,4,5,151645] if ' a ' in messages[-1]['content'] else [1,2,3,4,5,6,151645]
        pair=m.build_pair_masks(cases()[0],Tokenizer())
        self.assertEqual([p.scored_tokens for p in pair],[2,3])
        self.assertEqual(pair[0].labels,(-100,-100,-100,-100,5,151645))
        self.assertEqual(len(calls),3)
        for _,kwargs in calls:self.assertEqual((kwargs['enable_thinking'],kwargs['truncation']),(False,False))
        for prompt,full in (([9],[1,2,151645]),([1],[1,2,3]),([1],[1,151645,151645]),([1],[1]+[2]*255+[151645])):
            with self.assertRaises(ValueError):m.completion_mask(prompt,full)
        post=m.completion_mask([1],[1,2,151645,9]);self.assertEqual(post.labels,(-100,2,151645,-100))


class FixedAdapterScoringTests(unittest.TestCase):
    def test_fixed_order_per_slice_pair_denominators_and_noaction_null(self):
        m=module();groups={'development8':cases(),'final16':cases(split='final16')};calls=[];snapshots=[]
        def loss(policy,case,mask):
            calls.append((policy,case.row_id,len(mask.input_ids)))
            return 1.0 if mask.scored_tokens==(2 if case.human_choice==1 else 3) else 2.0
        report=m.evaluate_cases(groups,encode,loss,progress=lambda r:snapshots.append(copy.deepcopy(r)))
        self.assertEqual(calls[:4],[('NATIVE_BASE_QWEN',1,6),('NATIVE_BASE_QWEN',1,7),('FIXED_LORA_ADAPTER',1,6),('FIXED_LORA_ADAPTER',1,7)])
        self.assertEqual(len(calls),16)
        self.assertEqual(report['model_requests'],dict(assigned=16,attempted=16,completed=16,failed=0,unknown=0,not_run=0))
        for name in groups:
            slice=report['slices'][name]
            no=slice['policies']['NO_ACTION'];rule=slice['policies']['SHORTER_CANDIDATE_RULE']
            self.assertEqual((no['assigned'],no['abstained'],no['coverage'],no['conditional_accuracy']),(2,2,0,None))
            self.assertTrue(all(row['nll'] is None for row in no['groups']+rule['groups']))
            self.assertEqual(slice['paired']['base_adapter']['paired_valid_count'],2)
            self.assertEqual(slice['paired']['base_adapter']['base_correct_adapter_correct'],2)
        self.assertTrue(any(r['model_requests']['unknown']==1 for r in snapshots))

    def test_partial_second_candidate_failure_keeps_completed_intersection_and_notrun(self):
        m=module();calls=[]
        def loss(policy,case,mask):
            calls.append((policy,case.row_id,mask.scored_tokens))
            if len(calls)==8:raise RuntimeError('fictional private source text')
            return 1.0 if mask.scored_tokens==2 else 2.0
        r=m.evaluate_cases({'development8':cases(3)},encode,loss)
        self.assertEqual(len(calls),8)
        self.assertEqual(r['model_requests'],dict(assigned=12,attempted=8,completed=7,failed=1,unknown=0,not_run=4))
        p=r['slices']['development8']['policies']
        self.assertEqual((p['NATIVE_BASE_QWEN']['valid_completed'],p['FIXED_LORA_ADAPTER']['failed']),(2,1))
        self.assertEqual(p['NATIVE_BASE_QWEN']['not_run'],1)
        self.assertEqual(r['slices']['development8']['paired']['base_adapter']['paired_valid_count'],1)
        self.assertEqual(p['FIXED_LORA_ADAPTER']['groups'][1]['nll'][0]['mean'],1.0)
        self.assertNotIn('fictional private source text',json.dumps(r))

    def test_inflight_interruption_stays_unknown_and_untouched_notrun(self):
        m=module();seen=[]
        def loss(*_):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            m.evaluate_cases({'final16':cases(split='final16')},encode,loss,progress=lambda r:seen.append(copy.deepcopy(r)))
        r=seen[-1]
        self.assertEqual(r['model_requests']['unknown'],1)
        self.assertEqual(r['slices']['final16']['policies']['NATIVE_BASE_QWEN']['unknown'],1)
        self.assertEqual(r['slices']['final16']['policies']['FIXED_LORA_ADAPTER']['not_run'],2)

    def test_nonfinite_and_negative_loss_fail_without_retry(self):
        m=module()
        for value in (float('nan'),float('inf'),-1,True):
            calls=[]
            def loss(*args):calls.append(args);return value
            r=m.evaluate_cases({'development8':cases()},encode,loss)
            self.assertEqual(len(calls),1)
            self.assertEqual(r['model_requests']['failed'],1)
            self.assertEqual(r['slices']['development8']['paired']['base_adapter']['adapter_minus_base_accuracy'],None)

    def test_mean_not_sum_exact_hash_ties_and_paired_signed_difference(self):
        m=module()
        def loss(policy,case,mask):
            if policy=='NATIVE_BASE_QWEN':return 2.0 if mask.scored_tokens==2 else 1.5
            return 1.0
        r=m.evaluate_cases({'development8':cases()},encode,loss)['slices']['development8']
        base=r['policies']['NATIVE_BASE_QWEN']['groups'][0]
        self.assertEqual(base['choice'],2) # sum4 vs4.5 would choose1; mean chooses2.
        adapter=r['policies']['FIXED_LORA_ADAPTER']['groups'][0]
        self.assertTrue(adapter['tie'])
        self.assertEqual(adapter['choice'],min(range(2),key=lambda i:cases()[0].response_sha256[i])+1)
        cells=r['paired']['base_adapter']
        self.assertEqual(sum(cells[k] for k in ('base_correct_adapter_correct','base_correct_adapter_wrong','base_wrong_adapter_correct','base_wrong_adapter_wrong')),2)

    def test_invalid_masks_stop_all_models_before_first_request(self):
        m=module();called=[]
        def broken(_):return (m.completion_mask([1],[1,151645]),)*2
        with self.assertRaises(ValueError):
            m.evaluate_cases({'development8':cases()},broken,lambda *args:called.append(args))
        self.assertEqual(called,[])


class FixedAdapterNativeStateTests(unittest.TestCase):
    def fake(self,irregular=False,restore=True):
        class Model:
            enabled='irregular' if irregular else True
            training=False
            gradients_enabled=False
            def requires_grad_(self,enabled):
                self.gradients_enabled=enabled
                return self
            def get_model_status(self):return SimpleNamespace(enabled=self.enabled,merged_adapters=[],active_adapters=['default'],trainable_params=112 if self.gradients_enabled else 0)
            @contextmanager
            def disable_adapter(self):
                self.enabled=False
                try:yield
                finally:
                    self.enabled=True if restore else False
                    # Installed PEFT enable_adapters(True) calls set_adapter(),
                    # which sets the active adapter layers requires_grad=True.
                    self.gradients_enabled=bool(restore)
        return Model()

    def test_native_disable_restores_on_normal_and_forward_exception(self):
        m=module();model=self.fake()
        try:
            with m.base_condition(model):self.assertIs(model.enabled,False)
        except ValueError:
            self.fail('standard native context must restore enabled AND nontrainable inference state')
        self.assertIs(model.enabled,True)
        self.assertFalse(model.gradients_enabled)
        with self.assertRaises(RuntimeError):
            with m.base_condition(model):raise RuntimeError('synthetic forward failure')
        self.assertIs(model.enabled,True)
        self.assertFalse(model.gradients_enabled)
        for model in (self.fake(irregular=True),self.fake(restore=False)):
            with self.assertRaises(ValueError):
                with m.base_condition(model):pass

    def test_private_cli_failure_precedes_optional_import(self):
        m=module();import builtins
        original=builtins.__import__;seen=[]
        def guard(name,*args,**kwargs):
            if name.split('.')[0] in ('torch','transformers','peft','safetensors'):
                seen.append(name);raise AssertionError('ML forbidden')
            return original(name,*args,**kwargs)
        with tempfile.TemporaryDirectory() as td,patch('builtins.__import__',side_effect=guard):
            with self.assertRaisesRegex(ValueError,'^HELPSTEER2_FIXED_ADAPTER_EVAL_UNAVAILABLE$'):
                m.run_local(protocol_path=SCI,expected_sha256=m.PROTOCOL_SHA256,code_version=VERSION,
                    metadata_output_path=Path(td)/'receipt.json',execution_config_path=Path(td)/'missing')
        self.assertEqual(seen,[])

    def test_cli_has_required_nonabbreviated_paths_and_static_failure(self):
        path=ROOT/'scripts/evaluate_helpsteer2_fixed_adapter.py'
        self.assertTrue(path.is_file(),'fixed evaluation CLI missing')
        spec=importlib.util.spec_from_file_location('fixed_eval_cli',path)
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        out=io.StringIO()
        with redirect_stdout(out):status=cli.main(['--help'])
        self.assertEqual((status,out.getvalue()),(2,'HELPSTEER2_FIXED_ADAPTER_EVAL_UNAVAILABLE\n'))


class FixedAdapterExecutionTests(unittest.TestCase):
    def fixture(self,root):
        m=module();protocol=json.loads(SCI.read_bytes())
        parent=json.loads((ROOT/'experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json').read_bytes())
        adapter=root/'adapter';adapter.mkdir(mode=0o700)
        for name in ('adapter_model.safetensors','adapter_config.json','tokenizer.json','tokenizer_config.json','training_args.bin'):
            p=adapter/name;p.write_bytes(b'fictional saved bytes');p.chmod(0o600)
        saved=dict(r=8,lora_alpha=8,lora_dropout=0,target_modules=['q_proj','v_proj'],bias='none',task_type='CAUSAL_LM',
            inference_mode=True,peft_type='LORA',init_lora_weights=True,modules_to_save=None,base_model_name_or_path=str(root))
        (adapter/'adapter_config.json').write_text(json.dumps(saved))
        inventory={p.name:dict(bytes=p.stat().st_size,sha256=sha256(p.read_bytes()).hexdigest()) for p in adapter.iterdir()}
        canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        inventory_sha=sha256(canonical(inventory)).hexdigest()
        training=dict(schema='manager.helpsteer2-private-sft-result.v1',status='COMPLETED',event='ARTIFACT_FROZEN',
            scientific_protocol_sha256=m.PARENT_SHA256,manifest_sha256=m.MANIFEST_SHA256,
            artifact_inventory=inventory,artifact_inventory_sha256=inventory_sha,
            model_files=parent['model_files'],source_artifacts=parent['source_artifacts'],packages=parent['packages'])
        result=root/'training-result.json';result.write_text(json.dumps(training));result.chmod(0o600)
        pin=dict(path=str(result),sha256=sha256(result.read_bytes()).hexdigest())
        self.inputs=dict(protocol_path=str(SCI),parent_protocol_path=str(ROOT/'experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json'),
            manifest_path=str(ROOT/'experiments/behavior-model/helpsteer2-train27-manifest-v1.json'),data_dir=str(root),model_dir=str(root),
            rights_path=str(ROOT/'docs/research/source-rights.json'),adapter_dir=str(adapter))
        config=dict(kind='manager.helpsteer2-fixed-adapter-eval-execution.v1',
            acceptance_status='ACCEPTED_ONE_OFFLINE_FIXED_ADAPTER_EVALUATION_ATTEMPT',accepted_gates=['G7'],can_execute=False,
            scientific_protocol_sha256=m.PROTOCOL_SHA256,frozen_training_protocol_sha256=m.PARENT_SHA256,
            manifest_sha256=m.MANIFEST_SHA256,rights_record_sha256=m.RIGHTS_SHA256,code_version=VERSION,cwd=str(ROOT),
            input_paths=dict(self.inputs),output=str(root/'receipt.json'),max_cumulative_wall_seconds=900,max_process_group_rss_bytes=6442450944,
            source_files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in m.SOURCE_FILES},
            acceptance_evidence={name:dict(pin) for name in m.EVIDENCE_KEYS},watchdog=dict(pin),training_result=dict(pin),
            parent_training_normal_exit_verified=True,adapter_inventory_sha256=inventory_sha)
        path=root/'execution.json'
        return config,path,protocol,parent

    def validate(self,path,protocol,parent):
        return module().validate_execution_config(path,protocol=protocol,parent=parent,code_version=VERSION,
            input_paths=self.inputs,metadata_output_path=str(path.parent/'receipt.json'))

    def write(self,path,config):
        if path.exists():path.chmod(0o600)
        path.write_text(json.dumps(config));path.chmod(0o400)

    def test_complete_fictional_config_and_actual_inventory_hashes_are_checked(self):
        with tempfile.TemporaryDirectory() as td:
            config,path,p,parent=self.fixture(Path(td));self.write(path,config)
            verified,training=self.validate(path,p,parent)
            self.assertFalse(verified['can_execute']);self.assertEqual(training['status'],'COMPLETED')
            (Path(config['input_paths']['adapter_dir'])/'adapter_model.safetensors').write_bytes(b'tampered')
            with self.assertRaises(ValueError):self.validate(path,p,parent)

    def test_missing_g7_evidence_status_0400_source_paths_parent_and_inventory_rejected(self):
        for edit in ('status','G7','science','parent','rights','normal_exit','source','evidence','output','input','inventory','mode','circular'):
            with self.subTest(edit=edit),tempfile.TemporaryDirectory() as td:
                config,path,p,parent=self.fixture(Path(td))
                if edit=='status':config['acceptance_status']='PENDING'
                if edit=='G7':config['accepted_gates']=[]
                if edit=='science':config['scientific_protocol_sha256']='0'*64
                if edit=='parent':config['frozen_training_protocol_sha256']='0'*64
                if edit=='rights':config['rights_record_sha256']='0'*64
                if edit=='normal_exit':config['parent_training_normal_exit_verified']=False
                if edit=='source':config['source_files'][next(iter(config['source_files']))]='0'*64
                if edit=='evidence':config['acceptance_evidence'].pop('G7')
                if edit=='output':config['output']=str(Path(td)/'other.json')
                if edit=='input':config['input_paths']['data_dir']=str(ROOT)
                if edit=='inventory':config['adapter_inventory_sha256']='0'*64
                if edit=='circular':config['watchdog']['path']=str(path)
                self.write(path,config)
                if edit=='mode':path.chmod(0o600)
                with self.assertRaises((ValueError,KeyError)):self.validate(path,p,parent)


    def test_hash_matching_but_wrong_native_saved_recipe_stops_before_loader(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            config,path,p,parent=self.fixture(Path(td))
            adapter=Path(config['input_paths']['adapter_dir']);saved_path=adapter/'adapter_config.json'
            saved=json.loads(saved_path.read_text());saved['r']=16;saved_path.write_text(json.dumps(saved))
            result=Path(config['training_result']['path']);training=json.loads(result.read_text())
            training['artifact_inventory']['adapter_config.json']=dict(bytes=saved_path.stat().st_size,sha256=sha256(saved_path.read_bytes()).hexdigest())
            canonical=json.dumps(training['artifact_inventory'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            training['artifact_inventory_sha256']=config['adapter_inventory_sha256']=sha256(canonical).hexdigest()
            result.write_text(json.dumps(training));config['training_result']['sha256']=sha256(result.read_bytes()).hexdigest()
            # Other evidence shares the original artifact and must also bind its actual new bytes.
            for pin in (*config['acceptance_evidence'].values(),config['watchdog']):pin['sha256']=config['training_result']['sha256']
            self.write(path,config)
            with self.assertRaises(ValueError):self.validate(path,p,parent)

    def test_incomplete_parent_artifact_and_symlink_inventory_rejected(self):
        for edit in ('failed','partial','extra','link'):
            with self.subTest(edit=edit),tempfile.TemporaryDirectory() as td:
                config,path,p,parent=self.fixture(Path(td));result=Path(config['training_result']['path'])
                training=json.loads(result.read_text());adapter=Path(config['input_paths']['adapter_dir'])
                if edit=='failed':training['status']='FAILED'
                if edit=='partial':training['event']='SAVE_RETURNED'
                if edit=='extra':(adapter/'raw-data.txt').write_text('fictional')
                if edit=='link':
                    target=adapter/'tokenizer.json';target.unlink();target.symlink_to(adapter/'tokenizer_config.json')
                result.write_text(json.dumps(training));config['training_result']['sha256']=sha256(result.read_bytes()).hexdigest()
                self.write(path,config)
                with self.assertRaises(ValueError):self.validate(path,p,parent)


class FixedAdapterReceiptBoundaryTests(unittest.TestCase):
    def run_boundary(self,fault=None):
        m=module()
        spec=importlib.util.spec_from_file_location('fixed_eval_boundary_cli',ROOT/'scripts/evaluate_helpsteer2_fixed_adapter.py')
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        groups={'development8':cases(8),'final16':cases(16,'final16')}
        protocol=json.loads(SCI.read_bytes());parent=json.loads((ROOT/'experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json').read_bytes())
        import manager_core.helpsteer2_candidate_sft as writer_module
        real_dir=writer_module._fsync_directory;armed=False
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);output=root/'receipt.json';configpath=root/'execution.json';configpath.write_text('synthetic')
            def fsync_directory(path):
                nonlocal armed
                if output.exists() and json.loads(output.read_text())['status']=='COMPLETED':armed=True
                if armed and fault=='directory':raise OSError('private I/O fault')
                return real_dir(path)
            def native(groups,configuration,progress):
                def loss(policy,case,mask):
                    if fault=='interrupt':raise KeyboardInterrupt()
                    return 1.0 if mask.scored_tokens==2 else 2.0
                return m.evaluate_cases(groups,encode,loss,progress=progress)
            argv=[]
            for name,value in dict(protocol_path=SCI,expected_sha256=m.PROTOCOL_SHA256,
                parent_protocol_path=ROOT/'experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json',
                manifest_path=ROOT/'experiments/behavior-model/helpsteer2-train27-manifest-v1.json',data_dir=root,model_dir=root,
                rights_path=ROOT/'docs/research/source-rights.json',adapter_dir=root,code_version=VERSION,
                execution_config_path=configpath,output=output).items():argv+=['--'+name.replace('_','-'),str(value)]
            out=io.StringIO()
            before={key:os.environ.get(key) for key in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_DATASETS_OFFLINE')}
            with patch.object(m,'load_verified_inputs',return_value=(protocol,parent,{'attribution':{}},groups,{}, {'artifact_inventory_sha256':'0'*64})), \
                 patch.object(m,'_native_evaluate',side_effect=native),patch.object(writer_module,'_fsync_directory',side_effect=fsync_directory),redirect_stdout(out):
                status=cli.main(argv)
            self.assertEqual(before,{key:os.environ.get(key) for key in before})
            detailed=json.loads(output.read_text())
            if fault is None:
                self.assertEqual(status,0);aggregate=json.loads(out.getvalue())
                self.assertEqual(aggregate['model_requests']['completed'],96)
                self.assertNotIn('human_choice',out.getvalue());self.assertNotIn('groups',out.getvalue())
                self.assertNotIn('paired_ids',out.getvalue());self.assertNotIn('fictional',out.getvalue())
                self.assertEqual(detailed['status'],'COMPLETED')
                self.assertEqual(detailed['slices']['final16']['policies']['FIXED_LORA_ADAPTER']['assigned'],16)
            else:
                self.assertEqual((status,out.getvalue()),(2,'HELPSTEER2_FIXED_ADAPTER_EVAL_UNAVAILABLE\n'))
                self.assertEqual(detailed['status'],'FAILED')
                if fault=='directory':self.assertTrue(armed);self.assertTrue(detailed['metadata_write_failure_observed'])
                if fault=='interrupt':self.assertEqual(detailed['model_requests']['unknown'],1)

    def test_96_assignment_success_exposes_aggregate_only(self):self.run_boundary()
    def test_post_replace_directory_failure_never_returns_completed(self):self.run_boundary('directory')
    def test_interrupt_preserves_unknown_candidate_and_static_cli_failure(self):self.run_boundary('interrupt')


if __name__=='__main__':unittest.main()
