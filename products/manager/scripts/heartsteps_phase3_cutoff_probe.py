#!/usr/bin/env python3
"""Aggregate-only scan of decision-index cutoffs for HeartSteps paper mapping."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import heartsteps_phase3 as core


def scan(rows, cutoffs=range(190, 221)):
    result = {}
    for cutoff in cutoffs:
        included = available = 0
        reasons = {
            "missing_index": 0,
            "at_or_after_cutoff": 0,
            "unavailable_sent": 0,
            "missing_action": 0,
        }
        for row in rows:
            index = row.get("decision.index.nogap", "")
            if core._missing(index):
                reasons["missing_index"] += 1
                continue
            if int(float(index)) >= cutoff:
                reasons["at_or_after_cutoff"] += 1
                continue
            is_available = core._bool(row["avail"])
            sent = None if core._missing(row.get("send")) else core._bool(row["send"])
            if sent is True and not is_available:
                reasons["unavailable_sent"] += 1
                continue
            if core._missing(row.get("send.active")) or core._missing(row.get("send.sedentary")):
                reasons["missing_action"] += 1
                continue
            included += 1
            if is_available and sent is not None:
                available += 1
        result[str(cutoff)] = {
            "included": included,
            "available_with_assignment": available,
            "excluded": reasons,
        }
    matches = [
        int(key)
        for key, value in result.items()
        if value["included"] == core.PAPER["included"]
        and value["available_with_assignment"] == core.PAPER["available"]
    ]
    return {
        "scan": result,
        "exact_paper_matches": matches,
        "participant_rows_in_report": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="heartsteps-cutoff-") as tmp:
        raw = Path(tmp) / "suggestions.csv"
        core.download(core.SOURCE_URL, raw)
        report = scan(core.load_minimal(raw))
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "heartsteps_phase3_cutoff_probe.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "matches": report["exact_paper_matches"],
            "cutoff205": report["scan"]["205"],
            "cutoff210": report["scan"]["210"],
        }, sort_keys=True))


if __name__ == "__main__":
    main()
