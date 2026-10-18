"""Household synthesis commands with separate fitting and reference access."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from .artifacts import canonical,read_artifact,write_artifact,write_bytes,sha256
from .population.contracts import PopulationDataError
from .population.households import Person,Household,HouseholdControls
from .population.household_sources import fetch_household_sources,verify_sources
from .population.pums import read_pums,read_controls
from .population.household_fit import household_weights
from .population.integerize import integerize
from .population.household_export import export_population,audit_population,file_hash
from .benchmarks.households import evaluate_households
from .benchmarks.population import TRACKS

CONFIG_PATH=Path(__file__).resolve().parents[2]/'config/household-v0.json'
EXPECTED_CONFIG={'schema_version':1,'state':'44','period':'2020-2024',
 'universe':'Occupied housing units and their residents; group quarters excluded',
 'cell_order':['family_1','family_2','family_3plus','nonfamily_1','nonfamily_2','nonfamily_3plus'],
 'methods':['baseline','calibrated'],'tolerance':1e-10,'max_iterations':1000,'rng_seed':20261018,
 'integerization_replicates':10,'max_households':1000000,'max_persons':5000000}


def configuration():
    config=json.loads(CONFIG_PATH.read_text())
    if config!=EXPECTED_CONFIG:raise PopulationDataError('household config differs from this implementation contract')
    return config,hashlib.sha256(canonical(config)).hexdigest()


def identity():
    from .cli import identity as base_identity
    return dict(base_identity(),household_config_sha256=configuration()[1])


def fetch(args):fetch_household_sources(Path(args.out))


def prepare(args):
    start=time.perf_counter();directory=Path(args.input);out=Path(args.out)
    source=verify_sources(directory);households,stats=read_pums(directory/'housing.zip',directory/'persons.zip')
    controls,joint=read_controls(directory/'b11016.dat');config,config_hash=configuration()
    source_hash=sha256(directory/'source.json')
    payloads={'households.jsonl':[asdict(h) for h in households],
              'controls.json':{'controls':asdict(controls),'source_sha256':source_hash},
              'reference.json':{'joint':joint,'source_sha256':source_hash}}
    hashes={name:write_artifact(out/name,payload) for name,payload in payloads.items()}
    write_artifact(out/'manifest.json',{'schema_version':1,'source':source,'source_sha256':source_hash,
        'config':config,'config_sha256':config_hash,'code':identity(),'sample':stats,'artifacts':hashes,
        'elapsed_seconds':time.perf_counter()-start})


def load_prepared(directory,*,include_reference=False):
    directory=Path(directory);manifest=read_artifact(directory/'manifest.json');config,config_hash=configuration()
    if manifest['config']!=config or manifest['config_sha256']!=config_hash or manifest['code']!=identity():
        raise PopulationDataError('prepared configuration/code mismatch')
    if set(manifest['artifacts'])!={'households.jsonl','controls.json','reference.json'}:raise PopulationDataError('prepared coverage mismatch')
    names=['households.jsonl','controls.json']+(['reference.json'] if include_reference else [])
    for name in names:
        if file_hash(directory/name)!=manifest['artifacts'][name]:raise PopulationDataError(f'prepared artifact changed: {name}')
    data=read_artifact(directory/'households.jsonl');households=[]
    for value in data:
        value=dict(value);value['persons']=tuple(Person(**p) for p in value['persons']);households.append(Household(**value))
    if not households or tuple(h.serialno for h in households)!=tuple(sorted({h.serialno for h in households})):
        raise PopulationDataError('household seeds must be unique and sorted')
    if len(households)!=manifest['sample']['occupied_households'] or sum(h.size for h in households)!=manifest['sample']['household_persons']:
        raise PopulationDataError('prepared sample coverage mismatch')
    payload=read_artifact(directory/'controls.json');values=dict(payload['controls'])
    values['family']=tuple(values['family']);values['size']=tuple(values['size']);controls=HouseholdControls(**values)
    if payload['source_sha256']!=manifest['source_sha256']:raise PopulationDataError('control snapshot mismatch')
    reference=None
    if include_reference:
        ref=read_artifact(directory/'reference.json')
        if ref['source_sha256']!=manifest['source_sha256']:raise PopulationDataError('reference snapshot mismatch')
        reference=tuple(ref['joint'])
    return tuple(households),controls,manifest,reference


def synthesize(args):
    start=time.perf_counter();prepared=Path(args.prepared);out=Path(args.out)
    households,controls,manifest,_=load_prepared(prepared);config,config_hash=configuration()
    weights=household_weights(households,controls,args.method,tolerance=config['tolerance'],max_iterations=config['max_iterations'])
    copies=integerize(weights,controls.total,config['rng_seed'])
    weight_hash=write_artifact(out/'weights.json',{'method':args.method,'weights':weights,'copies':copies,
        'rng_seed':config['rng_seed'],'source_sha256':manifest['source_sha256'],'config_sha256':config_hash})
    expanded=export_population(households,copies,out);audit=audit_population(households,copies,out)
    hashes=dict(expanded['artifacts'],**{'weights.json':weight_hash})
    write_artifact(out/'manifest.json',{'schema_version':1,'method':args.method,'artifacts':hashes,'audit':audit,
        'prepared_manifest_sha256':sha256(prepared/'manifest.json'),'source_sha256':manifest['source_sha256'],
        'config_sha256':config_hash,'code':identity(),'reference_access':False,'paid_model_calls':0,
        'elapsed_seconds':time.perf_counter()-start})


def score(args):
    start=time.perf_counter();prepared=Path(args.prepared);households,controls,manifest,reference=load_prepared(prepared,include_reference=True)
    config,config_hash=configuration();results={};runs={}
    for directory in map(Path,args.run):
        run=read_artifact(directory/'manifest.json');method=run['method']
        if method not in config['methods'] or method in results:raise PopulationDataError('unknown/duplicate household method')
        required={'prepared_manifest_sha256':sha256(prepared/'manifest.json'),'source_sha256':manifest['source_sha256'],
                  'config_sha256':config_hash,'code':identity(),'reference_access':False,'paid_model_calls':0}
        if any(run.get(k)!=v for k,v in required.items()):raise PopulationDataError('run provenance mismatch')
        if set(run['artifacts'])!={'households.csv','persons.csv','weights.json'}:raise PopulationDataError('run artifact coverage mismatch')
        for name,expected in run['artifacts'].items():
            if file_hash(directory/name)!=expected:raise PopulationDataError(f'run artifact changed: {name}')
        fitted=read_artifact(directory/'weights.json')
        if fitted['method']!=method or fitted['source_sha256']!=manifest['source_sha256'] or fitted['config_sha256']!=config_hash or fitted['rng_seed']!=config['rng_seed']:
            raise PopulationDataError('weight provenance mismatch')
        weights=tuple(fitted['weights']);copies=tuple(fitted['copies'])
        if copies!=integerize(weights,controls.total,config['rng_seed']):raise PopulationDataError('integer copies do not reproduce from declared seed')
        audit=audit_population(households,copies,directory)
        if audit!=run['audit']:raise PopulationDataError('run audit mismatch')
        result=evaluate_households(households,weights,copies,controls,reference)
        if method=='calibrated' and result['weighted']['max_marginal_error_fraction']>config['tolerance']:
            raise PopulationDataError('calibrated residual exceeds tolerance')
        repetitions=[]
        for seed in range(config['rng_seed'],config['rng_seed']+config['integerization_replicates']):
            n=integerize(weights,controls.total,seed)
            metric=evaluate_households(households,weights,n,controls,reference)['integer']
            repetitions.append({'seed':seed,'tvd':metric['tvd'],'max_marginal_error_households':metric['max_marginal_error_households'],'persons':metric['persons']})
        result.update({'audit':audit,'integerization_replicates':repetitions});results[method]=result;runs[method]=run
    if set(results)!=set(config['methods']):raise PopulationDataError('baseline and calibrated runs are both required')
    limitations=['Single-state retrospective synthesis, not evidence of geographic transfer.',
        'PUMS and detailed ACS tables share a survey source; checks are not fully independent.',
        'Household replication preserves observed members, not every target or person-weighted distribution.',
        'Structural zeros are preserved; unsupported household types cannot be invented.',
        'Replicate-weight sampling uncertainty is not propagated; seed variation is only integerization variation.',
        'No behavior, policy, execution or field benefit is measured. No actual address or identity is reconstructed.']
    report={'stage':'empirical_household_synthesis','tracks':dict(TRACKS),'paid_model_calls':0,
        'state':'44','period':'2020-2024','universe':config['universe'],'sample':manifest['sample'],
        'controls':asdict(controls),'reference_joint':reference,'cell_order':config['cell_order'],'results':results,
        'source':manifest['source'],'source_sha256':manifest['source_sha256'],'config_sha256':config_hash,'code':identity(),
        'prepared_manifest_sha256':sha256(prepared/'manifest.json'),'runs':runs,'limitations':limitations,
        'elapsed_seconds':time.perf_counter()-start}
    lines=['# 世帯人口v0の実測','', 'Rhode Island、2020–2024 ACS。通常居住世帯のみ。','',
        '|方式|段階|6セルTVD|周辺制約の最大差（世帯）|世帯数|人数|','|---|---|---:|---:|---:|---:|']
    for method in config['methods']:
        for stage in ('weighted','integer'):
            v=results[method][stage];lines.append(f"|{method}|{stage}|{v['tvd']:.8f}|{v['max_marginal_error_households']:.6f}|{v['households']:.3f}|{v['persons']:.3f}|")
    lines+=['','世帯総数の一致は全人口・全属性の一致を意味しない。PUMSとACSは同じ調査由来。推計誤差の伝播と行動/介入評価は未実装。','']
    out=Path(args.out);write_bytes(out/'report.md','\n'.join(lines).encode());write_artifact(out/'report.json',report)


def add_household_commands(commands):
    p=commands.add_parser('fetch-households');p.add_argument('--out',required=True);p.set_defaults(handler=fetch)
    p=commands.add_parser('prepare-households');p.add_argument('--input',required=True);p.add_argument('--out',required=True);p.set_defaults(handler=prepare)
    p=commands.add_parser('synthesize-households');p.add_argument('--prepared',required=True);p.add_argument('--out',required=True)
    p.add_argument('--method',choices=('baseline','calibrated'),required=True);p.set_defaults(handler=synthesize)
    p=commands.add_parser('score-households');p.add_argument('--prepared',required=True);p.add_argument('--run',action='append',required=True);p.add_argument('--out',required=True);p.set_defaults(handler=score)
