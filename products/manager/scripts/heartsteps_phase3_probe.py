#!/usr/bin/env python3
"""Aggregate diagnostics for mapping released HeartSteps CSV to paper analysis data."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import heartsteps_phase3 as core


def _day(index, offset):
    return math.floor((float(index) - offset) / 5)


def aggregate(rows):
    result = {
        "rows": len(rows),
        "decision_nogap": {"missing": 0, "min": None, "max": None, "unique": 0},
        "missing_send": {
            "total": 0,
            "available_true": 0,
            "available_false": 0,
            "by_nogap_missing": 0,
            "by_day_gt_41_offset0": 0,
            "by_day_gt_41_offset1": 0,
        },
        "selection_variants": {},
        "index_frequency_tail": {},
    }
    values = []
    frequency = Counter()
    for row in rows:
        index = row.get("decision.index.nogap", "")
        if core._missing(index):
            result["decision_nogap"]["missing"] += 1
        else:
            value = int(float(index))
            values.append(value)
            frequency[value] += 1
        if core._missing(row.get("send")):
            result["missing_send"]["total"] += 1
            if core._bool(row["avail"]):
                result["missing_send"]["available_true"] += 1
            else:
                result["missing_send"]["available_false"] += 1
            if core._missing(index):
                result["missing_send"]["by_nogap_missing"] += 1
            else:
                if _day(index, 0) > 41:
                    result["missing_send"]["by_day_gt_41_offset0"] += 1
                if _day(index, 1) > 41:
                    result["missing_send"]["by_day_gt_41_offset1"] += 1
    if values:
        result["decision_nogap"].update(
            min=min(values), max=max(values), unique=len(set(values))
        )
        result["index_frequency_tail"] = {
            str(key): frequency[key] for key in sorted(frequency)[-20:]
        }
    for offset in (0, 1):
        for keep_missing_send in (True, False):
            key = f"offset{offset}_keep_missing_send_{str(keep_missing_send).lower()}"
            selected = available = 0
            reasons = Counter()
            for row in rows:
                index = row.get("decision.index.nogap", "")
                if core._missing(index):
                    reasons["missing_index"] += 1
                    continue
                if _day(index, offset) > 41:
                    reasons["day_gt_41"] += 1
                    continue
                is_available = core._bool(row["avail"])
                if core._missing(row.get("send")):
                    if not keep_missing_send:
                        reasons["missing_send"] += 1
                        continue
                    sent = None
                else:
                    sent = core._bool(row["send"])
                if sent is True and not is_available:
                    reasons["unavailable_sent"] += 1
                    continue
                if core._missing(row.get("send.active")) or core._missing(row.get("send.sedentary")):
                    reasons["missing_action"] += 1
                    continue
                selected += 1
                if is_available and sent is not None:
                    available += 1
            result["selection_variants"][key] = {
                "included": selected,
                "available_with_assignment": available,
                "excluded": dict(sorted(reasons.items())),
            }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="heartsteps-probe-") as tmp:
        raw = Path(tmp) / "suggestions.csv"
        core.download(core.SOURCE_URL, raw)
        rows = core.load_minimal(raw)
        report = aggregate(rows)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "heartsteps_phase3_probe.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
