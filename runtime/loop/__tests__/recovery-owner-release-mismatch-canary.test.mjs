import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { buildRecoveryIntent } from '../recovery-intent.mjs';
import { consumeRecoveryIntentQueue } from '../recovery-supervisor.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..', '..');
const FIXTURE_PATH = path.join(
  HERE, '..', 'fixtures', 'self-heal', 'agent-economy-owner-release-mismatch-canary.json',
);

async function fixture() {
  return JSON.parse(await readFile(FIXTURE_PATH, 'utf8'));
}

async function queueFiles(intent) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'lm-recovery-mismatch-canary-'));
  const queuePath = path.join(root, 'intents.jsonl');
  const journalPath = path.join(root, 'supervisor.jsonl');
  await writeFile(queuePath, `${JSON.stringify({ ...intent, record_type: 'recovery_intent' })}\n`);
  return { queuePath, journalPath };
}

async function journalRows(file) {
  const text = await readFile(file, 'utf8');
  return text.split('\n').filter(Boolean).map(JSON.parse);
}

test('canary fixture is pinned to the canonical keep-alive agent-economy owner contract', async () => {
  const value = await fixture();
  const registry = JSON.parse(await readFile(path.join(REPO_ROOT, 'config/loop-registry.json'), 'utf8'));
  const entry = registry.loops[value.target.loop_id];

  assert.equal(entry.label, value.target.label);
  assert.equal(entry.provider_route, value.target.provider_route);
  assert.equal(entry.effect_class, value.target.effect_class);
  assert.equal(entry.cadence?.keep_alive, true);
});

test('a keep-alive owner intent superseded by promotion is closed with an actionable next step, not a dead end', async () => {
  const value = await fixture();
  const intent = buildRecoveryIntent(value.failure_event);
  assert.equal(intent.action, 'reconcile_owner');
  assert.equal(intent.reason, 'bounded_owner_reconciliation');

  const { queuePath, journalPath } = await queueFiles(intent);
  const result = await consumeRecoveryIntentQueue({
    queuePath,
    journalPath,
    currentReleaseSha: value.current_release_sha,
    now: '2026-09-24T00:00:00.000Z',
    executeIntent: async () => { throw new Error('must not execute a superseded intent'); },
  });

  assert.equal(result.ok, true);
  assert.equal(result.state, 'idle');
  assert.equal(result.reason, 'no_pending_intent');

  const outcome = (await journalRows(journalPath)).find((row) => row.record_type === 'recovery_outcome');
  assert.equal(outcome.state, 'blocked');
  assert.equal(outcome.reason, 'release_sha_mismatch');
  assert.equal(outcome.attempt, 0);
  assert.equal(outcome.before_event_id, null);
  assert.equal(outcome.after_event_id, null);
  assert.equal(outcome.command_exit_code, null);
  // A superseded keep-alive owner is not exhausted: the outcome must still name
  // a concrete next step so recovery converges on the current release instead
  // of leaving the owner permanently unreconciled.
  assert.notEqual(outcome.next_action, 'none');
  assert.equal(outcome.next_action, 'reconcile_current_release');
});
