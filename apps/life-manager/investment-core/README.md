# Cross-venue investment-core contract

This directory owns a local-first, read-only measurement boundary for Alpaca, Hyperliquid carry, Solana copy-trading, and future investment receipt sources. It does not own venue admission, funding, signing, order submission, or loop release.

## StrategyCard contract

`strategy_cards.py` is the canonical, side-effect-free declaration for a
candidate strategy. A card must declare its instrument, timeframe, entry,
exit, sizing, cost model, risk limits, kill conditions, evidence URLs, and
status (`research`, `paper`, `shadow`, `live_candidate`, or `rejected`).

```python
from strategy_cards import StrategyCard, validate_strategy_card

card = StrategyCard.from_mapping(payload)
errors = validate_strategy_card(card)
if errors:
    # Do not grant an effect permission.
    raise ValueError(errors)
```

`StrategyCard` is frozen and recursively immutable. `to_mapping()` returns a
detached JSON-like mapping, and `Decimal` inputs are preserved as strings.
Missing cost or risk data never receives a default; missing exit, cost, risk,
or evidence data must remain invalid until the source is supplied.

## Strategy validation

`strategy_validation.validate_series(card, candles, split, costs)` is a finite
read-only evaluator. It uses chronological train/validation/holdout partitions
(60/20/20 by default), rejects duplicate or future-looking candle inputs,
subtracts entry/exit fees and slippage, and reports `unknown` when required
market or cost data is absent. A card becomes `paper` only when holdout net
P&L is positive, drawdown is within the card, no lookahead is detected, and
the nine-point parameter sensitivity gate passes. The evaluator never imports
credentials or calls venue effect functions.

The evaluator requires one instrument with an explicit `/QUOTE` suffix. USD
uses identity conversion. Other quotes require `quote_to_usd` on every candle:
`{currency, rate, timestamp, evidence_ref}`, with a finite positive USD-per-quote
rate, matching quote currency and candle timestamp, and nonempty source evidence.
Signals retain native prices; USD sizing and proceeds use entry and exit FX
respectively. Missing or invalid conversion yields `unknown` / `rejected` and
null USD money fields, so it cannot become a selected strategy. These are modeled
validation costs, not evidence of actual fees or realized profit.

For the Alpaca cards, `skills/alpaca-investment/strategy_policy.py`
`build_validation_candles(...)` derives RSI/EMA/TEMA/Bollinger/ATR features
from each prefix of the official 5-minute OHLC stream and discards only the
indicator warmup rows. If the official stream has a missing five-minute bar,
the builder starts a new contiguous segment; it never fills the gap or bridges
indicators across it. It never uses a future bar. Exit expressions may use the
current position's `entry_price` and `age_bars`; those values are supplied by
the evaluator, not invented by a model.

The new BTC `*-400-v2` hypotheses use one explicit finite indicator contract:
400 completed five-minute bars, SMA-seeded EMA/TEMA, compared with an observed
800-bar reference. Recursive-price differences above one part per million of
current close, or different internal entry/exit predicates, prevent adoption.
The longer prefix is a comparison input, not a claim of a true or universally
stable EMA. Both validation and runtime signal code use the same comparison
helper; unknown inputs retain null total USD amounts. A hard-stop or time-stop
predicate that agrees on both inputs is not suppressed solely by relative
indicator variation.

Legacy BTC v1 calculations remain available for owned-position resolution, but
the allocator rejects new v1 entries. New validation reports contain only v2
BTC hypotheses. The bounded reader can fetch exactly 800 completed BTC bars
with the same closed interval at aligned and unaligned observation times; gaps,
incomplete pages and invalid prices remain errors. Dispatch of that input in
the normal owner resolves the recorded owned entry policy before selecting history;
the task branch does not claim full runtime adoption or profitability.

Strategy refresh shares the existing investment `control_fence` with submit and
planned-receipt creation. While ownership or an unsettled intent exists, it only
refreshes the same canonical card (status changes do not change the policy).
Corrupt ownership/ledger data is an error. An ETF closed marker is accepted only
with the matching reconciled intent, official filled sell, receipt envelope and
account readback showing the position absent. A legacy BTC `closed` label alone
is insufficient. The existing validation owner evaluates BTC alongside the legacy
ETF policy; a BTC history failure is reported as partial and does not manufacture
a BTC report or prevent refreshing an existing owned ETF policy.

