"""Private finite original-candidate comparison; G7 and native work stay separate.

External0400 config hashes establish consistency of an operator assertion, not
cryptographic authentication of CI, root authority or parent process success.
"""
from __future__ import annotations

from contextlib import contextmanager
import gzip
from hashlib import sha256
from io import BytesIO
import importlib.metadata
import json
from math import isfinite
import os
from pathlib import Path
import re
import stat

from .helpsteer2_candidate_eval import (_json,_hash,_verify_file,_verify_model,
    completion_mask,CompletionMask,_choose,_summary,_QUALITY)
from .helpsteer2_candidate_sft import (PrivateCheckpoint,SelectedCase,_canonical,_canonical_hash,
    _digest_file,_path,_verify_evidence,_inventory_metadata,validate_manifest,
    verify_package_versions,validate_saved_config,SOURCE_FILES as TRAINING_SOURCE_FILES)

PROTOCOL_SHA256='cb7d6cebf90549e8fa17b8cb393efaa00cdcd4783d9cb4edaf3da343533ac2f9'
PARENT_SHA256='eb2e585321d954d507af52b1bf71db9eb3b7ae3150273484909b6aeeae48a53d'
MANIFEST_SHA256='7547ff63f7c06f8196689b3890288417154012d71e9609d0a3db232eeb0f182e'
RIGHTS_SHA256='088f6cc5a17f8ff3c83dfc10b44bca70dbd0855d3dd0c8b1063727ff2271225d'
UNAVAILABLE='HELPSTEER2_FIXED_ADAPTER_EVAL_UNAVAILABLE'
ROOT=Path(__file__).resolve().parents[1]
SOURCE_FILES=(TRAINING_SOURCE_FILES-{'scripts/train_helpsteer2_candidate_sft.py'}) | {
    'manager_core/helpsteer2_fixed_adapter_eval.py','scripts/evaluate_helpsteer2_fixed_adapter.py'}
EVIDENCE_KEYS=frozenset(('G7','parent_training','artifact_freeze','exposure_reaffirmation',
    'official_ci','independent_review','source_boundary','resources'))
POLICIES=('NO_ACTION','SHORTER_CANDIDATE_RULE','NATIVE_BASE_QWEN','FIXED_LORA_ADAPTER')
MODEL_POLICIES=POLICIES[2:]
INPUT_KEYS=frozenset(('protocol_path','parent_protocol_path','manifest_path','data_dir',
                     'model_dir','rights_path','adapter_dir'))


def _require(condition):
    if not condition:raise ValueError(UNAVAILABLE)


def validate_protocol(payload,expected_sha256):
    _require(type(payload) is bytes and expected_sha256==PROTOCOL_SHA256)
    _require(sha256(payload).hexdigest()==PROTOCOL_SHA256)
    return _json(payload)


def validate_parent(payload,protocol):
    _require(type(payload) is bytes and len(payload)==protocol['frozen_training_protocol']['bytes'])
    _require(sha256(payload).hexdigest()==PARENT_SHA256==protocol['frozen_training_protocol']['sha256'])
    return _json(payload)


def validate_rights(payload,protocol):
    _require(payload['schema']=='manager.source-rights.v1')
    matches=[r for r in payload['sources'] if r['id']==protocol['rights']['record_id']]
    _require(len(matches)==1)
    _require(sha256(_canonical(matches[0])).hexdigest()==RIGHTS_SHA256==protocol['rights']['record_canonical_sha256'])
    return matches[0]


def verify_adapter_inventory(directory,training,expected_digest,parent):
    directory=_path(directory,private=True)
    _require(directory.is_dir() and directory.stat().st_uid==os.getuid()
             and stat.S_IMODE(directory.stat().st_mode)==0o700)
    _require(training['schema']=='manager.helpsteer2-private-sft-result.v1'
             and training['status']=='COMPLETED' and training['event']=='ARTIFACT_FROZEN')
    _require(training['scientific_protocol_sha256']==PARENT_SHA256 and training['manifest_sha256']==MANIFEST_SHA256)
    for key in ('model_files','source_artifacts','packages'):_require(training[key]==parent[key])
    inventory=training['artifact_inventory']
    _inventory_metadata(inventory)
    _require(sha256(_canonical(inventory)).hexdigest()==training['artifact_inventory_sha256']==expected_digest)
    _require({p.name for p in directory.iterdir()}==set(inventory))
    for name,pin in inventory.items():
        path=_path(directory/name,private=True,file=True,mode=0o600)
        _require(path.stat().st_size==pin['bytes'] and _digest_file(path)==pin['sha256'])


