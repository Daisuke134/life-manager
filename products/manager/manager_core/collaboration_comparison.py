"""Source-bound offline comparison. No network, hidden labels or auto billing.

Optional model results are recorded artifacts, NOT an execution callback. Actual
provider calls belong to the existing durable/budgeted lab. Supplied records are
not authenticated merely because they contain a provider name or a hash.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import json
import random
from .collaboration import parse_advice, render_prompt
from .collaboration_baselines import no_action_baseline, rule_baseline
from .collaboration_evaluation import ScenarioCase, ValidationResult, score_case, VERSION


@dataclass(frozen=True)
class EvaluationSuite:
    development_cases: tuple[ScenarioCase,...]
    evaluation_cases: tuple[ScenarioCase,...]
    manifest_sha256: str


@dataclass(frozen=True)
class RecordedProviderRun:
    name: str
    manifest_sha256: str
    context_hashes: dict[str,str]
    outputs: dict[str,str | None]


def load_suite(path: Path) -> EvaluationSuite:
    from scripts.phase_ampersand_lab import scenario_context
    path=Path(path)
    raw=(path/'cases-manifest.json').read_bytes();manifest=json.loads(raw)
    expected={'cases.json','rubric.md','schema.json'}
    if set(manifest.get('hashes',{}))!=expected or manifest.get('evaluator_version')!=VERSION:
        raise ValueError('complete frozen manifest required')
    for name,digest in manifest['hashes'].items():
        if sha256((path/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('frozen evaluation bytes changed')
    baseline=Path(__file__).with_name('collaboration_baselines.py')
    if sha256(baseline.read_bytes()).hexdigest()!=manifest['baseline_source_sha256']:
        raise ValueError('baseline changed after evaluation freeze')
    data=json.loads((path/'cases.json').read_text())
    families=data.get('families',[])
    if len(families)!=12:raise ValueError('exactly twelve scenario families required')
    seen_families=set();seen_cases=set();dev=[];evaluation=[]
    for family in families:
        fid=family['family_id'];split=family['split']
        if fid in seen_families or split not in ('development','evaluation'):
            raise ValueError('unique family belongs to exactly one split')
        seen_families.add(fid)
        if len(family['variants'])!=5:raise ValueError('five variants per family required')
        for row in family['variants']:
            cid=row['case_id']
            if cid in seen_cases or not cid.startswith(fid+'_v'):
                raise ValueError('case identity must remain within its family')
            seen_cases.add(cid)
            # This adapter constructs explicitly fictional evidence, never a real observer.
            context=scenario_context((cid,row['goal'],row['fact'],'EVALUATOR_HIDDEN'),
                                     datetime.fromisoformat(data['fictional_clock']))
            case=ScenarioCase(cid,fid,context,frozenset(row['acceptable_decisions']),
                frozenset(row['forbidden_decisions']),row['rationale'],
                tuple(row['evidence_basis']),VERSION,row['question_useful'])
            (dev if split=='development' else evaluation).append(case)
    if len(dev)!=20 or len(evaluation)!=40:
        raise ValueError('four development / eight evaluation families required')
    return EvaluationSuite(tuple(dev),tuple(evaluation),sha256(raw).hexdigest())


def _paired_report(cases,left,right):
    families={}
    for c,l,r in zip(cases,left,right):
        if l is None or r is None:continue
        families.setdefault(c.family_id,[]).append(l-r)
    if not families:
        return {'clusters':0,'resamples':2000,'difference':None,'interval_95':None,'conclusion':'INCONCLUSIVE'}
    values=[sum(x)/len(x) for x in families.values()]
    rng=random.Random(20261022);draws=[]
    for _ in range(2000):
        draws.append(sum(rng.choice(values) for _ in values)/len(values))
    draws.sort();interval=[draws[49],draws[1949]]
    return {'clusters':len(values),'resamples':2000,'difference':sum(values)/len(values),
            'interval_95':interval,'conclusion':'INCONCLUSIVE' if interval[0]<=0<=interval[1]
            else 'P0_LABEL_AGREEMENT_DIFFERENCE_ONLY'}


def evaluate_suite(manifest: EvaluationSuite,provider: RecordedProviderRun | None=None,
                   seed_schedule=(20261022,20261023,20261024)) -> dict:
    if type(manifest) is not EvaluationSuite:raise ValueError('validated frozen suite required')
    if (type(seed_schedule) is not tuple or len(seed_schedule)!=3
            or any(type(s) is not int for s in seed_schedule) or len(set(seed_schedule))!=3):
        raise ValueError('three disclosed distinct repeat seeds required')
    cases=manifest.evaluation_cases
    if provider is not None:
        if type(provider) is not RecordedProviderRun or provider.manifest_sha256!=manifest.manifest_sha256:
            raise ValueError('recorded provider requires identical frozen manifest')
        expected={c.case_id:sha256(render_prompt(c.context).encode()).hexdigest() for c in cases}
        keys={f'{c.case_id}:{i}' for c in cases for i in range(3)}
        if provider.context_hashes!=expected or set(provider.outputs)!=keys:
            raise ValueError('same public inputs and all attempts, including failures, required')
        if any(v is not None and type(v) is not str for v in provider.outputs.values()):
            raise ValueError('recorded raw advice or explicit transport failure required')
    policies={'no_action':no_action_baseline,'rule':rule_baseline};results={};means={}
    if provider is not None:policies['supplied_provider']=None
    for name,policy in policies.items():
        raw=[];per_case=[]
        for case in cases:
            scores=[]
            for repeat,seed in enumerate(seed_schedule):
                text=None if provider is None else provider.outputs[f'{case.case_id}:{repeat}']
                if policy is not None:
                    reply=policy(case.context);validation=ValidationResult()
                else:
                    reply=None if text is None else parse_advice(text,frozenset(f.source.source_id for f in case.context.facts))
                    validation=ValidationResult(transport_ok=text is not None)
                score=score_case(case,reply,validation)
                scores.append(score.usefulness)
                raw.append({'case_id':case.case_id,'family_id':case.family_id,'repeat':repeat,
                    'scheduled_seed':seed,'raw_text':text if policy is None else None,
                    'decision':score.decision,'transport':score.transport,'format':score.format,
                    'label_agreement':score.usefulness,'interruption':score.interruption,
                    'critical_failure':score.critical_failure})
            # Failed attempts contribute zero to unconditional agreement, but remain
            # failures (not invented model PASS) in their separate status fields.
            per_case.append(sum(v if v is not None else 0 for v in scores)/3)
        results[name]={'attempts':len(raw),'unconditional_label_agreement':sum(per_case)/len(per_case),
            'transport_failures':sum(x['transport']==0 for x in raw),
            'format_failures':sum(x['format']==0 for x in raw),
            'critical_failures':sum(x['critical_failure'] for x in raw),
            'raw_attempts':raw,'settled_cost_usd':None,'cpu_cost_usd':None}
        means[name]=per_case
    return {'schema':'manager.collaboration-comparison.v2','manifest_sha256':manifest.manifest_sha256,
        'evaluation_cases':len(cases),'scheduled_attempts_per_policy':len(cases)*3,
        'provider_status':'NOT_RUN' if provider is None else 'SUPPLIED_OUTPUTS_NOT_AUTHENTICATED',
        'provider_label_agreement':None if provider is None else results['supplied_provider']['unconditional_label_agreement'],
        'actual_provider_calls':0,'seed_schedule':list(seed_schedule),'policies':results,
        'paired_rule_minus_no_action':_paired_report(cases,means['rule'],means['no_action']),
        'paired_provider_minus_rule':None if provider is None else _paired_report(cases,means['supplied_provider'],means['rule']),
        'conclusion':'NO_PROVIDER_COMPARISON' if provider is None else 'P0_RECORDED_COMPARISON_ONLY',
        'semantic_safety_assessment':'NOT_RUN','semantic_rationale_quality':'NOT_MEASURED',
        'human_outcome':'NOT_MEASURED','scope':'AUTHOR_WRITTEN_FICTIONAL_ENGINEERING_STRESS_TEST',
        'limitation':'Deterministic repeats add no independent information. Eight families are not a power-certified human study.'}
