# Investment Loop Generational Wealth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current fragmented investment paths into a receipt-verified, fee/model-cost-net portfolio loop that can scale one measured capital step at a time toward `$10,000` realised net trading profit per month, while treating generational wealth as a separate capital-accumulation problem rather than promising returns.

**Architecture:** Keep each venue as an effect owner: Alpaca owns Alpaca orders, Hyperliquid owns Hyperliquid deposits/orders, and Solana owns Solana transactions. Add one read-only portfolio evidence spine that normalises official receipts, subtracts every known cost exactly once, rejects unknown evidence, reports the gap to the target, and gates capital expansion. A separate treasury/cash engine records owner deposits, product revenue, investment P&L, costs, and reserves so owner cash flow is never mistaken for profit.

**Tech Stack:** Existing Python investment core and `unittest` suites; Alpaca CLI and official account/activity/order readbacks; Hyperliquid Python SDK and `/info` API; Solana RPC plus Jupiter quote/swap receipts; append-only JSONL state; existing Telegram outbox; existing loop registry owned by lm-lead.

**Spec:** `docs/superpowers/specs/2026-09-01-alpaca-money-maximizer-design.md` §7.3 and §8 L18; `docs/superpowers/plans/2026-09-27-hyperliquid-carry-live-loop.md`; `docs/superpowers/plans/2026-09-27-solana-memecoin-copy-trading.md`; `docs/superpowers/plans/2026-09-27-cross-venue-capital-allocator-net-pnl.md`.

## Global Constraints

- `$10,000/month` means official realised net trading P&L after fees, funding/borrow, slippage, gas, and model cost; paper P&L, unrealised P&L, deposits, projections, and subscription MRR do not count.
- No capital expansion while `measurement_status != measured`, net P&L is non-positive, any cost component is unknown, any receipt is missing, or a safety breach exists.
- Current Alpaca cap remains `$100` allocated capital, `$10` maximum loss per trade, `$20` daily loss halt until a later approved ladder step is proven.
- Current Hyperliquid leg cap remains `$25`, one delta-neutral position, day-loss cap `5%`, drawdown cap `20%`; a funded wallet does not imply live enablement.
- Solana begins read-only scout → paper replay → exactly one `$2.00` live canary with a hard cumulative `$3.00` ceiling; no user credential or target-wallet private key enters the repo.
- Owner deposits and withdrawals are principal cash flow, never investment revenue; each venue's official receipt IDs are required for attribution.
- Every live effect is journaled before submission, reconciled by official provider state, and made retry-safe; `effect_unknown` blocks new effects.
- The loop never increases risk, leverage, cap, or destination from a Telegram message; registry/runtime changes are requested from lm-lead through the owner path.
- Use no new scheduler, generic strategy framework, second ledger, or dashboard until an existing boundary cannot satisfy the acceptance test.

## Review Focus

- **Deposit mistaken for profit:** a `$50` owner transfer must increase principal and not net P&L; test positive and negative owner cash flow.
- **Unknown cost treated as zero:** missing funding, fee, gas, slippage, or model-cost receipt must produce `partial`/`blocked`, never a profitable number.
- **Cross-venue duplicate attribution:** one provider receipt ID or one cost line cannot be counted in two venue rows or in both venue and aggregate totals.
- **Stale or non-authoritative provider data:** an old quote, paper receipt, UI projection, or incomplete API response must exclude the candidate from allocation.
- **Capital ladder bypass:** a positive paper result, one lucky fill, or a projection cannot raise a cap; the next cap requires the named live sample, risk gates, and explicit owner/lm-lead promotion receipt.

## As-Is Evidence

The current state is now one measured, fail-closed evidence layer, but it is
not yet a profitable or fully funded investment machine:

```mermaid
flowchart LR
    Owner["Dais / existing capital\nno new transfer"] --> Alpaca["Alpaca live loop\ncap $100"]
    Owner --> HL["Hyperliquid wallet\nunfunded"]
    Owner --> Sol["Solana staged loop\nread-only default"]

    Alpaca --> AReceipt["Official receipts\n1 measured round trip"]
    AReceipt --> APerf["net P&L -$0.04\ncapital expansion false"]
    HL --> HLWait["deposit.py: wait\nUSDC 0 / ETH 0"]
    Sol --> SolScout["scout_unknown\n0 candidates / no effect"]

    APerf --> Allocator["read-only cross-venue\nallocator / daily report"]
    HLWait --> Allocator
    SolScout --> Allocator
    CFO["CFO receipt table\npartial / USD bridge 0"] --> Treasury
    Allocator --> Treasury["treasury rollup\npartial / fail closed"]
    Treasury --> Target["$10k/month\nnot achieved / no promotion"]
```

