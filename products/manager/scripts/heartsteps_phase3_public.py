#!/usr/bin/env python3
"""Public-CSV adapter for the HeartSteps phase-3 aggregate reproduction.

The released CSV contains rows where ``send`` is missing. They are excluded as
unknown assignments, never imputed to ``False``. All output remains aggregate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import heartsteps_phase3 as core


def select_public_analysis_rows(rows):
    selected, available = [], []
    audit = {
        "input_rows": 0,
        "missing_nogap_index": 0,
        "beyond_day_41": 0,
        "missing_send": 0,
        "unavailable_but_sent_anomaly": 0,
        "missing_action": 0,
        "included": 0,
        "available": 0,
    }
    for raw in rows:
        audit["input_rows"] += 1
        index = raw.get("decision.index.nogap")
        if core._missing(index):
            audit["missing_nogap_index"] += 1
            continue
        day = core.study_day_from_decision_index(index)
        if day > 41:
            audit["beyond_day_41"] += 1
            continue
        is_available = core._bool(raw["avail"])
        if core._missing(raw.get("send")):
            audit["missing_send"] += 1
            continue
        sent = core._bool(raw["send"])
        if not is_available and sent:
            audit["unavailable_but_sent_anomaly"] += 1
            continue
        if core._missing(raw.get("send.active")) or core._missing(raw.get("send.sedentary")):
            audit["missing_action"] += 1
            continue
        row = {
            "user": str(raw["user.index"]),
            "study_day": day,
            "avail": is_available,
            "send": sent,
            "send_active": core._bool(raw["send.active"]),
            "send_sedentary": core._bool(raw["send.sedentary"]),
            "outcome": core._float(raw["jbsteps30.zero"]),
            "pre": core._float(raw["jbsteps30pre.zero"]),
            "raw_outcome_missing": core._missing(raw.get("jbsteps30")),
        }
        selected.append(row)
        if is_available:
            available.append(row)
    audit["included"] = len(selected)
    audit["available"] = len(available)
    return selected, available, audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="heartsteps-phase3-") as tmp:
        raw = Path(tmp) / "suggestions.csv"
        core.download(core.SOURCE_URL, raw)
        rows = core.load_minimal(raw)
        selected, available, audit = select_public_analysis_rows(rows)
        if audit["included"] != core.PAPER["included"] or audit["available"] != core.PAPER["available"]:
            raise SystemExit(f"analysis-set mismatch {audit}")
        report = core.build_phase3_report(selected, available, audit)
        report["method"]["public_csv_missing_send"] = (
            "Rows with missing send were excluded as unknown assignment, not imputed as no action."
        )
        core.write_report(report, args.output)
        print(json.dumps({
            "included": audit["included"],
            "available": audit["available"],
            "missing_send": audit["missing_send"],
            "participants": report["descriptive"]["participants"],
            "any_ratio": report["models"]["any_average"]["ratio"],
            "walking_ratio": report["models"]["walking_average"]["ratio"],
            "raw_persisted": False,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
