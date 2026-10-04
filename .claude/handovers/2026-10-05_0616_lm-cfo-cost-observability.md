# Life Manager CFO handover

Snapshot commit: `88735d9cc863205911ac0f38fd3c9ca10946b16a` (pushed; fetch and verify before editing)

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
- Natural-owner status (06:02 JST): local CFO latest 05:57 and cloud Financial Report latest 06:02 are pre-effect capacity-deferred, no provider receipt, installed main SHA `82d31995…`. Separate local 04:02 `effect=unknown` remains unresolved. No retry/restart/wake; do not replay.
- Main was not merged or changed. The mobile candidate worktree remains outside this task and must not be edited because its lease/HEAD is mismatched. Worktree was clean at snapshot commit.

## Remaining order

1. §87-J item 5: close source freshness/coverage and official ownership for Moneytree, mobile/ASC/RevenueCat, Stripe, Capafy, and other revenue/cost rails. Stripe remains unknown until the Product Loop mapping is official.
2. Item 6: reconcile the official Google Cost Table by period/project/tenant/loop; repair the cross-month Cloud Storage row; measure actual API/fallback/alternative cost and UX.
3. Item 7: resolve the main-derived promotion path; verify a natural local report with durable provider/delivery receipt and same-period replay-zero; retire the cloud duplicate only afterward.
4. Item 8: observe seven consecutive same-period reports with freshness, coverage, cost, fallback, and delivery evidence.

First safe resume action: fetch and verify this branch/worktree/runtime; continue item 5 from the official Stripe product/owner crosswalk and the remaining financial-source coverage. Do not change production configuration or retry the unresolved 04:02 effect.

## Short restart prompt

Read this handover, SSOT §87-J, and the design spec. Verify current Git/runtime facts, then continue item 5 serially. Keep unknowns explicit, do not create a CLI, do not edit main/mobile worktrees, and push the same candidate branch without merging.

## User-sendable /goal

```
/goal Life Manager gives Dais a daily, receipt-backed personal/business CFO report with a provider-fresh MUFG balance; source-attributed settled revenue, refunds, fees, subscriptions, personal/business expenses; and actual provider/cloud costs. Stale, estimated, incomplete, and unknown values stay separate and never become zero; B7 remains separate from FinancialRecord totals until reconciliation proves non-duplication. Done requires current SSOT §87-J items 5–8 proved, one natural main-derived report with durable source/delivery receipt and same-period replay-zero, then seven consecutive same-period periods with freshness, coverage, cost, fallback, and no unresolved effects. First read this handover, SSOT, and design spec; verify current branch, HEAD, upstream, dirty state, and runtime. Continue the first open item serially and update the spec as evidence changes. Never create a CLI, guess product/owner attribution, infer Stripe ownership from category/owner/name alone, or replay an unresolved effect. Work only in repo /Users/anicca/Projects/life-manager-main, worktree /Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002, branch docs/lm-cfo-cost-observability-spec-20261002 tracking origin/docs/lm-cfo-cost-observability-spec-20261002, snapshot commit 88735d9cc863205911ac0f38fd3c9ca10946b16a. Never edit the shared main worktree or mobile candidate worktree. Push meaningful changes; do not merge before all acceptance passes. Use gpt-6.1-sol/medium for planning/review and gpt-6-luna/max for implementation. Use spawn_agent only for non-overlapping implementation or fresh read-only financial review after this user-sent /goal. Keep working through safe source alternatives; report blocked only when no safe path remains.
```

