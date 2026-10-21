"""SocSci210 real held-out response baselines from ephemeral **aggregate SQL only**.

Research-only: user has expressly authorized processing, external dataset
terms are not rewritten; no participant profiles, prompts, free text, row
identifiers, or source Parquet files are committed or printed.

Important science caveat: response codes are study-specific. We deliberately
label any 0..10 numeric category as itself, and out-of-range as OTHER. This
is a coarse cross-study *encoding* baseline, not the original Socrates task-
condition-aware prediction protocol, human cognitive accuracy, or effect size.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from math import sqrt
from statistics import median

BUCKETS = [str(i) for i in range(11)] + ["OTHER"]


def _guard_split(mapping):
    if not isinstance(mapping, dict) or set(mapping) != {"seen", "unseen"}:
        raise ValueError("bad study split")
    tr, te = mapping["seen"], mapping["unseen"]
    if len(tr) != 170 or len(te) != 40 or any(type(x) is not str for x in tr + te):
        raise ValueError("study split cardinality or key violation")
    if len(set(tr)) != 170 or len(set(te)) != 40 or set(tr) & set(te):
        raise ValueError("study overlap / leakage")
    return set(tr), set(te)


def _prop(counter):
    n = sum(counter.values())
    if n <= 0:
        raise ValueError("empty study")
    return [counter.get(v, 0) / n for v in BUCKETS]


def _tvd(p, q):
    return 0.5 * sum(abs(x - y) for x, y in zip(p, q))


def _brier(p, q):
    """Multiclass Brier: sum (p_j-I{Y=j})^2, scale [0,2]."""
    return 1.0 + sum(x*x for x in p) - 2*sum(x*y for x,y in zip(p,q))


def _round(z):
    return round(float(z), 8)


def evaluate_aggregates(mapping, aggregates):
    """Aggregated (study-id, response bucket, count); no participant data.

    No test outcomes enter training. The model predicts one common numeric
    response-code distribution for all 40 unseen studies; uncalibrated,
    semantically weak but genuinely out-of-study heldout.
    """
    seen, unseen = _guard_split(mapping)
    groups = defaultdict(Counter)
    for study, bucket, count in aggregates:
        if (not isinstance(study, str) or study not in seen | unseen
                or bucket not in BUCKETS or type(count) is not int or count < 1):
            raise ValueError("unexpected study label, bucket or disclosure count")
        groups[study][bucket] += count
    if seen - groups.keys() or unseen - groups.keys():
        raise ValueError("not all 210 studies present in real data")
    global_counts = Counter()
    for study in seen:
        global_counts.update(groups[study])
    p = _prop(global_counts)
    p_majority = [int(i == max(range(len(p)), key=lambda j:p[j])) for i in range(len(p))]
    evaluated = []
    for study in sorted(unseen):
        q = _prop(groups[study])
        n = sum(groups[study].values())
        evaluated.append({
            "n": n, "accuracy_majority": sum(a*b for a,b in zip(p_majority,q)),
            "accuracy_frequency_sampled":sum(a*b for a,b in zip(p,q)),
            "brier_frequency": _brier(p,q),
            "brier_majority":_brier(p_majority,q),
            "tvd_frequency":_tvd(p,q),
            "tvd_majority":_tvd(p_majority,q),
            "out_of_train_support_rate":sum(q[i] for i,b in enumerate(BUCKETS) if global_counts[b] == 0),
            "out_of_range_response_bucket_rate": q[-1],
        })
    weights = [r["n"] for r in evaluated]
    test_n = sum(weights)
    tr_n = sum(global_counts.values())
    def metric(key, aggregate):
        values=[r[key] for r in evaluated]
        if aggregate=="micro":
            return _round(sum(v*w for v,w in zip(values,weights))/test_n)
        return _round(sum(values)/len(values))
    # Study-level error uncertainty from bootstrap: resample whole studies,
    # not respondent rows, so within-study dependence is retained.
    import random
    rng=random.Random(20261021)
    tvds=[x["tvd_frequency"] for x in evaluated]
    boot=[sum(tvds[rng.randrange(len(tvds))] for _ in tvds)/len(tvds) for _ in range(1000)]
    boot.sort()
    def robust_stats(v):
        arr=sorted(v)
        return {"min":_round(arr[0]),"median":_round(median(arr)),
                "p90":_round(arr[int((len(arr)-1)*.9)]),
                "max":_round(arr[-1])}
    return {
        "schema":"manager.phase04.socsci210.real-heldout-coarse-code-baselines.v1",
        "source":"socratesft/SocSci210",
        "basis":"REAL_PUBLIC_SOURCE_HUMAN_RESPONSES_AGGREGATED_EPHEMERALLY",
        "task_semantics":"GLOBAL_NUMERIC_RESPONSE_CODE_ONLY_NOT_SAME_SCALE_ACROSS_STUDIES",
        "source_split":{"seen_studies":len(seen),"unseen_studies":len(unseen),"overlap":0,
                         "seen_rows":tr_n,"unseen_rows":test_n},
        "training_response_classes":BUCKETS,
        "train_fitted_distribution":{key:_round(v) for key,v in zip(BUCKETS,p)},
        "train_majority_label":BUCKETS[p_majority.index(1)],
        "unseen_baselines":{
            "frequency":{"expected_accuracy_micro":metric("accuracy_frequency_sampled","micro"),
                         "brier_multiclass_micro":metric("brier_frequency","micro"),
                         "tvd_micro":metric("tvd_frequency","micro"),
                         "tvd_study_macro":metric("tvd_frequency","macro")},
            "majority":{"accuracy_micro":metric("accuracy_majority","micro"),
                        "brier_multiclass_micro":metric("brier_majority","micro"),
                        "tvd_micro":metric("tvd_majority","micro"),
                        "tvd_study_macro":metric("tvd_majority","macro")}
        },
        "study_level_distribution_error":{
            "n":len(evaluated),"tvd_summary":robust_stats(tvds),
            "bootstrap_study_macro_tvd_ci95":[_round(boot[25]),_round(boot[974])],
            "bootstrap_seed":20261021,"resamples":1000,
            "respondent_level_ci_claim":False
        },
        "subgroups":[
            {"category":"heldout_studies_with_at_least_1000_observations",
             "studies":sum(x["n"]>=1000 for x in evaluated),
             "rows":sum(x["n"] for x in evaluated if x["n"]>=1000),
             "mean_study_tvd":_round(sum(x["tvd_frequency"] for x in evaluated if x["n"]>=1000)/max(1,sum(x["n"]>=1000))) if any(x["n"]>=1000 for x in evaluated) else None},
            {"category":"heldout_studies_below_1000_observations",
             "studies":sum(x["n"]<1000 for x in evaluated),
             "rows":sum(x["n"] for x in evaluated if x["n"]<1000),
             "mean_study_tvd":_round(sum(x["tvd_frequency"] for x in evaluated if x["n"]<1000)/max(1,sum(x["n"]<1000))) if any(x["n"]<1000 for x in evaluated) else None},
        ],
        "abstention_policy":{
            "decision":"ABSTAIN_ALL_UNSEEN_FOR_DEPLOYMENT",
            "reason":"No unseen-study task semantics, available options, or calibrated per-task prior available at inference time",
            "retrospective_tvd_is_never_used_to_predict_abstention":True},
        "privacy":{"participant_records_published":0,"personal_attributes_loaded":False,
                   "raw_prompt_loaded":False,"raw_rows_saved":False,
                   "only_study_response_bucket_counts_inspected_transiently":True},
        "scientific_gates":{
            "S002_cross_study_numeric_response_baseline":"MEASURED_RESTRICTED_SCOPE",
            "S002_original_semantic_task_aware_acceptance":"NOT_MET",
            "S004_calibration_of_meaningful_task_probabilities":"NOT_MET",
            "S005_pretrained_model_same_split":"NOT_RUN",
            "causal_effect_prediction":"NOT_TESTED",
            "manager_real_beneficiaries":"NOT_MEASURED",
        },
    }
