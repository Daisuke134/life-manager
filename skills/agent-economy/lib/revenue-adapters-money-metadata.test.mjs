import assert from "node:assert/strict";
import { test } from "node:test";

import { adaptX402WithEvmVerifier } from "./revenue-adapters.mjs";

const TX = `0x${"11".repeat(32)}`;
const PAYER = "0x1111111111111111111111111111111111111111";
const RECIPIENT = "0x2222222222222222222222222222222222222222";
const USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913";
const TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";

function topicAddress(address) {
  return `0x${address.slice(2).padStart(64, "0")}`;
}

function fakeRpc() {
  return async (_url, init) => {
    const { method } = JSON.parse(init.body);
    const result = method === "eth_chainId" ? "0x2105" : {
      status: "0x1",
      transactionHash: TX,
      logs: [{
        address: USDC,
        transactionHash: TX,
        logIndex: "0x0",
        topics: [TRANSFER_TOPIC, topicAddress(PAYER), topicAddress(RECIPIENT)],
        data: "0xbb8",
      }],
    };
    return { ok: true, json: async () => ({ result }) };
  };
}

test("x402 refuses a verified transfer when fee or refund metadata is absent", async () => {
  const row = {
    source_record_id: "x402-missing-components",
    provider: "x402",
    settled: true,
    amount_atomic: "3000",
    decimals: 6,
    currency: "USDC",
    payer: PAYER,
    recipient: RECIPIENT,
    transaction: TX,
    chain_id: 8453,
    occurred_at: "2026-10-12T00:00:00.000Z",
  };
  const result = await adaptX402WithEvmVerifier(row, {
    rpc: "https://rpc.invalid",
    fetchImpl: fakeRpc(),
  });
  assert.equal(result.ok, false);
  assert.equal(result.rejection.code, "MISSING_SETTLEMENT_COMPONENT");
});

test("x402 accepts explicit zero fee and refund after strict transfer verification", async () => {
  const row = {
    source_record_id: "x402-explicit-zero-components",
    provider: "x402",
    settled: true,
    amount_atomic: "3000",
    decimals: 6,
    currency: "USDC",
    payer: PAYER,
    recipient: RECIPIENT,
    transaction: TX,
    chain_id: 8453,
    fee: "0",
    refund: "0",
    occurred_at: "2026-10-12T00:00:00.000Z",
  };
  const result = await adaptX402WithEvmVerifier(row, {
    rpc: "https://rpc.invalid",
    fetchImpl: fakeRpc(),
  });
  assert.equal(result.ok, true);
  assert.equal(result.receipt.fee_decimal, "0");
  assert.equal(result.receipt.refund_decimal, "0");
});