## Net-P&L contract

Every measured venue snapshot carries official source receipt IDs and explicit costs:

```text
net_pnl_usd = gross_pnl_usd
              - trading_fees_usd
              - funding_or_borrow_usd
              - slippage_usd
              - gas_usd
              - model_cost_usd
              - system_cost_usd
```

`system_cost_usd` is the verified tool/browser/infrastructure total, separate from model cost. A missing total remains unknown; paid subtotals cannot fill it. Slippage and funding are signed. Other costs remain nonnegative. The core gross basis is before slippage: the Alpaca paper adapter converts explicitly identified fill-based gross to `fill_gross + signed_slippage` before using this formula, preserving the original paper receipt. Unknown paper gross basis remains partial.

Deposits and withdrawals are `owner_cash_flow_usd` and remain principal/cash-flow evidence. They are never investment revenue or net P&L. Missing, stale, duplicate, malformed, or `effect_unknown` evidence remains unknown/blocked and is never replaced with zero.

The canonical `VenueSnapshot` is in `portfolio_receipts.py`. `venue_receipts.py` normalizes receipt rows; `net_pnl.py` aggregates Decimal-safe totals; `cross_venue_allocator.py` ranks only measured, positive-net, sample-qualified, drawdown-safe candidates. `rolling_measurement.py` calculates the verified UTC 30-day window from daily receipts. The allocator always keeps the existing `$100` cap and reserve and returns `capital_expansion_allowed: false`.

## Daily wake and state

`cross_venue_reporter.wake(...)` is a finite read-only wake. It writes one `cross-venue-YYYY-MM-DD.json` receipt and uses `telegram_outbox.sqlite3` for idempotent delivery. A provider message ID is recorded only after the sender acknowledges it. Missing provider acknowledgement is `delivery_uncertain` and is not blindly resent. State roots must be owner-only (`0700` directory, `0600` files).

When `wake(...)` receives `readers["__daily_receipts__"]`, it calls
`rolling_measurement.rolling_30d(...)` and reports the result only when all 30
UTC days are present, delivered, measured, and source-receipt IDs are unique.
Missing/partial/undelivered days return `unknown`; malformed or duplicate
evidence returns `blocked`. Owner cash flow is summed as a separate field and
never added to rolling net P&L. A numeric target gap is never zero-filled.
When that reader is not supplied, `wake(...)` replays the persisted
`cross-venue-YYYY-MM-DD.json` files for the last 30 *completed* UTC days. The
current day is intentionally excluded until its delivery receipt is durable;
the result records `rolling_period_end` so the measured window is explicit.

## Owner-run entrypoint

`cross_venue_run.py` is a finite owner-runtime entrypoint. It accepts canonical
snapshot files with repeated `--snapshot venue=/path/to/snapshot.json` options,
an optional owner cash-flow receipt via `--owner-cash-flow-file`, and an
explicit `--available-capital-usd` value. It defaults to the standard venues
`alpaca`, `hyperliquid`, and `solana`; an unconfigured or malformed source is
reported as `unknown`, never as zero. The owner cash-flow file must include a
numeric `owner_cash_flow_usd` and non-empty `source_receipt_ids`.

Example owner invocation:

```text
python3 apps/life-manager/investment-core/cross_venue_run.py \
  --state-dir "$INVESTMENT_CROSS_VENUE_STATE_DIR" \
  --snapshot alpaca=/path/to/alpaca-snapshot.json \
  --snapshot hyperliquid=/path/to/hyperliquid-snapshot.json \
  --snapshot solana=/path/to/solana-snapshot.json \
  --owner-cash-flow-file /path/to/owner-cash-flow.json \
  --available-capital-usd 0
```

The entrypoint does not read credentials, sign, submit orders, fund wallets,
or edit loop admission. The Life Manager runtime owns the fixed argv/env,
cadence, release, and live provider acknowledgement.

### Life Manager To-Be connection

