# Manager product specification (independent product)

**Last reviewed:** 2026-10-20 JST  
**Mission:** End suffering.  
**Repository source scope:** `products/manager/` on GitHub branch `research/manager-product-r006-20261020` (source readback checked at 68a2214d1edc9de4cfdd24ef75b84c8d59e5db6c). This is **not Life Manager**, despite shared source hosting. No module imports, DB, credentials, runtime owner, release flow, or user profile sharing by default.

## Product direction clarification — Reuse → Connect → Evaluate (2026-10-21)

The **Internet is a real-world environment**, not a fake simulation. Primary delivery should use existing open standards and OSS to autonomously improve **mental, physical and financial** conditions through transparently accessible, Manager-controlled online public goods. No new model architecture, marketplace, token, generalized proprietary simulator, ad-hoc welfare scale or web evaluation engine should be written when reputable, licensed implementations already exist. The product has **no per-run human approval** requirement for permitted actions on self-controlled resources; it still requires lawful source rights, standing owner authority, safety boundaries and voluntary consent where appropriate. Standardized external measurement must remain separate from model predictions and transactions.

**Reuse mapping:** Existing source register [cross-field/SOURCES.json](research/crossfield-20261021/SOURCES.json) now catalogs validated WHO-5/WHODAS, OECD wellbeing, CFPB financial wellbeing, FAO food insecurity, NICE/SPIRIT/CONSORT evidence standards, Inspect AI/MentalHealthBench for response safety (NOT measured symptom relief), GrowthBook/PlanOut for internet experiments, DoWhy/EconML/OBP causal analysis, Renovatе/Dependabot/Playwright/axe-core for public internet interventions, Digital Public Goods Standard, and existing x402/ERC-4337/GoodDollar components. Read exact license terms; PROMIS and WHO questionnaire reuse must not be assumed commercial/embedding-permitted just because openly described.

**Evidence categories remain distinct:** P0 simulation/model/task score; P1 authentic execution receipt; P2 independently verified digital/world state changed; P3 authentic downstream human outcome; P4 preregistered causal net improvement incl costs/harms and sensitivity; P5 replication. A better WCAG scan or higher A/B opt-in conversion is not P3/P4 mental or financial wellbeing. One metric cannot add up all suffering. Record mental, physical and financial outcomes in their original units, distributions, missing data and any harms. **Human welfare NOT_MEASURED** unless independently observed.

**Preferred first wedge:** improve an owned public online artifact (e.g., a verified benefits-information page or accessibility improvement) with a deterministic NO_ACTION holdout and existing online experiment engine. This avoids asking charities or facility owners for permissions or introducing new private-person datasets. If a voluntary/ethical independent downstream wellbeing measure is unavailable, ship as measured *technical/public-goods* benefit only, not as reduced suffering. A page release requires valid control of that release channel, but not a human supervising each operational decision.

**Historical optional approaches:** F004/F007 legacy finance/indoor-site tasks remain blocked in the one canonical `tasks.json` until their original actual acceptance conditions are met. Their previous partner-first recommendations are optional pathways, **not the default architecture**. Any future task-scope revision requires explicit versioning of the same registry, not silently declaring completion or opening a second SSOT. Keep existing `manager_core/config.py` default prohibition on live external effects and all Life Manager production separation.

## Product thesis

A domain-general intervention system uses *lawfully public information* to identify a real-world problem, propose alternative interventions including `NO_ACTION`, predict likely consequences with uncertainty, seek independently granted execution authority, make a bounded real-world change, verify with third-party observations and estimate **causal net benefit and harms**. Digital Buddha / digital god is a long-term ethical metaphor, not a claim of omniscience or power over other people.

## Architecture (design states, not proof of deployed effects)

`Public sources -> source rights / provenance -> world state -> causal hypotheses -> action options -> optional behavioral simulation -> authority and safety -> effect executor -> independent public readback -> preregistered causal evaluation -> calibrated learning or rollback`.

- **Evidence:** No source without URL, version/hash, date and reuse/PII status; a research claim is not a measured intervention result.
- **Rights:** `docs/research-rights.md` and `docs/research/source-rights.json` are the R006 reference. `hold` means no dataset ingestion, model packaging, redistribution, public publishing or personal inference for that use.
- **Safety:** Model predictions cannot authorize money transfers, changes to a shared environment, messages, medical advice, or published content. Strict role/scope, budget, time, owner authorization, `UNKNOWN_EFFECT`, and idempotency.
- **Outcomes:** Record execution receipt P1, independent world change P2, human benefit P3, causal P4 and replication P5 separately.
- **Simulation:** Score descriptive fit, uncertainty, causal fidelity and actual impacts separately. R005 shows why visual realism is insufficient.
- **Generalization:** Identical core types and safety invariants must work across at least finance plus physical environment, with different adapters.

