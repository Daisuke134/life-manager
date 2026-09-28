import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";

import { CANARY_MAX_USD, CANARY_NOTIONAL_USD, decide } from "./policy.mjs";
import { paperApply } from "./paper.mjs";
import { readRows } from "./journal.mjs";

const NOW = 1_700_000_000_000;

function candidate(overrides = {}) {
  return {
    sourceSignature: "sig-copy-1",
    observedAtMs: NOW - 1_000,
    destinationMint: "TokenMint11111111111111111111111111111111111",
    sourceMint: "So11111111111111111111111111111111111111112",
    quoteObservedAtMs: NOW - 1_000,
    market: {
      gmgn: { priceUsd: 1, liquidityUsd: 100_000 },
      dexscreener: { priceUsd: 1, liquidityUsd: 100_000 },
      jupiter: { outAmount: 2_000_000, priceImpactPct: 0.1 },
    },
    ...overrides,
  };
}

function risk(overrides = {}) {
  return {
    nowMs: NOW,
    cumulativeCanaryUsd: 0,
    solBalanceLamports: 10_000_000,
    minSolReserveLamports: 5_000_000,
    estimatedFeeLamports: 5_000,
    openIntentCount: 0,
    seenSourceSignatures: [],
    maxSourceAgeMs: 900_000,
    maxQuoteAgeMs: 30_000,
    minLiquidityUsd: 1_000,
    maxPriceImpactPct: 2,
    ...overrides,
  };
}

test("decide emits exactly the initial $2 copy size", () => {
  const decision = decide(candidate(), risk());

  assert.equal(CANARY_NOTIONAL_USD, 2);
  assert.equal(CANARY_MAX_USD, 3);
  assert.deepEqual(decision, {
    action: "copy",
    mint: candidate().destinationMint,
    amountUsd: 2,
    reason: "eligible_initial_canary",
    sourceSignature: "sig-copy-1",
  });
});

test("decide never splits or exceeds the $3 cumulative canary ceiling", () => {
  const exhausted = decide(candidate(), risk({ cumulativeCanaryUsd: 2 }));
  const partial = decide(candidate(), risk({ cumulativeCanaryUsd: 1.5 }));
  const override = decide(candidate({ requestedAmountUsd: 4 }), risk());

  assert.equal(exhausted.action, "skip");
  assert.equal(exhausted.reason, "canary_budget_remaining_below_fixed_notional");
  assert.equal(partial.reason, "canary_budget_remaining_below_fixed_notional");
  assert.equal(override.reason, "fixed_notional_required");
});

test("decide skips when SOL reserve cannot cover the estimated fee", () => {
  const decision = decide(candidate(), risk({ solBalanceLamports: 5_004_999 }));

  assert.equal(decision.action, "skip");
  assert.equal(decision.reason, "insufficient_sol_reserve");
});

test("decide fails closed for stale, illiquid, high-impact, and unsafe candidates", () => {
  const stale = decide(candidate({ observedAtMs: NOW - 901_000 }), risk());
  const illiquid = decide(candidate({ market: {
    ...candidate().market,
    gmgn: { priceUsd: 1, liquidityUsd: 10 },
  } }), risk());
  const highImpact = decide(candidate({ market: {
    ...candidate().market,
    jupiter: { outAmount: 2_000_000, priceImpactPct: 3 },
  } }), risk());
  const unsafe = decide(candidate({ unsafe: true }), risk());

  assert.equal(stale.reason, "source_event_stale");
  assert.equal(illiquid.reason, "liquidity_below_minimum");
  assert.equal(highImpact.reason, "price_impact_exceeded");
  assert.equal(unsafe.action, "halt");
  assert.equal(unsafe.reason, "candidate_unsafe");
});

test("decide rejects duplicate source events and an existing open intent", () => {
  const duplicate = decide(candidate(), risk({ seenSourceSignatures: new Set(["sig-copy-1"]) }));
  const open = decide(candidate(), risk({ openIntentCount: 1 }));

  assert.equal(duplicate.reason, "source_signature_duplicate");
  assert.equal(open.reason, "open_intent_exists");
});

test("paperApply journals an effect-free receipt with explicit simulated costs", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "sol-copy-paper-"));
  const journalPath = path.join(directory, "journal.jsonl");
  const intent = {
    intentId: "intent-paper-1",
    action: "copy",
    mode: "paper",
    mint: candidate().destinationMint,
    amountUsd: 2,
    sourceSignature: "sig-copy-1",
    createdAtMs: NOW,
  };
  const quote = {
    outAmount: "2000000",
    priceImpactPct: 0.1,
    simulatedFeeUsd: 0.01,
    simulatedSlippageUsd: 0.02,
  };

  const receipt = await paperApply(intent, quote, journalPath);
  const rows = await readRows(journalPath);

  assert.equal(receipt.status, "paper");
  assert.equal(receipt.effect, "none");
  assert.equal(receipt.simulatedFeeUsd, 0.01);
  assert.equal(receipt.simulatedSlippageUsd, 0.02);
  assert.equal(receipt.netPnlUsd, -0.03);
  assert.equal(Object.hasOwn(receipt, "signature"), false);
  assert.equal(Object.hasOwn(receipt, "liveSignature"), false);
  assert.deepEqual(rows.map((row) => row.kind), ["intent", "receipt"]);
  assert.equal(rows[0].intentId, "intent-paper-1");
});

test("paperApply is replay-zero for a repeated source signature", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "sol-copy-paper-replay-"));
  const journalPath = path.join(directory, "journal.jsonl");
  const intent = {
    intentId: "intent-paper-2",
    action: "copy",
    mode: "paper",
    mint: candidate().destinationMint,
    amountUsd: 2,
    sourceSignature: "sig-copy-2",
    createdAtMs: NOW,
  };
  const quote = { outAmount: "2000000", priceImpactPct: 0.1, simulatedFeeUsd: 0, simulatedSlippageUsd: 0 };

  await paperApply(intent, quote, journalPath);
  const second = await paperApply({ ...intent, intentId: "intent-paper-3" }, quote, journalPath);
  const rows = await readRows(journalPath);

  assert.equal(second.status, "rejected");
  assert.equal(second.reason, "source_signature_duplicate");
  assert.equal(rows.length, 2);
});

