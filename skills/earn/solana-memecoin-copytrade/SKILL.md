# Solana memecoin copy canary

This skill is a staged, local-first loop. Its default is read-only scouting. It does not use a human wallet, Binance credential, exchange credential, browser session, or manually pasted private key.

## Stages

1. `read_only`: read confirmed Solana RPC activity for public target wallets and enrich candidates with public market reads. No paper receipt and no transaction call.
2. `paper`: apply the same pure policy and append an effect-free receipt with explicit simulated fee/slippage. No signing or network mutation.
3. `live`: requires `SOL_COPY_MODE=live`, `SOL_COPY_LIVE=1`, the agent-owned wallet row in the credential SSOT, exact `$2.00` notional, cumulative `$3.00` ceiling, reserve and market gates, and a confirmed RPC receipt. A mode is never advanced automatically by this skill.

An `effect_unknown` receipt is terminal. The next wake is fenced and never retries the transaction.

## Operator invocation

Provide a JSON target file containing only public rows such as:

```json
{"targets":[{"address":"PublicSolanaAddress","label":"public-target"}]}
```

Then run the safe default:

```sh
SOL_COPY_TARGETS_FILE=/path/to/targets.json \
SOL_COPY_MODE=read_only \
skills/earn/solana-memecoin-copytrade/run.sh
```

The journal defaults to `~/.local/state/anicca/solana-memecoin-copytrade/journal.jsonl`; override it with `SOL_COPY_JOURNAL`. State directories are owner-only and journal files are mode `0600`.

The staged wake does not promote itself from read-only to paper or live. An owner/runtime process must provide the next `SOL_COPY_MODE`; a prior `effect_unknown` receipt permanently fences subsequent live wakes until it is reconciled outside this skill.

GMGN discovery requires an explicitly configured public token endpoint template in `GMGN_TOKEN_URL` containing `{mint}`. An optional agent-owned provider key is read from `GMGN_API_KEY` and is never written to target configuration or output. Missing provider configuration returns `scout_unknown`; it never produces a trade candidate.

## Safety contract

- Source activity must be a confirmed target-owned token swap, not a transfer.
- Source events, quotes, liquidity, price impact, SOL reserve, duplicate signatures, and open intents are checked before paper/live action.
- Live submission is journaled before send and reconciled against transaction fee plus before/after owner token deltas.
- Confirmed-but-mismatched deltas become `effect_unknown`; no retry is permitted.
- Deposits are principal, not investment revenue. Paper returns are not capital-promotion evidence.

## Public read references

- Solana `getTransaction`: https://solana.com/docs/rpc/http/gettransaction
- DexScreener Solana token pairs: https://docs.dexscreener.com/api/reference
- GMGN Solana API: https://docs.gmgn.ai/index/cooperation-api-integrate-gmgn-solana-trading-api
- Jupiter quote API: https://dev.jup.ag/docs/swap-api/get-quote