## First verifiable use case (still provisional)

Public ledger–based aid amplification / charitable matching, under explicit permission, risk cap, pre-registered comparator, and measurable *new outside funding net of the Manager-provided matching money* and any displacement. Do not claim suffering reduction without evidence of beneficiary welfare. If rights, operator access, or measurement are unavailable, select a shared physical-environment pilot with authorized actuation and independent indoor sensors.

## Learning and experimental progression

- **R006 completed research review:** upstream OSS and datasets rights determined or explicitly held; no automatic copying of raw participant records into GitHub.
- **R007:** citeable typed evidence registry; rights and privacy status is mandatory. Test fail-closed.
- **H001–H010:** HeartSteps offline scientific replication only after rights review; personal records do not flow into live Manager.
- **S001–S008:** actual human simulation benchmarking versus RCT causal fidelity; nonuniform rights among SocSci210 study contributors.
- **K001–K014:** independent implementation of generic observation, intervention, authority, execution and evaluation.
- **F001–F009:** external permissioned field trials and third-party readback. Never fabricate causal impact.
- **U/D/V/G/Y:** first users, multiple blessings, verification, safety and governance, YC and research/content strategy. See `docs/roadmap/tasks.json` for exact task IDs and dependency states. It is Manager-only; Life Manager's unified SSOT remains untouched.

## Distribution and future content

- Research artifacts: original source URLs/versions, short attribution-backed excerpts, source-rights register, owned analysis, original illustrations, and reproducible metrics.
- Versioned PDF research briefs produced from own notes may go to cloud Library and **public GitHub only when they contain no copied third-party full-text or raw records**.
- Articles (English-first), manga, carousels, slides, conferences and YC pitch material are downstream authored derivatives with claim-evidence links. **Runtime autonomous publishing remains disabled. The founder explicitly authorized the present English educational articles on the owned blog on 2026-10-20; use the canonical publishing bridge, review, and public URL readback. This does not authorize newsletters, third-party platforms, or other external effects.**
- Research reports are not proof of YC acceptance, external investment, decacorn valuation or beneficiary improvement.

## Review and gates

R006 tested 8 source families with `hold` for unknown downstream rights; detailed evidence at `docs/research-rights.md`. Product code currently offline-only and `money_transfer`, `private_person_data`, `physical_actuation`, `live_external_writes`, `public_posting` all disabled. Later phases must supply first-party evidence and legitimate operators.

**A different product may share a GitHub organization/repository without sharing runtime or user data.** Keep any future integration explicit, narrow and independently reviewed.

## R007 / R008 delivered (2026-10-20)

The small offline literature registry and evidence-type guards are implemented in `manager_core/evidence.py` and `manager_core/evidence_types.py`, with 8 source cards and 27 new tests (59 total). Validation is structural only, not a scientific truth or source-entailment check. RCT, survey, simulation, benchmark, review, company claim, and tool documentation remain distinct; abstract-only status is retained. Registration grants no raw-data rights or execution authority.

Expected Parrot already combines AI research and human validation; Simile validates behavior and confidence; Aaru reports survey and behavioral evaluation. Manager's proposed differentiation is an independently evaluated public-information welfare intervention loop, not exclusive ownership of human validation.

The proposed transparent impact page is not yet implemented. It must report actions, cost, externally verified changes, beneficiary outcomes, causal comparisons, harms and missingness separately. No field benefits have been demonstrated.

## Entity-first market map and L001 learning checkpoint (2026-10-20)

The ecosystem visual is an **organization-first Chaos Map**: 26 verified company, institute, lab, community or nonprofit entities in 6 overlapping activity clusters. Primary-source URLs and vendor-reporting caveats live at `docs/landscape/2026-10-20-behavior-intervention-entities.json`; companion SVG uses real organization names and no invented brand logos. This is not a competitive ranking or a claim that Manager has validated its market position. Companies such as Simile, Aaru and Expected Parrot already combine prediction and/or research with real-human validation. Penn Behavior Change for Good and GiveDirectly provide upstream lessons for actual behavioral intervention field work.

