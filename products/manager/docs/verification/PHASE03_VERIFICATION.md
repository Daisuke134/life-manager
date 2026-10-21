# Phase 03 verification — explicit scientific waiver

Date: 2026-10-21. Independent Manager product. Scope: HeartSteps V1 public observational sub-analysis, **not** independent reproduction of original randomized causal effect.

## Tests
- TDD: new H006-H010 exploratory unit tests observed failing before implementation, then 10 passing locally. Expanded CI run includes 159 passing tests, source boundary and backlog checker (with previous 113 tasks) passed: https://github.com/Daisuke134/life-manager/actions/runs/39526839908 .
- Actual source end-to-end: hash-pinned 8,274-row CSV, selected 6,330 eligible/known-action records from 37 people; 37 participant clusters. The real-data alternative analysis ran successfully in https://github.com/Daisuke134/life-manager/actions/runs/39526839889 .
- The original 2019 analysis-set implementation previously failed with 6,997/6,118 instead of 7,540/6,061; this discrepancy is preserved. Waived H005 is **skipped**, never "done".
- Descriptive counts, adjusted ASSOCIATIONS, cluster-adjusted intervals and ordinal-index trend reported. Neither a completed causal reproduction, an intervention by Manager, nor positive beneficiary impact is claimed.
- Original source article: https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/ ; public data: https://github.com/klasnja/HeartStepsV1 .

## Scope transition authorized by founder

The founder explicitly requested skipping H005 and proceeding through Phase 03 without wasting effort on currently non-identifiable author analysis data. This is a **scoped waiver**, not scientific resolution. All H006-H010 original acceptance wording is retained in `original_verify`; the revised acceptance verifies the reproducible **alternative exploratory analysis** only. The Gate 1 requirement for independently reproduced experimental effects remains **unmet** and must use another reproducible, permissioned original RCT before Gate 1 can pass.

## Privacy, reproducibility and claims

- Raw source downloaded only to isolated, short-lived GitHub Actions run storage and verified via pinned SHA. Never included in Git, publication bundles, library, or reports.
- The source study contains human research participants and cannot become Manager's production population simulator without independent privacy and rights review.
- CLI produces JSON and Markdown with aggregate totals; no individual subjects, locations or timestamps.
- Existing independent WLS estimator used; normal CIs are approximations, not the original authors' small-sample procedure.

## Scientific humility

A numerically close effect ratio does not establish the same causal estimand: research calendar day is absent, the selected subset differs by 269 available decisions, and cohort construction differs. `decision.index.nogap` is an ordinal position, **not** verified study day. All columns with `original_2019` in the report are references, not reproduced estimates.

## Next scientific step

Proceed to S001 only for rights-safe SocSci210 metadata and train/test study split audit. Do not ingest sensitive study participant records until original study licenses/ethical conditions are checked. An alternate published RCT with fully reproducible eligibility, assignment and outcomes should be selected before asserting Gate 1 independent RCT effect replication.