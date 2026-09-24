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
    'example-loop': {
      provider_route: 'deterministic', label: 'ai.anicca.example', effect_class: 'none',
      reconcile_queued_release: true,
    },
    'sibling-loop': {
      provider_route: 'deterministic', label: 'ai.anicca.sibling', effect_class: 'none',
    },
  },
};

function intent(overrides = {}) {
  return {
    schema_version: 1,
    intent_id: 'intent-1',
    loop_id: 'example-loop',
    owner_id: 'example-loop',
    occurrence_id: 'example-loop:run-1',
    release_sha: SHA,
    action: 'reconcile_owner',
    ...overrides,
  };
}

function status(overrides = {}) {
  return {
    classification: 'managed',
    loop_id: 'example-loop',
    job_id: 'example-loop',
    owner_id: 'example-loop',
    occurrence_id: 'example-loop:run-2',
    event_id: 'event-after',
    launchd_state: 'loaded-idle',
    installed_release_sha: SHA,
    event_release_sha: SHA,
    last_terminal_result: 'pass',
    diagnostic_complete: true,
    effect_status: 'not_applicable',
    blocker: null,
    evidence_refs: ['lm-loop://example-loop/run-2/summary.json'],
    ...overrides,
  };
}

function statusResult(row) {
  return { code: 0, stdout: JSON.stringify([row]), stderr: '' };
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
  const readbacks = [
    statusResult(status({
      event_id: 'event-before', event_release_sha: 'b'.repeat(40),
      last_terminal_result: 'fail', diagnostic_complete: false,
    })),
    statusResult(status({
      diagnostic_error: 'legacy_runtime_event_schema',
      failure_layer: 'runtime', error_class: 'legacy_runtime_event_schema',
      retryable: true, next_action: 'reload_current_release',
    })),
  ];
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
    readStatus: async (request) => {
      calls.push(request);
      return readbacks.shift();
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.state, 'repaired');
  assert.equal(calls.length, 3);
  assert.deepEqual(calls.map((call) => call.args), [
    ['status', 'example-loop'], plan.commands[0].args, ['status', 'example-loop'],
  ]);
  assert.equal(calls[1].executable, path.join(root, 'bin', 'lm-loop'));
  assert.equal(calls[1].env.LIFE_MANAGER_RELEASE_ROOT, root);
  assert.equal(calls[1].env.LIFE_MANAGER_LOOP_ID, 'life-manager-recovery-executor');
  assert.equal(result.before_readback.event_id, 'event-before');
  assert.equal(result.after_readback.event_id, 'event-after');
  assert.equal(result.after_readback.diagnostic_error, 'legacy_runtime_event_schema');
  assert.equal(result.after_readback.next_action, 'reload_current_release');
  assert.equal(result.budget_consumed, true);
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

test('routes an unclassified owner failure to guarded repair without reconciling', async () => {
  const plan = buildRecoveryApplyPlan({
    intent: intent({ action: 'escalate_owner' }),
    registry,
  });
  let invoked = false;
  const result = await executeRecoveryPlan({
    plan,
    registry,
    runCommand: async () => { invoked = true; throw new Error('must not run'); },
  });

  assert.equal(result.ok, true);
  assert.equal(result.state, 'escalated');
  assert.equal(result.next_action, 'guarded_code_repair');
  assert.equal(result.budget_consumed, false);
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
    readStatus: async () => statusResult(status({
      event_id: 'event-before', last_terminal_result: 'fail', blocker: 'entrypoint_exit_1',
    })),
  });

  assert.equal(result.ok, false);
  assert.equal(result.state, 'queued');
  assert.equal(result.reason, 'reconcile_failed');
});

test('keeps a pending-admission reconcile queued without consuming repair budget', async () => {
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
        applied: [],
        skipped_pending: ['example-loop'],
        failed: [],
      }),
      stderr: '',
    }),
    readStatus: async () => statusResult(status({
      event_id: 'event-before', last_terminal_result: 'fail', blocker: 'host_admission_deferred:resource_capacity_busy',
    })),
  });

  assert.equal(result.ok, false);
  assert.equal(result.state, 'queued');
  assert.equal(result.reason, 'admission_pending');
  assert.equal(result.next_action, 'retry_after_eligibility');
  assert.equal(result.budget_consumed, false);
  assert.equal(result.reconcile.skipped_pending[0], 'example-loop');
});

test('escalates a pending-admission reconcile when the release lacks its queue contract', async () => {
  const root = await releaseRoot();
  const registryWithoutContract = {
    loops: {
      ...registry.loops,
      'example-loop': { ...registry.loops['example-loop'], reconcile_queued_release: false },
    },
  };
  const plan = buildRecoveryApplyPlan({ intent: intent(), registry: registryWithoutContract });
  const result = await executeRecoveryPlan({
    plan,
    registry: registryWithoutContract,
    releaseRoot: root,
    runCommand: async () => ({
      code: 0,
      stdout: JSON.stringify({
        ok: true,
        route: 'deterministic',
        release_sha: SHA,
        eligible: 1,
        applied: [],
        skipped_pending: ['example-loop'],
        failed: [],
      }),
      stderr: '',
    }),
    readStatus: async () => statusResult(status({
      event_id: 'event-before', last_terminal_result: 'fail', blocker: 'host_admission_deferred:resource_capacity_busy',
    })),
  });

  assert.equal(result.ok, false);
  assert.equal(result.state, 'blocked');
  assert.equal(result.reason, 'admission_contract_missing');
  assert.equal(result.next_action, 'promote_release');
  assert.equal(result.budget_consumed, false);
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
    readStatus: async () => statusResult(status({
      event_id: 'event-before', last_terminal_result: 'fail', blocker: 'entrypoint_exit_1',
    })),
  });

  assert.equal(result.ok, false);
  assert.equal(result.state, 'blocked');
  assert.equal(result.reason, 'reconcile_target_not_applied');
});

test('keeps the intent queued when post-reconcile readback is not the exact owner and release', async () => {
  const root = await releaseRoot();
  const plan = buildRecoveryApplyPlan({ intent: intent(), registry });
  const readbacks = [
    statusResult(status({ event_id: 'before', last_terminal_result: 'fail' })),
    statusResult(status({ event_id: 'after', owner_id: 'sibling-loop' })),
  ];
  const result = await executeRecoveryPlan({
    plan,
    registry,
    releaseRoot: root,
    runCommand: async () => ({
      code: 0,
      stdout: JSON.stringify({
        ok: true, route: 'deterministic', release_sha: SHA, eligible: 1,
        applied: [{ label: 'ai.anicca.example' }], failed: [],
      }),
      stderr: '',
    }),
    readStatus: async () => readbacks.shift(),
  });

  assert.equal(result.ok, false);
  assert.equal(result.state, 'queued');
  assert.equal(result.reason, 'healthy_readback_pending');
  assert.equal(result.after_readback.owner_id, 'sibling-loop');
});

test('closes an already healthy intent from exact readback without another reconcile', async () => {
  const root = await releaseRoot();
  const plan = buildRecoveryApplyPlan({ intent: intent(), registry });
  let reconciled = false;
  const result = await executeRecoveryPlan({
    plan,
    registry,
    releaseRoot: root,
    runCommand: async () => { reconciled = true; throw new Error('must not reconcile'); },
    readStatus: async () => statusResult(status()),
  });

  assert.equal(result.ok, true);
  assert.equal(result.state, 'repaired');
  assert.equal(result.executed, false);
  assert.equal(result.budget_consumed, false);
  assert.equal(reconciled, false);
});
