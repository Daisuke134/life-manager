import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildRecoveryIntentRecord } from '../recovery-intent-record.mjs';
import { consumeRecoveryIntentQueue } from '../recovery-supervisor.mjs';
import { supervisorExitCode } from '../recovery-supervisor-cli.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(readFileSync(
  path.join(HERE, '..', 'fixtures', 'self-heal', 'issue-5898-franklin-loop-release-sha-mismatch.json'),
  'utf8',
));

/**
 * Retained regression fixture for GitHub issue #5898: a queued franklin-loop
 * recovery intent was recorded under an older release than the one loaded by
 * the time the supervisor drained the queue. This pins down that the
 * supervisor's existing "superseded by promotion" closure (recovery control
 * plane, not touched here) already treats it as a non-failure and keeps
 * bounded recovery available for the same owner under the current release,
 * so a future regression in that boundary is caught here first.
 */

async function journalRows(journal) {
  return (await readFile(journal, 'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
}

test('#5898: franklin-loop intent superseded by promotion closes as a non-failure, matching the sanitized incident', async () => {
  const staleIntent = buildRecoveryIntentRecord(FIXTURE.failure_event);
  assert.equal(staleIntent.occurrence_id, FIXTURE.expected_outcome.occurrence_id);
  assert.equal(staleIntent.action, FIXTURE.expected_outcome.action);
  assert.equal(staleIntent.reason, FIXTURE.expected_outcome.intent_reason);

  const root = await mkdtemp(path.join(os.tmpdir(), 'lm-recovery-5898-'));
  const queue = path.join(root, 'intents.jsonl');
  const journal = path.join(root, 'supervisor.jsonl');
  await writeFile(queue, `${JSON.stringify({ record_type: 'recovery_intent', ...staleIntent })}\n`);

  const result = await consumeRecoveryIntentQueue({
    queuePath: queue,
    journalPath: journal,
    currentReleaseSha: FIXTURE.current_release_sha,
    executeIntent: async () => { throw new Error('must never execute a superseded intent'); },
    now: '2026-09-26T00:00:00.000Z',
  });

  // No pending intent left to select: the stale one is closed in-wake, so the
  // wake reports idle rather than surfacing a queued/blocked failure.
  assert.deepEqual(result, { ok: true, state: 'idle', reason: 'no_pending_intent' });

  const outcome = (await journalRows(journal)).find((row) => row.record_type === 'recovery_outcome');
  assert.equal(outcome.owner_id, FIXTURE.expected_outcome.owner_id);
  assert.equal(outcome.occurrence_id, FIXTURE.expected_outcome.occurrence_id);
  assert.equal(outcome.release_sha, FIXTURE.failure_event.releaseSha);
  assert.equal(outcome.failure_layer, FIXTURE.failure_event.failureLayer);
  assert.equal(outcome.action, FIXTURE.expected_outcome.action);
  assert.equal(outcome.state, FIXTURE.expected_outcome.state);
  assert.equal(outcome.attempt, FIXTURE.expected_outcome.attempt);
  assert.equal(outcome.before_event_id, FIXTURE.expected_outcome.before_event_id);
  assert.equal(outcome.after_event_id, FIXTURE.expected_outcome.after_event_id);
  assert.equal(outcome.command_exit_code, FIXTURE.expected_outcome.command_exit_code);
  assert.equal(outcome.reason, FIXTURE.expected_outcome.reason);
  assert.equal(outcome.next_action, FIXTURE.expected_outcome.next_action);

  // Non-failure per the supervisor CLI's own exit-code contract: a stale-release
  // closure must not page as an entrypoint failure.
  assert.equal(
    supervisorExitCode({ ok: false, state: outcome.state, reason: outcome.reason }),
    FIXTURE.expected_outcome.supervisor_exit_code,
  );
});

test('#5898: franklin-loop bounded recovery is not exhausted -- a fresh intent under the current release still repairs the owner', async () => {
  const staleIntent = buildRecoveryIntentRecord(FIXTURE.failure_event);
  const freshIntent = buildRecoveryIntentRecord({
    ...FIXTURE.failure_event,
    releaseSha: FIXTURE.current_release_sha,
    runId: `${FIXTURE.failure_event.runId}-retry`,
  });

  const root = await mkdtemp(path.join(os.tmpdir(), 'lm-recovery-5898-'));
  const queue = path.join(root, 'intents.jsonl');
  const journal = path.join(root, 'supervisor.jsonl');
  await writeFile(queue, [staleIntent, freshIntent]
    .map((intent) => `${JSON.stringify({ record_type: 'recovery_intent', ...intent })}\n`).join(''));

  const calls = [];
  const result = await consumeRecoveryIntentQueue({
    queuePath: queue,
    journalPath: journal,
    currentReleaseSha: FIXTURE.current_release_sha,
    executeIntent: async (intent) => {
      calls.push(intent.intent_id);
      return { ok: true, state: 'repaired' };
    },
    now: '2026-09-26T00:00:00.000Z',
  });

  assert.deepEqual(calls, [freshIntent.intent_id]);
  assert.equal(result.state, 'repaired');
  assert.equal(result.loop_id, FIXTURE.expected_outcome.owner_id);
});
