# CFO hourly operator skill

This skill runs one repository-owned CFO pass and exits. It is the operator-facing wrapper for
`apps/life-manager/scripts/cfo-hourly-local.js`; launchd owns the one-hour cadence.

## Contract

- Invoke `skills/cfo/run.sh` from the canonical Life Manager checkout.
- Code is resolved from the same immutable repository release as this wrapper. No second CFO app copy
  or `LIFE_MANAGER_APP_DIR` override is used.
- Credentials are read from `LIFE_MANAGER_ENV_FILE` (default:
  `~/.local/state/life-manager/.env`) and are never printed or written to loop state.
- `LM_CFO_UID`, `TELEGRAM_ALERT_CHAT_ID`, and `TELEGRAM_BOT_TOKEN` are the shared-loop contract.
  `LM_CFO_TELEGRAM_CHAT_ID` remains accepted as a standalone chat-ID fallback; token ownership has one
  canonical name, `TELEGRAM_BOT_TOKEN`.
- State is outside the code release at `CFO_STATE_DIR` (default:
  `~/.local/state/life-manager/life-manager-cfo-hourly`). The wrapper and Node process use this exact
  same directory. Agent Economy revenue defaults to its repository-managed local state under
  `~/.local/state/life-manager/agent-economy`; `LM_AGENT_ECONOMY_STATE_ROOT` or `REVENUE_RECEIPT_JOURNAL` may select another
  self-hosted instance. Marketplace receipt journals are optional and explicitly configured with
  `LM_CFO_MARKETPLACE_RECEIPTS`. The wrapper records only the runner's redacted status envelope in
  `last-result.json`.
- A failure produces a fixed redacted status envelope and a non-zero exit. It never invents a
  financial amount, retries out of band, or logs raw provider/error payloads.

### App Store Connect financial packet

`LM_CFO_MOBILE_APPS_ASC_FINANCIAL_PACKET` may point to one private JSON packet with
`schema_version: 1`, the original `observed_at`, FINANCIAL/ZZ and FINANCE_DETAIL/Z1 report
metadata plus their decompressed TSV paths and SHA-256 values, the detail period, and App Store
Connect subscription-relationship evidence. Its top-level keys are `schema_version`,
`observed_at`, `financial`, `detail`, and `relationships`; each report has `metadata`,
`artifact_path`, `artifact_sha256`, and `period`. Relationships may use the legacy singleton
`{artifact_path, artifact_sha256}` shape or a bundle `{artifacts:[{artifact_path,artifact_sha256}]}`.
Every relationship artifact must be a private JSON object under a mode-0700 parent with mode-0600
file permissions. B7 re-reads each artifact through the private-file reader and compares the
SHA-256 of its exact raw bytes with the packet declaration before accepting provenance. Each
receipt's `data/<n>` and `included/<n>` evidence refs must both match that same artifact hash.
Only artifact hashes/aggregate and normalized receipt fields are persisted; private paths and raw
relationship identifiers are not. The adapter verifies both gzip streams, raw TSV hashes,
matching period/SKU/currency/quantity/amount, and the subscription-to-app relationship. It creates
a normalized receipt identity from the detail artifact SHA-256 and physical row number; it does
not create an App Store Connect native report ID. Partial packet evidence always leaves historical
and trailing coverage as gaps. If the packet and legacy `app_store_financial` input both produce
verified ASC receipts, CFO reports `unverified_receipt` coverage and emits neither source's
receipts until the inputs are reconciled. RevenueCat Revenue charts remain observations; they do
not become settled revenue receipts.

The pass is single-writer: do not run another CFO, `cfo-daily`, or financial-report loop against the
same snapshot/delivery tables.

## Economic attribution CLI (no send/pay; optional evidence write)

`python3 skills/cfo/loop_pnl.py [--date YYYY-MM-DD] [--snapshot-at RFC3339] [--trailing-start RFC3339] [--json]` projects B7 receipts and coverage for all 18 Product Loops in `apps/life-manager/config/product-loop-catalog.json`. `--date` sets only the Asia/Tokyo `reporting_date` label; it does not filter receipts to that day. `snapshot_at` bounds the historical/as-of view and `trailing_start` bounds the trailing view; MRR is an as-of snapshot. Do not present this output as one-day revenue, cost, or net.

- The B7 adapters cover Capafy/mobile, Stripe, affiliate, marketplace, Agent Economy/investment, actual-cost readback, and Writer. This projection does not read Moneytree or personal bank balances.
- Each verified amount must be supported by official receipt evidence. `status=zero` is valid only when required source coverage is complete and there are no qualifying receipts; `status=unknown` or coverage gaps are not zero. Empty currency totals mean no verified total, not `$0`.
- It does not send messages, publish, or pay. When `LM_CFO_MOBILE_APPS_REVENUECAT_LIVE_READBACK=1` and a valid managed occurrence context is present, it performs a RevenueCat read and persists a mode-0600 occurrence evidence file under `CFO_STATE_DIR/mobile-readbacks`. A run with that mode must not be described as no-write.
- `USD_API_EQUIV` is an estimate, not a provider bill. Currencies are never converted.
- Tests: `python3 -m unittest skills/cfo/test_loop_pnl.py` (fixtures in `fixtures/loop_pnl/`).

## Historical result note (September 30, 2026; not current)

This dated note is a historical example, not evidence of current revenue or a complete daily report. Do not infer today's income, all-loop coverage, or profit from it. Personal Moneytree balances are outside this business projection; missing/stale sources remain unknown rather than zero.

- `LM_CFO_REPORT_CHANNEL=email` is the default. Set `LM_CFO_REPORT_EMAIL` to the owner's address
  and supply `RESEND_API_KEY`. Explicit `telegram` uses the existing receipt-backed outbox. No
  automatic channel fallback. Do not run two CFO writers against the same state directory.
- `LM_CFO_REPORT_CADENCE=hourly` (default) or `daily` sets one consolidated receipt per period;
  launchd still owns when the pass runs. Detailed source evidence remains in collector JSON.
- A pending delivery freezes text, destination and key. No retargeting; after 23 hours an unresolved
  email effect requires reconciliation rather than a duplicate resend.
- Cloud: apply `2026-09-30-lm-cfo-result-report.sql` before deploying. Email uses the tenant's `email`
  and `cfo_report_channel`/`cfo_report_cadence`, a separate RLS-protected receipt table, and the
  service's existing Resend identity. Telegram requires explicit selection. Cloud coverage remains
  limited to tenant FinancialRecords/wallet until source adapters exist; the report says so.

Source changes alone do not configure an owner address, apply a database migration, deploy a Mac
release, repair paused jobs or stop other loops' progress chatter. Do not claim live delivery until
those host steps and a provider receipt are verified. Tests use fake providers only.

Spending/net: receipt-backed provider costs and refunds are summed separately by currency. Costs
labelled `USD_API_EQUIV` are estimates, not actual bills; missing cost values keep net unverified.
Bank-settled income, daily token counts and subscription allocation remain explicitly unverified
until suitable settlement/invoice/subscription sources are configured. A $200/month statement is
not an invoice or a daily paid expense; do not silently divide it or subtract it from sales.