def validate_execution_config(path,*,protocol,parent,code_version,input_paths,metadata_output_path):
    path=_path(path,private=True,file=True,mode=0o400)
    config=_json(path.read_bytes())
    _require(config['kind']=='manager.helpsteer2-fixed-adapter-eval-execution.v1')
    _require(config['acceptance_status']=='ACCEPTED_ONE_OFFLINE_FIXED_ADAPTER_EVALUATION_ATTEMPT')
    _require(config['accepted_gates']==['G7'] and config['can_execute'] is False)
    _require(config['parent_training_normal_exit_verified'] is True)
    _require(config['scientific_protocol_sha256']==PROTOCOL_SHA256)
    _require(config['frozen_training_protocol_sha256']==PARENT_SHA256)
    _require(config['manifest_sha256']==MANIFEST_SHA256 and config['rights_record_sha256']==RIGHTS_SHA256)
    _require(type(code_version) is str and re.fullmatch('[a-f0-9]{40}',code_version) is not None)
    _require(config['code_version']==code_version and config['cwd']==str(ROOT) and Path.cwd().resolve()==ROOT)
    _require(type(config['max_cumulative_wall_seconds']) is int and config['max_cumulative_wall_seconds']==900)
    _require(type(config['max_process_group_rss_bytes']) is int and config['max_process_group_rss_bytes']==6442450944)
    _require(set(input_paths)==set(config['input_paths'])==INPUT_KEYS)
    for key,actual in input_paths.items():_require(str(_path(actual))==str(_path(config['input_paths'][key])))
    _require(str(_path(metadata_output_path,private=True))==str(_path(config['output'],private=True)))
    _require(set(config['source_files'])==SOURCE_FILES)
    for name,digest in config['source_files'].items():
        _require(type(digest) is str and re.fullmatch('[a-f0-9]{64}',digest) is not None)
        _require(_digest_file(_path(ROOT/name,file=True))==digest)
    _require(set(config['acceptance_evidence'])==EVIDENCE_KEYS)
    for pin in (*config['acceptance_evidence'].values(),config['watchdog'],config['training_result']):
        _verify_evidence(pin)
        _require(Path(pin['path'])!=path)
    raw=Path(config['training_result']['path']).read_bytes()
    _require(sha256(raw).hexdigest()==config['training_result']['sha256'])
    training=_json(raw)
    verify_adapter_inventory(input_paths['adapter_dir'],training,config['adapter_inventory_sha256'],parent)
    validate_saved_config(_json((Path(input_paths['adapter_dir'])/'adapter_config.json').read_bytes()),input_paths['model_dir'])
    return config,training


def read_selected_rows(path,source,wanted):
    payload=Path(path).read_bytes();source.verify_content(payload)
    _require(type(wanted) is set and all(type(i) is int and i>0 for i in wanted))
    rows={}
    with gzip.open(BytesIO(payload),'rt',encoding='utf-8') as stream:
        for index,line in enumerate(stream,1):
            if index in wanted:rows[index]=_json(line)
    _require(set(rows)==wanted)
    return rows


