# H005 audit — what the public HeartSteps release does and does not establish

Date: 2026-10-21. Scope: published research replication, not Manager live action.

## Source provenance

- Primary 2019 HeartSteps paper: https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ ; Results, Included Decision Points / Available Decision Points.
- Published data repository pinned to `klasnja/HeartStepsV1@3016391de426116bdef41880d72bc8cd4b9b2477` (CC BY 4.0, with separate participant privacy obligations).
- Source `data_files/suggestions.csv`: git blob SHA-1 `67a55efd4d79e1f5646bdb26277f37ec988e2403` (8,274 rows, 86 columns; separately confirmed via GitHub Actions). SHA256 verified in the pinned CI source report: `60ee7896183d7084a084f9a6e8ef2d0afea2e7fecdb41d6b15382ce1745c5ddb`.
- Original author R analysis: https://github.com/StatisticalReinforcementLearningLab/HeartstepsV1Code . Published older derivative build description: https://github.com/LisaGotzian/HeartSteps/blob/master/build_heartsteps_data.R . The latter explicitly states it used `analysis.RData` and `csv.RData` from a nonpublic shared mailbox, so no access or replication of the original workspace is asserted.

## Verified contrasts

- Paper: 8,274 initial decisions - 390 corruption/travel/tech - 340 after day 42 - 4 anomalous = 7,540 included; 6,061 available for treatment.
- Naive `floor(decision.index.nogap / 5)` method currently selects 6,997 included and 6,118 available; the originally proposed day proxy is unsupported for causal reproduction.
- Earlier aggregate-only join to published Jawbone's `study.day.nogap` via participant and decision IDs yielded 7,233 unique mapped decisions. Combining past and following decision mappings yielded **7,427 unique**, **78 conflicting**, **769 absent** from the 8,274 decisions. Only **7,100** uniquely mapped decisions fall within day<=41, with **5,723** available under this partial coverage. This is evidence of *incomplete mapping*, not the paper's analysis selection.
- Among mapped decisions with nonmissing index, the simple `decision.index.nogap/5` proxy disagreed with observed step-day evidence **3,345 times** (of 7,409 comparable mapped decisions), indicating it is not a valid replacement for `study.day.nogap`.
- A later Google Fit join attempt failed explicitly because a required `study.day.nogap` field was absent from the released Google Fit CSV, despite upstream derivative-builder references to fields present in older sources. Code now treats absent columns as a named diagnostic rather than inventing study days.

## Rules for reproduction

1. Preserve anonymized data locally/in CI temporary storage only. Do not publish participant rows, dates, contexts or profiles; do not cross-reidentify individuals.
2. Public RCT data can be used for methodological understanding, but Manager's live product remains solely based on lawfully public nonpersonal observations.
3. Do not choose exclusion cutoffs or imputation rules merely to force the published 7,540/6,061 results.
4. Keep **H005 blocked** until every inclusion/exclusion decision can be sourced and independently reproduced from accessible material (or the exact, correctly permissioned original analysis source is available). H006–H010 remain undone while their prerequisite is not met.
5. A subsequent analysis of a well-defined *publicly reconstructed subset* may be valuable, but it must be labeled exploratory and nonidentical—not an exact replication of 2019 estimates.
6. Do not mark a model successful merely because synthetic-fixture unit tests pass. Hosted real-source CI failures are meaningful scientific feedback.

## Use an alternative route if this source remains nonreproducible

Do not require private participant profiles or operator credentials to unlock an educational study. Select a different public experiment with published assignment, outcome, eligibility and analysis dataset; create a separately tracked comparable replication task. Preserve the HeartSteps H005 limitation as an honest documented outcome. Select an independent benchmark by its rights and reproducibility, not by a desired success number.

## Status

The H005 public-data task is presently **blocked, not complete**. The end-to-end societal intervention loop, all real-world blessings, and any reduction in suffering have **not yet been demonstrated** by Manager.
## Fresh public-source CI readback (2026-10-21)

- Manager offline CI: [run 39523967370](https://github.com/Daisuke134/life-manager/actions/runs/39523967370), 149 unit tests pass, Manager-only import boundary and 113-task view checks pass.
- Pinned empirical pipeline: [run 39523967390](https://github.com/Daisuke134/life-manager/actions/runs/39523967390). Input/source audit and aggregate cross-device day-join steps complete; **original-paper replication gate remains FAILED as designed** (`analysis-set mismatch`).
- Public Jawbone plus following-decision mapping: 7,427 unique decision-level observed days, 78 conflicting, 769 without mapping. The 2023 public Google Fit export lacks both `study.day.nogap` and `study.day.nogap.following.dec`; verified source bytes are pinned to Google Fit blob `3fbe7a1e4555282414e579f2ba4f3380856a2b3c`. These missing columns are now explicit aggregate diagnostics; no inferred participant study days are inserted.
- Naive index/5 days generate 6,997 included / 6,118 available; paper reports 7,540 / 6,061. A 149-test passing harness cannot override the failed scientific comparison.
- Next acceptable action: locate **genuinely public, permission-cleared** source records that document the original day and anomaly exclusion rules, or independently replicate a different fully public RCT under a separate named task. Do not ask Manager to collect nonpublic personal records or privileged human credentials to unlock this analysis.
