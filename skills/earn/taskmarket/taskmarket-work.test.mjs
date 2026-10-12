import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { TASKMARKET_CLI, classifyTask, ensureTaskmarketWallet, runTaskMarketPass, selectTask } from './taskmarket-work.mjs';

const NOW = Date.parse('2026-07-28T08:00:00Z');
const TASKMARKET_WORKER = '0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A';
const BLOCKRUN_PAY_TO = '0xe9030014F5DAe217d0A152f02A043567b16c1aBf';
const BLOCKRUN_TX = `0x${'7'.repeat(64)}`;
const BLOCKRUN_BLOCK_HASH = `0x${'8'.repeat(64)}`;
const BLOCKRUN_RECEIPT_ID = `blockrun:${'a'.repeat(64)}`;
const USDC_BASE = '0x833589fCD6eDb6E08f4c7C32d4f71b54bda02913';
const TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef';
const IMAGE_BRIEF = [
  'Make one still image, 1:1 square.',
  'FLOOR: made with a real frontier image model such as GPT Image 2 or better.',
  'DELIVER: one finished hero image, plus concept-note.md and sources.md.',
].join(' ');

const topicAddress = (address) => `0x${address.slice(2).toLowerCase().padStart(64, '0')}`;

function blockrunReceiptRpc({
  amountAtomic = '65000',
  tx = BLOCKRUN_TX,
  finalizedBlock = '0x100',
  canonicalHash = BLOCKRUN_BLOCK_HASH,
  receiptBlockHash = BLOCKRUN_BLOCK_HASH,
} = {}) {
  return async (method, params = []) => {
    if (method === 'eth_chainId') return '0x2105';
    if (method === 'eth_getBlockByNumber') {
      return params[0] === 'finalized'
        ? { number: finalizedBlock }
        : { number: '0x99', hash: canonicalHash };
    }
    if (method === 'eth_getTransactionReceipt') {
      return {
        transactionHash: tx,
        status: '0x1',
        blockNumber: '0x99',
        blockHash: receiptBlockHash,
        logs: [{
          address: USDC_BASE,
          transactionHash: tx,
          logIndex: '0x3',
          topics: [TRANSFER_TOPIC, topicAddress(TASKMARKET_WORKER), topicAddress(BLOCKRUN_PAY_TO)],
          data: `0x${BigInt(amountAtomic).toString(16).padStart(64, '0')}`,
        }],
      };
    }
    if (method === 'eth_getTransactionByHash') return { hash: tx, from: '0x4444444444444444444444444444444444444444' };
    throw new Error(`unexpected RPC method ${method}`);
  };
}

test('TaskMarket uses the repository-local CLI on every operating system', () => {
  assert.equal(TASKMARKET_CLI, join(import.meta.dirname, 'node_modules', '.bin', 'taskmarket'));
  assert.doesNotMatch(TASKMARKET_CLI, /homebrew/);
});

test('clean tenant initializes TaskMarket with the same citizen wallet and stores no plaintext key', async () => {
  const home = mkdtempSync(join(tmpdir(), 'taskmarket-clean-home-'));
  const walletKey = '0x' + '1'.repeat(64);
  const expectedAddress = '0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a';
  let importedKey;
  const result = await ensureTaskmarketWallet({
    walletKey,
    home,
    runImport: async (key) => {
      importedKey = key;
      const dir = join(home, '.taskmarket');
      mkdirSync(dir, { recursive: true });
      writeFileSync(join(dir, 'keystore.json'), JSON.stringify({
        walletAddress: expectedAddress,
        encryptedKey: 'ciphertext-only',
      }), { mode: 0o600 });
    },
  });
  assert.equal(importedKey, walletKey);
  assert.deepEqual(result, { initialized: true, address: expectedAddress });
  assert.doesNotMatch(readFileSync(join(home, '.taskmarket', 'keystore.json'), 'utf8'), new RegExp(walletKey.slice(2)));
});