### Verified repo/runtime facts

- `skills/alpaca-investment/performance.py` reports `capital_expansion_allowed: false`, requires at least `30` round trips for statistical support, and hard-caps the current performance gate at `$100`.
- The retained Alpaca live receipt reports one completed round trip with fee-inclusive net P&L `-$0.006970681885`; the sealed performance projection reports net `-$0.04`, realised `-$0.01`, unrealised `-$0.03`, fees `$0.01`, and `statistically_supported: false`.
- The current Alpaca readback has equity about `$66.60`, no trade allocation, and a `USDCUSD` holding; this is account state, not revenue.
- Hyperliquid carry code and tests are merged, but the registry row/runtime lock was owner-requested rather than directly changed by this lane; the current agent wallet readback is USDC `0` / ETH `0`, with no `userFunding`, deposit transaction, entry receipt, or daily P&L.
- The Solana loop is implemented through staged read-only/paper/live-gate boundaries. A fresh public-target scout returned `scout_unknown`, `0` candidates, `20` evidence rows, and no effect; no live transaction receipt exists.
- The cross-venue allocator/reporter and treasury rollup are implemented as read-only code. The acceptance fixture measures aggregate net `$8.70` with owner cash flow `$100.00`, but it is test evidence, not revenue; live provider inputs remain partial and `capital_expansion_allowed` stays `false`.
- The existing CFO producer can read Alpaca, Stripe, x402, marketplace, Capafy, mobile-app, and usage sources. Its fresh `2026-09-28` run has no USD customer-revenue receipts, a missing Stripe live credential, two missing marketplace payment ledgers, and `USD_API_EQUIV` estimates that are not provider bills; the new bridge keeps that state partial instead of claiming a measured cash surplus.
- The Task 8 bridge replayed that same table as `evidence_status=partial`: `0` USD treasury receipts, `20` missing-source records, `7` excluded non-USD/API-estimate records, `15` explicit zero observations, and no investment-row leakage into customer cash. This is a measurement result, not a revenue result.

## Target Economics

These are planning calculations, not forecasts:

| Target | Required net capital at 10% APR | at 15% APR | at 20% APR |
|---|---:|---:|---:|
| `$10,000/month` net (`$120,000/year`) | `$1.20M` | `$800k` | `$600k` |
| `$1,000/month` net | `$120k` | `$80k` | `$60k` |

The current `$100` Alpaca cap at a hypothetical 10% net annual return produces about `$0.83/month`; a `$24` Hyperliquid leg at the plan's measured 11% APR produces about `$0.22/month` gross before variable funding and fees. Therefore the path to generational wealth must combine a measured investment engine with a cash-generation engine and recurring contributions. The investment loop alone cannot turn `$100` into `$10k/month` without assuming an unsafe, unmeasured return.

## To-Be Architecture

```mermaid
flowchart TD
    Cash["Cash engine\nproduct / agent / affiliate revenue"] --> CFO["CFO source adapters\nreceipts / missing evidence"]
    CFO --> Treasury["Treasury ledger\nprincipal, revenue, costs, reserves"]
    Owner["Owner deposits\nexplicit principal"] --> Treasury
    Treasury --> Allocator["Read-only capital allocator\nfree cash + caps + evidence"]

    Allocator --> Alpaca["Alpaca\nsmallest defined-risk effect"]
    Allocator --> Carry["Hyperliquid\nspot long + perp short"]
    Allocator --> Solana["Solana\nverified copy canary"]

    Alpaca -->|official fills, fees, cash flow| Receipts["Canonical receipt adapters"]
    Carry -->|clearinghouse, userFunding, deposits| Receipts
    Solana -->|signature, token delta, gas| Receipts
    Receipts --> Net["Fee/model-cost-net P&L\nunknown blocks ranking"]
    Net --> Gates{"Promotion gates"}
    Gates -->|negative / unknown / breach| Hold["HOLD / halt / reconcile"]
    Gates -->|measured positive sample| Ladder["One approved capital step"]
    Ladder --> Treasury
    Net --> Report["Daily Telegram report\nactual, target gap, evidence IDs"]
    Report --> Owner
```

