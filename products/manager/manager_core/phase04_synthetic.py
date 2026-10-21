"""S002-S008 preparation: safe synthetic evaluation, not human prediction evidence.

This intentionally does not ingest SocSci210 respondent records and cannot
satisfy the empirical study/model/generalization gates by itself.
"""
from collections import defaultdict
from math import isfinite
from numbers import Real
from typing import Mapping

from manager_core.calibration import assert_disjoint_groups
from manager_core.evaluation import brier_score, total_variation


def _binary_values(ys):
    if not isinstance(ys, (list, tuple)) or not ys:
        raise ValueError("nonempty binary sequence required")
    if any(type(y) is not int or y not in (0, 1) for y in ys):
        raise ValueError("only integer 0/1 outcomes are allowed")
    return ys


def binary_baselines(train_outcomes):
    """Train once on labeled TRAIN outcomes; never inspect held-out responses."""
    ys = _binary_values(train_outcomes)
    rate = sum(ys) / len(ys)
    return {"frequency": rate, "majority": int(rate >= 0.5), "train_n": len(ys)}


def _distribution(prob):
    return {"yes": float(prob), "no": float(1 - prob)}


def wasserstein_ordinal(p, q, values):
    """1D Earth Mover's / W1 on an ordered, normalized [0,1] response scale.

    The Socrates paper uses Wasserstein after normalizing ordinal labels.
    TVD is a separate distribution diagnostic; DO NOT equate the two.
    """
    if (not all(isinstance(x, (list, tuple)) for x in (p, q, values))
            or len(p) != len(q) or len(p) != len(values) or len(p) < 2):
        raise ValueError("matching ordered categorical distributions required")
    if any(type(v) not in (int, float) or not isfinite(v) for v in values):
        raise ValueError("finite numeric response coordinates required")
    if values[0] < 0 or values[-1] > 1 or any(a >= b for a,b in zip(values, values[1:])):
        raise ValueError("strictly ordered normalized responses required")
    for dist in (p, q):
        if any(type(x) not in (int, float) or not isfinite(x) or x < 0 or x > 1
               for x in dist) or abs(sum(dist) - 1) > 1e-9:
            raise ValueError("finite categorical probabilities summing to one required")
    cumulative_p = 0.0
    cumulative_q = 0.0
    result = 0.0
    for i in range(len(values) - 1):
        cumulative_p += p[i]
        cumulative_q += q[i]
        result += abs(cumulative_p - cumulative_q) * (values[i+1] - values[i])
    return result


def compare_on_unseen_studies(train_studies, unseen_studies, train_outcomes,
                              heldout_rows, *, max_scenario_tvd=0.2,
                              min_scenario_n=4):
    """Validate distinct study IDs and evaluate naive baselines on synthetic rows.

    Acceptance is LOCAL METHOD correctness only; not SocSci210 40-study results.
    """
    assert_disjoint_groups(train_studies, unseen_studies)
    if len(set(train_studies)) != len(train_studies) or len(set(unseen_studies)) != len(unseen_studies):
        raise ValueError("duplicate study identifiers in a split")
    if (type(max_scenario_tvd) not in (int, float)
            or not isfinite(max_scenario_tvd) or not 0 <= max_scenario_tvd <= 1
            or type(min_scenario_n) is not int or min_scenario_n < 1):
        raise ValueError("unsafe calibration/abstention threshold")
    if not isinstance(heldout_rows, (list, tuple)) or not heldout_rows:
        raise ValueError("nonempty heldout rows required")
    ys = []
    groups = defaultdict(list)
    for row in heldout_rows:
        if not isinstance(row, Mapping) or set(row) != {"study_id", "scenario", "outcome"}:
            raise ValueError("study/scenario/binary-only fields; no participant data")
        study, scenario, y = row["study_id"], row["scenario"], row["outcome"]
        if study not in unseen_studies or type(scenario) is not str or not scenario:
            raise ValueError("unknown heldout study or scenario")
        if type(y) is not int or y not in (0, 1):
            raise ValueError("heldout outcome must be integer binary")
        ys.append(y)
        groups[scenario].append(y)
    base = binary_baselines(train_outcomes)
    result = {}
    actual = sum(ys) / len(ys)
    for name in ("frequency", "majority"):
        p = base[name]
        result[name] = {
            "accuracy": sum(int((p >= 0.5) == bool(y)) for y in ys) / len(ys),
            "brier": brier_score([p] * len(ys), ys),
            "overall_tvd": total_variation(_distribution(p), _distribution(actual)),
            "train_n": base["train_n"],
            "test_n": len(ys),
        }
    novel = []
    for key in sorted(groups):
        response = groups[key]
        empirical_rate = sum(response) / len(response)
        tvd = total_variation(_distribution(base["frequency"]), _distribution(empirical_rate))
        decision = "ABSTAIN" if len(response) < min_scenario_n or tvd > max_scenario_tvd else "NOT_ABSTAIN_TOY"
        novel.append({"scenario": key, "n": len(response),
                      "observed_binary_rate": empirical_rate,
                      "frequency_model_tvd": tvd,
                      "decision": decision})
    return {
        "basis": "SYNTHETIC_ONLY",
        "heldout_study_count": len(set(row["study_id"] for row in heldout_rows)),
        "total_heldout_records": len(ys),
        "test_studies_disjoint": True,
        "real_study_evaluated": False,
        "real_world_impact_measured": False,
        "baselines": result,
        "novel_scenarios": novel,
        "thresholds": {"max_scenario_tvd": max_scenario_tvd,
                       "min_scenario_n": min_scenario_n},
    }


def constructed_causal_gap():
    """Counterexample in a hand-constructed randomized world, NOT a field RCT.

    Equal randomization of 0/1 and p(Y=1|do(0))=.3, p(Y=1|do(1))=.7
    yield marginal probability .5. A treatment-blind model predicting
    .5 always matches the marginal exactly but misses ATE=.4 entirely.
    """
    control, treated, blind = 0.3, 0.7, 0.5
    return {
        "basis": "SYNTHETIC_CONSTRUCTED_WORLD",
        "marginal_tvd": total_variation(_distribution(blind),
                                      _distribution((control + treated) / 2)),
        "known_treatment_effect_in_constructed_world": treated - control,
        "treatment_blind_predicted_effect": blind - blind,
        "effect_error": abs((treated - control) - (blind - blind)),
        "random_assignment": "ASSUMED_IN_CONSTRUCTED_WORLD_ONLY",
        "real_world_causal_validation": False,
    }


def synthetic_phase04_report():
    """Exactly two novel synthetic conditions, no real participants."""
    toy = compare_on_unseen_studies(
        ["train-only"], ["unseen-A", "unseen-B"], [1, 1, 0, 0],
        [
            *[{"study_id": "unseen-A", "scenario": "new-A", "outcome": y}
              for y in (1, 0, 0, 0)],
            *[{"study_id": "unseen-B", "scenario": "new-B", "outcome": y}
              for y in (1, 1, 1, 0)],
        ],
    )
    return {
        "schema": "manager.phase04.offline-methods.v1",
        "source": "HAND_CONSTRUCTED_SYNTHETIC_FIXTURES_ONLY",
        "study_evaluation": toy,
        "causal_counterexample": constructed_causal_gap(),
        "real_soc_sci_benchmark": "NOT_PERFORMED_RIGHTS_HOLD",
        "published_socrates_comparison": "NOT_PERFORMED",
        "concordia_run": "NOT_PERFORMED_BY_THIS_SCRIPT",
        "real_beneficiaries": 0,
        "scientific_task_completion": False,
    }
