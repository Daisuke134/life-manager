import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, chmod } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { buildRecoveryApplyPlan } from '../recovery-apply-plan.mjs';
import { executeRecoveryPlan } from '../recovery-executor.mjs';

const SHA = 'a'.repeat(40);
const registry = {
  loops: {
    'example-loop': { provider_route: 'deterministic', label: 'ai.anicca.example' },
    'sibling-loop': { provider_route: 'deterministic', label: 'ai.anicca.sibling' },
  },
};

function intent(overrides = {}) {
  return {
    schema_version: 1,
    intent_id: 'intent-1',
    loop_id: 'example-loop',
    owner_id: 'owner-1',
    release_sha: SHA,
    action: 'reconcile_owner',
    ...overrides,
  };
}

async function releaseRoot(sha = SHA) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'lm-recovery-executor-'));
  await mkdir(path.join(root, 'bin'));
  await writeFile(path.join(root, 'RELEASE.json'), `${JSON.stringify({ sha })}\n`);
  const executable = path.join(root, 'bin', 'lm-loop');
  await writeFile(executable, '#!/bin/sh\n');
  await chmod(executable, 0o755);
  return root;
}

test('executes exactly one owner-scoped reconcile on the intended release', async () => {
  const root = await releaseRoot();
  const plan = buildRecoveryApplyPlan({ intent: intent(), registry });
  const calls = [];
  const result = await executeRecoveryPlan({
    plan,
    registry,
    releaseRoot: root,
    runCommand: async (request) => {
      calls.push(request);
      return {
        code: 0,
        stdout: JSON.stringify({
          ok: true,
          route: 'deterministic',
          release_sha: SHA,
          eligible: 1,
          applied: [{ label: 'ai.anicca.example' }],
          failed: [],
        }),
        stderr: '',
      };
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.state, 'repaired');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].executable, path.join(root, 'bin', 'lm-loop'));
  assert.deepEqual(calls[0].args, plan.commands[0].args);
  assert.equal(calls[0].env.LIFE_MANAGER_RELEASE_ROOT, root);
  assert.equal(calls[0].env.LIFE_MANAGER_LOOP_ID, 'life-manager-recovery-executor');
});

test('holds uncertain-effect plans without invoking reconcile', async () => {
  const plan = buildRecoveryApplyPlan({
    intent: intent({ action: 'hold_effect_unknown' }),
    registry,
  });
  let invoked = false;
  const result = await executeRecoveryPlan({
    plan,
    registry,
    runCommand: async () => { invoked = true; throw new Error('must not run'); },
  });

  assert.equal(result.ok, true);
  assert.equal(result.state, 'held');
  assert.equal(invoked, false);
});

test('refuses a plan whose release SHA is not the loaded release', async () => {
  const root = await releaseRoot('b'.repeat(40));
  const plan = buildRecoveryApplyPlan({ intent: intent(), registry });
  let invoked = false;
  const result = await executeRecoveryPlan({
    plan,
    registry,
    releaseRoot: root,
    runCommand: async () => { invoked = true; return {}; },
  });

  assert.equal(result.ok, false);
  assert.equal(result.state, 'blocked');
  assert.equal(result.reason, 'release_sha_mismatch');
  assert.equal(invoked, false);
});

test('refuses a plan that could target a sibling or more than one owner', async () => {
  const root = await releaseRoot();
  const base = buildRecoveryApplyPlan({ intent: intent(), registry });
  const plan = {
    ...base,
    commands: [{
      ...base.commands[0],
      args: ['reconcile', 'deterministic', '--loaded-idle-only', '--max-owners', '2', '--loop-id', 'sibling-loop'],
    }, base.commands[0]],
  };
  let invoked = false;
  const result = await executeRecoveryPlan({
    plan,
    registry,
    releaseRoot: root,
    runCommand: async () => { invoked = true; return {}; },
  });

  assert.equal(result.ok, false);
  assert.equal(result.state, 'blocked');
  assert.equal(result.reason, 'command_contract_invalid');
  assert.equal(invoked, false);
});

test('keeps a failed reconcile queued for the next bounded wake', async () => {
  const root = await releaseRoot();
  const plan = buildRecoveryApplyPlan({ intent: intent(), registry });
  const result = await executeRecoveryPlan({
    plan,
    registry,
    releaseRoot: root,
    runCommand: async () => ({
      code: 1,
      stdout: JSON.stringify({ ok: false, failed: [{ loop_id: 'example-loop' }] }),
      stderr: 'resource_control_busy',
    }),
  });

  assert.equal(result.ok, false);
  assert.equal(result.state, 'queued');
  assert.equal(result.reason, 'reconcile_failed');
});

test('does not call a recovery repaired when reconcile applied another owner', async () => {
  const root = await releaseRoot();
  const plan = buildRecoveryApplyPlan({ intent: intent(), registry });
  const result = await executeRecoveryPlan({
    plan,
    registry,
    releaseRoot: root,
    runCommand: async () => ({
      code: 0,
      stdout: JSON.stringify({
        ok: true,
        route: 'deterministic',
        release_sha: SHA,
        eligible: 1,
        applied: [{ label: 'ai.anicca.sibling' }],
        failed: [],
      }),
      stderr: '',
    }),
  });

  assert.equal(result.ok, false);
  assert.equal(result.state, 'blocked');
  assert.equal(result.reason, 'reconcile_target_not_applied');
});
