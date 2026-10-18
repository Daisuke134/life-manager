"""Offline-capable population experiment commands, separated by responsibility."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time
import importlib.metadata
from .artifacts import canonical, read_artifact, sha256, write_artifact, write_bytes
from .population.acs import FIPS, fetch_acs_extract, read_acs_extract
from .population.contracts import SourceRef, JointTable, Marginals, FitResult, PopulationDataError
from .population.prepare import DEVELOPMENT, VALIDATION, CELL_ORDER, LEAVES, aggregate_b17001, partition_tables, marginalize, build_seed
from .population.fit import independent_population, fit_population
from .benchmarks.population import score_population, summarize_population, TRACKS

APP=Path(__file__).resolve().parents[2]


def configuration():
    config=json.loads((APP/'config/population-v0.json').read_text())
    expected={'table':'B17001','period':'2020-2024','cell_order':list(CELL_ORDER),'fips':list(FIPS),
              'development_fips':list(DEVELOPMENT),'validation_fips':list(VALIDATION),
              'methods':['independent','ipf'],'tolerance':1e-10,'max_iterations':1000,
              'schema_version':1,'evaluation_version':'population-fidelity-v0',
              'leaf_estimates':{key:[f'B17001_E{i:03}' for i in group] for key,group in zip(CELL_ORDER,LEAVES)}}
    if config!=expected: raise PopulationDataError('config differs from this implementation contract')
    return config, hashlib.sha256(canonical(config)).hexdigest()


def identity():
    paths=sorted((APP/'src/manager').rglob('*.py'))+[APP/'config/population-v0.json',APP/'requirements-population.lock']
    hashes={str(p.relative_to(APP)):sha256(p) for p in paths}
    return {'source_tree_sha256':hashlib.sha256(canonical(hashes)).hexdigest(),
            'python':sys.version.split()[0],
            'dependencies':{name:importlib.metadata.version(name) for name in ('ipfn','numpy','pandas')}}


def decode(data, cls):
    data=dict(data)
    if 'source' in data: data['source']=SourceRef(**data['source'])
    for field in ('counts','poverty','age'):
        if field in data:data[field]=tuple(data[field])
    return cls(**data)


def prepare(args):
    start=time.perf_counter();source,rows=read_acs_extract(Path(args.input))
    tables=tuple(aggregate_b17001(row,source) for row in rows if row['GEO_ID'][-2:]!='72')
    partitions=partition_tables(tables);tables=tuple(t for group in partitions.values() for t in group)
    tables=tuple(sorted(tables,key=lambda t:t.geo_id));config,config_hash=configuration()
    out=Path(args.out)
    payloads={'seed.json':{'counts':build_seed(partitions['development']),'source':asdict(source),
                          'development_geo_ids':[t.geo_id for t in partitions['development']],'config_sha256':config_hash},
              'marginals.jsonl':[asdict(marginalize(t)) for t in tables],
              'reference/all.jsonl':[asdict(t) for t in tables],
              'split.json':{k:[t.geo_id for t in v] for k,v in partitions.items()}}
    hashes={name:write_artifact(out/name,payload) for name,payload in payloads.items()}
    manifest={'schema_version':1,'source':asdict(source),'artifacts':hashes,'config':config,'config_sha256':config_hash,
              'code':identity(),'invalid_counts':0,'elapsed_seconds':time.perf_counter()-start}
    write_artifact(out/'manifest.json',manifest)


def reconstruct(args):
    start=time.perf_counter();config,config_hash=configuration()
    seed=read_artifact(Path(args.seed));raw_targets=read_artifact(Path(args.marginals))
    source=SourceRef(**seed['source']);expected_ids=['0400000US'+f for f in DEVELOPMENT]
    if seed['development_geo_ids']!=expected_ids or seed['config_sha256']!=config_hash:
        raise PopulationDataError('seed development/config provenance mismatch')
    targets=[decode(value,Marginals) for value in raw_targets]
    ids=[t.geo_id for t in targets]
    if len(ids)!=51 or set(ids)!={'0400000US'+f for f in FIPS} or any(t.source!=source for t in targets):
        raise PopulationDataError('marginal coverage/source mismatch')
    predictions=[]
    for target in sorted(targets,key=lambda t:t.geo_id):
        result=independent_population(target) if args.method=='independent' else fit_population(tuple(seed['counts']),target,
                tolerance=config['tolerance'],max_iterations=config['max_iterations'])
        predictions.append(asdict(result))
    output=Path(args.out)
    output_hash=write_artifact(output,predictions)
    write_artifact(Path(str(output)+'.run.json'),{'method':args.method,'prediction_sha256':output_hash,
        'seed_artifact_sha256':sha256(args.seed),'marginals_artifact_sha256':sha256(args.marginals),
        'config_sha256':config_hash,'code':identity(),'elapsed_seconds':time.perf_counter()-start,
        'reference_access':False,'paid_model_calls':0,'numerical_settings':{'tolerance':config['tolerance'],'max_iterations':config['max_iterations']}})


def score(args):
    start=time.perf_counter();manifest_path=Path(args.manifest);manifest=read_artifact(manifest_path)
    config,config_hash=configuration()
    if manifest['config']!=config or manifest['config_sha256']!=config_hash:raise PopulationDataError('manifest config mismatch')
    base=manifest_path.parent
    required={'seed.json','marginals.jsonl','split.json','reference/all.jsonl'}
    if set(manifest['artifacts'])!=required:raise PopulationDataError('manifest artifact coverage mismatch')
    for name,expected in manifest['artifacts'].items():
        if sha256(base/name)!=expected:raise PopulationDataError(f'prepared artifact changed: {name}')
    if sha256(args.reference)!=manifest['artifacts']['reference/all.jsonl']:raise PopulationDataError('wrong reference artifact')
    references=[decode(value,JointTable) for value in read_artifact(Path(args.reference))]
    partitions=partition_tables(references);source=SourceRef(**manifest['source'])
    if any(r.source!=source for r in references):raise PopulationDataError('reference source mismatch')
    split={k:[t.geo_id for t in v] for k,v in partitions.items()}
    if read_artifact(base/'split.json')!=split:raise PopulationDataError('split differs from fixed protocol')
    seed=read_artifact(base/'seed.json')
    if tuple(seed['counts'])!=build_seed(partitions['development']):raise PopulationDataError('seed is not development-only')
    expected_seed_hash=hashlib.sha256(json.dumps([float(x) for x in seed['counts']],separators=(',',':'),allow_nan=False).encode()).hexdigest()
    refs={r.geo_id:r for r in references};scores=[];runs={};per_region=[];inputs={}
    for path in map(Path,args.predictions):
        predictions=[decode(value,FitResult) for value in read_artifact(path)]
        methods={p.method for p in predictions};ids=[p.geo_id for p in predictions]
        if len(methods)!=1 or len(ids)!=51 or set(ids)!=set(refs):raise PopulationDataError('prediction coverage mismatch')
        method=next(iter(methods))
        if method in runs:raise PopulationDataError('duplicate prediction method')
        run=read_artifact(Path(str(path)+'.run.json'))
        checks={'method':method,'prediction_sha256':sha256(path),'seed_artifact_sha256':manifest['artifacts']['seed.json'],
                'marginals_artifact_sha256':manifest['artifacts']['marginals.jsonl'],'config_sha256':config_hash,
                'reference_access':False,'paid_model_calls':0,'code':identity(),
                'numerical_settings':{'tolerance':config['tolerance'],'max_iterations':config['max_iterations']}}
        if any(run.get(k)!=v for k,v in checks.items()):raise PopulationDataError('prediction run provenance mismatch')
        for p in predictions:
            if p.seed_sha256!=(expected_seed_hash if method=='ipf' else None):raise PopulationDataError('prediction seed hash mismatch')
            if p.max_residual>config['tolerance']:raise PopulationDataError('prediction residual exceeds tolerance')
            target=marginalize(refs[p.geo_id]);actual=marginalize(JointTable(p.geo_id,source,p.counts,refs[p.geo_id].total))
            residual=max(abs(a-b) for a,b in zip(actual.poverty+actual.age,target.poverty+target.age))/target.total
            if residual>config['tolerance']:raise PopulationDataError('prediction does not match target marginals')
            s=score_population(p,refs[p.geo_id]);scores.append(s);per_region.append(asdict(s))
        runs[method]=run;inputs[method]=sha256(path)
    if set(runs)!=set(config['methods']):raise PopulationDataError('both independent and ipf are required')
    summaries={}
    for name,group in partitions.items():
        ids={r.geo_id for r in group}
        summaries[name]=summarize_population([s for s in scores if s.geo_id in ids],group)
    report={'stage':'empirical_reconstruction','tracks':dict(TRACKS),'coverage':{'regions':51,'methods':2},
            'paid_model_calls':0,'partitions':summaries,'per_region':sorted(per_region,key=lambda s:(s['geo_id'],s['method'])),
            'source':asdict(source),'cell_order':list(CELL_ORDER),'split':split,'config_sha256':config_hash,
            'code':identity(),'manifest_sha256':sha256(manifest_path),'prediction_sha256':inputs,'runs':runs,
            'elapsed_seconds':time.perf_counter()-start,
            'limitations':['ACS point estimates are uncertain, not exact population truth.',
                'Retrospective reconstruction from marginals of the same source; not independent field validation.',
                'Development seed regions are not held out. Geographic split is not a random sample.',
                'Poverty status is not a direct measure of suffering. Behavior and intervention effects are not evaluated.']}
    lines=['# 人口v0：公開集計の復元結果','', 'ACS 2020–2024 B17001。貧困状態を判定できる人口が対象。TVDは0が一致、1が最大。','',
           '|地域分割|方式|地域平均TVD|人口加重TVD|最大TVD|','|---|---|---:|---:|---:|']
    for name,summary in summaries.items():
        for method,m in summary['methods'].items():lines.append(f"|{name}|{method}|{m['mean_tvd']:.6f}|{m['population_weighted_mean_tvd']:.6f}|{m['max_tvd']:.6f}|")
    lines+=['','入力に渡していない年齢×貧困の6セルを、ACSの推計値と比較した結果です。行動予測・介入・実地効果は未実行。',
            '開発6州の結果は学習外評価ではありません。地域分割は無作為抽出ではなく、全国への一般化区間は出しません。',
            'ACSの推計誤差は未伝播です。貧困状態を苦しみそのものとは扱いません。',f"出典：{source.url}",f"州抽出SHA256：{source.extract_sha256}",'']
    out=Path(args.out);write_bytes(out/'report.md','\n'.join(lines).encode())
    write_artifact(out/'report.json',report)


def main(argv=None):
    parser=argparse.ArgumentParser(prog='manager');commands=parser.add_subparsers(dest='command',required=True)
    fetch=commands.add_parser('fetch-acs');fetch.add_argument('--out',required=True)
    prep=commands.add_parser('prepare-population');prep.add_argument('--input',required=True);prep.add_argument('--out',required=True)
    recon=commands.add_parser('reconstruct')
    for flag in ('seed','marginals','out'):recon.add_argument('--'+flag,required=True)
    recon.add_argument('--method',choices=('independent','ipf'),required=True)
    scoring=commands.add_parser('score-population');scoring.add_argument('--predictions',action='append',required=True)
    for flag in ('reference','manifest','out'):scoring.add_argument('--'+flag,required=True)
    from .household_cli import add_household_commands
    add_household_commands(commands)
    args=parser.parse_args(argv)
    try:
        if hasattr(args,'handler'):args.handler(args)
        elif args.command=='fetch-acs':fetch_acs_extract(Path(args.out))
        elif args.command=='prepare-population':prepare(args)
        elif args.command=='reconstruct':reconstruct(args)
        else:score(args)
        return 0
    except (PopulationDataError,OSError,KeyError,TypeError,ValueError) as exc:
        print(f'population error: {exc}',file=sys.stderr);return 2
