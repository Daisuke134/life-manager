"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { createX402CostObserver } = require("./x402-cost-observer.js");
const {
  buildAgentEconomyEconomicSourceBundle,
} = require("./agent-economy-economic-source.js");

function headers(values) {
  return { get: (name) => values[name.toLowerCase()] || null };
}

async function fixture() {
  const revenueModule = await import("../../../skills/agent-economy/lib/revenue-receipt.mjs");
  const receipt = revenueModule.normalizeRevenueReceipt({
    provider: "x402", payer: "buyer", recipient: "seller",
    gross: "1.25", fee: "0.05", refund: "0", asset: "USDC",
    terminal_state: "settled", occurred_at: "2026-09-24T01:00:00Z",
    proof: { chain_id: 8453, tx_hash: `0x${"a".repeat(64)}`, log_index: 1, verified: true },
  });
  const financialAdapter = await import("../../../skills/agent-economy/lib/financial-record-adapter.mjs");
  const revenueRecords = financialAdapter.revenueReceiptToFinancialRecords(receipt, {
    subjectId: "tenant-a", recordedAt: "2026-09-24T02:00:00Z",
  });
  const costs = [];
  const observer = createX402CostObserver({
    subjectId: "tenant-a", now: () => "2026-09-24T02:00:00Z",
    store: { append: async (record) => { costs.push(record); return { created: true }; } },
  });
  const requirement = Buffer.from(JSON.stringify({
    resource: { url: "https://blockrun.ai/api/v1/chat/completions" },
    accepts: [{ amount: "1234", network: "eip155:8453",
      asset: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" }],
  })).toString("base64");
  const url = "https://blockrun.ai/api/v1/chat/completions";
  const body = JSON.stringify({ model: "test" });
  await observer.observe(url, { body, headers: {} }, {
    status: 402, ok: false, headers: headers({ "payment-required": requirement }),
  });
  await observer.observe(url, { body, headers: { "payment-signature": "signed" } }, {
    status: 200, ok: true, headers: headers({ "payment-response": "settled-compute-receipt" }),
  });
  return { receipts: [receipt], revenueRecords, costRecords: costs };
}

test("projects verified x402 revenue and compute receipts into deterministic economic sources", async () => {
  const input = {
    subjectId: "tenant-a", observedAt: "2026-09-24T02:00:00Z",
    revenueReadState: "observed", costReadState: "observed",
    ...(await fixture()),
  };
  const first = await buildAgentEconomyEconomicSourceBundle(input);
  const replay = await buildAgentEconomyEconomicSourceBundle(input);

  assert.deepEqual(replay, first);
  assert.deepEqual(first.sourceObservations.map((row) => [
    row.source_kind, row.adapter, row.state,
  ]), [
    ["funnel", "agent-economy-revenue-receipt", "observed_verified"],
    ["financial", "agent-economy-financial-record", "observed_verified"],
    ["cost", "x402-cost-observer", "observed_verified"],
  ]);
  assert.equal(first.funnelObservations.length, 1);
  assert.deepEqual([
    first.funnelObservations[0].stage,
    first.funnelObservations[0].state,
    first.funnelObservations[0].count,
  ], ["payment", "observed_verified", 1]);
  assert.equal(first.sourceObservations.every((row) => row.provider_receipt_ids.length === 1), true);
});

test("missing inputs remain explicit and never become zero revenue or zero cost", async () => {
  const result = await buildAgentEconomyEconomicSourceBundle({
    subjectId: "tenant-a", observedAt: "2026-09-24T02:00:00Z",
    revenueReadState: "not_configured", costReadState: "observed",
    receipts: [], revenueRecords: [], costRecords: [],
  });

  assert.deepEqual(result.sourceObservations.map((row) => [row.source_kind, row.state]), [
    ["funnel", "not_configured"],
    ["financial", "not_configured"],
    ["cost", "unavailable"],
  ]);
  assert.deepEqual([
    result.funnelObservations[0].state,
    result.funnelObservations[0].count,
  ], ["not_configured", null]);
});

test("unsupported revenue input fails closed instead of manufacturing source coverage", async () => {
  await assert.rejects(() => buildAgentEconomyEconomicSourceBundle({
    subjectId: "tenant-a", observedAt: "2026-09-24T02:00:00Z",
    revenueReadState: "observed", costReadState: "unavailable",
    receipts: [{ provider: "x402", estimated_revenue: 100 }],
    revenueRecords: [], costRecords: [],
  }), /verified|normalized|receipt/i);
});
