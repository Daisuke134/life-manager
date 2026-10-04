# Life Manager CFO handover

Verified clean base commit before this spec/handover refresh: `a9203cafd6ebaa5348d53d0a44003a21e65d07b2` (remote matched). Fetch the branch tip and verify HEAD/upstream/dirty state before editing; the refresh commit is the resulting branch tip.

- Repository: `/Users/anicca/Projects/life-manager-main`
- Worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002`
- Branch/upstream: `docs/lm-cfo-cost-observability-spec-20261002` / `origin/docs/lm-cfo-cost-observability-spec-20261002`
- TODO SSOT: [unified SSOT §87-J](/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md), items 5→6→7→8. Cursor: item 5.
- Design: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002/docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md`.
- Evidence: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002/docs/evidence/cfo/2026-10-05-cfo-live-observability-readback.md`.

## Verified state

- Candidate CFO report carries B7's precomputed receipt-backed economic snapshot separately from FinancialRecord totals; no JS re-summing. B7 nonfresh status and unknown MRR/runway make the report partial.
- Candidate Stripe adapter requires a recognized `lm_product_loop_id` matching the expected lane for verified revenue/refund/payment-fee/MRR. Category, generic owner, product name, or fixed `self-build` argument alone do not prove loop ownership.
- Tests: Python CFO 271/271; report/runtime/hourly Node 36/36. Fresh read-only review of report and Stripe guard: PASS. Source/test only; no production load.
- Latest candidate B7 direct projection (06:13 JST): historical/trailing gaps 135/130; all 14 loops, MRR, and runway unknown.
- Fresh Moneytree read (05:35 JST) still has no provider freshness timestamp; summary stops at 2026-08, and the 2026-09-01..10-05 transaction query is empty. No exact balance or transaction amounts are stored in this handover.
- Stripe GET (05:47 JST): 19 charge objects had no category or Product Loop/owner tags. Product/Price metadata had no recognized loop ID; one generic `owner` value remains unresolved. Do not infer attribution.
- Stripe Checkout Session/subscription GETs (06:55 JST): 231 all-time Sessions (8 `complete`+`paid`, 223 `expired`+`unpaid`; 61 subscription mode, 170 payment mode). All 231 lack `lm_product_loop_id`; the 8 paid Sessions have no `metadata.product`, loop ID, or `client_reference_id`, though 7 have invoice/subscription references and 1 has a PaymentIntent. The matching 30-day window has 4 Sessions, all expired/unpaid; all 7 returned subscriptions are canceled. This does not establish zero Stripe/company revenue or product ownership, and Sessions are not joined to the 19 charges. Official Product Loop crosswalk remains unresolved (§87-AR).
- Moneytree `show_accounts` (06:55 JST) returned one MUFG JPY account without source/provider/last-sync timestamp. The displayed value is last-known, not confirmed current cash; the connected plugin has no sync/refresh operation and September–October expense coverage remains unknown (§87-AS, §87-AN). Exact private balance omitted.
- RevenueCat V2 MRR chart reads (06:55 JST) covered six configured apps for 2026-09-07..2026-10-05; all report JPY and latest complete period 2026-10-03. Anicca iOS MRR was JPY 3,196.91, the other five were 0.0, and the six-app sum was JPY 3,196.91. This is an MRR stock metric, not settlement or bank proceeds. `collect_revenuecat` omits top-level `currency`/`revenue_definition` required by `capafy_mobile.py`'s exact MRR contract, so the current row cannot flow into B7 until the source contract is fixed (§87-AT). No raw app IDs, credentials, or payloads were persisted; no ledger write or send occurred.
- Natural-owner status (06:35 JST): read-only `lm-loop status` reports local CFO latest 05:57 and cloud Financial Report latest 06:33; both are exit 75 / `resource_capacity_busy`, `effect=not_applicable`, with no provider receipt. Installed main SHA is `82d31995…`. The separate local 04:02 `effect=unknown` remains unresolved. No retry/restart/wake; do not replay. These status rows do not prove daily delivery.
- Main was not merged or changed. The mobile candidate worktree remains outside this task and must not be edited because its lease/HEAD is mismatched. Worktree was clean at snapshot commit.

## Remaining order

1. §87-J item 5: close source freshness/coverage and official ownership for Moneytree, mobile/ASC/RevenueCat, Stripe, Capafy, and other revenue/cost rails. Fix the `collect_revenuecat` → `capafy_mobile.py` currency/revenue-definition contract before expecting this MRR readback in B7; keep it separate from settled revenue. Stripe remains unknown until the Product Loop mapping is official.
2. Item 6: reconcile the official Google Cost Table by period/project/tenant/loop; repair the cross-month Cloud Storage row; measure actual API/fallback/alternative cost and UX.
3. Item 7: resolve the main-derived promotion path; verify a natural local report with durable provider/delivery receipt and same-period replay-zero; retire the cloud duplicate only afterward.
4. Item 8: observe seven consecutive same-period reports with freshness, coverage, cost, fallback, and delivery evidence.

First safe resume action: fetch and verify this branch/worktree/runtime; continue item 5 with the local RevenueCat contract gap: `collect_revenuecat` omits top-level `currency` and `revenue_definition` required by `capafy_mobile.py` before B7 can carry the MRR snapshot. Preserve the exact `mrr`/`active_paid_subscriptions`/`monthly` definition and do not treat it as settled revenue. Then continue the official Stripe product/loop crosswalk and Moneytree freshness/expense coverage. The §87-AR Session readback does not resolve Stripe ownership. Do not change production configuration or retry the unresolved 04:02 effect.

## Short restart prompt

Read this handover, SSOT §87-J/§87-AQ/§87-AR/§87-AS/§87-AT, and the design spec. Fetch and verify the current branch tip and runtime state, then continue item 5 serially. Keep unknowns explicit, do not create a CLI, do not edit main/mobile worktrees, and push the same candidate branch without merging.

## User-sendable /goal

```
/goal Life Manager gives Dais a daily, receipt-backed personal/business CFO report with a provider-fresh MUFG balance; source-attributed settled revenue, refunds, fees, subscriptions, personal/business expenses; and actual provider/cloud costs. Keep stale, estimated, incomplete, and unknown separate from zero; keep B7 outside FinancialRecord totals until non-duplication is reconciled. Done requires SSOT §87-J items 5–8 proved, one natural main-derived report with durable source/delivery receipt and same-period replay-zero, then seven consecutive same-period reports with freshness, coverage, cost, fallback, and no unresolved effects. First read this handover, SSOT §87-AR/§87-AS/§87-AT, and design spec; fetch and verify branch, HEAD, upstream, dirty state, and runtime. Continue the first open item and update the spec as evidence changes. Do not create a CLI, guess product/owner attribution, infer Stripe ownership from category/owner/name alone, or replay an unresolved effect. Use repo /Users/anicca/Projects/life-manager-main, worktree /Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002, branch docs/lm-cfo-cost-observability-spec-20261002 tracking origin/docs/lm-cfo-cost-observability-spec-20261002; verified base before this docs refresh: a9203cafd6ebaa5348d53d0a44003a21e65d07b2. Assign spec/source writes only to this branch; reviewers use a detached read-only snapshot; never edit the shared main or mobile candidate worktree. Push meaningful changes; do not merge before all acceptance passes. Use gpt-6.1-sol/medium for planning/review and gpt-6-luna/max for implementation. When independent high-risk evidence review changes Done, use one non-overlapping read-only spawn_agent reviewer; the user must send this /goal line to launch it. Report blocked only when no safe source/readback path remains.
```