### Promotion ladder

| Stage | Capital boundary | Required evidence | Allowed action |
|---|---:|---|---|
| S0 | `$0–100` | current receipts, no unknowns, baseline reports | measure only; no expansion |
| S1 | `$100–1,000` | at least `30` completed live round trips per venue, positive net after every cost, no risk breach, and no `unknown` evidence | explicit cap promotion; one venue at a time |
| S2 | `$1,000–10,000` | 90-day rolling positive net, drawdown within policy, venue concentration and liquidity checks | add a second verified venue |
| S3 | `$10,000–100,000` | 6–12 months positive net, stress/replay evidence, tax/reserve accounting, operational owner review | measured diversification and treasury contributions |
| S4 | `$100,000–600,000+` | audited monthly receipts, stable net APR, external custody/legal/tax review, no single-strategy dependency | pursue `$10k/month` target |

No stage is automatic. A stage recommendation is data; a stage promotion is a separately recorded owner-approved capital boundary.

---

### Task 1: Canonical multi-venue receipt and net-P&L spine

**Files:**
- Create: `apps/life-manager/investment-core/portfolio_receipts.py`
- Create: `apps/life-manager/investment-core/portfolio_performance.py`
- Test: `apps/life-manager/investment-core/test_portfolio_performance.py`
- Modify: `apps/life-manager/investment-core/performance.py` only where the common schema can be reused without changing Alpaca's accepted receipt contract
- Parity check: `skills/alpaca-investment/` remains byte-equivalent where it is a release copy; do not silently update one copy only

**Interfaces:**
- Consumes: venue-specific official receipt readers and owner cash-flow records.
- Produces: `VenueSnapshot` with `venue`, `observed_at`, `equity_usd`, `free_cash_usd`, `gross_pnl_usd`, `trading_fees_usd`, `funding_or_borrow_usd`, `slippage_usd`, `gas_usd`, `model_cost_usd`, `source_receipt_ids`, `risk`, and `measurement_status`; `aggregate(snapshots, owner_cash_flow_usd) -> dict`.

- [x] **Step 1: Write failing tests** for owner deposits excluded from P&L, exact `net_pnl = gross - trading_fees - funding_or_borrow - slippage - gas - model_cost`, duplicate receipt rejection, missing-cost blocking, stale snapshot exclusion, and cross-venue source ID uniqueness.
- [x] **Step 2: Run the focused test** with `cd apps/life-manager/investment-core && python3 -m unittest test_portfolio_performance`; the expected missing-adapter `ModuleNotFoundError` was observed.
- [x] **Step 3: Implement the pure schema/aggregate boundary** without provider submit/signing imports; preserve unknown fields as blocked evidence, never as zero.
- [x] **Step 4: Run focused tests and existing `skills/alpaca-investment/test_performance.py`**; new tests pass `6/6`, existing performance tests pass `7/7`, and the complete investment suite passes `139/139`.
- [x] **Step 5: Commit** `feat(investment): add canonical fee-model-cost net pnl spine` (`fa710b6310`); focused task-done verification records `6/6` passing.

### Task 2: Hyperliquid funded canary and verified carry evidence

**Files:**
- Reuse: `skills/earn/hyperliquid-carry/{deposit.py,run.py,market.py,ledger.py,execute.py}`
- Reuse tests: `skills/earn/hyperliquid-carry/test_hyperliquid_carry.py`
- Operational owner path: `config/loop-registry.json` and production runtime, owned by lm-lead; do not edit directly in this lane

**Interfaces:**
- Consumes: agent-wallet Arbitrum deposit and Hyperliquid official `/info` responses.
- Produces: verified deposit receipt, `clearinghouseState`, `userFunding`, entry/exit receipts, and a venue snapshot for Task 1.