function task(overrides = {}) {
  return {
    id: '0x' + '1'.repeat(64),
    status: 'open',
    phase: 'active',
    submissionWindowOpen: true,
    stakeRequired: false,
    description: IMAGE_BRIEF,
    reward: '5000000',
    netReward: '4625000',
    submissionCount: 20,
    expiryTime: '2026-07-29T08:00:00Z',
    ...overrides,
  };
}

test('classifyTask accepts one unstaked frontier still-image delivery', () => {
  assert.deepEqual(classifyTask(task(), { maxImageCostUsd: 0.06 }), {
    supported: true,
    reason: 'supported_still_image',
  });
});

test('classifyTask rejects closed, staked, unsupported, and uneconomic tasks', () => {
  assert.equal(classifyTask(task({ submissionWindowOpen: false }), { maxImageCostUsd: 0.06 }).reason, 'submission_window_closed');
  assert.equal(classifyTask(task({ stakeRequired: true }), { maxImageCostUsd: 0.06 }).reason, 'stake_required');
  assert.equal(classifyTask(task({ description: 'Produce one short film with three scenes.' }), { maxImageCostUsd: 0.06 }).reason, 'unsupported_deliverable');
  assert.equal(classifyTask(task({ netReward: '1100000' }), { maxImageCostUsd: 0.06 }).reason, 'reward_below_20x_cost');
});

test('selectTask excludes owned submissions and ranks expiry, competition, then reward', () => {
  const submittedId = '0x' + '2'.repeat(64);
  const laterLowCompetition = task({
    id: '0x' + '3'.repeat(64),
    expiryTime: '2026-07-30T08:00:00Z',
    submissionCount: 1,
    netReward: '9000000',
  });
  const earliestCrowded = task({
    id: '0x' + '4'.repeat(64),
    expiryTime: '2026-07-29T07:00:00Z',
    submissionCount: 50,
  });
  const earliestSparse = task({
    id: '0x' + '5'.repeat(64),
    expiryTime: '2026-07-29T07:00:00Z',
    submissionCount: 10,
    netReward: '4000000',
  });
  const alreadySubmitted = task({ id: submittedId, expiryTime: '2026-07-28T09:00:00Z' });

  const selected = selectTask({
    tasks: [laterLowCompetition, earliestCrowded, alreadySubmitted, earliestSparse],
    submissions: [{ id: 'sub_1', taskId: submittedId }],
    now: NOW,
    maxImageCostUsd: 0.06,
  });

  assert.equal(selected.id, earliestSparse.id);
});

test('selectTask returns null for expired or unsupported inventory', () => {
  const selected = selectTask({
    tasks: [
      task({ expiryTime: '2026-07-28T07:59:59Z' }),
      task({ description: 'Build a single-page flashcard web app.' }),
    ],
    submissions: [],
    now: NOW,
    maxImageCostUsd: 0.06,
  });
  assert.equal(selected, null);
});

function squarePng(width = 1024, height = 1024) {
  const png = Buffer.alloc(33);
  Buffer.from('89504e470d0a1a0a', 'hex').copy(png, 0);
  png.writeUInt32BE(13, 8);
  Buffer.from('IHDR').copy(png, 12);
  png.writeUInt32BE(width, 16);
  png.writeUInt32BE(height, 20);
  png[24] = 8;
  png[25] = 2;
  return png;
}

