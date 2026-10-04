# Moneytree current-plugin readback — 2026-10-04 17:30 JST

## Observation

- Read-only `show_accounts` succeeded for the connected Moneytree source and returned one bank account. The response exposes a balance field but no source-updated or last-sync timestamp; an on-demand successful read is not proof that the provider data is fresh.
- `show_transactions` for 2026-09-05..2026-10-04 returned 0 rows.
- A diagnostic `show_transactions` query for 2026-08-01..2026-08-31 returned 80 rows, with latest transaction date 2026-08-25. This does not mean no later spending occurred; it bounds the available readback.
- `show_spending_summary` for 2026-07-05..2026-10-04 returned July and August buckets only. July's requested range starts after the first day of that month; August's latest transaction is August 25. September and October buckets are absent.
- Transaction classification includes negative-value transfers and repayments separately from explicit expense rows. Summing every negative transaction as spending would double-count transfers and misstate expense.

## Boundary and next evidence

- This is a read-only observation; no sync, bank mutation, transaction update, or payment was initiated.
- The available Moneytree tool surface in this session exposes account, transaction, and spending-summary reads, but no sync/refresh status operation. No account number, transaction description, merchant name, or personal amount is retained here.
- Keep personal cash balance freshness `partial/stale` and September/October personal expenses `unknown` until a provider freshness cursor or another official current readback covers the period.

## 12-month transaction revalidation — later 2026-10-04

- Four non-overlapping `show_transactions` windows returned 178 / 311 / 316 / 183 rows, 988 total with no repeated transaction IDs. Available date range was 2025-10-04..2026-08-25, unchanged from the earlier read.
- Moneytree assigned `category_type=expense` to 45 rows and `income` to 48 rows. The remaining 895 rows had neither classification; 887 of those were negative amounts. Negative rows include transfers and repayments and must not all be summed as consumption expenses.
- Eleven transactions had an `expense` category but positive amounts; these are credits/reversals and must not be converted with `abs()` into spending. The sum of negative `expense`-typed rows reconciled to the separate Moneytree spending-summary buckets. This is the supported categorized-spend interpretation; no private amount is stored here.
- The 12-month response still has no transactions from 2026-08-26 through 2026-10-04. No personal amounts, account numbers, transaction descriptions, or merchant names are retained.
- TODO/status source of truth → [Unified SSOT](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md).

## Current-session direct plugin re-read — evening 2026-10-04

- `show_accounts` again returned one MUFG ordinary JPY bank account and a displayed balance; no source-updated/last-sync timestamp was returned. The exact personal balance is intentionally omitted.
- `show_transactions` for 2026-07-04..2026-10-04 with `limit=1000` returned 183/183 rows; first/last transaction dates were 2026-07-04 and 2026-08-25. No row exposed a provider update/sync timestamp.
- Category counts include 167 transfers, 2 card repayments, 2 ATM withdrawals, and 2 unclassified rows, alongside salary/income/interest and one social-expense row. Raw inflow/outflow is not a complete income/expense statement because transfers, repayments, cash withdrawals, and unclassified entries cannot be treated as economic revenue/expense.
- A September-only income query returned 0 rows and the September-only spending summary returned no buckets. Given the transaction feed ends on August 25, these are coverage gaps, not evidence of zero September income/spend.
- This plugin exposes no sync/refresh operation in the current tool surface. No account/login/sync mutation was performed. Fresh current cash and September/October expense remain unverified.