- [ ] **Step 1: Obtain lm-lead readback** for registry row `hyperliquid-carry`, cadence `3600s`, `HL_CARRY_LIVE=1`, `HL_CARRY_MAX_LEG_USD=25`, state root, daily `deposit.py` wake, and locked SDK install. Read-only repo/runtime evidence currently shows no `hyperliquid-carry` registry row; an explicit readback request was sent to `lm-lead`, with no reply yet. This is not treated as live enablement.
- [x] **Step 2: Re-run deposit preflight without live env** and verify the exact Arbitrum address, native USDC token, ETH gas balance, and no pending `effect_unknown` deposit before any send. Result: wallet `0xA428…9302`, USDC `0`, ETH `0`, action `wait/usdc_below_bridge_minimum`, no journal/pending deposit.
- [ ] **Step 3: After owner funding, reconcile the Arbitrum tx** through provider receipt and Hyperliquid `userNonFundingLedgerUpdates`; record the tx hash and credited amount as principal, not profit.
- [ ] **Step 4: Run one smallest delta-neutral entry/exit canary** only after equity, market, and risk gates pass; read back `clearinghouseState`, fills, and `userFunding`.
- [ ] **Step 5: Require 14 days of daily net evidence** before any additional capital; report gross funding, trading fees, bridge/gas, slippage, and net separately.
- [ ] **Step 6: Commit only documentation/evidence updates** if code remains unchanged; runtime/registry mutation is lm-lead's owner action.

### Task 3: Alpaca capital-ladder promotion gate

**Files:**
- Create: `apps/life-manager/investment-core/capital_ladder.py`
- Modify: `apps/life-manager/investment-core/performance_gate.py`
- Modify: `apps/life-manager/investment-core/risk_policy.py`
- Mirror after parity review: `skills/alpaca-investment/capital_ladder.py`, `skills/alpaca-investment/test_capital_ladder.py`
- Reference: `skills/alpaca-investment/{performance.py,performance_gate.py,test_performance.py}`

**Interfaces:**
- Consumes: official measured net-P&L receipt, round-trip count, drawdown, current cap, explicit approved next cap, and venue health.
- Produces: `recommend_next_cap(evidence, current_cap, requested_cap) -> {status: "hold"|"recommend"|"reject", current_cap_usd, next_cap_usd, reasons, evidence_ids}`. It never submits an order or changes the cap itself.

- [x] **Step 1: Write failing tests** proving current negative/one-round-trip evidence rejects expansion, paper evidence rejects expansion, unknown cost rejects expansion, and a positive fixture with `round_trips >= 30` recommends only the next discrete cap. Added a regression for a missing unknown-cost vector.
- [x] **Step 2: Implement the pure ladder** with exact caps `$100 → $1,000 → $10,000 → $100,000`; require an explicit requested cap and preserve the existing `$10` trade / `$20` daily loss gates until a separately approved risk revision exists.
- [x] **Step 3: Add receipt-backed promotion evidence** to the Telegram/report schema without exposing secrets or allowing a message to authorize promotion. The report is recommendation-only and always requires owner authorization.
- [x] **Step 4: Run `cd skills/alpaca-investment && python3 -m unittest test_performance test_capital_ladder test_risk_policy` plus the existing investment suite, then run the app/skill parity check.** Focused tests pass `25/25`, app tests pass `3/3`, full investment discovery passes `147/147`, and parity is clean.
- [x] **Step 5: Commit** `feat(investment): gate capital ladder by measured net pnl` (`3e6c81970d`).

### Task 4: Solana read-only scout → paper → `$2–3` canary

**Files:**
- Implement the existing plan: `docs/superpowers/plans/2026-09-27-solana-memecoin-copy-trading.md`
- Create under that plan: `skills/earn/solana-memecoin-copytrade/`
- Reuse verified swap pattern: `skills/earn/sol-trade/lib/record-swap.mjs`

**Interfaces:**
- Consumes: public target-wallet RPC history, GMGN/DexScreener metadata, Jupiter quotes, and Solana confirmed transaction receipts.
- Produces: public-wallet `scout_unknown|ok`, paper receipts, and one on-chain-verified canary receipt with source signature, token delta, fee, slippage, and final balance.

- [x] **Step 1: Write tests** for transfer-vs-swap discrimination, provider disagreement, stale/illiquid quote, duplicate source signature, mismatched token delta, and failed transaction fee accounting; nested suite covers these boundaries.
- [x] **Step 2: Implement read-only scout and deterministic paper policy**; no signing path is imported by scout/paper mode.
- [x] **Step 3: Run one public-target read-only scout** and save evidence without target-wallet secrets; result is `scout_unknown`, `0` candidates, `20` evidence rows, effect `none`, with sanitized evidence outside the repo.
- [x] **Step 4: Implement the staged paper wake**; no paper return is used as capital-expansion evidence and the mode never promotes itself.
- [ ] **Step 5: Run exactly one `$2.00` live canary with a hard `$3.00` cumulative ceiling** only after explicit owner funding and all RPC receipt checks pass; this remains open because no funding/owner receipt exists.
- [x] **Step 6: Run each focused `node --test` command named in `docs/superpowers/plans/2026-09-27-solana-memecoin-copy-trading.md` and obtain a fresh read-only review before any second canary.** Nested suite passes `28/28`; no live transaction was sent.