test('runTaskMarketPass generates three files, submits once, retries bounded readback, and records cost', async () => {
  const root = mkdtempSync(join(tmpdir(), 'taskmarket-work-'));
  const ledger = join(root, 'earn-ledger.jsonl');
  const selected = task({
    id: '0x' + 'a'.repeat(64),
    description: [
      'The Maya mathematician who signed his own formula.',
      IMAGE_BRIEF,
      'Locked facts: 260, 365, 584, 780. His name is Sak Tahn Waax.',
    ].join(' '),
  });
  let submissionReads = 0;
  const submitCalls = [];
  const prompts = [];
  const sleeps = [];

  const result = await runTaskMarketPass({
    action: 'execute',
    aniccaHome: root,
    earnLedgerPath: ledger,
    computeCostJournalPath: join(root, 'compute-receipts.jsonl'),
    wakeId: 'wake-taskmarket-1',
    now: NOW,
  }, {
    listTasks: async () => [selected],
    listSubmissions: async () => {
      submissionReads += 1;
      return submissionReads < 4
        ? []
        : [{ id: 'sub_taskmarket_1', taskId: selected.id }];
    },
    sleep: async (ms) => { sleeps.push(ms); },
    loadWalletKey: () => '0x' + '1'.repeat(64),
    ensureWallet: async () => {},
    reserveSpend: async () => {},
    rpcCall: blockrunReceiptRpc(),
    generateImage: async ({ prompt, reserveSpend }) => {
      prompts.push(prompt);
      await reserveSpend?.(0.065);
      return {
        url: 'https://cdn.blockrun.example/maya.png',
        model: 'openai/gpt-image-2',
        costUsd: 0.065,
        paymentReceiptId: BLOCKRUN_RECEIPT_ID,
        paymentSettlement: {
          transaction: BLOCKRUN_TX,
          network: 'eip155:8453',
          payer: TASKMARKET_WORKER.toLowerCase(),
          recipient: BLOCKRUN_PAY_TO.toLowerCase(),
          amountAtomic: '65000',
          quotedAmountAtomic: '65000',
          asset: USDC_BASE.toLowerCase(),
          scheme: 'exact',
          providerReceiptId: BLOCKRUN_RECEIPT_ID,
        },
        created: 1785230000,
      };
    },
    downloadImage: async () => squarePng(),
    submitTask: async (taskId, files) => {
      submitCalls.push({ taskId, files });
      return { ok: true };
    },
  });

  assert.deepEqual(result, {
    ok: true,
    action: 'submitted',
    taskId: selected.id,
    submissionId: 'sub_taskmarket_1',
    model: 'openai/gpt-image-2',
    costUsd: 0.065,
  });
  assert.equal(prompts.length, 1);
  assert.equal(submissionReads, 4);
  assert.deepEqual(sleeps, [1000, 1000]);
  assert.match(prompts[0], /Sak Tahn Waax/);
  assert.match(prompts[0], /260, 365, 584, 780/);
  assert.equal(submitCalls.length, 1);
  assert.equal(submitCalls[0].taskId, selected.id);
  assert.deepEqual(submitCalls[0].files.map((path) => path.split('/').at(-1)), [
    'hero.png',
    'concept-note.md',
    'sources.md',
  ]);
  assert.match(readFileSync(submitCalls[0].files[1], 'utf8'), /openai\/gpt-image-2/);
  assert.match(readFileSync(submitCalls[0].files[2], 'utf8'), new RegExp(selected.id));
  const rows = readFileSync(ledger, 'utf8').trim().split('\n').map(JSON.parse);
  assert.deepEqual(rows, [{
    ts: Math.floor(NOW / 1000),
    wake: 'wake-taskmarket-1',
    source: 'taskmarket_work_payment_intent',
    task: selected.id,
    payment_state: 'effect_unknown',
    quoted_cost_usdc: '0.065',
  }, {
    ts: Math.floor(NOW / 1000),
    wake: 'wake-taskmarket-1',
    source: 'taskmarket_work_payment_verified',
    task: selected.id,
    payment_state: 'verified',
    payment_receipt_id: BLOCKRUN_RECEIPT_ID,
    cost_usdc: '0.065',
    tx_hash: BLOCKRUN_TX,
  }, {
    ts: Math.floor(NOW / 1000),
    wake: 'wake-taskmarket-1',
    source: 'taskmarket_work_attempt',
    task: selected.id,
    earn_usdc: 0,
    cost_usdc: 0.065,
    net_usdc: -0.065,
    submission_id: 'sub_taskmarket_1',
    model: 'openai/gpt-image-2',
    payment_receipt_id: BLOCKRUN_RECEIPT_ID,
  }]);
});

