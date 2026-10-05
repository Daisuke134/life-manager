# Google Cost Table Cross-Month Row Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` on the existing CFO candidate worktree. This is one coupled parser change; do not create another worktree or delegate overlapping writes. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Both Life Manager Cost Table readers include invoice-scoped nonzero Japanese usage rows even when `使用開始日` falls in the prior month, retain valid usage-date provenance, and fail closed on malformed dates.

**Architecture:** The selected Japanese CSV is invoice-scoped; its usage-start date is provenance, not invoice membership. Keep the English CSV path's explicit `Invoice month` filtering. Apply the same minimal fix to the existing Node CFO reader and Python B7 reader.

**Tech Stack:** Node.js CommonJS + `node:test`; Python `unittest` + `Decimal`; existing Google Cost Table readers.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` §87-J item 5/6 and §87-AW.

## Global Constraints

- Missing, malformed, or incomplete billing input remains unknown/failed, never zero.
- The caller-selected `invoiceMonth` remains the billing period; preserve actual usage-start dates where emitted.
- Keep service usage, tax, rounding, and invoice total separate and exact; never convert currencies.
- Use synthetic fixtures for tests; the actual private CSV may be read locally without printing its path or raw rows.
- Post-fix actual-invoice replay and service-cost reconciliation remain in unified SSOT §87-J item 6; the configured private CSV reference is unavailable in this implementation shell/loaded CFO job, so no fresh actual parser output is claimed here.
- Do not call providers, write runtime state, change report arithmetic, launchd, or production configuration.
- Modify only the two existing parser files and their two existing tests.

## Review Focus

- September's invoice includes the 2026-08-31 nonzero Cloud Storage row in the September service subtotal; zero-value rows do not affect totals.
- The row remains dated 2026-08-31 as usage evidence while its `invoiceMonth` remains 2026-09.
- A selected nonzero Japanese usage row with a missing or invalid `使用開始日` fails closed; valid prior-month dates and years 0001–9999 are accepted, but year 0000 is rejected in both runtimes.
- Six-decimal JPY precision is preserved (`0.000300` becomes `0.0003`).
- Tax/rounding rows do not become service usage, and the total reconciles to the invoice total.
- English-format exports continue filtering by their explicit `Invoice month` field.

---

### Task 1: Correct the Japanese Cost Table invoice boundary in both readers

**Files:**
- Modify: `apps/life-manager/lib/google-billing-readback.js`
- Test: `apps/life-manager/lib/google-billing-readback.test.js`
- Modify: `skills/cfo/loop_pnl.py`
- Test: `skills/cfo/test_loop_pnl.py`

**Interfaces:**
- Node `readGoogleBillingCsv(filePath, { invoiceMonth, observedAt })` returns the included usage lines, service totals, invoice month, tax, rounding, and invoice total.
- Python `google_billing_actual_cost_readback(path, { invoice_month, snapshot_at, trailing_start })` emits corresponding official invoice lines and variance fields.

- [x] **Step 1: Write failing parser tests.** Node and Python tests cover prior-month Cloud Storage JPY `0.000300` in a selected `2026-09` invoice and reject empty, impossible (`2026-02-30`), and year-zero (`0000-01-01`) usage dates with `google_billing_usage_date_invalid`. The valid row keeps `invoiceMonth=2026-09` and Python `occurred_at=2026-08-31T00:00:00Z`.
- [x] **Step 2: Run both focused suites and confirm RED.** The prior-month-only row first failed in both parsers; the later missing/impossible/year-zero cases also failed before the respective date checks. TDD evidence and exact outputs are in the SDD task report.
- [x] **Step 3: Implement the minimal fix.** Both Japanese readers use the selected invoice document as membership, retain valid usage dates as provenance, and fail closed for nonzero rows with missing/invalid dates; allowed calendar years are 0001–9999. English-format `Invoice month`, tax, rounding, and total logic remain unchanged; zero-value rows remain omitted.
- [x] **Step 4: Verify source behavior.** Node suite 6/6, Python suite 48/48, `git diff --check`, source-boundary, and independent code review pass. The configured post-fix private CSV replay could not be run because its path is absent from the current shell and loaded CFO job. The preceding official invoice read is recorded in SSOT §87-AW, but it is not a post-fix parser output; exact service-cost reconciliation remains open under §87-J item 6.
- [x] **Step 5: Commit and push the candidate branch.** Source commit `461a8814dd1645a929e0f461e4b6bb5e5cbe50cb` is on the candidate branch. No merge or deployment.