### Task 5: Cross-venue allocator and daily target-gap report

**Files:**
- Implement the existing plan: `docs/superpowers/plans/2026-09-27-cross-venue-capital-allocator-net-pnl.md`
- Reuse: `apps/life-manager/investment-core/allocator.py`, `performance.py`, `reporter.py`, `telegram_outbox.py`
- Tests: the plan's `test_venue_snapshots`, `test_aggregate`, `test_allocator`, and `test_reporter` files

**Interfaces:**
- Consumes: Task 1 venue snapshots, free cash, risk caps, stale/unknown state, and target `$10,000/month`.
- Produces: `rank(...) -> allocate|hold|halt`, daily aggregate receipt, `rolling_30d_net_pnl_usd`, `target_gap_usd`, `capital_expansion_allowed`, and source receipt IDs.

- [x] **Step 1: Add failing tests** for positive net vs unknown-cost candidates, owner cash-flow adjustment, stale venue exclusion, drawdown halt, deterministic tie-breaks, duplicate daily report, and target-gap accuracy. Cross-venue nested plan tests cover these boundaries.
- [x] **Step 2: Implement read-only ranking**; the allocator must not import or call venue submit/signing functions.
- [x] **Step 3: Implement one UTC-daily report** through the existing idempotent Telegram outbox; unknown values render `不明`, never zero. Missing owner/runtime or provider receipts remain explicit.
- [x] **Step 4: Run focused tests, existing investment tests, and replay-zero checks**; prove the allocator cannot create a second order or reinterpret a deposit as revenue. Cross-venue acceptance/report suite passes `26/26`.
- [x] **Step 5: Commit** `feat(investment): rank verified cross-venue net returns` via nested implementation commits through `d48e355e7b`.

### Task 6: Treasury and generational-wealth cash engine

**Files:**
- Create: `apps/life-manager/investment-core/treasury.py`
- Create: `apps/life-manager/investment-core/test_treasury.py`
- Modify: `apps/life-manager/config/product-loop-catalog.json` only through the normal owner/release path if a new economic source is actually wired
- Reference: existing agent-economy, affiliate, and investment financial adapters

**Interfaces:**
- Consumes: official customer-revenue receipts, owner cash-flow receipts, venue net-P&L receipts, model/API cost receipts, and reserve policy.
- Produces: `treasury_snapshot(period) -> {customer_revenue_usd, investment_net_pnl_usd, owner_cash_flow_usd, model_cost_usd, tax_reserve_usd, investable_surplus_usd, investment_net_pnl_target_gap_usd, treasury_surplus_target_gap_usd, evidence_status}`.

- [x] **Step 1: Write tests** for principal/revenue/P&L separation, missing cost evidence, duplicate receipt IDs, reserve calculation, separate target gaps, and negative investable surplus; focused tests pass `5/5`.
- [x] **Step 2: Implement a read-only treasury rollup**; it never transfers funds and never counts projected investment return as cash.
- [x] **Step 3: Connect only existing receipt producers**; currently no complete product financial adapter is available in this lane, so missing categories remain visible as `partial` and `product-loop-catalog.json` is unchanged.
- [x] **Step 4: Report two separate targets:** investment net P&L target `$10k/month` and optional treasury surplus target; owner cash flow and customer revenue are not merged with trading P&L.
- [x] **Step 5: Commit** `feat(investment): separate treasury cash from investment pnl`.

### Task 7: Acceptance, promotion, and $10k/month scoreboard

**Files:**
- Review only: `docs/superpowers/specs/2026-09-01-alpaca-money-maximizer-design.md` L18 remains unchanged because the target evidence threshold is not met
- Modify: `docs/superpowers/plans/2026-09-28-investment-loop-generational-wealth.md` with the current cursor and receipts
- Test/replay: all venue focused suites, loop contract, natural wake, provider readbacks

