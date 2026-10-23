#!/usr/bin/env python3
"""Run the fixed study-holdout diagnostic on the hash-pinned private snapshot."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import inspect_external_behavior_benchmark as inspector  # noqa: E402
from manager_core.external_behavior_eval import evaluate_released_effects, make_fixed_study_split  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("ERROR SNAPSHOT_INVALID", file=sys.stderr)
        return 2
    try:
        rows, legacy_report = inspector.load_validated_snapshot(
            Path(arguments[0]), inspector._load_repository_nature()
        )
        groups = {row["study"]: row["group"] for row in rows}
        split, digest = make_fixed_study_split(groups)
        result = evaluate_released_effects(
            rows, study_split=split, bootstrap_seed=20261022, n_resamples=2000
        )
        result["protocol"]["split_algorithm"] = "sha256_stratified_study_id_v1"
        result["protocol"]["split_seed"] = 20261022
        result["protocol"]["split_digest_sha256"] = digest
        result["protocol"]["split_counts"] = {
            label: sum(value == label for value in split.values()) for label in ("train", "test")
        }
        result["source"] = {
            "doi": legacy_report["source"]["doi"],
            "version": legacy_report["source"]["version"],
            "verified_files": [
                {"name": item["name"], "sha256": item["sha256"]}
                for item in legacy_report["source"]["files"]
            ],
        }
        rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    except Exception:
        print("ERROR SNAPSHOT_INVALID", file=sys.stderr)
        return 2
    sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
