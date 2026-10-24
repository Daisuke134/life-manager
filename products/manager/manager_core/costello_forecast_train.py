"""One explicitly admitted private train128 call to standard PEFT/TRL.

The operator config is an assertion, not cryptographic proof of approval.
No model execution, network, evaluation or rights changes occur on import.
"""
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from .costello_forecast import (ROOT, DESIGN_SHA256, require, _json,
                               read_training, build_training_example)
from .helpsteer2_candidate_eval import _verify_model
from .helpsteer2_candidate_sft import (PrivateCheckpoint, create_adapter_dir, freeze_inventory,
    _path, _trainables, validate_saved_config, verify_optimizer_membership, SOURCE_FILES as OLD_SOURCES)
from .helpsteer2_candidate_sft import PROTOCOL_SHA256 as OLD_MODEL_PROTOCOL_SHA256

CONFIG_KIND = 'manager.costello-numeric-train128.v1'
TRAIN_ROWS = 128
OPTIMIZER_OPPORTUNITIES = 32
MAX_WALL_SECONDS = 900
MAX_RSS_BYTES = 5368709120
SOURCE_FILES = OLD_SOURCES | frozenset(('manager_core/costello_forecast.py',
    'manager_core/costello_forecast_train.py','scripts/train_costello_forecast.py'))
CONFIG_KEYS = frozenset(('kind','accepted_actions','can_execute','code_version','source_files',
    'cwd',
    'design_sha256','prepared_manifest_sha256','prepared_dir','python_path','python_executable_sha256',
    'packages','model_dir','model_assets','adapter_dir','receipt_path','monitor_receipt',
    'monitor_source','acceptance_evidence','max_wall_seconds','max_rss_bytes'))


def training_kwargs(output_dir):
    return dict(output_dir=str(output_dir), num_train_epochs=1, max_steps=-1,
        per_device_train_batch_size=1, gradient_accumulation_steps=4, learning_rate=0.0002,
        seed=42, data_seed=42, optim='adamw_torch', weight_decay=0.0,
        lr_scheduler_type='constant', warmup_steps=0, max_grad_norm=1.0,
        use_cpu=True, bf16=True, fp16=False, gradient_checkpointing=False,
        dataset_kwargs={'skip_prepare_dataset':True}, completion_only_loss=True,
        assistant_only_loss=False, loss_type='nll', packing=False, padding_free=False,
        dataloader_drop_last=False, dataloader_num_workers=0, dataloader_pin_memory=False,
        report_to='none', save_strategy='no', eval_strategy='no', save_safetensors=True,
        logging_strategy='steps',logging_steps=1,disable_tqdm=True,push_to_hub=False)


def _pin(pin):
    require(type(pin) is dict and set(pin)=={'path','sha256'})
    p=_path(pin['path'],private=True,file=True)
    require(sha256(p.read_bytes()).hexdigest()==pin['sha256'])
    return p


def validate_model_assets(pins):
    """Reuse only the frozen base/tokenizer pins, not old training data or gates."""
    raw=(ROOT/'experiments/behavior-model/helpsteer2-private-sft-protocol-v1.json').read_bytes()
    require(sha256(raw).hexdigest()==OLD_MODEL_PROTOCOL_SHA256)
    old=_json(raw.decode())
    require(old['model_id']=='Qwen/Qwen3-0.6B'
            and old['model_revision']=='c1899de289a04d12100db370d81485cdf75e47ca')
    require(pins==old['model_files'])


def validate_monitor_record(measured,pid,pgid,sid):
    require(type(measured) is dict and measured['status']=='RUNNING')
    require(type(pid) is int and pid>0 and measured['own_pid']==pid
            and measured['own_process_group']==pgid==sid==pid)
    require(type(measured['wall_limit_seconds']) is int
            and measured['wall_limit_seconds']==MAX_WALL_SECONDS
            and type(measured['observed_process_group_rss_limit_bytes']) is int
            and measured['observed_process_group_rss_limit_bytes']==MAX_RSS_BYTES)


def _admission(config_path):
    path=_path(config_path,private=True,file=True,mode=0o400)
    cfg=_json(path.read_text())
    require(set(cfg)==CONFIG_KEYS and cfg['kind']==CONFIG_KIND)
    require(cfg['cwd']==str(ROOT) and Path.cwd().resolve()==ROOT)
    require(cfg['accepted_actions']==['train128_private_once'] and cfg['can_execute'] is False)
    require(type(cfg['max_wall_seconds']) is int and cfg['max_wall_seconds']==MAX_WALL_SECONDS
            and type(cfg['max_rss_bytes']) is int and cfg['max_rss_bytes']==MAX_RSS_BYTES)
    require(cfg['python_path']==sys.executable and sha256(Path(sys.executable).resolve().read_bytes()).hexdigest()
            ==cfg['python_executable_sha256'])
    require(cfg['design_sha256']==DESIGN_SHA256)
    science_raw=(ROOT/'experiments/behavior-model/costello-numeric-forecast-design-v1.json').read_bytes()
    require(sha256(science_raw).hexdigest()==DESIGN_SHA256)
    design=_json(science_raw.decode())
    require(cfg['prepared_manifest_sha256']==design['prepared_private_manifest_sha256'])
    require(cfg['packages']==design['recipe']['library_versions'])
    require(cfg['packages']=={name:importlib.metadata.version(name) for name in cfg['packages']})
    require(type(cfg['code_version']) is str and re.fullmatch('[a-f0-9]{40}',cfg['code_version']))
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==cfg['code_version'])
    require(set(cfg['source_files'])==SOURCE_FILES)
    for name,digest in cfg['source_files'].items():
        actual=(ROOT/name).read_bytes()
        require(sha256(actual).hexdigest()==digest)
        require(actual==subprocess.check_output(['git','show',cfg['code_version']+':products/manager/'+name],cwd=ROOT))
    require(set(cfg['acceptance_evidence'])=={'review','official_ci','data_purpose'})
    for pin in cfg['acceptance_evidence'].values():_pin(pin)
    purpose=_json(_pin(cfg['acceptance_evidence']['data_purpose']).read_text())
    require(purpose['kind']=='manager.costello-train128-purpose.v1'
            and purpose['status']=='ACCEPTED_PRIVATE_TRAIN128_ONLY'
            and purpose['design_sha256']==DESIGN_SHA256
            and purpose['prepared_manifest_sha256']==cfg['prepared_manifest_sha256'])
    monitor=_pin(cfg['monitor_source'])
    require(sha256(monitor.read_bytes()).hexdigest()==
            'c5e33ed50c2dc97dc06c4410c7c381074cd6b0d89a6263f64da3793151bdcf1d')
    receipt=_path(cfg['monitor_receipt'],private=True,file=True,mode=0o600)
    measured=_json(receipt.read_text())
    validate_monitor_record(measured,os.getpid(),os.getpgrp(),os.getsid(0))
    cases=read_training(cfg['prepared_dir'])
    model=_path(cfg['model_dir'],private=True)
    validate_model_assets(cfg['model_assets'])
    _verify_model(model,cfg['model_assets'])
    _path(cfg['adapter_dir'],private=True,fresh=True)
    _path(cfg['receipt_path'],private=True,fresh=True)
    require(len({str(path),cfg['receipt_path'],cfg['monitor_receipt'],cfg['adapter_dir']})==4)
    return cfg,cases