- [x] **Step 1: Record S0 baseline**: Alpaca has one closed official round trip at `-$0.006970681885` and sealed projection `-$0.04`; Hyperliquid is unfunded with USDC/ETH `0`; Solana is implemented but its read-only scout is `scout_unknown` with `0` candidates and no effect; cross-venue and treasury are read-only with incomplete live receipts. No capital promotion.
- [x] **Step 2: Audit canary closure status**: Alpaca's entry/exit/fee receipt is closed; Hyperliquid has no funded entry/exit; Solana has no live canary; missing funding/gas/model-cost/customer-revenue inputs remain explicit and are not converted to zero.
- [x] **Step 3: Evaluate the positive-month gate**: no official rolling monthly receipt reports `net_pnl_usd >= 10000`; S1 is withheld and one negative round trip cannot recommend expansion.
- [x] **Step 4: Evaluate discrete-cap promotion**: no venue has the required positive, cost-complete, sample-qualified evidence or owner/lm-lead promotion receipt; current caps remain held with rollback/hold behavior.
- [x] **Step 5: Evaluate the target claim**: `$10k/month` is not achieved, and generational wealth is not claimed because the treasury/net-worth ledger has no complete verified source set. L18 remains unchanged.
- [x] **Step 6: Run the final verification package**: pre-Task-8 core `34/34`, Alpaca discovery `147/147`, Hyperliquid `69/69`, Solana `28/28`, provider read-only preflights, staged natural wakes/replay-zero, and diff checks pass for the implemented/read-only boundary. The shared loop-contract gate reports one pre-existing unrelated Capafy declaration mismatch (`read_only_external_owner` missing from `loops[12].recovery_classes`); investment files do not change the catalog, and effect-dependent canaries remain open.

### Task 8: Bridge existing CFO receipts into treasury

**Files:**
- Create: `apps/life-manager/investment-core/cfo_receipts.py`
- Create: `apps/life-manager/investment-core/test_cfo_receipts.py`
- Modify: `apps/life-manager/investment-core/treasury.py` and `apps/life-manager/investment-core/test_treasury.py` to keep customer refunds and operating costs separate from model costs
- Modify: `apps/life-manager/investment-core/README.md` with the adapter contract
- Reference only: `skills/cfo/loop_pnl.py`; the adapter consumes its JSON table and does not make provider calls

**Interfaces:**
- Consumes: the existing CFO JSON table (`reporting_date`, `sources`, and per-loop `revenue`/`refund`/`cost` cells).
- Produces: `cfo_table_to_treasury_receipts(table, period) -> {receipts, evidence_status, missing_sources, excluded_currencies, excluded_investment_rows, source_receipt_ids}`.
- Maps only non-investment USD cells: `revenue -> customer_revenue`, `refund -> customer_refund`, and `cost -> operating_cost`. The canonical investment row is excluded because Task 1 owns investment net P&L; owner cash flow and model cost must come from their own receipts.
- Excludes `JPY`, `USDC`, and `USD_API_EQUIV` rather than applying an unverified FX rate or treating an API-price estimate as a provider bill. Unverified cells and incomplete cost cells remain missing evidence. No adapter receipt authorizes a transfer or capital promotion.

- [x] **Step 1: Write failing tests** for USD mapping, investment-row exclusion, non-USD/`USD_API_EQUIV` exclusion, unverified and incomplete cells, deterministic aggregate receipt IDs, and malformed/duplicate input rejection; the initial run failed with the expected missing adapter/new-category failures.
- [x] **Step 2: Extend treasury categories** with `customer_refund` and `operating_cost`; calculate net customer revenue and deductible operating/model costs separately while preserving owner cash-flow and investment-P&L separation.
- [x] **Step 3: Implement the pure CFO-table adapter** with no network or credential imports; keep source receipt IDs and reasons in the output for audit.
- [x] **Step 4: Run focused adapter/treasury tests, the full investment suite, and a fresh CFO read-only table replay**; focused tests pass `11/11`, full investment-core discovery passes `40/40`, and the fresh table remains explicit `partial` with no USD receipt invented.
- [x] **Step 5: Commit and push** as `b756217a25` (`feat(investment): bridge CFO receipts into treasury`); this plan update is pushed separately before moving to the next external receipt gate.

## Current TODO Cursor

