import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRecoveryApplyPlan } from '../recovery-apply-plan.mjs';

const registry = { loops: {
  'example-loop': { provider_route: 'deterministic', entrypoint: 'bin/example' },
  'life-manager-recovery-supervisor': {
    provider_route: 'deterministic', entrypoint: 'runtime/loop/recovery-supervisor-cli.mjs',
  },
  'paid-loop': {
    provider_route: 'deterministic', entrypoint: 'skills/earn/gig/scripts/paid-direct-owner',
    priority: 'critical_paid',
  },
} };
const intent = (overrides = {}) => ({
  schema_version: 1, intent_id: 'intent-1', loop_id: 'example-loop', owner_id: 'example-loop',
  occurrence_id: 'example-loop:run-1', release_sha: 'a'.repeat(40),
  action: 'reconcile_owner', ...overrides,
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

test('plan rejects an owner identity that differs from the target job', () => {
  assert.throws(
    () => buildRecoveryApplyPlan({ intent: intent({ owner_id: 'sibling-loop' }), registry }),
    /owner identity mismatch/,
  );
});

test('plan refuses every Paid fulfillment owner even if a queue row is forged', () => {
  assert.throws(
    () => buildRecoveryApplyPlan({ intent: intent({
      loop_id: 'paid-loop', owner_id: 'paid-loop', occurrence_id: 'paid-loop:run-1',
    }), registry }),
    /paid owner excluded/,
  );
});

test('plan refuses the recovery supervisor itself even if a queue row already exists', () => {
  assert.throws(
    () => buildRecoveryApplyPlan({ intent: intent({
      loop_id: 'life-manager-recovery-supervisor',
      owner_id: 'life-manager-recovery-supervisor',
      occurrence_id: 'life-manager-recovery-supervisor:run-1',
    }), registry }),
    /supervisor owner excluded/,
  );
});
