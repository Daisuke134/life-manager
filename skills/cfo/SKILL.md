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
metadata plus their decompressed TSV paths and SHA-256 values, the detail period, and the
App Store Connect subscription-relationship path and SHA-256. Its top-level keys are
`schema_version`, `observed_at`, `financial`, `detail`, and `relationships`; each report has
`metadata`, `artifact_path`, `artifact_sha256`, and `period`, while `relationships` has
`artifact_path` and `artifact_sha256`. The adapter verifies both gzip
streams, raw TSV hashes, matching period/SKU/currency/quantity/amount, and the subscription to
app relationship. It creates a normalized receipt identity from the detail artifact SHA-256 and
physical row number; it does not create an App Store Connect native report ID. Partial packet
evidence always leaves historical and trailing coverage as gaps. If the packet and legacy
`app_store_financial` input both produce verified ASC receipts, CFO reports `unverified_receipt`
coverage and emits neither source's receipts until the inputs are reconciled. RevenueCat Revenue
charts remain observations; they do not become settled revenue receipts.

The pass is single-writer: do not run another CFO, `cfo-daily`, or financial-report loop against the
same snapshot/delivery tables.

## Per-loop daily P&L (read-only)

`python3 skills/cfo/loop_pnl.py [--date YYYY-MM-DD] [--json]` prints revenue, refunds, cost and net
for each of the 14 Product Loops in `apps/life-manager/config/product-loop-catalog.json` for one
Asia/Tokyo day. It only reads; it never sends, pays or writes state.

- Every number is a sum of entries carrying an official id (`alpaca:activity:*`, `stripe:txn_*`,
  `base:<tx>:<logIndex>`, `lancers:<receipt_id>`, `agent-usage:<event_id>`). `0` means the owning
  source was read for that day and had no entries. `unverified` means no source, a missing
  credential, or a failed read; its reason is printed and net becomes `unverified`.
- Sources: Alpaca live account activities (FIFO realized P&L + fees), Stripe live balance
  transactions (`self-build`; needs an `sk_live_`/`rk_live_` key in the credential SSOT), USDC
  `transferWithAuthorization` transfers on Base for the x402 wallets named by `x402-sell` state
  (own-to-own excluded), marketplace-core `payment_received` ledger rows, and agent-runner
  `agent-usage.jsonl` `provider_cost_usd`.
- `USD_API_EQUIV` is the runner's API-price estimate, not a provider bill. Currencies are never
  converted. `*` marks a cost that excludes usage events lacking a cost value.
- Tests: `python3 -m unittest skills/cfo/test_loop_pnl.py` (fixtures in `fixtures/loop_pnl/`).

## Minimal result report (September 30, 2026)

The local CLI now uses `cfo-result-local.js` and the read-only `loop_pnl.py` collector, not personal
Moneytree balances. It checks all catalog loops and reports today's receipt-backed income by loop,
with an explicit partial subtotal and unknown sources. Missing/stale data never becomes zero.
Investment is realized P&L, other loops are revenue; no claim of net profit is made. Unknown app
currency is shown separately and excluded from currency totals. Personal assets and raw errors are
not pushed.

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
