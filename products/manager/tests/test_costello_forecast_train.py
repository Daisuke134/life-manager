"""Private numeric training admission and standard recipe contracts; no ML execution."""
import builtins
import importlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout,redirect_stderr


def module():
    assert importlib.util.find_spec('manager_core.costello_forecast_train'), 'numeric SFT caller missing'
    return importlib.import_module('manager_core.costello_forecast_train')


class NumericTrainingTests(unittest.TestCase):
    def test_monitor_record_must_describe_this_isolated_native_process_and_limits(self):
        m=module()
        self.assertTrue(hasattr(m,'validate_monitor_record'),'native monitor binding missing')
        record=dict(status='RUNNING',own_pid=12345,own_process_group=12345,
            wall_limit_seconds=900,observed_process_group_rss_limit_bytes=5368709120)
        m.validate_monitor_record(record,12345,12345,12345)
        for key,value in [('status','EXITED_SUCCESS'),('own_pid',999),('own_process_group',999),
                          ('wall_limit_seconds',901),('observed_process_group_rss_limit_bytes',1)]:
            bad=dict(record);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                m.validate_monitor_record(bad,12345,12345,12345)
        with self.assertRaises(ValueError):m.validate_monitor_record(record,12345,999,12345)
        with self.assertRaises(ValueError):m.validate_monitor_record(record,12345,12345,999)

    def test_base_assets_cannot_be_reapproved_as_empty_or_different_weights(self):
        m=module()
        self.assertTrue(hasattr(m,'validate_model_assets'),'frozen base binding missing')
        root=Path(__file__).resolve().parents[1]
        old=json.loads((root/'experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json').read_text())
        m.validate_model_assets(old['model_files'])
        with self.assertRaises(ValueError):m.validate_model_assets({})
        bad=json.loads(json.dumps(old['model_files']))
        bad['model.safetensors']['sha256']='0'*64
        with self.assertRaises(ValueError):m.validate_model_assets(bad)

    def test_failure_before_gradient_observation_does_not_claim_finite_gradients(self):
        m=module()
        with tempfile.TemporaryDirectory() as td:
            receipt=Path(td)/'receipt.json'
            cfg={'receipt_path':str(receipt),'code_version':'a'*40}
            with patch.object(m,'_admission',return_value=(cfg,())),patch.object(m,'_native',side_effect=RuntimeError('private')):
                with self.assertRaises(RuntimeError):m.run_train('/fictional-admission')
            r=json.loads(receipt.read_text())
            self.assertEqual(r['status'],'FAILED')
            self.assertIsNone(r['finite_gradients'])

    def test_cli_invalid_arguments_emit_only_generic_failure(self):
        cli=importlib.import_module('scripts.train_costello_forecast')
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):
            self.assertEqual(cli.main([]),2)
        self.assertEqual(out.getvalue(),'COSTELLO_FORECAST_UNAVAILABLE\n')
        self.assertEqual(err.getvalue(),'')

    def test_standard_recipe_is_one_epoch_and_32_opportunities(self):
        m=module();cfg=m.training_kwargs('/fictional-private-output')
        self.assertEqual((cfg['num_train_epochs'],cfg['per_device_train_batch_size'],
                          cfg['gradient_accumulation_steps']), (1,1,4))
        self.assertEqual(cfg['learning_rate'],0.0002)
        self.assertEqual(cfg['seed'],42)
        self.assertEqual(cfg['dataset_kwargs'],{'skip_prepare_dataset':True})
        self.assertTrue(cfg['completion_only_loss'])
        self.assertFalse(cfg['packing'])
        self.assertEqual(cfg['save_strategy'],'no')
        self.assertEqual(cfg['eval_strategy'],'no')
        self.assertEqual(cfg['report_to'],'none')

    def test_missing_operator_admission_cannot_import_ml(self):
        m=module();imports=[];original=builtins.__import__
        def guard(name,*a,**kw):
            if name.split('.')[0] in {'torch','transformers','trl','peft','datasets','safetensors'}:
                imports.append(name);raise AssertionError('native import before admission')
            return original(name,*a,**kw)
        with patch('builtins.__import__',side_effect=guard):
            with self.assertRaises((ValueError,FileNotFoundError)):
                m.run_train('/nonexistent/operator-config.json')
        self.assertEqual(imports,[])

    def test_execution_scope_is_finite_and_does_not_loosen_old_train27(self):
        m=module()
        self.assertEqual(m.CONFIG_KIND,'manager.costello-numeric-train128.v1')
        self.assertEqual(m.TRAIN_ROWS,128)
        self.assertEqual(m.OPTIMIZER_OPPORTUNITIES,32)
        self.assertEqual(m.MAX_WALL_SECONDS,900)
        self.assertEqual(m.MAX_RSS_BYTES,5368709120)


if __name__=='__main__':unittest.main()
