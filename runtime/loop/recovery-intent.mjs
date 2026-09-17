import { createHash } from 'node:crypto';

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const SAFE_REF = /^[a-z][a-z0-9+.-]*:\/\/[A-Za-z0-9._:/-]{1,512}$/u;
const EFFECT_BEARING = new Set(['publish', 'message', 'money', 'application', 'trade', 'account_mutation']);
const FAILURE_LAYERS = new Set(['clean', 'brain_transport', 'tool_missing', 'tool_timeout', 'tool_logic', 'unknown']);

function safeId(value, field) {
  if (typeof value !== 'string' || !SAFE_ID.test(value)) throw new Error(`invalid ${field}`);
  return value;
}

function refs(value) {
  if (!Array.isArray(value) || value.length > 32 || value.some((ref) => typeof ref !== 'string' || !SAFE_REF.test(ref))) {
    throw new Error('invalid evidence_refs');
  }
  return [...value];
}

function stableHash(value) {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex').slice(0, 32);
}

/**
 * Decide the next safe recovery boundary. This function never invokes launchd,
 * a provider, a browser, a model, or a self-fix process.
 */
export function buildRecoveryIntent(input = {}) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('recovery input must be an object');
  const loopId = safeId(input.loop_id, 'loop_id');
  const ownerId = safeId(input.owner_id, 'owner_id');
  const wakeId = safeId(input.wake_id, 'wake_id');
  const runId = safeId(input.run_id, 'run_id');
  const releaseSha = safeId(input.release_sha, 'release_sha');
  const failureLayer = input.failure_layer == null ? 'unknown' : String(input.failure_layer);
  if (!FAILURE_LAYERS.has(failureLayer)) throw new Error('invalid failure_layer');
  const effectClass = input.effect_class == null ? 'none' : String(input.effect_class);
  const effectStatus = input.effect_status == null ? 'unknown' : String(input.effect_status);
  if (!SAFE_ID.test(effectClass) || !SAFE_ID.test(effectStatus)) throw new Error('invalid effect state');
  const status = input.status == null ? 'fail' : String(input.status);
  if (!['running', 'pass', 'fail', 'blocked'].includes(status)) throw new Error('invalid status');
  const blocker = input.blocker == null ? null : safeId(String(input.blocker), 'blocker');
  const streak = Number(input.consecutive_failure_streak == null ? 0 : input.consecutive_failure_streak);
  const threshold = Number(input.threshold == null ? 3 : input.threshold);
  if (!Number.isInteger(streak) || streak < 0 || !Number.isInteger(threshold) || threshold < 1) {
    throw new Error('invalid failure threshold');
  }
  const evidenceRefs = refs(input.evidence_refs || []);
  const base = { loop_id: loopId, owner_id: ownerId, wake_id: wakeId, run_id: runId,
    release_sha: releaseSha, failure_layer: failureLayer, effect_class: effectClass,
    effect_status: effectStatus, blocker, evidence_refs: evidenceRefs };

  let action = 'reconcile_owner';
  let reason = 'bounded_owner_reconciliation';
  let retryable = true;
  let effectFence = 'not_required';
  if (status === 'pass' || failureLayer === 'clean') {
    action = 'no_action';
    reason = 'healthy_terminal';
    retryable = false;
  } else if (EFFECT_BEARING.has(effectClass) && effectStatus === 'unknown') {
    action = 'hold_effect_unknown';
    reason = 'official_readback_required_before_retry';
    retryable = false;
    effectFence = 'required';
  } else if (failureLayer === 'unknown') {
    action = 'escalate_owner';
    reason = 'failure_boundary_unclassified';
    retryable = false;
  } else if (streak >= threshold) {
    action = 'escalate_repeated_failure';
    reason = 'bounded_retry_budget_exhausted';
    retryable = false;
  }

  const intentId = stableHash({ ...base, action, reason, streak, threshold });
  return Object.freeze({
    schema_version: 1,
    intent_id: intentId,
    loop_id: loopId,
    owner_id: ownerId,
    wake_id: wakeId,
    run_id: runId,
    release_sha: releaseSha,
    action,
    reason,
    failure_layer: failureLayer,
    effect_fence: effectFence,
    retryable,
    mutates_external_effect: false,
    evidence_refs: evidenceRefs,
    next_eligible_at: input.next_eligible_at == null ? null : String(input.next_eligible_at),
  });
}
