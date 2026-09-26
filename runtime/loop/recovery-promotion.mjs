import { execFile } from 'node:child_process';
import { mkdir, readFile as readFileFs, readlink as readlinkFs } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';

import { classifyRecoveryJob } from './recovery-class.cjs';

const execFileAsync = promisify(execFile);
const SHA256 = /^[a-f0-9]{40}$/u;
const TERMINAL_RESULTS = new Set(['pass', 'fail', 'blocked']);

async function runCommandDefault({ executable, args, env }) {
  try {
    const output = await execFileAsync(executable, args, {
      env, encoding: 'utf8', timeout: 120_000, maxBuffer: 2 * 1024 * 1024,
    });
    return { code: 0, stdout: output.stdout || '', stderr: output.stderr || '' };
  } catch (error) {
    return {
      code: Number.isInteger(error?.code) ? error.code : 1,
      stdout: error?.stdout || '',
      stderr: error?.stderr || String(error?.message || error),
    };
  }
}

function hook(name, ok, detail) {
  return { hook: name, ok, detail: detail ?? {} };
}

function tail(text, limit = 4000) {
  const value = String(text || '');
  return value.length > limit ? value.slice(-limit) : value;
}

async function resolveCurrentTarget(loopsRoot, readlinkFn) {
  try {
    const target = await readlinkFn(path.join(loopsRoot, 'current'));
    return path.isAbsolute(target) ? target : path.resolve(loopsRoot, target);
  } catch {
    return null;
  }
}

async function readManifestSha(releasePath, readFileFn) {
  try {
    const manifest = JSON.parse(await readFileFn(path.join(releasePath, 'RELEASE.json')));
    return manifest?.sha ?? null;
  } catch {
    return null;
  }
}

/**
 * Promote a merged recovery PR's commit into a real, isolated loop-runtime deployment for one
 * `deterministic`/`effect_class: none` owner: cut an immutable release, apply only that owner as a
 * canary, poll its next natural terminal result under the new release, and roll back to the
 * previously current release if the canary or its health readback fails. Every side effect is
 * injected through `deps` so tests never touch a real release, a real `lm-loop`, or production.
 */