The canonical Life Manager job ID is `investment-cross-venue-report`. Its
registry entry runs this finite entrypoint once per UTC day with state root
`~/.local/state/life-manager/investment-cross-venue` and manifest
`inputs.json`. The investment product catalog maps this reporting job beside
`alpaca-investment-live`; it is one owner-controlled receipt path, not a
second ad-hoc scheduler.

The manifest is the owner-to-reader boundary:

```json
{
  "snapshot_specs": ["alpaca=/path/to/alpaca-snapshot.json"],
  "alpaca_state_dir": "~/.local/state/life-manager/alpaca-investment-live",
  "owner_cash_flow_path": "/path/to/owner-cash-flow.json",
  "available_capital_usd": "0"
}
```

When no explicit `--snapshot alpaca=...` is supplied, `alpaca_state_dir` lets
the reader consume the prior completed UTC day's
`performance-daily-YYYY-MM-DD.json` plus the latest observation and risk
readbacks, without credentials or provider calls. The live performance gate
and the paper performance producer both write this day-keyed receipt. During
migration, a legacy `performance-latest.json` is accepted only when its own
observation day exactly matches the requested completed day; a new-day latest
record is never used as the prior day. If the completed-day receipt is
missing or mismatched, Alpaca remains `unknown`. An explicit snapshot file
wins over the state directory. If the manifest is absent, invalid, or a source
file is missing, the daily receipt records
`input_manifest_status` as `missing` or `invalid`, keeps unavailable venues
`unknown`, and uses no available capital. It never turns a missing input into
`$0` profit. `configured` means only that the manifest was validly read; it
does not mean a venue made money. Missing funding, gas, or model-cost fields
remain partial/unknown rather than zero.

During a complete Life Manager release handoff, `bin/reconcile-agent-runner-release.sh`
invokes `provision_manifest.py` before owner reconciliation when that provisioner is
present in the release. If the owner manifest is absent, it creates only the safe
zero-capital default (`snapshot_specs=[]`, the durable Alpaca state directory, and
`available_capital_usd="0"`). A valid existing manifest is preserved; an invalid
existing manifest is not overwritten and fails the handoff. The daily wake never
creates or repairs this file.

Current source boundaries:

- Alpaca performance receipts: existing `skills/alpaca-investment` readback and `investment-core` adapters.
- Hyperliquid carry: its local journal and official account/funding readbacks; currently unfunded with no journal receipt.
- Solana copy-trade: `skills/earn/solana-memecoin-copytrade` journal; the staged read-only scout evidence is outside the repo under `~/.local/state/anicca/solana-memecoin-copytrade/`.
- Owner cash flow and model/API cost: an explicit reader must provide these receipts. Absent input is `不明`/blocked, not zero.

## $10k/month scoreboard

The `$10,000/month` target is a measurement target, not a forecast. It is achieved only when a rolling monthly official receipt reports `net_pnl_usd >= 10000` after all listed costs. Until then, `target_gap_usd` is `不明` unless `rolling_30d(...)` returns a measured 30-day receipt. Treasury cash surplus and customer revenue remain separate from investment P&L.

## Treasury cash contract

`treasury.treasury_snapshot(period, receipts, reserve_policy)` is a read-only
rollup. It keeps `customer_revenue`, `investment_net_pnl`, `owner_cash_flow`,
and `model_cost` as separate receipt categories. Owner cash flow is never
added to profit. A model cost is deducted from treasury only when its receipt
explicitly says it was not already included in investment net P&L; missing
scope, cost, duplicate, or unverified receipts produce `partial`/`blocked`
evidence rather than zero.

The result exposes two independent gaps: `investment_net_pnl_target_gap_usd`
against the `$10,000/month` trading target, and the optional
`treasury_surplus_target_gap_usd` after tax and cash reserves. Neither target
authorizes a transfer, a capital increase, or a live venue action.

