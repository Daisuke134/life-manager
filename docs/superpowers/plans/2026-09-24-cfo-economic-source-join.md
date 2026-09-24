# CFO Economic Source Join Implementation Plan

**Goal:** Make every one of the fourteen Product Loops declare its economic role and official funnel/revenue/cost sources, then join verified sources into the existing CFO and LM-EAB contracts without treating activity, estimates, fundraising, unrealized value, missing data or payouts as MRR.

**Architecture:** Extend the existing Product Loop catalog rather than create another loop registry. A shared exact economic-source contract classifies each loop, reports missing/unobserved/unavailable inputs explicitly, and feeds the existing immutable `FinancialRecord` store plus LM-EAB attribution/cost coverage. Provider adapters remain thin; CFO and LM-EAB remain the only aggregation and economic-score authorities.

**Scope boundary:** Do not modify or operate Coconala/CrowdWorks/Lancers/Upwork Paid fulfillment code, state, owners, sessions, effects or `config/loop-registry.json` Paid rows. Marketplace integration consumes only official receipts produced by that owner after they exist.

**Current status:** Task 1 is complete on branch commit `13ab24a9a4`. The catalog loader covers all fourteen
loops and fails closed on malformed economic roles, source declarations and fundraising classification.
Focused Product Loop tests pass 39/39; the runtime catalog tests pass 19/19; `lm-loop-contract` reports
14 loops, 167 jobs and zero errors. Current cursor: Task 2, the official funnel/source join contract.

## Task 1 — Freeze the fourteen-loop economic source inventory

Status: complete.

- Add an exact `economic` declaration to all fourteen entries in `apps/life-manager/config/product-loop-catalog.json`.
- Validate closed roles, revenue classes and source declarations in `product-onboarding.js`.
- Require every revenue-capable loop to declare funnel, financial and cost sources; allow explicit `not_applicable` only for non-economic/aggregator roles.
- Add contract tests proving all fourteen loops are covered once, unsupported fields fail closed, fundraising is never customer MRR, and missing adapters stay visible.

## Task 2 — Add the official funnel/source join contract

- Add exact immutable records for per-loop source observation and funnel stage evidence.
- Join records only by stable loop/subject/receipt IDs and evidence refs.
- Preserve `unknown`, `not_configured`, `unavailable`, `empty` and `observed_verified` as different states.
- Never turn a missing count into zero or an estimated amount into a settled `FinancialRecord`.

## Task 3 — Expose economic source coverage through CFO

- Extend `ingestFinancialRecords` to return per-loop source coverage alongside the existing source summary.
- Extend CFO report data with private, redacted coverage; do not add routine Telegram noise.
- Fail a complete LM-EAB episode when a required cost or official revenue source is absent.

## Task 4 — Connect existing read-only receipt producers one by one

1. Agent Economy/x402 revenue and compute costs.
2. Affiliate placement funnel, approved/paid commission and actual cash costs.
3. Mobile/RevenueCat funnel plus App Store settlement; RevenueCat estimates remain non-settled.
4. Capafy official seller earnings/refunds/payout state; unknown active subscriptions remain unknown MRR.
5. Life Manager/Stripe subscription settlement and payment fees.
6. Investment realized gains/losses only; paper/shadow/unrealized values never become revenue.
7. Writer official publisher/payment receipts.
8. Fundraiser receipts classified as financing, never customer revenue or MRR.
9. Marketplace receipts from the existing shared marketplace projection, read-only with respect to the separate Paid owner.

Each adapter gets a deterministic fixture, replay-zero assertion and explicit unsupported/missing state before the next adapter starts.

## Task 5 — Join CFO output to LM-EAB and self-improvement

- Produce LM-EAB attribution and cost-coverage records from the verified CFO join.
- Select the earliest measurable funnel loss per loop.
- Permit candidate promotion only after held-out evaluation, bounded live canary, official settlement/readback and rollback/replay-zero.

## Task 6 — Acceptance

- Focused unit and contract tests pass.
- `lm-loop-contract` still reports fourteen loops and zero errors.
- All economically relevant loops appear in CFO coverage, including missing/unavailable ones.
- No Paid fulfillment implementation or runtime owner changed.
- A read-only production pass proves source coverage without sending, applying, purchasing, restarting or claiming revenue.
- Update the architecture spec with exact evidence and advance §J4.2 to item 3 only when every required source is either officially joined or explicitly incapable/not-applicable by contract.
