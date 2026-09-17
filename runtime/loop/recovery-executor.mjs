import { execFile } from 'node:child_process';
import { access, constants, readFile } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const SHA256 = /^[0-9a-f]{40}$/u;
const RECOVERY_EXECUTOR_LOOP_ID = 'life-manager-recovery-executor';

function resultBase(plan, state, ok, extra = {}) {
  return {
    schema_version: 1,
    intent_id: plan.intent_id,
    loop_id: plan.loop_id,
    owner_id: plan.owner_id,
    release_sha: plan.release_sha,
    action: plan.action,
    state,
    ok,
    ...extra,
  };
}

function expectedCommand(plan, registry) {
  const entry = registry?.loops?.[plan.loop_id];
  if (!entry || typeof entry !== 'object' || typeof entry.provider_route !== 'string'
      || typeof entry.label !== 'string') return null;
  const command = plan.commands?.length === 1 ? plan.commands[0] : null;
  const args = [
    'reconcile', entry.provider_route, '--loaded-idle-only', '--max-owners', '1',
    '--loop-id', plan.loop_id,
  ];
  if (!command || command.program !== 'lm-loop'
      || JSON.stringify(command.args) !== JSON.stringify(args)) return null;
  return { entry, args };
}

async function runLmLoop({ executable, args, env }) {
  try {
    const output = await execFileAsync(executable, args, {
      env,
      encoding: 'utf8',
      timeout: 120_000,
      maxBuffer: 2 * 1024 * 1024,
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

function appliedTarget(result, loopId, label) {
  if (!Array.isArray(result?.applied)) return false;
  return result.applied.some((item) => item && (
    item.loop_id === loopId || item.label === label
  ));
}

/**
 * Execute the already-compiled, owner-scoped recovery plan through the existing
 * lm-loop reconcile command. This is the only impure boundary for self-heal.
 * It never invokes a provider, browser, credential, or sibling loop.
 */
export async function executeRecoveryPlan({
  plan,
  registry,
  releaseRoot,
  runCommand = runLmLoop,
} = {}) {
  if (!plan || typeof plan !== 'object' || Array.isArray(plan)) {
    throw new Error('recovery plan invalid');
  }
  if (!registry || typeof registry !== 'object') throw new Error('loop registry invalid');

  if (plan.execute !== true) {
    const state = plan.action === 'hold_effect_unknown' ? 'held' : 'skipped';
    return resultBase(plan, state, true, { executed: false });
  }

  if (typeof releaseRoot !== 'string' || releaseRoot.length === 0) {
    return resultBase(plan, 'blocked', false, { reason: 'release_root_missing' });
  }
  if (!SHA256.test(plan.release_sha)) {
    return resultBase(plan, 'blocked', false, { reason: 'release_sha_invalid' });
  }

  const command = expectedCommand(plan, registry);
  if (!command) {
    return resultBase(plan, 'blocked', false, { reason: 'command_contract_invalid' });
  }

  let manifest;
  try {
    manifest = JSON.parse(await readFile(path.join(releaseRoot, 'RELEASE.json'), 'utf8'));
  } catch {
    return resultBase(plan, 'blocked', false, { reason: 'release_manifest_unreadable' });
  }
  if (manifest?.sha !== plan.release_sha) {
    return resultBase(plan, 'blocked', false, { reason: 'release_sha_mismatch' });
  }

  const executable = path.join(releaseRoot, 'bin', 'lm-loop');
  try {
    await access(executable, constants.X_OK);
  } catch {
    return resultBase(plan, 'blocked', false, { reason: 'release_entrypoint_unavailable' });
  }

  let commandResult;
  try {
    commandResult = await runCommand({
      executable,
      args: command.args,
      // The executor is a control-plane owner, never the target loop. This prevents
      // lm-loop's self-exclusion guard from hiding the owner being repaired when the
      // caller happens to run inside that loop's environment.
      env: {
        ...process.env,
        LIFE_MANAGER_LOOP_ID: RECOVERY_EXECUTOR_LOOP_ID,
        LIFE_MANAGER_RELEASE_ROOT: releaseRoot,
      },
    });
  } catch {
    return resultBase(plan, 'queued', false, { reason: 'reconcile_exception' });
  }

  let parsed;
  try {
    parsed = JSON.parse(String(commandResult?.stdout || ''));
  } catch {
    return resultBase(plan, 'blocked', false, {
      reason: 'reconcile_result_invalid',
      command: { executable, args: command.args },
    });
  }
  const succeeded = commandResult?.code === 0
    && parsed?.ok === true
    && parsed?.release_sha === plan.release_sha
    && parsed?.route === command.entry.provider_route
    && parsed?.eligible === 1
    && Array.isArray(parsed?.failed)
    && parsed.failed.length === 0;
  if (!succeeded) {
    return resultBase(plan, 'queued', false, {
      reason: 'reconcile_failed',
      command: { executable, args: command.args },
      reconcile: parsed,
    });
  }
  if (!appliedTarget(parsed, plan.loop_id, command.entry.label)) {
    return resultBase(plan, 'blocked', false, {
      reason: 'reconcile_target_not_applied',
      command: { executable, args: command.args },
      reconcile: parsed,
    });
  }
  return resultBase(plan, 'repaired', true, {
    executed: true,
    command: { executable, args: command.args },
    reconcile: parsed,
  });
}