def reconstruct_cases(specs,preferences,quality,slice_name):
    final=slice_name=='final16'
    _require(slice_name in ('development8','final16') and bool(specs))
    ids=[s['source_preference_row_1based'] for s in specs]
    _require(all(type(i) is int and i>0 for i in ids) and len(set(ids))==len(ids) and set(ids)==set(preferences))
    qids=[i for s in specs for i in s['quality_rows_1based']]
    _require(len(set(qids))==2*len(ids) and set(qids)==set(quality))
    cases=[]
    for spec in specs:
        row=preferences[spec['source_preference_row_1based']]
        raw,native,semantic=('val','validation','final_test') if final else ('train','train','dev')
        _require((spec['raw_preference_split'],spec['native_split'],spec['proposed_split'])==(raw,native,semantic))
        _require(row['split']==raw and _hash(row['prompt'])==spec['prompt_exact_sha256']
                 and _canonical_hash(row['prompt'])==spec['prompt_canonical_sha256'])
        strength=row['preference_strength']
        _require(type(strength) is int and strength in (-3,-2,-1,1,2,3))
        responses=(row['response_1'],row['response_2']);labels=[]
        for i,response in enumerate(responses):
            _require(_hash(response)==spec['response_exact_sha256'][i]
                     and _canonical_hash(response)==spec['response_canonical_sha256'][i])
            q=quality[spec['quality_rows_1based'][i]]
            _require(q['prompt']==row['prompt'] and q['response']==response)
            values={k:q[k] for k in _QUALITY}
            _require(all(type(v) is int and 0<=v<=4 for v in values.values()));labels.append(values)
        cases.append(SelectedCase(spec['source_preference_row_1based'],spec['prompt_exact_sha256'],tuple(spec['response_exact_sha256']),
            1 if strength<0 else 2,strength,tuple(spec['quality_rows_1based']),tuple(labels),
            tuple(spec['full_sequence_token_counts']),row['prompt'],responses,native,semantic,
            tuple(spec['completion_mask_token_lengths_by_candidate'])))
    _require(len({c.prompt_sha256 for c in cases})==len(cases))
    return tuple(cases)


def verify_native_source(protocol):
    pin=protocol['native_inference']['api_source_audit']
    distribution=importlib.metadata.distribution('peft')
    path=distribution.locate_file(pin['package_relative_path'])
    _require(Path(path).stat().st_size==pin['bytes'] and _digest_file(path)==pin['sha256'])


def load_verified_inputs(*,protocol_path,expected_sha256,parent_protocol_path,manifest_path,data_dir,model_dir,
                         rights_path,adapter_dir,code_version,execution_config_path,metadata_output_path):
    try:
        protocol=validate_protocol(_path(protocol_path,file=True).read_bytes(),expected_sha256)
        parent=validate_parent(_path(parent_protocol_path,file=True).read_bytes(),protocol)
        inputs=dict(protocol_path=protocol_path,parent_protocol_path=parent_protocol_path,manifest_path=manifest_path,
            data_dir=data_dir,model_dir=model_dir,rights_path=rights_path,adapter_dir=adapter_dir)
        config,training=validate_execution_config(execution_config_path,protocol=protocol,parent=parent,
            code_version=code_version,input_paths=inputs,metadata_output_path=metadata_output_path)
        rights=validate_rights(_json(_path(rights_path,file=True).read_bytes()),protocol)
        raw=_path(manifest_path,file=True).read_bytes()
        _require(len(raw)==protocol['shared_manifest']['bytes'] and sha256(raw).hexdigest()==MANIFEST_SHA256)
        manifest=_json(raw);validate_manifest(manifest)
        verify_package_versions(parent);verify_native_source(protocol)
        data_dir=_path(data_dir);_require(data_dir.is_dir())
        sources={name:_verify_file(_path(data_dir/name,file=True),pin,source_id='helpsteer2:'+name,
            url='https://huggingface.co/datasets/nvidia/HelpSteer2/resolve/'+parent['dataset_revision']+'/'+name)
            for name,pin in parent['source_artifacts'].items()}
        _verify_model(_path(model_dir),parent['model_files'])
        prefs=read_selected_rows(data_dir/'preference/preference.jsonl.gz',sources['preference/preference.jsonl.gz'],
            {s['source_preference_row_1based'] for name in ('development8','final16') for s in manifest[name]})
        groups={}
        for name,filename in (('development8','train.jsonl.gz'),('final16','validation.jsonl.gz')):
            specs=manifest[name]
            quality=read_selected_rows(data_dir/filename,sources[filename],{i for s in specs for i in s['quality_rows_1based']})
            selected={s['source_preference_row_1based']:prefs[s['source_preference_row_1based']] for s in specs}
            groups[name]=reconstruct_cases(specs,selected,quality,name)
        return protocol,parent,rights,groups,config,training
    except Exception:
        raise ValueError(UNAVAILABLE) from None


def build_pair_masks(case,tokenizer):
    user=[dict(role='user',content=case.prompt)]
    prefix=tokenizer.apply_chat_template(user,tokenize=True,add_generation_prompt=True,enable_thinking=False,truncation=False)
    masks=tuple(completion_mask(prefix,tokenizer.apply_chat_template(user+[dict(role='assistant',content=response)],
        tokenize=True,add_generation_prompt=False,enable_thinking=False,truncation=False)) for response in case.responses)
    _check_masks(case,masks)
    return masks


