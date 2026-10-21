# Phase 04 final evidence update — 2026-10-21 (authoritative snapshot)

**Current:** Eight of eight research/engineering task IDs S001–S008 are done **within recorded bounded verification scopes**; individual-response research with the actual 210 studies/2,901,390 response rows succeeded and two independent same-sample publicly pretrained model comparisons were executed. **The original Socrates task-specific/condition-specific 8B/14B human-behavior accuracy was not replicated; causal effect fidelity and real-world Manager benefits remain unmeasured.** Source-of-truth JSON: `docs/roadmap/tasks.json`. Full external readbacks and limitations: [Final scientific report](PHASE04_FINAL_REAL_DATA_EVIDENCE_JA.md). 

**Canonical total:** 45 done, 65 todo, 2 blocked, 1 skipped of 113. The source metadata 170/40 study split has zero overlap. Original response labels are not semantically harmonized between the different studies; answering numerically with a global 12-class output should not be described as meaningful population behavioral simulation. S002/S004/S005 original acceptance text and revised verified scope coexist in the canonical registry.

**Independent successful CI:** [210-study real data / 2.9M survey responses](https://github.com/Daisuke134/life-manager/actions/runs/39562546535), [MiniLM same-sample 800 individual heldout responses](https://github.com/Daisuke134/life-manager/actions/runs/39561547086), [SmolLM2 same-sample 320 individual heldout responses](https://github.com/Daisuke134/life-manager/actions/runs/39562677909), [full task-status and 208-test run](https://github.com/Daisuke134/life-manager/actions/runs/39564516003). Raw responses and participant profiles were not committed. **Product Gate 1 remains UNMET.**

---
**Historical progress snapshot below, before completion of S002/S004/S005. It is preserved for provenance and is superseded by the new final report.**

# Manager Phase 04 — Verified progress and scientifically open acceptance gates

**Audit date:** 2026-10-21 JST. **Status: partial.** This document records finished implementation and actual GitHub CI readbacks, not a claim that S001–S008 or empirical causal fidelity are fully completed.

## Summary / canonical task truth

- **S001 DONE:** official SocSci210 study-ID split metadata pinned, downloaded and verified, with 170 seen and 40 unseen studies, 0 overlap, without respondent records.
- **S002 BLOCKED:** original survey participant-response rows carry per-original-study rights / research consent uncertainty and source-rights registry has `local_research: hold`. Cannot produce empirical held-out SocSci210 accuracy/TVD while they are inaccessible under approved handling.
- **S003 DONE:** real source study-ID mapping 170/40 and deliberate leakage-injection rejection. Human-response rows are still untouched.
- **S004/S005 TODO:** rights-cleared real study subgroups/calibration, pretrained same-split comparison and cost measurement remain missing.
- **S006 DONE only as analytic falsification:** constructed marginal TVD=0 and stipulated intervention-effect error=0.4; NOT a real human causal estimate.
- **S007 DONE only as Concordia technology integration:** actual pinned upstream artificial agents, simulation logs and a separate zero-human-evidence receipt. Human fidelity remains unvalidated.
- **S008 DONE only for observed public aggregate time transfer:** year-2012 winter and summer have measured test errors; NOT unseen SocSci210 human populations.
- **Canonical status: 40 done, 69 todo, 3 blocked, 1 skipped overall. Phase04 is 5 scoped done / 2 todo / 1 blocked. Evidence Gate 1 still UNMET.**
- H005 from Phase03 remains `skipped` (with evidence), so the overall evidence Gate 1 for independent human RCT effect reproduction remains unmet. No measured Manager-induced human welfare impact exists.

Canonical: `docs/roadmap/tasks.json` only; generated `docs/roadmap/ATOMIC_BACKLOG.md` is synchronized. Neither Life Manager progress SSOT nor production systems were modified.

## S001 — Real pinned metadata audit

Official source `socratesft/SocSci210@048481111a4425ed83dc0eacf15f8431f252b21a`, `metadata/participant_mapping.json`. Despite the filename, the file contains *study IDs* in `seen` / `unseen` arrays. Immutable blob SHA-1 `8aa37bd598ce8bb00103a5a885948299f75f5ce7`, **1,710 bytes**, **170 seen + 40 unseen**, **0 ID overlap**. The 210-study mapping is a necessary split-provenance check, NOT evidence of model predictive accuracy.

- Implemented: `scripts/socsci_split_audit.py`, a byte-limited HTTPS read of the immutable revision, Git blob hash validation, size/schema/count/disjoint checks, and aggregate-only output (no study/participant identifiers serialized).
- Synthetic unit contract: `tests/test_socsci_split_audit.py`: 5/5 pass, including duplicate/overlap/malformed/changed-hash failures.
- Real external verification: [GitHub Actions run 39536829220](https://github.com/Daisuke134/life-manager/actions/runs/39536829220) SUCCESS; aggregate artifact `socsci-s001-study-split-aggregate`. No respondent CSV/Parquet or participant records were downloaded.
- Longer source and rights evidence: `docs/research/socsci/S001_STUDY_SPLIT_AUDIT_JA.md`, `docs/research/source-rights.json`.
- Upstream: https://huggingface.co/datasets/socratesft/SocSci210 and https://aclanthology.org/2025.emnlp-main.1530/ .

## S002/S004/S005 scientific gates remain open; S006 logical falsifier is verified but not real human causality

- `manager_core/phase04_synthetic.py`: `binary_baselines`, `compare_on_unseen_studies`, `wasserstein_ordinal`, `constructed_causal_gap`, `synthetic_phase04_report`.
- `tests/test_phase04_synthetic.py`: six deterministic contract tests, including cross-study leakage rejection, ordinal distribution support, binary Brier/TVD, and absence of respondent fields.
- `scripts/phase04_synthetic_bench.py`: separate aggregate outputs for a **synthetic** prediction/shift test, a constructed causal-gap counterexample, and an explicit real-validation absence record.
- Hosted offline CI [run 39537750991](https://github.com/Daisuke134/life-manager/actions/runs/39537750991) **SUCCESS: 170/170 unit tests, bounded Manager imports, backlog checker PASS (113 tasks), synthetic CLI and aggregate evidence boundaries passed**.
- Two synthetic novel conditions with 4 observations each, training baseline p=0.5: frequency model pooled **accuracy 0.50, Brier 0.25, TVD 0**; tie-break majority model pooled **accuracy 0.50, Brier 0.50, TVD 0.50**. Per-condition TVD=0.25 leads to **2/2 ABSTAIN** under toy threshold 0.20.
- Constructed causal *counterexample*, NOT learned empirical causal effect: P(Y=1|do(0))=.3, P(Y=1|do(1))=.7 and balanced randomization. Treatment-blind p=.5 gives pooled TVD0 but effect prediction 0 vs construction truth .4; **error .4**. Shows descriptive match is insufficient for causal decisions.
- Important metric distinction: Original Socrates article evaluates accuracy and normalized ordinal **Wasserstein** errors, whereas Manager TVD/Brier are supplemental. Neither substitutes for a real held-out human study or actual randomized intervention effect evaluation.
- Source-boundary in scripts: no personal records or real-effect executor; all results are labeled `SYNTHETIC_ONLY`, `NOT_PERFORMED` where appropriate.
- Scientific report and exact toy equations: `docs/research/socsci/PHASE04_METHODS_PARTIAL_JA.md`.

**Blocker**: Per-study licensed/consented participant outcomes and a documented permitted evaluation pathway are missing; no full 40-study held-out dataset was processed. The public model's original performance and inference costs are not Manager-measured. S002 remains blocked; S004 and S005 remain todo. S006 and S008 now have narrow nonhuman methodological / observed-aggregate successes only.

## S007 — Actual upstream Concordia engine executed, but human validity unmeasured

- Upstream `google-deepmind/concordia@7128586aa8c1073bfa09dcb3781cea21e1a49229` (Apache-2.0, package v2.4.0); Python 3.12, separate ephemeral upstream source checkout, no reused Life Manager infrastructure, no API key/model requests.
- Actual upstream executable: `python -m examples.deep_time.run --scenario=daisyworld --mode=mock --ticks=6 --seed=0 --out_dir=...`; **6 mock simulation ticks**, real upstream simulation files `simulation/log.html`, `simulation/summary.json`, `simulation/topics.mmd`.
- Workflow `.github/workflows/manager-concordia-sandbox.yml` creates **separate** `simulation/` and `real_world_validation/verification.json`; real-world records **0**, external effects **DISABLED**, human fidelity **NOT_MEASURED**. Artifact records are retained by GitHub Actions for 14 days; workflow code is version-controlled permanently.
- First independent execution [run 39537295867](https://github.com/Daisuke134/life-manager/actions/runs/39537295867) **FAILED** with upstream example's missing PyYAML import. Root-cause log `ModuleNotFoundError: No module named 'yaml'`. Added bounded pinned dependency `PyYAML==6.0.2` (no unrelated app changes).
- Follow-up [run 39537485934](https://github.com/Daisuke134/life-manager/actions/runs/39537485934) **SUCCESS**, including readback of actual generated artifacts and independent validation-absence record. [Concrete sandbox artifact](https://github.com/Daisuke134/life-manager/actions/runs/39537485934/artifacts/12317987966).
- **Limit**: `daisyworld` is a planetary toy scenario, not independently validated human social behavior. Six mock ticks demonstrate software integration only. S007's narrow sandbox execution and evidence-separation task is now marked done with the former criterion retained. Human behavioral fidelity, actual learned memory/reflection quality and independent field validation remain open.

## Scientific validation still unfinished, including after scoped task completions

| Task | Scientific completion still missing |
|---|---|
| S002 | Rights-cleared real 40-study held-out response benchmarks, frequency/majority accuracy and TVD |
| S003 | Study-ID metadata overlap is verified ZERO on real 170/40 source and injection test rejects leakage (DONE); real respondent-outcome handling not tested (S002). |
| S004 | Real unknown-study TVD/Brier/subgroup calibration, denominators, abstention failure analysis |
| S005 | Public pretrained models under same splits, license and inference cost comparison |
| S006 | Artificial counterexample is verified (DONE technical method); real treatment-assignment ground truth, effect size and causal-error comparisons remain unmeasured. |
| S007 | Concordia real upstream engine and separate evidence logs are verified (DONE narrow integration); human-behavior accuracy absent, mock-format warnings documented. |
| S008 | Two observed out-of-year aggregate bike-demand conditions evaluated (DONE temporal scope); new human populations or city/domain transfer unmeasured. |

Permitted next work: review primary-source rights per study, use only a documented permission-cleared experiment or **public aggregate outcome tables where suitable and authorized**, add independent paper-metric scoring, compare and report real results. Do not ask for or process the private participant records to shortcut a publication. An alternate fully reproducible public RCT can meet the separate HeartSteps/H005 unmet original-effect replication gate. External interventions and beneficiary claims remain strictly separate.

## New actual-source research: public mobility and social-agent sandbox (2026-10-21)

Complete source-linked study: [UCI temporal out-of-sample mobility report](../research/public_aggregate/PHASE04_UCI_BIKESHARE_EMPIRICAL_JA.md); [editable evidence flow diagram](../architecture/PHASE04_EVIDENCE_FLOW_JA.mmd).

- **Public dataset rights:** CC BY 4.0 UCI Bike Sharing, DOI 10.24432/C5W894. Official archive day.csv and independent pinned GitHub mirror were byte-for-byte identical: 57,569 bytes, Git blob SHA1 d39017f2f1ad2e70a4a854d17aada04d45608575. [Real hosted CI run 39545601251](https://github.com/Daisuke134/life-manager/actions/runs/39545601251) SUCCESS.
- **Real temporal holdout:** 2011 365 training days, 2012 366 heldout days, with no future labels leaked. Pooled mean baseline MAE 2,488.67 rentals/day; season mean MAE 2,303.65. Gain 185.02 rentals/day, seven-day block bootstrap 95% [-50.30,391.18] spanning zero. These are observational forecasting errors and NOT a causal effect.
- **Two distinct 2012 environments:** winter 91 days (TVD 0.45055, Brier 0.45055), summer 94 days (TVD 0.13830, Brier 0.01913). Accuracy alone obscures this large shift. These are new calendar-year contexts, NOT unseen human populations or studies.
- **Concordia Island real engine:** pinned upstream official Concordia at 7128586aa8c1073bfa09dcb3781cea21e1a49229 executed 2 fictional ESA agents / 4 mock ticks / 4 emitted engine events in [successful hosted workflow 39545009858](https://github.com/Daisuke134/life-manager/actions/runs/39545009858). Actual simulation HTML and summary stored apart from real_world_validation report recording n=0. A prior attempt failed because the upstream claimed bundled Brecksville persona files were absent. Later run passed. JSON modality parsing warnings remain, and human memory/reflection fidelity is NOT verified. Full technical receipt: [S007](S007_CONCORDIA_TECHNICAL_JA.md).
- **Independent counterexample:** an explicitly artificial world satisfies marginal prediction TVD=0 but stipulated causal effect error=0.4, proving that descriptive fit cannot itself certify intervention choices. Not an empirical RCT or evidence of reduced suffering.
- **Latest integrated hosted checks:** [GitHub Actions run 39546138495](https://github.com/Daisuke134/life-manager/actions/runs/39546138495) 181/181 Python tests PASS, task view 113 tasks PASS, source import boundary PASS, simulated/real evidence separation PASS.
- **Science is still open:** SocSci210 respondent data are HOLD; the actual 40-unseen-study benchmark, same-study model inference-cost comparison, human treatment-fidelity check and true Manager independent welfare improvement have not been performed. Completed task IDs S006/S007/S008 have original descriptions preserved as original_change/original_verify and explicit scope_override, evidence run and human_effect_verified=false in the canonical task registry.

## Runtime verification scope

Everything listed above was verified through actual authenticated GitHub tool reads and hosted GitHub Actions logs, not a local canonical Mac checkout. This session had **no access to the user's `/Users/anicca/Projects/life-manager-main` checkout**, so the local `scripts/verify-source-boundary.sh` script itself was **not run**. GitHub Actions tested `products/manager/scripts/check_boundaries.py` and explicitly checked that no prohibited Life Manager module imports were present. Never conflate the latter with the unavailable Mac checkout boundary verification.

**Mission:** End suffering, with real-world causal benefit ultimately independently demonstrated. This report makes no claim of new beneficiaries, a validated behavior simulator or Phase04 complete.