test('runTaskMarketPass records the finalized BlockRun receipt in Agent Economy compute costs before submit', async () => {
  const root = mkdtempSync(join(tmpdir(), 'taskmarket-compute-cost-'));
  const computeCostJournalPath = join(root, 'compute-receipts.jsonl');
  const selected = task({ id: `0x${'f'.repeat(64)}` });
  let submissionReads = 0;
  let submitted = false;
  const result = await runTaskMarketPass({
    action: 'execute',
    aniccaHome: root,
    earnLedgerPath: join(root, 'earn-ledger.jsonl'),
    computeCostJournalPath,
    wakeId: 'wake-taskmarket-cost-1',
    now: NOW,
  }, {
    listTasks: async () => [selected],
    listSubmissions: async () => {
      submissionReads += 1;
      return submissionReads < 4 ? [] : [{ id: 'sub-cost-1', taskId: selected.id }];
    },
    loadWalletKey: () => '0x' + '1'.repeat(64),
    ensureWallet: async () => {},
    reserveSpend: async () => {},
    generateImage: async ({ reserveSpend }) => {
      await reserveSpend?.(0.065);
      return {
        url: 'https://cdn.blockrun.example/cost.png',
        model: 'openai/gpt-image-2',
        costUsd: 0.065,
        paymentReceiptId: BLOCKRUN_RECEIPT_ID,
        paymentSettlement: {
          transaction: BLOCKRUN_TX,
          network: 'eip155:8453',
          payer: TASKMARKET_WORKER.toLowerCase(),
          recipient: BLOCKRUN_PAY_TO.toLowerCase(),
          amountAtomic: '65000',
          quotedAmountAtomic: '65000',
          asset: USDC_BASE.toLowerCase(),
          scheme: 'exact',
          providerReceiptId: BLOCKRUN_RECEIPT_ID,
        },
      };
    },
    rpcCall: blockrunReceiptRpc(),
    downloadImage: async () => squarePng(),
    submitTask: async () => {
      submitted = true;
      assert.equal(existsSync(computeCostJournalPath), true);
    },
  });

  assert.equal(result.action, 'submitted');
  assert.equal(submitted, true);
  const rows = readFileSync(computeCostJournalPath, 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].provider, 'blockrun');
  assert.equal(rows[0].cost_usdc, '0.065');
  assert.equal(rows[0].proof.verified, true);
  assert.equal(rows[0].proof.provider_receipt_id, BLOCKRUN_RECEIPT_ID);
  assert.equal(rows[0].proof.tx_hash, BLOCKRUN_TX);
  assert.equal(rows[0].proof.log_index, 3);
  assert.equal(rows[0].proof.receipt_block, 153);
  assert.equal(rows[0].proof.finalized_block, 256);
});

test('runTaskMarketPass refuses to submit an image with no BlockRun settlement receipt', async () => {
  const root = mkdtempSync(join(tmpdir(), 'taskmarket-unverified-cost-'));
  const computeCostJournalPath = join(root, 'compute-receipts.jsonl');
  const selected = task({ id: `0x${'e'.repeat(64)}` });
  let submitted = false;
  await assert.rejects(() => runTaskMarketPass({
    action: 'execute',
    aniccaHome: root,
    earnLedgerPath: join(root, 'earn-ledger.jsonl'),
    computeCostJournalPath,
    now: NOW,
    submissionReadbackAttempts: 1,
  }, {
    listTasks: async () => [selected],
    listSubmissions: async () => [],
    loadWalletKey: () => '0x' + '1'.repeat(64),
    ensureWallet: async () => {},
    reserveSpend: async () => {},
    generateImage: async ({ reserveSpend }) => {
      await reserveSpend?.(0.065);
      return {
        url: 'https://cdn.blockrun.example/unverified.png',
        model: 'openai/gpt-image-2',
        costUsd: 0.065,
        paymentReceiptId: BLOCKRUN_RECEIPT_ID,
      };
    },
    downloadImage: async () => squarePng(),
    submitTask: async () => { submitted = true; },
  }), /settlement|receipt/i);
  assert.equal(submitted, false);
  assert.equal(existsSync(computeCostJournalPath), false);
});

