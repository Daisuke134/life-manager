import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runtimeOccurrenceId, recordSaleCandidates } from '../settlement-recorder.mjs';

test('settlement receipts carry only a validated host occurrence identity', () => {
  assert.equal(
    runtimeOccurrenceId({ LIFE_MANAGER_OCCURRENCE_ID: 'x402-settlement-recorder:run-1' }),
    'x402-settlement-recorder:run-1',
  );
  assert.equal(runtimeOccurrenceId({ LIFE_MANAGER_OCCURRENCE_ID: 'not safe/identity' }), null);
  assert.equal(runtimeOccurrenceId({}), null);
});

test('normalized candidates are reverified and recorded by a five-minute one-shot LaunchAgent', () => {
  const runner = readFileSync(new URL('../settlement-recorder.mjs', import.meta.url), 'utf8');
  const boot = readFileSync(new URL('../settlement-recorder-boot.sh', import.meta.url), 'utf8');
  const registry = JSON.parse(readFileSync(new URL('../../../../config/loop-registry.json', import.meta.url), 'utf8'));
  const job = registry.loops['x402-settlement-recorder'];

  assert.match(runner, /x402-sale-candidates\.jsonl/);
  assert.match(runner, /collectVerifiedSaleCandidates/);
  assert.match(runner, /appendUniqueExternalInflows/);
  assert.match(runner, /walletLedgerPath/);
  assert.match(runner, /SELF_WALLETS/);
  assert.match(runner, /occurrence_id: occurrenceId/);
  assert.match(runner, /verified_external_revenue/);
  assert.match(boot, /exec \/usr\/bin\/env node "\$DIR\/settlement-recorder\.mjs"/);
  assert.equal(job.label, 'ai.anicca.x402-settlement-recorder');
  assert.equal(job.entrypoint, 'skills/earn/x402-sell/settlement-recorder-boot.sh');
  assert.equal(job.cadence.start_interval_seconds, 300);
  assert.equal(job.cadence.keep_alive, undefined);
});

test('verified future settlement rows retain the exact host occurrence', async () => {
  const stateDir = mkdtempSync(join(tmpdir(), 'lm-x402-reconcile-'));
  const tx = `0x${'a'.repeat(64)}`;
  const payTo = '0x3eccad24794ca298d25378e9902a251322ea8749';
  const from = '0x0000000000000000000000000000000000000001';
  const topicAddress = (value) => `0x${value.slice(2).padStart(64, '0')}`;
  const receipt = {
    status: '0x1', transactionHash: tx, blockNumber: '0x7a',
    logs: [{
      address: '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',
      topics: [
        '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef',
        topicAddress(from), topicAddress(payTo),
      ],
      data: '0x2710', transactionHash: tx,
    }],
  };
  const rpc = async (method) => ({
    eth_chainId: '0x2105',
    eth_getBlockByNumber: { number: '0x7b' },
    eth_getTransactionReceipt: receipt,
    eth_getTransactionByHash: { from },
  }[method]);
  const result = await recordSaleCandidates({
    stateDir,
    rpc,
    occurrenceId: 'x402-settlement-recorder:future-1',
    candidates: [{
      source: 'x402-railway', source_sale_id: 'sale-future-1', offer_id: '/funding-rates',
      tx, expected_pay_to: payTo, expected_usdc_atomic: '10000',
      observed_at: '2026-09-25T00:00:00.000Z',
    }],
  });
  assert.equal(result.recorded, 1);
  const ledger = readFileSync(join(stateDir, `external-inflows-${payTo}.jsonl`), 'utf8');
  const row = JSON.parse(ledger.trim());
  assert.equal(row.occurrence_id, 'x402-settlement-recorder:future-1');
  assert.equal(row.provider_receipt_id, tx);
  assert.equal(row.official_readback_ref, `base://tx/${tx}`);
  assert.equal(row.proof_kind, 'base_finalized_usdc_transfer');
  assert.equal(row.verified, true);
});
