import test from 'node:test';
import assert from 'node:assert/strict';

import { promoteLoopRuntimeRepair } from '../recovery-promotion.mjs';

const MERGED_SHA = 'a'.repeat(40);
const OWNER = 'test-deterministic-owner';
const LABEL = 'ai.anicca.test-deterministic-owner';
const REPO_ROOT = '/repo';
const LOOPS_ROOT = '/loops';
const NEW_RELEASE = '/loops/releases/20260926T000000-new-sha';
const PREVIOUS_RELEASE = '/loops/releases/20260901T000000-previous-sha';

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

// The candidate is cut with LOOPS_ACTIVATE_CURRENT=0 (see recovery-promotion.mjs), so it is never
// found by reading `current` -- it has to be located by scanning `<loopsRoot>/releases/*` for the
// manifest whose sha matches. `current` itself never advances during a successful run: it still
// points at PREVIOUS_RELEASE throughout every test below, exactly as it would with a live promotion
// hold in front of the release-reconciler.
function baseDeps({ registry = deterministicRegistry(), releaseDirs = [PREVIOUS_RELEASE] } = {}) {
  const calls = [];
  const releaseNames = () => releaseDirs.map((full) => full.split('/').pop());
  return {
    calls,
    releaseDirs,
    deps: {
      registryPath: `${REPO_ROOT}/config/loop-registry.json`,
      ledgerPath: '/state/promotions.jsonl',
      readFile: async (file) => {
        if (file === `${REPO_ROOT}/config/loop-registry.json`) return registry;
        if (file === `${PREVIOUS_RELEASE}/RELEASE.json`) {
          return JSON.stringify({ sha: 'c'.repeat(40) });
        }
        throw new Error(`unexpected readFile ${file}`);
      },
      readlink: async (file) => {
        if (file === `${LOOPS_ROOT}/current`) return PREVIOUS_RELEASE;
        throw new Error(`unexpected readlink ${file}`);
      },
      readdir: async (dir) => {
        if (dir === `${LOOPS_ROOT}/releases`) return releaseNames();
        throw new Error(`unexpected readdir ${dir}`);
      },
      appendLedger: async () => {},
      sleep: async () => {},
      now: () => 0,
      cutRetryDelayMs: 0,
    },
  };
}