test('runTaskMarketPass refuses to submit before the BlockRun transfer is finalized', async () => {
  const root = mkdtempSync(join(tmpdir(), 'taskmarket-unfinalized-cost-'));
  const computeCostJournalPath = join(root, 'compute-receipts.jsonl');
  const selected = task({ id: `0x${'9'.repeat(64)}` });
  let submitted = false;
  await assert.rejects(() => runTaskMarketPass({
    action: 'execute',
    aniccaHome: root,
    earnLedgerPath: join(root, 'earn-ledger.jsonl'),
    computeCostJournalPath,
    now: NOW,
    submissionReadbackAttempts: 1,
  }, {
    listTasks: async () => [selected],
    listSubmissions: async () => [],
    loadWalletKey: () => '0x' + '1'.repeat(64),
    ensureWallet: async () => {},
    reserveSpend: async () => {},
    rpcCall: blockrunReceiptRpc({ finalizedBlock: '0x98' }),
    generateImage: async ({ reserveSpend }) => {
      await reserveSpend?.(0.065);
      return {
        url: 'https://cdn.blockrun.example/unfinalized.png',
        model: 'openai/gpt-image-2',
        costUsd: 0.065,
        paymentReceiptId: BLOCKRUN_RECEIPT_ID,
        paymentSettlement: {
          transaction: BLOCKRUN_TX,
          network: 'eip155:8453',
          payer: TASKMARKET_WORKER.toLowerCase(),
          recipient: BLOCKRUN_PAY_TO.toLowerCase(),
          amountAtomic: '65000',
          quotedAmountAtomic: '65000',
          asset: USDC_BASE.toLowerCase(),
          scheme: 'exact',
          providerReceiptId: BLOCKRUN_RECEIPT_ID,
        },
      };
    },
    downloadImage: async () => squarePng(),
    submitTask: async () => { submitted = true; },
  }), /not finalized/i);
  assert.equal(submitted, false);
  assert.equal(existsSync(computeCostJournalPath), false);
});

test('runTaskMarketPass refuses a finalized receipt whose block hash is not canonical', async () => {
  const root = mkdtempSync(join(tmpdir(), 'taskmarket-noncanonical-cost-'));
  const computeCostJournalPath = join(root, 'compute-receipts.jsonl');
  const selected = task({ id: `0x${'8'.repeat(64)}` });
  let submitted = false;
  await assert.rejects(() => runTaskMarketPass({
    action: 'execute',
    aniccaHome: root,
    earnLedgerPath: join(root, 'earn-ledger.jsonl'),
    computeCostJournalPath,
    now: NOW,
    submissionReadbackAttempts: 1,
  }, {
    listTasks: async () => [selected],
    listSubmissions: async () => [],
    loadWalletKey: () => '0x' + '1'.repeat(64),
    ensureWallet: async () => {},
    reserveSpend: async () => {},
    rpcCall: blockrunReceiptRpc({ canonicalHash: `0x${'9'.repeat(64)}` }),
    generateImage: async ({ reserveSpend }) => {
      await reserveSpend?.(0.065);
      return {
        url: 'https://cdn.blockrun.example/noncanonical.png',
        model: 'openai/gpt-image-2',
        costUsd: 0.065,
        paymentReceiptId: BLOCKRUN_RECEIPT_ID,
        paymentSettlement: {
          transaction: BLOCKRUN_TX,
          network: 'eip155:8453',
          payer: TASKMARKET_WORKER.toLowerCase(),
          recipient: BLOCKRUN_PAY_TO.toLowerCase(),
          amountAtomic: '65000',
          quotedAmountAtomic: '65000',
          asset: USDC_BASE.toLowerCase(),
          scheme: 'exact',
          providerReceiptId: BLOCKRUN_RECEIPT_ID,
        },
      };
    },
    downloadImage: async () => squarePng(),
    submitTask: async () => { submitted = true; },
  }), /canonical/i);
  assert.equal(submitted, false);
  assert.equal(existsSync(computeCostJournalPath), false);
});

