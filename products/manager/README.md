# Manager — independent intervention research prototype

**Code unit:** `manager-independent` (independent package). GitHub source is to be mirrored in `Daisuke134/life-manager` under a Manager-only directory and research branch, as explicitly authorized by the user. This does not connect Life Manager runtime to Manager.

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

All checks are offline, standard-library only. GitHub branch-level source mirror is reviewed separately from this standalone historical Git repository; a GitHub-hosted source tree is **not** equivalent to a tested production deployment. CI scaffold is included but may not run as a nested workflow.

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