**L001 completed:** `examples/01_probability.py` (pure standard library) calculates `P(Y|X)` from a fully normalized joint distribution, with explicit rejection of malformed input and zero-mass contexts. `tests/test_probability_l001.py` includes 9 focused tests, run red then green; `docs/learning/L001_CONDITIONAL_PROBABILITY_JA.md` explains an illustrative 60%/20% daypart calculation. These probabilities are synthetic and observational; they are not actual people, causal effect estimates, or verified field outcomes. After this task the ledger has 15 done, 96 todo, 2 blocked. Next dependency-order learning task is L002 (TVD / Brier score).

The Manager runtime still has no permission to transfer money, act on private people, or operate physical systems.

## L002: predicted response distributions versus individual error (2026-10-20)

- The existing **offline** `manager_core/evaluation.py` functions `total_variation` (TVD) and `brier_score` were retained, not replaced with a new evaluation platform. Input validity was tightened to exclude non-numeric, boolean, non-finite and out-of-range probabilities; Brier's binary outcomes require integer `0` or `1`.
- `examples/02_scores.py` and `docs/learning/L002_TVD_BRIER_JA.md` teach population distribution error separately from *paired individual* forecast error. Example: TVD 0.20 for synthetic 70/30 vs 50/50 population predictions; Brier 0.01 vs 0.81 for the same predictions assigned to aligned/reversed synthetic outcomes.
- **No causal result** follows from either number. No real people were observed; no external provider was called. Treat these metrics as model diagnostics, not live policy effectiveness, operator authorization or verified suffering reduction.
- The L002 acceptance includes old tests demonstrating TVD=0 and 1 and a new 13-case test file covering published Brier arithmetic, rejection of booleans/string/NaN and wrong-length pairs, and test-first execution evidence at `docs/verification/L002.md`.
- **Next:** L003 evaluates predictive calibration with an explicit held-out set; do not infer good calibration from low Brier alone.
## Phase 02 L003–L012: completed learning code, not field validation (2026-10-20)

L001/L002 probability and TVD/Brier were already completed and preserved. L003-L012 now contain original no-dependency educational implementations plus independent tests and source-grounded Japanese learning notes. The accepted scope consists of reliability bins and study-ID holdout, JITAI design terms, a deliberately confounded synthetic example, synthetic potential outcomes, individual randomization, five daily MRT points conditional on availability, outcome windows, program displacement accounting, a toy inverse-propensity estimator with known support, and a reviewed P0–P5 evidence-presence contract.

- Reading guide: `docs/learning/PHASE02_SUMMARY_JA.md`
- Source map: `research/imozuru/phase02-fundamentals/map.md` and `report.html` (six local excerpt-line checks; no claim of scientific verification or complete source archiving).
- Phase overview: `docs/architecture/phase02-methods-ja.mmd`
- Original image renderer: `scripts/build_phase02_visuals.py` (optional Pillow dependency; no Manager runtime dependency).
- PDF and two PNG diagrams were rendered and visually checked, then stored in ChatGPT Library `/Manager/Phase02/`; regenerable visual source is in GitHub.
- TDD: missing implementations first produced RED on 29 tests. Two later documentation regressions were separately observed failing before correction. 30 focused Phase 02 tests passed in the local source snapshot; local whole-tree 84 tests passed. Hosted GitHub CI on the integrated tree is the authoritative count and must be read back before full completion claims.
- Status after verification: 26/113 task IDs done, 85 todo, 2 blocked. All 12 Phase02 L001–L012 learning tasks have passed their scoped offline acceptance tests, but no HeartSteps raw-data reproduction or real-world beneficiary effect has yet occurred.
- Next main dependency task: Phase03 H001 read-only dataset/schema/license review. In parallel S001 (SocSci210 permitted metadata only) and time-critical founder application work are available separately.

No user messaging, private individual profiling, physical actuation, autonomous donations, new external publishing, or execution authority is granted by this phase.

## Phase 03 H001: published HeartSteps metadata, no raw ingestion (2026-10-20)

The upstream `klasnja/HeartStepsV1` main tree at `3016391de426116bdef41880d72bc8cd4b9b2477` contains four released CSV files. `suggestions.csv` (author README: 8,274 decision points × 86 columns) is the initial H002 retrieval candidate. H001 records official Wiki **candidate** column names (identifier, availability, randomization, send, delivered action type, raw and zero-imputed 30-minute steps), CC BY 4.0 repository rights and independent privacy limits, immutable source/blob identifiers, and original article/analysis-code locators. It does **not** ingest participant rows, or assert that the RData source fields match the released CSV without checks.

