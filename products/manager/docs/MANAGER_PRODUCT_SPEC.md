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
- Articles (English-first), manga, carousels, slides, conferences and YC pitch material are downstream authored derivatives with claim-evidence links. **No autonomous publishing while a release gate is disabled.**
- Research reports are not proof of YC acceptance, external investment, decacorn valuation or beneficiary improvement.

## Review and gates

R006 tested 8 source families with `hold` for unknown downstream rights; detailed evidence at `docs/research-rights.md`. Product code currently offline-only and `money_transfer`, `private_person_data`, `physical_actuation`, `live_external_writes`, `public_posting` all disabled. Later phases must supply first-party evidence and legitimate operators.

**A different product may share a GitHub organization/repository without sharing runtime or user data.** Keep any future integration explicit, narrow and independently reviewed.
