"""Held-out evaluation on genuinely observed, *non-personal aggregate* rentals.

Distinct from SocSci210 and from the 2019 HeartSteps RCT. The label is a
daily total of public bike rentals, not individual behavior, treatment,
randomization or causal welfare impact. Python stdlib only.
"""
from __future__ import annotations

import csv
import hashlib
import io
import random
import statistics
from collections import defaultdict
from datetime import date
from math import isfinite

from manager_core.evaluation import brier_score, total_variation

SOURCE_REPO = "KeithJLZ/UCI-Bike-Sharing-Dataset"
SOURCE_COMMIT = "f6781459ddfb55e94fc0f984c610a0cd8957b870"
SOURCE_URL = ("https://raw.githubusercontent.com/" + SOURCE_REPO +
              "/" + SOURCE_COMMIT + "/day.csv")
SOURCE_GIT_BLOB_SHA1 = "d39017f2f1ad2e70a4a854d17aada04d45608575"
SOURCE_BYTES = 57569
ORIGINAL_CITATION = "https://doi.org/10.24432/C5W894"
ORIGINAL_LICENSE = "https://creativecommons.org/licenses/by/4.0/"
ORIGINAL_CATALOG = "https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset"
FIELDS = (
    "instant", "dteday", "season", "yr", "mnth", "holiday", "weekday",
    "workingday", "weathersit", "temp", "atemp", "hum", "windspeed",
    "casual", "registered", "cnt",
)


def git_blob_sha(blob: bytes) -> str:
    if type(blob) is not bytes:
        raise ValueError("source must be exact bytes")
    return hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()


def verify_snapshot(blob: bytes, *, expected_bytes: int = SOURCE_BYTES,
                    expected_sha: str = SOURCE_GIT_BLOB_SHA1) -> str:
    if type(blob) is not bytes or len(blob) != expected_bytes:
        raise ValueError("source byte count does not match immutable snapshot")
    actual = git_blob_sha(blob)
    if actual != expected_sha:
        raise ValueError("source Git blob hash does not match immutable snapshot")
    return actual


def parse_aggregate_days(blob: bytes) -> list[dict]:
    """Fail closed on schema, duplicate dates, missing or invalid counts.

    Not a respondent dataset; contains daily rental counts and weather only.
    """
    if type(blob) is not bytes:
        raise ValueError("CSV must be bytes")
    try:
        text = blob.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("unexpected columns; participant data not accepted")
        result = []
        last_day = None
        for entry in reader:
            if set(entry) != set(FIELDS) or any(v is None or not v.strip() for v in entry.values()):
                raise ValueError("missing/extra fields")
            d = date.fromisoformat(entry["dteday"])
            if last_day is not None and d <= last_day:
                raise ValueError("duplicate or unsorted dates")
            last_day = d
            if d.year not in (2011, 2012) or int(entry["yr"]) != d.year - 2011:
                raise ValueError("outside train/test observation period")
            season = int(entry["season"])
            weather = int(entry["weathersit"])
            month = int(entry["mnth"])
            if season not in (1, 2, 3, 4) or not 1 <= weather <= 4 or month != d.month:
                raise ValueError("invalid season/weather/date")
            casual, registered, total = (int(entry[k]) for k in ("casual", "registered", "cnt"))
            if min(casual, registered, total) < 0 or casual + registered != total:
                raise ValueError("invalid aggregate rental totals")
            result.append({"date": d, "year": d.year, "season": season,
                           "weather": weather, "count": total})
        if not result:
            raise ValueError("empty data")
        return result
    except (UnicodeDecodeError, csv.Error, ValueError, OverflowError) as exc:
        raise ValueError("invalid aggregate dataset") from exc


def _distribution(p: float) -> dict:
    return {"yes": p, "no": 1.0 - p}


def _percentile(sorted_values, q):
    pos = q * (len(sorted_values) - 1)
    a = int(pos)
    b = min(len(sorted_values) - 1, a + 1)
    return sorted_values[a] * (b - pos) + sorted_values[b] * (pos - a)


def _paired_week_block_ci(errors_global, errors_season, seed=20261021, rounds=600):
    """Diagnostic week-block resampling; not an RCT or generalization guarantee."""
    n = len(errors_global)
    rng = random.Random(seed)
    step = min(7, n)
    deltas = []
    for _ in range(rounds):
        picks = []
        while len(picks) < n:
            start = rng.randrange(n - step + 1)
            picks.extend(range(start, start + step))
        picks = picks[:n]
        deltas.append(sum(errors_global[i] - errors_season[i] for i in picks) / n)
    deltas.sort()
    return [_percentile(deltas, 0.025), _percentile(deltas, 0.975)]


def _measure_binary(predictions, outcomes):
    n = len(outcomes)
    p_actual = sum(outcomes) / n
    p_mean = sum(predictions) / n
    return {
        "days": n,
        "accuracy": sum(int(int(p >= 0.5) == y) for p, y in zip(predictions, outcomes)) / n,
        "brier": brier_score(predictions, outcomes),
        "tvd": total_variation(_distribution(p_mean), _distribution(p_actual)),
        "observed_high_demand_fraction": p_actual,
        "mean_predicted_high_demand_probability": p_mean,
    }