export async function promoteLoopRuntimeRepair({
  ownerId,
  mergedSha,
  repoRoot,
  loopsRoot = path.join(os.homedir(), 'loops'),
  deps = {},
} = {}) {
  const runCommand = deps.runCommand || runCommandDefault;
  const readFileFn = deps.readFile || ((file) => readFileFs(file, 'utf8'));
  const readlinkFn = deps.readlink || ((file) => readlinkFs(file));
  const sleep = deps.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const now = deps.now || (() => Date.now());
  const appendLedger = deps.appendLedger || defaultAppendLedger;
  const registryPath = deps.registryPath || path.join(repoRoot, 'config/loop-registry.json');
  const ledgerPath = deps.ledgerPath
    || path.join(os.homedir(), '.local/state/life-manager/recovery/promotions.jsonl');
  const healthDeadlineMs = deps.healthDeadlineMs ?? 45 * 60 * 1000;
  const healthIntervalMs = deps.healthIntervalMs ?? 10_000;

  const base = { owner_id: ownerId, merged_sha: mergedSha };

  if (!SHA256.test(String(mergedSha || ''))) {
    return { ...base, ok: false, reason: 'merged_sha_invalid', release_path: null,
      previous_release_path: null, hooks: [], rolled_back: false };
  }

  let registry;
  try {
    registry = JSON.parse(await readFileFn(registryPath));
  } catch {
    return { ...base, ok: false, reason: 'registry_unreadable', release_path: null,
      previous_release_path: null, hooks: [], rolled_back: false };
  }
  const entry = registry?.loops?.[ownerId];
  let recoveryClass = null;
  try {
    recoveryClass = entry ? classifyRecoveryJob(entry) : null;
  } catch {
    recoveryClass = null;
  }
  // Only a registry-verified `deterministic`/`effect_class: none` owner is bound to this runtime
  // path. This is the boundary that stops a recovery PR's own class marker from being trusted: the
  // merge guard may believe the PR is deterministic, but only the registry decides eligibility here.
  if (!entry || recoveryClass !== 'deterministic' || entry.effect_class !== 'none') {
    return { ...base, ok: false, reason: 'promotion_class_not_bound', release_path: null,
      previous_release_path: null, hooks: [], rolled_back: false };
  }

  const previousReleasePath = await resolveCurrentTarget(loopsRoot, readlinkFn);
  const hooks = [];

  let releasePath = null;
  let immutableOk = false;
  try {
    const cut = await runCommand({
      executable: 'bash',
      args: [path.join(repoRoot, 'bin/cut-loop-release.sh'), mergedSha],
      env: { ...process.env, LOOPS_ROOT: loopsRoot },
    });
    if (cut?.code === 0) {
      releasePath = await resolveCurrentTarget(loopsRoot, readlinkFn);
      const releaseSha = releasePath ? await readManifestSha(releasePath, readFileFn) : null;
      immutableOk = releaseSha === mergedSha;
      hooks.push(hook('immutable_release', immutableOk, {
        release_path: releasePath, release_sha: releaseSha, exit_code: cut.code,
      }));
    } else {
      hooks.push(hook('immutable_release', false, {
        exit_code: cut?.code ?? null, stderr: tail(cut?.stderr),
      }));
    }
  } catch (error) {
    hooks.push(hook('immutable_release', false, { error: String(error?.message || error) }));
  }

  if (!immutableOk) {
    return finalize({
      ...base, ok: false, release_path: releasePath, previous_release_path: previousReleasePath,
      hooks, rolled_back: false,
    }, ledgerPath, appendLedger, deps);
  }

  const loopExecutable = path.join(releasePath, 'bin/lm-loop');
  let canaryOk = false;
  try {
    const applied = await runCommand({
      executable: loopExecutable,
      args: ['apply'],
      env: { ...process.env, LIFE_MANAGER_APPLY_TARGET: ownerId, LIFE_MANAGER_RELEASE_ROOT: releasePath },
    });
    let parsed = null;
    try { parsed = JSON.parse(String(applied?.stdout || '')); } catch { parsed = null; }
    const item = Array.isArray(parsed)
      ? parsed.find((row) => row && (row.loop_id === ownerId || row.label === entry.label))
      : null;
    canaryOk = applied?.code === 0 && Boolean(item) && item.ok === true && item.skipped == null;
    hooks.push(hook('isolated_canary', canaryOk, { exit_code: applied?.code ?? null, item }));
  } catch (error) {
    hooks.push(hook('isolated_canary', false, { error: String(error?.message || error) }));
  }

  let healthOk = false;
  if (canaryOk) {
    const deadline = now() + healthDeadlineMs;
    let lastRow = null;
    for (;;) {
      let statusResult;
      try {
        statusResult = await runCommand({
          executable: loopExecutable,
          args: ['status', ownerId],
          env: { ...process.env, LIFE_MANAGER_RELEASE_ROOT: releasePath },
        });
      } catch (error) {
        statusResult = { code: 1, stdout: '', stderr: String(error?.message || error) };
      }
      let rows = null;
      try { rows = JSON.parse(String(statusResult?.stdout || '')); } catch { rows = null; }
      const row = Array.isArray(rows) ? rows[0] : null;
      if (row) lastRow = row;
      if (row?.event_release_sha === mergedSha && TERMINAL_RESULTS.has(row.last_terminal_result)) {
        healthOk = row.last_terminal_result === 'pass';
        hooks.push(hook('exact_health', healthOk, { row: lastRow }));
        break;
      }
      if (now() >= deadline) {
        hooks.push(hook('exact_health', false, { reason: 'timeout', row: lastRow }));
        break;
      }
      await sleep(healthIntervalMs);
    }
  } else {
    hooks.push(hook('exact_health', false, { reason: 'canary_failed' }));
  }

  let rolledBack = false;
  const needsRollback = !canaryOk || !healthOk;
  if (needsRollback) {
    const available = previousReleasePath != null;
    let executed = false;
    let result = null;
    if (available) {
      try {
        result = await runCommand({
          executable: path.join(previousReleasePath, 'bin/lm-loop'),
          args: ['apply'],
          env: {
            ...process.env,
            LIFE_MANAGER_APPLY_TARGET: ownerId,
            LIFE_MANAGER_RELEASE_ROOT: previousReleasePath,
          },
        });
        executed = true;
        rolledBack = result?.code === 0;
      } catch (error) {
        result = { code: 1, error: String(error?.message || error) };
      }
    }
    hooks.push(hook('rollback', available, {
      executed, result, previous_release_path: previousReleasePath,
    }));
  } else {
    hooks.push(hook('rollback', previousReleasePath != null, {
      executed: false, reason: 'not_needed', previous_release_path: previousReleasePath,
    }));
  }

  const ok = immutableOk && canaryOk && healthOk;
  return finalize({
    ...base, ok, release_path: releasePath, previous_release_path: previousReleasePath,
    hooks, rolled_back: rolledBack,
  }, ledgerPath, appendLedger, deps);
}

async function defaultAppendLedger(ledgerPath, line) {
  await mkdir(path.dirname(ledgerPath), { recursive: true, mode: 0o700 });
  const fs = await import('node:fs/promises');
  await fs.appendFile(ledgerPath, line, { mode: 0o600 });
}

async function finalize(result, ledgerPath, appendLedger) {
  const line = `${JSON.stringify({ ...result, ts: new Date().toISOString() })}\n`;
  try {
    await appendLedger(ledgerPath, line);
  } catch {
    // A ledger write failure must not hide the promotion result from its caller; the guard's own
    // ledger row still records the outcome.
  }
  return result;
}
