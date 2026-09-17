import { buildRecoveryIntent } from './recovery-intent.mjs';

const RELEASE_SHA = /^[0-9a-f]{40}$/u;

/**
 * Turn one sanitized runtime failure into a durable recovery-intent record.
 * Missing identity or release provenance returns null: guessing a target is
 * less safe than leaving the failure visible for a later bounded observer.
 */
export function buildRecoveryIntentRecord({
  loopId,
  ownerId,
  wakeId,
  runId,
  releaseSha,
  failureLayer = 'unknown',
  effectClass = 'none',
  effectStatus = 'unknown',
  consecutiveFailureStreak = 1,
  threshold = 3,
  blocker = null,
} = {}) {
  if (typeof loopId !== 'string' || !loopId.trim()
    || typeof ownerId !== 'string' || !ownerId.trim()
    || typeof wakeId !== 'string' || !wakeId.trim()
    || typeof runId !== 'string' || !runId.trim()
    || typeof releaseSha !== 'string' || !RELEASE_SHA.test(releaseSha)) return null;
  try {
    return buildRecoveryIntent({
      loop_id: loopId,
      owner_id: ownerId,
      wake_id: wakeId,
      run_id: runId,
      release_sha: releaseSha,
      failure_layer: failureLayer,
      effect_class: effectClass,
      effect_status: effectStatus,
      consecutive_failure_streak: consecutiveFailureStreak,
      threshold,
      blocker,
      evidence_refs: [`lm-loop://${loopId}/${wakeId}/failure`],
    });
  } catch {
    return null;
  }
}
