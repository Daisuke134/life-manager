import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

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
