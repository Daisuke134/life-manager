# Manager — independent intervention research prototype

**Code unit:** `manager-independent` (independent package). GitHub source is mirrored at [Daisuke134/life-manager, branch `research/manager-product-r006-20261020`](https://github.com/Daisuke134/life-manager/tree/research/manager-product-r006-20261020/products/manager) under a Manager-only directory, as explicitly authorized by the user. This does not connect Life Manager runtime to Manager.

> **Mission: End suffering.** A domain-general, evidence-grounded system for proposing, safely executing, and causally evaluating interventions based on lawful public information. “Digital Buddha” is an aspiration/metaphor—not omniscience, unrestricted permission, or an achieved system.

## Product boundary

**Manager ≠ Life Manager.** This standalone repository has no imports, credentials, runtime contracts, or shared database with Life Manager. Later integration would require a separately reviewed API contract. Previous Life Manager code is **not** imported.

**Current status:** source research and offline learning scaffold only; no live intervention; no trial replicated yet; no actual human-impact claim.

## What is intentionally forbidden in this scaffold

- All external writes, donations, public posting, physical device changes are disabled in `manager_core/config.py`. There is not yet a live executor.
- No private individual information; a publicly reachable page containing sensitive personal data is not automatically acceptable.
- No automated publishing of blog posts or articles. Research precedes future optional English-language publications.
- No claim that a simulation or an API response alone proves reduced suffering.

## Architecture and tasks

- [Manager product specification](docs/MANAGER_PRODUCT_SPEC.md)
- [GitHub research source and verification](docs/GITHUB_SOURCE.md)
- [Architecture](docs/architecture/ARCHITECTURE.md)
- [R006 source rights review](docs/research-rights.md)
- [R006 machine-readable source decisions](docs/research/source-rights.json)
- [Atomic backlog (learn + implement + verify)](docs/roadmap/ATOMIC_BACKLOG.md)
- [Structured task manifest](docs/roadmap/tasks.json)
- [imozuru source map](research/imozuru/manager-foundations/map.md)
- [imozuru verification report](research/imozuru/manager-foundations/report.html)
- [Upstream imozuru script and provenance](tools/imozuru/README.md)

## Offline checks

```bash
python3 -m manager_core
python3 -m unittest discover -s tests -v
python3 scripts/check_boundaries.py
python3 tools/imozuru/report.py research/imozuru/manager-foundations --check
```

All checks are offline, standard-library only. GitHub branch-level source mirror is reviewed separately from this standalone historical Git repository; a GitHub-hosted source tree is **not** equivalent to a tested production deployment. The research branch also adds a root `.github/workflows/manager-research-ci.yml` for offline tests; hosted check results have not yet been verified.

## Current research record

- [R004: HeartSteps methods, results and limits (Japanese)](docs/learning/R004_HEARTSTEPS_JA.md)
- [R005: Descriptive fit versus causal fidelity (Japanese)](docs/research/R005_LI_JI_JA.md)
- [R006: data/code licensing and reuse boundary (Japanese)](docs/research-rights.md)
- [R005: Effect-error data with first-source locators](docs/research/R005_CAUSAL_ERROR_EVIDENCE.json)
- [imozuru R005 evidence report](research/imozuru/causal-r005/report.html)
- [Completion and blessings roadmap](docs/roadmap/PRODUCT_COMPLETION_GATES.md)
- [Illustrative long-term vision image](docs/visuals/manager-longterm-vision-ja.png) (aspiration, not a measured result)
- [R004 source map](research/imozuru/heartsteps-r004/map.md)
- [R004 reproduction questions](research/imozuru/heartsteps-r004/OPEN_REPRODUCTION_QUESTIONS.md)
- Ordered task status remains in the existing [atomic backlog](docs/roadmap/ATOMIC_BACKLOG.md) and its [structured view](docs/roadmap/tasks.json). This page does not introduce another task sequence.

## Evidence integrity

Research under `research/imozuru` references original URLs and short excerpt-only locators. The original author-provided imozuru `report.py` is vendored exactly, checked against its Git blob SHA; it is **actually executed** for the excerpt location check. imozuru's downloader and OpenAlex chain scripts cannot connect from this environment, so primary sources and linked papers were investigated using Firecrawl and connected GitHub tools instead. Full copies of third-party papers are not redistributed.

## R007 / R008

See [Japanese implementation note](docs/R007_R008_IMPLEMENTATION_JA.md). Run `python3 -m manager_core.evidence` for the eight-card offline inventory; `python3 -m unittest discover -s tests -v` runs 59 tests. Structural validation does not prove scientific correctness or Manager impact.

## October 20, 2026: entity-first landscape and Phase 02 L001

- [26-organization market map and official primary-source URLs](docs/landscape/2026-10-20-behavior-intervention-entities.md)
- [Machine-readable map](docs/landscape/2026-10-20-behavior-intervention-entities.json)
- [Editable logo-free SVG market map](docs/landscape/2026-10-20-behavior-intervention-chaos-map.svg)
- [L001: conditional probability explanation (Japanese)](docs/learning/L001_CONDITIONAL_PROBABILITY_JA.md)
- [L001: synthetic Python probability demo](examples/01_probability.py)

L001 is an offline learning example, **not** behavioral model training, causal evaluation, or field impact. Organizational categorization is editorial and non-exhaustive.

## L002: TVD and binary Brier forecast diagnostics (2026-10-20)

- [TVD/Brier Japanese learning note](docs/learning/L002_TVD_BRIER_JA.md)
- [Offline score example](examples/02_scores.py) — `python3 -m examples.02_scores`
- [L002 test-first verification](tests/test_scores_l002.py) — 13 new tests.
- [Visual teaching diagram (editable SVG)](docs/visuals/2026-10-20-L002-TVD-Brier-JA.svg)
- [L002 verification record](docs/verification/L002.md)

TVD=0.20 and Brier=0.01/0.81 are **synthetic illustrations** and say nothing about Manager's effects on real people. PDF/PNG teaching versions are also saved in the ChatGPT Library `/Manager/Reports`.

## Phase 02 learning checkpoint (2026-10-20)

All L001–L012 learning tasks are now verified as **synthetic-only, offline learning material**. The combined diagram and summary:
- [Phase 02 Japanese guide](docs/learning/PHASE02_SUMMARY_JA.md)
- [Editable Mermaid causal learning sequence](docs/architecture/phase02-methods-ja.mmd)
- [JITAI / HeartSteps terminology](docs/learning/JITAI_GLOSSARY.md)
- [Calibration example](examples/02_calibration.py)
- [Causal graph and counterexample](docs/learning/CAUSAL_DAG.md)
- [Potential-outcome demo](examples/03_potential_outcomes.py)
- [Randomized assignment demo](examples/04_randomization.py)
- [MRT description](docs/learning/MRT.md)
- [Proximal vs distal outcome windows](docs/learning/PROXIMAL_VS_LONG_TERM.md)
- [External displacement example](examples/05_spillover.py)
- [Off-policy assumption demo](examples/06_policy_basics.py)
- [Evidence level P0–P5](docs/learning/OUTCOME_LADDER.md)
- [Learning-focused verification report](docs/verification/PHASE02_COMPLETE_JA.md)

The PDF and two original Japanese PNG illustrations are stored in ChatGPT Library `/Manager/Phase02`; `scripts/build_phase02_visuals.py` is the reproducible source. They contain no original participant records. Manager has **not** replicated a human RCT or demonstrated net welfare benefits.

## H001: HeartSteps original data structure (read-only metadata review)

- [H001 public dataset and rights review (Japanese)](docs/research/heartsteps/H001_PUBLIC_DATA_REVIEW_JA.md)
- [Pinned upstream files and minimal column candidates (JSON)](docs/research/heartsteps/H001_PUBLIC_DATA_MANIFEST.json)
- [H001 first-source investigation (imozuru)](research/imozuru/heartsteps-h001/map.md)
- [H001 editable data map](docs/visuals/2026-10-20-H001-HeartSteps-Data-Map-JA.mmd)
- [H001 original PDF/PNG rendering source](scripts/build_h001_visual.py)
- [H001 verification](docs/verification/H001.md)

H001 does not copy participant CSVs into the public repo or the Manager runtime. Historical row-level data will be considered independently under H002, with privacy and raw-redistribution restrictions.

## October 21, 2026: autonomy philosophy and first real-data audit

Routine Manager operation is designed to use no human per-action approval. Legitimate standing delegated scopes and safe policy gates remain necessary for external effects. Read [H002–H005 source audit and philosophy](docs/research/heartsteps/H002_H005_VALIDATION_2026-10-21.md). H002/H003/H004 are source-data audit checkpoints only, not an experimental treatment-effect reproduction. Raw participant rows are not part of the public repository.

## H005 dataset-lineage diagnosis (2026-10-21)

The aggregate-only [pinned public study-day join probe](scripts/heartsteps_phase3_day_join_probe.py) and its [nine focused tests](tests/test_heartsteps_day_join_probe.py) show 7,427 nonconflicting matched days from 8,274 notification decisions, 769 missing and 78 contradictory join-days. The day shortcut disagrees on 3,345 of 7,409 comparable decisions. Scientific exact-replication remains blocked. Details and [CI evidence](docs/research/heartsteps/H002_H005_VALIDATION_2026-10-21.md).

## No-human macro/environment engineering doctrine (2026-10-21)

[Founder clarified world-engineering and autonomy requirements](docs/MANAGER_NO_HUMAN_WORLD_ENGINEERING.md). Manager's recurring loop is autonomous by design and must be operable using lawfully public nonpersonal observations and Manager-controlled/permissionless actions. Partners are optional; no person-by-person micromanagement or privileged third-party infrastructure is a default requirement. Historical HeartSteps study data remain isolated learning-only.

[HeartSteps H005 reproducibility audit](docs/research/heartsteps/H005_PUBLIC_DATA_RECONCILIATION.md) explains which published study-day fields are absent or only partially reconstructible. It is a scientific blocker and not an invitation to invent missing observations.

## Phase 03 closes with documented H005 waiver and exploratory public reanalysis (2026-10-21)

Founder explicitly skipped H005 because publicly released HeartSteps files do not uniquely recover the original 2019 7,540/6,061 analytic set. H005 is `skipped`, never `done`. H006–H010 are complete only under revised, preserved-original-criteria **exploratory** acceptance. The pinned CSV produced 6,330 selected available decisions from 37 persons; noncausal participant-cluster adjusted ratios 1.140 [1.001,1.297] for any message and 1.239 [1.056,1.454] for walking message; decision-ordinal index/50 interaction 0.858 [0.772,0.953]. The 2019 sample, original time definition and inference procedure are not reproduced. **Gate 1 independent randomized causal replication remains UNMET.** No verified Manager human benefit exists.

The public research outputs are at `docs/research/heartsteps/PHASE03_PUBLIC_ANALYSIS_JA.md`, `docs/research/heartsteps/PHASE03_PUBLIC_METRICS.json`, `docs/verification/PHASE03_VERIFICATION.md`. Real-data CI: https://github.com/Daisuke134/life-manager/actions/runs/39526839889 . Proceed next to S001 rights-safe study-level metadata. Individual participant data are not copied to the Manager product.
