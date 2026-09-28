# Solana Memecoin Wallet-Copy Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first Solana wallet-copy-trading loop that advances from read-only scouting to paper replay and then to one on-chain-verified $2–3 live canary without using a human's credentials.

**Architecture:** Add a separate `skills/earn/solana-memecoin-copytrade/` skill so the existing `sol-trade` base agent remains unchanged. Public wallet activity is discovered through Solana RPC and enriched by GMGN and DexScreener; Jupiter is used for executable quotes. A pure policy produces a copy intent, paper mode replays the same intent without signing, and live mode is gated twice and verifies every submitted signature, token delta, fee, and final balance through Solana RPC before recording a receipt.

**Tech Stack:** Node.js ESM, existing `@solana/web3.js`/`bs58` dependencies, Jupiter Swap API, GMGN read-only data, DexScreener API, Solana JSON-RPC, `node:test`.

**Spec:** Dais directive 2026-09-27 (read-only scout → paper → $2–3 live canary, Jupiter/GMGN/DexScreener, no human credentials), `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md` investment ladder, and the existing verified-swap pattern in `skills/earn/sol-trade/lib/record-swap.mjs`.

## Global Constraints

- `SOL_COPY_MODE` defaults to `read_only`; only `paper` and then `live` are valid transitions, and a live wake requires `SOL_COPY_LIVE=1` as a second gate.
- The live canary starts at exactly `$2.00` notional and has a hard total canary ceiling of `$3.00`; no order, retry, or split order may exceed the remaining ceiling.
- Target wallets, token mints, and provider URLs are public data only; no human private key, exchange credential, browser session, or manually pasted API key is accepted.
- The signing key is an agent-owned Solana wallet stored in the credential SSOT under a dedicated service row; it never appears in the repository, logs, Telegram, fixtures, or provider request text.
- A candidate must carry source evidence from Solana RPC plus at least one market source; provider-reported PnL is discovery context, never proof of profit.
- Every live transaction is journaled before submission, reconciled by signature, and rejected unless confirmed RPC token deltas, lamport fees, mint, owner, and final balance agree with the intent.
- Stale source events, missing RPC receipts, unknown token mint/owner, insufficient liquidity, excessive price impact, failed confirmation, and any ambiguous effect fail closed and never trigger a retry.
- No file under `runtime/loop`, `runtime/host`, `bin/`, or `config/loop-registry.json` is modified by this plan; registry/admission and release work is a separate lm-lead boundary.

## Review Focus

- A target wallet's transfer is not a trade: require a parsed swap with source and destination mints, amount, owner, and confirmed signature; test a transfer-only fixture.
- GMGN/DexScreener disagree or are unavailable: preserve the RPC evidence and return `scout_unknown`, never invent a price or PnL; test partial provider failure.
- Jupiter quotes a route whose price impact or output is outside the canary policy: paper records a rejected intent and live signs nothing; test both boundaries.
- A live signature is confirmed but the wallet delta does not match the intent after fees: record `effect_unknown` and block further live actions; test mismatched post-balances.
- A repeated wake sees the same source event or an open intent: deduplicate by target-wallet signature and intent id, without submitting a second transaction; test replay-zero.

---

### Task 1: Agent wallet, public target configuration, and append-only journal

**Files:**
- Create: `skills/earn/solana-memecoin-copytrade/wallet.mjs`
- Create: `skills/earn/solana-memecoin-copytrade/journal.mjs`
- Create: `skills/earn/solana-memecoin-copytrade/test_wallet_journal.mjs`

**Interfaces:**
- Produces `loadOrCreateAgentWallet(ssotPath) -> { publicKey, signTransaction }` and `readTargets(configPath) -> Array<{address, label}>`; reject private keys in target configuration.
- Produces `append(journalPath, row)`, `readRows(journalPath)`, `openIntent(journalPath)`, and `seenSourceSignature(journalPath, signature)` with owner-only state permissions.

- [x] **Step 1: Write the failing tests** for SSOT preservation, 0700/0600 state permissions, public-only target validation, intent-before-effect ordering, and source-signature deduplication.
- [x] **Step 2: Run `node --test skills/earn/solana-memecoin-copytrade/test_wallet_journal.mjs` and verify it fails because the modules do not exist.** RED observed with missing `wallet.mjs`.
- [x] **Step 3: Implement the wallet and journal contracts** using the existing credential-SSOT shape and atomic append; never print or serialize the secret.
- [x] **Step 4: Run the focused test and verify all assertions pass.** `5/5` pass.
- [ ] **Step 5: Commit** `feat(sol-copy): add agent wallet and durable copy journal`.

### Task 2: Read-only scout using Solana RPC, GMGN, DexScreener, and Jupiter

**Files:**
- Create: `skills/earn/solana-memecoin-copytrade/sources.mjs`
- Create: `skills/earn/solana-memecoin-copytrade/scout.mjs`
- Create: `skills/earn/solana-memecoin-copytrade/test_scout.mjs`

**Interfaces:**
- Produces `scout(targets, adapters, nowMs) -> { status: "ok"|"scout_unknown", candidates, evidence }`.
- Produces `parseTargetTransactions(rpcRows, targetAddress) -> Array<CopyEvent>` where each event has the confirmed source signature, slot, mint, source/destination amounts, observed owner, and observed timestamp.
- Adapters are injected functions: `rpc.getSignatures`, `rpc.getTransaction`, `gmgn.readToken`, `dexscreener.readPairs`, and `jupiter.quote`; the default adapters use only public read endpoints and an optional agent-owned provider credential resolved outside the target-wallet config.

