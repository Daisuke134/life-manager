#!/usr/bin/env python3
"""Alternative exploratory public-CSV analysis; NOT the 2019 HeartSteps RCT replication.

Only a pinned public research CSV is read temporarily. Its original study-day
field is not present; no proxy can be relabeled as the original calendar day.
No participant IDs, records, or timestamps are written to output. This module
reuses Manager's existing participant-cluster WLS estimator as a statistical
summary, not as proof of the published trial or of Manager field impact.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

SOURCE_COMMIT = '3016391de426116bdef41880d72bc8cd4b9b2477'
SOURCE_URL = (f'https://raw.githubusercontent.com/klasnja/HeartStepsV1/{SOURCE_COMMIT}'
              '/data_files/suggestions.csv')
SOURCE_BYTES = 4_371_854
SOURCE_GIT_BLOB = '67a55efd4d79e1f5646bdb26277f37ec988e2403'
SOURCE_SHA256 = '60ee7896183d7084a084f9a6e8ef2d0afea2e7fecdb41d6b15382ce1745c5ddb'
MISSING = {'', 'na', 'nan', 'n/a', 'null'}
REQUIRED = {'user.index','decision.index.nogap','avail','send',
            'send.active','send.sedentary','jbsteps30','jbsteps30.zero',
            'jbsteps30pre.zero'}


def _missing(v):
    return v is None or str(v).strip().lower() in MISSING


def _bool(v):
    if _missing(v):return None
    if str(v).lower().strip() in {'true','t','1'}:return True
    if str(v).lower().strip() in {'false','f','0'}:return False
    return None


def _valid_nonnegative(v):
    if _missing(v):return None
    try:num=float(v)
    except (TypeError,ValueError):return None
    return num if math.isfinite(num) and num>=0 else None


def select_public_assignments(raw_rows):
    """Public, specifically defined estimand: all available/known-action decisions.

    Does not claim to implement the 2019 paper's data exclusions or planned days.
    Subset selection is transparent; every exclusion has one reason.
    """
    kept=[];excluded=Counter()
    for r in raw_rows:
        excluded['input_rows']+=1
        avail=_bool(r.get('avail'))
        if avail is None:
            excluded['missing_availability']+=1;continue
        if not avail:
            excluded['unavailable']+=1;continue
        send=_bool(r.get('send'))
        if send is None:
            excluded['missing_send']+=1;continue
        active=_bool(r.get('send.active'))
        sedentary=_bool(r.get('send.sedentary'))
        if active is None or sedentary is None or (send and active==sedentary) or (not send and (active or sedentary)):
            excluded['ambiguous_action']+=1;continue
        if _missing(r.get('decision.index.nogap')):
            excluded['missing_decision_index']+=1;continue
        idx=_valid_nonnegative(r.get('decision.index.nogap'))
        if idx is None or not idx.is_integer():
            excluded['invalid_decision_index']+=1;continue
        post=_valid_nonnegative(r.get('jbsteps30.zero'))
        pre=_valid_nonnegative(r.get('jbsteps30pre.zero'))
        if post is None or pre is None:
            if _missing(r.get('jbsteps30.zero')) or _missing(r.get('jbsteps30pre.zero')):
                excluded['missing_outcome']+=1
            else:excluded['invalid_outcome']+=1
            continue
        user=r.get('user.index')
        if _missing(user):
            excluded['missing_cluster_id']+=1;continue
        kept.append({'user':str(user),'decision_index':int(idx),'send':send,
                     'send_active':active,'send_sedentary':sedentary,
                     'outcome':post,'pre':pre,
                     'raw_outcome_missing':_missing(r.get('jbsteps30'))})
    excluded['retained']=len(kept)
    return kept,dict(sorted(excluded.items()))


def descriptive_summary(rows, exclusion):
    import statistics
    return {'observed_rows':exclusion['input_rows'],
            'selected_available_decisions':len(rows),
            'unique_participants_included':len({r['user'] for r in rows}),
            'notification':sum(r['send'] for r in rows),
            'walking_notification':sum(r['send_active'] for r in rows),
            'sedentary_notification':sum(r['send_sedentary'] for r in rows),
            'no_notification':sum(not r['send'] for r in rows),
            'raw_outcome_missing':sum(r['raw_outcome_missing'] for r in rows),
            'mean_imputed_30min_steps':statistics.fmean(r['outcome'] for r in rows) if rows else None,
            'sd_imputed_30min_steps':statistics.stdev(r['outcome'] for r in rows) if len(rows)>1 else None,
            'descriptive_only':True,'causal_effect_estimated':False}


def _regression(rows,with_index_interaction=False):
    # Reuse the upstream-independent estimator already in the Manager source.
    from heartsteps_phase3 import weighted_cluster_regression
    if len({r['user'] for r in rows})<5:raise ValueError('at least five clusters required for exploratory uncertainty')
    center=sum(r['decision_index'] for r in rows)/len(rows)
    X=[];y=[];group=[];weights=[]
    for r in rows:
        # Index is an ordinal *proxy*, never the study.day.nogap column.
        time=(r['decision_index']-center)/50.0
        action=float(r['send'])
        vec=[1.0, math.log(r['pre']+.5), time, action]
        if with_index_interaction:vec.append(time*action)
        X.append(vec);y.append(math.log(r['outcome']+.5));group.append(r['user']);weights.append(1.0)
    model=weighted_cluster_regression(X,y,group,weights)
    effect=model['beta'][3];se=model['se'][3]
    return {'n':len(rows),'clusters':model['clusters'],
            'ratio':math.exp(effect),'ratio_ci_95_normal':[math.exp(effect-1.96*se),math.exp(effect+1.96*se)],
            'ordinal_index_50_interaction':model['beta'][4] if with_index_interaction else None,
            'ordinal_index_50_multiplier':math.exp(model['beta'][4]) if with_index_interaction else None,
            'description':'participant-cluster-robust regression; association, not exact 2019 causal RCT reproduction',
            'covariance':model['covariance']}


def fit_exploratory_models(rows):
    from heartsteps_phase3 import weighted_cluster_regression  # required checked dependency
    any_model=_regression(rows,False)
    with_time=_regression(rows,True)
    active_only=[r for r in rows if not r['send_sedentary']]
    if len({r['user'] for r in active_only}) <5 or not any(r['send_active'] for r in active_only):
        raise ValueError('insufficient walking vs no-message comparison clusters')
    walking=_regression(active_only,False)
    return {'any_ratio':any_model['ratio'],'any_ci_95':any_model['ratio_ci_95_normal'],
            'walking_association_ratio':walking['ratio'],
            'walking_ci_95':walking['ratio_ci_95_normal'],
            'any_time_index_interaction':with_time['ordinal_index_50_interaction'],
            'any_index_50_multiplier':with_time['ordinal_index_50_multiplier'],
            'index_centering':'decision.index.nogap, per 50 ordinal decisions, NOT original study days',
            'clusters':any_model['clusters'],
            'method':'cluster_robust_normal_approx_associations',
            'causal_effect_estimated':False}


def build_public_report(rows,exclusions):
    descript=descriptive_summary(rows,exclusions)
    models=fit_exploratory_models(rows)
    return {'schema':'manager.heartsteps.public-exploratory.v1',
            'scientific_status':'exploratory_nonidentical',
            'source':{'repository':'klasnja/HeartStepsV1','commit':SOURCE_COMMIT,
                      'csv':'data_files/suggestions.csv','source_sha256':SOURCE_SHA256,
                      'license':'CC BY 4.0; anonymized research use only; no raw redistribution'},
            'selection':{'rule':'Only public CSV decisions with avail=true, known send and coherent action, valid ordinal index and nonnegative pre/post outcomes; no unvalidated 42-day proxy cutoff',
                         'exclusions':exclusions},
            'outcomes':descript,
            'model_outputs':models,
            'source_comparison':{'original_2019_paper':{'included':7540,'available':6061,'mean_steps':253,
                                                       'any_ratio':1.14,'walking_ratio':1.24},
                                 'replicated_2019_trial':'NO',
                                 'unmet_original_selection_requirement':True,
                                 'reason':'public export lacks author analysis study.day.nogap and unambiguous full eligibility mapping; do not force-match'},
            'privacy':{'individual_rows_in_report':False,'participant_ids_in_report':False,
                       'download_temporary':True,'raw_csv_redistributed':False},
            'limitations':['unverified comparability to 2019 analysis set',
                           'action indicators require original author coding confirmation',
                           'ordinal decision index is not study day',
                           'zero-imputed outcome mixes observed zero with missing device observations',
                           'cluster-robust confidence intervals are approximations and not causal effects',
                           'no field intervention or welfare benefit by Manager']}


def write_reports(report,out):
    out.mkdir(parents=True,exist_ok=True)
    (out/'phase03_exploratory_public.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf8')
    s=report['outcomes'];m=report['model_outputs'];e=report['selection']['exclusions']
    lines=[
        '# Phase 03 — public HeartSteps exploratory analysis (not paper replication)',
        '',f"- CSV pinned: {SOURCE_COMMIT}; SHA256 `{SOURCE_SHA256}`",
        f"- Available decisions with known assignment: **{s['selected_available_decisions']:,}**; subjects: **{s['unique_participants_included']}**",
        f"- Walking / sedentary / no message: **{s['walking_notification']:,} / {s['sedentary_notification']:,} / {s['no_notification']:,}**",
        f"- Mean 30-minute imputed steps: **{s['mean_imputed_30min_steps']:.2f}**; SD: **{s['sd_imputed_30min_steps']:.2f}**",
        '', '| Exploratory association | Ratio | Cluster-robust normal 95% CI | 2019 reported |',
        '|---|---:|---:|---:|',
        f"| Any message vs none | {m['any_ratio']:.3f} | {m['any_ci_95'][0]:.3f}–{m['any_ci_95'][1]:.3f} | 1.14 (nonidentical data) |",
        f"| Walking message vs none (descriptive conditional subset) | {m['walking_association_ratio']:.3f} | {m['walking_ci_95'][0]:.3f}–{m['walking_ci_95'][1]:.3f} | 1.24 (nonidentical data) |",
        f"| Ordinal-index effect interaction / 50 decisions | {m['any_index_50_multiplier']:.3f} | n/a | Not the paper's study-day effect |",
        '',
        '**IMPORTANT: NOT A REPLICATION OF THE 2019 RCT ESTIMAND. No causal effect or real-world blessing is established.**',
        '', 'This is a carefully labeled exploratory regression over available, assigned public decisions. Its eligibility, time variable, intervention definition and uncertainty differ from the original paper. The computed differences are scientific limits, not discrepancies to hide.',
        '',f"- Excluded counts (sequential): `{json.dumps(e,sort_keys=True)}`",
        '- No participant rows or identifiers are serialized.',
        '- Scientific waiver H005 applies **only** to the inaccessible matching dataset, not to the requirement for truthful reporting.'
    ]
    (out/'phase03_exploratory_public.md').write_text('\n'.join(lines)+'\n',encoding='utf8')


def main():
    from urllib.request import Request,urlopen
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with TemporaryDirectory(prefix='manager-heartsteps-public-alt-') as tmp:
        raw=Path(tmp)/'suggestions.csv'
        with urlopen(Request(SOURCE_URL,headers={'User-Agent':'Manager-read-only-study'}),timeout=120) as response,raw.open('wb') as o:
            while b:=response.read(1024*1024):o.write(b)
        payload=raw.read_bytes()
        if len(payload)!=SOURCE_BYTES or hashlib.sha256(payload).hexdigest()!=SOURCE_SHA256:
            raise SystemExit('Pinned source hash/size mismatch; no output')
        blob=f'blob {len(payload)}\0'.encode()+payload
        if hashlib.sha1(blob).hexdigest()!=SOURCE_GIT_BLOB:
            raise SystemExit('Git source identity mismatch; no output')
        with raw.open(newline='',encoding='utf-8-sig') as f:
            reader=csv.DictReader(f)
            if reader.fieldnames is None or len(reader.fieldnames)!=len(set(reader.fieldnames)) or not REQUIRED<=set(reader.fieldnames):
                raise SystemExit('Invalid source columns; no output')
            selected,exclusions=select_public_assignments(reader)
        if exclusions['input_rows']!=8274:
            raise SystemExit('Unexpected source row count; no output')
        report=build_public_report(selected,exclusions)
        write_reports(report,args.output)
        print(json.dumps({'source_rows':exclusions['input_rows'],'selected_available':len(selected),
             'participants':report['outcomes']['unique_participants_included'],
             'any_ratio':report['model_outputs']['any_ratio'],
             'walking_association_ratio':report['model_outputs']['walking_association_ratio'],
             'index_50_multiplier':report['model_outputs']['any_index_50_multiplier'],
             'original_replication':False,'causal_impact':False,'raw_persisted':False},sort_keys=True))

if __name__=='__main__':main()