Unresolved README/Wiki column count conflicts for users.csv, jbsteps.csv, and gfsteps.csv and RData/CSV field-name differences are explicitly recorded at `docs/research/heartsteps/H001_PUBLIC_DATA_REVIEW_JA.md` and machine-readable `H001_PUBLIC_DATA_MANIFEST.json`. H002 must perform separate read-only CSV snapshot/SHA256 and header validation before any analysis. Generated original visual source lives at `scripts/build_h001_visual.py` and accompanying `.mmd`; PNG/PDF stored in ChatGPT Library `/Manager/Phase03/`. Research only. All Manager live execution/beneficiary impact remain absent.

## Autonomous-by-default philosophy — No Human in the Routine Loop (2026-10-21)

- **Non-negotiable engineering target:** public observation → causal hypotheses → behavioral simulation when informative → multiple interventions including `NO_ACTION` → automatic policy decision → bounded external effect → independent evidence → cautious improvement, *without ad-hoc human prompts at each normal iteration*.
- **Use standing authority, not constant approval:** for a legitimate operator-controlled resource, delegated budgets, scopes, time limits, cost caps, objective and safety conditions are pre-established and validated in code. Subsequent permitted routine actions are automatic. Out-of-scope actions, harm warnings, unauthorized resources and unresolved unknown effects fail closed. The agent cannot expand its own grants.
- **Human rights exist outside the routine loop:** legitimate grant/revocation, data protection, emergency stopping, contestability and retrospective independent audits. The Manager goal is not dependent on forcing beneficiaries to install a UI or surrender private data. No stealth profiling, coercion, unconsented medical/psychological influence, or unauthorized use of another's property.
- **Relationship to Life Manager:** reuse philosophical invariants and selected design *knowledge* only. Do not share private user information, runtime process, accounts, production permissions or money ledgers. A later connection requires a separate typed and scoped contract.
- **Metrics:** report autonomy (human prompts per 1,000 routine actions; share of eligible actions completed automatically; abstention precision), rights/safety (unauthorized actions=0; unknown effects not reported as successes), and welfare (independently measured net benefit, adverse effects and causal comparisons). High autonomy without demonstrated benefit is not superintelligence.
- **H002-H004 source milestone:** fixed public HeartSteps CSV audited 8,274 rows × 86 columns with SHA-256 and excluded subject rows. Exact original H005–H010 replication remains pending because original `study.day.nogap`/inclusion rules cannot yet be matched to the released schema; see `docs/research/heartsteps/H002_H005_VALIDATION_2026-10-21.md`.

## H005 scientific blocker (2026-10-21)

Original HeartSteps analysis computes inclusion from `study.day.nogap` in an original `analysis.RData` dataset. The publicly released `suggestions.csv` has that variable discarded in Lisa Gotzian's published construction script (joined daily data reduced to `colnames(suggesttimes)`). The current independent model substituted `floor(decision.index.nogap/5)`, which yielded 7,602/6,118 or 6,997/6,118 rather than the paper's 7,540/6,061. Details and first-source line references: `docs/research/heartsteps/H002_H005_VALIDATION_2026-10-21.md`.

Exact historical causal estimation is not claimed. H005 stays blocked until an independently verified population mapping exists. No-human routine operation must fail closed on scientific unknowns instead of inventing evidence. The research project can continue independent work on general causal-evaluation tooling and held-out prediction while respecting task dependencies; a study-specific exact replication is not a necessary philosophical gate for building an autonomous public-information intervention kernel, but any revised completion gate must preserve truthful evidence labels.

## H005 independent day-join result — research status (2026-10-21)

