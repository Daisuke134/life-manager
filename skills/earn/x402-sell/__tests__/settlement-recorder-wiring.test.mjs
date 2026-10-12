import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { recordSaleCandidates } from '../settlement-recorder.mjs';
import { TRANSFER_TOPIC, USDC_ADDRESS, walletLedgerPath } from '../lib/external-inflow-recorder.mjs';

const PAY_TO = '0x3EcCAD24794ca298D25378E9902A251322ea8749';
const PAYER = `0x${'1'.repeat(40)}`;
const TX = `0x${'a'.repeat(64)}`;

function topicAddress(address) {
  return `0x${address.slice(2).toLowerCase().padStart(64, '0')}`;
}

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
  assert.match(runner, /verified_external_revenue/);
  assert.match(boot, /exec \/usr\/bin\/env node "\$DIR\/settlement-recorder\.mjs"/);
  assert.equal(job.label, 'ai.anicca.x402-settlement-recorder');
  assert.equal(job.entrypoint, 'skills/earn/x402-sell/settlement-recorder-boot.sh');
  assert.equal(job.cadence.start_interval_seconds, 300);
  assert.equal(job.cadence.keep_alive, undefined);
});

test('seller logs the successful settlement transaction and finished HTTP status', () => {
  const serve = readFileSync(new URL('../serve.mjs', import.meta.url), 'utf8');
  const requirePattern = (pattern, label) => assert.ok(pattern.test(serve), `${label} is not wired`);

  requirePattern(/from "\.\/lib\/settle-gate\.mjs"/, 'settle-gate import');
  requirePattern(/const paymentResponse = res\.getHeader\("X-PAYMENT-RESPONSE"\)/, 'payment response readback');
  requirePattern(/const settled = isSettled\(paymentResponse\)/, 'verified settle status');
  requirePattern(/tx: settled \? decodeTransaction\(paymentResponse\) : null/, 'settlement transaction');
  requirePattern(/status: res\.statusCode/, 'delivery status');
  requirePattern(/res\.on\("finish"/, 'response completion boundary');
});

test('retries Agent Economy projection when a finalized inflow was already recorded', async (t) => {
  const root = mkdtempSync(join(tmpdir(), 'x402-agent-economy-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const stateDir = join(root, 'x402-sell');
  const agentEconomyDir = join(root, 'agent-economy');
  const journalPath = join(agentEconomyDir, 'revenue-receipts.jsonl');
  const rejectionPath = `${journalPath}.rejections.jsonl`;
  const candidates = [{
    source: 'x402-image',
    source_sale_id: `x402-image:${TX}`,
    offer_id: '/image',
    tx: TX,
    expected_pay_to: PAY_TO,
    expected_usdc_atomic: '30000',
    observed_at: '2026-10-12T00:00:00.000Z',
  }];
  const receipt = {
    transactionHash: TX,
    blockNumber: '0x64',
    status: '0x1',
    logs: [{
      address: USDC_ADDRESS,
      transactionHash: TX,
      topics: [TRANSFER_TOPIC, topicAddress(PAYER), topicAddress(PAY_TO)],
      data: '0x7530',
    }],
  };
  const rpc = async (method) => {
    if (method === 'eth_chainId') return '0x2105';
    if (method === 'eth_getBlockByNumber') return { number: '0x65' };
    if (method === 'eth_getTransactionReceipt') return receipt;
    if (method === 'eth_getTransactionByHash') return { hash: TX, from: PAYER };
    throw new Error(`unexpected RPC method: ${method}`);
  };

  writeFileSync(agentEconomyDir, 'block projection journal path');
  await assert.rejects(recordSaleCandidates({
    candidates,
    rpc,
    stateDir,
    revenueJournalPath: journalPath,
    revenueRejectionPath: rejectionPath,
  }), { code: 'EEXIST' });
  const externalLedgerPath = walletLedgerPath(PAY_TO, { stateDir });
  assert.equal(readFileSync(externalLedgerPath, 'utf8').trim().split('\n').length, 1);

  rmSync(agentEconomyDir);
  mkdirSync(agentEconomyDir);
  const replay = await recordSaleCandidates({
    candidates,
    rpc,
    stateDir,
    revenueJournalPath: journalPath,
    revenueRejectionPath: rejectionPath,
  });

  assert.equal(replay.verified, 1);
  assert.equal(replay.recorded, 0);
  assert.equal(replay.duplicates, 1);
  assert.notEqual(replay.revenue_projection, null);
  assert.equal(replay.revenue_projection.rejected, 1);
  assert.equal(replay.revenue_projection.rejection_persisted, 1);
  assert.equal(existsSync(journalPath), false);
  const [rejection] = readFileSync(rejectionPath, 'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(rejection.provider, 'x402');
  assert.equal(rejection.code, 'MISSING_SETTLEMENT_COMPONENT');

  const duplicateReplay = await recordSaleCandidates({
    candidates,
    rpc,
    stateDir,
    revenueJournalPath: journalPath,
    revenueRejectionPath: rejectionPath,
  });
  assert.equal(duplicateReplay.recorded, 0);
  assert.equal(duplicateReplay.duplicates, 1);
  assert.equal(duplicateReplay.revenue_projection.rejected, 1);
  assert.equal(duplicateReplay.revenue_projection.rejection_duplicates, 1);
  assert.equal(readFileSync(rejectionPath, 'utf8').trim().split('\n').length, 1);
});
