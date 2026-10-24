"""One separately admitted, label-free generation grid for a frozen adapter.

Only identical feature prompts share a prediction. Participant scoring is separate.
Importing this module does not load ML libraries or confer execution authority.
"""
import copy
from hashlib import sha256
import importlib.metadata
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from .costello_forecast import (ROOT, DESIGN_SHA256, ForecastCase, Prediction,
    parse_prediction, require, _json)
from .costello_forecast_train import (SOURCE_FILES as TRAIN_SOURCES, _pin,
    validate_model_assets)
from .helpsteer2_candidate_eval import _verify_model
from .helpsteer2_candidate_sft import (PrivateCheckpoint, _path, _digest_file,
    validate_saved_config)

CONFIG_KIND='manager.costello-numeric-generate.v1'
ADAPTER_FREEZE_SHA256='83b2d22d575b46e66935336a70d0a374ceb1790b24001c076a8305e41aeb4983'
MAX_WALL_SECONDS=1800
MAX_RSS_BYTES=5368709120
SOURCE_FILES=TRAIN_SOURCES | frozenset(('manager_core/costello_forecast_generate.py',
    'scripts/generate_costello_forecast.py'))
CONFIG_KEYS=frozenset(('kind','accepted_actions','can_execute','code_version','source_files',
    'cwd','design_sha256','python_path','python_executable_sha256','packages',
    'model_dir','model_assets','adapter_dir','adapter_freeze','arm','settings',
    'receipt_path','monitor_receipt','monitor_source','acceptance_evidence',
    'max_wall_seconds','max_rss_bytes'))


def contexts():
    # These are an exhaustive feature grid, not fictional human observations.
    return tuple(dict(pre=p,condition=c,
        prompt=ForecastCase('GRID_CONTEXT','NOT_A_PARTICIPANT',p,c,None).prompt)
        for p in range(50,101) for c in ('Control','Treatment'))


def generation_settings():
    return dict(do_sample=False,num_beams=1,max_new_tokens=16,use_cache=True)


def validate_generation_settings(settings):
    expected=generation_settings()
    require(type(settings) is dict and set(settings)==set(expected))
    require(all(type(settings[k]) is type(v) and settings[k]==v for k,v in expected.items()))


def _state(raw):
    require(type(raw) is str and len(raw)<=2048)
    try:
        parse_prediction(raw)
        return 'VALID'
    except ValueError:
        return 'INVALID'


def collect_contexts(generate,checkpoint):
    report=dict(schema='manager.costello-context-grid.v1',status='INITIALIZED',
                rows=[],pending_index=None)
    checkpoint(copy.deepcopy(report))
    try:
        for i,c in enumerate(contexts()):
            report.update(status='RUNNING',pending_index=i)
            checkpoint(copy.deepcopy(report))
            raw=generate(c['prompt'])
            report['rows'].append(dict(index=i,pre=c['pre'],condition=c['condition'],
                                       state=_state(raw),raw=raw))
            report['pending_index']=None
            checkpoint(copy.deepcopy(report))
        report['status']='COMPLETED'
        checkpoint(copy.deepcopy(report))
        return report
    except BaseException:
        report['status']='FAILED'
        checkpoint(copy.deepcopy(report))
        raise


def expand_predictions(cases,report):
    require(type(report) is dict and set(report)=={'schema','status','rows','pending_index'})
    require(report['schema']=='manager.costello-context-grid.v1'
            and report['status'] in ('INITIALIZED','RUNNING','FAILED','COMPLETED'))
    rows=report['rows'];pending=report['pending_index'];grid=contexts()
    require(type(rows) is list and len(rows)<=len(grid))
    require(pending is None or type(pending) is int and pending==len(rows)<len(grid))
    if report['status']=='INITIALIZED':require(not rows and pending is None)
    if report['status']=='COMPLETED':require(len(rows)==len(grid) and pending is None)
    lookup={}
    for i,r in enumerate(rows):
        require(type(r) is dict and set(r)=={'index','pre','condition','state','raw'})
        require(type(r['index']) is int and r['index']==i
                and type(r['pre']) is int and r['pre']==grid[i]['pre']
                and r['condition']==grid[i]['condition'] and r['state']==_state(r['raw']))
        lookup[(r['pre'],r['condition'])]=Prediction(r['state'],
            r['raw'] if len(r['raw'])<=128 else None)
    if pending is not None:
        c=grid[pending];lookup[(c['pre'],c['condition'])]=Prediction('UNKNOWN',None)
    require(type(cases) is tuple and all(type(c) is ForecastCase for c in cases))
    require(len({c.row_key for c in cases})==len(cases)
            and len({c.participant_key for c in cases})==len(cases))
    result={}
    for c in cases:
        c.__post_init__()
        result[c.row_key]=lookup.get((c.pre,c.condition),Prediction('NOT_RUN',None))
    return result


def validate_generation_monitor(measured,pid,pgid,sid):
    require(type(measured) is dict and measured['status']=='RUNNING')
    require(type(pid) is int and pid>0 and measured['own_pid']==pid
            and measured['own_process_group']==pgid==sid==pid)
    require(type(measured['wall_limit_seconds']) is int
            and measured['wall_limit_seconds']==MAX_WALL_SECONDS
            and type(measured['observed_process_group_rss_limit_bytes']) is int
            and measured['observed_process_group_rss_limit_bytes']==MAX_RSS_BYTES)


