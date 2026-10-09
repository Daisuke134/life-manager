import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRecoveryIntent } from '../recovery-intent.mjs';
import { buildRecoveryApplyPlan } from '../recovery-apply-plan.mjs';

const input = (started = false) => ({loop_id:'example', owner_id:'example', run_id:'run-1',
  wake_id:'wake-1', occurrence_id:'example:run-1', release_sha:'a'.repeat(40),
  status:'fail', failure_layer:'runtime', effect_class:'publish', effect_status:'not_applicable',
  storage_failure:{errno:28, operation:'scratch_allocation', effect_started:started,
    proof_ref:'lm-storage://example/run-1/scratch_allocation'}});

test('proved storage pre-effect reuses reconcile and carries its proof to execution', () => {
  const intent = buildRecoveryIntent(input());
  assert.equal(intent.action, 'reconcile_owner');
  assert.equal(intent.reason, 'storage_write_failed_pre_effect');
  const plan = buildRecoveryApplyPlan({intent, registry:{loops:{example:{provider_route:'deterministic'}}}});
  assert.deepEqual(plan.storage_failure, input().storage_failure);
});
test('unknown storage effect cannot be downgraded by a not-applicable label', () => {
  const intent = buildRecoveryIntent(input(null));
  assert.equal(intent.action, 'hold_effect_unknown');
  assert.equal(intent.retryable, false);
});
test('foreign proof and unsupported pre-effect operation are rejected', () => {
  const value = input(); value.storage_failure.proof_ref = 'lm-storage://other/run-1/scratch_allocation';
  assert.throws(() => buildRecoveryIntent(value));
  const other = input(); other.storage_failure.operation = 'provider_process';
  other.storage_failure.proof_ref = 'lm-storage://example/run-1/provider_process';
  assert.throws(() => buildRecoveryIntent(other));
});
