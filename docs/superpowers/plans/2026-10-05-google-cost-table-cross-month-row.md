# Google Cost Table Cross-Month Row Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` on the existing CFO candidate worktree. This is one coupled parser change; do not create another worktree or delegate overlapping writes. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Both Life Manager Cost Table readers include every nonzero billed Japanese invoice usage row—even when its `使用開始日` falls in the previous month—and reconcile service subtotal, tax/rounding, and invoice total.

**Architecture:** The selected Japanese CSV is invoice-scoped; its usage-start date is provenance, not invoice membership. Keep the English CSV path's explicit `Invoice month` filtering. Apply the same minimal fix to the existing Node CFO reader and Python B7 reader.

**Tech Stack:** Node.js CommonJS + `node:test`; Python `unittest` + `Decimal`; existing Google Cost Table readers.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` §87-J item 5/6 and §87-AW.

## Global Constraints

- Missing, malformed, or incomplete billing input remains unknown/failed, never zero.
- The caller-selected `invoiceMonth` remains the billing period; preserve actual usage-start dates where emitted.
- Keep service usage, tax, rounding, and invoice total separate and exact; never convert currencies.
- Use synthetic fixtures for tests; the actual private CSV may be read locally without printing its path or raw rows.
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

- [ ] **Step 1: Write failing parser tests.** Preserve Node test `Google Cost Table Japanese export includes prior-month usage in selected invoice` and Python test `test_google_billing_includes_previous_month_usage_row_in_selected_invoice` for a synthetic `2026-09` Japanese invoice containing only a Cloud Storage usage row dated `2026-08-31` for JPY `0.000300`, invoice total JPY `0.000300`, and no tax/rounding. Also add Node test `Google Cost Table Japanese export rejects missing, invalid, and year-zero usage dates` and Python test `test_google_billing_rejects_missing_invalid_and_year_zero_usage_dates`; each checks empty date, impossible date `2026-02-30`, and year-zero date `0000-01-01` on a nonzero usage row fail closed with `google_billing_usage_date_invalid`. Assert the valid prior-month Node row remains `status="settled"`, `costJpy="0.0003"`, `totalJpy="0.0003"`, `invoiceMonth="2026-09"`, and the Cloud Storage service row; assert Python emits amount `"0.0003"` at `occurred_at="2026-08-31T00:00:00Z"` and variance `{invoice_total:"0.0003", positive_cost_total:"0.0003", tax_and_rounding:"0"}`.
- [ ] **Step 2: Run both focused suites and confirm RED.** Run `node --test lib/google-billing-readback.test.js` from `apps/life-manager` and `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest skills.cfo.test_loop_pnl` from repo root. Expected failure: both readers reject/omit the prior-month-only usage row because of the start-date month filter; import/setup must succeed.
- [ ] **Step 3: Implement the minimal fix.** For Japanese invoices, include every nonzero usage row in the selected invoice and do not filter membership by the calendar month of `使用開始日`; require each selected nonzero usage row to have a valid calendar date in `YYYY-MM-DD` form with year 0001–9999, or fail closed with `google_billing_usage_date_invalid`. Retain the actual date in the Python evidence line and keep the selected `invoiceMonth` as its billing period. Preserve tax, rounding, total, and all English-format behavior; zero-value rows may remain omitted.
- [ ] **Step 4: Verify GREEN and re-read the private September invoice.** Re-run both focused suites and `git diff --check`. Using the configured file in memory only, confirm the Cloud Storage service total includes JPY `0.000300`, the usage subtotal is JPY `25,354.451251`, tax is JPY `2,535`, and invoice total is JPY `27,889`; do not print or save the source path/raw rows.
- [ ] **Step 5: Commit and push the candidate branch.** Do not merge or deploy.
