# CFO cost observability acceptance — 2026-10-02

Status: partial (fail-closed; not a production-complete CFO close)
Owner: `lm-cfo-observability-1002`
Code release observed: `e26fa24b86`

## Natural-run evidence

### Moneytree official read-only observation

- Run: `moneytree-read-20261002T080439Z`
- Retrieved: `2026-10-02T08:04:39.109Z`
- Account count: 1
- MUFG balance observed: `JPY 504,302` at `2026-10-02T08:04:35.217Z`
- Transaction count for `2026-09-01..2026-10-02`: `0`
- Account source status: `partial / source_freshness_unknown`
- Transaction source status: `partial / transaction_completeness_unknown`
- Transaction coverage: `unknown`
- Account payload receipt: `bcffe42adda6105d554c5b77b4b479e13f7ba2bffe096cc4772c3fc89cdbd623`
- Transaction payload receipt: `46a36894bff8d6377882b2232d0351c821ba16f7ad4a6db8468c7245879ff596`

Interpretation: the balance is last-known/partial, not a fresh cash position. The empty transaction array is not evidence of zero spending. The personal CLI exited `1` and rendered income, spending, and net as `未確認`.

### Moneytree wider official readback

The connector's allowed maximum three-month window (`2026-07-03..2026-10-02`) returned 187 transactions. The latest transaction was `2026-08-25`, so this is still stale, but it is a usable last-known flow snapshot:

- income: `JPY 806,201`
- personal spending after excluding transfers/card repayments: `JPY 205,500`
- internal transfers/card repayments excluded from spending: `JPY 481,810` gross movement bucket
- spending summary by month: July `JPY 102,000`, August `JPY 103,500`
- source freshness: `partial / source_freshness_unknown`
- transaction coverage: `unknown`
- three-month transaction payload receipt: `7ea3475725ac9b66d9529376bfdf19ea1afe94712f0262d3d7bbb48fe9a9735b`

### Moneytree refresh boundary

- Moneytree login/read access through the installed ChatGPT Moneytree plugin succeeded.
- The MUFG connection explicitly showed `接続の更新が必要です`; the consent/update flow reached the official MUFG Direct login page.
- The optional MUFG refresh UI requires branch code, account number (or contract number), and bank login password, but the plugin still provides the last-known read-only snapshot without those values.
- No guessed credential, alternate credential store, bank submission, or false refresh receipt was used. The tab was closed before input/submission.
- The branch propagates structured Moneytree `next_action` values (`moneytree_reconnect_mufg` or `moneytree_refresh_and_readback`) through the immutable observation and daily report warning; this is a freshness warning, not a plugin availability blocker.
- A fail-closed seven-period observation gate is now implemented and tested: seven consecutive receipt-backed days can become `ready`, but `complete` additionally requires all required sources fresh and settled cost each day. No natural seven-day run is claimed yet.

### Canonical local daily close (deterministic fixture, delivery injected)

- Run: `cfo-natural-fixture-20261002T070000Z`
- First result: `sent`
- Provider message receipt: `natural-1` (injected delivery)
- Digest: `4b6b1f95a0a86f1e6e984a5b0367f5920b5ad72ee84b2e3ddd0b853f185a8cc3`
- Replay result: `quiet / unchanged`
- Last-known personal asset shown as stale: `JPY 504,302`
- Moneytree source: `partial` (`source_freshness_unknown` + `transaction_completeness_unknown`)
- B7 business source: `partial`, gap `self-build / stripe-financial-record / source_unconnected`
- Google billing settlement: `settled` (official Cost Table CSV receipt; details below)
- Provider budget: `degraded`, `unknownCount=1`, reason `unknown_cost`

### Canonical local daily close with live Moneytree (delivery injected)

- Run: `cfo-live-moneytree-20261002T0822Z`
- Result: `sent`, injected provider receipt `live-readonly-3`
- Digest: `309a9d0e799dde3948518a2f3f7b8119c4f750fa25cd4c326f2018a81fc5af65`
- stale MUFG asset: `JPY 504,302`
- stale income: `JPY 806,201`
- stale spending: `JPY 205,500`
- stale flow period: `2026-07-16T15:00:00Z..2026-08-24T15:00:00Z`
- live run used injected delivery and did not send to Telegram/email
- Personal CLI read-only output: `今月: stale 収入 ¥806,201 / stale 支出 ¥205,500 / stale 差引 ¥600,701`, process exit `1` because freshness/completeness remain partial

