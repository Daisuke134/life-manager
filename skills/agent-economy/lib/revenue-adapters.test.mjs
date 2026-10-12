import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { promisify } from "node:util";

import {
  adaptCoconala,
  adaptLancers,
  adaptTaskMarket,
  adaptX402,
  adaptX402WithEvmVerifier,
  adaptWriterStripe,
  projectRevenueReceipts,
} from "./revenue-adapters.mjs";
import * as AdapterModule from "./revenue-adapters.mjs";
import { runTaskMarketPass } from "../../earn/taskmarket/taskmarket-work.mjs";

const RECIPIENT = "acct_life_manager_instance_01";
const PAYER = "customer_external_01";
const EVM_PAYER = "0x1111111111111111111111111111111111111111";
const EVM_RECIPIENT = "0x2222222222222222222222222222222222222222";
const BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const topicAddress = (address) => `0x${address.slice(2).padStart(64, "0")}`;
const NOW = "2026-08-27T00:00:00.000Z";
const execFileAsync = promisify(execFile);

test("adapter does not export a forgeable trusted-proof wrapper", () => {
  assert.equal("createTrustedReadbackVerifier" in AdapterModule, false);
});

function squarePng() {
  const png = Buffer.alloc(33);
  Buffer.from("89504e470d0a1a0a", "hex").copy(png, 0);
  png.writeUInt32BE(13, 8); Buffer.from("IHDR").copy(png, 12);
  png.writeUInt32BE(1024, 16); png.writeUInt32BE(1024, 20); png[24] = 8; png[25] = 2;
  return png;
}

function successfulEvmReceipt({ tx, payer = EVM_PAYER, recipient = EVM_RECIPIENT, contract = BASE_USDC, amount = "3000", logIndex = "0x0", extraLogs = [] } = {}) {
  return {
    status: "0x1", transactionHash: tx,
    logs: [{
      address: contract, transactionHash: tx, logIndex,
      topics: [TRANSFER_TOPIC, topicAddress(payer), topicAddress(recipient)],
      data: `0x${BigInt(amount).toString(16).padStart(64, "0")}`,
    }, ...extraLogs],
  };
}

function fakeRpc({ tx, receipt, chainId = "0x2105", calls = [] }) {
  return async (_url, init) => {
    const body = JSON.parse(init.body);
    calls.push(body);
    if (body.method === "eth_chainId") return { ok: true, json: async () => ({ result: chainId }) };
    if (body.method === "eth_getTransactionReceipt") return { ok: true, json: async () => ({ result: receipt || successfulEvmReceipt({ tx }) }) };
    throw new Error(`unexpected RPC method ${body.method}`);
  };
}

function accepted(result) {
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.rejection, undefined);
  return result.receipt;
}

function rejected(result, reason) {
  assert.equal(result.ok, false, JSON.stringify(result));
  assert.equal(result.receipt, undefined);
  assert.match(`${result.rejection.reason} ${result.rejection.code}`, new RegExp(reason, "i"));
  assert.equal(result.rejection.kind, "revenue_rejection");
  return result.rejection;
}

test("Coconala mapping remains rejection-only until an official provider verifier exists", () => {
  const result = adaptCoconala({
    source_record_id: "coconala-payout-1",
    requestId: "90000001",
    status: "検収完了",
    gross_jpy: 10000,
    fee_jpy: 2200,
    payout_jpy: 7800,
    payer: PAYER,
    recipient: RECIPIENT,
    payout_status: "paid",
    payout_receipt_id: "coconala-payout-1",
    payout_proof_verified: true,
    ts: NOW,
  });
  assert.equal(result.ok, false);
  assert.match(result.rejection.code + result.rejection.reason, /VERIFIER|rejection|non-revenue/i);
});

test("Coconala net-only sales and payout-requested UI are durable rejections", () => {
  rejected(adaptCoconala({
    requestId: "90000002", status: "検収完了", jpy: 7800, net_of_fee: true,
    payout_requested: true, evidence: "https://coconala.example/revenue", ts: NOW,
    payer: PAYER, recipient: RECIPIENT,
  }), "settlement|gross|payout");
});