`cfo_receipts.cfo_table_to_treasury_receipts(table, period)` is the read-only
bridge from `skills/cfo/loop_pnl.py`. It maps only non-investment `USD`
`revenue`, `refund`, and `cost` cells to `customer_revenue`,
`customer_refund`, and `operating_cost`. The `investment` row remains owned by
the canonical venue P&L spine; owner cash flow and model cost require their own
receipts. `JPY`, `USDC`, and `USD_API_EQUIV` are reported as excluded rather
than converted or treated as a provider bill. Unverified or incomplete cells
remain partial, and the aggregate receipt retains the source receipt IDs.

`financial_record_receipts.financial_records_to_treasury_receipts(records,
subject_id, period)` consumes rows already returned by the canonical
FinancialRecord store. It requires an exact subject and `YYYY-MM` period,
maps only verified USD `business_revenue` and explicit `fee` rows, and keeps
native-asset balances, ambiguous `business_cost` rows, payouts, transfers,
taxes, stale rows, and non-USD assets outside the USD treasury. A second
subject is a blocked input, never an additional revenue source.

`x402_inflow_receipts.x402_inflows_to_cash_receipts(rows, period)` consumes the
separate finalized external-inflow ledger produced by the x402 seller. It
requires successful finalized Base USDC transfers, `external=true`, exact
pay-to binding, unique transaction/source-sale IDs, and timezone-aware
timestamps. It returns `amount_usdc` only; it never invents an FX rate or an
`amount_usd` field, and therefore cannot silently enter the USD Treasury rollup.
The current audited ledger has 18 unique Railway inflows totaling `0.180000
USDC`; September has 15 totaling `0.150000 USDC`.

The local CFO discovers `external-inflows-0x*.jsonl` under the shared
`x402-sell` state root, projects the current period through this adapter, and
renders a separate `x402外部USDC cash` briefing section. That section is
delivery/reporting evidence only; it does not create a USD FinancialRecord or
authorize a transfer.

## Life Manager runtime boundary

The allocator may report a recommendation, but it must not edit `config/loop-registry.json`, `runtime/loop`, `runtime/host`, `bin/`, or any provider wallet. Life Manager runtime owns cadence, registry admission, release, external funding, and live enablement. A missing owner/runtime receipt keeps the relevant venue visible as partial/unknown.

### Recorded BTC ownership before submission