- [ ] **Step 1: Write fixture-backed failing tests** for a valid swap, a transfer-only transaction, malformed RPC metadata, missing GMGN/DexScreener data, and a stale source event.
- [ ] **Step 2: Run the focused test and verify failure.**
- [ ] **Step 3: Implement source adapters and normalization**; keep provider responses as evidence and do not treat their PnL or security score as an execution approval.
- [ ] **Step 4: Run the focused test and verify valid candidates are emitted only with RPC evidence.**
- [ ] **Step 5: Commit** `feat(sol-copy): add read-only on-chain scout sources`.

### Task 3: Pure copy policy and paper replay

**Files:**
- Create: `skills/earn/solana-memecoin-copytrade/policy.mjs`
- Create: `skills/earn/solana-memecoin-copytrade/paper.mjs`
- Create: `skills/earn/solana-memecoin-copytrade/test_policy_paper.mjs`

**Interfaces:**
- Produces `decide(snapshot, risk) -> { action: "copy"|"skip"|"exit"|"halt", mint, amountUsd, reason, sourceSignature }`.
- Produces `paperApply(intent, quote, journalPath) -> receipt` with no signing, no RPC mutation, and explicit simulated fees/slippage from the quote.

- [ ] **Step 1: Write failing tests** for the exact $2 initial size, the $3 hard ceiling, insufficient SOL reserve, stale/illiquid/unsafe candidates, duplicated source events, and a paper receipt that contains no live signature.
- [ ] **Step 2: Run the focused test and verify failure.**
- [ ] **Step 3: Implement deterministic risk gates**: quote freshness, maximum price impact, minimum liquidity, SOL gas reserve, one open intent, target-event age, and cumulative canary budget.
- [ ] **Step 4: Run the focused test and verify all paper decisions are deterministic and effect-free.**
- [ ] **Step 5: Commit** `feat(sol-copy): add gated policy and paper replay`.

### Task 4: $2–3 live canary and RPC receipt verification

**Files:**
- Create: `skills/earn/solana-memecoin-copytrade/execute.mjs`
- Create: `skills/earn/solana-memecoin-copytrade/receipt.mjs`
- Create: `skills/earn/solana-memecoin-copytrade/test_live_canary.mjs`

**Interfaces:**
- Produces `executeCanary(intent, quote, wallet, clients, journalPath) -> receipt`; `clients` supplies quote/build/send/confirm/readTransaction/readBalances functions so tests never touch the network.
- Produces `verifyReceipt(intent, transaction, beforeBalances, afterBalances) -> { verified, status, netUsd, feeLamports, evidence }` and accepts only `verified` or a typed `effect_unknown`/`rejected` result.

- [ ] **Step 1: Write failing tests** proving read-only and paper modes never call `send`, live mode rejects missing `SOL_COPY_LIVE=1`, a $4 intent is rejected, a confirmed matching swap is verified, and a mismatched confirmed swap becomes `effect_unknown` without retry.
- [ ] **Step 2: Run the focused test and verify failure.**
- [ ] **Step 3: Implement the double gate, journal-before-send boundary, Jupiter transaction submission, and RPC receipt verification.**
- [ ] **Step 4: Run the focused test and verify the canary invariants.**
- [ ] **Step 5: Commit** `feat(sol-copy): verify live canary receipts on chain`.

### Task 5: One wake, operator notes, and staged acceptance

**Files:**
- Create: `skills/earn/solana-memecoin-copytrade/run.mjs`
- Create: `skills/earn/solana-memecoin-copytrade/run.sh`
- Create: `skills/earn/solana-memecoin-copytrade/SKILL.md`
- Create: `skills/earn/solana-memecoin-copytrade/test_run.mjs`

**Interfaces:**
- Produces `wake({ mode, liveGate, targets, clients, journalPath, nowMs }) -> { stage, decision, receipt }` and never advances mode automatically; a mode transition is an explicit state record produced by the owner loop, not a human credential prompt.

- [ ] **Step 1: Write failing integration tests** for read-only → paper → live stage reporting, daily idempotent report rows, no live call in the first two stages, and terminal `effect_unknown` fencing.
- [ ] **Step 2: Run the focused suite and verify failure.**
- [ ] **Step 3: Implement the finite wake and `SKILL.md`** with the provider URLs, credential prohibition, risk caps, journal path, and the exact staged acceptance sequence.
- [ ] **Step 4: Run all plan tests and a real read-only scout against one public target wallet; save the evidence without exposing secrets.**
- [ ] **Step 5: Commit** `feat(sol-copy): stage autonomous memecoin copy canary`.

## Source references

- Jupiter Swap API: https://dev.jup.ag/docs/swap-api/get-quote and https://dev.jup.ag/docs/swap-api/build-swap-transaction
- GMGN AI Agent API: https://docs.gmgn.ai/index/gmgn-agent-api
- DexScreener API reference: https://docs.dexscreener.com/api/reference.md
- Solana RPC `getSignaturesForAddress` / `getTransaction`: https://solana.com/docs/rpc/http/getsignaturesforaddress and https://solana.com/docs/rpc/http/gettransaction
