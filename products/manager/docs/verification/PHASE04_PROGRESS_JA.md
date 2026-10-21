# Manager Phase 04 — Verified progress and scientifically open acceptance gates

**Audit date:** 2026-10-21 JST. **Status: partial.** This document records finished implementation and actual GitHub CI readbacks, not a claim that S001–S008 or empirical causal fidelity are fully completed.

## Summary / canonical task truth

- **S001 DONE:** official SocSci210 study-ID split metadata pinned, downloaded and verified, with 170 seen and 40 unseen studies, 0 overlap, without respondent records.
- **S002 BLOCKED:** original survey participant-response rows carry per-original-study rights / research consent uncertainty and source-rights registry has `local_research: hold`. Cannot produce empirical held-out SocSci210 accuracy/TVD while they are inaccessible under approved handling.
- **S003–S008 TODO:** some engineering components and a real *Concordia engine mock run* exist, but their original sequential acceptance criteria require real permitted study data, human/model comparisons, causal fidelity, and generalization and are **not** satisfied. Do not promote statuses due to synthetic fixtures or simulated logs.
- H005 from Phase03 remains `skipped` (with evidence), so the overall evidence Gate 1 for independent human RCT effect reproduction remains unmet. No measured Manager-induced human welfare impact exists.

Canonical: `docs/roadmap/tasks.json` only; generated `docs/roadmap/ATOMIC_BACKLOG.md` is synchronized. Neither Life Manager progress SSOT nor production systems were modified.

## S001 — Real pinned metadata audit

Official source `socratesft/SocSci210@048481111a4425ed83dc0eacf15f8431f252b21a`, `metadata/participant_mapping.json`. Despite the filename, the file contains *study IDs* in `seen` / `unseen` arrays. Immutable blob SHA-1 `8aa37bd598ce8bb00103a5a885948299f75f5ce7`, **1,710 bytes**, **170 seen + 40 unseen**, **0 ID overlap**. The 210-study mapping is a necessary split-provenance check, NOT evidence of model predictive accuracy.

