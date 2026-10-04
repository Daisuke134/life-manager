# Life Manager CFO handover

- Snapshot commit: `047eb0e7c07b5521c389dcee8ef9473990357b4f` (pushed; verify current remote state before editing)
- Repository: `/Users/anicca/Projects/life-manager-main`
- Worktree: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002`
- Branch/upstream: `docs/lm-cfo-cost-observability-spec-20261002` / `origin/docs/lm-cfo-cost-observability-spec-20261002`
- Spec/TODO SSOT: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002/docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`, §87-J items 5→6→7→8. Current cursor: item 5.
- Evidence: `/Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002/docs/evidence/cfo/2026-10-05-cfo-live-observability-readback.md`.

## Verified snapshot

- Candidate B7 now ignores the account-wide Stripe default; the regression and focused CFO tests pass (46/46, 268/268). Independent financial-document review passed after correcting stale time-scoped text.
- Candidate direct B7 projection at 05:15 JST: historical/trailing gaps 135/130; all 14 loops, self-build, and runway unknown. This is candidate-only, not a production/natural report, and is not company-wide zero or replay-zero.
- Host runtime env no longer has the unsafe Stripe default line; mode 600 and live-readback flag remain. No restart/wake was performed; installed main SHA remains `82d31995…`.
- Fresh 05:21 JST status: cloud Financial Report was pre-effect capacity-deferred with no receipt; local CFO remained deferred at 04:57. A separate 04:02 local occurrence remains `effect=unknown`; do not retry/replay it without official readback.
- This task did not merge into or modify main. The mobile candidate worktree remains outside this task and must not be edited because its owner/lease HEAD is mismatched.

## Remaining order

1. §87-J item 5: complete source freshness/coverage and attribution for Moneytree, mobile/ASC/RevenueCat, Stripe owner/product crosswalk and FinancialRecord persistence, Capafy seller order/refund/fee/payout joins, and all actual subscription/tool/cloud costs. Keep unsupported totals unknown.
2. Item 6: reconcile official Google Cost Table/CSV to actual usage by billing period/project/tenant/loop; fix the split-month Cloud Storage parser case; measure remaining Google calls, OpenPOI/routing fallbacks, UX quality, and actual cost on one period.
3. Item 7: resolve the formal main-derived promotion route; verify one natural local daily report with provider/delivery receipt, source freshness/coverage, and same-period replay-zero; retire the legacy cloud duplicate only after local receipt evidence. Do not add a new CLI, tenant binding, enqueue endpoint, or database credential.
4. Item 8: after prior items pass, observe seven consecutive same-period daily reports for freshness, coverage, receipts, cost, fallback, and replay-zero.

First safe resume action: verify remote branch/HEAD, dirty state, and current natural/provider readbacks; then continue item 5 from the official product/owner crosswalk and source-completeness gaps.

## Short restart prompt

Read this handover and SSOT §87-J, verify branch/runtime facts, and continue item 5 first. Work serially, keep unknowns explicit, do not create a CLI, do not edit main/mobile worktrees, and update/push the same spec as evidence changes.

## User-sendable /goal

```
/goal Life Manager CFO gives Dais a daily report with MUFG's current provider-fresh balance and attributable settled revenue, refunds, fees, subscriptions, and actual tool/cloud costs across income and spending streams; estimated, stale, incomplete, and unknown values stay visibly separate. Done means existing SSOT §87-J items 5–8 pass: source-complete, per-loop B7 records with official receipt/owner attribution; Google invoice-to-usage actual-cost reconciliation and measured alternative-routing UX/cost; one main-derived natural daily report with official delivery/source receipts and same-period replay-zero after the promotion path is resolved; then seven consecutive days of same-period freshness, coverage, cost, fallback, and delivery evidence. First read this handover and the spec, then verify branch, HEAD, upstream, dirty state, and current runtime/provider state. Continue the first open §87-J item serially and keep the spec current. Do not create a CLI, guess product ownership, represent estimates as actuals or missing values as zero, replay an unresolved effect, or merge before all acceptance criteria pass. Work only in repo /Users/anicca/Projects/life-manager-main, worktree /Users/anicca/Projects/life-manager-main/.worktrees/lm-cfo-cost-observability-20261002, branch docs/lm-cfo-cost-observability-spec-20261002 tracking origin/docs/lm-cfo-cost-observability-spec-20261002, snapshot commit 047eb0e7c07b5521c389dcee8ef9473990357b4f. Never edit the shared main worktree or mobile candidate worktree. Fetch and verify HEAD/upstream/dirty state before editing; push each meaningful change. Use gpt-6.1-sol/medium for planning/review and gpt-6-luna/max for implementation. Use spawn_agent only for non-overlapping implementation or independent read-only financial review after this user-sent /goal. Keep source gaps explicitly unknown and continue safe evidence work; report blocked only after available safe source/readback paths are exhausted.
```