1. Do not send more owner capital yet; the current measured evidence is negative/insufficient.
2. Hyperliquid read-only preflight is complete; obtain `lm-lead` owner/runtime receipt before any funding or canary.
3. Task 1 canonical fee/model-cost net-P&L spine is implemented and verified (`fa710b6310`); its source contract is ready for venue adapters.
4. Task 3 Alpaca capital-ladder recommendation gate is implemented and verified (`3e6c81970d`); keep the cap at `$100` until its live evidence is complete.
5. Solana nested Tasks 1–5 (wallet/journal, read-only scout, pure policy/paper, fake-client receipt verification, and staged wake) are implemented and focused-tested; real read-only evidence is saved, but no live transaction has been sent.
6. Continue Alpaca measurement until the first 30-round-trip decision gate; no cap increase.
7. Cross-venue allocator/reporter/acceptance is implemented and pushed (`d48e355e7b`); capital expansion remains disabled.
8. Task 8 is complete and pushed (`b756217a25`); the fresh CFO table remains `partial`, so no cash-surplus target claim is allowed.
9. Current cursor: return to Hyperliquid only after owner/runtime receipt and explicit funding boundary; require 14 daily net receipts before expansion.
10. Keep the Solana `$2/$3` live canary closed until an explicit owner-funding/runtime receipt and complete RPC verification exist.
11. S0 scoreboard is recorded below; keep capital expansion disabled and promote only one measured step at a time after the external receipts arrive. Never chase the `$10k/month` number with leverage or blind deposits.
12. The shared loop-contract gate still has a pre-existing Capafy `read_only_external_owner` declaration mismatch; resolve it through the Capafy owner/release path before treating the repository-wide gate as green.

### Current S0 scoreboard

| Lane | Current measured result | Capital/promotion state | Next required proof |
|---|---|---|---|
| Alpaca | One official round trip `-$0.006970681885`; sealed net projection `-$0.04`; `1/30` round trips | Cap `$100`; expansion false | 29 additional completed round trips, positive cost-complete monthly evidence, and owner-approved next cap |
| Hyperliquid | Arbitrum wallet USDC `0`, ETH `0`; Hyperliquid equity/withdrawable/positions/funding rows `0` | Unfunded; no effect allowed from this lane | lm-lead owner/runtime receipt, explicit funding boundary, then 14 daily net receipts |
| Solana copy | Read-only scout `scout_unknown`; `0` candidates; `20` evidence rows; effect `none` | Live canary not run; `$2/$3` gate remains closed | explicit owner-funded canary boundary and one confirmed receipt |
| Cross-venue allocator | Fixture net `$8.70` with owner cash flow `$100.00`; live inputs incomplete | Read-only; expansion false | complete venue/customer/cost receipts with unique source IDs |
| Treasury | CFO bridge implemented; fresh `2026-09-28` table is `partial`, USD bridge receipts `0`, missing `20`, excluded `7` | No transfer; no target claim | fix source ledgers/credential, then verified revenue/refund/operating-cost, owner-flow, P&L, model-cost, tax/reserve receipts |
| Goal | No official rolling monthly net receipt at or above `$10,000`; generational wealth unmeasured | S0 hold | verified monthly P&L plus accumulating treasury/net-worth ledger |

### Execution order ruling

The original task order was `Task 1 → Task 2 full canary → Task 3`. The safe executable order was
`Task 1 → Task 2 read-only evidence → Task 3 pure gate → Task 4 read-only/paper → Task 5 → Task 6 → Task 7 acceptance evaluation → Task 2/Task 4 effect gates`.
The current order is `Task 8 CFO receipt bridge (complete) → Task 2/Task 4 effect gates → rolling measurement`. The bridge remains read-only and partial; it does not unlock owner-funded venue effects, production registry changes, wallet state, or capital expansion.

## Source References

- Hyperliquid funding is hourly, peer-to-peer, and rate-dependent: <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding>
- Hyperliquid fees vary by rolling volume/tier and differ between spot/perps: <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees>
- Hyperliquid official `clearinghouseState`, `userFunding`, and non-funding ledger readbacks: <https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint>
- Alpaca paper trading is simulation and can differ from live execution; live crypto fees are volume/order-type dependent: <https://docs.alpaca.markets/us/docs/paper-trading>, <https://docs.alpaca.markets/us/docs/crypto-fees>
- Solana transaction fees include base and optional prioritisation fees, including on failed transactions: <https://solana.com/docs/core/fees/fee-structure>
- Diversification lowers concentration risk but cannot guarantee against losses: <https://www.investor.gov/introduction-investing/investing-basics/diversify-your-investments>
