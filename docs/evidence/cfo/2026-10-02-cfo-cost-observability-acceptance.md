# CFO cost observability acceptance — 2026-10-02

Status: partial (fail-closed; not a production-complete CFO close)
Owner: `lm-cfo-observability-1002`
Code release observed: `8e0a0b50e6`

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
- Google billing settlement: `unknown` (no Cost Table CSV receipt)
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

### Canonical source-specific artifact readback

- Capafy analytics artifact observed at `2026-10-02T06:07:57Z` was fresh.
- Canonical Financial Manager last-7-day verified Capafy revenue: `USD 19.94`.
- Mobile app artifact was present but did not yield a verified supported-currency revenue amount.
- This source-specific figure is intentionally separate from the strict B7 company total, which remains `unknown` until its receipt-backed coverage envelope is complete.

## Acceptance matrix

| Requirement | Result | Evidence / blocker |
|---|---|---|
| Moneytree stale/empty is not zero | proved | live read + CLI exit 1 + fixture replay |
| Canonical local Financial Manager path | proved | `runHourlyCfo` daily default, 1-day idempotent receipt |
| Settled business coverage and gaps | partial | B7 table receipt contract exists; live source artifacts remain unconnected |
| Google estimate vs settled invoice | partial | CSV parser/ledger/migration shipped; official Cost Table CSV not supplied/read back |
| Persistent geocode and free Japan POI lane | proved | Supabase hash-key store, OpenPOI official probe: 1 candidate + attribution |
| Provider budget governor | proved | pure states, tenant isolation, cache-only stopped path, route/Places gates |
| Positive delivery receipt / replay-zero | proved in fixture | `natural-1`, same digest replay quiet; no live send performed |
| Cloud canary | partial/blocked | Supabase read-only tenant probe reached the cloud adapter, but the selected tenant had no email recipient/wallet binding (`email_unbound`); no production claim/send was performed |
| Seven consecutive periods | blocked | requires elapsed observation time and scheduler-owned production readbacks |

## Remaining owner-visible blockers

1. Moneytree authorization/source refresh must be restored so account source update time and transaction completeness can be proven.
2. Google Cloud Cost Table CSV must be exported/read-only imported for the invoice month; the user-provided ¥27,889 screenshot is not a machine receipt.
3. Each configured revenue/expense rail must produce a current official receipt; B7 gaps remain explicit rather than zero.
4. Cloud canary and seven-period observation require the existing production loop owner and official provider receipts; this evidence run intentionally did not mutate or send production state.