### Live B7 business readback

- Collector: `skills/cfo/loop_pnl.py --date 2026-10-02 --json`
- Snapshot: `2026-10-02T15:00:00.000000Z`
- Trailing window: `2026-09-02T15:00:00.000000Z..2026-10-02T15:00:00.000000Z`
- Historical company: `unknown`, no settled company total (`134` coverage gaps)
- Trailing company: `unknown`, no settled company total (`129` coverage gaps)
- Historical gap classes: `missing_category=125`, `source_unconnected=2`, `missing_coverage=5`, `stale_readback=1`, `unverified_receipt=1`
- Trailing gap classes: `missing_category=121`, `source_unconnected=2`, `missing_coverage=5`, `stale_readback=1`
- Readback artifact SHA-256: `38e1dfce3fd2bd193a88c88cfb73e34ae2dbe4a3a55c477a5d200b1eae03655b`
- Canonical artifact-path rerun receipt: `loop-pnl://sha256/979f5e3ee3903cd0add3a5138c793f87b6dd9344408edd33117c9fe0bccfdd1b`
- The new CFO `coverageSummary` groups the actionable roots: Coconala/Lancers `source_unconnected=2`; Writer `stale_readback=1`; CrowdWorks partial receipt, PartnerStack empty commission, Alpaca order P&L, and Capafy/Mobile partial artifacts `missing_coverage=5`; plus explicit unreported-loop coverage rows. The Google official invoice is now connected to `cfo` infra cost; Stripe is no longer `read_failed` and its trailing financial readback is complete, while one historical JCT fee adjustment remains `unverified_receipt`. The remaining `missing_category` rows are derived category gaps, not independent incidents.
- Fresh private-state audit now has official PartnerStack and Alpaca account readbacks. PartnerStack has an empty commission/payout report and therefore remains `missing_coverage`; Alpaca cash balance is verified but filled-order realized P&L is not derived, so order coverage remains `missing_coverage`. The Lancers marketplace SQLite still has `260` `application_verified` events and `0` `payment_received` events; Capafy/Mobile files are analytics snapshots rather than strict order/financial readbacks.

Interpretation: the collector is running and preserving the gaps. Stripe now has an official readback path and source-backed trailing receipts, but portfolio-wide settled MRR/net/revenue remains unknown until the other configured rails provide current receipt-backed coverage.

### PartnerStack official commission/payout readback

- Capture command: existing `skills/affiliate/scripts/revenue_cli.py capture --cdp-port 9324` against the authenticated PartnerStack dashboard.
- Provider observed at `2026-10-02T14:31:29.921688Z`; official commission rows: `0`; payout rows: `0`.
- Provider state: `PAYOUT_BLOCKED_BY_TAX_SETUP`; tax information is required and payment-provider selection is still shown. These are provider facts, not guessed zeros.
- Content-addressed artifact SHA-256: `95a4803a2f48c69814760f47ec31eec584ea8bc9c08f1e5c7f4b6f384ddc37f3`.
- The CFO adapter now accepts the configured `latest.json` capture receipt only when its sibling artifact hash and bytes match; a recent readback within 24 hours is not incorrectly marked stale.

### Alpaca official account readback

- Runtime flag: `LM_CFO_ALPACA_LIVE_READBACK=1`; each B7 run reads the official live API account and orders collection without writing to Alpaca.
- Read-only account readback observed at `2026-10-02T14:52:25.940435Z`; official orders collection returned `10` filled orders.
- Verified liquid cash: `USD 0`; account equity was observed separately but is not substituted for liquid cash.
- Account readback artifact SHA-256 from the diagnostic capture: `4d52a7922d7f2ec3b0e879bf5a7b906e85abb3ca934ce71af5485a3a3f6149ee`.
- No realized P&L is invented from order rows. The account coverage is verified; order/realized-P&L coverage remains explicitly `missing_coverage` until a broker-settled P&L bundle exists.
- The B0 projection uses a 24-hour freshness window for recent official provider readbacks; future or 24-hour-and-older observations remain stale.

