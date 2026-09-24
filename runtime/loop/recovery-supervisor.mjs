import { promises as fs } from 'node:fs';
import path from 'node:path';

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const RELEASE_SHA = /^[0-9a-f]{40}$/u;
const SAFE_REF = /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._:/-]{1,512}$/u;
const TERMINAL_STATES = new Set(['repaired', 'held', 'skipped', 'blocked', 'escalated']);
const OUTCOME_STATES = new Set(['queued', 'repaired', 'held', 'skipped', 'blocked', 'escalated']);

async function readJsonLines(file) {
  try {
    const text = await fs.readFile(file, 'utf8');
    return text.split('\n').filter(Boolean).map((line) => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean);
  } catch (error) {
    if (error?.code === 'ENOENT') return [];
    throw error;
  }
}

async function appendJsonLine(file, value) {
  await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
  const handle = await fs.open(file, 'a', 0o600);
  try {
    await handle.write(`${JSON.stringify(value)}\n`, null, 'utf8');
    await handle.sync();
  } finally {
    await handle.close();
  }
}

function validIntent(value) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && value.schema_version === 1
    && (value.record_type === undefined || value.record_type === 'recovery_intent')
    && typeof value.intent_id === 'string' && ID.test(value.intent_id)
    && typeof value.loop_id === 'string' && ID.test(value.loop_id)
    && typeof value.owner_id === 'string' && ID.test(value.owner_id)
    && typeof value.occurrence_id === 'string' && ID.test(value.occurrence_id)
    && value.occurrence_id.startsWith(`${value.loop_id}:`)
    && typeof value.release_sha === 'string' && RELEASE_SHA.test(value.release_sha)
    && typeof value.action === 'string' && ID.test(value.action)
    && value.mutates_external_effect === false;
}

function journalState(journalRows) {
  const states = new Map();
  for (const row of journalRows) {
    if (!row || typeof row.intent_id !== 'string') continue;
    const previous = states.get(row.intent_id) || {
      attempts: 0, terminal: false, nextEligibleAt: null,
    };
    const countsBudget = row.record_type === 'recovery_outcome'
      ? row.budget_consumed === true
      : row.record_type === 'recovery_supervisor' && row.state !== 'claimed';
    const attempt = countsBudget && Number.isSafeInteger(row.attempt) && row.attempt > previous.attempts
      ? row.attempt : previous.attempts;
    const nextEligibleAt = typeof row.next_eligible_at === 'string'
      && Number.isFinite(Date.parse(row.next_eligible_at))
      ? row.next_eligible_at : previous.nextEligibleAt;
    states.set(row.intent_id, {
      attempts: attempt,
      terminal: previous.terminal || TERMINAL_STATES.has(row.state),
      nextEligibleAt,
    });
  }
  return states;
}

function safeReadback(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const fields = [
    'event_id', 'loop_id', 'job_id', 'owner_id', 'occurrence_id', 'launchd_state',
    'installed_release_sha', 'event_release_sha', 'last_terminal_result',
    'diagnostic_complete', 'diagnostic_error', 'effect_status', 'blocker',
    'failure_layer', 'error_class', 'retryable', 'next_action',
  ];
  return Object.fromEntries(fields.filter((field) => Object.hasOwn(value, field))
    .map((field) => [field, value[field]]));
}

function defaultNextAction(state) {
  if (state === 'repaired' || state === 'skipped') return 'none';
  if (state === 'held') return 'official_readback_required';
  if (state === 'queued') return 'retry_after_cooldown';
  return 'escalate_owner';
}

function recoveryOutcome(intent, outcome, { attempt, now, nextEligibleAt }) {
  const state = OUTCOME_STATES.has(outcome?.state) ? outcome.state : 'blocked';
  const before = safeReadback(outcome?.before_readback);
  const after = safeReadback(outcome?.after_readback);
  const evidence = Array.isArray(outcome?.evidence_refs)
    ? outcome.evidence_refs.filter((value) => typeof value === 'string' && SAFE_REF.test(value)).slice(0, 32)
    : Array.isArray(intent.evidence_refs)
      ? intent.evidence_refs.filter((value) => typeof value === 'string' && SAFE_REF.test(value)).slice(0, 32)
      : [];
  return {
    schema_version: 1,
    record_type: 'recovery_outcome',
    intent_id: intent.intent_id,
    loop_id: intent.loop_id,
    owner_id: intent.owner_id,
    occurrence_id: intent.occurrence_id,
    release_sha: intent.release_sha,
    action: intent.action,
    failure_layer: typeof intent.failure_layer === 'string' ? intent.failure_layer : 'unknown',
    intent_reason: typeof intent.reason === 'string' ? intent.reason : null,
    state,
    result: state,
    attempt,
    budget_consumed: outcome?.budget_consumed === true,
    before_event_id: typeof before?.event_id === 'string' ? before.event_id : null,
    after_event_id: typeof after?.event_id === 'string' ? after.event_id : null,
    command_exit_code: Number.isInteger(outcome?.command_exit_code) ? outcome.command_exit_code : null,
    readback: after,
    evidence_refs: evidence,
    next_action: typeof outcome?.next_action === 'string'
      ? outcome.next_action : defaultNextAction(state),
    next_eligible_at: nextEligibleAt,
    observed_at: now,
    ...(typeof outcome?.reason === 'string' ? { reason: outcome.reason } : {}),
  };
}

