"""Standalone validator for ManagerBench intervention cases (schema v1).

Mirrors the semantics of the canonical checker (anicca-ops
files/eval/managerbench/check_intervention_cases.py) plus the schema's
treated-arm requirements, with no dependencies. Input: a JSON file
holding a list of cases (or {"cases": [...]}).

Usage:
    python validate_cases.py cases.json [more.json ...]
Exit code 0 and "PASS ... invalid=0" when every case is valid.
"""
import json
import sys

REQUIRED = {
    "case_id", "person_id", "decision_point_at", "available",
    "personal_history", "treatment_assigned", "assigned_probability",
    "proximal_outcome", "outcome_window_sec",
}


def validate(case):
    missing = sorted(REQUIRED - case.keys())
    if missing:
        return f"missing required fields: {', '.join(missing)}"
    p = case.get("assigned_probability")
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not 0 < p < 1:
        return "assigned_probability must be a number strictly between 0 and 1"
    if not isinstance(case["personal_history"], dict) or not case["personal_history"]:
        return "personal_history must be a non-empty object"
    if not isinstance(case["outcome_window_sec"], int) or case["outcome_window_sec"] < 1:
        return "outcome_window_sec must be a positive integer"
    if case["treatment_assigned"]:
        if not case.get("intervention_id"):
            return "treated case requires intervention_id"
        if not case.get("delivery_id"):
            return "treated case requires delivery_id"
    return None


def main(paths):
    count, errors = 0, []
    for path in paths:
        payload = json.load(open(path))
        cases = payload if isinstance(payload, list) else payload.get("cases", [])
        for i, case in enumerate(cases):
            count += 1
            err = validate(case)
            if err:
                errors.append(f"{path}:{i}: {err}")
    if errors:
        print("INVALID")
        print("\n".join(errors))
        return 1
    print(f"PASS: intervention cases={count}; invalid=0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