### CrowdWorks partial official readback

- Read-only contract page showed a completed contract, gross `JPY 12`, processor deduction `JPY 2`, and member net `JPY 10`.
- Content-addressed artifact: `e24ff82fc772431201981b934a2f49bc77df92d118a25b490ca8ea78da1e6468`.
- The platform-specific path is enabled, so this receipt is visible while Lancers/Coconala remain explicitly unconnected. Historical/trailing coverage is intentionally partial; one contract is never promoted to platform-wide complete revenue.

### Stripe official API readback and settlement reconciliation

- Runtime flag: `LM_CFO_STRIPE_LIVE_READBACK=1`; account classification policy: explicit `settled_external_revenue` default for empty metadata only.
- Official collections fetched read-only with complete pagination: balance transactions `20`, charges `19`, refunds `3`, subscriptions `7`; every collection reported `has_more=false`.
- Stripe Charge/Refund objects are retained in their source currency, while settled amounts use the linked Balance Transaction currency and amount. The adapter now verifies both currencies independently, so the live USD-to-JPY settlements are not rejected as false inconsistencies.
- Trailing Stripe coverage is complete for the requested financial categories; historical coverage remains a gap only for one old JCT fee adjustment whose accounting sign is not representable by the current unsigned cost-component contract. It is not allowed to poison the trailing window.
- The readback is read-only; no Stripe mutation or raw provider payload was persisted.

### Google Cloud Cost Table official readback

- Billing account `017949-09509F-6A3FB6`: open
- Project `anicca-461216`: billing enabled
- Current gcloud identity: billing-admin permission confirmed read-only
- Cost Table route: Google Cloud Console billing account `017949-09509F-6A3FB6`, tabular report, invoice month `2026-09`.
- Google Prompt was approved in the registered Gmail app; the CSV was exported read-only and copied to the local CFO state path `/Users/anicca/.local/state/life-manager/cfo/google-billing/latest-cost-table.csv` with mode `0600`.
- Invoice number: `5712284328`; invoice date: `2026-09-30`.
- Official invoice total: `JPY 27,889`; tax: `JPY 2,535`.
- Japanese Cost Table parser read `41` service/SKU rows from the exact CSV bytes and returned:
  - pre-tax raw cost: `JPY 25,354.450951`
  - tax: `JPY 2,535`
  - invoice total: `JPY 27,889`
  - rounding adjustment: `JPY -0.451251`
- CSV receipt: `google-billing://sha256/c5157075fe3e8331fa2a72d3b33fc98bbacb8b84a0ee2cfc945051ee87f66c64`.
- Service totals (pre-tax raw): Gemini API `JPY 5,160.873099`; Places API `JPY 9,419.856821`; Geocoding API `JPY 7,493.014626`; Directions API `JPY 3,271.171127`; Cloud Key Management Service `JPY 9.530434`; Cloud Storage `JPY 0.004844`; Cloud Run `JPY 0`.
- The daily ingestion path accepts `LM_CFO_GOOGLE_BILLING_CSV` and `LM_CFO_GOOGLE_BILLING_INVOICE_MONTH`, preserves the receipt, and never folds usage estimates into the settled amount.
- B7 now builds an official actual-cost envelope from the same CSV bytes: `35` infra-cost receipt lines sum to `JPY 27,889` including the invoice tax/rounding reconciliation; the CSV SHA above is the evidence root. Credits that cannot be represented as negative unsigned components are folded into the explicit tax-and-rounding reconciliation line, never silently dropped from the invoice total.

### Canonical local close with settled Google billing

- Run: `cfo-google-settlement-20261002T150000+0900`
- Result: `sent` with injected provider receipt `google-settlement-live-1` (no external message sent).
- Digest: `d8a77e173eeec388e61d72814b5b5b10ac407e7fb65966de356d8026ad133e08`.
- Report state: `googleBilling=fresh`; settlement `2026-09 / JPY 27,889`; source receipt is the CSV SHA above.
- The same close remained `partial` for Moneytree and B7, so it did not claim a complete CFO close.

### Canonical local close with artifact-backed B7 diagnostics

