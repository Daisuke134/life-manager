#!/usr/bin/env python3
"""Read-only aggregate mapping audit; no participant-level results are exported."""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

SOURCE_COMMIT = "3016391de426116bdef41880d72bc8cd4b9b2477"
BASE = f"https://raw.githubusercontent.com/klasnja/HeartStepsV1/{SOURCE_COMMIT}/data_files/"
SUGGESTIONS_BLOB_SHA1 = "67a55efd4d79e1f5646bdb26277f37ec988e2403"
SUGGESTIONS_BYTES = 4371854
JAWBONE_BLOB_SHA1 = "1a8da5a8e3cbd9126cc624f0ff3b59a1570dd4cf"
JAWBONE_BYTES = 17652097
MISSING = {"", "NA", "NaN", "nan", "N/A", "NULL", "null"}

def _required(reader, names):
    columns = reader.fieldnames
    if not columns or not set(names).issubset(columns):
        raise ValueError("required public CSV columns missing")
    if len(columns) != len(set(columns)):
        raise ValueError("duplicate columns in public CSV")

def _day(value):
    if value is None or str(value).strip() in MISSING:
        return None
    number = float(value)
    if not math.isfinite(number) or not number.is_integer() or number < 0:
        raise ValueError("invalid observed study.day.nogap")
    return int(number)

def build_day_lookup(step_rows):
    """(participant ID, decision index) -> observed study day, or None if conflicting."""
    _required(step_rows, ["user.index", "decision.index", "study.day.nogap"])
    lookup = {}
    rows_seen = missing_field = collisions = 0
    for row in step_rows:
        rows_seen += 1
        uid = row.get("user.index", "").strip()
        decision = row.get("decision.index", "").strip()
        day = _day(row.get("study.day.nogap"))
        if not uid or uid in MISSING or not decision or decision in MISSING or day is None:
            missing_field += 1
            continue
        key = (uid, decision)
        if key not in lookup:
            lookup[key] = day
        elif lookup[key] is not None and lookup[key] != day:
            lookup[key] = None
            collisions += 1
    counts = {
        "source_step_rows": rows_seen,
        "missing_keys_or_day": missing_field,
        "conflicting_observations": collisions,
        "unique_day_keys": sum(day is not None for day in lookup.values()),
        "ambiguous_keys": sum(day is None for day in lookup.values()),
    }
    return lookup, counts

def aggregate_coverage(suggestion_rows, day_lookup):
    """Count join coverage without serializing or logging personal observations."""
    _required(suggestion_rows, ["user.index", "decision.index", "avail"])
    out = Counter()
    for row in suggestion_rows:
        out["source_rows"] += 1
        uid = row.get("user.index", "").strip()
        decision = row.get("decision.index", "").strip()
        if not uid or uid in MISSING or not decision or decision in MISSING:
            out["join_absent"] += 1
            continue
        key = (uid, decision)
        if key not in day_lookup:
            out["join_absent"] += 1
        elif day_lookup[key] is None:
            out["join_ambiguous"] += 1
        else:
            day = day_lookup[key]
            out["join_unique"] += 1
            if day > 41:
                out["day_gt_41"] += 1
            else:
                out["join_unique_in_study_window"] += 1
                if str(row["avail"]).strip().lower() in {"true", "t", "1"}:
                    out["unique_available"] += 1
    return {
        field: out[field] for field in (
            "source_rows", "join_unique", "join_ambiguous", "join_absent",
            "join_unique_in_study_window", "day_gt_41", "unique_available"
        )
    }

def main():
    from heartsteps_research import download, validate_source
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="heartsteps-day-join-probe-") as td:
        root = Path(td)
        suggestions = root / "suggestions.csv"
        jawbone = root / "jbsteps.csv"
        download(BASE + "suggestions.csv", suggestions)
        download(BASE + "jbsteps.csv", jawbone)
        src1 = validate_source(suggestions, SUGGESTIONS_BYTES, SUGGESTIONS_BLOB_SHA1)
        src2 = validate_source(jawbone, JAWBONE_BYTES, JAWBONE_BLOB_SHA1)
        with jawbone.open(newline="", encoding="utf-8-sig") as fh:
            lookup, step_counts = build_day_lookup(csv.DictReader(fh))
        with suggestions.open(newline="", encoding="utf-8-sig") as fh:
            coverage = aggregate_coverage(csv.DictReader(fh), lookup)
        del lookup
        report = {
            "schema": "manager.heartsteps.pinned-day-join-diagnostic.v1",
            "source_commit": SOURCE_COMMIT,
            "verified_git_blobs": {
                "suggestions": src1["git_blob_sha1"],
                "jawbone": src2["git_blob_sha1"],
            },
            "steps": step_counts,
            "coverage": coverage,
            "original_paper_counts": {"included": 7540, "available": 6061},
            "raw_subject_rows_persisted": False,
            "causal_effect_estimated": False,
            "exact_original_analysis_replicated": False,
            "manager_field_benefit_established": False,
        }
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "day_join_aggregate.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, sort_keys=True))

if __name__ == "__main__":
    main()
