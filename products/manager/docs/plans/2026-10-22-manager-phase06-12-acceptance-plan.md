# Manager Phase 06–12 Remaining Acceptance Implementation Plan


> **旧研究ブランチの履歴資料 — 現行の実装順ではありません（2026-10-22）**
>
> こちらの計画は、F004/F007の廃止と実装順カーソルの統一より前の保存版です。**実行しないでください。** 現行の唯一のManagerタスク状態・順序は [SSOT](https://github.com/Daisuke134/life-manager/blob/research/manager-phase06-owned-public-good-20261022/products/manager/docs/roadmap/tasks.json) の F009実行カーソルを参照。正しい実装順は **E01→E02→E03→E04→E05→E06→E07→E08→E09→E10→E11→E12→E13→E14→E15→E16**。**F005→F006→F008→F009** は受け入れ判定。F004/F007は廃止・未実施です。
>
> [最新版E実装計画](https://github.com/Daisuke134/life-manager/blob/research/manager-phase06-owned-public-good-20261022/products/manager/docs/plans/2026-10-22-manager-core-execution-plan.md) · [最新版生成バックログ](https://github.com/Daisuke134/life-manager/blob/research/manager-phase06-owned-public-good-20261022/products/manager/docs/roadmap/ATOMIC_BACKLOG.md) · [統合PR #8526](https://github.com/Daisuke134/life-manager/pull/8526)


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development. Execute the checkbox cycle for each task below. This is a derived execution plan; `../roadmap/tasks.json` remains the status authority.

**Goal:** Resolve every original open acceptance condition without substituting preparation, simulation, generated text or a successful deployment for actual outcomes.
**Architecture:** The default product follows the public/owned digital loop in the core execution plan. Original finance, facility and human-research conditions remain explicitly gated partner tracks. Reuse existing domain/evidence/causal modules; add actual receipts and outcome data only within rights and authority.
**Tech Stack:** Existing Python contracts and SQLite, DoWhy 0.14, GrowthBook 3.2.2, current NumPy/SciPy, existing source/publication/presentation tooling. No new global workflow engine.
**Spec:** `../specs/2026-10-22-manager-validated-autonomy-design.md` and `../MANAGER_PRODUCT_SPEC.md`.

## Global Constraints

- Snapshot: 113 original tasks; 69 done, 41 todo, 2 blocked, 1 scientifically waived. Exactly 43 IDs below are unfinished. A prepared module does not satisfy dependent field acceptance.
- F004/F007 are optional third-party pathways, NOT blockers for the default authorized owned-digital engineering route. Preserve original dependency chains and explicit unmet statuses.
- P0/P1/P2/P3/P4/P5 represent simulation, execution, independent change, beneficiary outcome, causal net effect, replication. No phase is promoted from a model's self-report.
- Actual source URLs, timestamps, hashes, units, missingness, protocol versions and role-specific authority are required. No invented people, records, contacts, payments or consent.
- Use only public nonpersonal or explicitly authorized minimal data. Never copy private respondent records into the public repository. Rights and consent are separate from technical accessibility.
- Publishing articles and updating the owned homepage are now authorized; obtaining participants, sending third-party messages, spending funds or submitting applications still has its own actual authority requirements.

## Review Focus

1. Existing code mistaken for field completion (F005,U006,D011).
2. Interference/displacement and time trends mistaken for a treatment effect (F006,D002,D006).
3. Input source or pseudo-participant contaminated across conditions/splits (V002,V003).
4. Proxy success mistaken for health, money, mental wellbeing or universal welfare (D003,D008,D016).
5. Consent revocation, adverse events, billing reversal or late contradictory evidence (D015,G002,G006).

## Common execution cycle — apply separately to each ID

All paths in tables are relative to `products/manager/`.

- [ ] **1 RED:** add the named rejection test first (missing required external evidence, invalid units, unsupported proof grade or dependency not met). Use the existing test file listed, or the new explicit file where named.
- [ ] **2 Verify RED:** `python -m unittest discover -s tests -p '<test file>' -v`; record the expected missing-behavior failure, not an unrelated import failure.
- [ ] **3 Implement/reconcile:** reuse the stated module; write the task-specific manifest/report and import only genuine admissible receipts. For an external gate, write the blocker and needed evidence instead of synthesizing it. Do not run a field intervention merely to make a test pass.
- [ ] **4 Verify GREEN:** run the same test and actual evidence check. Unit tests may pass while task remains blocked/todo. Only authoritative real readback satisfies field acceptance.
- [ ] **5 Commit/update:** commit files and a receipt with the exact source revision. Update `tasks.json` only if its original acceptance and dependencies are satisfied, then run `python scripts/make_roadmap.py --check` after regenerating the view with the script's documented mode.

The worker must preserve `code_ready`, `data_ready`, `authority_ready`, `field_verified` separately. `false`, `unknown`, `not_applicable` and numeric zero are not interchangeable.

## Phase 06 — Six original open tasks

| ID / dependency | Exact next deliverable and reused files | Regression and actual completion gate |
|---|---|---|
| **F004 blocked**; F003,K007 | Create `pilot/authority/F004-authority.json` with issuer identity, allowed funding source, target, action, amount ceiling/currency, expiry and revocation. Reuse `manager_core/authority.py`, `field_readiness.py`, `scripts/check_phase06_authority.py`. | `tests/test_phase06_unblocking.py`: missing issuer/expiry/budget or fabricated approval rejects. **External:** genuine operator authorization and resources must exist; do not infer from this general task request. |
| **F005**; F004,K009 | Create `pilot/cases/F005/execution.json` and `independent-readback.json`; reuse `outbox.py`, `reconcile.py`, `verifier.py` and public finance receipt adapter. | `tests/test_phase06_f002_f003.py` plus new `tests/test_f005_live_receipt.py`: submitting is not settled execution, duplicate replay writes0, readback references exact occurrence. Actual P1/P2 required; no authority means no dispatch. |
| **F006**; F005,K011 | Create `pilot/cases/F006/analysis-plan.json`, `outcome-report.json`; reuse `causal_analysis.py`, `evaluator.py`, `preregistration.py`. Specify estimand, assignment/comparator, observation window, harms and uncertainty before outcomes. | `tests/test_causal_analysis.py`: no comparator→NOT_IDENTIFIED, inadequate sample→INCONCLUSIVE, shifted outcome definition rejects. Actual data and confidence interval/null result, never fabricated significance. |
| **F007 blocked**; F001 | Create `pilot/authority/F007-site.json`, documenting actual site owner, sensor provenance/calibration, allowed controller, temporal scope and stop/revert control; reuse `physical_outcomes.py`. | `tests/test_physical_outcomes.py`: outdoor data cannot impersonate indoor treatment/control; missing facility authority denies. **External:** real site and operator permission. |
| **F008**; F007,K010 | Create `pilot/cases/F008/measurement-manifest.json` and paired intervention/control measurements; reuse `physical_outcomes.py`, `phase06_public_indoor_readback.py`. | `tests/test_physical_outcomes.py`: timestamps, unit conversions, invalid/calibration-outside readings and incomplete energy/noise reject/mark missing. Authorized actual indoor exposure change and independent readback required. |
| **F009**; F006,F008 | Create `docs/verification/PHASE06_TWO_DOMAIN_RESULT.json`; run both real cases through existing kernel/evidence interfaces without domain-specific kernel branches. | `tests/test_phase05_kernel.py` plus new `test_f009_crossdomain_receipts.py`: both domain occurrence IDs and P2+ evidence required; two simulations or public-page changes do not satisfy original finance+physical acceptance. |

**Digital route in parallel:** core E10–E16 completes owned public change safely, with its own technical proof. Do not silently repurpose the six original F tasks or force partnerships before digital engineering.

## Phase 07 — One original open task

| ID / dependency | Exact next deliverable | Regression and actual completion gate |
|---|---|---|
| **C002**; F006 | Update `docs/articles/` and `docs/presentations/` with the eventual real-study report in English/Japanese, explicit negative/null findings and limitations. Reuse `scripts/build_blog_publication.py`. | `tests/test_blog_publication.py`: unsupported impact claim and mismatched source hash rejects. Technical API articles can publish now, but do **not** close F006-dependent real-result acceptance. Separate content products plan owns current publishing. |

## Phase 08 — Seven original open tasks

| ID / dependency | Exact next deliverable and interface | Regression and actual completion gate |
|---|---|---|
| **U002**; U001 | Create `docs/product/interviews/consent-register.json` and five minimal de-identified role-specific notes (operator, beneficiary, supporter). Record actual desired outcomes, not invented quotations. | New `tests/test_discovery_evidence.py`: duplicate person/source, missing permission and fictional note excluded from count. **External:** five genuinely consented interviews. Digital prototype work does not wait for them. |
| **U003**; U002 | Finalize existing `docs/product/FIRST_WEDGE.md`; retain a separate provisional public-digital wedge until original stakeholder condition passes. Specify beneficiary, operator, observable endpoint, action, cost ceiling, alternatives and rejection reasons. | `tests/test_phase06_f001_u001.py`: a provisional decision cannot be final without its source evidence; no source or conflicting operator authority stays proposed. |
| **U004**; U003,F002 | Finalize existing `pilot/FIRST_STUDY.md` and immutable preregistration JSON. Compute sample/power from chosen endpoint, unit and minimum meaningful effect; specify cluster/time interference, consent/withdrawal and harms. | `tests/test_phase06_welfare_bridge.py`: outcome/analysis changed after execution time rejects; unknown randomization probability blocks off-policy claims. **External:** suitable operator/research permission. No universal invented sample count. |
| **U005**; U003,K010 | Operationalize the existing read-only proof page using `digital_environment.py` and `audit.py`; add `docs/product/proof-explorer-contract.json` mapping source→proposal→occurrence→readback→outcome. | `tests/test_digital_proof_occurrence.py`: P0/P1/P2 labels cannot be elevated, no secret fields, missing links visible. Actual public GET must reproduce the evidence view and source hashes. |
| **U006**; U004,F005 | Save one authentic authorized pilot in `pilot/cases/U006/` with preconditions, release intent, receipt, comparison observation and stop outcome. Reuse digital or domain adapter, preserving original acceptance mapping. | `tests/test_phase06_welfare_bridge.py`: unknown provider state cannot be success. Actual public nonpersonal or consented independent readback required. |
| **U007**; U006,F006 | Create `pilot/cases/U007/net-benefit.json` with primary outcome, interval, cost, burden, displacement, negative effects and missing endpoints. | `tests/test_causal_analysis.py`, `test_economic_scorecard.py`: gross revenue, smiles or clicks cannot stand in for net human benefit; no independent comparison→not identified. |
| **U008**; U007,U002 | Create `docs/product/retention-evidence.json` recording actual continued use, voluntary support or settled paid commitment and operating cost. | New `tests/test_demand_evidence.py`: expressions of interest differ from payment; refunds/cancellations preserved; synthetic respondents do not count. **External:** genuine feedback/commitment, no unsolicited outreach. |

## Phase 09 — Fourteen original open tasks

| ID / dependency | Exact next deliverable and reused implementation | Regression and actual completion gate |
|---|---|---|
| **D001**; F006 | Fill `pilot/finance/funding-ledger.json` from actual source-of-funds receipts; use `program_funding.py`. | `test_program_funding.py`: founder capital/matching budget not counted as newly generated external income; currency and refund dates explicit. |
| **D002**; D001,L010 | Write `pilot/finance/displacement-design.json`; join comparable other-project totals through `spillover.py` and `program_funding.py`. | `test_program_funding.py`: own-project increase with equal losses elsewhere gives no demonstrated aggregate gain; no comparison remains UNKNOWN. |
| **D003**; D002 | Link `pilot/finance/beneficiary-outcomes.json` to independent public recipient reports and separate financial receipts. | `test_program_funding.py`: a completed transfer is P1/P2 financial state, not livelihood improvement; absent recipient outcome stays NOT_MEASURED. |
| **D004**; D003,U007 | Register and execute a second authorized regional/program case in `pilot/finance/replication/`, with prespecified comparability and changed assumptions. | New `test_domain_replication.py`: identical rerun of the same dataset is not replication; external second case and real comparison required. |
| **D005**; F008 | Populate `pilot/physical/sensor-manifest.json`; join indoor/outdoor/T/RH at defined UTC intervals using `physical_outcomes.py`. | `test_physical_outcomes.py`: wrong units, duplicate sensor times, gaps, sensor calibration out of range reject or missing; actual sensor data required. |
| **D006**; D005 | Register `pilot/physical/control-design.json` with simultaneous control zone or justified crossover and weather/occupancy covariates. | `test_physical_outcomes.py`, `test_causal_analysis.py`: before/after-only trends cannot be called treatment effects; interference/carryover documented. |
| **D007**; D006 | Populate `pilot/physical/tradeoffs.json` with independent energy, time-weighted noise, expense and exposure measurements. | `test_physical_outcomes.py`: no arithmetic mean of logarithmic sound levels; meter totals/reset and missing readings handled; real tradeoff report rather than one air-quality number. |
| **D008**; D007 | Store exposure and clinical endpoints in separate grades via `outcome_ladder.py`, `physical_outcomes.py`; update `pilot/physical/outcome-ladder.json`. | `test_physical_outcomes.py`: lower PM2.5 cannot be labeled reduced disease without direct appropriate evidence. |
| **D009**; D008,U007 | Execute an independently authorized second-site case in `pilot/physical/replication/`. | `test_domain_replication.py`: owner permissions and sensor calibration are site-specific; no blind extrapolation from first location. |
| **D011**; D010 | Populate `pilot/work/settlement-matches.json` using `opportunity_outcomes.py`; link delivered artifact, independent acceptance and settled payment. | `test_opportunity_outcomes.py`: posted bounty/quote/invoice is not payment; partial settlement, duplicates, reversals and unrelated receipts handled. |
| **D012**; D011 | Fill `pilot/work/net-income.json`; reuse `economic_scorecard.py` for settled net income, time, compute, fees, taxes-as-recorded and opportunity-cost assumptions. | `test_economic_scorecard.py`: gross advertised price not net income; unknown time/cost stays unknown; compare baseline opportunity. |
| **D014**; D013 | Finalize existing `pilot/PUBLIC_AGGREGATE_COLLABORATION_PROTOCOL.md` with a real organization's agreed public aggregate endpoints and appropriate ethics/withdrawal process. | `test_phase06_welfare_bridge.py`: private individual data refused; public aggregate availability and legitimate purpose independently evidenced. **External:** actual collaborator/review as appropriate. |
| **D015**; D014 | Finalize existing `pilot/MENTAL_OUTCOME_SAFETY_AND_STOP_RULES.md`; connect stop/revoke to `governance.py` and independent oversight. | `test_governance.py`: refusal, possible harm, uncertainty or loss of authority stops relevant exposure; model cannot override or diagnose hidden distress. |
| **D016**; D015,D012,D009 | Generate `docs/verification/CROSS_DOMAIN_OUTCOME_PORTFOLIO.json` through `outcome_bench.py`; each domain retains outcome definition, unit, proof and harms. | `test_outcome_bench.py`: money, exposure and wellbeing not blindly summed; subgroup harm visible; missing domains remain missing; original three-domain actual evidence required. |

D010/D013 already represent scoped preparation; do not rebuild them or infer their downstream data has arrived.

## Phase 10 — Six original open tasks, with explicit simulation substeps

| ID / dependency | Exact next deliverable and reused implementation | Regression and actual completion gate |
|---|---|---|
| **V001**; K014,D016 | Run current common kernel contracts against finance, physical and work/support adapters, with actual receipts linked in `docs/verification/THREE_DOMAIN_CONTRACTS.json`. | `test_phase05_kernel.py`/`test_outcome_bench.py`: no new domain branches or borrowed privileges in kernel. Offline adapters alone do not satisfy D016-dependent field gate. |
| **V002**; V001 | Extend `outcome_bench.py` to separate behavioral MAE/TVD/Brier, treatment-effect error, technical readback, burden and harms; version rubric under `evaluation/`. | `test_outcome_bench.py`: high imitation accuracy never becomes P4. Preserve raw vs sample-adjusted population errors. Add simulation steps S1–S3 below before human-like trajectory claims. |
| **V003**; V002 | Freeze geographic/income/domain/time/group splits and OOD gates; reuse `calibration.py`; save `evaluation/domain-holdout-manifest.json`. | `test_calibrated_abstention.py`: same household/person/study/scenario-family across split rejects; unsupported population/language remains unvalidated; harmful subgroup does not hide inside mean. |
| **V004**; V003 | Connect existing `learning.py` to real independent evaluation receipts: isolated→shadow→narrow canary→promote/rollback. Save versioned policy registry outside Git and public release receipts. | `test_phase05_adversarial.py` plus `test_policy_promotion_receipts.py`: scores supplied by the candidate itself cannot promote; worse or unknown performance retains baseline; authority cannot expand. |
| **V005**; V004 | Export rights-cleared reproducibility package with data/code/model/prompt hashes, environment lock, positive/negative/unknown outcomes and replication commands. | `test_evidence_registry.py`: evidence ID resolves to exact source; secret/private rows excluded; fresh third-party rebuild agrees within declared tolerance. Public source alone is not verification. |
| **V006**; V005 | Build `docs/verification/REAL_CASE_PORTFOLIO.json` with at least 24 distinct authorized actual cases as the operational interpretation of 'dozens', preserving failures, costs, subgroups and unknowns. | `test_outcome_bench.py`: repeated calls and duplicate source snapshots count once; no cumulative welfare number from incomparable proxies; denominator and selection stated. 24 is an operational inventory threshold, not statistical adequacy. |

### S1 — Reuse the existing simulation engine, not another model platform

**Files:** extend `scripts/concordia_island_mock.py` via separate `scripts/concordia_policy_trial.py`; `tests/test_simulation_provider_contract.py`; `evaluation/simulation-provider-manifest.json`.
**Consumes/produces:** `simulate(scenario: SyntheticScenario, policy, rng_seed: int) -> SimulatedTrajectory`, with actual provider/model IDs and explicit `SYNTHETIC_ONLY`.
- [ ] RED missing provider, unavailable Persimmon credentials, policy reading hidden simulator persona, and mismatched model ID reject.
- [ ] Verify RED; no current mock output may be relabeled Persimmon.
- [ ] Reuse pinned Concordia components and existing fictional scenarios. Independently verify Persimmon access/terms only if selected; no authentication cross-use or paid signup without authorization.
- [ ] GREEN fixture contract; then budgeted actual provider response if available, explicitly model-simulated, never real human.
- [ ] Commit; if external provider unavailable, keep offline baseline operational and record unavailable capability.

### S2 — Add paired interventions and negative-control drift checks

**Files:** `manager_core/simulation_checks.py`, `tests/test_simulation_drift.py`, `evaluation/paired-scenarios.json`.
**Interface:** `compare_trajectories(control, treatment, invariants: tuple[str,...]) -> DriftReport`.
- [ ] RED inject different age/history into treatment clone; detector must fail; an intended change to task completion must not be incorrectly treated as invariant drift.
- [ ] Verify RED using exactly paired source scenario hashes and common exogenous event schedule.
- [ ] Freeze persona/initial context and invariant outcomes across arms; keep reward/evaluator hidden from policy; sample distributions, not one convenient dialogue. Retain partial/unresponsive trajectories.
- [ ] GREEN named tests and a report of raw negative-control discrepancy; no automatic claim that drift correction proves field causal validity.
- [ ] Commit design and observed failures; no post-hoc replacement of the unfavorable simulator.

### S3 — Compare predicted interventions to actual external reference effects

**Files:** extend `causal_analysis.py`, `calibration.py`; add `tests/test_sim_to_real_calibration.py`; `pilot/sim-to-real-validation.json`.
**Interface:** `validate_transport(predictions, reference_studies, split_manifest) -> TransportReport`.
- [ ] RED missing reference outcome, changed population/time, unknown assignment probability, training leakage, within-team spillover and incompatible outcome units reject causal interpretation.
- [ ] Verify RED on controlled data with known effects, labeled synthetic.
- [ ] Reuse rights-cleared actual benchmark/study outputs; fit calibration only on development reference groups and evaluate untouched groups. Identify estimand before choosing regression; DoWhy cannot invent identification.
- [ ] GREEN known-truth tests; real-case report retains uncertainty and all refutations, with NO_REAL_REFERENCE when absent.
- [ ] Commit; simulation fidelity, predictive calibration and field ATE remain separate scores.

## Phase 11 — Three original open tasks

| ID / dependency | Exact next deliverable | Regression and actual completion gate |
|---|---|---|
| **Y003**; Y002 | Review existing `docs/yc/` application and founder-video assets against the actual current official application form; store submission receipt only after founder-approved real submission. | New `tests/test_outreach_receipts.py`: a draft or uploaded video is not submitted or accepted. **External:** personal application approval and deadline/eligibility verification. |
| **Y005**; Y004 | Create source-grounded questions for five relevant researchers/customers in existing outreach folder; send only via approved means and record sent/response/nonresponse accurately. | `test_outreach_receipts.py`: public address discovery is not send consent, generated reply not actual reply; preserve opt-out. No automatic cold email from publication authorization. |
| **Y008**; Y007,C002 | Publish reviewed actual-result material and preserve public URLs, time, version, corrections and feedback using existing content pipeline. | `test_blog_publication.py`: draft/PR/build not published; independently fetch actual deployed page, language/canonical/body/hash. Technical content publication is separately useful but does not close F006-dependent acceptance. |

## Phase 12 — Six original open tasks

| ID / dependency | Exact next deliverable | Regression and actual completion gate |
|---|---|---|
| **G001**; K007,V001 | Ratify existing `docs/governance/` charter with actual responsible operator and scoped authority/revocation/appeal endpoints; retain draft/adopted distinction. | `test_governance.py`: policy cannot grant itself privileges, operator kill-switch stops next dispatch, missing adoption remains DRAFT. |
| **G002**; G001 | Put external audit/incident practice into operation: incident owner, severity, immediate containment, preserved evidence, notification scope and follow-up. | `test_governance.py`: failed/negative/unknown records retained, revocation propagated, independent auditor evidence not invented. Actual reviewed drill required. |
| **G003**; G002,V006 | Register staged multi-region/population validation with comparable endpoints and local rights in `pilot/multi-region/`. | `test_domain_replication.py`: new region cannot inherit previous effects/consent/calibration; explicit OOD hold prevents unsupported rollout. |
| **G004**; G003 | Finalize `docs/governance/PUBLIC_API_CONTRACT.md` with authenticated clients, scopes, budgets, rate limits, revocation and versioned schemas; reuse core contracts. | New `tests/test_public_api_contract.py`: wrong tenant/audience, revoked grant, unknown field and over-budget requests reject; actual partner onboarding/readback still needed. |
| **G005**; G004 | Complete `docs/product/OPERATING_ECONOMICS.json`: observed hosting/model/measurement/support cost, budget owner, actual revenue/funding and beneficiary outcomes in separate ledgers. | `test_economic_scorecard.py`: missing cost !=0, capital transfer !=profit, subscription quote !=paid support; sensitivity analyses disclose assumptions. |
| **G006**; G005 | Maintain `docs/verification/FAILURES_AND_UNMEASURED.md` with unmeasured groups, negative results, inequity, model/source drift and prioritized unresolved questions. | `test_outcome_bench.py`: no finite study permits a universal 'suffering ended' claim; case totals reconcile with complete denominator. Each release preserves contradictions and corrections. |

## Status and plan audit

Open original IDs listed exactly once: F004,F005,F006,F007,F008,F009,C002,U002,U003,U004,U005,U006,U007,U008,D001,D002,D003,D004,D005,D006,D007,D008,D009,D011,D012,D014,D015,D016,V001,V002,V003,V004,V005,V006,Y003,Y005,Y008,G001,G002,G003,G004,G005,G006.

This is 43 original acceptance items plus three implementation-only simulation work packages. The core plan and content plan add execution detail without changing original registry counts. Before closing any item, verify its dependencies in `tasks.json`; preserve real blockers and the H005 waiver. External uncertainty becomes a named evidence gate, never an invented guaranteed outcome.
