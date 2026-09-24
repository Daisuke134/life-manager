import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import recoveryClass from '../recovery-class.cjs';
import { buildRecoveryIntent } from '../recovery-intent.mjs';

const {
  RECOVERY_CLASSES,
  RECOVERY_PROMOTION_HOOKS,
  RECOVERY_PROMOTION_POLICY,
  classifyRecoveryJob,
  evaluateRecoveryPromotion,
} = recoveryClass;
const HERE = path.dirname(fileURLToPath(import.meta.url));

test('recovery class set is closed and stable', () => {
  assert.deepEqual([...RECOVERY_CLASSES], [
    'browser',
    'continuous_service',
    'deterministic',
    'external_effect_owner',
    'model',
    'read_only_external_owner',
  ]);
});

test('production recovery PR promotion remains class-bound and fail-closed without a loop runtime path', () => {
  assert.deepEqual([...RECOVERY_PROMOTION_HOOKS], [
    'immutable_release',
    'isolated_canary',
    'exact_health',
    'rollback',
  ]);
  assert.deepEqual(Object.keys(RECOVERY_PROMOTION_POLICY), [...RECOVERY_CLASSES]);
  for (const recoveryClass of RECOVERY_CLASSES) {
    assert.equal(RECOVERY_PROMOTION_POLICY[recoveryClass].runtime_path, 'unbound');
    assert.deepEqual(
      evaluateRecoveryPromotion(recoveryClass, {}).missing_hooks,
      [...RECOVERY_PROMOTION_HOOKS],
    );
    assert.deepEqual(evaluateRecoveryPromotion(recoveryClass, {
      immutable_release: true,
      isolated_canary: true,
      exact_health: true,
      rollback: true,
    }), {
      eligible: false,
      reason: 'recovery_runtime_promotion_unbound',
      missing_hooks: [],
    });
  }
});

test('each runtime owner resolves to exactly one highest-safety recovery class', () => {
  assert.equal(classifyRecoveryJob({
    priority: 'critical_paid', effect_class: 'money', provider_route: 'shared-agent-runner',
    resource_class: 'browser', cadence: { keep_alive: true }, entrypoint: 'x/paid-owner',
  }), 'read_only_external_owner');
  assert.equal(classifyRecoveryJob({
    effect_class: 'publish', provider_route: 'shared-agent-runner', resource_class: 'browser',
    cadence: { keep_alive: true }, entrypoint: 'x/run',
  }), 'external_effect_owner');
  assert.equal(classifyRecoveryJob({
    effect_class: 'none', provider_route: 'deterministic', cadence: { keep_alive: true },
    entrypoint: 'x/run',
  }), 'continuous_service');
  assert.equal(classifyRecoveryJob({
    effect_class: 'none', provider_route: 'deterministic', resource_class: 'browser',
    cadence: { start_interval_seconds: 30 }, entrypoint: 'x/run',
  }), 'browser');
  assert.equal(classifyRecoveryJob({
    effect_class: 'none', provider_route: 'shared-agent-runner',
    cadence: { start_interval_seconds: 30 }, entrypoint: 'x/run',
  }), 'model');
  assert.equal(classifyRecoveryJob({
    effect_class: 'none', provider_route: 'deterministic',
    cadence: { start_interval_seconds: 30 }, entrypoint: 'x/run',
  }), 'deterministic');
});

test('every recovery class has one retained failure fixture with the expected safe action', async () => {
  const fixture = JSON.parse(await readFile(path.join(
    HERE, '..', 'fixtures', 'self-heal', 'recovery-classes.json',
  ), 'utf8'));
  assert.equal(fixture.schema_version, 1);
  assert.deepEqual(fixture.classes.map((row) => row.id), [...RECOVERY_CLASSES]);
  for (const row of fixture.classes) {
    assert.equal(classifyRecoveryJob(row.registry_entry), row.id, row.id);
    assert.equal(buildRecoveryIntent(row.failure_event).action, row.expected.intent_action, row.id);
    assert.equal(row.expected.local_queue, row.id !== 'read_only_external_owner', row.id);
  }
});
