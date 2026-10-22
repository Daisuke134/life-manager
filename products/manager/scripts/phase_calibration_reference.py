#!/usr/bin/env python3
"""E09 retrospective UCI daily-aggregate diagnostic, never human calibration."""
import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from statistics import median
from urllib.request import Request,urlopen
from zipfile import ZipFile
from manager_core.phase04_bike_sharing import verify_snapshot,parse_aggregate_days,ORIGINAL_CITATION,ORIGINAL_LICENSE
from manager_core.calibration import ErrorReference,PredictionCase,fit_error_calibrator,selective_risk_curve

SOURCE='https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip'
SCOPE='uci_dc_daily_weather_frequency_2011q1_to_2012'


def read_official():
    with urlopen(Request(SOURCE,headers={'User-Agent':'Manager-readonly-reference/0.1'}),timeout=20) as response:
        archive=response.read(2_000_001)
    if len(archive)>2_000_000:raise ValueError('bounded public archive required')
    with ZipFile(BytesIO(archive)) as z:
        if z.getinfo('day.csv').file_size!=57569:raise ValueError('unexpected daily aggregate size')
        return z.read('day.csv')


def run_reference(body):
    verify_snapshot(body);rows=parse_aggregate_days(body)
    base=[r for r in rows if r['date']<date(2011,4,1)]
    training=[r for r in rows if date(2011,4,1)<=r['date']<date(2011,7,1)]
    validation=[r for r in rows if date(2011,7,1)<=r['date']<date(2012,1,1)]
    test=[r for r in rows if r['date']>=date(2012,1,1)]
    threshold=median(r['count'] for r in base)
    buckets=defaultdict(list)
    for row in base:buckets[row['weather']].append(int(row['count']>=threshold))
    probabilities={k:sum(v)/len(v) for k,v in buckets.items()}
    fallback=sum(int(r['count']>=threshold) for r in base)/len(base)
    def reference(row):
        p=probabilities.get(row['weather'],fallback)
        return ErrorReference(row['date'].isoformat(),row['date'].strftime('%Y-%m'),
                              SCOPE,'en',(1-p,p),int(row['count']>=threshold))
    train_refs=tuple(map(reference,training));val_refs=tuple(map(reference,validation))
    model=fit_error_calibrator(train_refs,val_refs,scope=SCOPE,max_validation_risk=.25)
    refs=tuple(map(reference,test))
    estimates=tuple(model.predict_error(PredictionCase(r.reference_id,SCOPE,'en',r.distribution,
        out_of_distribution=row['weather'] not in probabilities)) for r,row in zip(refs,test))
    selected=[r for r,e in zip(refs,estimates) if e.accepted]
    def error(items):return sum((r.distribution[1]-r.outcome)**2 for r in items)/len(items) if items else None
    subgroups=[]
    for weather in sorted({row['weather'] for row in test}):
        idx=[i for i,row in enumerate(test) if row['weather']==weather]
        accepted=[refs[i] for i in idx if estimates[i].accepted]
        subgroups.append(dict(weather=weather,days=len(idx),accepted=len(accepted),
                             coverage=len(accepted)/len(idx),accepted_brier=error(accepted)))
    return dict(schema='manager.scoped-error-calibration.v1',scope=SCOPE,
        source=dict(url=SOURCE,doi=ORIGINAL_CITATION,license_url=ORIGINAL_LICENSE,
                    attribution='Hadi Fanaee-T, UCI Bike Sharing Dataset',body_sha256=sha256(body).hexdigest(),bytes=len(body)),
        evidence='ACTUAL_OBSERVED_NONPERSONAL_AGGREGATE_RETROSPECTIVE',
        partitions=dict(base_fit=len(base),error_fit=len(training),threshold_validation=len(validation),heldout_test=len(test)),
        split_groups=dict(training=list(model.training_group_ids),validation=list(model.validation_group_ids),
                          test=sorted({r.group_id for r in refs})),
        model=dict(intercept=model.intercept,slope=model.slope,threshold=model.threshold,
                   max_validation_risk=.25,reference_hash=model.reference_hash,base_count_threshold=threshold,
                   base_weather_probabilities=probabilities),
        evaluation=dict(coverage=len(selected)/len(refs),accepted_brier=error(selected),
                        all_case_brier=error(refs),accepted_days=len(selected),subgroups=subgroups,
                        coverage_risk_curve=[asdict(p) for p in selective_risk_curve(estimates,refs)]),
        promotion_decision='DENIED_SUBGROUP_RISK' if any(
            g['accepted_brier'] is not None and g['accepted_brier']>.25 for g in subgroups) else 'DIAGNOSTIC_ONLY_NOT_DEPLOYED',
        human_outcome='NOT_MEASURED',human_behavior_calibration='NOT_ESTABLISHED',
        owned_digital_predictions='ABSTAIN_SCOPE',
        limitations=['Prior research already examined this public dataset: not a fresh independent external holdout.',
          'Temporal groups prevent partition overlap but do not guarantee exchangeability or future calibration.',
          'Small retrospective error-regression diagnostic; no causal, human welfare or universal coverage guarantee.',
          'The model is never used to score human benefit or authorize an owned digital change.'])


def assert_reference_report(actual,expected):
    """Exact evidence identities; allow only 1e-12 cross-Python float roundoff."""
    from math import isclose,isfinite
    if type(actual) is not type(expected):raise ValueError('reference report type changed')
    if isinstance(expected,dict):
        if set(actual)!=set(expected):raise ValueError('reference report fields changed')
        for key in expected:assert_reference_report(actual[key],expected[key])
    elif isinstance(expected,list):
        if len(actual)!=len(expected):raise ValueError('reference report length changed')
        for a,e in zip(actual,expected):assert_reference_report(a,e)
    elif type(expected) is float:
        if not isfinite(actual) or not isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12):
            raise ValueError('reference metric differs beyond numerical roundoff')
    elif actual!=expected:raise ValueError('reference identity/count/status changed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--day-csv',type=Path);source.add_argument('--fetch-official',action='store_true')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=run_reference(read_official() if args.fetch_official else args.day_csv.read_bytes())
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(partitions=report['partitions'],evaluation=report['evaluation'],
                         human_outcome=report['human_outcome']),allow_nan=False))


if __name__=='__main__':main()
