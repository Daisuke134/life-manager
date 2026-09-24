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
    occurrence_id: `${loopId}:occurrence-${id}`,
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

  const options = {
    queuePath: queue, journalPath: journal, executeIntent,
    now: '2026-09-24T00:00:00.000Z',
  };
  const first = await consumeRecoveryIntentQueue(options);
  const second = await consumeRecoveryIntentQueue(options);
  const third = await consumeRecoveryIntentQueue(options);

  assert.deepEqual(first, { ok: true, state: 'repaired', intent_id: 'one', loop_id: 'example-loop', attempt: 1 });
  assert.deepEqual(second, { ok: true, state: 'repaired', intent_id: 'two', loop_id: 'sibling-loop', attempt: 1 });
  assert.deepEqual(third, { ok: true, state: 'idle', reason: 'no_pending_intent' });
  assert.deepEqual(calls, ['example-loop', 'sibling-loop']);
  const rows = await journalRows(journal);
  const outcomes = rows.filter((row) => row.record_type === 'recovery_outcome');
  assert.equal(outcomes.length, 2);
  assert.deepEqual(outcomes[0], {
    schema_version: 1,
    record_type: 'recovery_outcome',
    intent_id: 'one',
    loop_id: 'example-loop',
    owner_id: 'example-loop',
    occurrence_id: 'example-loop:occurrence-one',
    release_sha: SHA,
    action: 'reconcile_owner',
    state: 'repaired',
    result: 'repaired',
    attempt: 1,
    budget_consumed: false,
    before_event_id: null,
    after_event_id: null,
    command_exit_code: null,
    readback: null,
    evidence_refs: [],
    next_action: 'none',
    next_eligible_at: null,
    observed_at: '2026-09-24T00:00:00.000Z',
  });
});

test('retries queued reconciliation only up to the bounded attempt limit', async () => {
  const { queue, journal } = await files([intent('retry')]);
  let calls = 0;
  const executeIntent = async () => {
    calls += 1;
    return { ok: false, state: 'queued', reason: 'reconcile_failed' };
  };

  const first = await consumeRecoveryIntentQueue({
    queuePath: queue, journalPath: journal, executeIntent, maxAttempts: 3,
    now: '2026-09-24T00:00:00.000Z', cooldownSeconds: 60,
  });
  const cooled = await consumeRecoveryIntentQueue({
    queuePath: queue, journalPath: journal, executeIntent, maxAttempts: 3,
    now: '2026-09-24T00:00:30.000Z', cooldownSeconds: 60,
  });
  const second = await consumeRecoveryIntentQueue({
    queuePath: queue, journalPath: journal, executeIntent, maxAttempts: 3,
    now: '2026-09-24T00:01:00.000Z', cooldownSeconds: 60,
  });
  const third = await consumeRecoveryIntentQueue({
    queuePath: queue, journalPath: journal, executeIntent, maxAttempts: 3,
    now: '2026-09-24T00:02:00.000Z', cooldownSeconds: 60,
  });
  const fourth = await consumeRecoveryIntentQueue({
    queuePath: queue, journalPath: journal, executeIntent, maxAttempts: 3,
    now: '2026-09-24T00:03:00.000Z', cooldownSeconds: 60,
  });

  assert.equal(first.state, 'queued');
  assert.deepEqual(cooled, { ok: true, state: 'idle', reason: 'cooldown_active' });
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

test('records exact readback evidence and does not spend budget on verification-only polls', async () => {
  const { queue, journal } = await files([intent('evidence')]);
  const result = await consumeRecoveryIntentQueue({
    queuePath: queue,
    journalPath: journal,
    now: '2026-09-24T00:00:00.000Z',
    executeIntent: async () => ({
      ok: false,
      state: 'queued',
      reason: 'healthy_readback_pending',
      budget_consumed: false,
      before_readback: { event_id: 'event-before' },
      after_readback: {
        event_id: 'event-after', loop_id: 'example-loop', owner_id: 'example-loop',
        installed_release_sha: SHA, event_release_sha: SHA,
      },
      command_exit_code: 0,
      evidence_refs: ['lm-loop://example-loop/run-1/summary.json'],
      next_action: 'await_healthy_terminal',
    }),
  });

  assert.equal(result.state, 'queued');
  const outcome = (await journalRows(journal)).at(-1);
  assert.equal(outcome.record_type, 'recovery_outcome');
  assert.equal(outcome.before_event_id, 'event-before');
  assert.equal(outcome.after_event_id, 'event-after');
  assert.equal(outcome.budget_consumed, false);
  assert.equal(outcome.command_exit_code, 0);
  assert.equal(outcome.next_action, 'await_healthy_terminal');
  assert.deepEqual(outcome.readback, {
    event_id: 'event-after', loop_id: 'example-loop', owner_id: 'example-loop',
    installed_release_sha: SHA, event_release_sha: SHA,
  });
});

test('skips every Paid intent and consumes the next non-Paid owner without mutation', async () => {
  const { queue, journal } = await files([
    intent('paid', 'coconala-paid'), intent('safe', 'connector'),
  ]);
  const calls = [];
  const result = await consumeRecoveryIntentQueue({
    queuePath: queue,
    journalPath: journal,
    now: '2026-09-24T00:00:00.000Z',
    allowIntent: (value) => value.loop_id !== 'coconala-paid',
    executeIntent: async (value) => {
      calls.push(value.loop_id);
      return { ok: true, state: 'repaired', budget_consumed: false };
    },
  });

  assert.equal(result.loop_id, 'connector');
  assert.deepEqual(calls, ['connector']);
  assert.equal((await journalRows(journal)).some((row) => row.loop_id === 'coconala-paid'), false);
});
