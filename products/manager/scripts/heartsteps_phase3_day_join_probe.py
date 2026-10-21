#!/usr/bin/env python3
"""Aggregate-only scientific probe: can released step data recover study days?

Public HeartSteps participant rows stay inside temporary files. The only output
is aggregate coverage/mismatch counts. This is NOT a clinical or causal result.
All downloads are pinned to the authors' immutable GitHub commit and verified
by Git object hash. The original 2019 analysis used nonpublic .RData and the
public export omits the study.day.nogap field from suggestions.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory

SOURCE_COMMIT = '3016391de426116bdef41880d72bc8cd4b9b2477'
BASE = f'https://raw.githubusercontent.com/klasnja/HeartStepsV1/{SOURCE_COMMIT}/data_files/'
SUGGESTIONS_BLOB_SHA1 = '67a55efd4d79e1f5646bdb26277f37ec988e2403'
SUGGESTIONS_BYTES = 4371854
JAWBONE_BLOB_SHA1 = '1a8da5a8e3cbd9126cc624f0ff3b59a1570dd4cf'
JAWBONE_BYTES = 17652097
GOOGLE_FIT_BLOB_SHA1 = '3fbe7a1e4555282414e579f2ba4f3380856a2b3c'
GOOGLE_FIT_BYTES = 10021829
MISSING = {'', 'NA', 'NaN', 'nan', 'N/A', 'NULL', 'null'}


def _required(reader, names):
    columns = reader.fieldnames
    if not columns or not set(names).issubset(columns):
        raise ValueError('required public CSV columns missing')
    if len(columns) != len(set(columns)):
        raise ValueError('duplicate columns in public CSV')


def _day(value):
    if value is None or str(value).strip() in MISSING:
        return None
    number=float(value)
    if not math.isfinite(number) or not number.is_integer() or number < 0:
        raise ValueError('invalid observed study.day.nogap')
    return int(number)



def _norm_key(value):
    text=str(value if value is not None else '').strip()
    if text in MISSING:
        return ''
    try:
        number=Decimal(text)
    except InvalidOperation:
        return text
    if number.is_finite() and number >= 0 and number == number.to_integral_value():
        return str(int(number))
    return text

def summarize_key_alignment(suggestion_rows, day_lookup):
    """Only cardinalities of key intersections; no participant or decision IDs."""
    _required(suggestion_rows,['user.index','decision.index'])
    suggestion_keys={(_norm_key(row.get('user.index')), _norm_key(row.get('decision.index'))) for row in suggestion_rows}
    suggestion_keys={x for x in suggestion_keys if all(x)}
    step_keys=set(day_lookup)
    su={k[0] for k in suggestion_keys}; sd={k[1] for k in suggestion_keys}
    ju={k[0] for k in step_keys}; jd={k[1] for k in step_keys}
    return {
        'suggestion_unique_users':len(su),
        'step_unique_users':len(ju),
        'user_overlap':len(su & ju),
        'suggestion_unique_decisions':len(sd),
        'step_unique_decisions':len(jd),
        'decision_overlap':len(sd & jd),
        'pair_overlap':len(suggestion_keys & step_keys),
    }

def build_day_lookup(step_rows):
    """(user.index, decision.index) → observed study day, or None if conflicting."""
    _required(step_rows, ['user.index', 'decision.index', 'study.day.nogap'])
    lookup={}
    rows_seen=0
    missing_field=0
    collisions=0
    for row in step_rows:
        rows_seen+=1
        uid=_norm_key(row.get('user.index',''))
        decision=_norm_key(row.get('decision.index',''))
        day=_day(row.get('study.day.nogap'))
        if not uid or uid in MISSING or not decision or decision in MISSING or day is None:
            missing_field+=1
            continue
        key=(uid,decision)
        if key not in lookup:
            lookup[key]=day
        elif lookup[key] is not None and lookup[key]!=day:
            lookup[key]=None
            collisions+=1
    counts={
        'source_step_rows':rows_seen,
        'missing_keys_or_day':missing_field,
        'conflicting_observations':collisions,
        'unique_day_keys':sum(day is not None for day in lookup.values()),
        'ambiguous_keys':sum(day is None for day in lookup.values()),
    }
    return lookup,counts



def build_following_day_lookup(step_rows):
    """Get a second independently observed study-day mapping before a decision."""
    _required(step_rows,['user.index','decision.index.following.dec','study.day.nogap.following.dec'])
    lookup={}
    for row in step_rows:
        uid=_norm_key(row.get('user.index'))
        ix=_norm_key(row.get('decision.index.following.dec'))
        day=_day(row.get('study.day.nogap.following.dec'))
        if not uid or not ix or day is None:
            continue
        key=(uid,ix)
        if key not in lookup:
            lookup[key]=day
        elif lookup[key] is not None and lookup[key]!=day:
            lookup[key]=None
    return lookup,{'unique_day_keys':sum(v is not None for v in lookup.values()),
                   'ambiguous_keys':sum(v is None for v in lookup.values())}

def merge_day_lookups(primary,following):
    merged=dict(primary)
    conflict=new_nonconflicting=0
    for key,day in following.items():
        if key not in merged:
            merged[key]=day
            if day is not None: new_nonconflicting+=1
        elif merged[key] is not None and day is not None and merged[key]!=day:
            merged[key]=None
            conflict+=1
    return merged,{'conflicting_keys':conflict,
                   'new_nonconflicting_keys':new_nonconflicting,
                   'merged_unique_keys':sum(v is not None for v in merged.values()),
                   'merged_ambiguous_keys':sum(v is None for v in merged.values())}

def optional_primary_day_lookup(reader):
    """Treat a missing study-day column as unavailable data, never guess it."""
    required={'user.index','decision.index','study.day.nogap'}
    missing=sorted(required-set(reader.fieldnames or []))
    if missing:
        return {}, {'state':'missing_in_public_csv','missing_required_columns':missing}
    mapping,counts=build_day_lookup(reader)
    return mapping,{'state':'available', **counts}


def optional_following_day_lookup(reader):
    required={'user.index','decision.index.following.dec','study.day.nogap.following.dec'}
    missing=sorted(required-set(reader.fieldnames or []))
    if missing:
        return {}, {'state':'missing_in_public_csv','missing_required_columns':missing}
    mapping,counts=build_following_day_lookup(reader)
    return mapping,{'state':'available', **counts}


def merge_device_evidence(lookups):
    """Merge independent device+position mappings; conflicts remain unknown.

    Returned audit is aggregate only; per-subject keys never leave caller memory.
    """
    merged = {}
    conflict_keys = set()
    additions = 0
    for mapping in lookups:
        for key, day in mapping.items():
            if key not in merged:
                merged[key] = day
                if day is not None:
                    additions += 1
                continue
            if day is not None and merged[key] is not None and merged[key] != day:
                merged[key] = None
                conflict_keys.add(key)
    return merged, {
        'conflicting_keys': len(conflict_keys),
        'merged_unique_keys': sum(day is not None for day in merged.values()),
        'merged_ambiguous_keys': sum(day is None for day in merged.values()),
        'new_nonconflicting_keys': additions,
    }


def compare_proxy_days(suggestion_rows, day_lookup):
    """Compare observed study.day to the old unsupported index/5 assumption."""
    _required(suggestion_rows,['user.index','decision.index','decision.index.nogap'])
    out=Counter()
    for row in suggestion_rows:
        key=(_norm_key(row.get('user.index')), _norm_key(row.get('decision.index')))
        if key not in day_lookup or day_lookup[key] is None:
            continue
        out['matched']+=1
        index=row.get('decision.index.nogap')
        if index is None or str(index).strip() in MISSING:
            out['missing_proxy']+=1
            continue
        numeric=float(index)
        if not math.isfinite(numeric) or numeric<0 or not numeric.is_integer():
            raise ValueError('invalid decision index for proxy comparison')
        old_proxy=int(numeric)//5
        if old_proxy==day_lookup[key]:out['agree']+=1
        else:out['disagree']+=1
    return {key:out[key] for key in ['matched','agree','disagree','missing_proxy']}

def aggregate_coverage(suggestion_rows, day_lookup):
    """Only aggregate totals, NEVER personally linked observations."""
    _required(suggestion_rows,['user.index','decision.index','avail'])
    out=Counter()
    for row in suggestion_rows:
        out['source_rows']+=1
        uid=_norm_key(row.get('user.index',''))
        decision=_norm_key(row.get('decision.index',''))
        if not uid or uid in MISSING or not decision or decision in MISSING:
            out['join_absent']+=1
            continue
        key=(uid,decision)
        if key not in day_lookup:
            out['join_absent']+=1
        elif day_lookup[key] is None:
            out['join_ambiguous']+=1
        else:
            day=day_lookup[key]
            out['join_unique']+=1
            if day > 41:
                out['day_gt_41']+=1
            else:
                out['join_unique_in_study_window']+=1
                if str(row['avail']).strip().lower() in {'true','t','1'}:
                    out['unique_available']+=1
    return {field:out[field] for field in ('source_rows','join_unique','join_ambiguous','join_absent',
        'join_unique_in_study_window','day_gt_41','unique_available')}


def main():
    from heartsteps_research import download, validate_source
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with TemporaryDirectory(prefix='heartsteps-join-probe-') as td:
        root=Path(td)
        paths={'suggestions':root/'suggestions.csv','jawbone':root/'jbsteps.csv','google_fit':root/'gfsteps.csv'}
        download(BASE+'suggestions.csv',paths['suggestions'])
        download(BASE+'jbsteps.csv',paths['jawbone'])
        download(BASE+'gfsteps.csv',paths['google_fit'])
        src1=validate_source(paths['suggestions'],SUGGESTIONS_BYTES,SUGGESTIONS_BLOB_SHA1)
        src2=validate_source(paths['jawbone'],JAWBONE_BYTES,JAWBONE_BLOB_SHA1)
        src3=validate_source(paths['google_fit'],GOOGLE_FIT_BYTES,GOOGLE_FIT_BLOB_SHA1)
        with paths['jawbone'].open(newline='',encoding='utf-8-sig') as fh:
            lookup,step_counts=build_day_lookup(csv.DictReader(fh))
        with paths['suggestions'].open(newline='',encoding='utf-8-sig') as fh:
            coverage=aggregate_coverage(csv.DictReader(fh),lookup)
        with paths['suggestions'].open(newline='',encoding='utf-8-sig') as fh:
            key_alignment=summarize_key_alignment(csv.DictReader(fh),lookup)
        with paths['jawbone'].open(newline='',encoding='utf-8-sig') as fh:
            reader=csv.DictReader(fh)
            fields={'user.index','decision.index.following.dec','study.day.nogap.following.dec'}
            has_following=bool(reader.fieldnames and fields.issubset(reader.fieldnames))
            if has_following:
                following,following_report=build_following_day_lookup(reader)
            else:
                following,following_report={}, {'columns_available':False}
        merged,merged_report=merge_day_lookups(lookup,following)
        with paths['google_fit'].open(newline='',encoding='utf-8-sig') as fh:
            gfprimary,gfprimary_report=optional_primary_day_lookup(csv.DictReader(fh))
        with paths['google_fit'].open(newline='',encoding='utf-8-sig') as fh:
            gffollowing,gffollowing_report=optional_following_day_lookup(csv.DictReader(fh))
        all_four,all_four_report=merge_device_evidence([lookup,following,gfprimary,gffollowing])
        with paths['suggestions'].open(newline='',encoding='utf-8-sig') as fh:
            all_four_coverage=aggregate_coverage(csv.DictReader(fh),all_four)
        with paths['suggestions'].open(newline='',encoding='utf-8-sig') as fh:
            all_four_proxy_compare=compare_proxy_days(csv.DictReader(fh),all_four)
        with paths['suggestions'].open(newline='',encoding='utf-8-sig') as fh:
            merged_coverage=aggregate_coverage(csv.DictReader(fh),merged)
        with paths['suggestions'].open(newline='',encoding='utf-8-sig') as fh:
            proxy_comparison=compare_proxy_days(csv.DictReader(fh),merged)
        del lookup,merged,following,gfprimary,gffollowing,all_four
        report={
            'schema':'manager.heartsteps.pinned-day-join-diagnostic.v1',
            'method':'aggregate join of published Jawbone study-day and suggestions; incomplete coverage is not imputed',
            'source_commit':SOURCE_COMMIT,
            'verified_git_blobs':{'suggestions':src1['git_blob_sha1'],'jawbone':src2['git_blob_sha1'],'google_fit':src3['git_blob_sha1']},
            'steps':step_counts,
            'coverage':coverage,
            'combined_coverage':merged_coverage,
            'following_mapping':following_report,
            'combined_mapping':merged_report,
            'cross_device_coverage':all_four_coverage,
            'cross_device_mapping':all_four_report,
            'google_fit_primary':gfprimary_report,
            'google_fit_following':gffollowing_report,
            'cross_device_proxy_comparison':all_four_proxy_compare,
            'old_proxy_comparison':proxy_comparison,
            'key_alignment':key_alignment,
            'original_paper_counts':{'included':7540,'available':6061},
            'raw_subject_rows_persisted':False,
            'causal_effect_estimated':False,
            'exact_original_analysis_replicated':False,
            'manager_field_benefit_established':False,
        }
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/'day_join_aggregate.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        print(json.dumps(report,sort_keys=True))

if __name__=='__main__':
    main()