def build_report(rows: list[dict], *, source_verified: bool) -> dict:
    if not rows or any(set(r) != {"date", "year", "season", "weather", "count"} for r in rows):
        raise ValueError("only daily aggregate observations allowed")
    train = [r for r in rows if r["year"] == 2011]
    test = [r for r in rows if r["year"] == 2012]
    if len(train) < 2 or len(test) < 2:
        raise ValueError("both chronological partitions required")
    threshold = statistics.median(r["count"] for r in train)
    labels_train = [int(r["count"] >= threshold) for r in train]
    labels_test = [int(r["count"] >= threshold) for r in test]
    probability_global = sum(labels_train) / len(train)
    probability_majority = float(probability_global >= 0.5)
    mean_global = statistics.mean(r["count"] for r in train)
    by_season = defaultdict(list)
    for r in train:
        by_season[r["season"]].append(r["count"])
    if set(by_season) != {1, 2, 3, 4}:
        # Educational fixtures may have 1/3; any truly unseen season must abstain.
        pass
    p_season = {}
    mean_season = {}
    for s, vals in by_season.items():
        p_season[s] = sum(int(v >= threshold) for v in vals) / len(vals)
        mean_season[s] = statistics.mean(vals)
    if any(r["season"] not in by_season for r in test):
        raise ValueError("unsupported season: abstain rather than invent predictions")
    predictions = {
        "frequency": [probability_global] * len(test),
        "majority": [probability_majority] * len(test),
        "season_only": [p_season[r["season"]] for r in test],
    }
    day_estimates = {
        "frequency": [mean_global] * len(test),
        "majority": [mean_global] * len(test),
        "season_only": [mean_season[r["season"]] for r in test],
    }
    models = {}
    for name, probs in predictions.items():
        outcome = _measure_binary(probs, labels_test)
        outcome["mae_daily_rentals"] = sum(
            abs(p - r["count"]) for p, r in zip(day_estimates[name], test)
        ) / len(test)
        models[name] = outcome
    # Preregistered test environments, both observed after 2011 fit.
    novel = []
    for label, season in (("winter_2012", 1), ("summer_2012", 3)):
        indices = [i for i, r in enumerate(test) if r["season"] == season]
        if not indices:
            raise ValueError("missing one of two predeclared validation environments")
        slice_y = [labels_test[i] for i in indices]
        slice_preds = [predictions["season_only"][i] for i in indices]
        report = _measure_binary(slice_preds, slice_y)
        report.update({
            "name": label,
            "mean_daily_rentals": sum(test[i]["count"] for i in indices) / len(indices),
            "mae_daily_rentals_season_only": sum(
                abs(day_estimates["season_only"][i] - test[i]["count"]) for i in indices
            ) / len(indices),
            "type": "same city, new year; NOT a new person population",
        })
        novel.append(report)
    err_global = [abs(mean_global - r["count"]) for r in test]
    err_season = [abs(mean_season[r["season"]] - r["count"]) for r in test]
    parameters = {
        "frequency_p": probability_global, "majority_p": probability_majority,
        "global_mean_rentals": mean_global,
        "season_p": {str(s): p_season[s] for s in sorted(p_season)},
        "season_mean_rentals": {str(s): mean_season[s] for s in sorted(mean_season)},
    }
    return {
        "schema": "manager.phase04.public-aggregate-heldout.v1",
        "source_kind": "PUBLIC_AGGREGATE_OBSERVED",
        "source_snapshot_verified": bool(source_verified),
        "empirical_unit": "daily aggregate rental count",
        "license": "CC-BY-4.0 attribution required",
        "source": {
            "catalog": ORIGINAL_CATALOG, "doi": ORIGINAL_CITATION,
            "license_url": ORIGINAL_LICENSE, "pinned_mirror": SOURCE_URL,
            "git_blob_sha1": SOURCE_GIT_BLOB_SHA1,
            "source_bytes": SOURCE_BYTES,
        },
        "train_days": len(train), "heldout_days": len(test),
        "split": {"train_year": 2011, "test_year": 2012,
                  "training_features": ["season"],
                  "training_label": "daily_rentals_above_2011_median",
                  "target_and_future_year_excluded_from_features": True,
                  "train_test_date_disjoint": not bool(
                      {r["date"] for r in train} & {r["date"] for r in test}
                  ) is False},
        "train_threshold_daily_rentals": threshold,
        "train_fitted_parameters": parameters,
        "baselines": models,
        "heldout_conditions": novel,
        "block_bootstrap": {
            "block_days": 7, "repeats": 600, "seed": 20261021,
            "mae_gain_season_minus_global_ci95": _paired_week_block_ci(err_global, err_season),
            "interpretation": "MAE(global)-MAE(season); paired 7-day blocks; no causal inference",
        },
        "socsci210_human_benchmark": "NOT_PERFORMED_RIGHTS_HOLD",
        "public_pretrained_model_comparison": "NOT_PERFORMED",
        "individual_human_behavior_validated": False,
        "randomized_intervention_test": False,
        "causal_effect_estimated": False,
        "manager_benefit_proven": False,
        "scientific_limitations": (
            "not an unseen SocSci210 study; single-city observational year shift; "
            "weather, supply and secular trend can confound rentals; "
            "no simulation of individual human responses or causal intervention"
        ),
        "privacy": {"participant_records": 0, "raw_rows_published": False,
                    "dates_in_aggregate_report": False},
    }