- Implemented: `scripts/socsci_split_audit.py`, a byte-limited HTTPS read of the immutable revision, Git blob hash validation, size/schema/count/disjoint checks, and aggregate-only output (no study/participant identifiers serialized).
- Synthetic unit contract: `tests/test_socsci_split_audit.py`: 4/4 pass, including duplicate/overlap/malformed/changed-hash failures.
- Real external verification: [GitHub Actions run 39536829220](https://github.com/Daisuke134/life-manager/actions/runs/39536829220) SUCCESS; aggregate artifact `socsci-s001-study-split-aggregate`. No respondent CSV/Parquet or participant records were downloaded.
- Longer source and rights evidence: `docs/research/socsci/S001_STUDY_SPLIT_AUDIT_JA.md`, `docs/research/source-rights.json`.
- Upstream: https://huggingface.co/datasets/socratesft/SocSci210 and https://aclanthology.org/2025.emnlp-main.1530/ .

## S002–S006 & S008 — Methods code is verified, real-science acceptance remains open

- `manager_core/phase04_synthetic.py`: `binary_baselines`, `compare_on_unseen_studies`, `wasserstein_ordinal`, `constructed_causal_gap`, `synthetic_phase04_report`.
- `tests/test_phase04_synthetic.py`: six deterministic contract tests, including cross-study leakage rejection, ordinal distribution support, binary Brier/TVD, and absence of respondent fields.
- `scripts/phase04_synthetic_bench.py`: separate aggregate outputs for a **synthetic** prediction/shift test, a constructed causal-gap counterexample, and an explicit real-validation absence record.
- Hosted offline CI [run 39537750991](https://github.com/Daisuke134/life-manager/actions/runs/39537750991) **SUCCESS: 170/170 unit tests, bounded Manager imports, backlog checker PASS (113 tasks), synthetic CLI and aggregate evidence boundaries passed**.
- Two synthetic novel conditions with 4 observations each, training baseline p=0.5: frequency model pooled **accuracy 0.50, Brier 0.25, TVD 0**; tie-break majority model pooled **accuracy 0.50, Brier 0.50, TVD 0.50**. Per-condition TVD=0.25 leads to **2/2 ABSTAIN** under toy threshold 0.20.
- Constructed causal *counterexample*, NOT learned empirical causal effect: P(Y=1|do(0))=.3, P(Y=1|do(1))=.7 and balanced randomization. Treatment-blind p=.5 gives pooled TVD0 but effect prediction 0 vs construction truth .4; **error .4**. Shows descriptive match is insufficient for causal decisions.
- Important metric distinction: Original Socrates article evaluates accuracy and normalized ordinal **Wasserstein** errors, whereas Manager TVD/Brier are supplemental. Neither substitutes for a real held-out human study or actual randomized intervention effect evaluation.
- Source-boundary in scripts: no personal records or real-effect executor; all results are labeled `SYNTHETIC_ONLY`, `NOT_PERFORMED` where appropriate.
- Scientific report and exact toy equations: `docs/research/socsci/PHASE04_METHODS_PARTIAL_JA.md`.

**Blocker**: Per-study licensed/consented participant outcomes and a documented permitted evaluation pathway are missing; no full 40-study held-out dataset was processed. The public model's original performance and inference costs are not Manager-measured, and S002–S006/S008 remain uncompleted.

## S007 — Actual upstream Concordia engine executed, but human validity unmeasured

- Upstream `google-deepmind/concordia@7128586aa8c1073bfa09dcb3781cea21e1a49229` (Apache-2.0, package v2.4.0); Python 3.12, separate ephemeral upstream source checkout, no reused Life Manager infrastructure, no API key/model requests.
- Actual upstream executable: `python -m examples.deep_time.run --scenario=daisyworld --mode=mock --ticks=6 --seed=0 --out_dir=...`; **6 mock simulation ticks**, real upstream simulation files `simulation/log.html`, `simulation/summary.json`, `simulation/topics.mmd`.
- Workflow `.github/workflows/manager-concordia-sandbox.yml` creates **separate** `simulation/` and `real_world_validation/verification.json`; real-world records **0**, external effects **DISABLED**, human fidelity **NOT_MEASURED**. Artifact records are retained by GitHub Actions for 14 days; workflow code is version-controlled permanently.
- First independent execution [run 39537295867](https://github.com/Daisuke134/life-manager/actions/runs/39537295867) **FAILED** with upstream example's missing PyYAML import. Root-cause log `ModuleNotFoundError: No module named 'yaml'`. Added bounded pinned dependency `PyYAML==6.0.2` (no unrelated app changes).
- Follow-up [run 39537485934](https://github.com/Daisuke134/life-manager/actions/runs/39537485934) **SUCCESS**, including readback of actual generated artifacts and independent validation-absence record. [Concrete sandbox artifact](https://github.com/Daisuke134/life-manager/actions/runs/39537485934/artifacts/12317987966).
- **Limit**: `daisyworld` is a planetary toy scenario, not independently validated human social behavior. Six mock ticks demonstrate software integration only. S007 original task and its S006 dependency remain open for bona fide social/behavioral experiments and independent human comparison.

## Unfinished validation gates (mandatory, not faked or silently waived)

| Task | Scientific completion still missing |
|---|---|
| S002 | Rights-cleared real 40-study held-out response benchmarks, frequency/majority accuracy and TVD |
| S003 | Leakage verified on real study outcomes (synthetic mechanism already tested) |
| S004 | Real unknown-study TVD/Brier/subgroup calibration, denominators, abstention failure analysis |
| S005 | Public pretrained models under same splits, license and inference cost comparison |
| S006 | Empirical treatment-assignment ground truth, effect-size/uncertainty and causal-error comparisons |
| S007 | Empirical generative-agent human-behavior validation beyond Concordia mock demonstration |
| S008 | Generalization errors for two rights-cleared genuinely unfamiliar real conditions/populations |

Permitted next work: review primary-source rights per study, use only a documented permission-cleared experiment or **public aggregate outcome tables where suitable and authorized**, add independent paper-metric scoring, compare and report real results. Do not ask for or process the private participant records to shortcut a publication. An alternate fully reproducible public RCT can meet the separate HeartSteps/H005 unmet original-effect replication gate. External interventions and beneficiary claims remain strictly separate.

## Runtime verification scope

Everything listed above was verified through actual authenticated GitHub tool reads and hosted GitHub Actions logs, not a local canonical Mac checkout. This session had **no access to the user's `/Users/anicca/Projects/life-manager-main` checkout**, so the local `scripts/verify-source-boundary.sh` script itself was **not run**. GitHub Actions tested `products/manager/scripts/check_boundaries.py` and explicitly checked that no prohibited Life Manager module imports were present. Never conflate the latter with the unavailable Mac checkout boundary verification.

**Mission:** End suffering, with real-world causal benefit ultimately independently demonstrated. This report makes no claim of new beneficiaries, a validated behavior simulator or Phase04 complete.