test('success path: candidate cut with LOOPS_ACTIVATE_CURRENT=0, canary apply, healthy readback, no rollback', async () => {
  const { deps, calls } = baseDeps();
  deps.readFile = async (file) => {
    if (file === `${REPO_ROOT}/config/loop-registry.json`) return deterministicRegistry();
    if (file === `${PREVIOUS_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: 'c'.repeat(40) });
    if (file === `${NEW_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: MERGED_SHA });
    throw new Error(`unexpected readFile ${file}`);
  };
  deps.readdir = async (dir) => {
    if (dir === `${LOOPS_ROOT}/releases`) {
      return [PREVIOUS_RELEASE, NEW_RELEASE].map((full) => full.split('/').pop());
    }
    throw new Error(`unexpected readdir ${dir}`);
  };
  deps.runCommand = async (request) => {
    calls.push(request);
    if (request.executable === 'bash') return { code: 0, stdout: '', stderr: '' };
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

  const cutCall = calls.find((c) => c.executable === 'bash');
  assert.equal(cutCall.env.LOOPS_ACTIVATE_CURRENT, '0');
  assert.deepEqual(cutCall.args, [`${REPO_ROOT}/bin/cut-loop-release.sh`, MERGED_SHA]);
});

test('canary apply failure triggers rollback to the previous release', async () => {
  const { deps, calls } = baseDeps();
  deps.readFile = async (file) => {
    if (file === `${REPO_ROOT}/config/loop-registry.json`) return deterministicRegistry();
    if (file === `${PREVIOUS_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: 'c'.repeat(40) });
    if (file === `${NEW_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: MERGED_SHA });
    throw new Error(`unexpected readFile ${file}`);
  };
  deps.readdir = async () => [PREVIOUS_RELEASE, NEW_RELEASE].map((full) => full.split('/').pop());
  deps.runCommand = async (request) => {
    calls.push(request);
    if (request.executable === 'bash') return { code: 0, stdout: '', stderr: '' };
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
  const { deps } = baseDeps();
  deps.readFile = async (file) => {
    if (file === `${REPO_ROOT}/config/loop-registry.json`) return deterministicRegistry();
    if (file === `${PREVIOUS_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: 'c'.repeat(40) });
    if (file === `${NEW_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: MERGED_SHA });
    throw new Error(`unexpected readFile ${file}`);
  };
  deps.readdir = async () => [PREVIOUS_RELEASE, NEW_RELEASE].map((full) => full.split('/').pop());
  deps.runCommand = async (request) => {
    if (request.executable === 'bash') return { code: 0, stdout: '', stderr: '' };
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
  deps.readFile = async (file) => {
    if (file === `${REPO_ROOT}/config/loop-registry.json`) return deterministicRegistry();
    if (file === `${PREVIOUS_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: 'c'.repeat(40) });
    if (file === `${NEW_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: MERGED_SHA });
    throw new Error(`unexpected readFile ${file}`);
  };
  deps.readdir = async () => [PREVIOUS_RELEASE, NEW_RELEASE].map((full) => full.split('/').pop());
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
    if (request.executable === 'bash') return { code: 0, stdout: '', stderr: '' };
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

test('RELEASE.json sha mismatch: cut succeeds but no release directory matches, immutable_release fails', async () => {
  const { deps, calls } = baseDeps();
  deps.readFile = async (file) => {
    if (file === `${REPO_ROOT}/config/loop-registry.json`) return deterministicRegistry();
    if (file === `${PREVIOUS_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: 'c'.repeat(40) });
    throw new Error(`unexpected readFile ${file}`);
  };
  // No release directory carries mergedSha's manifest -- the same real-world shape as a cut that
  // succeeded but wrote a different sha (a stale symlink resolution, a race with another build).
  deps.readdir = async () => [PREVIOUS_RELEASE].map((full) => full.split('/').pop());
  deps.runCommand = async (request) => {
    calls.push(request);
    if (request.executable === 'bash') return { code: 0, stdout: '', stderr: '' };
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

test('cut fails because another release build owns the lock: retries with backoff, then promotion_never_started with no apply/status calls', async () => {
  const { deps, calls } = baseDeps();
  const sleeps = [];
  deps.sleep = async (ms) => { sleeps.push(ms); };
  deps.cutRetryDelayMs = 5000;
  deps.runCommand = async (request) => {
    calls.push(request);
    if (request.executable === 'bash') {
      return { code: 1, stdout: '', stderr: 'cut-loop-release: another release build owns /loops/.release-cut.lock' };
    }
    throw new Error(`unexpected command ${JSON.stringify(request.args)}`);
  };

  const result = await promoteLoopRuntimeRepair({
    ownerId: OWNER, mergedSha: MERGED_SHA, repoRoot: REPO_ROOT, loopsRoot: LOOPS_ROOT, deps,
  });

  assert.equal(result.ok, false);
  assert.equal(result.reason, 'promotion_never_started');
  assert.equal(result.rolled_back, false);
  assert.equal(result.release_path, null);
  assert.equal(result.hooks.length, 1);
  assert.equal(result.hooks[0].hook, 'immutable_release');
  assert.equal(result.hooks[0].ok, false);
  // Exactly 3 cut attempts (the default), no apply and no status -- nothing was ever cut or applied.
  assert.equal(calls.filter((c) => c.executable === 'bash').length, 3);
  assert.equal(calls.filter((c) => c.args?.[0] === 'apply').length, 0);
  assert.equal(calls.filter((c) => c.args?.[0] === 'status').length, 0);
  assert.deepEqual(sleeps, [5000, 5000]);
});

test('cut succeeds on a later retry after the lock frees up', async () => {
  const { deps, calls } = baseDeps();
  deps.readFile = async (file) => {
    if (file === `${REPO_ROOT}/config/loop-registry.json`) return deterministicRegistry();
    if (file === `${PREVIOUS_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: 'c'.repeat(40) });
    if (file === `${NEW_RELEASE}/RELEASE.json`) return JSON.stringify({ sha: MERGED_SHA });
    throw new Error(`unexpected readFile ${file}`);
  };
  deps.readdir = async () => [PREVIOUS_RELEASE, NEW_RELEASE].map((full) => full.split('/').pop());
  deps.cutRetryDelayMs = 0;
  let cutAttempts = 0;
  deps.runCommand = async (request) => {
    calls.push(request);
    if (request.executable === 'bash') {
      cutAttempts += 1;
      if (cutAttempts < 2) {
        return { code: 1, stdout: '', stderr: 'cut-loop-release: another release build owns /loops/.release-cut.lock' };
      }
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
  assert.equal(cutAttempts, 2);
});