test("Lancers mapping remains rejection-only until an official provider verifier exists", () => {
  const result = adaptLancers({
    source_record_id: "lancers-payment-1",
    proposal_id: "lancers-project-1",
    status: "paid",
    gross_jpy: 20000,
    fee_jpy: 2000,
    payer: "lancers-client-1",
    recipient: RECIPIENT,
    payment_receipt_id: "lancers-payment-1",
    payment_proof_verified: true,
    occurred_at: NOW,
  });
  assert.equal(result.ok, false);
  assert.match(result.rejection.code + result.rejection.reason, /VERIFIER|rejection|non-revenue/i);
  rejected(adaptLancers({
    provider_id: "lancers-project-2", status: "working", gross_jpy: 20000,
    fee_jpy: 2000, payer: "lancers-client-2", recipient: RECIPIENT, occurred_at: NOW,
  }), "settlement|proof|trusted|unavailable");
});

test("TaskMarket never treats submitTxHash or an unverified award id as payment proof", () => {
  rejected(adaptTaskMarket({
    taskId: "0x" + "1".repeat(64), submissionId: "submission-1",
    submitTxHash: "0x" + "2".repeat(64), status: "submitted",
    netReward: "5000000", payer: PAYER, recipient: RECIPIENT, occurred_at: NOW,
  }), "award|settlement|proof");

  const award = adaptTaskMarket({
    source_record_id: "taskmarket-award-1",
    taskId: "0x" + "3".repeat(64), submissionId: "submission-2", status: "awarded",
    gross_atomic: "5000000", fee_atomic: "250000", asset: "USDC", decimals: 6,
    payer: PAYER, recipient: RECIPIENT, award_receipt_id: "taskmarket-award-1",
    award_proof_verified: true, occurred_at: NOW,
  });
  assert.equal(award.ok, false);
  assert.match(award.rejection.code + award.rejection.reason, /VERIFIER|non-revenue/i);
});

test("x402 synchronous mapping never accepts a facilitator header without strict verifier", () => {
  const result = adaptX402({
    source_record_id: "x402-tx-1",
    route: "/research", settled: true, success: true,
    amount: "$0.003", currency: "USDC", payer: PAYER, recipient: RECIPIENT,
    transaction: "0x" + "4".repeat(64), chain_id: 8453, log_index: 0,
    settlement_verified: true, ts: NOW,
    amount_atomic: "3000", decimals: 6,
  });
  assert.equal(result.ok, false);
  assert.match(result.rejection.code + result.rejection.reason, /strict|verifier|rejection/i);
  rejected(adaptX402({
    route: "/research", settled: true, success: true, amount: "$0.003", currency: "USDC",
    payer: PAYER, recipient: RECIPIENT, ts: NOW,
  }), "proof|decimals|strict|unavailable");
  rejected(adaptX402({
    route: "/research", settled: true, success: true, amount: "$0.003", currency: "USD!",
    payer: PAYER, recipient: RECIPIENT, transaction: "0x" + "5".repeat(64), chain_id: 8453,
    log_index: 0, settlement_verified: true, ts: NOW,
  }), "currency|strict|unavailable");
  rejected(adaptX402({
    route: "/research", settled: true, success: true, amount: "$0.003", currency: "USDC",
    payer: RECIPIENT, recipient: RECIPIENT, transaction: "0x" + "6".repeat(64), chain_id: 8453,
    log_index: 0, settlement_verified: true, ts: NOW,
  }), "self|strict|unavailable");
});