function resultFor(intent, state, attempt, ok, extra = {}) {
  return {
    ok,
    state,
    intent_id: intent.intent_id,
    loop_id: intent.loop_id,
    attempt,
    ...extra,
  };
}

/**
 * Consume at most one durable recovery intent. The release reconciler is the
 * supervisor; this function only chooses one owner, records the attempt, and
 * delegates the already-bounded plan execution to the caller.
 */
export async function consumeRecoveryIntentQueue({
  queuePath,
  journalPath,
  executeIntent,
  allowIntent = () => true,
  supervisorOwnerId = null,
  maxAttempts = 3,
  now = new Date().toISOString(),
  cooldownSeconds = 300,
} = {}) {
  if (typeof queuePath !== 'string' || !queuePath) throw new Error('recovery queue path required');
  if (typeof journalPath !== 'string' || !journalPath) throw new Error('recovery journal path required');
  if (typeof executeIntent !== 'function') throw new Error('recovery executor required');
  if (typeof allowIntent !== 'function') throw new Error('recovery allowIntent invalid');
  if (supervisorOwnerId !== null
      && (typeof supervisorOwnerId !== 'string' || !ID.test(supervisorOwnerId))) {
    throw new Error('recovery supervisor owner invalid');
  }
  if (!Number.isSafeInteger(maxAttempts) || maxAttempts < 1) throw new Error('recovery maxAttempts invalid');
  if (!Number.isSafeInteger(cooldownSeconds) || cooldownSeconds < 1) {
    throw new Error('recovery cooldownSeconds invalid');
  }
  const nowMs = Date.parse(now);
  if (!Number.isFinite(nowMs)) throw new Error('recovery now invalid');

  const [queueRows, historyRows] = await Promise.all([
    readJsonLines(queuePath),
    readJsonLines(journalPath),
  ]);
  const history = journalState(historyRows);
  let selected = null;
  let attempt = 0;
  let cooldownActive = false;
  for (const candidate of queueRows) {
    const intent = candidate?.recovery_intent && typeof candidate.recovery_intent === 'object'
      ? candidate.recovery_intent : candidate;
    if (!validIntent(intent)) continue;
    const state = history.get(intent.intent_id) || {
      attempts: 0, terminal: false, nextEligibleAt: null,
    };
    if (state.terminal) continue;
    if (supervisorOwnerId !== null
        && (intent.loop_id === supervisorOwnerId || intent.owner_id === supervisorOwnerId)) {
      const reason = 'supervisor_self_recovery_excluded';
      await appendJsonLine(journalPath, recoveryOutcome(intent, {
        state: 'skipped',
        budget_consumed: false,
        next_action: 'none',
        reason,
      }, { attempt: state.attempts, now, nextEligibleAt: null }));
      return resultFor(intent, 'skipped', state.attempts, true, { reason });
    }
    if (!allowIntent(intent)) continue;
    const eligibleAt = state.nextEligibleAt || intent.next_eligible_at;
    if (typeof eligibleAt === 'string' && Number.isFinite(Date.parse(eligibleAt))
        && Date.parse(eligibleAt) > nowMs) {
      cooldownActive = true;
      continue;
    }
    if (state.attempts >= maxAttempts) {
      await appendJsonLine(journalPath, recoveryOutcome(intent, {
        state: 'escalated', budget_consumed: false, next_action: 'escalate_owner',
      }, { attempt: state.attempts, now, nextEligibleAt: null }));
      return resultFor(intent, 'escalated', state.attempts, false);
    }
    selected = intent;
    attempt = state.attempts + 1;
    break;
  }
  if (!selected) return {
    ok: true, state: 'idle', reason: cooldownActive ? 'cooldown_active' : 'no_pending_intent',
  };

  await appendJsonLine(journalPath, {
    schema_version: 1, record_type: 'recovery_supervisor', intent_id: selected.intent_id,
    loop_id: selected.loop_id, owner_id: selected.owner_id, state: 'claimed',
    attempt, observed_at: now,
  });
  let outcome;
  try {
    outcome = await executeIntent(selected);
  } catch {
    outcome = { ok: false, state: 'queued', reason: 'supervisor_executor_exception' };
  }
  const state = OUTCOME_STATES.has(outcome?.state) ? outcome.state : 'blocked';
  const ok = outcome?.ok === true;
  const budgetConsumed = outcome?.budget_consumed === true
    || (outcome?.budget_consumed !== false && state === 'queued');
  const nextEligibleAt = TERMINAL_STATES.has(state) ? null
    : new Date(nowMs + cooldownSeconds * 1000).toISOString();
  const record = recoveryOutcome(selected, {
    ...outcome, state, budget_consumed: budgetConsumed,
  }, { attempt, now, nextEligibleAt });
  await appendJsonLine(journalPath, record);
  return resultFor(selected, state, attempt, ok, typeof outcome?.reason === 'string'
    ? { reason: outcome.reason } : {});
}
