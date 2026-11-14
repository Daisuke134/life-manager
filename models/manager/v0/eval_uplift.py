"""Manager v0 eval harness: MG-06 uplift protocol on the frozen Hillstrom split.

Scores one LLM arm (base or post-trained) against the population prior,
random targeting and a T-learner (logistic regression) on the SAME eval
rows, with normalized Qini (sklift), AUUC, uplift@30% and a 500-resample
bootstrap 95% CI. The gate (MG-06 prereg section 4): the model's lower CI
must exceed the random-targeting p95.

Eval protocol (declared before scoring; identical for every arm):
- Frozen split: two-arm Hillstrom, train_test_split(test_size=0.3,
  random_state=0, stratify=treatment x visit) -> train 29,885 / test 12,808.
- Eval rows: fixed 1,000-row subsample of the frozen test split
  (stratified by treatment x visit, groupby sample random_state=0),
  sorted by source row index.
- Random arm: 200 draws from numpy default_rng(0); bootstrap resamples
  continue the same rng stream (500 per arm, arms in the order
  prior -> T-learner -> LLM; the prior is not bootstrapped).
- LLM score: P(visit | x, treated) - P(visit | x, control), where each
  probability is the model's next-token distribution at the digit
  position of the canonical prompt (serialize.py), normalized over
  {token '0', token '1'}.

Reconstruction note (2026-11-14): the first version of this harness was
lost with a workspace cleanup before publication. This version was
rebuilt from the surviving result file and data, and is verified to
reproduce every classical-arm number of the original base-model run
exactly (prior, random mean/p95, T-learner Qini / AUUC / uplift@30 / CI).

Usage:
    python eval_uplift.py --source hillstrom.csv.gz --model <path-or-hf-id> \
        --label manager-v0 --out eval_manager-v0.json
"""
import argparse
import json
import time

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklift.metrics import qini_auc_score, uplift_at_k, uplift_auc_score
from transformers import AutoModelForCausalLM, AutoTokenizer

import serialize

SEED = 0
FEATURES = ["recency", "history", "mens", "womens", "zip_code", "newbie",
            "channel"]


def load_split(source):
    df = pd.read_csv(source)
    df = df[df.segment.isin(["Womens E-Mail", "No E-Mail"])].reset_index(drop=True)
    t = (df.segment == "Womens E-Mail").astype(int).values
    y = df.visit.values.astype(float)
    X = pd.get_dummies(df[FEATURES], columns=["zip_code", "channel"],
                       dtype=float).values
    strat = t * 2 + y
    idx = np.arange(len(df))
    itr, ite, ytr, yte, ttr, tte, Xtr, Xte = train_test_split(
        idx, y, t, X, test_size=0.3, random_state=SEED, stratify=strat)
    return df, itr, ite, ytr, yte, ttr, tte, Xtr, Xte


def eval_subsample(df, ite, yte, tte, n):
    dte = pd.DataFrame({"pos": np.arange(len(ite)),
                        "strat": (tte * 2 + yte).astype(int)})
    sub = dte.groupby("strat", group_keys=False).apply(
        lambda g: g.sample(frac=n / len(ite), random_state=SEED))
    pos = sub["pos"].values
    pos = pos[np.argsort(ite[pos])]  # sort by source row index
    return pos


def arm_metrics(y, t, s, rng, bootstrap=True):
    out = {
        "qini": float(qini_auc_score(y, s, t)),
        "auuc": float(uplift_auc_score(y, s, t)),
        "uplift_at_30pct": float(uplift_at_k(y, s, t, strategy="overall", k=0.3)),
    }
    if bootstrap:
        qs = []
        for _ in range(500):
            ii = rng.integers(0, len(y), len(y))
            qs.append(float(qini_auc_score(y[ii], s[ii], t[ii])))
        lo, hi = np.percentile(qs, [2.5, 97.5])
        out["qini_boot95"] = [float(lo), float(hi)]
    return out


