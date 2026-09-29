import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";

import { readRows } from "./journal.mjs";
import { executeCanary } from "./execute.mjs";

const OWNER = "Agent111111111111111111111111111111111111111";
const SOURCE_MINT = "So11111111111111111111111111111111111111112";
const DESTINATION_MINT = "TokenMint11111111111111111111111111111111111";
const NOW = 1_700_000_000_000;

function tokenBalance(accountIndex, owner, mint, amount) {
  return {
    accountIndex,
    owner,
    mint,
    uiTokenAmount: { amount: String(amount), decimals: 6, uiAmount: Number(amount) / 1e6 },
  };
}

function balances(sourceAmount, destinationAmount) {
  return [
    { owner: OWNER, mint: SOURCE_MINT, rawAmount: String(sourceAmount) },
    { owner: OWNER, mint: DESTINATION_MINT, rawAmount: String(destinationAmount) },
  ];
}

function transaction(destinationAmount = "900000") {
  return {
    slot: 123,
    blockTime: NOW / 1000,
    meta: {
      err: null,
      fee: 5_000,
      preTokenBalances: [tokenBalance(0, OWNER, SOURCE_MINT, "1000000"), tokenBalance(1, OWNER, DESTINATION_MINT, "0")],
      postTokenBalances: [tokenBalance(0, OWNER, SOURCE_MINT, "0"), tokenBalance(1, OWNER, DESTINATION_MINT, destinationAmount)],
    },
  };
}

function intent(overrides = {}) {
  return {
    intentId: "intent-live-1",
    mode: "live",
    liveGate: true,
    owner: OWNER,
    mint: DESTINATION_MINT,
    sourceMint: SOURCE_MINT,
    destinationMint: DESTINATION_MINT,
    sourceRawAmount: "1000000",
    destinationRawAmount: "900000",
    amountUsd: 2,
    sourceSignature: "source-copy-1",
    createdAtMs: NOW,
    ...overrides,
  };
}

const quote = {
  inputMint: SOURCE_MINT,
  outputMint: DESTINATION_MINT,
  inAmount: "1000000",
  outAmount: "900000",
  priceImpactPct: 0.1,
};

function clientsFor({ after = balances("0", "900000") } = {}) {
  const calls = { send: 0, confirm: 0, readTransaction: 0, readBalances: [] };
  const clients = {
    async build() { return { unsigned: true }; },
    async send() { calls.send += 1; return "live-signature-1"; },
    async confirm() { calls.confirm += 1; return { confirmed: true }; },
    async readTransaction() { calls.readTransaction += 1; return transaction(after[1].rawAmount); },
    async readBalances({ phase }) {
      calls.readBalances.push(phase);
      return phase === "before" ? balances("1000000", "0") : after;
    },
  };
  return { clients, calls };
}

function wallet() {
  return { publicKey: OWNER, async signTransaction(value) { return { ...value, signed: true }; } };
}

async function journalPath() {
  const directory = await mkdtemp(path.join(os.tmpdir(), "sol-copy-live-"));
  return path.join(directory, "journal.jsonl");
}

async function withLiveGate(value, fn) {
  const previous = process.env.SOL_COPY_LIVE;
  if (value == null) delete process.env.SOL_COPY_LIVE;
  else process.env.SOL_COPY_LIVE = value;
  try { return await fn(); } finally {
    if (previous == null) delete process.env.SOL_COPY_LIVE;
    else process.env.SOL_COPY_LIVE = previous;
  }
}

test("read-only and paper modes never call send", async () => {
  for (const mode of ["read_only", "paper"]) {
    const journal = await journalPath();
    const { clients, calls } = clientsFor();
    const result = await withLiveGate("1", () => executeCanary(intent({ mode }), quote, wallet(), clients, journal));
    assert.equal(result.status, "rejected");
    assert.equal(result.reason, "live_mode_required");
    assert.equal(calls.send, 0);
  }
});

test("live mode rejects when SOL_COPY_LIVE=1 is missing", async () => {
  const journal = await journalPath();
  const { clients, calls } = clientsFor();
  const result = await withLiveGate(null, () => executeCanary(intent(), quote, wallet(), clients, journal));

  assert.equal(result.status, "rejected");
  assert.equal(result.reason, "live_gate_missing");
  assert.equal(calls.send, 0);
  assert.deepEqual(await readRows(journal), []);
});

test("live mode rejects any intent above the exact $2 canary size", async () => {
  const journal = await journalPath();
  const { clients, calls } = clientsFor();
  const result = await withLiveGate("1", () => executeCanary(intent({ amountUsd: 4 }), quote, wallet(), clients, journal));

  assert.equal(result.status, "rejected");
  assert.equal(result.reason, "fixed_notional_required");
  assert.equal(calls.send, 0);
  assert.deepEqual(await readRows(journal), []);
});

test("confirmed matching token deltas produce a verified receipt", async () => {
  const journal = await journalPath();
  const { clients, calls } = clientsFor();
  const result = await withLiveGate("1", () => executeCanary(intent(), quote, wallet(), clients, journal));
  const rows = await readRows(journal);

  assert.equal(result.status, "verified");
  assert.equal(result.signature, "live-signature-1");
  assert.equal(result.feeLamports, 5_000);
  assert.equal(calls.send, 1);
  assert.equal(calls.confirm, 1);
  assert.equal(calls.readTransaction, 1);
  assert.deepEqual(calls.readBalances, ["before", "after"]);
  assert.deepEqual(rows.map((row) => row.kind), ["intent", "receipt"]);
  assert.equal(rows[1].status, "verified");
});

test("a confirmed mismatched delta becomes effect_unknown without retry", async () => {
  const journal = await journalPath();
  const { clients, calls } = clientsFor({ after: balances("0", "800000") });
  const result = await withLiveGate("1", () => executeCanary(intent(), quote, wallet(), clients, journal));
  const rows = await readRows(journal);

  assert.equal(result.status, "effect_unknown");
  assert.equal(result.reason, "token_delta_mismatch");
  assert.equal(calls.send, 1);
  assert.equal(calls.confirm, 1);
  assert.equal(rows[1].status, "effect_unknown");
  assert.equal(rows[1].retry, false);
});