Approved BTC entry decisions freeze the canonical card, release, owner and mode
in the existing receipts ledger. Owned HOLD/EXIT resolves that entry through
its sealed intent and consistent official filled-buy outcome; a stale or replaced
current selection cannot replace the owned policy. Missing or conflicting fill
evidence remains an error. Native fill price and `filled_at` define the entry.
Before selling, the existing control fence checks fresh account quantity and the
exact original entry effect/client/provider identity. A changed position is not
submitted. New crypto buys also revalidate the fresh selected card, release and
expiry under that fence before sealing; only a new report for the same policy
and release may replace the entry report. Paper and live share the existing
bounded BTC/USDC market/gtc transport, keeping their mode-specific contexts.
Paper uses the same recorded BTC ownership and EXIT path as live, alongside its
existing owned ETF path. Missing account positions retain open/pending entry
markers; absence alone does not prove a close. Before a new buy, fresh account
and marker observations under the submit fence prevent overwriting another
entry. Ambiguous or contradictory fill history cannot become a zero-fill close.
Paper pending BTC orders defer the legacy option campaign with unknown P&L,
while keeping the account-wide allocator, risk and unresolved-intent checks.
A managed BTC close records its sealed original entry, exact filled sell and
mode-scoped account readback in the existing outcome strategy receipt before
closing the position. The position owner and durable intent fence share one pure
recorded-close validator from `crypto_ownership_proof`, including the core
selection guard despite its other module names. Completion callers must pass
full ledger history; planned and unresolved work prevent policy replacement.
Account lag remains pending across repeated runs and
receipt recovery; complete reconciliation replays without another query/append.
Terminal no-fill requires an explicit finite zero consistent with known fills.
Missing or malformed quantities remain pending. A later official zero can enrich
unknown evidence without erasing a known positive fill. Positive partial fills
require the terminal acquisition/remainder proofs described below.
Existing closed markers are also audited: a sell needs its recorded original-entry,
close and account proof; a no-fill needs a sealed entry, official terminal zero and
flat account receipt. Known owner/policy/status contradictions are rejected across
all fill phases. Proven closed/no-fill state permits the next policy refresh;
unproved state cannot become permission to reenter. No-fill receipts retain unknown
USD net profit and do not assert zero operating costs.
Managed filled buys now require recorded same-mode acquisition/account evidence
before opening ownership. Account lag remains durably unresolved, and malformed
completed phases cannot hide an invalid proof from the common counter.
Terminal partial recovery first reads bounded FILL/CFEE snapshots through the
existing CLI. CFEE may post at end of day without an order ID: an empty query
or an observed balance difference does not prove zero or attributed fees.
Paused orders (`done_for_day`, `stopped`, `suspended`) remain unresolved. Only
`canceled`, `expired`, and `rejected` can prove a final zero-fill failure, consistent
with full known fill history. Prior raw paused-zero outcomes can progress to an
exact same-order fill; reversed identity, decreasing quantity and post-fill
regressions remain invalid. Terminal partial buys now use the existing callback,
recorded entry proof, durable counter and ownership synchronization. Exact FILL
and same-mode account evidence must be saved before opening ownership. A stale
or contradictory pending quantity is not overwritten during receipt adoption;
known non-null fill times must also agree with executions and account time.
FILL/account lag remains unresolved, without another order. Normal owned EXIT
keeps the same original policy and parent. Terminal partial/zero sells now save
an account/activity/remainder receipt before reopening the proven remaining qty.
The original acquisition and each prior sell leg are revalidated in ledger order,
including unique known provider order and target FILL IDs across the cycle.
A final flat close must conserve that same history. Open close pointers remain
paired and audited; only proven zero remaining qty permits flat policy refresh.
No account balance difference is inferred to be a fee.
New BTC BUY decisions retain the existing under-fence fresh account observation
as `pre_trade_account_readback` before sealing. Native account, mode, position
shape/finite quantities, and decision/submission time bounds are revalidated by
the shared entry proof. Missing USDC positions stay absent, never inferred zero;
legacy decisions are not backfilled. This is an immutable raw baseline for later
quote-flow reconciliation, not an atomic account snapshot, fee completeness,
settlement, or net-profit authority. The clock is read before positions by the
existing observation reader. No additional provider reads or financial values
are introduced by this capture.
The under-fence crypto order path additionally opts into a `flow_sink` on the
existing allocator reader. It keeps raw wallet transfers (unsupported/null on
paper) and bounded all-type activity pages in the sealed decision, with their
actual query window and partial/error state. Default snapshots and risk inputs
are unchanged. Additional capture errors retain valid observations and never
become zero costs or another trading gate. This is raw input retention only;
cycle-wide/late-fee coverage, flow identity, reconciliation and net remain open.
`crypto_fill_activity_proof` validates the saved snapshot and raw order, sums
quantities and computes native VWAP with exact rational arithmetic. Display
rounding cannot decide quantity equality. Nullable broker fields stay unchanged;
FILL execution times and the exact average ratio are separate facts. The proof
retains unknown fees/P&L and alone never opens or closes ownership.
The existing run now writes owned BTC cycle reports through one paper/live
projector: `performance-crypto-latest.json` and
`performance-crypto-daily-YYYY-MM-DD.json`. One acquisition and all proven sell
legs form one cycle. Actual FILL notionals provide native execution cashflow;
missing evidence remains unknown. Validated activity snapshots are reused,
daily reports include newly closed cycles, and history anchors survive errors.
The core selects the BTC namespace if its latest or daily files exist and never
falls back to legacy measured ETF reports when BTC evidence is missing/invalid.
Phase-one BTC reports remain partial, with all USD profit/cost values unknown
and capital expansion disabled. Native cashflow is not settled net profit.
Observed CFEE rows are deduplicated across validated snapshots. Only an explicit
order link and validated received-asset quantity can attribute a native fee.
Conflicting activity IDs and fees above actual received quantity are rejected;
missing links remain unattributed. Daily attribution includes only its cycles,
while account-window observation counts and unattributed evidence remain explicit.
Empty results never prove zero fees or settlement. After execution snapshots
are cached, separate fee references retain late readbacks without changing those
execution references. The existing reader advances one window of at most 90 days
per run; a completed UTC day waits for the next day, and the same successful
observation replays without reads. Invalid snapshots retain prior cache/anchors.
New or conflicting fills for completed orders are rejected; daily generated_as_of
records when historical results were actually rebuilt. Page limits shrink the
actual UTC window for the next run; unrelated failures retain its width. A minimum
day limit retains its exact range and prevents larger-prefix repeat reads.
Missing executions advance from saved window ends. Local schema2 activity bundles
retain the original bounded wire snapshots and validate contiguous coverage and
quantity with the same execution proof; they never claim one provider response.
CFEE attribution uses each original segment's time window and receipt reference.
Within-day page limits now use the same transport with saved last-activity tokens.
Each run reads at most four pages for one activity kind. Pure progress validates
all token/window/kind/ID boundaries; only short terminal pages for both FILL and
CFEE produce a local schema3 paged window, retaining every original raw chunk.
The existing paper/live main injects this reader into the same writer. Partial
chains and failed resumes keep their checkpoint/cache and never advance completed
coverage. Successful same-clock replays read nothing.
CFEE activity/settlement dates are distinct from creation-time query bounds.
A backdated fee is allowed; optional created_at is checked against its original
wire window, without generating a missing timestamp. A fixed live readback
confirmed four raw CFEE order IDs match four official orders, and the pinned CLI
preserves all fields. Scoped CFEE queries returned empty in that diagnostic;
retain unfiltered bounded reads and exact response IDs without inferring zero fees.
The pure native BUY fee reader additionally requires executed received-BTC debits,
exact order identity and creation times; missing evidence remains pending. It
retains exact cumulative quantity and original activity IDs/window references.
The shared historical quantity fold starts with actual credited quantity and
validates every prior partial, zero and full sell using the same receipts.
Acquisition and full-close quantity text preserves all digits independently of
ambient Decimal precision. The pure native debit proof now composes this history
with explicit cumulative BUY fees and a fresh same-mode account. Expected qty is
gross BUY fills minus explicit BTC fees minus proven SELL fills; only the difference
from currently proven qty is a new debit. Already embedded fees are not subtracted
twice. Account lag stays pending; unexplained gaps and increases are rejected.
Known activity IDs remain bound to their original FILL/CFEE facts across saved
history and new readbacks. Proven execution sets include zero-fill orders;
conflicting or new executions for those sets are rejected. Previously observed
BUY fee IDs cannot disappear from the cumulative recovery evidence.
The existing effect store now persists positive native debit proofs once under
its receipt-ledger lock. Zero debits append nothing. The shared quantity fold
revalidates debit events in ledger order alongside SELL legs; each sell uses only
adjustments recorded before its seal. Original acquisition and SELL receipts stay
unchanged. Save-before-marker-update replays append nothing; further new fees wait
until the saved quantity is adopted. The first valid acquisition/SELL receipt
anchors history, while all later observations remain subject to conflict checks.
The existing open owner now adopts the same validated quantity state, and the
policy loader rejects an unproved or stale marker quantity. The current official
last order is audited against its historical account receipt. Only a new account
quantity decrease triggers a bounded BUY fee observation, receipt save and marker
update. Save-before-marker-update replays recover from the saved event without
activity reads. Explicit fee exhaustion has a separate proven flat marker/guard;
no SELL is invented. The fresh submit check discovers no new fees: a changed
quantity rejects that decision and is handled on the next natural wake. Missing
BTC without fee evidence retains the existing pending/no-trade behavior.
Terminal partial/zero SELL reconciliation now reads from the original BUY and
uses the same native fee proof against the raw account. Additional debit evidence
is saved inside that SELL receipt, with sold and debited quantities kept separate.
Historical receipt checks use the saved account; current flatness is checked
separately so a later clock never rewrites a closed fee proof.
Performance now derives each pre-sell and final quantity from this same chain.
Fee-only closures count as closed ownership cycles, but never as completed round
trips without a positive SELL. A position closed by a fee uses the saved flat
account observation time, including a partial SELL followed by a next-day fee;
it is never attributed to the earlier SELL day. Post-acquisition quantity adjustments are explicit;
native execution cashflow uses actual FILL notionals without subtracting BTC fees
twice. Observed executed SELL fees denominated in USDC have separate per-cycle known
subtotals and native cashflow after those observed quote fees. Missing/invalid
quote fees stay null, and missing execution cashflow prevents a numeric adjusted
cashflow. These fields cover observed components only; BTC base fees are not
subtracted again. USD net/cost completeness and capital expansion remain unproved.
Each performance order also retains the sealed `requested_notional_usd` budget
separately from `execution_quote_currency=USDC` and actual FILL notional. SELL
requests have no requested notional. Missing fills never fall back to the budget;
a short fill is not an inferred fee. Alpaca documents a 2% price collar for crypto
market orders, so requested and filled values need not match:
https://alpaca.markets/support/why-do-i-see-a-discrepancy-between-the-notional-value-requested-and-the-order-value-ultimately-filled
The requested USD field expresses our sealed budget; pair-specific backend sizing
and quote funding still require the existing pre-live currency/capital proof.
Crypto performance reuses the existing paid-cost adapter with exact paper/live
owner, order group, period and broker/FILL source IDs. Known paid model/system
components have separate verified subtotals; missing coverage never fills complete
model/system costs or net P&L. Daily reports select the same closed subset. The
writer uses the existing CFO readback path and caches accepted billing evidence;
missing or regressed input preserves known verified components and reports a gap.
Cached raw evidence must also match saved charge anchors. A mismatch makes cost
subtotals unknown while retaining native cycles and anchors; correct incoming
evidence restores the subtotal without accepting a changed historical charge.
The paper and crypto writers now capture independent local source inventory via
the existing private runtime journals, read-only admission DB, saved source
snapshots and exact-SHA release catalogs. They retain actual claimed occurrences,
read limits, missing evidence and saved paid-source lower bounds. Strict ledger
reads reject damaged rows; financial readback never substitutes a newer release
for old evidence. One-order fee closures and multi-order partial exits retain
ordered economic groups. Daily reports select the same closed scope subset.
Official query coverage now consumes that inventory: actual execution-owner/run/
claimed-occurrence tuples, same owner/mode/ordered group/period, read history bounds
and every required provider/account/category must match finalized paginated billing
facts. One-order fee closures, partial exits and owner periods are supported. Shared
executors keep their identity. Legacy observations and unverified diagnostics remain
separate from independent scope coverage. Known paid charges require the scoped
paid allocation (including invoice/receipt aliases); a final-no-charge claim cannot
hide them. Scope coverage and cost evidence are selected by group and period for
daily output, without inventing zero-dollar receipts or net-profit totals.
Execution inventory now retains native started/finished timestamps. Billing windows
for owned trade groups must cover their full seeded executions, without moving the
economic close or pulling in later runs. Paid components can include pre-intent and
post-close work only through verified query evidence and the exact allocated run's
incurred-time window. Unproven or mismatched attribution remains an explicit component
gap; it never becomes zero cost. Owner periods use a half-open calendar interval.
Confirmed operating totals now require complete selected scope coverage, verified
attribution and an audit of every paid investment allocation in that billing
footprint. Scope-specific proof can retain a valid paid cost despite a separate
whole-loop historical gap. Unmapped or unverified owned obligations block totals;
unknown accounts cannot hitchhike on another account's final-zero query. Exact
model/system sums count each underlying charge once. Zero totals require final
scope evidence; absent data remains null. Builders and daily output preserve
confirmed operating totals while fees, FX and net retain their own gates.
Calendar requests independently verify same-owner/mode child scopes, then include
in-period child expenses only when the parent final query covers the same billing
provider/account/category/document. Components keep their original trade binding;
selecting parent and child counts each charge once. Rejected child costs retain
their event time so the calendar also preserves their gap. Periodic/standing service
allocation, idle costs, durable account/coverage and full net remain D4 work.
An incomplete calendar rollup never reports zero by excluding verified child
expenses. Explicit paid service-period allocations require matching official line
and paid-allocation join periods, a full matching owner period and verified final
billing coverage. They retain the whole original amount as a service expense;
execution timing is not substituted for service attribution. Partial periods and
unverified service metadata remain gaps, without guessed daily proration or new
money receipts. A partial view cannot invalidate a separately confirmed full
service period. Owned raw obligations with missing or inconsistent scope-kind
metadata still block a parent final-zero claim; unverified obligations are not
excluded merely because their claimed occurrence time is outside the calendar.
Known paid charge anchors now retain the exact amount, category, original group
and period, and any known billing account across daily history and crypto caches.
The same charge or receipt alias cannot replace those facts. Missing legacy account
metadata stays unknown and can be enriched by a fresh validated input without
changing money facts; a raw-cache edit cannot perform that enrichment. Conflicting
inputs retain prior evidence or return a typed unknown instead of redefining costs.
Confirmed source observations are retained in the existing report's
`known_operating_cost_source_evidence`, including zero-charge scopes with no paid
components. Records retain their original scope, payer/category/document/query
references and billing observation time. Duplicate input does not add duplicate
records. These historical records have `current_cost_authority=false`: current
money, coverage, net and capital gates still use the current readback and independent
inventory. Regressed input therefore remains unknown even while the old evidence
is preserved. Invalid source history is rejected without dropping the previously
loaded activity or entry/closed/fee proof caches from the failure envelope.
Historical execution intervals retain their native clock: their end is not bounded
by an earlier billing observation; the original independent-inventory validation
owns that execution-time bound.
The same local paper/live pass now attaches `owner_period_operating_costs` to
`allocation-latest.json`, covering the last completed UTC day even without trades
or closed cycles. The inventory fills an empty owner-period evidence list only
from native start/terminal event IDs; missing executions remain a gap. Paper passes
supply all verified completed economic scopes with original `closed_at`, including
prior-day trades, and crypto supplies its verified cycle scopes. Confirmed daily
paid components are retained as lower bounds: a later zero/missing/changed claim
cannot erase them, move them to another day, or double-count a receipt alias.
The first allocation update preserves the previous same-owner/mode snapshot until
the reporting read completes; this read adds no provider calls or submit/risk/fence
changes. Incomplete evidence stays null and net/capital remain unverified/false.
Cloud and shadow paths do not run this local report.
Production gaps are not cleared by passing fixtures.
The pinned quote transport can now capture a single USDC/USD BBO at or before
an economic timestamp, using a fixed 30-second window and descending limit one.
The shared pure proof preserves nanoseconds in both the request and age checks,
rejects future/stale/invalid quotes and never invents FX parity for missing data.
An older page token is retained without claiming an exhausted history window.
The result is explicitly a reference quote, not a cash conversion. The performance
consumer contract binds each raw FILL timestamp and identity to an as-of midpoint,
keeping exact rational USD reference amounts separate from native cashflow and
actual cash settlement. Attributed fees use credited-asset weighted execution
cost basis; BTC fees are not subtracted twice. Missing FX stays null. The existing
cycle reference also subtracts verified, fully scoped model/system USD costs once
as `cashflow_after_observed_fees_and_scoped_operating_costs_usd`. Cycle, strategy,
root and daily views use exact rational sums; missing FX, observed quote fees or
cost coverage leaves this value null. It is a reference cashflow, not settled
net profit, and excludes unallocated standing/idle costs. The writer recomputes
it after selecting accepted billing history; capital expansion stays disabled.
The cross-venue reader accepts these scoped operating amounts only with complete
operating coverage and finite nonnegative decimal strings. The crypto snapshot
remains partial, with gross/net and broker fee economics unknown; known operating
costs never authorize a measured result or a legacy measured fallback.
The existing
writer caches mode-bound raw FX evidence, reads at most two missing timestamps per
pass and avoids retrying the same timestamp at the same observation clock. A
transport failure preserves native performance; invalid FX cache preserves native
history anchors while failing closed. The normal run injects the same-mode read-only
FX reader. Complete operating costs and production adoption remain in the SSOT.
This branch is source only: verified fee quantity-drift recovery, FX and complete
actual costs, deployment, natural outcomes and profitable evaluation remain in
the canonical SSOT.
