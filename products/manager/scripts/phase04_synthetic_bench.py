#!/usr/bin/env python3
"""Emit three distinctly labeled synthetic reports; no SocSci210 respondent load."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.phase04_synthetic import synthetic_phase04_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = synthetic_phase04_report()
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, data in (
        ("prediction_and_shift.json", result["study_evaluation"]),
        ("causal_fidelity_counterexample.json", result["causal_counterexample"]),
        ("verification_boundary.json", {
            "source": result["source"],
            "real_soc_sci_benchmark": result["real_soc_sci_benchmark"],
            "published_socrates_comparison": result["published_socrates_comparison"],
            "concordia_run": result["concordia_run"],
            "real_beneficiaries": result["real_beneficiaries"],
            "scientific_task_completion": result["scientific_task_completion"]
        }),
    ):
        (args.output / filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({
        "basis": result["source"],
        "test_studies": result["study_evaluation"]["heldout_study_count"],
        "novel_scenarios": len(result["study_evaluation"]["novel_scenarios"]),
        "abstained_scenarios": sum(
            s["decision"] == "ABSTAIN" for s in result["study_evaluation"]["novel_scenarios"]
        ),
        "causal_effect_error_in_constructed_world":
            result["causal_counterexample"]["effect_error"],
        "real_soc_sci_benchmark": result["real_soc_sci_benchmark"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
