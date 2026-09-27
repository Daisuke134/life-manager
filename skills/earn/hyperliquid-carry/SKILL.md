# Hyperliquid carry wake

Purpose: run one bounded, delta-neutral Hyperliquid spot-long/perp-short carry wake. `run.py` reads market/account state, journals equity, decides under caps, reconciles any cursor before a new entry, and sends one Telegram report per UTC day.

## Live gate and configuration

- Dry-run is the default. Signed Hyperliquid actions occur only when `HL_CARRY_LIVE=1`.
- `HL_CARRY_MAX_LEG_USD` defaults to `$25`; non-finite, non-positive, and above-$25 values fail closed and cannot expand the hard cap.
- `LIFE_MANAGER_STATE_ROOT` overrides the state directory; the journal is `${LIFE_MANAGER_STATE_ROOT:-~/.local/state/life-manager/hyperliquid-carry}/journal.jsonl`.
- The wallet is stored only in `~/.local/share/anicca/credentials.json` under service `hyperliquid-carry-agent-wallet`.

Caps: max leg `$25`; minimum leg and exchange minimum notional `$11`; daily-loss cap `5%`; peak drawdown cap `20%`; entry horizon `14` days; exit APR `5%`; minimum spot volume `$150,000`.

## Safety and evidence

The loop creates clients and signs only after the live gate. `execute` journals every intent before effect and writes a readback-based receipt. It does not send a new entry while an enter/exit intent is open or the ledger marks an unhedged receipt; the next wake reconciles with `execute.exit` first. A verified flat exit records `resolves_intent_id` and terminalizes the original intent; partial and effect-unknown receipts remain retryable. Deposit intents share the journal but never enter spot/perp reconciliation. A halt with an open position also resolves an exit before returning. A missing current pair can use only a recorded complete `perp`/`spot` pair; an `@...` spot additionally requires its recorded `spot_token` (for example `UZEC`). Otherwise the wake returns `reconciliation_pending` without signing.

`deposit.py` journals its sender, native-USDC token, Bridge2 target, chain, and raw amount before a live transfer; it stores a `submitted` tx hash before waiting for the provider receipt. Pending or `effect_unknown` deposits are read back on later invocations and are never auto-resubmitted, including unknown states without a hash.

Telegram sender failures raise before the daily `report` row is appended, so the next wake can retry delivery instead of treating a nonzero subprocess exit as sent.

Funding evidence is the trailing 24-hour Hyperliquid `fundingHistory` average annualized as hourly rate × `24 × 365`; spot liquidity is `spotMetaAndAssetCtxs.dayNtlVlm`. The carry gate requires expected 14-day funding to exceed the round-trip-cost estimate of `0.23%`. The spot taker fee evidence used by execution tests is `0.07%` (`0.0007`) in base asset per fill. Funding/bridge operationalization is Task 7.

Daily reports expose account-equity net P&L as current verified equity minus the first equity mark for that UTC day. Cross-venue fee, funding, and model-cost allocation remains in the separate allocator plan.
