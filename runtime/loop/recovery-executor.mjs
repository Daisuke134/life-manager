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
    occurrence_id: plan.occurrence_id,
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

const READBACK_FIELDS = [
  'event_id', 'loop_id', 'job_id', 'owner_id', 'occurrence_id', 'launchd_state',
  'installed_release_sha', 'event_release_sha', 'last_terminal_result',
  'diagnostic_complete', 'diagnostic_error', 'effect_status', 'blocker',
  'failure_layer', 'error_class', 'retryable', 'next_action', 'evidence_refs',
];

function sanitizedReadback(row) {
  if (!row || typeof row !== 'object' || Array.isArray(row)) return null;
  return Object.fromEntries(READBACK_FIELDS
    .filter((field) => Object.hasOwn(row, field))
    .map((field) => [field, row[field]]));
}

function readbackHealthy(row, plan, entry) {
  if (!row || typeof row !== 'object' || Array.isArray(row)) return false;
  const safeEffect = entry.effect_class === 'none'
    ? row.effect_status === 'not_applicable'
    : ['verified', 'reconciled'].includes(row.effect_status);
  return row.classification === 'managed'
    && row.loop_id === plan.loop_id
    && row.job_id === plan.loop_id
    && row.owner_id === plan.owner_id
    && row.installed_release_sha === plan.release_sha
    && row.event_release_sha === plan.release_sha
    && row.last_terminal_result === 'pass'
    && row.diagnostic_complete === true
    && row.blocker == null
    && ['loaded-idle', 'loaded-running'].includes(row.launchd_state)
    && safeEffect;
}

async function statusSnapshot({ executable, plan, entry, releaseRoot, readStatus }) {
  const request = {
    executable,
    args: ['status', plan.loop_id],
    env: {
      ...process.env,
      LIFE_MANAGER_LOOP_ID: RECOVERY_EXECUTOR_LOOP_ID,
      LIFE_MANAGER_RELEASE_ROOT: releaseRoot,
    },
  };
  let result;
  try {
    result = await readStatus(request);
  } catch {
    return { healthy: false, readback: null, reason: 'status_exception' };
  }
  let rows;
  try {
    rows = JSON.parse(String(result?.stdout || ''));
  } catch {
    return { healthy: false, readback: null, reason: 'status_result_invalid' };
  }
  if (result?.code !== 0 || !Array.isArray(rows) || rows.length !== 1) {
    return { healthy: false, readback: null, reason: 'status_result_invalid' };
  }
  return {
    healthy: readbackHealthy(rows[0], plan, entry),
    readback: sanitizedReadback(rows[0]),
    reason: null,
  };
}