- Run: `cfo-coverage-close-20261002T150000+0900`
- Result: `sent` with injected provider receipt `coverage-close-2` (no external message sent).
- Digest: `4a9547ef08fbd62c38cea7ac5dafe416144369804b546b83f75832bb32b644bd`.
- Google settlement remained `settled` from the official CSV receipt.
- B7 coverage diagnostics returned `20` grouped source/reason rows; the report no longer crashes when immutable readback coverage is extended by later adapters.
- Launchd readback showed `LM_CFO_TELEGRAM_CHAT_ID` is configured. The CFO skill requires explicit channel selection; `LM_CFO_REPORT_CHANNEL=telegram` is now set in the mode-0600 state env and the runner test proves the explicit Telegram binding is honored. Explicit email remains fail-closed without an email.

### Cloud email canary and replay-zero

- Canonical tenant: the launchd-bound owner UID; tenant email binding read back before the canary.
- Initial worker failure root cause: `money-printer-worker` lacked `RESEND_API_KEY`; the same secret was present on the existing `life-call` service.
- Repair: copied the secret without printing it, copied the existing `LM_MAIL_FROM`, and redeployed only `money-printer-worker`.
- Official email receipt: provider message ID `01a0fbf9-1382-7132-b4cc-ef198204375f`.
- Supabase `lm_cfo_result_receipts`: `status=sent`, period `2026-10-02:09`, recipient hash and snapshot hash read back.
- Runtime DB: both canary job attempts are `completed` with `outcome=reconciled_present`; no unresolved effect remains.
- Immediate same-period replay returned `duplicate` with the same provider message ID; no second email was sent.
- This proves the current production worker's cloud delivery boundary. The feature branch still requires its normal release promotion before claiming branch-to-production parity.

### Canonical source-specific artifact readback

- Capafy analytics artifact observed at `2026-10-02T06:07:57Z` was fresh.
- Canonical Financial Manager last-7-day verified Capafy revenue: `USD 19.94`.
- Mobile app artifact was present but did not yield a verified supported-currency revenue amount.
- Source coverage in the same close: `capafy=fresh` (18 verified records), `mobile-apps=empty` (no supported-currency receipt).
- This source-specific figure is intentionally separate from the strict B7 company total, which remains `unknown` until its receipt-backed coverage envelope is complete.

## Acceptance matrix

| Requirement | Result | Evidence / blocker |
|---|---|---|
| Moneytree stale/empty is not zero | proved | installed plugin read + CLI exit 1 + fixture replay; last-known balance ¥504,302, income ¥806,201, spending ¥205,500 |
| Canonical local Financial Manager path | proved | `runHourlyCfo` daily default, 1-day idempotent receipt |
| Settled business coverage and gaps | partial | B7 table receipt contract exists; Stripe trailing, Google infra cost, and Alpaca account readbacks are connected, PartnerStack is official-empty, and order/marketplace gaps remain explicit |
| Google estimate vs settled invoice | proved for September settlement; partial for event-level attribution | Official Cost Table CSV parsed with receipt, tax, rounding, and service/SKU totals; joining every usage event to a billing SKU remains incomplete |
| Persistent geocode and free Japan POI lane | proved | Supabase hash-key store, OpenPOI official probe: 1 candidate + attribution |
| Provider budget governor | proved | pure states, tenant isolation, cache-only stopped path, route/Places gates |
| Positive delivery receipt / replay-zero | proved in fixture | `natural-1`, same digest replay quiet; no live send performed |
| Cloud canary | proved for current production worker; branch promotion pending | Official email provider ID, Supabase sent receipt, runtime `reconciled_present`, and same-period duplicate readback |
| Seven consecutive periods | blocked | requires elapsed observation time and scheduler-owned production readbacks |

## Remaining owner-visible blockers

1. The installed Moneytree plugin is readable now, but its latest transaction is 2026-08-25; provider refresh is needed only to upgrade stale/partial values to fresh.
2. Each configured revenue/expense rail must produce a current official receipt; B7 gaps remain explicit rather than zero.
3. The feature branch still needs normal immutable release promotion and branch-to-production parity readback.
4. Seven-period observation requires the existing production loop owner and official provider receipts; one canary does not prove seven natural periods.