@torch.no_grad()
def llm_scores(model_id, df, ite, pos):
    tok = AutoTokenizer.from_pretrained(model_id)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    id1 = tok("1", add_special_tokens=False)["input_ids"]
    id0 = tok("0", add_special_tokens=False)["input_ids"]
    assert len(id1) == 1 and len(id0) == 1, (id1, id0)
    id1, id0 = id1[0], id0[0]
    model = AutoModelForCausalLM.from_pretrained(model_id)
    model.eval()

    prompts, meta = [], []
    for p in pos:
        row = df.loc[ite[p]]
        for treated in (1, 0):
            prompts.append(serialize.render_eval_prompt(row, treated))
            meta.append((p, treated))
    p1 = {}
    bs = 64
    t0 = time.time()
    for i in range(0, len(prompts), bs):
        batch = prompts[i:i + bs]
        enc = tok(batch, return_tensors="pt", padding=True)
        logits = model(**enc).logits
        lens = enc["attention_mask"].sum(1) - 1
        last = logits[np.arange(len(batch)), lens]
        pair = torch.stack([last[:, id0], last[:, id1]], dim=1)
        prob1 = torch.softmax(pair.float(), dim=1)[:, 1].numpy()
        for (p, treated), v in zip(meta[i:i + bs], prob1):
            p1[(p, treated)] = float(v)
        if (i // bs) % 10 == 0:
            print(f"  scored {i + len(batch)}/{len(prompts)} prompts", flush=True)
    sec = time.time() - t0
    s = np.array([p1[(p, 1)] - p1[(p, 0)] for p in pos])
    return s, sec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--eval-n", type=int, default=1000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    df, itr, ite, ytr, yte, ttr, tte, Xtr, Xte = load_split(args.source)
    pos = eval_subsample(df, ite, yte, tte, args.eval_n)
    ye, te_, Xe = yte[pos], tte[pos], Xte[pos]
    ate = float(ye[te_ == 1].mean() - ye[te_ == 0].mean())

    rng = np.random.default_rng(SEED)
    rand_qs = [float(qini_auc_score(ye, rng.random(len(ye)), te_))
               for _ in range(200)]
    rand_mean = float(np.mean(rand_qs))
    rand_p95 = float(np.percentile(rand_qs, 95))

    arms = {}
    arms["population_prior"] = arm_metrics(
        ye, te_, np.zeros(len(ye)), rng, bootstrap=False)

    m1 = LogisticRegression(max_iter=2000).fit(Xtr[ttr == 1], ytr[ttr == 1])
    m0 = LogisticRegression(max_iter=2000).fit(Xtr[ttr == 0], ytr[ttr == 0])
    s_t = m1.predict_proba(Xe)[:, 1] - m0.predict_proba(Xe)[:, 1]
    arms["t_learner_logreg"] = arm_metrics(ye, te_, s_t, rng, bootstrap=True)

    s_llm, sec = llm_scores(args.model, df, ite, pos)
    arms[args.label] = arm_metrics(ye, te_, s_llm, rng, bootstrap=True)

    lower = arms[args.label]["qini_boot95"][0]
    res = {
        "label": args.label,
        "model": args.model,
        "protocol": "MG-06 prereg (anicca-ops files/mg06-prereg-2026-11-14.md); frozen split seed 0",
        "n_train_full": int(len(itr)),
        "n_test_full": int(len(ite)),
        "n_eval": int(len(pos)),
        "eval_subsample": "seed 0, stratified by treatment x visit, declared before scoring (CPU compute)",
        "ate_eval": ate,
        "random_qini_mean": rand_mean,
        "random_qini_p95": rand_p95,
        "llm_scoring_sec": sec,
        "arms": arms,
        "gate_vs_random": {
            "rule": "MG-06 training gate: uplift ranking beats random targeting (lower 95% CI > random p95)",
            "lower_ci": lower,
            "random_p95": rand_p95,
            "pass": bool(lower > rand_p95),
        },
    }
    with open(args.out, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