def _adapter(cfg):
    pin=cfg['adapter_freeze'];require(pin['sha256']==ADAPTER_FREEZE_SHA256)
    frozen=_path(_pin(pin),private=True,file=True,mode=0o400)
    f=_json(frozen.read_text())
    require(f['status']=='ARTIFACT_FROZEN_BEFORE_NEW_MODEL_EVALUATION'
            and f['selection']=='SINGLE_ARTIFACT_NO_MODEL_SCORE_SELECTION'
            and f['new_model_evaluation_performed'] is False)
    directory=_path(cfg['adapter_dir'],private=True)
    require(directory.is_dir() and stat.S_IMODE(directory.stat().st_mode)==0o700)
    require({p.name for p in directory.iterdir()}==set(f['inventory']))
    for name,pin in f['inventory'].items():
        p=_path(directory/name,private=True,file=True,mode=0o600)
        require(p.stat().st_size==pin['bytes'] and _digest_file(p)==pin['sha256'])
    validate_saved_config(_json((directory/'adapter_config.json').read_text()),Path(cfg['model_dir']))


def _admission(config_path):
    path=_path(config_path,private=True,file=True,mode=0o400)
    cfg=_json(path.read_text())
    require(set(cfg)==CONFIG_KEYS and cfg['kind']==CONFIG_KIND)
    require(cfg['cwd']==str(ROOT) and Path.cwd().resolve()==ROOT)
    require(cfg['arm'] in ('FROZEN_BASE','FROZEN_SINGLE_ADAPTER')
            and cfg['accepted_actions']==['generate102_private_once'] and cfg['can_execute'] is False)
    validate_generation_settings(cfg['settings'])
    require(type(cfg['max_wall_seconds']) is int and cfg['max_wall_seconds']==MAX_WALL_SECONDS
            and type(cfg['max_rss_bytes']) is int and cfg['max_rss_bytes']==MAX_RSS_BYTES)
    require(cfg['python_path']==sys.executable and _digest_file(Path(sys.executable).resolve())
            ==cfg['python_executable_sha256'])
    require(cfg['design_sha256']==DESIGN_SHA256)
    raw=(ROOT/'experiments/behavior-model/costello-numeric-forecast-design-v1.json').read_bytes()
    require(sha256(raw).hexdigest()==DESIGN_SHA256)
    design=_json(raw.decode())
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
    require(purpose['kind']=='manager.costello-generate102-purpose.v1'
            and purpose['status']=='ACCEPTED_PRIVATE_GENERATION_ONLY'
            and purpose['arm']==cfg['arm'] and purpose['code_version']==cfg['code_version']
            and purpose['design_sha256']==DESIGN_SHA256
            and purpose['adapter_freeze_sha256']==ADAPTER_FREEZE_SHA256)
    monitor=_pin(cfg['monitor_source'])
    require(_digest_file(monitor)=='c5e33ed50c2dc97dc06c4410c7c381074cd6b0d89a6263f64da3793151bdcf1d')
    measured=_json(_path(cfg['monitor_receipt'],private=True,file=True,mode=0o600).read_text())
    validate_generation_monitor(measured,os.getpid(),os.getpgrp(),os.getsid(0))
    _path(cfg['model_dir'],private=True)
    validate_model_assets(cfg['model_assets']);_verify_model(Path(cfg['model_dir']),cfg['model_assets'])
    _adapter(cfg)
    _path(cfg['receipt_path'],private=True,fresh=True)
    require(len({str(path),cfg['receipt_path'],cfg['monitor_receipt']})==3)
    return cfg


def generate_text(model,tokenizer,prompt):
    encoded=tokenizer.apply_chat_template([dict(role='user',content=prompt)],tokenize=True,
        add_generation_prompt=True,enable_thinking=False,truncation=False,
        return_tensors='pt',return_dict=True)
    require(encoded['input_ids'].shape[0]==1 and encoded['input_ids'].shape[1]<=256)
    output=model.generate(**encoded,**generation_settings())
    return tokenizer.decode(output[0][encoded['input_ids'].shape[1]:],
        skip_special_tokens=True,clean_up_tokenization_spaces=False)


def _native(cfg,checkpoint):
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    torch.set_num_threads(2);torch.manual_seed(42)
    tokenizer=AutoTokenizer.from_pretrained(cfg['model_dir'],local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(cfg['model_dir'],local_files_only=True,
        trust_remote_code=False,use_safetensors=True,torch_dtype=torch.bfloat16,
        device_map=None,attn_implementation='eager')
    if cfg['arm']=='FROZEN_SINGLE_ADAPTER':
        from peft import PeftModel
        model=PeftModel.from_pretrained(model,cfg['adapter_dir'],is_trainable=False,
            local_files_only=True,autocast_adapter_dtype=True)
    model.eval();model.requires_grad_(False);model.config.use_cache=True
    require(not model.training and not any(p.requires_grad for p in model.parameters()))
    with torch.inference_mode():
        return collect_contexts(lambda prompt:generate_text(model,tokenizer,prompt),checkpoint)


def run_generate(config_path):
    cfg=_admission(config_path)
    checkpoint=PrivateCheckpoint(cfg['receipt_path'])
    report=dict(schema='manager.costello-generation-receipt.v1',status='INITIALIZED',
        code_version=cfg['code_version'],config_sha256=_digest_file(Path(config_path)),
        arm=cfg['arm'],adapter_freeze_sha256=ADAPTER_FREEZE_SHA256,
        design_sha256=DESIGN_SHA256,grid_size=102,generation=None,
        proof='P0',human_benefit='NOT_MEASURED',model_adoption='HOLD',can_execute=False)
    checkpoint(report)
    def emit(grid):
        report.update(status=grid['status'],generation=grid)
        checkpoint(report)
    try:
        _native(cfg,emit)
        return report
    except BaseException:
        report['status']='FAILED'
        checkpoint(report)
        raise
