import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { consumeRecoveryIntentQueue } from '../recovery-supervisor.mjs';

const SHA = 'a'.repeat(40);

function intent(id, loopId = 'example-loop') {
  return {
    schema_version: 1,
    record_type: 'recovery_intent',
    intent_id: id,
    loop_id: loopId,
    owner_id: loopId,
    wake_id: `wake-${id}`,
    run_id: `run-${id}`,
    release_sha: SHA,
    action: 'reconcile_owner',
    mutates_external_effect: false,
  };
}

async function files(lines) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'lm-recovery-supervisor-'));
  const queue = path.join(root, 'intents.jsonl');
  const journal = path.join(root, 'supervisor.jsonl');
  await writeFile(queue, lines.map((line) => `${JSON.stringify(line)}\n`).join(''));
  return { queue, journal };
}

async function journalRows(journal) {
  return (await readFile(journal, 'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
}

test('consumes exactly one owner intent and does not replay a repaired intent', async () => {
  const { queue, journal } = await files([intent('one'), intent('two', 'sibling-loop')]);
  const calls = [];
  const executeIntent = async (value) => {
    calls.push(value.loop_id);
    return { ok: true, state: 'repaired' };
  };

  const first = await consumeRecoveryIntentQueue({ queuePath: queue, journalPath: journal, executeIntent });
  const second = await consumeRecoveryIntentQueue({ queuePath: queue, journalPath: journal, executeIntent });
  const third = await consumeRecoveryIntentQueue({ queuePath: queue, journalPath: journal, executeIntent });

  assert.deepEqual(first, { ok: true, state: 'repaired', intent_id: 'one', loop_id: 'example-loop', attempt: 1 });
  assert.deepEqual(second, { ok: true, state: 'repaired', intent_id: 'two', loop_id: 'sibling-loop', attempt: 1 });
  assert.deepEqual(third, { ok: true, state: 'idle', reason: 'no_pending_intent' });
  assert.deepEqual(calls, ['example-loop', 'sibling-loop']);
});

test('retries queued reconciliation only up to the bounded attempt limit', async () => {
  const { queue, journal } = await files([intent('retry')]);
  let calls = 0;
  const executeIntent = async () => {
    calls += 1;
    return { ok: false, state: 'queued', reason: 'reconcile_failed' };
  };

  const first = await consumeRecoveryIntentQueue({ queuePath: queue, journalPath: journal, executeIntent, maxAttempts: 3 });
  const second = await consumeRecoveryIntentQueue({ queuePath: queue, journalPath: journal, executeIntent, maxAttempts: 3 });
  const third = await consumeRecoveryIntentQueue({ queuePath: queue, journalPath: journal, executeIntent, maxAttempts: 3 });
  const fourth = await consumeRecoveryIntentQueue({ queuePath: queue, journalPath: journal, executeIntent, maxAttempts: 3 });

  assert.equal(first.state, 'queued');
  assert.equal(second.state, 'queued');
  assert.equal(third.state, 'queued');
  assert.deepEqual(fourth, { ok: false, state: 'escalated', intent_id: 'retry', loop_id: 'example-loop', attempt: 3 });
  assert.equal(calls, 3);
  assert.equal((await journalRows(journal)).filter((row) => row.state === 'escalated').length, 1);
});

test('holds unknown-effect intent as terminal without executing a provider action', async () => {
  const { queue, journal } = await files([intent('held')]);
  let called = false;
  const result = await consumeRecoveryIntentQueue({
    queuePath: queue,
    journalPath: journal,
    executeIntent: async () => { called = true; return { ok: true, state: 'held' }; },
  });
  assert.equal(result.state, 'held');
  assert.equal(called, true, 'executor may record the hold, but must not run a provider effect');
  assert.equal((await journalRows(journal)).at(-1).state, 'held');
});