def _check_masks(case,masks):
    _require(len(masks)==2 and all(type(m) is CompletionMask for m in masks))
    _require(tuple(len(m.input_ids) for m in masks)==case.full_sequence_token_counts)
    _require(tuple(m.scored_tokens for m in masks)==case.completion_token_counts)


def _policy_summary(rows):
    result=_summary(rows)
    return dict(assigned=result['assigned'],attempted=result['attempted'],valid_completed=result['covered'],
        failed=result['failed'],unknown=result['unknown'],not_run=result['unattempted'],abstained=result['abstained'],
        correct=result['correct'],covered=result['covered'],coverage=result['coverage'],conditional_accuracy=result['conditional_accuracy'],
        ties=sum(r['status']=='COMPLETED' and r['tie'] is True for r in rows),nll=None,groups=rows)


def _paired(base,adapter,*,rule=False):
    left={r['preference_row_1based']:r for r in base if r['status']=='COMPLETED'}
    right={r['preference_row_1based']:r for r in adapter if r['status']=='COMPLETED'}
    ids=sorted(set(left)&set(right));cells=[0,0,0,0];difference=0
    for row_id in ids:
        a=left[row_id]['choice']==left[row_id]['human_choice'];b=right[row_id]['choice']==right[row_id]['human_choice']
        cells[(0 if a else 2)+(0 if b else 1)]+=1;difference+=int(b)-int(a)
    result=dict(paired_valid_count=len(ids),paired_missing_or_failed_count=len(base)-len(ids),
        paired_ids=ids,paired_assigned_coverage=len(ids)/len(base))
    if not rule:
        result.update(zip(('base_correct_adapter_correct','base_correct_adapter_wrong','base_wrong_adapter_correct','base_wrong_adapter_wrong'),cells))
    result['adapter_minus_rule_accuracy' if rule else 'adapter_minus_base_accuracy']=difference/len(ids) if ids else None
    return result


def evaluate_cases(groups,encode,mean_loss,*,progress=None):
    """Finite ordered candidate requests; native seam only, never a new engine."""
    _require(bool(groups) and set(groups)<={'development8','final16'})
    rows={}
    for name in ('development8','final16'):
        if name not in groups:continue
        cases=groups[name];_require(bool(cases) and len({c.row_id for c in cases})==len(cases))
        template=[dict(preference_row_1based=c.row_id,prompt_sha256=c.prompt_sha256,response_sha256=list(c.response_sha256),
            human_choice=c.human_choice,preference_strength=c.preference_strength,quality_rows_1based=list(c.quality_rows),
            full_sequence_token_counts=list(c.full_sequence_token_counts),completion_token_counts=None,
            status='NOT_RUN',choice=None,tie=None,nll=None) for c in cases]
        rows[name]={policy:_json(json.dumps(template)) for policy in POLICIES}
    assigned=sum(len(c) for c in groups.values())*4
    requests=dict(assigned=assigned,attempted=0,completed=0,failed=0,unknown=0,not_run=assigned)
    def emit():
        slices={name:dict(policies={p:_policy_summary(rr) for p,rr in policies.items()},paired=dict(
            base_adapter=_paired(policies['NATIVE_BASE_QWEN'],policies['FIXED_LORA_ADAPTER']),
            adapter_rule=_paired(policies['SHORTER_CANDIDATE_RULE'],policies['FIXED_LORA_ADAPTER'],rule=True)))
            for name,policies in rows.items()}
        snapshot=_json(json.dumps(dict(slices=slices,model_requests=requests),allow_nan=False))
        if progress is not None:progress(snapshot)
        return snapshot
    emit()
    encoded={}
    # All masks must pass before the first model request, including final pairs.
    for name in rows:
        encoded[name]=[]
        for case in groups[name]:
            masks=tuple(encode(case));_check_masks(case,masks);encoded[name].append(masks)
    for name,policies in rows.items():
        for index,(case,masks) in enumerate(zip(groups[name],encoded[name])):
            for policy in POLICIES:policies[policy][index]['completion_token_counts']=[m.scored_tokens for m in masks]
            policies['NO_ACTION'][index]['status']='ABSTAIN'
            rule=policies['SHORTER_CANDIDATE_RULE'][index]
            rule.update(status='COMPLETED')
            rule['choice'],rule['tie']=_choose(tuple(m.scored_tokens for m in masks),case.response_sha256)
    emit();stopped=False
    for name,policies in rows.items():
        for index,(case,masks) in enumerate(zip(groups[name],encoded[name])):
            for policy in MODEL_POLICIES:
                if stopped:continue
                row=policies[policy][index];row['nll']=[None,None]
                for candidate,mask in enumerate(masks):
                    row['status']='UNKNOWN';requests['attempted']+=1;requests['unknown']+=1;requests['not_run']-=1
                    emit() # Durable uncertainty before native forward.
                    try:
                        value=mean_loss(policy,case,mask)
                        _require(type(value) in (int,float) and isfinite(value) and value>=0 and isfinite(value*mask.scored_tokens))
                        row['nll'][candidate]=dict(mean=value,summed=value*mask.scored_tokens,scored_tokens=mask.scored_tokens)
                        requests['completed']+=1
                    except Exception:
                        row['status']='FAILED';requests['failed']+=1;stopped=True
                    requests['unknown']-=1
                    if stopped:emit();break
                    if candidate==1:
                        row['choice'],row['tie']=_choose(tuple(item['mean'] for item in row['nll']),case.response_sha256)
                        row['status']='COMPLETED'
                    emit()
    return emit()


