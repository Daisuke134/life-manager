"""Empirical individual-response scoring for a fixed SocSci210 unseen-study sample.

Never export respondent rows, participant IDs, free-text prompts, model
generated text, demographics or individual predictions. This is a
methodological measurement of the global 12-code task, NOT a reproduction
of the source authors' task-wise human experiment accuracy.

The validation sample is selected deterministically by non-outcome fields
and committed before model inference. All metrics use identical rows.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from math import isfinite
from random import Random
import re

from manager_core.phase04_socsci_empirical import BUCKETS, _guard_split


def label_of_response(value):
    if type(value) is not int:
        raise ValueError("numeric response code required")
    return str(value) if 0 <= value <= 10 else "OTHER"


def parse_generated_response(value):
    if not isinstance(value, str):
        raise ValueError("string response required")
    # Parse only the first answer token; do not cherry pick a code mentioned
    # later in generated explanations.
    m = re.match(r"^\s*(?:\*\*)?\s*(OTHER|10|[0-9])(?:\b|$)", value, flags=re.I)
    return (m.group(1).upper() if m else None)


def _mean(xs):
    return sum(xs)/len(xs) if xs else None


def _round(x):
    return round(x, 8) if x is not None else None


def _brier_for_onehot(outcome, candidate):
    return 0.0 if outcome == candidate else 2.0


def evaluate_predictions(mapping, train_counts, samples, model_outputs,
                         *, requested_per_study, source_model, model_revision,
                         elapsed_inference_seconds, elapsed_model_load_seconds):
    """Model output is aligned 1:1 with sample list. Internal per-row records
    used for metric computation only; never returned in artifacts.
    """
    seen, unseen = _guard_split(mapping)
    if not samples or len(samples)!=len(model_outputs):
        raise ValueError("sample/prediction count mismatch")
    if (type(requested_per_study) is not int or requested_per_study < 1
            or type(elapsed_inference_seconds) not in (int,float)
            or type(elapsed_model_load_seconds) not in (int,float)
            or not all(isfinite(x) and x>=0 for x in
                    (elapsed_model_load_seconds,elapsed_inference_seconds))):
        raise ValueError("invalid sample size or timing")
    freq = Counter()
    for study,code,count in train_counts:
        if study not in seen or code not in BUCKETS or type(count) is not int or count < 1:
            raise ValueError("training count contamination")
        freq[code] += count
    total=sum(freq.values())
    if total<=0:raise ValueError("training counts missing")
    prior={k:freq[k]/total for k in BUCKETS}
    majority=max(BUCKETS,key=lambda k:prior[k])
    grouped=defaultdict(list)
    for (study,outcome),raw_pred in zip(samples,model_outputs):
        if study not in unseen or outcome not in BUCKETS:
            raise ValueError("test study or label invalid")
        decoded=parse_generated_response(raw_pred)
        grouped[study].append((outcome,decoded))
    if set(grouped)!=unseen:
        raise ValueError("all forty never-trained-on studies required")
    if any(len(v)!=requested_per_study for v in grouped.values()):
        raise ValueError("test study samples must match predeclared count")
    results=[]
    for study,records in grouped.items():
        n=len(records)
        outcomes=[o for o,_ in records]
        preds=[p for _,p in records]
        correct_majority=sum(o==majority for o in outcomes)
        valid=sum(x is not None for x in preds)
        correct_model=sum(o==p for o,p in records if p is not None)
        mean_prior_acc=sum(prior[o] for o in outcomes)/n
        mean_prior_brier=sum(1+sum(v*v for v in prior.values())-2*prior[o] for o in outcomes)/n
        q={k:outcomes.count(k)/n for k in BUCKETS}
        group_pred=Counter(p for p in preds if p is not None)
        pred_probs={k:group_pred[k]/valid for k in BUCKETS} if valid else None
        tvd_f=.5*sum(abs(prior[k]-q[k]) for k in BUCKETS)
        tvd_majority=1-q[majority]
        tvd_model=.5*sum(abs(pred_probs[k]-q[k]) for k in BUCKETS) if valid else None
        results.append({
            "n":n,"valid":valid,"code_other":outcomes.count("OTHER"),
            "majority_accuracy":correct_majority/n,
            "frequency_expected_accuracy":mean_prior_acc,
            "frequency_brier":mean_prior_brier,
            "frequency_tvd":tvd_f,"majority_tvd":tvd_majority,
            "pretrained_coverage":valid/n,
            "pretrained_accuracy_with_abstention_wrong":correct_model/n,
            "pretrained_valid_only_accuracy":correct_model/valid if valid else None,
            "pretrained_tvd_valid_only":tvd_model,
            "pretrained_brier_valid_only":(_mean([_brier_for_onehot(o,p) for o,p in records if p is not None])),
        })
    n_all=sum(r["n"] for r in results)
    def wavg(key):
        values=[(r[key],r["n"]) for r in results if r[key] is not None]
        if not values:return None
        return _round(sum(v*n for v,n in values)/sum(n for _,n in values))
    def macro(key):
        v=[r[key] for r in results if r[key] is not None]
        return _round(_mean(v))
    rng=Random(20261021)
    boots=[]
    for _ in range(1000):
        draws=[results[rng.randrange(len(results))] for _ in results]
        boots.append(_mean([d["frequency_tvd"] for d in draws]))
    boots.sort()
    total_valid=sum(r["valid"] for r in results)
    return {
      "schema":"manager.phase04.socsci210.real-individual-heldout-openmodel.v1",
      "model":{"id":source_model,"revision":model_revision,"license":"Apache-2.0", "training":"public pre-trained checkpoint, not fitted on current heldout labels",
               "load_seconds":_round(elapsed_model_load_seconds),
               "inference_seconds":_round(elapsed_inference_seconds),
               "median_tokens_per_sample":"NOT_RECORDED",
               "samples_per_second":_round(n_all/elapsed_inference_seconds) if elapsed_inference_seconds else None,
               "direct_paid_api_cost_usd":0,
               "electricity_hardware_cost_usd":"NOT_MEASURED"},
      "evaluation":{"unit":"individual survey response code on unseen study; NOT an interpretable universal behavioral label",
                    "seen_training_studies":len(seen),"unseen_test_studies":len(unseen),
                    "individual_test_rows":n_all,"sampling":"hash(study_id,participant,sample_id,task_num,condition_num), response EXCLUDED",
                    "predeclared_per_study":requested_per_study,
                    "global_majority_label":majority,
                    "mean_original_response_OTHER_rate":_round(sum(r["code_other"] for r in results)/n_all)},
      "same_sample_scores":{
        "frequency_expected_accuracy_micro":wavg("frequency_expected_accuracy"),
        "frequency_brier_micro":wavg("frequency_brier"),
        "frequency_tvd_micro":wavg("frequency_tvd"),
        "frequency_tvd_macro":macro("frequency_tvd"),
        "majority_accuracy_micro":wavg("majority_accuracy"),
        "majority_tvd_micro":wavg("majority_tvd"),
        "pretrained_accuracy_including_abstentions_as_wrong":wavg("pretrained_accuracy_with_abstention_wrong"),
        "pretrained_coverage":_round(total_valid/n_all),
        "pretrained_accuracy_valid_only_macro":macro("pretrained_valid_only_accuracy"),
        "pretrained_tvd_valid_only_macro":macro("pretrained_tvd_valid_only"),
        "pretrained_brier_valid_only_macro":macro("pretrained_brier_valid_only"),
      },
      "study_level_uncertainty":{"n":40,"frequency_tvd_macro_bootstrap_ci95":[_round(boots[25]),_round(boots[974])],"resamples":1000,"unit":"study"},
      "subgroup":{
        "response_other_rate":_round(sum(r["code_other"] for r in results)/n_all),
        "study_coverage_min":_round(min(r["pretrained_coverage"] for r in results)),
        "study_coverage_max":_round(max(r["pretrained_coverage"] for r in results)),
        "studies_with_zero_valid_model_responses":sum(r["valid"]==0 for r in results)},
      "deployment_decision":"ABSTAIN: individual response codes not semantically matched across source studies",
      "scientific_scope":{
        "individual_records_evaluated":True,
        "same_exact_test_sample_all_models":True,
        "text_model_executed_on_real_unseen_prompts":True,
        "canonical_socrates_task_aware_metric_reproduced":False,
        "author_llama8b_or_qwen14b_model_evaluated":False,
        "causal_effect_validated":False,
        "person_level_prediction_clinically_or_socially_validated":False,
        "independent_real_world_manager_benefit":False,
        "warning":"Generic numeric code has differing meaning and option sets by task and study; one-hot model outputs are not calibrated probability vectors"},
      "privacy":{"raw_person_rows_in_report":0,"participant_identifiers_in_report":False,"prompts_in_report":False,"generated_text_in_report":False,"published_per_person_predictions":False,
                 "evaluation_fully_local_no_external_inference_api":True}
    }
