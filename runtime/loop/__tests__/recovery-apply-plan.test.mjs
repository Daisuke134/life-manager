import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRecoveryApplyPlan } from '../recovery-apply-plan.mjs';

const registry = { loops: { 'example-loop': { provider_route: 'deterministic' } } };
const intent = (overrides = {}) => ({
  schema_version: 1, intent_id: 'intent-1', loop_id: 'example-loop', owner_id: 'owner-1',
  release_sha: 'a'.repeat(40), action: 'reconcile_owner', ...overrides,
});

test('reconcile intent becomes one owner-scoped loaded-idle plan', () => {
  const plan = buildRecoveryApplyPlan({ intent: intent(), registry });
  assert.equal(plan.execute, true);
  assert.deepEqual(plan.commands[0].args, [
    'reconcile', 'deterministic', '--loaded-idle-only', '--max-owners', '1', '--loop-id', 'example-loop',
  ]);
  assert.equal(plan.constraints.sibling_mutation, false);
  assert.equal(plan.constraints.external_effect, false);
});

test('uncertain effect intent produces no automatic command', () => {
  const plan = buildRecoveryApplyPlan({ intent: intent({ action: 'hold_effect_unknown' }), registry });
  assert.equal(plan.execute, false);
  assert.deepEqual(plan.commands, []);
});

test('plan rejects an owner absent from the canonical registry', () => {
  assert.throws(
    () => buildRecoveryApplyPlan({ intent: intent({ loop_id: 'missing-loop' }), registry }),
    /not in registry/,
  );
});