def _regular_state(model,enabled):
    state=model.get_model_status()
    _require(model.training is False and state.enabled is enabled and state.merged_adapters==[]
             and state.active_adapters==['default'] and state.trainable_params==0)


@contextmanager
def base_condition(model):
    _regular_state(model,True)
    try:
        with model.disable_adapter():
            _regular_state(model,False)
            yield
    finally:
        # PEFT enable_adapters/set_adapter restores enabled state and enables
        # active adapter gradients; restore our inference-only flag as well.
        model.requires_grad_(False)
        _regular_state(model,True)


def _check_native_model(model,torch):
    _regular_state(model,True)
    _require(all(not module.training for module in model.modules()))
    config=model.config;_require(config.model_type=='qwen3' and config.num_hidden_layers==28 and config.hidden_size==1024)
    expected={}
    for layer in range(28):
        for target,heads in (('q_proj',config.num_attention_heads),('v_proj',config.num_key_value_heads)):
            prefix=f'base_model.model.model.layers.{layer}.self_attn.{target}.lora_'
            expected[prefix+'A.default.weight']=(8,1024)
            expected[prefix+'B.default.weight']=(heads*config.head_dim,8)
    adapter={name:p for name,p in model.named_parameters() if '.lora_' in name}
    _require(set(adapter)==set(expected))
    for name,p in model.named_parameters():
        _require(p.requires_grad is False)
        if name in expected:_require(tuple(p.shape)==expected[name] and p.dtype==torch.float32 and bool(torch.isfinite(p).all().item()))
        else:_require(p.dtype==torch.bfloat16)
    return adapter


