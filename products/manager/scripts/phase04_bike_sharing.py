#!/usr/bin/env python3
"""CI-only provenance-pinned UCI daily aggregate study; no source rows persisted."""
import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from manager_core.phase04_bike_sharing import (
    SOURCE_URL, SOURCE_BYTES, verify_snapshot, parse_aggregate_days, build_report,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with urlopen(Request(SOURCE_URL, headers={
        "User-Agent": "Manager-Research-Aggregate-Only/1.0"
    }), timeout=30) as response:
        blob = response.read(SOURCE_BYTES + 1)
    verify_snapshot(blob)
    rows = parse_aggregate_days(blob)
    if len(rows) != 731 or sum(r["year"] == 2011 for r in rows) != 365 or sum(r["year"] == 2012 for r in rows) != 366:
        raise SystemExit("unexpected verified cohort shape; fail closed")
    report = build_report(rows, source_verified=True)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "public_bikeshare_aggregate.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "source_git_blob": report["source"]["git_blob_sha1"],
        "train_days": report["train_days"],
        "heldout_days": report["heldout_days"],
        "scenarios": [v["name"] for v in report["heldout_conditions"]],
        "baseline_metrics": report["baselines"],
        "heldout_conditions": report["heldout_conditions"],
        "bootstrap_uncertainty": report["block_bootstrap"],
        "human_personal_records": 0,
        "causal_effect_estimated": False,
        "original_socsci210_replicated": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
