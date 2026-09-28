import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";

import { readRows } from "./journal.mjs";
import { wake } from "./run.mjs";
import { paperApply } from "./paper.mjs";

const NOW = 1_700_000_000_000;
const MINT = "TokenMint11111111111111111111111111111111111";

function candidate(signature = "source-run-1") {
  return {
    sourceSignature: signature,
    sourceMint: "So11111111111111111111111111111111111111112",
    destinationMint: MINT,
    sourceRawAmount: "1000000",
    destinationRawAmount: "900000",
    observedAtMs: NOW - 1_000,
    quoteObservedAtMs: NOW - 1_000,
    market: {
      gmgn: { priceUsd: 1, liquidityUsd: 100_000 },
      dexscreener: { priceUsd: 1, liquidityUsd: 100_000 },
      jupiter: { outAmount: "900000", priceImpactPct: 0.1 },
    },
  };
}

async function journalPath() {
  const directory = await mkdtemp(path.join(os.tmpdir(), "sol-copy-run-"));
  return path.join(directory, "journal.jsonl");
}

function clients({ sourceSignature = "source-run-1", executeResult = null } = {}) {
  const calls = { scout: 0, paper: 0, live: 0 };
  const adapters = {};
  return {
    calls,
    adapters,
    async scout() { calls.scout += 1; return { status: "ok", candidates: [candidate(sourceSignature)], evidence: [] }; },
    decide(snapshot) {
      return { action: "copy_entry", mint: snapshot.destinationMint, amountUsd: 2, reason: "test_copy", sourceSignature: snapshot.sourceSignature };
    },
    quoteFor() {
      return {
        inputMint: "So11111111111111111111111111111111111111112",
        outputMint: MINT,
        inAmount: "1000000",
        outAmount: "900000",
        simulatedFeeUsd: 0.01,
        simulatedSlippageUsd: 0.02,
      };
    },
    async paperApply() { calls.paper += 1; return { status: "paper", effect: "none", intentId: "paper" }; },
    async executeCanary() { calls.live += 1; return executeResult || { status: "verified", effect: "verified", signature: "live" }; },
  };
}

test("wake reports each explicit stage and never calls live in read-only or paper", async () => {
  const readJournal = await journalPath();
  const readClients = clients();
  const read = await wake({ mode: "read_only", liveGate: false, targets: [{ address: "target" }], clients: readClients, journalPath: readJournal, nowMs: NOW });
  assert.equal(read.stage, "read_only");
  assert.equal(readClients.calls.live, 0);
  assert.equal(readClients.calls.paper, 0);

  const paperJournal = await journalPath();
  const paperClients = clients();
  const paper = await wake({ mode: "paper", liveGate: false, targets: [{ address: "target" }], clients: paperClients, journalPath: paperJournal, nowMs: NOW });
  assert.equal(paper.stage, "paper");
  assert.equal(paper.receipt.status, "paper");
  assert.equal(paperClients.calls.live, 0);
  assert.equal(paperClients.calls.paper, 1);
});

test("wake is daily-idempotent and does not advance mode automatically", async () => {
  const journal = await journalPath();
  const testClients = clients();
  const first = await wake({ mode: "read_only", liveGate: false, targets: [{ address: "target" }], clients: testClients, journalPath: journal, nowMs: NOW });
  const second = await wake({ mode: "read_only", liveGate: false, targets: [{ address: "target" }], clients: testClients, journalPath: journal, nowMs: NOW + 1_000 });
  const rows = await readRows(journal);

  assert.equal(first.stage, "read_only");
  assert.equal(second.stage, "read_only");
  assert.equal(rows.filter((row) => row.kind === "daily_report").length, 1);
});

test("wake fences a terminal effect_unknown and never retries live", async () => {
  const journal = await journalPath();
  const testClients = clients({ executeResult: { status: "effect_unknown", effect: "unknown", reason: "token_delta_mismatch" } });
  const first = await wake({ mode: "live", liveGate: true, targets: [{ address: "target" }], clients: testClients, journalPath: journal, nowMs: NOW });
  const second = await wake({ mode: "live", liveGate: true, targets: [{ address: "target" }], clients: testClients, journalPath: journal, nowMs: NOW + 1_000 });

  assert.equal(first.stage, "live");
  assert.equal(first.receipt.status, "effect_unknown");
  assert.equal(second.stage, "fenced");
  assert.equal(second.decision.reason, "effect_unknown_fence");
  assert.equal(testClients.calls.live, 1);
});

test("wake evaluates a held position before considering a new entry", async () => {
  const journal = await journalPath();
  const position = {
    mint: MINT,
    amountRaw: "900000",
    entryPriceUsd: 1,
    entryAtMs: NOW - 1_000,
    sourceSignature: "source-run-entry-1",
    exitMint: "So11111111111111111111111111111111111111112",
  };
  const result = await wake({
    mode: "paper",
    liveGate: false,
    targets: [{ address: "target" }],
    clients: {
      async scout() {
        return { status: "ok", candidates: [candidate("new-source-must-not-enter")] };
      },
      position,
      exitSnapshot: { currentPriceUsd: 0.69 },
      risk: { nowMs: NOW, hardStopPct: 0.30, maxHoldMs: 24 * 60 * 60 * 1000 },
      exitQuoteFor() {
        return {
          inputMint: MINT,
          outputMint: position.exitMint,
          inAmount: position.amountRaw,
          outAmount: "600000",
          priceImpactPct: 0.2,
          simulatedFeeUsd: 0.01,
          simulatedSlippageUsd: 0.02,
        };
      },
      paperApply,
    },
    journalPath: journal,
    nowMs: NOW,
  });
  const rows = await readRows(journal);

  assert.equal(result.decision.action, "stop_exit");
  assert.equal(result.receipt.status, "paper");
  assert.equal(result.receipt.action, "stop_exit");
  assert.equal(rows.filter((row) => row.kind === "intent")[0].action, "stop_exit");
});
