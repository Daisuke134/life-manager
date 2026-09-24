import recoveryClass from './recovery-class.cjs';

const { classifyRecoveryJob } = recoveryClass;

const ACTIONS_WITHOUT_EXECUTION = new Set([
  'no_action',
  'hold_effect_unknown',
  'escalate_owner',
  'escalate_repeated_failure',
]);

function required(value, field) {
  if (typeof value !== 'string' || value.length === 0) throw new Error(`recovery plan missing ${field}`);
  return value;
}

/**
 * Convert a recovery intent into a bounded reconcile plan. This is still a
 * plan, not a launchd/provider mutation. A supervisor may execute only the
 * generated command after checking the same release and owner constraints.
 */
export function buildRecoveryApplyPlan({ intent, registry }) {
  if (!intent || typeof intent !== 'object' || Array.isArray(intent)) throw new Error('recovery intent invalid');
  if (!registry || typeof registry !== 'object' || !registry.loops || typeof registry.loops !== 'object') {
    throw new Error('loop registry invalid');
  }
  const loopId = required(intent.loop_id, 'loop_id');
  const ownerId = required(intent.owner_id, 'owner_id');
  const occurrenceId = required(intent.occurrence_id, 'occurrence_id');
  const intentId = required(intent.intent_id, 'intent_id');
  const releaseSha = required(intent.release_sha, 'release_sha');
  const action = required(intent.action, 'action');
  const entry = registry.loops[loopId];
  if (!entry || typeof entry !== 'object') throw new Error(`recovery loop not in registry: ${loopId}`);
  if (ownerId !== loopId) throw new Error('recovery owner identity mismatch');
  if (!occurrenceId.startsWith(`${loopId}:`)) throw new Error('recovery occurrence identity mismatch');
  if (entry.entrypoint === 'runtime/loop/recovery-supervisor-cli.mjs') {
    throw new Error('recovery supervisor owner excluded');
  }
  if (classifyRecoveryJob(entry) === 'read_only_external_owner') {
    throw new Error('recovery paid owner excluded');
  }
  if (ACTIONS_WITHOUT_EXECUTION.has(action)) {
    return Object.freeze({
      schema_version: 1,
      intent_id: intentId,
      loop_id: loopId,
      owner_id: ownerId,
      occurrence_id: occurrenceId,
      release_sha: releaseSha,
      action,
      execute: false,
      commands: [],
      constraints: { external_effect: false, sibling_mutation: false },
    });
  }
  if (action !== 'reconcile_owner') throw new Error(`unsupported recovery action: ${action}`);
  const providerRoute = required(entry.provider_route, 'provider_route');
  return Object.freeze({
    schema_version: 1,
    intent_id: intentId,
    loop_id: loopId,
    owner_id: ownerId,
    occurrence_id: occurrenceId,
    release_sha: releaseSha,
    action,
    execute: true,
    commands: [{
      program: 'lm-loop',
      args: ['reconcile', providerRoute, '--loaded-idle-only', '--max-owners', '1', '--loop-id', loopId],
    }],
    constraints: {
      release_sha: releaseSha,
      loaded_idle_only: true,
      max_owners: 1,
      external_effect: false,
      sibling_mutation: false,
    },
  });
}
