#!/usr/bin/env python3
"""Aggregate-only HeartSteps phase-3 reproduction using the pinned public CSV.

No participant row is written to output. The model is an independent Python
implementation of the publicly described centered weighted least-squares shape,
with participant-cluster sandwich covariance and an explicit small-sample factor.
It does not copy the unlicensed upstream R implementation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen

SOURCE_COMMIT = "3016391de426116bdef41880d72bc8cd4b9b2477"
SOURCE_URL = (
    "https://raw.githubusercontent.com/klasnja/HeartStepsV1/"
    f"{SOURCE_COMMIT}/data_files/suggestions.csv"
)
PAPER = {
    "included": 7540,
    "available": 6061,
    "sent": 3594,
    "walking": 2015,
    "sedentary": 1579,
    "mean_steps": 253,
    "sd_steps": 473,
    "raw_missing": 1434,
    "any_ratio": 1.14,
    "any_ci": [0.99, 1.31],
    "walking_ratio": 1.24,
    "walking_ci": [1.04, 1.47],
    "initial_any_ratio": 1.66,
    "daily_any_ratio": 0.98,
}
MISSING = {"", "NA", "NaN", "nan", "N/A", "NULL", "null"}


def _missing(value):
    return value is None or str(value).strip() in MISSING


def _bool(value):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "t", "1"}:
        return True
    if text in {"false", "f", "0"}:
        return False
    raise ValueError(f"invalid boolean {value!r}")


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite numeric value")
    return number


def study_day_from_decision_index(value):
    number = _float(value)
    if number < 0 or not number.is_integer():
        raise ValueError("decision.index.nogap must be a nonnegative integer")
    return int(number) // 5


def select_analysis_rows(rows):
    selected, available = [], []
    audit = {
        "input_rows": 0,
        "missing_nogap_index": 0,
        "beyond_day_41": 0,
        "unavailable_but_sent_anomaly": 0,
        "missing_action": 0,
        "included": 0,
        "available": 0,
    }
    for raw in rows:
        audit["input_rows"] += 1
        index = raw.get("decision.index.nogap")
        if _missing(index):
            audit["missing_nogap_index"] += 1
            continue
        day = study_day_from_decision_index(index)
        if day > 41:
            audit["beyond_day_41"] += 1
            continue
        is_available = _bool(raw["avail"])
        sent = _bool(raw["send"])
        if not is_available and sent:
            audit["unavailable_but_sent_anomaly"] += 1
            continue
        if _missing(raw.get("send.active")) or _missing(raw.get("send.sedentary")):
            audit["missing_action"] += 1
            continue
        row = {
            "user": str(raw["user.index"]),
            "study_day": day,
            "avail": is_available,
            "send": sent,
            "send_active": _bool(raw["send.active"]),
            "send_sedentary": _bool(raw["send.sedentary"]),
            "outcome": _float(raw["jbsteps30.zero"]),
            "pre": _float(raw["jbsteps30pre.zero"]),
            "raw_outcome_missing": _missing(raw.get("jbsteps30")),
        }
        selected.append(row)
        if is_available:
            available.append(row)
    audit["included"] = len(selected)
    audit["available"] = len(available)
    return selected, available, audit


def descriptive_summary(rows):
    outcomes = [row["outcome"] for row in rows]
    sent = sum(row["send"] for row in rows)
    walking = sum(row["send_active"] for row in rows)
    sedentary = sum(row["send_sedentary"] for row in rows)
    return {
        "participants": len({row["user"] for row in rows}),
        "decision_points": len(rows),
        "sent": sent,
        "walking": walking,
        "sedentary": sedentary,
        "no_suggestion": len(rows) - sent,
        "mean_steps": statistics.fmean(outcomes) if outcomes else None,
        "sd_steps": statistics.stdev(outcomes) if len(outcomes) > 1 else None,
        "raw_outcome_missing": sum(row["raw_outcome_missing"] for row in rows),
        "descriptive_only": True,
        "causal_effect_estimated": False,
    }


def _invert(matrix):
    size = len(matrix)
    if size == 0 or any(len(row) != size for row in matrix):
        raise ValueError("square matrix required")
    work = [
        list(map(float, row)) + [1.0 if i == j else 0.0 for j in range(size)]
        for i, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) < 1e-12:
            raise ValueError("singular design")
        work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        work[column] = [value / divisor for value in work[column]]
        for row in range(size):
            if row == column:
                continue
            factor = work[row][column]
            work[row] = [x - factor * y for x, y in zip(work[row], work[column])]
    return [row[size:] for row in work]


def _matmul(left, right):
    return [
        [
            sum(left[i][k] * right[k][j] for k in range(len(right)))
            for j in range(len(right[0]))
        ]
        for i in range(len(left))
    ]


def _matvec(matrix, vector):
    return [sum(x * y for x, y in zip(row, vector)) for row in matrix]


def _outer(left, right):
    return [[x * y for y in right] for x in left]


def _add(left, right):
    return [[x + y for x, y in zip(a, b)] for a, b in zip(left, right)]


def weighted_cluster_regression(x, y, groups, weights):
    n = len(y)
    if not (n and len(x) == len(groups) == len(weights) == n):
        raise ValueError("equal nonempty inputs required")
    k = len(x[0])
    if any(len(row) != k for row in x):
        raise ValueError("ragged design")
    if any(weight <= 0 or not math.isfinite(weight) for weight in weights):
        raise ValueError("positive finite weights required")
    xtwx = [[0.0] * k for _ in range(k)]
    xtwy = [0.0] * k
    for row, outcome, weight in zip(x, y, weights):
        if not all(math.isfinite(value) for value in row + [outcome]):
            raise ValueError("finite design required")
        for i in range(k):
            xtwy[i] += weight * row[i] * outcome
            for j in range(k):
                xtwx[i][j] += weight * row[i] * row[j]
    bread = _invert(xtwx)
    beta = _matvec(bread, xtwy)
    scores = defaultdict(lambda: [0.0] * k)
    for row, outcome, group, weight in zip(x, y, groups, weights):
        residual = outcome - sum(coefficient * value for coefficient, value in zip(beta, row))
        for i in range(k):
            scores[group][i] += weight * row[i] * residual
    meat = [[0.0] * k for _ in range(k)]
    for score in scores.values():
        meat = _add(meat, _outer(score, score))
    covariance = _matmul(_matmul(bread, meat), bread)
    clusters = len(scores)
    correction = (
        (clusters / (clusters - 1)) * ((n - 1) / (n - k))
        if clusters > 1 and n > k
        else 1.0
    )
    covariance = [[value * correction for value in row] for row in covariance]
    standard_errors = [math.sqrt(max(covariance[i][i], 0)) for i in range(k)]
    p_values = [
        math.erfc(abs(coefficient / error) / math.sqrt(2)) if error > 0 else None
        for coefficient, error in zip(beta, standard_errors)
    ]
    return {
        "beta": beta,
        "se": standard_errors,
        "p_normal_approx": p_values,
        "covariance_matrix": covariance,
        "n": n,
        "clusters": clusters,
        "covariance": "cluster_robust_small_sample",
        "small_sample_factor": correction,
    }


def _result(model, names, effect_name, interaction_name=None, center_probability=None):
    index = names.index(effect_name)
    coefficient = model["beta"][index]
    error = model["se"][index]
    result = {
        key: model[key]
        for key in ("n", "clusters", "covariance", "small_sample_factor")
    }
    result.update(
        {
            "terms": names,
            "coefficients": dict(zip(names, model["beta"])),
            "standard_errors": dict(zip(names, model["se"])),
            "p_normal_approx": dict(zip(names, model["p_normal_approx"])),
            "effect_term": effect_name,
            "log_effect": coefficient,
            "ratio": math.exp(coefficient),
            "ratio_ci_95_normal": [
                math.exp(coefficient - 1.96 * error),
                math.exp(coefficient + 1.96 * error),
            ],
            "center_probability": center_probability,
        }
    )
    if interaction_name:
        interaction_index = names.index(interaction_name)
        interaction = model["beta"][interaction_index]
        interaction_error = model["se"][interaction_index]
        result.update(
            {
                "interaction_term": interaction_name,
                "log_daily_interaction": interaction,
                "daily_effect_multiplier": math.exp(interaction),
                "daily_effect_multiplier_ci_95_normal": [
                    math.exp(interaction - 1.96 * interaction_error),
                    math.exp(interaction + 1.96 * interaction_error),
                ],
            }
        )
    return result


def fit_any_suggestion(rows, with_time=False):
    design, outcomes, groups, weights = [], [], [], []
    for row in rows:
        pre = math.log(row["pre"] + 0.5)
        treatment = float(row["send"]) - 0.6
        values = [1.0, pre]
        names = ["intercept", "log_pre30"]
        if with_time:
            values += [float(row["study_day"]), treatment, float(row["study_day"]) * treatment]
            names += ["study_day", "send_centered", "study_day_x_send"]
        else:
            values += [treatment]
            names += ["send_centered"]
        design.append(values)
        outcomes.append(math.log(row["outcome"] + 0.5))
        groups.append(row["user"])
        weights.append(1.0)
    model = weighted_cluster_regression(design, outcomes, groups, weights)
    return _result(
        model,
        names,
        "send_centered",
        "study_day_x_send" if with_time else None,
        0.6,
    )


def fit_walking_suggestion(rows, with_time=False):
    subset = [row for row in rows if not row["send_sedentary"]]
    design, outcomes, groups, weights = [], [], [], []
    for row in subset:
        pre = math.log(row["pre"] + 0.5)
        treatment = float(row["send_active"]) - 0.5
        values = [1.0, pre]
        names = ["intercept", "log_pre30"]
        if with_time:
            values += [float(row["study_day"]), treatment, float(row["study_day"]) * treatment]
            names += ["study_day", "walking_centered", "study_day_x_walking"]
        else:
            values += [treatment]
            names += ["walking_centered"]
        design.append(values)
        outcomes.append(math.log(row["outcome"] + 0.5))
        groups.append(row["user"])
        weights.append(3.0 / (float(row["send_active"]) + 2.0))
    model = weighted_cluster_regression(design, outcomes, groups, weights)
    return _result(
        model,
        names,
        "walking_centered",
        "study_day_x_walking" if with_time else None,
        0.5,
    )


def compare_to_paper(report):
    descriptive = report["descriptive"]
    models = report["models"]
    return {
        "counts": {
            key: {"reproduced": report["selection"][key], "paper": PAPER[key]}
            for key in ("included", "available")
        },
        "descriptive": {
            key: {"reproduced": descriptive[key], "paper": PAPER[key]}
            for key in ("sent", "walking", "sedentary", "mean_steps", "sd_steps", "raw_missing")
        },
        "effects": {
            "any_ratio": {"reproduced": models["any_average"]["ratio"], "paper": PAPER["any_ratio"]},
            "walking_ratio": {"reproduced": models["walking_average"]["ratio"], "paper": PAPER["walking_ratio"]},
            "initial_any_ratio": {"reproduced": models["any_time"]["ratio"], "paper": PAPER["initial_any_ratio"]},
            "daily_any_ratio": {"reproduced": models["any_time"]["daily_effect_multiplier"], "paper": PAPER["daily_any_ratio"]},
        },
    }


def build_phase3_report(selected, available, audit):
    descriptive = descriptive_summary(available)
    descriptive["raw_missing"] = descriptive.pop("raw_outcome_missing")
    report = {
        "schema": "manager.heartsteps.phase3.v1",
        "selection": audit,
        "descriptive": descriptive,
        "models": {
            "any_average": fit_any_suggestion(available, False),
            "any_time": fit_any_suggestion(available, True),
            "walking_average": fit_walking_suggestion(available, False),
            "walking_time": fit_walking_suggestion(available, True),
        },
        "method": {
            "outcome": "log(jbsteps30.zero + 0.5)",
            "pretreatment": "log(jbsteps30pre.zero + 0.5)",
            "day_derivation": "floor(decision.index.nogap / 5), zero-based",
            "estimator": "independent weighted least squares with participant-cluster sandwich covariance",
            "difference_from_author": "Does not copy xgeepack small-sample correction; uses documented standard cluster factor and normal-approximation CI.",
        },
        "privacy": {"participant_rows_in_report": False, "raw_data_persisted": False},
        "claims": {
            "external_study_reproduction": True,
            "manager_intervention": False,
            "manager_human_benefit": False,
        },
    }
    report["paper_comparison"] = compare_to_paper(report)
    return report


def download(url, path):
    request = Request(url, headers={"User-Agent": "Anicca-Manager-Research/1.0"})
    with urlopen(request, timeout=120) as response, path.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)


def load_minimal(path):
    required = [
        "user.index",
        "decision.index.nogap",
        "avail",
        "send",
        "send.active",
        "send.sedentary",
        "jbsteps30",
        "jbsteps30.zero",
        "jbsteps30pre.zero",
    ]
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in required if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing columns {missing}")
        for raw in reader:
            rows.append({column: raw[column] for column in required})
    return rows


def write_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "heartsteps_phase3.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    selection = report["selection"]
    descriptive = report["descriptive"]
    models = report["models"]
    lines = [
        "# HeartSteps V1 — independent aggregate reproduction",
        "",
        f"- Included decision points: **{selection['included']:,}** (paper: 7,540)",
        f"- Available decision points: **{selection['available']:,}** (paper: 6,061)",
        f"- Participants: **{descriptive['participants']}**",
        f"- Mean 30-min steps: **{descriptive['mean_steps']:.2f}**; SD **{descriptive['sd_steps']:.2f}**",
        f"- Sent / walking / sedentary: **{descriptive['sent']:,} / {descriptive['walking']:,} / {descriptive['sedentary']:,}**",
        "",
        "| Model | Reproduced ratio | 95% normal approx CI | Paper |",
        "|---|---:|---:|---:|",
        f"| Any suggestion, average | {models['any_average']['ratio']:.3f} | {models['any_average']['ratio_ci_95_normal'][0]:.3f}–{models['any_average']['ratio_ci_95_normal'][1]:.3f} | 1.14 |",
        f"| Walking suggestion, average | {models['walking_average']['ratio']:.3f} | {models['walking_average']['ratio_ci_95_normal'][0]:.3f}–{models['walking_average']['ratio_ci_95_normal'][1]:.3f} | 1.24 |",
        f"| Any suggestion, day 0 | {models['any_time']['ratio']:.3f} | {models['any_time']['ratio_ci_95_normal'][0]:.3f}–{models['any_time']['ratio_ci_95_normal'][1]:.3f} | 1.66 |",
        f"| Daily effect multiplier | {models['any_time']['daily_effect_multiplier']:.3f} | {models['any_time']['daily_effect_multiplier_ci_95_normal'][0]:.3f}–{models['any_time']['daily_effect_multiplier_ci_95_normal'][1]:.3f} | 0.98 |",
        "",
        "This independently implements the public model shape. It does not copy the unlicensed R scripts or claim exact replication of their small-sample correction.",
        "No participant rows are included. This is an external research reproduction, not Manager field impact.",
    ]
    (output / "heartsteps_phase3.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="heartsteps-phase3-") as tmp:
        raw = Path(tmp) / "suggestions.csv"
        download(SOURCE_URL, raw)
        rows = load_minimal(raw)
        selected, available, audit = select_analysis_rows(rows)
        if audit["included"] != PAPER["included"] or audit["available"] != PAPER["available"]:
            raise SystemExit(f"analysis-set mismatch {audit}")
        report = build_phase3_report(selected, available, audit)
        write_report(report, args.output)
        print(
            json.dumps(
                {
                    "included": audit["included"],
                    "available": audit["available"],
                    "participants": report["descriptive"]["participants"],
                    "any_ratio": report["models"]["any_average"]["ratio"],
                    "walking_ratio": report["models"]["walking_average"]["ratio"],
                    "raw_persisted": False,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