test('runTaskMarketPass does not pay again for a task with an unresolved prior payment intent', async () => {
  const root = mkdtempSync(join(tmpdir(), 'taskmarket-unresolved-payment-'));
  const earnLedgerPath = join(root, 'earn-ledger.jsonl');
  const selected = task({ id: `0x${'d'.repeat(64)}` });
  writeFileSync(earnLedgerPath, `${JSON.stringify({
    ts: Math.floor(NOW / 1000),
    wake: 'wake-taskmarket-payment-unknown',
    source: 'taskmarket_work_payment_intent',
    task: selected.id,
    payment_state: 'effect_unknown',
  })}\n`);
  let generated = false;
  let submitted = false;
  const result = await runTaskMarketPass({
    action: 'execute',
    aniccaHome: root,
    earnLedgerPath,
    now: NOW,
  }, {
    listTasks: async () => [selected],
    listSubmissions: async () => [],
    loadWalletKey: () => '0x' + '1'.repeat(64),
    ensureWallet: async () => {},
    generateImage: async () => { generated = true; throw new Error('must not pay again'); },
    submitTask: async () => { submitted = true; },
  });
  assert.equal(result.action, 'held_unresolved_payment');
  assert.equal(result.taskId, selected.id);
  assert.equal(generated, false);
  assert.equal(submitted, false);
});

test('runTaskMarketPass does not generate or submit an already-owned task', async () => {
  const root = mkdtempSync(join(tmpdir(), 'taskmarket-work-existing-'));
  const selected = task({ id: '0x' + 'b'.repeat(64) });
  let generated = false;
  let submitted = false;

  const result = await runTaskMarketPass({
    action: 'execute',
    taskId: selected.id,
    aniccaHome: root,
    earnLedgerPath: join(root, 'earn-ledger.jsonl'),
    wakeId: 'wake-taskmarket-2',
    now: NOW,
  }, {
    listTasks: async () => [selected],
    listSubmissions: async () => [{ id: 'sub_existing', taskId: selected.id }],
    loadWalletKey: () => '0x' + '1'.repeat(64),
    ensureWallet: async () => {},
    generateImage: async () => { generated = true; },
    downloadImage: async () => squarePng(),
    submitTask: async () => { submitted = true; },
  });

  assert.deepEqual(result, {
    ok: true,
    action: 'already_submitted',
    taskId: selected.id,
    submissionId: 'sub_existing',
    costUsd: 0,
  });
  assert.equal(generated, false);
  assert.equal(submitted, false);
});