test("Writer/Stripe joins settled money with its fee, emits refund correction, and rejects tests/pending/unjoined rows", () => {
  const rows = [
    { receipt_type: "money", kind: "sale", amount: 10, currency: "USD", status: "verified_received", test: false, external_receipt_id: "pi_1", payer: PAYER, recipient: RECIPIENT, occurred_at: NOW, provider_receipt_id: "pi_1", proof_verified: true },
    { receipt_type: "fee", amount: 0.3, currency: "USD", status: "verified", test: false, money_external_receipt_id: "pi_1", external_receipt_id: "txn_1", provider_receipt_id: "txn_1", proof_verified: true, occurred_at: NOW },
    { receipt_type: "refund", amount: 2, currency: "USD", status: "refunded", test: false, external_receipt_id: "re_1", money_external_receipt_id: "pi_1", provider_receipt_id: "re_1", proof_verified: true, occurred_at: NOW },
  ];
  const result = adaptWriterStripe(rows, {
    payer: PAYER,
    recipient: RECIPIENT,
  });
  assert.equal(result.accepted.length, 0);
  assert.equal(result.rejected.length, 2);
  assert.ok(result.rejected.every((row) => /VERIFIER|rejection|non-revenue/i.test(row.code + row.reason)));

  const pending = adaptWriterStripe([
    { receipt_type: "money", kind: "sale", amount: 10, currency: "USD", status: "observed", test: false, external_receipt_id: "pi_pending", occurred_at: NOW },
  ], { payer: PAYER, recipient: RECIPIENT });
  assert.equal(pending.accepted.length, 0);
  assert.equal(pending.rejected.length, 1);
  assert.match(pending.rejected[0].reason, /settled|pending/i);

  const wrongLineage = adaptWriterStripe([
    { receipt_type: "money", kind: "sale", amount: 10, currency: "USD", status: "verified_received", test: false, external_receipt_id: "pi_exact", payer: PAYER, recipient: RECIPIENT, occurred_at: NOW },
    { receipt_type: "fee", amount: 0.3, currency: "USD", status: "verified", test: false, money_external_receipt_id: "pi_exact", external_receipt_id: "txn_exact", occurred_at: NOW },
    { receipt_type: "refund", amount: 2, currency: "USD", status: "refunded", test: false, money_external_receipt_id: "pi_other", artifact_id: "same-artifact", run_id: "same-run", external_receipt_id: "re_wrong", occurred_at: NOW },
  ], {
    payer: PAYER,
    recipient: RECIPIENT,
  });
  assert.equal(wrongLineage.accepted.length, 0);
  assert.ok(wrongLineage.rejected.length >= 1);
});

test("projectRevenueReceipts appends accepted rows once and persists rejection rows", async () => {
  const root = await mkdtemp(join(tmpdir(), "revenue-adapters-"));
  const journalPath = join(root, "revenue-receipts.jsonl");
  const rejectionPath = join(root, "revenue-rejections.jsonl");
  const tx = "0x" + "7".repeat(64);
  const rows = [{
    provider: "x402", route: "/research", settled: true, success: true,
    amount_atomic: "3000", decimals: 6, currency: "USDC", payer: EVM_PAYER, recipient: EVM_RECIPIENT,
    transaction: tx, chain_id: 8453, fee: "0", refund: "0", ts: NOW,
  }, {
    provider: "x402", route: "/research", settled: false, success: false,
    amount_atomic: "3000", decimals: 6, currency: "USDC", payer: EVM_PAYER, recipient: EVM_RECIPIENT, ts: NOW,
  }];
  const first = await projectRevenueReceipts({ journalPath, rejectionPath, provider: "x402", rows, options: { rpc: "https://rpc.invalid", fetchImpl: fakeRpc({ tx, receipt: successfulEvmReceipt({ tx }) }) } });
  assert.equal(first.accepted, 1);
  assert.equal(first.rejected, 1);
  assert.equal(first.duplicates, 0);
  const second = await projectRevenueReceipts({ journalPath, rejectionPath, provider: "x402", rows, options: { rpc: "https://rpc.invalid", fetchImpl: fakeRpc({ tx, receipt: successfulEvmReceipt({ tx }) }) } });
  assert.equal(second.accepted, 0);
  assert.equal(second.duplicates, 1);
  assert.equal(second.rejected, 1);
  assert.equal((await readFile(journalPath, "utf8")).trim().split("\n").length, 1);
  assert.equal((await readFile(rejectionPath, "utf8")).trim().split("\n").length, 1);
});

test("raw proof ids and verification booleans cannot bypass the trusted readback boundary", () => {
  const forged = adaptX402({
    source_record_id: "forged-1", route: "/research", settled: true, success: true,
    amount_atomic: "3000", decimals: 6, currency: "USDC", payer: PAYER, recipient: RECIPIENT,
    transaction: "0x" + "8".repeat(64), chain_id: 8453, log_index: 0,
    proof: { provider_receipt_id: "fake-provider-receipt", verified: true }, settlement_verified: true, ts: NOW,
  });
  rejected(forged, "trusted|proof|strict|unavailable");
});

