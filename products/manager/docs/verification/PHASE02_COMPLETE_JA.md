# Manager Phase02 L001–L012 — 実装検証記録

Date: 2026-10-20 JST. Branch: `research/manager-product-r006-20261020` of `Daisuke134/life-manager`, directory `products/manager/`. Manager is **not** Life Manager and imports no Life Manager runtime.

## Scope
- L001/L002: completed in earlier turns, left untouched by L003–L012 work other than future task status descriptions.
- L003/L004: calibration on synthetic holdout and the six core JITAI components.
- L005–L007: confounding counterexample, synthetic oracle potential outcomes, randomized trial simulation.
- L008/L009: repeated decision points conditioned on availability; proximal vs distal outcome window contract.
- L010/L011: financial interference/displacement arithmetic; tiny IPS off-policy toy requiring logged propensities and support.
- L012: P0–P5 proof level *presence checks*, not an automatic causal validity certification.
- Models, papers and original research are first-source linked. No personal records, clinical outcomes, donation, physical changes, account access, real-world intervention or article publication in this work.

## Verification
- Test-first RED: initial 29 tests failed because the listed modules/documents were missing. Two more targeted tests were written and observed failing before amending the causal DAG and documented module execution command.
- GREEN: 30 tests in `tests/test_phase02_l003_l012.py` passed.
- Local full tree: 84 tests passed on the local, earlier independent source snapshot. The canonical GitHub branch contains additional R007/R008 tests not present in this older local snapshot; use GitHub-hosted CI for the actual final full-suite claim.
- `python3 scripts/check_boundaries.py`: PASS, no banned Life Manager imports.
- `python3 scripts/make_roadmap.py --check`: PASS 113-task view.
- `python3 tools/imozuru/report.py research/imozuru/phase02-fundamentals --check`: 6 short excerpt line checks passed, NOT scientific proof of the claims or comprehensive paper downloading.
- `python3 -m examples.02_calibration` etc.: local example smoke tested.
- PDF exported from original PIL diagrams and visually checked after rendering both pages.

## Honest results
- All example numbers are **SYNTHETIC** and must not be reported as prediction accuracy on humans, randomized field results, improvement in suffering, or general intelligence.
- A test that validates a boolean evidence flag cannot ensure the evidence is real; independent scientific review is still required.
- No new training on human participant data or reproduction of HeartSteps published estimates occurred.
- Next is Phase03 H001: review HeartSteps actual public data schema and permitted use, before raw data ingestion; H002 requires a lawful read-only way to fetch bytes.

## CI readback

Pending GitHub push/hosted tests when this file was created. Current CI status must be verified separately before claiming Phase02 completion across the full GitHub repository.
