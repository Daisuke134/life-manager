# Personal Moneytree Section in CFO Report Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` task-by-task. The unified SSOT remains the only TODO/order/cursor source; this parallel A7/A9 slice does not advance or reorder its A4.1 cursor.

**Goal:** Put a private, source-linked Moneytree balance and transaction-coverage section in the existing Life Manager CFO report without mixing personal money into business P&L.

**Architecture:** The active entrypoint calls `runResultCfo`, which accepts `collect(date)` and persists/hashes the returned projection and rendered message. `cfo-hourly-local.js` will use that seam to run the existing business `loop_pnl.py` collector and add a minimized `personal_moneytree` projection. `cfo-result-summary.js` will render a separate personal section. `cfo-result-local.js` stays untouched because the active B7 owner controls it.

**Tech Stack:** Node.js, existing `loop_pnl.py`, Moneytree app-server adapter and observation store, `node:test`.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` (A7/A9) and `docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md`.

## Global Constraints

- Personal data has owner `dais_personal`; never add it to company revenue, cost, net, MRR, or runway.
- Moneytree provides retrieval time but no upstream bank-sync timestamp. Label balances as provider-reported with freshness unknown; missing transactions are unknown, never zero.
- Exclude internal transfers from personal income/expense. Do not move funds or imply that a transfer is revenue.
- Never persist account numbers, credentials, raw payloads, or transaction-level rows. The private owner-facing report/cache may include normalized institution labels, category totals, and recurring-charge candidate labels because subscription visibility is explicitly requested; raw transaction descriptions never enter logs or source fixtures.
- Preserve the existing single CFO delivery route, event key, pending-receipt fence, and B7 snapshot hashing. No second message or loop.
- A Moneytree read/evidence failure yields an unavailable/unknown personal section but does not discard a valid business report.
- Do not edit `cfo-result-local.js` or B7-owned files; do not change the unified SSOT while its lease is held.
- This patch is explicitly partial A7 progress: query coverage can be established for the latest 12 months, but upstream freshness remains unknown because the current Moneytree tool provides no sync timestamp. Repeated charges remain candidates, not verified subscriptions.

## Review Focus

- No provider sync timestamp: show the last-observed balance with retrieval time; never call it fresh/current.
- Zero rows in a reporting period: show coverage unknown, not ¥0.
- Read the available 12-month history through four serial, non-overlapping Moneytree queries, each no longer than three months; a failed or overflowed chunk stays a visible coverage gap.
- Older returned rows: show latest observed transaction date and mark category/period values as partial observations.
- Transfers are excluded; personal amounts never change business totals.
- Repeated merchant charges are candidates, not verified subscriptions, until another authoritative subscription source confirms them; card repayments and ATM withdrawals are not consumption.
- Moneytree read or evidence-store failure keeps the business report intact; same-period pending retry reuses the exact frozen message without recollection.

---

### Task 1: Preserve a safe institution label

**Files:**
- Modify: `apps/life-manager/lib/moneytree-local-adapter.js`
- Test: `apps/life-manager/lib/moneytree-local-adapter.test.js`

**Interfaces:**
- Consumes: Moneytree group `institutionName`, account `nickname`/`institution_account_name`, and transaction query metadata.
- Produces: normalized account `name` such as `三菱UFJ銀行 普通`; transaction observation metadata `{query_start_date,query_end_date,provider_total_count,returned_count,limit}`; categories `振替`, `カード返済`, and `ATM引き出し` are cash movements, not consumption; never account number or provider account ID.

- [x] **Step 1: Write `normalizeAccounts preserves the bank label without account identifiers`** with literal `三菱UFJ銀行 普通` and assert the account number is absent.
- [x] **Step 2: Write `readTransactions records requested range and returned coverage`** with literal range/count values and assert they appear in the adapter observation metadata.
- [x] **Step 3: Write `Moneytree transfer, card repayment, and ATM withdrawal categories are not consumption`**; assert each becomes an unallocated cash movement, not personal expense.
- [x] **Step 4: Run `node --test apps/life-manager/lib/moneytree-local-adapter.test.js`; confirm the new assertions fail.**
- [x] **Step 5: Add the safe institution label, bounded query metadata, and non-consumption classification; never store account numbers/provider IDs.**
- [x] **Step 6: Run `node --test apps/life-manager/lib/moneytree-local-adapter.test.js`; confirm all adapter tests pass.**
- [x] **Step 7: Commit the task.**

### Task 2: Add the personal snapshot to the existing B7 report

**Files:**
- Modify: `apps/life-manager/scripts/cfo-hourly-local.js`
- Modify: `apps/life-manager/lib/cfo-result-summary.js`
- Test: `apps/life-manager/scripts/cfo-hourly-local.test.js`
- Test: `apps/life-manager/lib/cfo-result-summary.test.js`

**Interfaces:**
- `collectCfoProjection(date, options) -> Promise<businessTable & {personal_moneytree}>` runs the current read-only `loop_pnl.py` invocation, then reads Moneytree accounts once and transactions in four serial, non-overlapping inclusive windows covering `[reportDate minus 12 calendar months, reportDate]`. Each window is at most three months; the next starts the day after the previous ends.
- Each window records `{query_start_date,query_end_date,provider_total_count,returned_count,limit,coverage_status,evidence_ref}`. `coverage_status` is `complete` only when provider total equals returned rows and the 1000-row limit was not reached; otherwise mark that window partial/unknown.
- The private `personal_moneytree` projection contains `schema_version: 1`, `owner: "dais_personal"`, `status: observed|partial|unavailable|stale`, `observed_at`, `provider_sync_at: null`, `freshness_status: unknown|stale`, per-window evidence/coverage, safe-label balances, latest transaction date, JPY category-period observed subtotals, cash-movement subtotals, and recurring-charge candidates. A candidate requires the same normalized merchant label in at least two distinct months; it is never represented as a verified subscription. No account IDs or raw transaction rows are stored.
- Cache only that minimized projection and evidence references in `stateDir/personal-moneytree-snapshot.json`, atomically with mode 0600, for at most 24 hours. Cache age is distinct from provider freshness. Expired cache plus refresh failure becomes stale/unknown, never current.
- On a Moneytree/evidence error, `collectCfoProjection` preserves the business table and sets personal status to unavailable; it does not throw.
- `renderResultSummary(table)` appends a personal section only when `personal_moneytree` exists. Snapshots without that field keep their exact existing message.

- [ ] **Step 1: Write `collectCfoProjection preserves business data and binds Moneytree evidence`**; literal business-table fields remain unchanged while each personal window is paired with its receipt.
- [ ] **Step 2: Write `Moneytree reads cover four bounded windows and dedupe boundary rows`**; assert the four literal ranges, no duplicate transaction IDs, returned-vs-total counts, and visible gap state on an incomplete chunk.
- [ ] **Step 3: Write `Moneytree periods without provider sync remain unknown, not zero`**; assert `provider_sync_at === null`, `freshness_status === "unknown"`, latest transaction date is retained, and zero-row flow amounts are null.
- [ ] **Step 4: Write `Moneytree transfers are excluded and recurring charges remain candidates`**; assert transfer/card repayment/ATM rows do not enter expense totals and a repeated merchant is shown only as an observed candidate.
- [ ] **Step 5: Write `Moneytree failure preserves business data and legacy rendering`**; assert read/evidence failure leaves the business projection intact and a projection without `personal_moneytree` renders exactly as before.
- [ ] **Step 6: Write `Moneytree cache reuses a same-day snapshot and never upgrades stale data`**; assert one provider read within the 24-hour cache window and freshness stays unknown.
- [ ] **Step 7: Run `node --test apps/life-manager/scripts/cfo-hourly-local.test.js apps/life-manager/lib/cfo-result-summary.test.js`; verify the new assertions fail for the missing behavior.**
- [ ] **Step 8: Implement `collectCfoProjection(date, options)` and pass it through `runResultCfo({collect})`.** Preserve the exact business `loop_pnl.py` args/environment/timeout; read accounts once and transaction chunks serially; hash-bind each window receipt; dedupe rows; cache only the minimized summary for 24 hours.
- [ ] **Step 9: Render balances as provider-reported/freshness-unknown, empty periods as unknown, observed category totals as partial, and recurring charges as candidates only.**
- [ ] **Step 10: Exercise real `runResultCfo` pending/retry with an injected notifier; verify one frozen message and no recollect/resend.**
- [ ] **Step 11: Run focused tests and commit the task.**

### Task 3: Verify source and report contracts

- [ ] Run `node --test apps/life-manager/lib/moneytree-local-adapter.test.js apps/life-manager/scripts/cfo-hourly-local.test.js apps/life-manager/lib/cfo-result-summary.test.js apps/life-manager/scripts/cfo-result-local.test.js`.
- [ ] Run `git diff --check`, `bash scripts/verify-source-boundary.sh`, and `./bin/lm-loop-contract`.
- [ ] Review for PII/secret leakage and verify business totals, MRR, runway, provider routing, registry, cadence, and B7-owned source files are unchanged.
- [ ] Commit/push and open a draft PR. Production acceptance remains separate: main-derived immutable release, existing owner apply, natural scheduled report, and source receipt/readback.

## Execution Notes

- The live release calls `cfo-hourly-local.main`, which chooses the business-only `runResultCfo` path. The Moneytree-enabled `runHourlyCfo` exists but is not called by `main`.
- The existing `runResultCfo.collect` seam composes a separate personal projection into the B7 snapshot and message hash without editing `cfo-result-local.js` or changing delivery idempotency.
- The current mainline cursor remains A4.1; this is a parallel, explicitly partial A7/A9 implementation slice. It does not claim A4 completion, current bank freshness, verified subscription contracts, or production acceptance.
- Task 1 verification: the adapter tests first failed on the three intended behaviors, then passed after the minimal adapter change. The related ingest test had an unrelated stale literal (`15`) after main commit `6c5240d70e` expanded the catalog to 18 loops; its expected count now reflects the current contract. Adapter + ingest tests pass 15/15.