function readbackEvidence(readback) {
  return Array.isArray(readback?.evidence_refs)
    ? readback.evidence_refs.filter((value) => typeof value === 'string').slice(0, 32)
    : [];
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
  readStatus = runLmLoop,
} = {}) {
  if (!plan || typeof plan !== 'object' || Array.isArray(plan)) {
    throw new Error('recovery plan invalid');
  }
  if (!registry || typeof registry !== 'object') throw new Error('loop registry invalid');

  if (plan.execute !== true) {
    const state = plan.action === 'hold_effect_unknown' ? 'held'
      : plan.action.startsWith('escalate_') ? 'escalated' : 'skipped';
    return resultBase(plan, state, true, {
      executed: false,
      budget_consumed: false,
      next_action: plan.action === 'hold_effect_unknown' ? 'official_readback_required'
        : state === 'escalated' ? 'guarded_code_repair' : 'none',
    });
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


  const before = await statusSnapshot({
    executable, plan, entry: command.entry, releaseRoot, readStatus,
  });
  if (before.healthy) {
    return resultBase(plan, 'repaired', true, {
      executed: false,
      budget_consumed: false,
      before_readback: before.readback,
      after_readback: before.readback,
      evidence_refs: readbackEvidence(before.readback),
      next_action: 'none',
    });
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
    const after = await statusSnapshot({
      executable, plan, entry: command.entry, releaseRoot, readStatus,
    });
    if (after.healthy) {
      return resultBase(plan, 'repaired', true, {
        executed: true,
        budget_consumed: true,
        before_readback: before.readback,
        after_readback: after.readback,
        command_exit_code: null,
        evidence_refs: readbackEvidence(after.readback),
        next_action: 'none',
      });
    }
    return resultBase(plan, 'queued', false, {
      reason: 'reconcile_exception',
      budget_consumed: true,
      before_readback: before.readback,
      after_readback: after.readback,
      command_exit_code: null,
      evidence_refs: readbackEvidence(after.readback),
      next_action: 'retry_after_cooldown',
    });
  }

  const after = await statusSnapshot({
    executable, plan, entry: command.entry, releaseRoot, readStatus,
  });
  const evidence = readbackEvidence(after.readback);

  let parsed;
  try {
    parsed = JSON.parse(String(commandResult?.stdout || ''));
  } catch {
    if (after.healthy) {
      return resultBase(plan, 'repaired', true, {
        executed: true,
        budget_consumed: true,
        before_readback: before.readback,
        after_readback: after.readback,
        command_exit_code: Number.isInteger(commandResult?.code) ? commandResult.code : null,
        evidence_refs: evidence,
        next_action: 'none',
      });
    }
    return resultBase(plan, 'blocked', false, {
      reason: 'reconcile_result_invalid',
      budget_consumed: true,
      before_readback: before.readback,
      after_readback: after.readback,
      command_exit_code: Number.isInteger(commandResult?.code) ? commandResult.code : null,
      evidence_refs: evidence,
      next_action: 'escalate_owner',
      command: { executable, args: command.args },
    });
  }
  const succeeded = commandResult?.code === 0
    && parsed?.ok === true
    && parsed?.release_sha === plan.release_sha
    && parsed?.route === command.entry.provider_route
    && Number.isSafeInteger(parsed?.eligible)
    && parsed.eligible >= 0
    && parsed.eligible <= 1
    && Array.isArray(parsed?.failed)
    && parsed.failed.length === 0;
  if (!succeeded) {
    if (after.healthy) {
      return resultBase(plan, 'repaired', true, {
        executed: true,
        budget_consumed: true,
        before_readback: before.readback,
        after_readback: after.readback,
        command_exit_code: Number.isInteger(commandResult?.code) ? commandResult.code : null,
        evidence_refs: evidence,
        next_action: 'none',
        command: { executable, args: command.args },
        reconcile: parsed,
      });
    }
    return resultBase(plan, 'queued', false, {
      reason: 'reconcile_failed',
      budget_consumed: true,
      before_readback: before.readback,
      after_readback: after.readback,
      command_exit_code: Number.isInteger(commandResult?.code) ? commandResult.code : null,
      evidence_refs: evidence,
      next_action: 'retry_after_cooldown',
      command: { executable, args: command.args },
      reconcile: parsed,
    });
  }
  const skippedPending = Array.isArray(parsed?.skipped_pending)
    && parsed.skipped_pending.includes(plan.loop_id);
  if (skippedPending && !after.healthy) {
    return resultBase(plan, 'queued', false, {
      reason: 'admission_pending',
      executed: false,
      budget_consumed: false,
      before_readback: before.readback,
      after_readback: after.readback,
      command_exit_code: commandResult.code,
      evidence_refs: evidence,
      next_action: 'retry_after_eligibility',
      command: { executable, args: command.args },
      reconcile: parsed,
    });
  }
  const applied = appliedTarget(parsed, plan.loop_id, command.entry.label);
  if (parsed.eligible === 1 && !applied) {
    if (after.healthy) {
      return resultBase(plan, 'repaired', true, {
        executed: false,
        budget_consumed: false,
        before_readback: before.readback,
        after_readback: after.readback,
        command_exit_code: commandResult.code,
        evidence_refs: evidence,
        next_action: 'none',
        command: { executable, args: command.args },
        reconcile: parsed,
      });
    }
    return resultBase(plan, 'blocked', false, {
      reason: 'reconcile_target_not_applied',
      budget_consumed: true,
      before_readback: before.readback,
      after_readback: after.readback,
      command_exit_code: commandResult.code,
      evidence_refs: evidence,
      next_action: 'escalate_owner',
      command: { executable, args: command.args },
      reconcile: parsed,
    });
  }

  if (!after.healthy) {
    return resultBase(plan, 'queued', false, {
      reason: 'healthy_readback_pending',
      executed: applied,
      budget_consumed: applied,
      before_readback: before.readback,
      after_readback: after.readback,
      command_exit_code: commandResult.code,
      evidence_refs: evidence,
      next_action: 'await_healthy_terminal',
      command: { executable, args: command.args },
      reconcile: parsed,
    });
  }
  return resultBase(plan, 'repaired', true, {
    executed: applied,
    budget_consumed: applied,
    before_readback: before.readback,
    after_readback: after.readback,
    command_exit_code: commandResult.code,
    evidence_refs: evidence,
    next_action: 'none',
    command: { executable, args: command.args },
    reconcile: parsed,
  });
}
