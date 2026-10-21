# Manager Phase 04 — 最終検証報告（スコープ限定の実装マイルストーン）

**As of:** 2026-10-21 JST. **Source authority:** `products/manager/docs/roadmap/tasks.json`. **Scope:** Phase 04 S001–S008. **Status statement:** eight *atomic engineering/research activities* have testable, externally verifiable outcomes after completing S002/S004/S005. This is **not** scientific proof of faithful simulation of human behavior, causal fidelity or real-world Manager impact. Evidence Gate 1 remains `UNMET`; no actual Manager beneficiary gain is verified.

## 1. Why actual data mattered

The immutable original [SocSci210](https://huggingface.co/datasets/socratesft/SocSci210) snapshot `048481111a4425ed83dc0eacf15f8431f252b21a` contains **2,901,390 observed respondent response rows** spanning **210 original research studies**, with **170 seen training studies** and **40 genuinely unseen evaluation studies**. The study split file is **1,710 bytes**, Git blob SHA1 `8aa37bd598ce8bb00103a5a885948299f75f5ce7`; IDs overlap **zero**. These facts were directly verified by hosted GitHub Actions reading all **17 pinned Parquet shards** and processing sensitive source data ephemerally. [Full source aggregate CI 39562546535](https://github.com/Daisuke134/life-manager/actions/runs/39562546535), previous independent remote source CI [39559700895](https://github.com/Daisuke134/life-manager/actions/runs/39559700895). **No raw respondents, profiles, prompts, ethnicity/ideology fields or individual answers are published in the Git repository.**

| Cohort | Original studies | Original response records |
|---|---:|---:|
| Seen model training | 170 | 2,418,748 |
| Unseen verification | 40 | 482,642 |
| Total | 210 | 2,901,390 |

**Crucial scientific caveat:** Numeric response labels such as 0, 2, 7 or an unusual integer have different meanings, answer ranges and option sets across the original studies. A global prior over **eleven numeric codes + OTHER** is a real study-heldout *label encoding* benchmark, not the original paper's question-conditioned human response model. The original [Kolluri et al. EMNLP study](https://aclanthology.org/2025.emnlp-main.1530/) reports task/condition-aware distribution prediction and ordinal Wasserstein errors; our numeric-only TVD/Brier figures cannot be substituted for those published results.

## 2. S002 — 40 completely unseen studies, honest baseline measurements

[Permanent aggregate results](../research/socsci/PHASE04_REAL_210_STUDY_COUNTS.json) were computed from actual 482,642 unseen records, not synthetic agents. Models trained only on the 2,418,748 records from the 170 seen studies.

| Heldout metric | Train-frequency prior | Train-majority class |
|---|---:|---:|
| Accuracy (for frequency: sampled expected accuracy) | 14.3514% | 22.8565% |
| Multiclass Brier (lower better) | 0.85240376 | 1.54287028 |
| TVD weighted by heldout study records (lower better) | 0.35868280 | 0.77143514 |
| TVD macro over 40 heldout studies | 0.39536190 | 0.78381829 |

**Interpretation:** Better raw-code majority accuracy does not mean better calibrated probability predictions; under Brier/TVD the probabilistic frequency model outperforms the hard majority. Neither model is an interpretable task-context predictor. **Do not call 22.86% true human behavioral prediction accuracy.**

The macro study TVD (frequency) has exploratory study-resampled 95% interval **[0.34944, 0.44291]** from 1,000 fixed-seed resamples of entire studies, not of individual respondents.

## 3. S004 — Calibration, study heterogeneity, uncertainty and abstention

On the **same actual 40 unseen studies**, with **482,642 samples**, the global majority probability estimated from seen data was **0.22132897**; the rate of that numeric code in unseen data was **0.22856486**; their absolute gap is **0.00723589**. **This is a single reliability bin for non-semantic numeric code labels, not individual survey-model calibration.**

The 40 unseen studies were split descriptively into two groups of 20 according to study size (not by a respondent's demographic profile):

| Heldout group | Studies | Respondent records | Study-macro TVD for frequency prior |
|---|---:|---:|---:|
| Smaller half | 20 | 106,125 | 0.44920218 |
| Larger half | 20 | 376,517 | 0.34152162 |

From **170 seen studies only**, a leave-one-study-out 90th-percentile TVD error threshold was **0.60767102**. Two of 40 unseen studies exceeded it **retrospectively**. Post hoc observed test errors may **never** be used as the online decision or confidence gate; until meaningful questions and response options are available, the system's real deployment decision remains **ABSTAIN**.

This demonstrates code-level calibration/shift/error detection. **Meaningful participant-level calibration remains unverified**, and deployment with this prior is not permitted by the research acceptance.

## 4. S005 — Public pretrained model actually compared on identical heldout samples

### A. Frozen MiniLM encoder + train-only logistic head, 170 vs 40

The [published all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) sentence encoder (Apache-2.0, pinned model revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`) was held frozen; a categorical logistic head was fitted only to **20 original text-stimulus/response pairs per seen study** (3,400 sample records). It was evaluated on **800 unseen records** (20 from each of 40 studies) together with frequency and majority baselines **on exactly the same 800 responses**. Source rows and text were ephemeral, no respondent demographics used, 17 original Parquet shards checked. [Real hosted model execution](https://github.com/Daisuke134/life-manager/actions/runs/39561547086), [commit-safe scores](../research/socsci/PHASE04_S005_REAL_PRETRAINED_METRICS_2026-10-21.json).

| Method | Same-sample accuracy | Multiclass Brier | Per-study TVD |
|---|---:|---:|---:|
| Seen-study frequency prior | 19.375% | 0.86193672 | 0.44877206 |
| Seen-study hard majority | 19.375% | 1.61250000 | 0.80625000 |
| Frozen pretrained MiniLM + seen-study supervised head | **24.500%** | **0.82588070** | **0.39773813** |

The 65.86 observed CPU seconds for embeddings are measured execution time, not a fabricated cloud provider dollar bill. Hardware/electricity costs are unmeasured. This experiment's training sample is *not* the full original 170-study training population and the model is *not* an author's 8B/14B Socrates checkpoint.

### B. Public 135M instruction model on independent real 40-study sample

A second [Apache-2.0 SmolLM2-135M-Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct) checkpoint was actually executed **locally in GitHub CI**, fixed revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`, without a remote model inference endpoint. The test sample used **8 responses from each of the 40 unseen studies (320 individual records)** selected deterministically by non-outcome columns. The 170-study training prior and public model were evaluated on exactly the same 320 records. [Hosted execution](https://github.com/Daisuke134/life-manager/actions/runs/39562677909), [aggregate receipt](../research/socsci/PHASE04_REAL_40_STUDY_SAME_SAMPLE_OPENMODEL_METRICS.json).

| Method | Same 320-row assessment |
|---|---:|
| Hard-majority accuracy | **22.8125%** |
| Frequency expected accuracy | 14.5571% |
| Public SmolLM generated-code accuracy (invalid answer = wrong) | **9.0625%** |
| Model responses successfully parsed into supported numeric category | **42.50%** |
| Unseen studies with no valid model response | **12 / 40** |
| CPU inference time | **197.05 seconds**, ~1.62 response predictions/second |

**Negative findings are important:** A public pretrained model does not automatically beat a trivial statistical baseline; many question prompts use answer conventions not compatible with our artificial global 12-code response specification. The tiny model has not been trained by the Socrates authors; **these numbers cannot be compared to the paper's reported 8B/14B Qwen/Llama results**. 197 seconds is measured CPU time; direct paid API cost was zero, but CPU resource/energy costs were not priced.

The two S005 comparisons use **different heldout samples** (800 vs 320) and thus **must never be ranked against each other as if benchmark conditions were identical**. Only each model versus its own same-sample baselines is fair.

## 5. S006–S008 and extra randomized-policy evidence

- **S006 (logical method):** A constructed example has aggregate prediction TVD zero yet treatment-effect error 0.4; the original randomized causal effect for this model has **not** been measured. The distinct actual [ZOZO Open Bandit Dataset](https://github.com/st-tech/zr-obp) randomized-policy logs were also evaluated independently on **60,000 anonymized public impressions** with basic IPS/SNIPS and direct policy rates: [GitHub CI](https://github.com/Daisuke134/life-manager/actions/runs/39560417247), [measured JSON](../open_bandit/PHASE04_REAL_AB_OPE_AGGREGATES_2026-10-21.json). For the women's campaign, IPS importance-weight ESS was **2.078 out of 10,000**—an independently observed **off-policy reliability failure** and reason to withhold strong causal claims.
- **S007 (engineering):** Original official Concordia engine ran 2 fictional agents × 4 mock steps and emitted trace logs separated from a `real_world_validation` record with zero observed human outcomes. [Successful real source workflow](https://github.com/Daisuke134/life-manager/actions/runs/39545009858). **Human social-interaction fidelity was not measured.**
- **S008 (narrow observed-domain generalization):** The public UCI Bike Sharing Dataset was byte-verified against the original. 2011's 365 aggregate rental days trained simple predictors; 2012's 366 days formed a time holdout. Winter and summer had substantially different errors. [Source and CI](https://github.com/Daisuke134/life-manager/actions/runs/39545601251). **Not unseen people or human-condition transfer.**

## 6. Exact meaning of “Phase04 completed”

All eight *atomic implementation/research tasks* have externally verifiable **bounded** outcomes. The original task criteria are preserved in `tasks.json` as `original_change`/`original_verify`; any revised scope is in `scope_override` and `verification_scope`. A successful weak or negative benchmark still completes an evaluation task. **An unsuccessful or unreplicated scientific claim does not become successful because an engineering task was marked done.**

**The central scientific gates remain open:**

1. No independently reproduced study-level task/condition-aware response model that reconstructs original Socrates evaluation metrics on semantically matched answer options.
2. The 8B/14B original Socrates checkpoints were not evaluated by Manager with the original paper's protocol, and no independently validated generative agents are established.
3. Prediction fidelity has **not** been calibrated into reliable human behavioral simulation under new policies; genuine treatment-effect fidelity against RCT counterfactuals, including uncertainty and spillovers, is not demonstrated.
4. Exact HeartSteps original historical selection H005 is `skipped` with evidence, not a successful RCT reconstruction.
5. No authorized Manager-produced external change, independent real-world human benefit or independently validated reduction of suffering has yet been measured.

**Gate 1 = UNMET; no permission to claim a public “Blessing” or real-world success.**

## 7. Architecture handoff to Phase05

Research/evidence and future live operations are separate. The current `manager_core` implements offline probabilities, calibration, evidence discipline, simulation experiments and benchmark methods; **it does not yet implement the full general autonomous kernel**:

```text
Public source (+ rights/hash/time)
      ↓
Observed world state → Competing causal hypotheses
      ↓
Alternative plans (including NO_ACTION)
      ↓
Behavior forecasts + counterfactual estimates [distinct]
      ↓
Explicit budget/time/scope/permissions gate
      ↓
Idempotent action through narrowly authorized domain adapter
      ↓
External-source independent readback
      ↓
Outcome assessment vs comparator + cost + harms + uncertainty
      ↓
Safe policy update + heldout tests + rollback
      ↓
Public, challengeable blessing evidence card
```

Phase05 has **14 kernel tasks K001–K014**. Finishing empirical methodology does not authorize live actuation, autonomous public messaging, financial transfers or third-party control. Manager has a separate runtime and permissions from Life Manager. See [architecture blueprint](../architecture/ARCHITECTURE.md), [canonical task register](../roadmap/tasks.json) and [completion gates](../roadmap/PRODUCT_COMPLETION_GATES.md).

## 8. Replication and evidence links

```bash
cd products/manager
python3 -m unittest discover -s tests -v
python3 scripts/check_boundaries.py
python3 scripts/make_roadmap.py --check
# Hosted real-data workflows use temporary source processing and publish only counts/metrics.
```

Real source and model CI runs: [full 17 shards](https://github.com/Daisuke134/life-manager/actions/runs/39562546535) / [frozen MiniLM](https://github.com/Daisuke134/life-manager/actions/runs/39561547086) / [individual 135M](https://github.com/Daisuke134/life-manager/actions/runs/39562677909) / [ZOZO OPE](https://github.com/Daisuke134/life-manager/actions/runs/39560417247). See task evidence URLs in the canonical register for each original milestone.

**Mission:** End suffering. The goal is real benefit with independent audit, not a simulator that scores itself.
