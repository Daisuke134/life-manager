#!/usr/bin/env python3
"""Recompute Gate 13 completion evidence from the attribution ledger."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import experiment_attribution  # noqa: E402


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def verify_gate13(ledger_path: Path, evidence_path: Path) -> dict:
    evidence = read_json(evidence_path)
    matches = [row for row in read_jsonl(ledger_path)
               if row.get("attribution_id") == evidence.get("attribution_id")]
    experiment_attribution.require(len(matches) == 1,
                                   "exact attribution snapshot required")
    snapshot = matches[0]
    experiment_attribution.validate_snapshot(snapshot)
    results = snapshot["results"]
    statuses = Counter(row["status"] for row in results)
    classes = Counter(row["attribution_class"] for row in results)
    unknown = [row for row in results if row["attribution_class"] == "unknown"]
    fabricated_zero = [row["metric_name"] for row in results
                       if row["value"] == 0 and
                       (row["status"] != "observed" or
                        row["attribution_class"] == "unknown")]
    click = next(row for row in results if row["metric_name"] == "qualified_clicks")
    click_query = evidence.get("click_query") or {}
    click_consistent = (
        click_query.get("status") != "available"
        or (click["status"] == "observed"
            and click["attribution_class"] == "deterministic"
            and click["value"] == click_query.get("count"))
    )
    gate_pass = (len(results) == len(experiment_attribution.REQUIRED_METRICS)
                 and not fabricated_zero and click_consistent)
    return {
        "schema_version": 1, "gate": 13, "gate_pass": gate_pass,
        "attribution_id": snapshot["attribution_id"],
        "publish_key": snapshot["publish_key"],
        "experiment_id": snapshot["experiment_id"],
        "product_id": snapshot["product_id"],
        "native_post_id": snapshot["native_post_id"],
        "native_post_url": snapshot["native_post_url"],
        "observed_at": snapshot["observed_at"],
        "result_records": len(results),
        "status_counts": dict(sorted(statuses.items())),
        "attribution_class_counts": dict(sorted(classes.items())),
        "fabricated_zero_count": len(fabricated_zero),
        "click_query_status": click_query.get("status"),
        "qualified_clicks": click["value"],
        "unknown_metrics": [row["metric_name"] for row in unknown],
        "unknown_metric_reasons": {
            row["metric_name"]: row["null_reason"] for row in unknown
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_gate13(args.ledger, args.evidence)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
