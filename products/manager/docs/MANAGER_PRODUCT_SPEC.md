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
