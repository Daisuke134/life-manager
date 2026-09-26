import test from 'node:test';
import assert from 'node:assert/strict';

import { promoteLoopRuntimeRepair } from '../recovery-promotion.mjs';

const MERGED_SHA = 'a'.repeat(40);
const OWNER = 'test-deterministic-owner';
const LABEL = 'ai.anicca.test-deterministic-owner';
const REPO_ROOT = '/repo';
const LOOPS_ROOT = '/loops';
const NEW_RELEASE = '/loops/releases/new-sha';
const PREVIOUS_RELEASE = '/loops/releases/previous-sha';

function deterministicRegistry() {
  return JSON.stringify({
    loops: {
      [OWNER]: {
        label: LABEL, effect_class: 'none', provider_route: 'deterministic',
        cadence: { start_interval_seconds: 30 }, entrypoint: 'bin/test-owned-entrypoint',
      },
    },
  });
}

function baseDeps({ registry = deterministicRegistry(), readlinkTarget = PREVIOUS_RELEASE } = {}) {
  const calls = [];
  return {
    calls,
    deps: {
      registryPath: `${REPO_ROOT}/config/loop-registry.json`,
      ledgerPath: '/state/promotions.jsonl',
      readFile: async (file) => {
        if (file === `${REPO_ROOT}/config/loop-registry.json`) return registry;
        if (file === `${NEW_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: MERGED_SHA });
        throw new Error(`unexpected readFile ${file}`);
      },
      readlink: async (file) => {
        if (file === `${LOOPS_ROOT}/current`) return readlinkTarget;
        throw new Error(`unexpected readlink ${file}`);
      },
      appendLedger: async () => {},
      sleep: async () => {},
      now: () => 0,
    },
  };
}

test('success path: cut, canary apply, healthy readback, no rollback', async () => {
  const { deps, calls } = baseDeps();
  let readlinkTarget = PREVIOUS_RELEASE;
  deps.readlink = async (file) => {
    if (file !== `${LOOPS_ROOT}/current`) throw new Error('unexpected readlink');
    return readlinkTarget;
  };
  deps.runCommand = async (request) => {
    calls.push(request);
    if (request.executable === 'bash') {
      readlinkTarget = NEW_RELEASE;
      return { code: 0, stdout: '', stderr: '' };
    }
    if (request.args[0] === 'apply') {
      return { code: 0, stdout: JSON.stringify([{ loop_id: OWNER, label: LABEL, ok: true }]), stderr: '' };
    }
    if (request.args[0] === 'status') {
      return {
        code: 0,
        stdout: JSON.stringify([{ event_release_sha: MERGED_SHA, last_terminal_result: 'pass' }]),
        stderr: '',
      };
    }
    throw new Error(`unexpected command ${JSON.stringify(request.args)}`);
  };

  const result = await promoteLoopRuntimeRepair({
    ownerId: OWNER, mergedSha: MERGED_SHA, repoRoot: REPO_ROOT, loopsRoot: LOOPS_ROOT, deps,
  });

  assert.equal(result.ok, true);
  assert.equal(result.owner_id, OWNER);
  assert.equal(result.merged_sha, MERGED_SHA);
  assert.equal(result.release_path, NEW_RELEASE);
  assert.equal(result.previous_release_path, PREVIOUS_RELEASE);
  assert.equal(result.rolled_back, false);
  const byHook = Object.fromEntries(result.hooks.map((h) => [h.hook, h]));
  assert.equal(byHook.immutable_release.ok, true);
  assert.equal(byHook.isolated_canary.ok, true);
  assert.equal(byHook.exact_health.ok, true);
  assert.equal(byHook.rollback.ok, true);
  assert.equal(byHook.rollback.detail.executed, false);
  assert.equal(calls.filter((c) => c.args?.[0] === 'apply').length, 1);
});

test('canary apply failure triggers rollback to the previous release', async () => {
  const { deps, calls } = baseDeps();
  let readlinkTarget = PREVIOUS_RELEASE;
  deps.readlink = async () => readlinkTarget;
  deps.runCommand = async (request) => {
    calls.push(request);
    if (request.executable === 'bash') {
      readlinkTarget = NEW_RELEASE;
      return { code: 0, stdout: '', stderr: '' };
    }
    if (request.args[0] === 'apply' && request.env.LIFE_MANAGER_RELEASE_ROOT === NEW_RELEASE) {
      return { code: 1, stdout: JSON.stringify([{ loop_id: OWNER, label: LABEL, ok: false }]), stderr: '' };
    }
    if (request.args[0] === 'apply' && request.env.LIFE_MANAGER_RELEASE_ROOT === PREVIOUS_RELEASE) {
      return { code: 0, stdout: JSON.stringify([{ loop_id: OWNER, label: LABEL, ok: true }]), stderr: '' };
    }
    throw new Error(`unexpected command ${JSON.stringify(request.args)}`);
  };

  const result = await promoteLoopRuntimeRepair({
    ownerId: OWNER, mergedSha: MERGED_SHA, repoRoot: REPO_ROOT, loopsRoot: LOOPS_ROOT, deps,
  });

  assert.equal(result.ok, false);
  assert.equal(result.rolled_back, true);
  const byHook = Object.fromEntries(result.hooks.map((h) => [h.hook, h]));
  assert.equal(byHook.isolated_canary.ok, false);
  assert.equal(byHook.exact_health.ok, false);
  assert.equal(byHook.exact_health.detail.reason, 'canary_failed');
  assert.equal(byHook.rollback.ok, true);
  assert.equal(byHook.rollback.detail.executed, true);
  const rollbackCalls = calls.filter((c) => c.env?.LIFE_MANAGER_RELEASE_ROOT === PREVIOUS_RELEASE);
  assert.equal(rollbackCalls.length, 1);
});

test('health failure (terminal fail) triggers rollback', async () => {
  const { deps, calls } = baseDeps();
  let readlinkTarget = PREVIOUS_RELEASE;
  deps.readlink = async () => readlinkTarget;
  deps.runCommand = async (request) => {
    calls.push(request);
    if (request.executable === 'bash') {
      readlinkTarget = NEW_RELEASE;
      return { code: 0, stdout: '', stderr: '' };
    }
    if (request.args[0] === 'apply' && request.env.LIFE_MANAGER_RELEASE_ROOT === NEW_RELEASE) {
      return { code: 0, stdout: JSON.stringify([{ loop_id: OWNER, label: LABEL, ok: true }]), stderr: '' };
    }
    if (request.args[0] === 'status') {
      return {
        code: 0,
        stdout: JSON.stringify([{ event_release_sha: MERGED_SHA, last_terminal_result: 'fail' }]),
        stderr: '',
      };
    }
    if (request.args[0] === 'apply' && request.env.LIFE_MANAGER_RELEASE_ROOT === PREVIOUS_RELEASE) {
      return { code: 0, stdout: JSON.stringify([{ loop_id: OWNER, label: LABEL, ok: true }]), stderr: '' };
    }
    throw new Error(`unexpected command ${JSON.stringify(request.args)}`);
  };

  const result = await promoteLoopRuntimeRepair({
    ownerId: OWNER, mergedSha: MERGED_SHA, repoRoot: REPO_ROOT, loopsRoot: LOOPS_ROOT, deps,
  });

  assert.equal(result.ok, false);
  assert.equal(result.rolled_back, true);
  const byHook = Object.fromEntries(result.hooks.map((h) => [h.hook, h]));
  assert.equal(byHook.isolated_canary.ok, true);
  assert.equal(byHook.exact_health.ok, false);
  assert.equal(byHook.exact_health.detail.row.last_terminal_result, 'fail');
  assert.equal(byHook.rollback.detail.executed, true);
});

test('health timeout with no terminal result triggers rollback', async () => {
  const { deps } = baseDeps();
  let readlinkTarget = PREVIOUS_RELEASE;
  deps.readlink = async () => readlinkTarget;
  let ticks = 0;
  deps.now = () => {
    ticks += 1;
    // First call establishes the deadline; subsequent calls report past it immediately so the
    // poll loop exits on its first health read without a real 45-minute wait.
    return ticks <= 1 ? 0 : 10_000;
  };
  deps.healthDeadlineMs = 1;
  let statusCalls = 0;
  deps.runCommand = async (request) => {
    if (request.executable === 'bash') {
      readlinkTarget = NEW_RELEASE;
      return { code: 0, stdout: '', stderr: '' };
    }
    if (request.args[0] === 'apply' && request.env.LIFE_MANAGER_RELEASE_ROOT === NEW_RELEASE) {
      return { code: 0, stdout: JSON.stringify([{ loop_id: OWNER, label: LABEL, ok: true }]), stderr: '' };
    }
    if (request.args[0] === 'status') {
      statusCalls += 1;
      return {
        code: 0,
        stdout: JSON.stringify([{ event_release_sha: MERGED_SHA, last_terminal_result: null }]),
        stderr: '',
      };
    }
    if (request.args[0] === 'apply' && request.env.LIFE_MANAGER_RELEASE_ROOT === PREVIOUS_RELEASE) {
      return { code: 0, stdout: JSON.stringify([{ loop_id: OWNER, label: LABEL, ok: true }]), stderr: '' };
    }
    throw new Error(`unexpected command ${JSON.stringify(request.args)}`);
  };

  const result = await promoteLoopRuntimeRepair({
    ownerId: OWNER, mergedSha: MERGED_SHA, repoRoot: REPO_ROOT, loopsRoot: LOOPS_ROOT, deps,
  });

  assert.equal(result.ok, false);
  assert.equal(result.rolled_back, true);
  assert.equal(statusCalls, 1);
  const byHook = Object.fromEntries(result.hooks.map((h) => [h.hook, h]));
  assert.equal(byHook.exact_health.ok, false);
  assert.equal(byHook.exact_health.detail.reason, 'timeout');
});

test('non-deterministic owner is refused with no dependency calls', async () => {
  const registry = JSON.stringify({
    loops: { [OWNER]: {
      label: LABEL, effect_class: 'money', provider_route: 'shared-agent-runner',
      cadence: { start_interval_seconds: 30 }, entrypoint: 'bin/paid-owner',
    } },
  });
  const { deps, calls } = baseDeps({ registry });
  deps.runCommand = async (request) => {
    calls.push(request);
    throw new Error('runCommand must not be called for a refused owner');
  };
  deps.appendLedger = async () => {
    throw new Error('appendLedger must not be called for a refused owner');
  };

  const result = await promoteLoopRuntimeRepair({
    ownerId: OWNER, mergedSha: MERGED_SHA, repoRoot: REPO_ROOT, loopsRoot: LOOPS_ROOT, deps,
  });

  assert.equal(result.ok, false);
  assert.equal(result.reason, 'promotion_class_not_bound');
  assert.deepEqual(result.hooks, []);
  assert.equal(calls.length, 0);
});

test('RELEASE.json sha mismatch fails the immutable_release hook and refuses further hooks', async () => {
  const { deps, calls } = baseDeps();
  let readlinkTarget = PREVIOUS_RELEASE;
  deps.readlink = async () => readlinkTarget;
  deps.readFile = async (file) => {
    if (file === `${REPO_ROOT}/config/loop-registry.json`) return deterministicRegistry();
    if (file === `${NEW_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: 'b'.repeat(40) });
    throw new Error(`unexpected readFile ${file}`);
  };
  deps.runCommand = async (request) => {
    calls.push(request);
    if (request.executable === 'bash') {
      readlinkTarget = NEW_RELEASE;
      return { code: 0, stdout: '', stderr: '' };
    }
    throw new Error(`unexpected command ${JSON.stringify(request.args)}`);
  };

  const result = await promoteLoopRuntimeRepair({
    ownerId: OWNER, mergedSha: MERGED_SHA, repoRoot: REPO_ROOT, loopsRoot: LOOPS_ROOT, deps,
  });

  assert.equal(result.ok, false);
  assert.equal(result.rolled_back, false);
  assert.equal(result.hooks.length, 1);
  assert.equal(result.hooks[0].hook, 'immutable_release');
  assert.equal(result.hooks[0].ok, false);
  assert.equal(calls.length, 1);
});
