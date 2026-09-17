import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRecoveryIntent } from '../recovery-intent.mjs';

const base = (overrides = {}) => ({
  loop_id: 'example-loop', owner_id: 'owner-1', wake_id: 'wake-1', run_id: 'run-1',
  release_sha: 'a'.repeat(40), status: 'fail', failure_layer: 'tool_timeout',
  effect_class: 'none', effect_status: 'not_applicable', blocker: 'timeout',
  consecutive_failure_streak: 1, threshold: 3, evidence_refs: ['lm-loop://example-loop/run-1/summary.json'],
  ...overrides,
});

test('recovery intent reconciles one owner without mutating an external effect', () => {
  const intent = buildRecoveryIntent(base());
  assert.equal(intent.action, 'reconcile_owner');
  assert.equal(intent.retryable, true);
  assert.equal(intent.mutates_external_effect, false);
  assert.equal(intent.effect_fence, 'not_required');
});

test('unknown effect is fenced and never retried automatically', () => {
  const intent = buildRecoveryIntent(base({ effect_class: 'application', effect_status: 'unknown' }));
  assert.equal(intent.action, 'hold_effect_unknown');
  assert.equal(intent.retryable, false);
  assert.equal(intent.effect_fence, 'required');
});

test('repeated failures escalate instead of retrying forever', () => {
  const intent = buildRecoveryIntent(base({ consecutive_failure_streak: 3 }));
  assert.equal(intent.action, 'escalate_repeated_failure');
  assert.equal(intent.retryable, false);
});

test('healthy terminal emits no action', () => {
  const intent = buildRecoveryIntent(base({ status: 'pass', failure_layer: 'clean' }));
  assert.equal(intent.action, 'no_action');
  assert.equal(intent.retryable, false);
});

test('different owners cannot share an intent identity', () => {
  const first = buildRecoveryIntent(base({ owner_id: 'owner-1' }));
  const second = buildRecoveryIntent(base({ owner_id: 'owner-2' }));
  assert.notEqual(first.intent_id, second.intent_id);
});
