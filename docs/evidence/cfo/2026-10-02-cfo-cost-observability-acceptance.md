# CFO cost observability acceptance — 2026-10-02

Status: partial (fail-closed; not a production-complete CFO close)
Owner: `lm-cfo-observability-1002`
Code release observed: `8f0e4bf599`

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
- Historical company: `unknown`, no settled currency total
- Trailing company: `unknown`, no settled currency total
- Historical/trailing coverage gaps: `137` each
- Main gap classes: `missing_category=126`, `source_unconnected=5`, `read_failed=5`, `stale_readback=1`
- Readback artifact SHA-256: `84717b38c32e7ef81c14c43a02a6b2afa86e89f8a43a542f552a6e0ea2edf9c6`

Interpretation: the collector is running and preserving the gaps, but it cannot honestly produce settled MRR/net/revenue until the configured rails provide current receipt-backed coverage.

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

### Canonical local close with settled Google billing

- Run: `cfo-google-settlement-20261002T150000+0900`
- Result: `sent` with injected provider receipt `google-settlement-live-1` (no external message sent).
- Digest: `d8a77e173eeec388e61d72814b5b5b10ac407e7fb65966de356d8026ad133e08`.
- Report state: `googleBilling=fresh`; settlement `2026-09 / JPY 27,889`; source receipt is the CSV SHA above.
- The same close remained `partial` for Moneytree and B7, so it did not claim a complete CFO close.

### Canonical source-specific artifact readback

- Capafy analytics artifact observed at `2026-10-02T06:07:57Z` was fresh.
- Canonical Financial Manager last-7-day verified Capafy revenue: `USD 19.94`.
- Mobile app artifact was present but did not yield a verified supported-currency revenue amount.
- Source coverage in the same close: `capafy=fresh` (18 verified records), `mobile-apps=empty` (no supported-currency receipt).
- This source-specific figure is intentionally separate from the strict B7 company total, which remains `unknown` until its receipt-backed coverage envelope is complete.

## Acceptance matrix

| Requirement | Result | Evidence / blocker |
|---|---|---|
| Moneytree stale/empty is not zero | proved | live read + CLI exit 1 + fixture replay |
| Canonical local Financial Manager path | proved | `runHourlyCfo` daily default, 1-day idempotent receipt |
| Settled business coverage and gaps | partial | B7 table receipt contract exists; live source artifacts remain unconnected |
| Google estimate vs settled invoice | proved for September settlement; partial for event-level attribution | Official Cost Table CSV parsed with receipt, tax, rounding, and service/SKU totals; joining every usage event to a billing SKU remains incomplete |
| Persistent geocode and free Japan POI lane | proved | Supabase hash-key store, OpenPOI official probe: 1 candidate + attribution |
| Provider budget governor | proved | pure states, tenant isolation, cache-only stopped path, route/Places gates |
| Positive delivery receipt / replay-zero | proved in fixture | `natural-1`, same digest replay quiet; no live send performed |
| Cloud canary | partial/blocked | Supabase read-only tenant probe reached the cloud adapter, but the selected tenant had no email recipient/wallet binding (`email_unbound`); no production claim/send was performed |
| Seven consecutive periods | blocked | requires elapsed observation time and scheduler-owned production readbacks |

## Remaining owner-visible blockers

1. Moneytree authorization/source refresh must be restored so account source update time and transaction completeness can be proven.
2. Each configured revenue/expense rail must produce a current official receipt; B7 gaps remain explicit rather than zero.
3. Cloud canary still lacks an email/wallet binding for the selected tenant, so no production send claim is made.
4. Seven-period observation requires the existing production loop owner and official provider receipts; this evidence run intentionally did not mutate or send production state.