test("a Stripe dashboard URL and external id are not trusted proof", () => {
  const result = adaptWriterStripe([
    { receipt_type: "money", kind: "sale", amount: 10, currency: "USD", status: "verified_received", test: false, external_receipt_id: "pi_fake", source_url: "https://dashboard.stripe.com/payments/pi_fake", payer: PAYER, recipient: RECIPIENT, occurred_at: NOW },
    { receipt_type: "fee", amount: 0.3, currency: "USD", status: "verified", test: false, money_external_receipt_id: "pi_fake", external_receipt_id: "txn_fake", source_url: "https://dashboard.stripe.com/balance/txn_fake", occurred_at: NOW },
  ], { payer: PAYER, recipient: RECIPIENT });
  assert.equal(result.accepted.length, 0);
  assert.equal(result.rejected.length, 1);
  assert.match(result.rejected[0].reason + result.rejected[0].code, /trusted|proof|unavailable/i);
});

test("x402 atomic amount 3000 at six decimals is 0.003 and needs chain proof", () => {
  const result = adaptX402({
    source_record_id: "x402-atomic", route: "/research", settled: true, success: true,
    amount_atomic: "3000", decimals: 6, currency: "USDC", payer: PAYER, recipient: RECIPIENT,
    transaction: "0x" + "9".repeat(64), chain_id: 8453, log_index: 0, ts: NOW,
  });
  assert.equal(result.ok, false);
});

test("x402 production adapter calls strict EVM verifier with exact transfer tuple", async () => {
  const payer = EVM_PAYER;
  const recipient = EVM_RECIPIENT;
  const tx = "0x" + "d".repeat(64);
  const receipt = successfulEvmReceipt({ tx, payer, recipient, logIndex: "0x4" });
  const calls = [];
  const result = await adaptX402WithEvmVerifier({
    source_record_id: "x402-strict", settled: true, success: true, amount_atomic: "3000", decimals: 6,
    currency: "USDC", payer, recipient, transaction: tx, chain_id: 8453, fee: "0", refund: "0", ts: NOW,
  }, { rpc: "https://rpc.invalid", fetchImpl: fakeRpc({ tx, receipt, calls }) });
  assert.equal(result.ok, true);
  assert.equal(result.receipt.gross, 0.003);
  assert.equal(result.receipt.proof.log_index, 4);
  assert.ok(calls.some((call) => call.method === "eth_getTransactionReceipt" && call.params[0] === tx));
  assert.ok(calls.some((call) => call.method === "eth_chainId"));
  assert.equal(calls.filter((call) => call.method === "eth_getTransactionReceipt").length, 1);
});

test("x402 hardcodes Base USDC decimals to six and rejects conflicting decimals", async () => {
  const tx = "0x" + "f".repeat(64);
  const row = { source_record_id: "x402-decimals", settled: true, success: true, amount_atomic: "3000", decimals: 3, currency: "USDC", payer: EVM_PAYER, recipient: EVM_RECIPIENT, transaction: tx, chain_id: 8453, fee: "0", refund: "0", ts: NOW };
  const result = await adaptX402WithEvmVerifier(row, { rpc: "https://rpc.invalid", fetchImpl: fakeRpc({ tx, receipt: successfulEvmReceipt({ tx }) }) });
  assert.equal(result.ok, false);
  const correct = await adaptX402WithEvmVerifier({ ...row, decimals: 6 }, { rpc: "https://rpc.invalid", fetchImpl: fakeRpc({ tx, receipt: successfulEvmReceipt({ tx }) }) });
  assert.equal(correct.ok, true);
  assert.equal(correct.receipt.gross, 0.003);
});

test("standard x402 response without amount/currency/decimals/log uses the configured route price", async () => {
  const tx = "0x" + "c".repeat(64);
  const result = await adaptX402WithEvmVerifier({
    source_record_id: "x402-standard", settled: true, success: true,
    payer: EVM_PAYER, recipient: EVM_RECIPIENT, transaction: tx, network: "eip155:8453", fee: "0", refund: "0", ts: NOW,
  }, {
    configuredPrice: "$0.003", configuredNetwork: "eip155:8453",
    rpc: "https://rpc.invalid", fetchImpl: fakeRpc({ tx, receipt: successfulEvmReceipt({ tx }) }),
  });
  assert.equal(result.ok, true);
  assert.equal(result.receipt.gross, 0.003);
});

