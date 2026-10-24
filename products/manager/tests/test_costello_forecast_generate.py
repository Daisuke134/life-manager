"""Fictional contexts; no model, participant data or external service."""
import copy
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from manager_core.costello_forecast import ForecastCase, score_predictions


def module():
    assert importlib.util.find_spec('manager_core.costello_forecast_generate'), 'fixed context generator missing'
    return importlib.import_module('manager_core.costello_forecast_generate')


class GenerationTests(unittest.TestCase):
    def test_grid_passes_only_fixed_feature_prompt_without_label_or_person(self):
        m=module();grid=m.contexts()
        self.assertEqual(len(grid),102)
        self.assertEqual([(r['pre'],r['condition']) for r in grid],
            [(p,c) for p in range(50,101) for c in ('Control','Treatment')])
        for r in grid:
            self.assertEqual(set(r),{'pre','condition','prompt'})
            self.assertEqual(r['prompt'],ForecastCase('unused','unused',r['pre'],r['condition'],None).prompt)

    def test_begun_context_is_unknown_and_rest_not_run_without_retry(self):
        m=module();saved=[];calls=[]
        def generate(prompt):
            calls.append(prompt)
            if len(calls)==2:raise RuntimeError('fictional generation failure')
            return '{"post_belief":40}'
        with self.assertRaises(RuntimeError):
            m.collect_contexts(generate,lambda r:saved.append(copy.deepcopy(r)))
        r=saved[-1]
        self.assertEqual((r['status'],r['pending_index'],len(r['rows'])),('FAILED',1,1))
        cases=(ForecastCase('a','p-a',50,'Control',45),
               ForecastCase('b','p-b',50,'Treatment',45),
               ForecastCase('c','p-c',51,'Control',None))
        p=m.expand_predictions(cases,r)
        self.assertEqual([p[c.row_key].state for c in cases],['VALID','UNKNOWN','NOT_RUN'])
        self.assertEqual(len(calls),2)
        self.assertEqual(saved[1]['pending_index'],0)
        self.assertEqual(saved[1]['rows'],[])

    def test_exact_context_reuse_preserves_people_and_missing_labels(self):
        m=module();calls=[]
        r=m.collect_contexts(lambda p:(calls.append(p) or '{"post_belief":40}'),lambda r:None)
        cases=tuple(ForecastCase(str(i),'p'+str(i),50,'Control',45 if i<2 else None) for i in range(3))
        s=score_predictions(cases,m.expand_predictions(cases,r))
        self.assertEqual((len(calls),s['assigned'],s['human_labelled'],s['states']['VALID']),(102,3,2,3))
        self.assertEqual(s['mae_valid_labelled'],5)
        self.assertTrue(s['complete_forecast'])

    def test_malformed_or_long_output_stays_invalid_without_repair(self):
        m=module();outputs=iter(['```json\n{"post_belief":40}\n```','x'*129]+['{"post_belief":40}']*100)
        r=m.collect_contexts(lambda p:next(outputs),lambda r:None)
        cases=(ForecastCase('a','p-a',50,'Control',45),ForecastCase('b','p-b',50,'Treatment',45))
        s=score_predictions(cases,m.expand_predictions(cases,r))
        self.assertEqual(s['states']['INVALID'],2)
        self.assertIsNone(s['mae_valid_labelled'])
        self.assertFalse(s['complete_forecast'])
        self.assertEqual(s['worst_case_mae_all_labelled'],100)

    def test_rejects_duplicate_or_altered_grid_record_and_forged_completion(self):
        m=module();r=m.collect_contexts(lambda p:'{"post_belief":40}',lambda r:None)
        c=(ForecastCase('a','p-a',50,'Control',45),)
        for kind in ('duplicate','grid','state','pending','complete','extra','raw'):
            x=copy.deepcopy(r)
            if kind=='duplicate':x['rows'][1]=x['rows'][0]
            if kind=='grid':x['rows'][0]['pre']=99
            if kind=='state':x['rows'][0]['state']='INVALID'
            if kind=='pending':x['pending_index']=102
            if kind=='complete':x['rows'].pop()
            if kind=='extra':x['rows'][0]['target']=10
            if kind=='raw':x['rows'][0]['raw']='{"post_belief":true}'
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.expand_predictions(c,x)

    def test_generation_settings_reject_sampling_and_resource_redeclaration(self):
        m=module();s=m.generation_settings();m.validate_generation_settings(s)
        self.assertEqual(s,dict(do_sample=False,num_beams=1,max_new_tokens=16,use_cache=True))
        for k,v in [('do_sample',True),('num_beams',2),('max_new_tokens',32),('use_cache',False)]:
            x=dict(s);x[k]=v
            with self.assertRaises(ValueError):m.validate_generation_settings(x)
        for v in ({},dict(s,temperature=1.0),dict(s,num_beams=True)):
            with self.assertRaises(ValueError):m.validate_generation_settings(v)

    def test_bad_admission_precedes_any_native_import(self):
        m=module()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';p.write_text('{}');p.chmod(0o400)
            with self.assertRaises(ValueError):m.run_generate(str(p))
        self.assertNotIn('torch',sys.modules)

    def test_generation_monitor_does_not_reuse_training_or_other_pid_budget(self):
        m=module();r=dict(status='RUNNING',own_pid=123,own_process_group=123,
            wall_limit_seconds=1800,observed_process_group_rss_limit_bytes=5368709120)
        m.validate_generation_monitor(r,123,123,123)
        for key,value in [('own_pid',124),('status','EXITED_SUCCESS'),('wall_limit_seconds',900),
                          ('observed_process_group_rss_limit_bytes',True)]:
            x=dict(r);x[key]=value
            with self.assertRaises(ValueError):m.validate_generation_monitor(x,123,123,123)

    def test_native_generate_passes_fixed_prompt_and_only_decodes_new_tokens(self):
        m=module();seen={}
        class Tensor:
            shape=(1,3)
        class Tokenizer:
            def apply_chat_template(self,messages,**kw):
                seen['messages']=messages;seen['template']=kw
                return {'input_ids':Tensor(),'attention_mask':Tensor()}
            def decode(self,tokens,**kw):
                self_assert.assertEqual(tokens,[7,8]);seen['decode']=kw
                return '{"post_belief":40}'
        class Model:
            def generate(self,**kw):seen['generation']=kw;return [[1,2,3,7,8]]
        self_assert=self
        raw=m.generate_text(Model(),Tokenizer(),'only features')
        self.assertEqual(raw,'{"post_belief":40}')
        self.assertEqual(seen['messages'],[dict(role='user',content='only features')])
        self.assertEqual(seen['template'],dict(tokenize=True,add_generation_prompt=True,
            enable_thinking=False,truncation=False,return_tensors='pt',return_dict=True))
        self.assertEqual(seen['decode'],dict(skip_special_tokens=True,clean_up_tokenization_spaces=False))
        self.assertTrue(all(seen['generation'][k]==v for k,v in m.generation_settings().items()))

    def test_cli_unknown_argument_is_quiet_and_does_not_echo_input(self):
        m=module()
        script=Path(m.__file__).resolve().parents[1]/'scripts/generate_costello_forecast.py'
        r=subprocess.run([sys.executable,str(script),'--private-input-secret'],capture_output=True,text=True)
        self.assertEqual((r.returncode,r.stdout,r.stderr),(2,'COSTELLO_FORECAST_UNAVAILABLE\n',''))


if __name__=='__main__':unittest.main()
