import test from 'node:test';
import assert from 'node:assert/strict';
import { chmod, mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { buildRecoveryApplyPlan } from '../recovery-apply-plan.mjs';
import { executeRecoveryPlan } from '../recovery-executor.mjs';
import { buildRecoveryIntent } from '../recovery-intent.mjs';
import { consumeRecoveryIntentQueue } from '../recovery-supervisor.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..', '..');
const FIXTURE_PATH = path.join(
  HERE, '..', 'fixtures', 'self-heal', 'connector-wake-boundary-canary.json',
);

async function fixture() {
  return JSON.parse(await readFile(FIXTURE_PATH, 'utf8'));
}

test('one shared recovery supervisor owner continuously consumes non-Paid intents', async () => {
  const registry = JSON.parse(await readFile(path.join(REPO_ROOT, 'config/loop-registry.json'), 'utf8'));
  const catalog = JSON.parse(await readFile(
    path.join(REPO_ROOT, 'apps/life-manager/config/product-loop-catalog.json'), 'utf8',
  ));
  const entry = registry.loops['life-manager-recovery-supervisor'];
  const selfBuild = catalog.loops.find((loop) => loop.id === 'self-build');

  assert.deepEqual(entry, {
    adapter: 'exec',
    admission_class: 'borrow',
    cadence: { start_interval_seconds: 60 },
    cleanup: { max_age_days: 14, max_runs: 100 },
    command: [],
    domain: 'system',
    effect_class: 'none',
    entrypoint: 'runtime/loop/recovery-supervisor-cli.mjs',
    label: 'ai.anicca.life-manager-recovery-supervisor',
    log_root: '~/.local/state/life-manager/recovery/logs',
    priority: 'support',
    provider_route: 'deterministic',
    resource_class: 'deterministic',
    state_root: '~/.local/state/life-manager/recovery',
  });
  assert.equal(catalog.loops.filter(
    (loop) => loop.job_ids.includes('life-manager-recovery-supervisor'),
  ).length, 1);
  assert.ok(selfBuild.job_ids.includes('life-manager-recovery-supervisor'));
});

test('canary fixture is pinned to the canonical non-Paid Connector owner contract', async () => {
  const value = await fixture();
  const registry = JSON.parse(await readFile(path.join(REPO_ROOT, 'config/loop-registry.json'), 'utf8'));
  const catalog = JSON.parse(await readFile(
    path.join(REPO_ROOT, 'apps/life-manager/config/product-loop-catalog.json'), 'utf8',
  ));
  const entry = registry.loops[value.target.loop_id];
  const connector = catalog.loops.find((loop) => loop.id === 'connector');

  assert.equal(entry.label, value.target.label);
  assert.equal(entry.provider_route, 'deterministic');
  assert.equal(entry.effect_class, 'none');
  assert.notEqual(entry.priority, 'critical_paid');
  assert.doesNotMatch(entry.entrypoint, /paid-(?:owner|direct-owner)$/);
  assert.ok(connector.job_ids.includes(value.target.loop_id));
});

function registryFor(value) {
  const row = (item) => ({
    label: item.label,
    provider_route: item.provider_route,
    effect_class: item.effect_class,
    entrypoint: 'bin/test-owned-entrypoint',
    priority: 'support',
  });
  return {
    loops: {
      [value.target.loop_id]: row(value.target),
      [value.sibling.loop_id]: row(value.sibling),
    },
  };
}

async function releaseRoot(sha) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'lm-recovery-canary-release-'));
  await mkdir(path.join(root, 'bin'));
  await writeFile(path.join(root, 'RELEASE.json'), `${JSON.stringify({ sha })}\n`);
  const executable = path.join(root, 'bin', 'lm-loop');
  await writeFile(executable, '#!/bin/sh\nexit 97\n');
  await chmod(executable, 0o755);
  return root;
}

async function queueFiles(intent) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'lm-recovery-canary-state-'));
  const queuePath = path.join(root, 'intents.jsonl');
  const journalPath = path.join(root, 'supervisor.jsonl');
  await writeFile(queuePath, `${JSON.stringify({ ...intent, record_type: 'recovery_intent' })}\n`);
  return { queuePath, journalPath };
}

async function journalRows(file) {
  const text = await readFile(file, 'utf8');
  return text.split('\n').filter(Boolean).map(JSON.parse);
}

function initialInstallation(value) {
  return {
    [value.target.loop_id]: {
      event_id: 'event-before',
      release_sha: value.release_sha,
      terminal: 'fail',
      diagnostic_complete: false,
      blocker: 'wake_boundary_failed',
    },
    [value.sibling.loop_id]: {
      event_id: 'sibling-stable',
      release_sha: value.release_sha,
      terminal: 'pass',
      diagnostic_complete: true,
      blocker: null,
    },
  };
}

function statusResult(value, installation) {
  const target = installation[value.target.loop_id];
  return {
    code: 0,
    stdout: JSON.stringify([{
      classification: 'managed',
      event_id: target.event_id,
      loop_id: value.target.loop_id,
      job_id: value.target.loop_id,
      owner_id: value.target.loop_id,
      occurrence_id: value.failure_event.occurrence_id,
      launchd_state: 'loaded-idle',
      installed_release_sha: target.release_sha,
      event_release_sha: target.release_sha,
      last_terminal_result: target.terminal,
      diagnostic_complete: target.diagnostic_complete,
      effect_status: 'not_applicable',
      blocker: target.blocker,
      evidence_refs: value.failure_event.evidence_refs,
    }]),
    stderr: '',
  };
}