test("configured x402 price binds any supplied atomic amount and transfer", async () => {
  const tx = "0x" + "1".repeat(64);
  const mismatch = await adaptX402WithEvmVerifier({
    source_record_id: "x402-price-mismatch", settled: true, success: true, amount_atomic: "3000", decimals: 6,
    currency: "USDC", payer: EVM_PAYER, recipient: EVM_RECIPIENT, transaction: tx, network: "eip155:8453", fee: "0", refund: "0", ts: NOW,
  }, {
    configuredPrice: "$0.004", configuredNetwork: "eip155:8453", rpc: "https://rpc.invalid",
    fetchImpl: fakeRpc({ tx, receipt: successfulEvmReceipt({ tx, amount: "3000" }) }),
  });
  assert.equal(mismatch.ok, false);
  const correct = await adaptX402WithEvmVerifier({
    source_record_id: "x402-price-match", settled: true, success: true, amount_atomic: "3000", decimals: 6,
    currency: "USDC", payer: EVM_PAYER, recipient: EVM_RECIPIENT, transaction: tx, network: "eip155:8453", fee: "0", refund: "0", ts: NOW,
  }, {
    configuredPrice: "$0.003", configuredNetwork: "eip155:8453", rpc: "https://rpc.invalid",
    fetchImpl: fakeRpc({ tx, receipt: successfulEvmReceipt({ tx, amount: "3000" }) }),
  });
  assert.equal(correct.ok, true);
});

test("strict x402 transport rejects amount, payer, recipient, contract, chain, and ambiguous log mismatches", async () => {
  const tx = "0x" + "e".repeat(64);
  const base = { source_record_id: "x402-mismatch", settled: true, success: true, amount_atomic: "3000", decimals: 6, currency: "USDC", payer: EVM_PAYER, recipient: EVM_RECIPIENT, transaction: tx, chain_id: 8453, fee: "0", refund: "0", ts: NOW };
  const run = (row, receipt, chainId = "0x2105") => adaptX402WithEvmVerifier(row, { rpc: "https://rpc.invalid", fetchImpl: fakeRpc({ tx, receipt, chainId }) });
  assert.equal((await run({ ...base, amount_atomic: "3001" }, successfulEvmReceipt({ tx }))).ok, false);
  assert.equal((await run({ ...base, payer: "0x3333333333333333333333333333333333333333" }, successfulEvmReceipt({ tx }))).ok, false);
  assert.equal((await run({ ...base, recipient: "0x4444444444444444444444444444444444444444" }, successfulEvmReceipt({ tx }))).ok, false);
  assert.equal((await run({ ...base, currency: "DAI" }, successfulEvmReceipt({ tx }))).ok, false);
  assert.equal((await run({ ...base, settled: false, success: false }, successfulEvmReceipt({ tx }))).ok, false);
  assert.equal((await run(base, successfulEvmReceipt({ tx, contract: "0x5555555555555555555555555555555555555555" }))).ok, false);
  assert.equal((await run(base, successfulEvmReceipt({ tx }), "0x1")).ok, false);
  const duplicate = successfulEvmReceipt({ tx, extraLogs: [successfulEvmReceipt({ tx, logIndex: "0x1" }).logs[0]] });
  assert.equal((await run(base, duplicate)).ok, false);
});

test("twenty concurrent projections append one receipt and one rejection", async () => {
  const root = await mkdtemp(join(tmpdir(), "revenue-adapters-concurrent-"));
  const journalPath = join(root, "journal.jsonl");
  const rejectionPath = join(root, "rejections.jsonl");
  const tx = "0x" + "a".repeat(64);
  const rows = [{ source_record_id: "concurrent-1", provider: "x402", settled: true, success: true, amount_atomic: "3000", decimals: 6, currency: "USDC", payer: EVM_PAYER, recipient: EVM_RECIPIENT, transaction: tx, chain_id: 8453, fee: "0", refund: "0", ts: NOW }, { source_record_id: "concurrent-bad", provider: "x402", settled: false, success: false, amount_atomic: "3000", decimals: 6, currency: "USDC", payer: EVM_PAYER, recipient: EVM_RECIPIENT, ts: NOW }];
  const receipt = successfulEvmReceipt({ tx });
  await Promise.all(Array.from({ length: 20 }, () => projectRevenueReceipts({ journalPath, rejectionPath, provider: "x402", rows, options: { rpc: "https://rpc.invalid", fetchImpl: fakeRpc({ tx, receipt }) } })));
  assert.equal((await readFile(journalPath, "utf8")).trim().split("\n").length, 1);
  assert.equal((await readFile(rejectionPath, "utf8")).trim().split("\n").length, 1);
});