With the pinned `jbsteps.csv`, both preceding and following decision references were checked. A numeric ID normalization repaired a false zero-match join; 7,427/8,274 decisions now have unambiguous mapped study days, 769 lack a map, and 78 have conflicting day evidence. Of 7,409 with an observed day and usable decision-index proxy, 3,345 disagree with `floor(index/5)`. The original RData-based sample cannot be reproduced by this shortcut. [Evidence log](docs/research/heartsteps/H002_H005_VALIDATION_2026-10-21.md) and [real-data workflow](https://github.com/Daisuke134/life-manager/actions/runs/39521897238). H005 remains blocked; H006–H010 are not marked done. This is a scientific data-lineage constraint, not a need for a human to review routine Manager actions.

## Founder clarified doctrine: macro, no human operational loop (2026-10-21)

See [Manager autonomy doctrine](MANAGER_NO_HUMAN_WORLD_ENGINEERING.md). The objective is **end-to-end unattended macro/world/environment engineering** using lawfully public nonpersonal signals and Manager-controlled or permissionless public actions. Routine execution must not require human approvals, human credentials, individual profiling, or third-party facility/funds access. Earlier donation/facility examples are *optional partner tracks*, not mandatory first use cases. They must not constrain Manager to a per-person wellness application or exclude animals/other welfare-bearing beings. Genuine property rights and consent still apply; when an intervention needs a third-party privileged capability, it is simply unavailable to this default action set. Transparent audit and external oversight are independent from per-action human steering. Real-world independently measurable net benefit remains the proof requirement; simulation-only results cannot satisfy it.

HeartSteps H005: The 2023 public CSV and the original private source workspace do not provide enough documented fields to assert an exact match to the original 7,540/6,061 selection. A reproducible public-source reconciliation note is at `docs/research/heartsteps/H005_PUBLIC_DATA_RECONCILIATION.md`. Mark H005 blocked and all downstream exact reproduction claims unverified unless independently demonstrated. Do not change task status to match a desired number.

## Phase 03 closes with documented H005 waiver and exploratory public reanalysis (2026-10-21)

Founder explicitly skipped H005 because publicly released HeartSteps files do not uniquely recover the original 2019 7,540/6,061 analytic set. H005 is `skipped`, never `done`. H006–H010 are complete only under revised, preserved-original-criteria **exploratory** acceptance. The pinned CSV produced 6,330 selected available decisions from 37 persons; noncausal participant-cluster adjusted ratios 1.140 [1.001,1.297] for any message and 1.239 [1.056,1.454] for walking message; decision-ordinal index/50 interaction 0.858 [0.772,0.953]. The 2019 sample, original time definition and inference procedure are not reproduced. **Gate 1 independent randomized causal replication remains UNMET.** No verified Manager human benefit exists.

The public research outputs are at `docs/research/heartsteps/PHASE03_PUBLIC_ANALYSIS_JA.md`, `docs/research/heartsteps/PHASE03_PUBLIC_METRICS.json`, `docs/verification/PHASE03_VERIFICATION.md`. Real-data CI: https://github.com/Daisuke134/life-manager/actions/runs/39526839889 . Proceed next to S001 rights-safe study-level metadata. Individual participant data are not copied to the Manager product.

## Phase 04 — evidence-linked scoped verification; independent human validation remains OPEN (2026-10-21)

**Canonical tasks:** S001 and S003 verified original study-ID source/split and hard-failed overlap injection; S006 verified *only a logical counterexample* of predictive fit and causal-error divergence; S007 verified *only a real Concordia upstream social agent sandbox* with completely fictional agents and an offline mock; S008 verified *only real observed, public aggregate* mobility demand generalization to two unseen 2012 time contexts. Thus Phase04 tasks 5 narrowly done, S002 blocked, S004/S005 todo. Overall tasks: 40 done / 69 todo / 3 blocked / 1 skipped out of 113. All scope changes preserve original task acceptance and record human_effect_verified=false. **No SocSci210 heldout respondent evaluation or validated generative human model exists.**

Source truth: official SocSci210 170 seen / 40 unseen study-only metadata, original license per source held for respondent rows. [S001 source audit](docs/research/socsci/S001_STUDY_SPLIT_AUDIT_JA.md) and [S003 overlap-injection validation](https://github.com/Daisuke134/life-manager/actions/runs/39544829400).

Independent real observed benchmark: [UCI Bike Sharing original daily aggregate](https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset), CC BY 4.0, DOI 10.24432/C5W894; original archive was byte-identical to pinned mirror (57,569 bytes, git blob d39017f2f1ad2e70a4a854d17aada04d45608575). Train 2011 365 daily aggregates; heldout 2012 366 daily aggregates. Global mean demand MAE 2,488.67 vs season-only mean 2,303.65 daily rentals; 7-day block bootstrap MAE gain 95% interval [-50.30,391.18] spans 0. Winter 2012 n=91 TVD 0.45055, summer 2012 n=94 TVD 0.13830, demonstrating within-domain temporal failure. This is **aggregate demand prediction**, not unobserved-person simulation or causal impact. [Full analysis](docs/research/public_aggregate/PHASE04_UCI_BIKESHARE_EMPIRICAL_JA.md), [actual source CI](https://github.com/Daisuke134/life-manager/actions/runs/39545601251).

Concordia official pinned Island social engine operated 2 totally fictional ESA-type agents in a deterministic mock for 4 ticks and emitted 4 engine log events; separate real_world_validation/verification.json reports n=0, no measured fidelity; JSON modality warnings retained. [Actual CI](https://github.com/Daisuke134/life-manager/actions/runs/39545009858), [technical log](docs/verification/S007_CONCORDIA_TECHNICAL_JA.md). Earlier missing bundled persona archive caused a CI failure, later corrected with a thin fictional-agent runner without copying upstream source.

Constructed causal counterexample: predictive marginal TVD=0 and stipulated treatment-effect error=0.4, method only, no empirical human causal effect. [Methodology](docs/research/socsci/PHASE04_METHODS_PARTIAL_JA.md). Source rights and independent outcomes are prerequisites before implementing actual welfare interventions.

**Latest full hosted CI:** [181/181 tests PASS; 113-task view and product boundaries PASS](https://github.com/Daisuke134/life-manager/actions/runs/39546138495). This does not pass product Gate 1: original HeartSteps exact H005 reconstruction is skipped, and independent replicated randomized real effects remain unavailable. It also does not pass real-world public-benefit gates.

See [Phase04 verification and blockers](docs/verification/PHASE04_PROGRESS_JA.md), [editable evidence flow](docs/architecture/PHASE04_EVIDENCE_FLOW_JA.mmd), and tasks.json for exact allowed scope. Manager and Life Manager remain isolated; no external money, messaging or physical effects executed.

## Phase 04 final verified readback — 2026-10-21

All **8/8 narrow atomic S001–S008 task acceptances** have now been evidenced by original source data and hosted CI. This is an **engineering/research milestone**, not completed *scientific proof* of human behavior simulation, causally valid intervention choice or real-world welfare gain. Canonical task totals: **45 done, 65 todo, 2 blocked, 1 skipped**, from 113.

The actual SocSci210 release was processed ephemerally: **210 studies / 2,901,390 rows** separated into **170 seen / 40 unseen studies, zero study-ID overlap**; 2,418,748 training responses and 482,642 heldout original responses. Study-conditioned response options have different meanings; our global numeric-code comparison is deliberately labeled **NOT the canonical Socrates benchmark**. It is legitimate technical evidence only at the restricted label-encoding level.

S004 real heldout-data Brier/TVD, one-bin calibration, 20/20 study-size subgroup errors, uncertainty and train-only error warning threshold were recorded; the online decision remains ABSTAIN because per-question response meanings and calibrated treatment effects are not available.

S005 independently executed two actual original-respondent heldout evaluations with original-source GitHub Actions: [MiniLM frozen public encoder + training-only head](https://github.com/Daisuke134/life-manager/actions/runs/39561547086) on **800 unseen individual responses**, compared on identical records to frequency and majority (24.50% vs 19.375% code accuracy); and [SmolLM2 135M](https://github.com/Daisuke134/life-manager/actions/runs/39562677909) on a *different*, but internally same-sample, **320 unseen individual responses**, yielding **42.5% parsable model outputs and 9.0625% code accuracy including invalid outputs as errors**. Model versions, Apache-2.0 license, CPU run time and unmeasured cloud costs are separate fields. Never compare these models as if they shared an 800/320 heldout sample.

S006–S008 are already verified under their narrower existing written scopes. Actual **60k historical ZOZO recommendation impressions** were evaluated with observable negative off-policy overlap diagnostics but were never Manager-run field intervention, while Concordia was executed with artificial/mock agents only.

**No Human Behavioral Fidelity Certificate; no independently reproduced source-author RCT effect; no actual Manager-induced blessing. Scientific Evidence Gate 1 remains `UNMET`**, and Phase 05 K001–K014 kernel design and safe authorized first intervention must still be implemented and externally verified.

Full report: [Phase04 210-study evidence, individual data metrics, limitations and handoff](docs/verification/PHASE04_FINAL_REAL_DATA_EVIDENCE_JA.md). This statement supersedes earlier same-day partial Phase04 snapshots and does not overwrite Life Manager's task registry.
