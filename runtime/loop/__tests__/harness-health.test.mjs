/**
 * harness-health.test.mjs — RED (Phase 2a, feature anicca-harness-tooluse-health).
 * R1, R2, R3, R4, R5 (behavioral-spec.md + verification-architecture.md proof table).
 *
 * runtime/loop/harness-health.mjs does not exist yet -> import fails -> RED.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  classifyLayer,
  computeSlotHealth,
  computeBrainTransportHealth,
  computeHarnessHealth,
  decideRecoveryAction,
  shouldEscalate,
  DEFAULT_STREAK_THRESHOLD,
} from '../harness-health.mjs';

// ── R1: classifyLayer — pure, fixed-enum mapping (never throws) ─────────────

test('R1: {wake,narrate,shutdown} -> clean', () => {
  assert.equal(classifyLayer({ kind: 'wake' }), 'clean');
  assert.equal(classifyLayer({ kind: 'narrate' }), 'clean');
  assert.equal(classifyLayer({ kind: 'shutdown' }), 'clean');
});

test('R1: wake_error -> brain_transport', () => {
  assert.equal(classifyLayer({ kind: 'wake_error' }), 'brain_transport');
});

test('R1: skill_missing -> tool_missing', () => {
  assert.equal(classifyLayer({ kind: 'skill_missing' }), 'tool_missing');
});

test('R1: skill_timeout -> tool_timeout', () => {
  assert.equal(classifyLayer({ kind: 'skill_timeout' }), 'tool_timeout');
});

test('R1: skill_error -> tool_logic', () => {
  assert.equal(classifyLayer({ kind: 'skill_error' }), 'tool_logic');
});

test('R1: unrecognized kind string -> unknown, never throws', () => {
  assert.equal(classifyLayer({ kind: 'some_future_kind_nobody_wrote_yet' }), 'unknown');
  assert.doesNotThrow(() => classifyLayer({}));
  assert.doesNotThrow(() => classifyLayer(null));
});

// ── R2: computeSlotHealth — pure, per-slot, loop_detect-excluded ────────────

test('R2: [wake,wake,skill_error,skill_error] for slot x -> wakes:4 failures:2 rate:0.5 streak:2', () => {
  const records = [
    { ts: 1, wake_id: 'a', kind: 'wake', slot: 'x' },
    { ts: 2, wake_id: 'b', kind: 'wake', slot: 'x' },
    { ts: 3, wake_id: 'c', kind: 'skill_error', slot: 'x' },
    { ts: 4, wake_id: 'd', kind: 'skill_error', slot: 'x' },
  ];
  const health = computeSlotHealth(records, 'x');
  assert.equal(health.wakes, 4);
  assert.equal(health.failures, 2);
  assert.equal(health.failureRate, 0.5);
  assert.equal(health.consecutiveFailureStreak, 2);
  assert.equal(health.lastFailureLayer, 'tool_logic');
  assert.equal(health.lastFailureTs, 4);
  assert.equal(health.lastFailureWakeId, 'd');
});

test('R2: a trailing wake after failures resets streak to 0', () => {
  const records = [
    { ts: 1, wake_id: 'a', kind: 'skill_error', slot: 'x' },
    { ts: 2, wake_id: 'b', kind: 'skill_error', slot: 'x' },
    { ts: 3, wake_id: 'c', kind: 'wake', slot: 'x' },
  ];
  const health = computeSlotHealth(records, 'x');
  assert.equal(health.consecutiveFailureStreak, 0);
});

test('R2: slot never present -> null', () => {
  const records = [{ ts: 1, wake_id: 'a', kind: 'wake', slot: 'x' }];
  assert.equal(computeSlotHealth(records, 'never-seen'), null);
});

test('R2: records with a DIFFERENT slot are excluded from x\'s count', () => {
  const records = [
    { ts: 1, wake_id: 'a', kind: 'wake', slot: 'x' },
    { ts: 2, wake_id: 'b', kind: 'skill_error', slot: 'y' },
  ];
  const health = computeSlotHealth(records, 'x');
  assert.equal(health.wakes, 1);
  assert.equal(health.failures, 0);
});

test('R2 (INV-LOOPDETECT-SEPARATE): a loop_detect record carrying slot:\'x\' is excluded entirely', () => {
  // FIND-001 live-data hazard: 238/1063 real loop_detect rows carry a matching slot value.
  const records = [
    { ts: 1, wake_id: 'a', kind: 'wake', slot: 'x' },
    { ts: 2, wake_id: 'b', kind: 'loop_detect', slot: 'x' },
    { ts: 3, wake_id: 'c', kind: 'skill_error', slot: 'x' },
  ];
  const health = computeSlotHealth(records, 'x');
  assert.equal(health.wakes, 2, 'loop_detect must not count toward wakes');
  assert.equal(health.failures, 1, 'loop_detect must not count toward failures');
});

// ── R3: computeBrainTransportHealth — pure, loop-level, never per-slot ──────

test('R3: wake_error (no slot) interspersed among slot records is counted independently', () => {
  const records = [
    { ts: 1, wake_id: 'a', kind: 'wake', slot: 'x' },
    { ts: 2, wake_id: 'b', kind: 'wake_error' },
    { ts: 3, wake_id: 'c', kind: 'skill_error', slot: 'x' },
  ];
  const brain = computeBrainTransportHealth(records);
  assert.equal(brain.failures, 1);
  const slotHealth = computeSlotHealth(records, 'x');
  assert.equal(slotHealth.failures, 1, 'wake_error must never inflate a slot\'s own failures');
});

test('R3: a wake_error immediately followed by a slot\'s own skill_error does NOT inflate that slot\'s streak', () => {
  const records = [
    { ts: 1, wake_id: 'a', kind: 'wake', slot: 'x' },
    { ts: 2, wake_id: 'b', kind: 'wake_error' },
    { ts: 3, wake_id: 'c', kind: 'skill_error', slot: 'x' },
  ];
  const slotHealth = computeSlotHealth(records, 'x');
  assert.equal(slotHealth.consecutiveFailureStreak, 1, 'only the real skill_error counts toward x\'s streak');
  const brain = computeBrainTransportHealth(records);
  assert.equal(brain.consecutiveFailureStreak, 1, 'the wake_error itself is brain-transport\'s own streak of 1');
});

test('R3: brain-transport streak resets on wake/narrate, counts trailing wake_error only', () => {
  const records = [
    { ts: 1, wake_id: 'a', kind: 'wake_error' },
    { ts: 2, wake_id: 'b', kind: 'wake' },
    { ts: 3, wake_id: 'c', kind: 'wake_error' },
    { ts: 4, wake_id: 'd', kind: 'wake_error' },
  ];
  const brain = computeBrainTransportHealth(records);
  assert.equal(brain.failures, 3);
  assert.equal(brain.consecutiveFailureStreak, 2, 'only the trailing 2 wake_error records after the wake reset count');
  assert.equal(brain.lastFailureTs, 4);
  assert.equal(brain.lastFailureWakeId, 'd');
});

// ── R4: computeHarnessHealth — pure, whole-ledger report shape ──────────────

test('R4: multi-slot fixture -> perSlot keys match exactly the distinct slots present', () => {
  const records = [
    { ts: 1, wake_id: 'a', kind: 'wake', slot: 'yield' },
    { ts: 2, wake_id: 'b', kind: 'skill_error', slot: 'yield' },
    { ts: 3, wake_id: 'c', kind: 'wake', slot: 'x402_sell' },
    { ts: 4, wake_id: 'd', kind: 'wake_error' },
  ];
  const report = computeHarnessHealth(records, { streakThreshold: 5 });
  assert.deepEqual(Object.keys(report.perSlot).sort(), ['x402_sell', 'yield']);
  assert.equal(report.perSlot.yield.escalate, false);
  assert.equal(report.perSlot.x402_sell.escalate, false);
  assert.ok('generatedAt' in report);
});

test('R4: empty records -> R4 empty-ledger shape, never throws', () => {
  const report = computeHarnessHealth([]);
  assert.deepEqual(report.perSlot, {});
  assert.equal(report.brainTransport.failures, 0);
  assert.equal(report.brainTransport.consecutiveFailureStreak, 0);
  assert.equal(report.brainTransport.lastFailureTs, null);
  assert.equal(report.brainTransport.lastFailureWakeId, null);
  assert.equal(report.brainTransport.escalate, false);
  assert.ok('generatedAt' in report);
  assert.doesNotThrow(() => computeHarnessHealth(undefined));
  assert.doesNotThrow(() => computeHarnessHealth(null));
});

test('R4: every perSlot/brainTransport entry carries escalate computed via R5 with the passed streakThreshold', () => {
  const records = [
    { ts: 1, wake_id: 'a', kind: 'skill_error', slot: 'x' },
    { ts: 2, wake_id: 'b', kind: 'skill_error', slot: 'x' },
    { ts: 3, wake_id: 'c', kind: 'wake_error' },
    { ts: 4, wake_id: 'd', kind: 'wake_error' },
  ];
  const report = computeHarnessHealth(records, { streakThreshold: 2 });
  assert.equal(report.perSlot.x.consecutiveFailureStreak, 2);
  assert.equal(report.perSlot.x.escalate, true, 'streak(2) >= threshold(2) must escalate');
  assert.equal(report.brainTransport.consecutiveFailureStreak, 2);
  assert.equal(report.brainTransport.escalate, true);
});

// ── R5: shouldEscalate — pure boundary predicate ─────────────────────────────

test('R5: one below threshold -> false', () => {
  assert.equal(shouldEscalate(4, 5), false);
});

test('R5: exactly at threshold -> true', () => {
  assert.equal(shouldEscalate(5, 5), true);
});

test('R5: one above threshold -> true', () => {
  assert.equal(shouldEscalate(6, 5), true);
});

test('R5: DEFAULT_STREAK_THRESHOLD is 5 when HARNESS_HEALTH_STREAK_THRESHOLD is unset (Number(process.env.X) || N idiom)', () => {
  assert.equal(DEFAULT_STREAK_THRESHOLD, 5);
});

test('R10: healthy owner continues without touching siblings', () => {
  assert.deepEqual(decideRecoveryAction({
    ownerId: 'owner-1',
    health: { slot: 'x', failures: 0, consecutiveFailureStreak: 0 },
    retryAttempts: 0,
    retryLimit: 2,
    streakThreshold: 5,
  }), {
    action: 'continue',
    ownerId: 'owner-1',
    slot: 'x',
    reason: 'healthy',
    retryAttempt: 0,
    preserveSiblings: true,
  });
});

test('R10: a bounded failure retries only the same owner', () => {
  assert.deepEqual(decideRecoveryAction({
    ownerId: 'owner-1',
    health: { slot: 'x', failures: 1, consecutiveFailureStreak: 1 },
    retryAttempts: 0,
    retryLimit: 2,
    streakThreshold: 5,
  }), {
    action: 'retry_owner',
    ownerId: 'owner-1',
    slot: 'x',
    reason: 'bounded_retry',
    retryAttempt: 1,
    preserveSiblings: true,
  });
});

test('R10: a failure streak escalates instead of restarting forever', () => {
  assert.deepEqual(decideRecoveryAction({
    ownerId: 'owner-1',
    health: { slot: 'x', failures: 5, consecutiveFailureStreak: 5 },
    retryAttempts: 1,
    retryLimit: 2,
    streakThreshold: 5,
  }), {
    action: 'escalate_repair',
    ownerId: 'owner-1',
    slot: 'x',
    reason: 'failure_streak_threshold',
    retryAttempt: 1,
    preserveSiblings: true,
  });
});

test('R10: exhausted retries become a typed blocker', () => {
  assert.deepEqual(decideRecoveryAction({
    ownerId: 'owner-1',
    health: { slot: 'x', failures: 1, consecutiveFailureStreak: 1 },
    retryAttempts: 2,
    retryLimit: 2,
    streakThreshold: 5,
  }), {
    action: 'escalate_repair',
    ownerId: 'owner-1',
    slot: 'x',
    reason: 'retry_budget_exhausted',
    retryAttempt: 2,
    preserveSiblings: true,
  });
});

// ── R8 cross-language parity anchor (JS side) — shared fixture with harness_health.py ──

test('R8 (JS side): computeHarnessHealth on the shared parity fixture matches its expected field-for-field (generatedAt excluded)', async () => {
  const { readFile } = await import('node:fs/promises');
  const path = await import('node:path');
  const { fileURLToPath } = await import('node:url');
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const fixturePath = path.join(__dirname, 'fixtures', 'harness-health-parity.json');
  const fixture = JSON.parse(await readFile(fixturePath, 'utf8'));

  const report = computeHarnessHealth(fixture.records, { streakThreshold: fixture.streakThreshold });
  const { generatedAt, ...withoutGeneratedAt } = report;
  assert.deepEqual(withoutGeneratedAt, fixture.expected);
});