test("deterministic CLI projection of a raw lane outbox records rejection without a verifier", async () => {
  const root = await mkdtemp(join(tmpdir(), "revenue-adapters-cli-"));
  const source = join(root, "x402-sales.jsonl");
  const journalPath = join(root, "journal.jsonl");
  const rejectionPath = join(root, "rejections.jsonl");
  await writeFile(source, `${JSON.stringify({
    source_record_id: "cli-raw", settled: true, success: true, amount_atomic: "3000", decimals: 6,
    currency: "USDC", payer: PAYER, recipient: RECIPIENT,
    transaction: "0x" + "b".repeat(64), chain_id: 8453, log_index: 0,
    proof: { provider_receipt_id: "forged-by-outbox", verified: true }, proof_verified: true, ts: NOW,
  })}\n`);
  const { stdout } = await execFileAsync(process.execPath, [
    "skills/agent-economy/lib/revenue-adapters.mjs", "--provider", "x402", "--rows", source,
    "--journal", journalPath, "--rejections", rejectionPath,
  ], { cwd: process.cwd(), timeout: 5000 });
  const result = JSON.parse(stdout);
  assert.equal(result.accepted, 0);
  assert.equal(result.rejected, 1);
  await assert.rejects(() => readFile(journalPath, "utf8"), { code: "ENOENT" });
  assert.equal((await readFile(rejectionPath, "utf8")).trim().split("\n").length, 1);
});

test("TaskMarket natural owner records a completed award from a status-free official submission row", async () => {
  const root = await mkdtemp(join(tmpdir(), "revenue-adapters-taskmarket-owner-"));
  const taskId = "0x" + "c".repeat(64);
  const txHash = "0x" + "d".repeat(64);
  const workerKey = "0x" + "1".repeat(64);
  const workerAddress = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A";
  const earnLedgerPath = join(root, "earn.jsonl");
  await writeFile(earnLedgerPath, `${JSON.stringify({
    source: "taskmarket_work_attempt", task: taskId, submission_id: "submission-owner",
  })}\n`);
  const selected = {
    id: taskId, status: "open", phase: "active", submissionWindowOpen: true, stakeRequired: false,
    description: "Make one still image, 1:1 square. Use GPT Image 2. Deliver one finished hero image.",
    reward: "5000000", netReward: "5000000", submissionCount: 1,
    expiryTime: "2026-08-28T00:00:00Z",
  };
  const recorded = { id: "submission-owner", taskId, workerAddress };
  const officialTask = {
    id: taskId, requester: EVM_PAYER, status: "completed", selfAward: false, awardCount: 1,
    awards: [{
      workerAddress, settlementTxHash: txHash, grossAmount: "5000000", workerPayment: "5000000",
      platformFee: "0", rank: 1, settledAt: NOW,
    }],
  };
  let submissionReads = 0;
  const result = await runTaskMarketPass({
    action: "execute", taskId, aniccaHome: root, earnLedgerPath, now: Date.parse(NOW),
    revenueJournalPath: join(root, "revenue.jsonl"), revenueRejectionPath: join(root, "rejections.jsonl"),
  }, {
    listTasks: async () => [selected],
    listSubmissions: async () => { submissionReads += 1; return [recorded]; },
    loadWalletKey: () => workerKey,
    ensureWallet: async () => ({ initialized: false }),
    generateImage: async () => ({ url: "https://cdn.example/hero.png", model: "fixture", costUsd: 0.01 }),
    downloadImage: async () => squarePng(),
    submitTask: async () => ({ ok: true }),
    fetchTask: async () => officialTask,
    verifyTaskMarketAward: async () => ({ ok: true, receiptBlock: 12345 }),
  });
  assert.equal(result.action, "already_submitted");
  assert.equal(result.revenue_projection.accepted, 1);
  assert.equal(result.revenue_projection.duplicates, 0);
  assert.equal(result.revenue_projection.rejected, 0);
  const receipt = JSON.parse((await readFile(join(root, "revenue.jsonl"), "utf8")).trim());
  assert.equal(receipt.provider, "taskmarket");
  assert.equal(receipt.signed_net_decimal, "5");
  assert.equal(submissionReads, 1);
  await assert.rejects(() => readFile(join(root, "rejections.jsonl"), "utf8"), { code: "ENOENT" });
});