def run_train(config_path):
    cfg,cases=_admission(config_path)
    checkpoint=PrivateCheckpoint(cfg['receipt_path'])
    report=dict(schema='manager.costello-numeric-training-receipt.v1',status='INITIALIZED',
        rows=TRAIN_ROWS,optimizer_opportunities=0,global_step=0,finite_gradients=None,
        finite_gradient_checks=0,
        can_execute=False,human_benefit='NOT_MEASURED',proof='P0',model_adoption='HOLD',
        design_sha256=DESIGN_SHA256,code_version=cfg['code_version'],evaluation_performed=False)
    checkpoint(report)
    try:
        return _native(cfg,cases,report,checkpoint)
    except BaseException:
        report.update(status='FAILED',finite_gradients=None)
        checkpoint(report)
        raise


def _native(cfg,cases,report,checkpoint):
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM,AutoTokenizer,TrainerCallback
    from trl import SFTConfig,SFTTrainer
    from safetensors import safe_open
    torch.set_num_threads(2);torch.manual_seed(42)
    tokenizer=AutoTokenizer.from_pretrained(cfg['model_dir'],local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(cfg['model_dir'],local_files_only=True,
        trust_remote_code=False,use_safetensors=True,torch_dtype=torch.bfloat16,
        device_map=None,attn_implementation='eager')
    model.config.use_cache=False
    examples=[build_training_example(c,tokenizer) for c in cases]
    require(len(examples)==TRAIN_ROWS)
    output=create_adapter_dir(cfg['adapter_dir'])
    trainer=SFTTrainer(model=model,args=SFTConfig(**training_kwargs(output)),
        train_dataset=Dataset.from_list(examples),processing_class=tokenizer,
        peft_config=LoraConfig(r=8,lora_alpha=8,lora_dropout=0.0,
            target_modules=['q_proj','v_proj'],bias='none',task_type='CAUSAL_LM'))
    trainable=_trainables(trainer.model,torch)
    initial={name:p.detach().clone() for name,p in trainable.items()}
    trainer.create_optimizer();verify_optimizer_membership(trainable,trainer.optimizer)
    class Observe(TrainerCallback):
        def on_pre_optimizer_step(self,args,state,control,**kw):
            verify_optimizer_membership(trainable,kw['optimizer'])
            require(all(p.grad is not None and bool(torch.isfinite(p.grad).all().item()) for p in trainable.values()))
            report['finite_gradient_checks']+=1
            report['finite_gradients']=True
        def on_optimizer_step(self,args,state,control,**kw):
            report['optimizer_opportunities']+=1
        def on_step_end(self,args,state,control,**kw):
            report.update(status='TRAINING',global_step=state.global_step);checkpoint(report)
    trainer.add_callback(Observe());report.update(status='TRAIN_BEGIN');checkpoint(report)
    trainer.train()
    require(trainer.state.global_step==OPTIMIZER_OPPORTUNITIES
            and report['optimizer_opportunities']==OPTIMIZER_OPPORTUNITIES
            and report['finite_gradient_checks']==OPTIMIZER_OPPORTUNITIES)
    report.update(status='SAVE_STARTED',global_step=trainer.state.global_step);checkpoint(report)
    trainer.save_model(str(output))
    validate_saved_config(_json((output/'adapter_config.json').read_text()),Path(cfg['model_dir']))
    with safe_open(str(output/'adapter_model.safetensors'),framework='pt',device='cpu') as saved:
        require(set(saved.keys())=={name.replace('.default.weight','.weight') for name in trainable})
        for name,p in trainable.items():
            tensor=saved.get_tensor(name.replace('.default.weight','.weight'))
            require(bool(torch.isfinite(tensor).all().item()) and torch.equal(tensor,p.detach().cpu()))
    report.update(status='COMPLETED',inventory=freeze_inventory(output),
        changed_adapter_tensors=sum(not torch.equal(initial[n],p.detach()) for n,p in trainable.items()),
        trainable_parameters=sum(p.numel() for p in trainable.values()))
    checkpoint(report)
    return report
