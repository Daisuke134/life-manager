# CFO A6 Google Billed Expense Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` and `superpowers:test-driven-development` to implement this plan inline. Steps use checkbox syntax for tracking.

**Goal:** Show the captured official Google Cloud invoice in the existing CFO report as billed expense, separate from cash paid and without unsupported loop allocation.

**Architecture:** Add a pure Python standard-library Cost Table CSV reader and attach its verified invoice-month projection beside, not inside, B0 settled receipts. The existing CFO result renderer shows invoice total and service/SKU breakdown, with cash payment and loop allocation explicitly unknown unless evidence exists. No provider call, migration, new loop, CLI, or global spend cap is introduced.

**Tech Stack:** Python standard library (`csv`, `decimal`, `hashlib`, `pathlib`), existing `loop_pnl.py` B7 projection, existing Node.js `cfo-result-summary.js` and `node:test`.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` (A6); `docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md` (business CFO and invoice-vs-cash contract).

## Global Constraints

- A billed invoice is an expense fact; it is not proof of cash payment.
- Keep the official invoice total distinct from provider estimates and settled receipts.
- Preserve the unrounded JPY amount column; never sum the invoice summary row with its details.
- Do not assign Google service/project cost to a business loop without occurrence-backed evidence; show company-level cost as unattributed.
- Missing, unreadable, or unreconciled invoice data is `unknown`/`unverified`, never zero.
- Do not expose billing-account ID, project ID/name, invoice number/ID, or raw CSV rows in the report.
- Use only the already captured local CSV; make no Google/provider request and do not read Moneytree.
- Keep `loop_pnl.py --date` semantics unchanged; label the invoice month from its source file, not the report date.

## Review Focus

- Wrong amount column: the unrounded JPY column must drive arithmetic; the rounded display column is not authoritative. Test the exact expected invoice reconciliation.
- Summary duplication: the table's `合計` row must be validated but not added to detail sums. Test one invoice whose detail arithmetic equals the metadata total.
- Adjustment signs: discount, tax-adjustment, and rounding rows may be negative; test each signed amount independently.
- Missing or malformed source: test that no file and invalid/mismatched CSV return unavailable/unverified with no zero amount.
- Privacy and attribution: test that account/project identifiers are absent from output and that payment/loop attribution remain unknown/unattributed.

---

### Task 1: Parse and verify the official Cost Table CSV

**Files:**
- Create: `skills/cfo/adapters/google_cost_table.py`
- Modify: `skills/cfo/loop_pnl.py`
- Create: `skills/cfo/test_google_billed_expense.py`

**Interfaces:**
- Produces `load_directory(directory: Path) -> BillingProjection`; `_b7_table(...)` adds top-level `table.google_billed_expenses` by reading the configured/default billing directory.
- `BillingProjection` is `{status: verified|unavailable|unverified, reason: str|null, invoices: Invoice[]}`; each `Invoice` is `{status, invoice_period: YYYY-MM, currency: JPY, billed_total_jpy: str|null, service_sku: [{service, sku, usage_gross_jpy, credits_jpy, net_billed_jpy}], adjustments: {usage_gross_jpy, credits_jpy, tax_jpy, rounding_jpy}, cash_paid_status: unknown, allocation_status: unattributed, source_ref, reason}`.
- The canonical B0 projection calculation and receipt schema remain unchanged. `_b7_table` exposes the separate result as top-level `google_billed_expenses`; billed invoices are not turned into B0 settled receipts or added to B0 net.
- Reads only CSV files named `YYYY-MM-cost-table.csv`; the parser ignores account and project columns in output.

- [x] **Step 1: Write RED integration tests** in `skills/cfo/test_google_billed_expense.py` named `test_google_invoice_uses_unrounded_cost_and_reconciles_adjustments`, `test_google_invoice_excludes_summary_row_from_detail_sum`, `test_google_invoice_mismatch_is_unverified_not_zero`, `test_google_invoice_missing_or_malformed_source_is_unknown`, and `test_google_invoice_projection_hides_account_project_and_invoice_ids`. Use synthetic 18-column CSV rows, patch `LM_CFO_GOOGLE_BILLING_DIR`, call `_b7_table`, and assert the public B7 table output. For the valid fixture, assert usage gross `100.123456`, credits `-0.003456`, tax `10`, rounding `-0.12`, invoice billed total `110`, and a service/SKU net of `100.12`.
- [x] **Step 2: Run RED** with `python3 -m unittest skills.cfo.test_google_billed_expense`; each new case failed by assertion because the `google_billed_expenses` table field was absent, not by import or syntax error.
- [x] **Step 3: Implement** `skills/cfo/adapters/google_cost_table.py::load_directory(directory: Path) -> BillingProjection` and add its result at the existing `_b7_table` boundary. Read `LM_CFO_GOOGLE_BILLING_DIR` or the existing default state directory; import the helper locally inside `_b7_table` to avoid the separate RevenueCat edit hunk. Detect the header by required column names, parse `Decimal` from `四捨五入前の費用（¥）`, group gross usage and only explicitly service/SKU-matched credits, keep tax/rounding separate, exclude the `合計` row from detail sums, and expose an invoice total only after exact reconciliation.
- [x] **Step 4: Run GREEN** with `python3 -m unittest skills.cfo.test_google_billed_expense`; 5/5 cases passed. The combined Google-cost and existing B7 test run passed 49/49, and the captured official CSV produced verified invoice total ¥27,889, cash-paid unknown, and unattributed loop scope.
- [x] **Step 5: Commit** the parser, B7 integration, tests, and this plan.

### Task 2: Attach billed expenses to the existing CFO report

**Files:**
- Modify: `apps/life-manager/lib/cfo-result-summary.js`
- Test: `apps/life-manager/lib/cfo-result-summary.test.js`

**Interfaces:**
- Consumes `table.google_billed_expenses` from Task 1.
- Produces the existing CFO result message with invoice period, billed amount, service totals, unknown cash payment and unattributed ownership; it does not alter B0 settled net.
- The Japanese message labels invoice period, currency, billed total, service totals, usage/credit/tax/rounding reconciliation, `支払状況: 未確認`, and `loop配賦: 未帰属`; the JSON field retains the full service/SKU breakdown.

- [x] **Step 1: Write RED tests** named `test_summary_displays_billed_invoice_without_claiming_cash_paid` and `test_summary_renders_unknown_billing_as_unknown_not_zero`.
- [x] **Step 2: Run RED** with `node --test apps/life-manager/lib/cfo-result-summary.test.js`; the two new tests failed because invoice data was omitted from the message.
- [x] **Step 3: Implement** a compact Japanese summary with service totals and usage/credit/tax/rounding reconciliation; the JSON projection retains all service/SKU rows, while the message labels invoice month, billed total, `支払状況: 未確認`, and `loop配賦: 未帰属`.
- [x] **Step 4: Run GREEN** with `node --test apps/life-manager/lib/cfo-result-summary.test.js`; all 15 tests passed, including the legacy text check.
- [x] **Step 5: Run affected verification**: `python3 -m unittest skills.cfo.test_google_billed_expense skills.cfo.test_loop_pnl` (49 passed); `node --test apps/life-manager/lib/cfo-result-summary.test.js` (15 passed); `git diff --check`.
- [x] **Step 6: Commit** the renderer and tests.

## Scope Boundary

This completes only the invoice-billed fact ingestion/display portion of A6. A6 remains open until the monitoring-estimate comparison uses a matching period and the bill's tax/credit/rounding details reconcile. Loop attribution stays unattributed unless A5/runtime evidence proves it; A8 owns the final loop-versus-company-overhead join. Do not claim cash paid or a complete company P&L from this subtask.
