import { promises as fs } from 'node:fs';
import path from 'node:path';

const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const RELEASE_SHA = /^[0-9a-f]{40}$/u;
const TERMINAL_STATES = new Set(['repaired', 'held', 'skipped', 'blocked', 'escalated']);

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
    && typeof value.release_sha === 'string' && RELEASE_SHA.test(value.release_sha)
    && typeof value.action === 'string' && ID.test(value.action)
    && value.mutates_external_effect === false;
}

function journalState(journalRows) {
  const states = new Map();
  for (const row of journalRows) {
    if (!row || typeof row.intent_id !== 'string') continue;
    const previous = states.get(row.intent_id) || { attempts: 0, terminal: false };
    const attempt = Number.isSafeInteger(row.attempt) && row.attempt > previous.attempts
      ? row.attempt : previous.attempts;
    states.set(row.intent_id, {
      attempts: attempt,
      terminal: previous.terminal || TERMINAL_STATES.has(row.state),
    });
  }
  return states;
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
  maxAttempts = 3,
  now = new Date().toISOString(),
} = {}) {
  if (typeof queuePath !== 'string' || !queuePath) throw new Error('recovery queue path required');
  if (typeof journalPath !== 'string' || !journalPath) throw new Error('recovery journal path required');
  if (typeof executeIntent !== 'function') throw new Error('recovery executor required');
  if (!Number.isSafeInteger(maxAttempts) || maxAttempts < 1) throw new Error('recovery maxAttempts invalid');

  const [queueRows, historyRows] = await Promise.all([
    readJsonLines(queuePath),
    readJsonLines(journalPath),
  ]);
  const history = journalState(historyRows);
  let selected = null;
  let attempt = 0;
  for (const candidate of queueRows) {
    const intent = candidate?.recovery_intent && typeof candidate.recovery_intent === 'object'
      ? candidate.recovery_intent : candidate;
    if (!validIntent(intent)) continue;
    const state = history.get(intent.intent_id) || { attempts: 0, terminal: false };
    if (state.terminal) continue;
    if (state.attempts >= maxAttempts) {
      await appendJsonLine(journalPath, {
        schema_version: 1, record_type: 'recovery_supervisor', intent_id: intent.intent_id,
        loop_id: intent.loop_id, owner_id: intent.owner_id, state: 'escalated',
        attempt: state.attempts, observed_at: now,
      });
      return resultFor(intent, 'escalated', state.attempts, false);
    }
    selected = intent;
    attempt = state.attempts + 1;
    break;
  }
  if (!selected) return { ok: true, state: 'idle', reason: 'no_pending_intent' };

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
  const state = typeof outcome?.state === 'string' ? outcome.state : 'blocked';
  const ok = outcome?.ok === true;
  await appendJsonLine(journalPath, {
    schema_version: 1, record_type: 'recovery_supervisor', intent_id: selected.intent_id,
    loop_id: selected.loop_id, owner_id: selected.owner_id, state,
    attempt, observed_at: now, ...(typeof outcome?.reason === 'string' ? { reason: outcome.reason } : {}),
  });
  return resultFor(selected, state, attempt, ok, typeof outcome?.reason === 'string'
    ? { reason: outcome.reason } : {});
}
