import { test } from "node:test";
import assert from "node:assert/strict";

import { parseTargetTransactions, scout } from "./scout.mjs";

const TARGET = "11111111111111111111111111111111";
const INPUT_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGkZwyTDt1v";
const OUTPUT_MINT = "So11111111111111111111111111111111111111112";
const NOW = 1_700_000_000_000;

function balance(accountIndex, owner, mint, amount) {
  return {
    accountIndex,
    owner,
    mint,
    uiTokenAmount: { amount: String(Math.round(amount * 1e6)), decimals: 6, uiAmount: amount },
  };
}

function swapRow({ signature = "sig-swap", blockTime = NOW / 1000, error = null } = {}) {
  return {
    signature,
    slot: 123,
    blockTime,
    meta: {
      err: error,
      preTokenBalances: [balance(0, TARGET, INPUT_MINT, 10), balance(1, TARGET, OUTPUT_MINT, 0)],
      postTokenBalances: [balance(0, TARGET, INPUT_MINT, 8), balance(1, TARGET, OUTPUT_MINT, 2)],
    },
    transaction: { message: { accountKeys: [] } },
  };
}

function transferRow() {
  return {
    signature: "sig-transfer",
    slot: 124,
    blockTime: NOW / 1000,
    meta: {
      err: null,
      preTokenBalances: [balance(0, TARGET, INPUT_MINT, 10), balance(1, "22222222222222222222222222222222", OUTPUT_MINT, 0)],
      postTokenBalances: [balance(0, TARGET, INPUT_MINT, 8), balance(1, "22222222222222222222222222222222", OUTPUT_MINT, 2)],
    },
    transaction: { message: { accountKeys: [] } },
  };
}

function adaptersFor(rows, overrides = {}) {
  return {
    rpc: {
      getSignatures: async () => rows.map((row) => ({ signature: row.signature, slot: row.slot, blockTime: row.blockTime })),
      getTransaction: async (signature) => rows.find((row) => row.signature === signature) || null,
      ...overrides.rpc,
    },
    gmgn: {
      readToken: async (mint) => ({ mint, priceUsd: 1, liquidityUsd: 100_000 }),
      ...overrides.gmgn,
    },
    dexscreener: {
      readPairs: async (mint) => [{ baseToken: { address: mint }, priceUsd: "1", liquidity: { usd: 100_000 } }],
      ...overrides.dexscreener,
    },
    jupiter: {
      quote: async () => ({ outAmount: "2000000", priceImpactPct: "0.1" }),
      ...overrides.jupiter,
    },
  };
}

test("parseTargetTransactions emits only a confirmed target-owned swap", () => {
  const [event] = parseTargetTransactions([swapRow()], TARGET);

  assert.equal(event.sourceSignature, "sig-swap");
  assert.equal(event.observedOwner, TARGET);
  assert.equal(event.sourceMint, INPUT_MINT);
  assert.equal(event.destinationMint, OUTPUT_MINT);
  assert.equal(event.sourceAmount, 2);
  assert.equal(event.destinationAmount, 2);
});

test("parseTargetTransactions rejects transfer-only activity and failed transactions", () => {
  assert.deepEqual(parseTargetTransactions([transferRow(), swapRow({ signature: "sig-failed", error: "err" })], TARGET), []);
});

test("scout returns scout_unknown for malformed RPC transaction", async () => {
  const result = await scout([{ address: TARGET, label: "target" }], adaptersFor([swapRow()], {
    rpc: { getTransaction: async () => ({ signature: "sig-swap", meta: null }) },
  }), NOW);

  assert.equal(result.status, "scout_unknown");
  assert.deepEqual(result.candidates, []);
  assert.ok(result.evidence.some((row) => row.reason === "rpc_transaction_malformed"));
});

test("scout rejects stale source events before market enrichment", async () => {
  const result = await scout([{ address: TARGET, label: "target" }], adaptersFor([swapRow({ blockTime: (NOW - 3_600_000) / 1000 })]), NOW);

  assert.equal(result.status, "ok");
  assert.deepEqual(result.candidates, []);
  assert.ok(result.evidence.some((row) => row.reason === "source_event_stale"));
});

test("scout returns scout_unknown when market providers disagree", async () => {
  const result = await scout([{ address: TARGET, label: "target" }], adaptersFor([swapRow()], {
    dexscreener: { readPairs: async (mint) => [{ baseToken: { address: mint }, priceUsd: "9", liquidity: { usd: 100_000 } }] },
  }), NOW);

  assert.equal(result.status, "scout_unknown");
  assert.deepEqual(result.candidates, []);
  assert.ok(result.evidence.some((row) => row.reason === "market_provider_disagreement"));
});

test("scout excludes an illiquid quote and deduplicates source signatures", async () => {
  let quoteCalls = 0;
  const result = await scout([{ address: TARGET, label: "target" }], adaptersFor([swapRow(), swapRow()], {
    dexscreener: { readPairs: async (mint) => [{ baseToken: { address: mint }, priceUsd: "1", liquidity: { usd: 5 } }] },
    jupiter: { quote: async () => { quoteCalls += 1; return { outAmount: "2000000", priceImpactPct: "5" }; } },
  }), NOW);

  assert.equal(result.status, "scout_unknown");
  assert.deepEqual(result.candidates, []);
  assert.equal(quoteCalls, 1);
  assert.ok(result.evidence.some((row) => row.reason === "quote_or_liquidity_invalid"));
  assert.ok(result.evidence.some((row) => row.reason === "source_signature_duplicate"));
});

test("scout emits a candidate only with RPC and market evidence", async () => {
  const result = await scout([{ address: TARGET, label: "target" }], adaptersFor([swapRow()]), NOW);

  assert.equal(result.status, "ok");
  assert.equal(result.candidates.length, 1);
  assert.equal(result.candidates[0].sourceSignature, "sig-swap");
  assert.equal(result.candidates[0].destinationMint, OUTPUT_MINT);
  assert.equal(result.candidates[0].sourceAmountUsd, 2);
  assert.deepEqual(result.candidates[0].evidenceIds, ["sig-swap", "gmgn:So11111111111111111111111111111111111111112", "dex:So11111111111111111111111111111111111111112"]);
});
