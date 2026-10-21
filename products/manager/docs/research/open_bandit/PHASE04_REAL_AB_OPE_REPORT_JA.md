# Phase 04 — ZOZO実データのA/B試験と反実仮想政策評価（2026-10-21）

**Source:** [Open Bandit Dataset and Pipeline](https://arxiv.org/abs/2008.07146) by Saito, Aihara, Matsutani & Narita; immutable [code and small sample](https://github.com/st-tech/zr-obp/tree/8cbd5fa4558b7ad2ba4781546d6604e4cc3e07c4/obd). Actual hosted [live-data GitHub Actions](https://github.com/Daisuke134/life-manager/actions/runs/39560417247) **SUCCESS** (3 focused mathematical tests + all six source cohorts hash-verified, 60,000 events); actual measured aggregate output [JSON](PHASE04_REAL_AB_OPE_AGGREGATES_2026-10-21.json).

## 実測値（架空データではない）

| Campaign | Random n / clicks / CTR | BTS n / clicks / CTR | Difference BTS - random (absolute percentage points) | Naive 95% CI of difference (pp) | Estimated random CTR from BTS via IPS / SNIPS | IPS importance ESS |
|---|---|---|---:|---|---|---:|
| all | 10000 / 38 / 0.380% | 10000 / 42 / 0.420% | 0.040 pp | [-0.135, 0.215] | 0.236% / 0.233% | 340.38 |
| men | 10000 / 46 / 0.460% | 10000 / 69 / 0.690% | 0.230 pp | [0.020, 0.440] | 0.301% / 0.319% | 655.71 |
| women | 10000 / 46 / 0.460% | 10000 / 46 / 0.460% | 0.000 pp | [-0.188, 0.188] | 0.744% / 0.237% | 2.08 |

## What this establishes — and what it does not

1. The input includes **real observed clicks** from ZOZOTOWN's published random-policy versus learned-policy experiment, NOT fabricated agents. Dataset repository includes a limited **first 10,000 records per policy/campaign**, not a population-representative random sample. The authors describe a randomized A/B design, but this specific small excerpt and independence conditions have **not** been independently established as a representative randomized subsample.
2. Two simple off-policy estimators were computed for a **uniform random recommendation policy** using actual logging propensities under BTS: **IPS** = mean(click × target_probability / logging_probability), and **SNIPS** = weighted clicks / sum(weights). No clipping was hidden. The direct random-cohort click-rate is a noisy reference, not necessarily the same target population.
3. In women, BTS importance-weight **ESS=2.078** from 10,000 events. One extremely rare logged action makes the IPS estimate unstable: **this is a concrete reason to abstain from a definitive counterfactual recommendation**. With current sample sizes, conventional standard errors also assume independent events, which might fail for repeated users.
4. Men's BTS-minus-random direct difference is 0.23 percentage points; naive CI does not include zero. But the selection of the first 10,000 records, repeat exposure and action propensities mean this is **NOT a certified population causal effect or Manager improvement**.
5. Do not confuse a historical field experiment conducted by ZOZO with an intervention executed by Manager. Manager only **analyzed** the published sample. External real-world benefits attributable to Manager remain **NOT_MEASURED**.

## Transfer to research architecture

Predictive assessment, counterfactual policy evaluation and human welfare measurement are separate gates. In this dataset, all six source files are pinned to original Git blobs, and evaluation computes reward estimates with uncertainty and overlap diagnostics. Manager's causal fidelity benchmark must further compare model-predicted treatment contrast against an independently measured ground truth on comparable populations; this A/B excerpt itself does not supply that full benchmark.

**Data minimization:** The script reads only click, item and propensity fields into memory after source hash checks. No individual profiles, demographics, usernames, prompts, raw CSVs or respondent rows are written into the report or Git repository.

**Replication:** `cd products/manager && python scripts/phase04_obd_empirical.py --output output/obd-real/aggregates.json` — external network required. CI workflow: `.github/workflows/manager-obd-real-ope.yml`. Original GitHub dataset repository's Apache-2.0 code license must not be assumed to authorize redistribution of respondent-level data across unrelated commercial contexts; only research aggregates are published here.
