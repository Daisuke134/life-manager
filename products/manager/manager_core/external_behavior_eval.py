"""Study-clustered diagnostics for fixed, released aggregate effect predictions.

This module accepts records already validated by the pinned snapshot inspector.
It returns aggregate diagnostics only; it does not read files or generate predictions.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Mapping

import numpy as np
from scipy import linalg, stats


class EvaluationError(ValueError):
    """Invalid rows, split, or objective mapping."""


_TOL = 1e-10
_SPLIT_SEED = 20261022


def _number(value: Any) -> float:
    if value is None or isinstance(value, (bool, str)):
        raise EvaluationError("INVALID_NUMBER")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise EvaluationError("INVALID_NUMBER") from None
    if not math.isfinite(number) or not -1 <= number <= 1:
        raise EvaluationError("INVALID_NUMBER")
    return number


def _validated_pairs(rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], list[tuple[float, float]]], dict[str, str]]:
    if not isinstance(rows, list) or not rows:
        raise EvaluationError("INVALID_ROWS")
    directed: dict[tuple[str, str, str, str], tuple[float, float]] = {}
    groups: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise EvaluationError("INVALID_ROW")
        study, outcome = row.get("study"), row.get("outcome.name")
        reference, condition, group = row.get("reference_condition"), row.get("condition.name"), row.get("group")
        if any(not isinstance(v, str) or not v for v in (study, outcome, reference, condition)) or reference == condition:
            raise EvaluationError("INVALID_LABEL")
        if not isinstance(group, str) or group not in {"published", "unpublished"}:
            raise EvaluationError("INVALID_GROUP")
        if study in groups and groups[study] != group:
            raise EvaluationError("INCONSISTENT_STUDY_GROUP")
        groups[study] = group
        key = (study, outcome, reference, condition)
        if key in directed:
            raise EvaluationError("DUPLICATE_CONTRAST")
        directed[key] = (_number(row.get("estimate")), _number(row.get("prediction")))

    pairs: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    unordered: set[tuple[str, str, str, str]] = set()
    for (study, outcome, reference, condition), value in directed.items():
        reverse_key = (study, outcome, condition, reference)
        reverse = directed.get(reverse_key)
        if reverse is None or abs(value[0] + reverse[0]) > _TOL or abs(value[1] + reverse[1]) > _TOL:
            raise EvaluationError("REVERSE_MISMATCH")
        if (study, outcome, min(reference, condition), max(reference, condition)) in unordered:
            continue
        unordered.add((study, outcome, min(reference, condition), max(reference, condition)))
        sign = 1.0 if reference < condition else -1.0
        pairs[(study, outcome)].append((sign * value[0], sign * value[1]))
    if not unordered:
        raise EvaluationError("INVALID_ROWS")
    return {key: sorted(values) for key, values in sorted(pairs.items())}, groups


def make_fixed_study_split(groups: Mapping[str, str], seed: int = _SPLIT_SEED) -> tuple[dict[str, str], str]:
    """Hash-stratified 50/50 split; v1 sorts SHA256(seed, study) within group."""
    if type(seed) is not int or not groups:
        raise EvaluationError("INVALID_SPLIT")
    split: dict[str, str] = {}
    for group in ("published", "unpublished"):
        members = [study for study, value in groups.items() if value == group]
        if len(members) < 2:
            raise EvaluationError("STRATUM_TOO_SMALL")
        ordered = sorted(members, key=lambda study: (hashlib.sha256(f"{seed}\0{study}".encode()).hexdigest(), study))
        train_count = len(ordered) // 2
        split.update({study: "train" for study in ordered[:train_count]})
        split.update({study: "test" for study in ordered[train_count:]})
    if set(split) != set(groups):
        raise EvaluationError("INVALID_GROUP")
    canonical = json.dumps(sorted(split.items()), separators=(",", ":"), ensure_ascii=True).encode()
    return split, hashlib.sha256(canonical).hexdigest()


def _study_losses(pairs: Mapping[tuple[str, str], list[tuple[float, float]]], split: Mapping[str, str], beta: float | None) -> dict[str, dict[str, Any]]:
    blocks: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: {name: [] for name in ("zero", "raw", "calibrated")})
    for key, observations in pairs.items():
        for estimate, prediction in observations:
            blocks[key]["zero"].append(abs(estimate))
            blocks[key]["raw"].append(abs(prediction - estimate))
            if beta is not None:
                blocks[key]["calibrated"].append(abs(beta * prediction - estimate))
    study_scores: dict[str, dict[str, Any]] = {}
    for (study, _outcome), values in blocks.items():
        entry = study_scores.setdefault(study, {name: [] for name in ("zero", "raw", "calibrated")})
        for name, losses in values.items():
            if losses:
                entry[name].append(float(np.mean(losses)))
    return {
        study: {"split": split[study], **{name: (float(np.mean(values[name])) if values[name] else None) for name in ("zero", "raw", "calibrated")}}
        for study, values in study_scores.items()
    }


def _score_metrics(pairs: Mapping[tuple[str, str], list[tuple[float, float]]], studies: set[str], beta: float | None) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for name in ("zero", "raw", "calibrated"):
        if name == "calibrated" and beta is None:
            metrics[name] = {
                "mae_full_scale": None,
                "rmse_full_scale": None,
                "direction": {"reason": "CALIBRATION_RANK_DEFICIENT"},
                "pearson_r_descriptive_only": {"value": None, "reason": "CALIBRATION_RANK_DEFICIENT"},
            }
            continue
        block_abs: dict[tuple[str, str], list[float]] = defaultdict(list)
        block_sq: dict[tuple[str, str], list[float]] = defaultdict(list)
        by_study: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"abs": [], "sq": []})
        directions = {"agreement": 0, "observed_zero": 0, "prediction_tie": 0, "eligible": 0}
        study_direction_rates: list[float] = []
        observed: list[float] = []
        predicted: list[float] = []
        for (study, _outcome), contrasts in pairs.items():
            if study not in studies:
                continue
            for estimate, prediction in contrasts:
                forecast = 0.0 if name == "zero" else prediction if name == "raw" else beta * prediction
                error = forecast - estimate
                block_abs[(study, _outcome)].append(abs(error))
                block_sq[(study, _outcome)].append(error * error)
                observed.append(estimate)
                predicted.append(forecast)
                if abs(estimate) <= _TOL:
                    directions["observed_zero"] += 1
                if abs(forecast) <= _TOL:
                    directions["prediction_tie"] += 1
                if abs(estimate) > _TOL and abs(forecast) > _TOL:
                    directions["eligible"] += 1
                    directions["agreement"] += int(math.copysign(1, estimate) == math.copysign(1, forecast))
        for (study, outcome), losses in block_abs.items():
            by_study[study]["abs"].append(float(np.mean(losses)))
            by_study[study]["sq"].append(float(np.mean(block_sq[(study, outcome)])))
        for study in by_study:
            study_blocks = [(key, values) for key, values in pairs.items() if key[0] == study]
            correct = eligible = 0
            for (_s, _outcome), contrasts in study_blocks:
                for estimate, prediction in contrasts:
                    forecast = 0.0 if name == "zero" else prediction if name == "raw" else beta * prediction
                    if abs(estimate) > _TOL and abs(forecast) > _TOL:
                        eligible += 1
                        correct += int(math.copysign(1, estimate) == math.copysign(1, forecast))
            if eligible:
                study_direction_rates.append(correct / eligible)
        if not by_study:
            raise EvaluationError("EMPTY_SPLIT")
        macro_abs = [float(np.mean(values["abs"])) for values in by_study.values()]
        macro_sq = [float(np.mean(values["sq"])) for values in by_study.values()]
        corr: dict[str, Any]
        if np.ptp(observed) == 0 or np.ptp(predicted) == 0:
            corr = {"value": None, "reason": "CONSTANT_INPUT"}
        else:
            corr = {"value": float(stats.pearsonr(observed, predicted).statistic), "reason": None}
        metrics[name] = {
            "mae_full_scale": float(np.mean(macro_abs)),
            "rmse_full_scale": float(np.sqrt(np.mean(macro_sq))),
            "direction": {**directions, "agreement_rate_among_non_ties": (float(np.mean(study_direction_rates)) if study_direction_rates else None), "agreement_rate_weighting": "study_macro_among_studies_with_eligible_pairs"},
            "pearson_r_descriptive_only": corr,
        }
    return metrics


def _bootstrap(study_scores: Mapping[str, Mapping[str, Any]], seed: int, n_resamples: int, beta: float | None) -> dict[str, Any]:
    tests = sorted(study for study, values in study_scores.items() if values["split"] == "test")
    output: dict[str, Any] = {"resampling_unit": "test_study", "confidence_level": 0.95, "method": "paired_percentile_conditional_on_fixed_train_fit"}
    for candidate in ("raw", "calibrated"):
        if candidate == "calibrated" and beta is None:
            output[f"{candidate}_vs_zero"] = {"mean_gap_full_scale": None, "interval": None, "reason": "CALIBRATION_RANK_DEFICIENT", "n_test_studies": len(tests)}
            continue
        base = np.asarray([study_scores[study]["zero"] for study in tests], dtype=float)
        model = np.asarray([study_scores[study][candidate] for study in tests], dtype=float)
        if len(tests) < 2:
            output[f"{candidate}_vs_zero"] = {"mean_gap_full_scale": float(np.mean(base - model)) if len(tests) else None, "interval": None, "reason": "FEWER_THAN_TWO_TEST_STUDIES", "n_test_studies": len(tests)}
            continue
        res = stats.bootstrap((base, model), lambda x, y: np.mean(x - y), paired=True, vectorized=False,
                              n_resamples=n_resamples, confidence_level=0.95, method="percentile",
                              rng=np.random.default_rng(seed))
        output[f"{candidate}_vs_zero"] = {
            "mean_gap_full_scale": float(np.mean(base - model)),
            "interval": [float(res.confidence_interval.low), float(res.confidence_interval.high)],
            "reason": "DEGENERATE_SAMPLE" if np.ptp(base - model) == 0 else None,
            "n_test_studies": len(tests),
        }
    return output


def _selection(pairs: Mapping[tuple[str, str], list[tuple[float, float]]], split: Mapping[str, str], objectives: Mapping[tuple[str, str], int] | None, beta: float | None) -> dict[str, Any]:
    if objectives is None:
        return {"status": "OBJECTIVE_NOT_SPECIFIED", "regret": None}
    regrets: dict[str, list[float]] = {name: [] for name in ("zero", "raw", "calibrated")}
    for (study, outcome), contrasts in pairs.items():
        if split[study] != "test" or (study, outcome) not in objectives:
            continue
        sign = objectives[(study, outcome)]
        if type(sign) is not int or sign not in (-1, 1):
            raise EvaluationError("INVALID_OBJECTIVE")
        for name in regrets:
            if name == "calibrated" and beta is None:
                continue
            loss = []
            for estimate, prediction in contrasts:
                y = sign * estimate
                p = 0.0 if name == "zero" else sign * prediction * (beta if name == "calibrated" else 1.0)
                choice = 1.0 if p > _TOL else 0.0 if p < -_TOL else 0.5
                loss.append(max(0.0, y) - choice * y)
            regrets[name].append(float(np.mean(loss)))
    coverage = len(regrets["zero"])
    if not coverage:
        return {"status": "NO_COMMON_OBJECTIVE_COVERAGE", "regret": None}
    return {"status": "DESCRIPTIVE_PAIRWISE_REGRET", "coverage_outcome_blocks": coverage,
            "regret": {name: (float(np.mean(values)) if values else None) for name, values in regrets.items()}}


def evaluate_released_effects(
    rows: list[dict[str, Any]], *, study_split: Mapping[str, str], bootstrap_seed: int,
    n_resamples: int = 2000, objective_signs: Mapping[tuple[str, str], int] | None = None,
) -> dict[str, Any]:
    """Score fixed released predictions with study-level splits and macro weights."""
    pairs, groups = _validated_pairs(rows)
    if type(bootstrap_seed) is not int or type(n_resamples) is not int or n_resamples < 1:
        raise EvaluationError("INVALID_BOOTSTRAP_CONFIG")
    studies = set(groups)
    if not isinstance(study_split, Mapping) or set(study_split) != studies or any(
        not isinstance(value, str) or value not in {"train", "test"} for value in study_split.values()
    ):
        raise EvaluationError("INVALID_SPLIT")
    if objective_signs is not None and not isinstance(objective_signs, Mapping):
        raise EvaluationError("INVALID_OBJECTIVE")
    train = sorted(s for s, label in study_split.items() if label == "train")
    test = sorted(s for s, label in study_split.items() if label == "test")
    if not train or not test:
        raise EvaluationError("EMPTY_SPLIT")
    train_values = [(study, estimate, prediction) for (study, _outcome), values in pairs.items() if study in train for estimate, prediction in values]
    # Every study-outcome block and contrast receives equal hierarchical weight.
    weight_by_block: dict[tuple[str, str], float] = {}
    for key in pairs:
        if key[0] in train:
            weight_by_block[key] = 1.0 / len(train) / sum(1 for study, _outcome in pairs if study == key[0]) / len(pairs[key])
    x = np.asarray([prediction for _study, estimate, prediction in train_values], dtype=float)
    y = np.asarray([estimate for _study, estimate, _prediction in train_values], dtype=float)
    w = np.asarray([weight_by_block[(study, outcome)] for (study, outcome), values in pairs.items() if study in train for _ in values], dtype=float)
    if len(x) != len(w):
        raise EvaluationError("INVALID_ROWS")
    design = x[:, None] * np.sqrt(w)[:, None]
    target = y * np.sqrt(w)
    beta: float | None = None
    rank = 0
    if np.any(design[:, 0] != 0.0):
        coef, _residuals, rank, _singular = linalg.lstsq(design, target)
        if rank == 1:
            beta = float(coef[0])
    calibration_reason = "CALIBRATION_RANK_DEFICIENT" if beta is None or not math.isfinite(beta) else None
    if calibration_reason:
        beta = None
    study_scores = _study_losses(pairs, study_split, beta)
    test_set = set(test)
    split_digest = hashlib.sha256(
        json.dumps(sorted(study_split.items()), separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    train_directed_prediction_mean = float(np.mean([
        _number(row["prediction"]) for row in rows if row["study"] in set(train)
    ]))
    return {
        "schema_version": 1,
        "protocol": {
            "kind": "fixed_released_study_holdout_diagnostic",
            "split_algorithm": "caller_supplied_study_mapping",
            "split_digest_sha256": split_digest,
            "bootstrap_seed": bootstrap_seed,
            "n_resamples": n_resamples,
            "weighting": "pair_mean_then_outcome_mean_then_study_mean_then_test_study_mean",
            "effect_scale": "full_scale_signed_difference_in[-1,1]",
            "calibration": "train_only_weighted_through_origin_unconstrained_beta",
        },
        "counts": {"studies": len(studies), "train_studies": len(train), "test_studies": len(test), "unordered_pairs": sum(len(v) for v in pairs.values()), "study_outcome_blocks": len(pairs)},
        "calibration": {
            "beta": beta,
            "fit_studies": len(train),
            "fit_rank": int(rank),
            "fit_scope": "train_only",
            "reason": calibration_reason,
            "train_directed_mean_prediction_full_scale": train_directed_prediction_mean,
            "train_mean_baseline_alias": {"alias_of": "zero_effect", "reason": "STRUCTURAL_ANTISYMMETRY"},
        },
        "scores": _score_metrics(pairs, test_set, beta),
        "selection": _selection(pairs, study_split, objective_signs, beta),
        "uncertainty": _bootstrap(study_scores, bootstrap_seed, n_resamples, beta),
        "limitations": {
            "cluster": "Provided study IDs are the only clustering level; linked experiments with different IDs are not merged.",
            "interval": "Exploratory test-study percentile interval conditional on one fixed training fit; it excludes training-fit and effect-sampling uncertainty.",
            "exposure": "Study holdout does not establish that predictions were unseen during model pretraining.",
            "reproduction": "Does not reproduce original random-reference, attenuation correction, LOSO pilot, or megastudy top-20-percent selection protocols.",
            "benefit": "No human benefit, harm, cost, or welfare is estimated.",
        },
    }
