"""Build Manager v0 datasets from the Hillstrom two-arm data.

Outputs (in --out dir):
- cases_train.jsonl / cases_test.jsonl: the full frozen split in the
  ManagerBench intervention-case schema v1 (situation -> stimulus ->
  measured response), in split order.
- sft_train.jsonl: 2,000 train cases as prompt/completion pairs
  (DataFrame.sample(n=2000, random_state=0) over the train split),
  serialized with serialize.py.
- manifest.json: provenance (source sha256, split definition, sizes).

Verified: running this on the pinned source file reproduces the shipped
sft_train.jsonl exactly (all 2,000 prompt/completion pairs) and the case
files row-for-row.

Usage:
    python build_dataset.py --source hillstrom.csv.gz --out data/
"""
import argparse
import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

import serialize

SEED = 0
DECISION_AT = "2008-01-01T00:00:00Z"
WINDOW_SEC = 1209600  # two weeks


def to_case(i, row, treated, visit):
    return {
        "case_id": f"hillstrom-{i}",
        "person_id": f"hillstrom-{i}",
        "decision_point_at": DECISION_AT,
        "available": True,
        "personal_history": {
            "recency": int(row["recency"]),
            "history": float(row["history"]),
            "mens": int(row["mens"]),
            "womens": int(row["womens"]),
            "zip_code": row["zip_code"],
            "newbie": int(row["newbie"]),
            "channel": row["channel"],
        },
        "treatment_assigned": bool(treated),
        "assigned_probability": 0.5,
        "intervention_id": "womens_email" if treated else None,
        "delivery_id": f"hillstrom-{i}-send" if treated else None,
        "proximal_outcome": int(visit),
        "outcome_window_sec": WINDOW_SEC,
        "outcome_observed": True,
        "source": "hillstrom_minethatdata",
        "outcome_name": "visit",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sft-n", type=int, default=2000)
    args = ap.parse_args()

    import os
    os.makedirs(args.out, exist_ok=True)
    sha = hashlib.sha256(open(args.source, "rb").read()).hexdigest()

    df = pd.read_csv(args.source)
    df = df[df.segment.isin(["Womens E-Mail", "No E-Mail"])].reset_index(drop=True)
    t = (df.segment == "Womens E-Mail").astype(int).values
    y = df.visit.values
    strat = t * 2 + y
    idx = np.arange(len(df))
    itr, ite = train_test_split(idx, test_size=0.3, random_state=SEED,
                                stratify=strat)[:2]

    for name, split_idx in (("train", itr), ("test", ite)):
        with open(os.path.join(args.out, f"cases_{name}.jsonl"), "w") as f:
            for i in split_idx:
                f.write(json.dumps(to_case(i, df.loc[i], t[i], y[i])) + "\n")

    train_frame = df.loc[itr]
    sample = train_frame.sample(n=args.sft_n, random_state=SEED)
    n_treated = 0
    visits = 0
    with open(os.path.join(args.out, "sft_train.jsonl"), "w") as f:
        for i, row in sample.iterrows():
            treated = bool(t[i])
            n_treated += treated
            visits += int(y[i])
            f.write(json.dumps({
                "prompt": serialize.render_prompt(
                    row["recency"], row["history"], row["mens"], row["womens"],
                    row["zip_code"], row["newbie"], row["channel"], treated),
                "completion": serialize.render_completion(y[i]),
            }) + "\n")

    # The file v0 actually trained on: a uniform 1,000-row subsample
    # (seed 0) of the prepared SFT file. v0 trains on a subset because
    # the run executes on shared CPU (see MODEL_CARD.md, "Compute").
    sub = sample.sample(n=min(1000, args.sft_n), random_state=SEED)
    with open(os.path.join(args.out, "sft_train_v0.jsonl"), "w") as f:
        for i, row in sub.iterrows():
            f.write(json.dumps({
                "prompt": serialize.render_prompt(
                    row["recency"], row["history"], row["mens"], row["womens"],
                    row["zip_code"], row["newbie"], row["channel"], bool(t[i])),
                "completion": serialize.render_completion(y[i]),
            }) + "\n")

    manifest = {
        "source_file": os.path.abspath(args.source),
        "source_sha256": sha,
        "source": "Hillstrom MineThatData e-mail challenge (2008), public S3 mirror used by MG-06 prereg",
        "rows_two_arm": int(len(df)),
        "n_train": int(len(itr)),
        "n_test": int(len(ite)),
        "split": "70/30 stratified by treatment x visit, random_state=0 (frozen, MG-06 prereg section 3)",
        "sft_n": int(args.sft_n),
        "sft_v0_n": 1000,
        "sft_v0_note": "sft_train_v0.jsonl = uniform subsample (seed 0) of the SFT file; the file Manager v0 trained on (CPU wall-clock, see MODEL_CARD.md)",
        "sft_treated_share": n_treated / args.sft_n,
        "sft_visit_rate": visits / args.sft_n,
        "features": ["recency", "history", "mens", "womens", "zip_code",
                     "newbie", "channel"],
        "outcome": "visit",
        "license_note": "Hillstrom challenge data is distributed for research/analysis use by MineThatData; this repo redistributes only serialized derivatives needed to reproduce the run, with attribution. See DATA_CARD.md.",
    }
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