function successfulReconcile(value) {
  return {
    code: 0,
    stdout: JSON.stringify({
      ok: true,
      route: value.target.provider_route,
      release_sha: value.release_sha,
      eligible: 1,
      applied: [{ loop_id: value.target.loop_id, label: value.target.label }],
      failed: [],
    }),
    stderr: '',
  };
}

test('test-owned Connector failure heals end to end and exact replay is zero', async () => {
  const value = await fixture();
  const intent = buildRecoveryIntent(value.failure_event);
  const registry = registryFor(value);
  const root = await releaseRoot(value.release_sha);
  const { queuePath, journalPath } = await queueFiles(intent);
  const installation = initialInstallation(value);
  const siblingBefore = structuredClone(installation[value.sibling.loop_id]);
  const calls = [];

  const options = {
    queuePath,
    journalPath,
    now: '2026-09-24T00:00:00.000Z',
    executeIntent: async (selected) => executeRecoveryPlan({
      plan: buildRecoveryApplyPlan({ intent: selected, registry }),
      registry,
      releaseRoot: root,
      readStatus: async (request) => {
        calls.push(request.args);
        return statusResult(value, installation);
      },
      runCommand: async (request) => {
        calls.push(request.args);
        installation[value.target.loop_id] = {
          event_id: 'event-after',
          release_sha: value.release_sha,
          terminal: 'pass',
          diagnostic_complete: true,
          blocker: null,
        };
        return successfulReconcile(value);
      },
    }),
  };

  const healed = await consumeRecoveryIntentQueue(options);
  const replay = await consumeRecoveryIntentQueue(options);

  assert.equal(healed.state, 'repaired');
  assert.equal(healed.loop_id, value.target.loop_id);
  assert.deepEqual(replay, { ok: true, state: 'idle', reason: 'no_pending_intent' });
  assert.deepEqual(calls, [
    ['status', value.target.loop_id],
    ['reconcile', 'deterministic', '--loaded-idle-only', '--max-owners', '1',
      '--loop-id', value.target.loop_id],
    ['status', value.target.loop_id],
  ]);
  assert.deepEqual(installation[value.sibling.loop_id], siblingBefore);
  const outcome = (await journalRows(journalPath)).find((row) => row.record_type === 'recovery_outcome');
  assert.equal(outcome.state, 'repaired');
  assert.equal(outcome.before_event_id, 'event-before');
  assert.equal(outcome.after_event_id, 'event-after');
  assert.equal(outcome.release_sha, value.release_sha);
  assert.equal(outcome.budget_consumed, true);
});

test('forced canary verification failure restores the test-owned snapshot within budget', async () => {
  const value = await fixture();
  const intent = buildRecoveryIntent({
    ...value.failure_event,
    run_id: 'run-canary-rollback',
    occurrence_id: `${value.target.loop_id}:run-canary-rollback`,
  });
  const registry = registryFor(value);
  const root = await releaseRoot(value.release_sha);
  const { queuePath, journalPath } = await queueFiles(intent);
  const installation = initialInstallation(value);
  const targetBefore = structuredClone(installation[value.target.loop_id]);
  const siblingBefore = structuredClone(installation[value.sibling.loop_id]);
  let attempts = 0;

  const executeIntent = async (selected) => executeRecoveryPlan({
    plan: buildRecoveryApplyPlan({ intent: selected, registry }),
    registry,
    releaseRoot: root,
    readStatus: async () => statusResult(value, installation),
    runCommand: async () => {
      attempts += 1;
      const snapshot = structuredClone(installation[value.target.loop_id]);
      installation[value.target.loop_id] = {
        event_id: 'event-canary-red',
        release_sha: value.release_sha,
        terminal: 'fail',
        diagnostic_complete: false,
        blocker: 'forced_canary_verification_failure',
      };
      // This is a test-owned analogue of lm-loop's atomic plist snapshot restore:
      // a verification failure restores the exact prior owner state before returning RED.
      installation[value.target.loop_id] = snapshot;
      return {
        code: 1,
        stdout: JSON.stringify({
          ok: false,
          route: value.target.provider_route,
          release_sha: value.release_sha,
          eligible: 1,
          applied: [],
          failed: [{ loop_id: value.target.loop_id, reason: 'forced_verification_failure' }],
        }),
        stderr: 'forced verification failure; snapshot restored',
      };
    },
  });

  const first = await consumeRecoveryIntentQueue({
    queuePath, journalPath, executeIntent,
    maxAttempts: 3, cooldownSeconds: 60, now: '2026-09-24T00:00:00.000Z',
  });
  const duringCooldown = await consumeRecoveryIntentQueue({
    queuePath, journalPath, executeIntent,
    maxAttempts: 3, cooldownSeconds: 60, now: '2026-09-24T00:00:30.000Z',
  });

  assert.equal(first.state, 'queued');
  assert.equal(first.attempt, 1);
  assert.deepEqual(duringCooldown, { ok: true, state: 'idle', reason: 'cooldown_active' });
  assert.equal(attempts, 1);
  assert.deepEqual(installation[value.target.loop_id], targetBefore);
  assert.deepEqual(installation[value.sibling.loop_id], siblingBefore);
  const outcome = (await journalRows(journalPath)).find((row) => row.record_type === 'recovery_outcome');
  assert.equal(outcome.state, 'queued');
  assert.equal(outcome.reason, 'reconcile_failed');
  assert.equal(outcome.budget_consumed, true);
  assert.equal(outcome.next_action, 'retry_after_cooldown');
});
