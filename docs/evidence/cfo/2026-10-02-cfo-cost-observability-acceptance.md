# CFO cost observability acceptance — 2026-10-02

Status: partial (fail-closed; not a production-complete CFO close)
Owner: `lm-cfo-observability-1002`
Code release observed: `553c38a134`

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
| Cloud canary | blocked | no production Supabase/Telegram mutation or official cloud receipt performed in this acceptance run |
| Seven consecutive periods | blocked | requires elapsed observation time and scheduler-owned production readbacks |

## Remaining owner-visible blockers

1. Moneytree authorization/source refresh must be restored so account source update time and transaction completeness can be proven.
2. Google Cloud Cost Table CSV must be exported/read-only imported for the invoice month; the user-provided ¥27,889 screenshot is not a machine receipt.
3. Each configured revenue/expense rail must produce a current official receipt; B7 gaps remain explicit rather than zero.
4. Cloud canary and seven-period observation require the existing production loop owner and official provider receipts; this evidence run intentionally did not mutate or send production state.