def _native_evaluate(groups,configuration,progress):
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from peft import PeftModel
    from safetensors import safe_open
    torch.set_num_threads(2);torch.manual_seed(42)
    tokenizer=AutoTokenizer.from_pretrained(str(configuration['model_dir']),local_files_only=True,trust_remote_code=False)
    base=AutoModelForCausalLM.from_pretrained(str(configuration['model_dir']),local_files_only=True,trust_remote_code=False,
        use_safetensors=True,torch_dtype=torch.bfloat16,device_map=None,attn_implementation='eager')
    base.config.use_cache=False;base.eval()
    model=PeftModel.from_pretrained(base,str(configuration['adapter_dir']),is_trainable=False,
        local_files_only=True,autocast_adapter_dtype=True)
    model.eval();model.requires_grad_(False)
    adapter=_check_native_model(model,torch)
    config=_json((Path(configuration['adapter_dir'])/'adapter_config.json').read_bytes())
    _require(config['peft_type']=='LORA' and config['r']==config['lora_alpha']==8 and config['lora_dropout']==0
             and config['bias']=='none' and set(config['target_modules'])=={'q_proj','v_proj'}
             and config['modules_to_save'] is None and config['task_type']=='CAUSAL_LM' and config['inference_mode'] is True
             and config['base_model_name_or_path']==str(configuration['model_dir']))
    with safe_open(str(Path(configuration['adapter_dir'])/'adapter_model.safetensors'),framework='pt',device='cpu') as saved:
        _require(set(saved.keys())=={name.replace('.default.weight','.weight') for name in adapter})
        for name,p in adapter.items():
            value=saved.get_tensor(name.replace('.default.weight','.weight'))
            _require(bool(torch.isfinite(value).all().item()) and torch.equal(value,p.detach().cpu()))
    with base_condition(model):pass # Check native disabled/restored semantics before any score.
    def mean_loss(policy,case,mask):
        ids=torch.tensor([mask.input_ids],dtype=torch.long,device='cpu')
        labels=torch.tensor([mask.labels],dtype=torch.long,device='cpu')
        def forward():
            with torch.inference_mode():
                return float(model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels,use_cache=False).loss.item())
        if policy=='NATIVE_BASE_QWEN':
            with base_condition(model):return forward()
        _regular_state(model,True)
        try:return forward()
        finally:_regular_state(model,True)
    return evaluate_cases(groups,lambda c:build_pair_masks(c,tokenizer),mean_loss,progress=progress)


def run_local(*,progress=None,**configuration):
    checkpoint=None;report=None;old_umask=os.umask(0o077)
    try:
        _require(re.fullmatch('[a-f0-9]{40}',configuration['code_version']) is not None)
        checkpoint=PrivateCheckpoint(configuration['metadata_output_path'])
        report=dict(schema='manager.helpsteer2-fixed-adapter-eval-result.v1',status='NOT_RUN',event='PREIMPORT',
            scientific_protocol_sha256=PROTOCOL_SHA256,frozen_training_protocol_sha256=PARENT_SHA256,
            manifest_sha256=MANIFEST_SHA256,rights_record_sha256=RIGHTS_SHA256,code_version=configuration['code_version'],
            completion_requires_successful_process_exit=True,can_execute=False,proof_level='P0_FINITE_ORIGINAL_CANDIDATES_ONLY',
            human_benefit='NOT_MEASURED',suffering_reduction='NOT_MEASURED',behavior_change=None,harms=None,pressure=None,dependency=None,
            base_numeric_in_memory_unchanged='NOT_MEASURED',slices={},model_requests=None)
        def publish():
            checkpoint(report)
            if progress is not None:progress(_json(json.dumps(report,allow_nan=False)))
        publish()
        protocol,parent,rights,groups,config,training=load_verified_inputs(**configuration)
        _require(len(groups['development8'])==8 and len(groups['final16'])==16)
        report.update(status='IN_PROGRESS',event='IMPORT_LOAD_START',adapter_inventory_sha256=training['artifact_inventory_sha256'],
            execution_config_sha256=_digest_file(configuration['execution_config_path']),model_files=parent['model_files'],
            packages=parent['packages'],attribution=rights['attribution'])
        publish()
        # PEFT type detection itself does not consistently forward local_files_only.
        env_keys=('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_DATASETS_OFFLINE')
        previous={key:os.environ.get(key) for key in env_keys}
        try:
            for key in env_keys:os.environ[key]='1'
            from scripts.evaluate_xstest_refusal import _silence
            def scoring_progress(results):
                report.update(results,event='SCORING');publish()
            with _silence():results=_native_evaluate(groups,configuration,scoring_progress)
        finally:
            for key,value in previous.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
        report.update(results)
        requests=results['model_requests']
        _require(requests['assigned']==requests['attempted']==requests['completed']==96
                 and requests['failed']==requests['unknown']==requests['not_run']==0)
        report.update(status='COMPLETED',event='EVALUATION_RETURNED');publish()
        _require(checkpoint.durability_confirmed)
        return _json(json.dumps(report,allow_nan=False))
    except (Exception,KeyboardInterrupt):
        if report is not None:
            report.update(status='FAILED',event='FAILED',metadata_write_failure_observed=checkpoint.write_failure_observed)
            try:checkpoint(report)
            except Exception:
                try:checkpoint.discard_unconfirmed_completion()
                except Exception:pass # External process failure remains required under broken storage.
        raise ValueError(UNAVAILABLE) from None
    finally:os.umask(old_umask)
