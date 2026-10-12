import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";

import { projectRevenueReceipts } from "./revenue-adapters.mjs";
import { revenueReceiptToFinancialRecords } from "./financial-record-adapter.mjs";

const TASK_ID = `0x${"11".repeat(32)}`;
const TX = `0x${"22".repeat(32)}`;
const WORKER = `0x${"33".repeat(20)}`;
const REQUESTER = `0x${"44".repeat(20)}`;
const ESCROW = `0x${"55".repeat(20)}`;
const USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913";
const TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const SETTLED_AT = "2026-10-11T12:00:00.000Z";

function topicAddress(address) {
  return `0x${address.slice(2).padStart(64, "0")}`;
}

function taskmarketRpc() {
  return async (_url, init) => {
    const { method } = JSON.parse(init.body);
    const result = method === "eth_chainId" ? "0x2105"
      : method === "eth_getBlockByNumber" ? { number: "0x5000" }
        : {
          status: "0x1",
          transactionHash: TX,
          blockNumber: "0x4fff",
          logs: [{
            address: USDC,
            transactionHash: TX,
            logIndex: "0x0",
            topics: [TRANSFER_TOPIC, topicAddress(ESCROW), topicAddress(WORKER)],
            data: `0x${BigInt("5000000").toString(16).padStart(64, "0")}`,
          }],
        };
    return { ok: true, json: async () => ({ result }) };
  };
}

test("TaskMarket award receipt uses the official task readback and finalized verifier", async () => {
  const root = await mkdtemp(join(tmpdir(), "taskmarket-revenue-adapter-"));
  const journalPath = join(root, "revenue.jsonl");
  const task = {
    id: TASK_ID,
    requester: REQUESTER,
    status: "completed",
    selfAward: false,
    awardCount: 1,
    awards: [{
      workerAddress: WORKER,
      settlementTxHash: TX,
      grossAmount: "5500000",
      workerPayment: "5000000",
      platformFee: "500000",
      rank: 1,
      settledAt: SETTLED_AT,
    }],
  };
  const result = await projectRevenueReceipts({
    journalPath,
    provider: "taskmarket",
    rows: [{ taskId: TASK_ID, submissionId: "submission-1" }],
    options: {
      workerAddress: WORKER,
      selfWallets: [],
      rpc: "https://rpc.invalid",
      fetchImpl: taskmarketRpc(),
      fetchTask: async (taskId) => {
        assert.equal(taskId, TASK_ID);
        return task;
      },
    },
  });

  assert.equal(result.accepted, 1);
  assert.equal(result.rejected, 0);
  const receipt = JSON.parse((await readFile(journalPath, "utf8")).trim());
  assert.equal(receipt.provider, "taskmarket");
  assert.equal(receipt.payer, REQUESTER.toLowerCase());
  assert.equal(receipt.recipient, WORKER.toLowerCase());
  assert.equal(receipt.gross_decimal, "5.5");
  assert.equal(receipt.fee_decimal, "0.5");
  assert.equal(receipt.refund_decimal, "0");
  assert.equal(receipt.signed_net_decimal, "5");
  assert.ok(receipt.proof.provider_receipt_id.includes(TX));
  assert.deepEqual(
    revenueReceiptToFinancialRecords(receipt, { subjectId: "agent-economy" })
      .map(({ kind, direction, amount_minor }) => [kind, direction, amount_minor]),
    [["business_revenue", "credit", 5_500_000], ["fee", "debit", 500_000]],
  );
});

test("TaskMarket submission pointer without a completed official task never books revenue", async () => {
  const root = await mkdtemp(join(tmpdir(), "taskmarket-revenue-pending-"));
  const journalPath = join(root, "revenue.jsonl");
  let taskReads = 0;
  const result = await projectRevenueReceipts({
    journalPath,
    provider: "taskmarket",
    rows: [{ taskId: TASK_ID, submissionId: "submission-2" }],
    options: {
      workerAddress: WORKER,
      selfWallets: [],
      fetchTask: async () => {
        taskReads += 1;
        return { id: TASK_ID, requester: REQUESTER, status: "open", awardCount: 0, awards: [] };
      },
    },
  });
  assert.equal(result.accepted, 0);
  assert.equal(taskReads, 1);
  assert.equal(result.rejected, 1);
});

test("TaskMarket awards are read and verified sequentially", async () => {
  const root = await mkdtemp(join(tmpdir(), "taskmarket-revenue-serial-"));
  const taskIds = [TASK_ID, `0x${"66".repeat(32)}`];
  const txs = [TX, `0x${"77".repeat(32)}`];
  let active = 0;
  let maxActive = 0;
  const delay = () => new Promise((resolve) => setTimeout(resolve, 5));
  const track = async (work) => {
    active += 1;
    maxActive = Math.max(maxActive, active);
    try { await delay(); return await work(); }
    finally { active -= 1; }
  };
  const result = await projectRevenueReceipts({
    journalPath: join(root, "revenue.jsonl"),
    provider: "taskmarket",
    rows: taskIds.map((taskId, index) => ({ taskId, submissionId: `submission-${index}` })),
    options: {
      workerAddress: WORKER,
      selfWallets: [],
      fetchTask: (taskId) => track(async () => ({
        id: taskId,
        requester: REQUESTER,
        status: "completed",
        selfAward: false,
        awardCount: 1,
        awards: [{
          workerAddress: WORKER,
          settlementTxHash: txs[taskIds.indexOf(taskId)],
          grossAmount: "5500000",
          workerPayment: "5000000",
          platformFee: "500000",
          rank: 1,
          settledAt: SETTLED_AT,
        }],
      })),
      verifyTaskMarketAward: (task, award) => track(async () => ({ ok: true, receiptBlock: 12345 })),
    },
  });
  assert.equal(result.accepted, 2);
  assert.equal(maxActive, 1);
});
