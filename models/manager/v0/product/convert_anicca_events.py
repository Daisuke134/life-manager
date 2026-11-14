"""Convert an Anicca app event export (JSONL) into ManagerBench
intervention cases (schema v1). See case-format.md for the export spec.

Join rule: outcomes attach to deliveries by delivery_id; an outcome
counts only if it arrives within the registered window
(--window-sec, default 86400 = 24 h) after the delivery. Cases without
a counting outcome are emitted with outcome_observed=false and
proximal_outcome=null — never silently dropped, never back-filled.

Usage:
    python convert_anicca_events.py --events events.jsonl \
        --out cases.json [--window-sec 86400] [--source anicca_app]
"""
import argparse
import json
from datetime import datetime, timezone


def parse_at(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--window-sec", type=int, default=86400)
    ap.add_argument("--source", default="anicca_app")
    args = ap.parse_args()

    deliveries, outcomes = [], {}
    with open(args.events) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev["type"] == "delivery":
                deliveries.append(ev)
            elif ev["type"] == "outcome":
                outcomes.setdefault(ev["delivery_id"], []).append(ev)

    cases = []
    for d in deliveries:
        treated = d.get("intervention_id") is not None
        t0 = parse_at(d["at"])
        outcome, observed = None, False
        for o in outcomes.get(d["delivery_id"], []):
            dt = (parse_at(o["at"]) - t0).total_seconds()
            if 0 <= dt <= args.window_sec:
                outcome, observed = o["proximal_outcome"], True
                break
        cases.append({
            "case_id": f"case-{d['delivery_id']}",
            "person_id": d["user_id"],
            "decision_point_at": d["at"],
            "available": bool(d.get("available", True)),
            "personal_history": d["personal_history"],
            "treatment_assigned": treated,
            "assigned_probability": d["assigned_probability"],
            "intervention_id": d.get("intervention_id"),
            "delivery_id": d["delivery_id"],
            "proximal_outcome": outcome,
            "outcome_window_sec": args.window_sec,
            "outcome_observed": observed,
            "source": args.source,
            "outcome_name": (outcomes.get(d["delivery_id"]) or [{}])[0].get(
                "outcome_name", "proximal_outcome"),
        })

    with open(args.out, "w") as f:
        json.dump(cases, f, indent=1)
    print(f"wrote {len(cases)} cases "
          f"({sum(c['outcome_observed'] for c in cases)} observed) -> {args.out}")


if __name__ == "__main__":
    main()
