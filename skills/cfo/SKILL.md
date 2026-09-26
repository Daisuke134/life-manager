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
