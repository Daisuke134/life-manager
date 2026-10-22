# Public behavior source inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Implement slice A: reproducible, read-only validation of the already released Nature aggregate snapshot, without a proprietary provider or Manager runtime dependency.

**Architecture:** Grow the existing stdlib inspection companion into one canonical CLI. Reuse the existing `reuse.json` metadata, validate all pinned bytes before parsing, then validate Fig1 panelA/B and emit aggregate-only JSON. The old companion becomes a thin entrypoint; other panels are inventory only.

**Tech Stack:** Python standard library, unittest, small synthetic OOXML fixtures. No dependency installation or new inference.

**Spec:** `docs/research/manager/2026-10-22-open-behavior-reuse-plan.md`, slice A; source metadata in `docs/research/manager/evidence/artificial-societies-20261022/reuse.json`.

## Global Constraints

- Manager is a 仏教的AIエンティティ／デジタル仏陀. This slice does not redefine its mission or claim measured human benefit.
- Do not import, copy or merge the unintegrated Manager runtime. Do not edit the E16 handoff worktree, runtime state, credentials, publishers or workflows.
- Preserve a single metadata authority: existing `reuse.json`. No CLI override of source pins or alternate manifest.
- Raw source PDF/XLSX, individual records, private paths, condition labels and study identifiers stay out of Git and CLI diagnostics.
- Input is an explicit local private directory. No network calls, downloads, API inference, paid resources, provider effects or input writes.
- Count 3356 directed rows as dependent contrasts, not independent studies, trials or 469 independent replicated effects. This is released-aggregate inspection, not original-method reproduction or new predictions.
- Source-boundary guard fails in this authorized cloud environment because `/home/agent/Projects/life-manager-main` is absent. Record FAIL; do not change the guard or claim PASS.
- TODO authority and original Phase/E16 acceptance remain unchanged.

## Review Focus

1. Hash mismatch or a missing source file must stop before parsing, including under `python -O`.
2. Missing required cells, duplicate identities, invalid numbers or reversed contrast signs must not silently become valid data or zero.
3. Repeated labels in different studies/outcomes must remain distinct; reverse pairs remain dependent rows.
4. Legitimate blank cells in unanalysed Fig3 panels must not fail Fig1 validation or imply a full reanalysis.
5. Errors and successful stdout must not disclose private input paths, study/condition labels or raw records.

## Task 1: Canonical inspector, tests and usage

**Files:**
- Create: `products/manager/scripts/inspect_external_behavior_benchmark.py`
- Create: `products/manager/tests/test_external_behavior_benchmark.py`
- Modify: `docs/research/manager/evidence/artificial-societies-20261022/inspect_source_data.py`
- Modify: `docs/research/manager/evidence/artificial-societies-20261022/reuse.json` (supplement URL only if needed)
- Modify: `docs/research/manager/evidence/artificial-societies-20261022/README.md`
- Modify: `docs/research/manager/2026-10-22-open-behavior-reuse-plan.md` (slice A actual verification/status only; B–F stay planned)

**Interfaces:**
- Consumes: local `supplement.pdf`, `fig1.xlsx`, `fig2.xlsx`, `fig3.xlsx`; existing `nature.version`, `source_downloads`, `execution_receipt` metadata.
- Produces: `inspect_snapshot(input_dir: Path, nature: dict) -> dict` for aggregate inspection; `main(argv=None) -> int` for CLI. Internal fixture metadata may be passed by tests; production CLI always loads the repository pin.
- CLI: `python products/manager/scripts/inspect_external_behavior_benchmark.py PRIVATE_DIRECTORY`; success stdout is finite JSON and exit 0; validation failure emits a fixed/sanitized error code to stderr, no success JSON, exit 2.
- Legacy companion delegates to the same `main` and preserves the positional directory invocation. It must work from a different current directory.

- [ ] Write synthetic tests first. Name the production mutation each test catches. Fixtures create OOXML ZIPs in temporary directories; never use original data bytes or labels. Cover byte tamper/missing file/hash checks before XML parsing, required headers/cells, shared/inline strings, duplicate headers/cells, nonfinite/non-numeric/error cells, missing sheet, study/outcome-scoped duplicate keys, self comparisons, missing reverse and wrong reverse sign. Check direction as condition minus reference on full-scale signed differences (percentage points are 100×); do not clip negative values. Tolerance is `1e-10`.
- [ ] Run the focused command and observe failure because the inspector does not yet exist. Record RED evidence in the private report.
- [ ] Reuse the existing companion parser and diagnostic computations in the canonical file. Keep the XLSX reader limited to this pinned format. Validate all four byte lengths and hashes before opening any workbook. Explicit exceptions replace `assert`. Fig1 panelA required fields are `study`, `reference_condition`, `outcome.name`, `condition.name`, `estimate`, `prediction`, `group`; both numeric fields are finite signed full-scale differences in [-1,1]. Group labels are published/unpublished. Validate complete directed comparisons per study×outcome, distinct-condition direction/reverse invariants and consistent study groups. Validate panelB numeric summaries against the existing receipt. Keep existing pooled diagnostics explicitly dependent/unadjusted, with no new CI or fit claim.
- [ ] Emit public source DOI/version/URLs/hash, study/directed/unordered-pair/study×outcome counts, published/unpublished counts, existing diagnostics and published GPT-4 summaries, units/direction, coverage and rights limitations. No study IDs, condition labels or private paths. Inventory all pinned XLSX sheets as acquired; strict data analysis is only Fig1 panelA/B. PDF is hash-verified only by this CLI. Use `allow_nan=False`.
- [ ] Run focused tests including optimized-process hash failure and sanitized CLI errors. Verify real private snapshot once: 70 studies, 3356 directed rows, 129 study×outcome blocks, 1678 unordered pairs, 8 panelB rows, group counts 1572/1784, four original hashes, GPT-4 raw r .8507895015768856 and adjusted .9151266459087334. Save aggregate output outside Git. Run legacy entrypoint from outside repo and compare output. Missing private inputs in CI are not a real-data pass.
- [ ] Update usage and the existing reuse plan with exact verified scope; do not mark B–F, E16 or human benefit complete. Run `python -B -m unittest discover -s products/manager/tests -p 'test_external_behavior_benchmark.py' -v` and `git diff --check`. Existing repo CI remains required for merge; no runtime test suite copied to main.
- [ ] Commit the bounded files. Produce a private implementation report with files, RED/GREEN commands/results, real-snapshot aggregate results, limitations, commit and any concerns. A fresh reviewer reads the actual diff before normal PR/green merge.