test('runTaskMarketPass reconciles an existing official submit tx exactly once without new image cost', async () => {
  const root = mkdtempSync(join(tmpdir(), 'taskmarket-work-reconcile-'));
  const ledger = join(root, 'earn-ledger.jsonl');
  const selected = task({ id: '0x' + 'd'.repeat(64) });
  const submitTxHash = '0x' + 'e'.repeat(64);
  await import('node:fs/promises').then(({ writeFile }) => writeFile(ledger, `${JSON.stringify({
    ts: Math.floor(NOW / 1000),
    wake: 'wake-original',
    source: 'taskmarket_work_attempt',
    task: selected.id,
    earn_usdc: 0,
    submission_id: null,
    model: 'openai/gpt-image-2',
  })}\n`));
  let generated = false;
  let submitted = false;
  const deps = {
    listTasks: async () => [selected],
    listSubmissions: async () => [{ taskId: selected.id, submitTxHash }],
    loadWalletKey: () => '0x' + '1'.repeat(64),
    ensureWallet: async () => {},
    generateImage: async () => { generated = true; },
    downloadImage: async () => squarePng(),
    submitTask: async () => { submitted = true; },
  };

  const first = await runTaskMarketPass({
    action: 'execute',
    aniccaHome: root,
    earnLedgerPath: ledger,
    wakeId: 'wake-reconcile-1',
    now: NOW,
  }, deps);
  const second = await runTaskMarketPass({
    action: 'execute',
    taskId: selected.id,
    aniccaHome: root,
    earnLedgerPath: ledger,
    wakeId: 'wake-reconcile-2',
    now: NOW + 1,
  }, deps);

  assert.deepEqual(first, {
    ok: true,
    action: 'reconciled_submission',
    taskId: selected.id,
    submissionId: submitTxHash,
    costUsd: 0,
  });
  assert.deepEqual(second, {
    ok: true,
    action: 'already_submitted',
    taskId: selected.id,
    submissionId: submitTxHash,
    costUsd: 0,
  });
  assert.equal(generated, false);
  assert.equal(submitted, false);
  const rows = readFileSync(ledger, 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[1], {
    ts: Math.floor(NOW / 1000),
    wake: 'wake-reconcile-1',
    source: 'taskmarket_work_reconciliation',
    task: selected.id,
    earn_usdc: 0,
    cost_usdc: null,
    net_usdc: null,
    submission_id: submitTxHash,
    reconciles_wake: 'wake-original',
  });
});

test('runTaskMarketPass fails closed after bounded retries when submit has no official readback', async () => {
  const root = mkdtempSync(join(tmpdir(), 'taskmarket-work-readback-'));
  const selected = task({ id: '0x' + 'c'.repeat(64) });
  let submissionReads = 0;
  const sleeps = [];
  await assert.rejects(
    runTaskMarketPass({
      action: 'execute',
      aniccaHome: root,
      earnLedgerPath: join(root, 'earn-ledger.jsonl'),
      computeCostJournalPath: join(root, 'compute-receipts.jsonl'),
      wakeId: 'wake-taskmarket-3',
      now: NOW,
    }, {
      listTasks: async () => [selected],
      listSubmissions: async () => { submissionReads += 1; return []; },
      sleep: async (ms) => { sleeps.push(ms); },
      loadWalletKey: () => '0x' + '1'.repeat(64),
      ensureWallet: async () => {},
      reserveSpend: async () => {},
      rpcCall: blockrunReceiptRpc(),
      generateImage: async ({ reserveSpend }) => {
        await reserveSpend?.(0.065);
        return {
          url: 'https://cdn.blockrun.example/missing.png',
          model: 'openai/gpt-image-2',
          costUsd: 0.065,
          paymentReceiptId: BLOCKRUN_RECEIPT_ID,
          paymentSettlement: {
            transaction: BLOCKRUN_TX,
            network: 'eip155:8453',
            payer: TASKMARKET_WORKER.toLowerCase(),
            recipient: BLOCKRUN_PAY_TO.toLowerCase(),
            amountAtomic: '65000',
            quotedAmountAtomic: '65000',
            asset: USDC_BASE.toLowerCase(),
            scheme: 'exact',
            providerReceiptId: BLOCKRUN_RECEIPT_ID,
          },
        };
      },
      downloadImage: async () => squarePng(),
      submitTask: async () => ({ ok: true }),
    }),
    /submission_readback_missing/,
  );
  assert.equal(submissionReads, 6);
  assert.deepEqual(sleeps, [1000, 1000, 1000, 1000]);
});
