# Manager product specification (independent product)

**Last reviewed:** 2026-10-20 JST  
**Mission:** End suffering.  
**Repository source scope:** `products/manager/` on GitHub branch `research/manager-product-r006-20261020` (source readback checked at 68a2214d1edc9de4cfdd24ef75b84c8d59e5db6c). This is **not Life Manager**, despite shared source hosting. No module imports, DB, credentials, runtime owner, release flow, or user profile sharing by default.

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
