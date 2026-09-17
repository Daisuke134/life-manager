import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRecoveryIntentRecord } from '../recovery-intent-record.mjs';

const SHA = 'a'.repeat(40);

test('failure record becomes an owner-scoped recovery intent with no external mutation', () => {
  const intent = buildRecoveryIntentRecord({
    loopId: 'example-loop',
    ownerId: 'example-loop',
    wakeId: 'wake-1',
    runId: 'run-1',
    releaseSha: SHA,
    failureLayer: 'tool_timeout',
  });

  assert.equal(intent.loop_id, 'example-loop');
  assert.equal(intent.owner_id, 'example-loop');
  assert.equal(intent.action, 'reconcile_owner');
  assert.equal(intent.mutates_external_effect, false);
  assert.deepEqual(intent.evidence_refs, ['lm-loop://example-loop/wake-1/failure']);
});

test('effect-bearing unknown state is fenced instead of retried', () => {
  const intent = buildRecoveryIntentRecord({
    loopId: 'example-loop', ownerId: 'example-loop', wakeId: 'wake-2', runId: 'run-2',
    releaseSha: SHA, failureLayer: 'tool_logic', effectClass: 'message', effectStatus: 'unknown',
  });
  assert.equal(intent.action, 'hold_effect_unknown');
  assert.equal(intent.effect_fence, 'required');
  assert.equal(intent.retryable, false);
});

test('missing owner or immutable release returns no intent rather than guessing a target', () => {
  assert.equal(buildRecoveryIntentRecord({
    loopId: null, ownerId: null, wakeId: 'wake-3', runId: 'run-3', releaseSha: SHA,
    failureLayer: 'tool_logic',
  }), null);
  assert.equal(buildRecoveryIntentRecord({
    loopId: 'example-loop', ownerId: 'example-loop', wakeId: 'wake-4', runId: 'run-4',
    releaseSha: 'unknown', failureLayer: 'tool_logic',
  }), null);
});
