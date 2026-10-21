> **Historical methods-only note (2026-10-21).** This document was written before the research-execution milestone. Since then, the complete SocSci210 dataset **2,901,390 real original human response rows / 210 studies** was analyzed with **170/40 study holdout**, and frozen public MiniLM/SmolLM2 comparisons were executed on actual individual response samples. For current quantitative measurements, scope and exact caveats see [Phase04 final evidence report](../../verification/PHASE04_FINAL_REAL_DATA_EVIDENCE_JA.md). The artificial examples below remain teaching examples and must never be presented as human causal verification. Original source-author task-conditioned evaluation and real-world Manager benefits are still UNMEASURED.

# Phase 04 — Prediction, causal fidelity, generalization (engineering work and scientific gaps)

Date: 2026-10-21 JST. **Not a completed human-behavior prediction benchmark.**

## Key distinction learned from the primary source

The original Socrates paper measures normalized ordinal accuracy and average **1D Wasserstein distance** on response distributions per study/condition/outcome; it does **not** report Manager's proposed TVD/Brier as equivalent primary metrics. In particular, Sec. 3.2 and Table 2 must not be replaced with a TVD comparison.

Source: https://arxiv.org/html/2509.05830v2 and https://aclanthology.org/2025.emnlp-main.1530/ .

A separate pure standard-library `manager_core/phase04_synthetic.py` implements binary frequency / majority baselines, strict study-group leakage rejection, aggregate TVD, binary Brier, **ordinal Wasserstein** on normalized response coordinates, scenario-specific abstention, and a causal-gap counterexample. It reuses `manager_core.evaluation` and `manager_core.calibration`; it is not another prediction service.

## Hand-constructed toy example, **not SocSci210 results**

Four synthetic TRAIN responses [1,1,0,0] produce a frequency baseline p=0.5 and tie-majority classifier 1. Two entirely new synthetic conditions hold four outcomes each: A=[1,0,0,0], B=[1,1,1,0].

| Metric | Frequency baseline | Majority baseline |
|---|---:|---:|
| P(yes), trained once | 0.5 | 1.0 |
| Held-out accuracy | 0.5 | 0.5 |
| Binary Brier | 0.25 | 0.5 |
| Overall TVD | 0.0 | 0.5 |

The frequency baseline perfectly matches the **pooled** outcome share of 0.5, but each new condition's own response rate differs by 0.25. With a **predefined** scenario max TVD=0.2 and minimum n=4, both novel conditions return `ABSTAIN`. This shows why correct overall proportions are insufficient for transfer to a new intervention context.

A second constructed thought experiment assumes balanced randomized treatment. Under do(no treatment) P(yes)=0.3, under do(treatment) P(yes)=0.7. The marginal P(yes) is 0.5. A treatment-blind p=0.5 model has **marginal TVD 0**, predicts **effect 0**, while the constructed true treatment effect is **0.4**; absolute causal effect error **0.4**. These are stipulated toy probabilities, NOT causal estimates from humans.

For ordinal score support x_1 < ... < x_K normalized into [0,1], `W1(P,Q)=sum_j |CDF_P(x_j)-CDF_Q(x_j)|*(x_{j+1}-x_j)` as a discrete 1D Wasserstein calculation. This is conceptually closer to the Socrates paper's ordinal distribution scoring than treating all categories as unordered. Neither synthetic metric proves fidelity to human behavior.

Run from Manager root:
```bash
python3 -m unittest tests/test_phase04_synthetic.py -v
python3 scripts/phase04_synthetic_bench.py --output output/phase04-toy
```

The CLI writes `prediction_and_shift.json`, `causal_fidelity_counterexample.json`, `verification_boundary.json` in different files with explicit SYNTHETIC / NOT_PERFORMED states. Synthetic unit tests are engineering checks. We must independently evaluate on rights-cleared empirical studies to call S002–S006 scientific milestones done.

## Phase04 task status truth

- **S001:** Official 170/40 study-ID split audit succeeded; see S001 report and actual Github Actions run.
- **S002–S005:** Real unseen study frequency/majority, accuracy/TVD, calibration/subgroup, trained-model comparison and inference cost are **not performed**; the original respondent corpus is rights-HOLD. Published Socrates numbers belong to its authors, not Manager.
- **S006:** Constructed descriptive/causal-gap demonstration implemented; NOT reproduced on real experiments, no empirically established causal-fidelity score. Keep original sequential task gate open.
- **S007:** Concordia engine sandbox is an independently tracked **technical probe** only; an offline deterministic mock must not be called validated social behavior.
- **S008:** Two synthetic novel conditions tested in isolation; **real population/generalization accuracy remains unmeasured**.
- **Gate 1:** HeartSteps exact trial population unreproduced; SocSci210 empirical benchmark not run; real-world Manager impact **zero measured**.

## Next technically legitimate steps

1. Confirm source-by-source research/redistribution rights for the 210 studies and choose a permission-cleared, provenance-linked subset without respondent profiling.
2. Run controlled, study-disjoint held-out predictions with appropriate baselines, both paper metric (ordinal Wasserstein) and supplemental TVD/Brier, and confidence intervals from study-level resampling.
3. Compare published open models on precisely the same permitted split and record inference cost, license chain and hardware; record inability rather than invent a number.
4. Validate treatment effect predictions against known randomized assignments and human outcome differences, not only overall response distributions.
5. Operate Concordia in a sandbox with generation and external evidence in distinct stores, then assess two genuinely novel real conditions and document failure as well as success.

No external effects, participant profiling or published model weights are authorized by this work.
