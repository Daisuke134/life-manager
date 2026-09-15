/**
 * harness-health.mjs — Pure: tool-use health aggregation over already-parsed ledger records.
 *
 * anicca-harness-tooluse-health R1-R5: classifyLayer, computeSlotHealth,
 * computeBrainTransportHealth, computeHarnessHealth, shouldEscalate. Every function here takes
 * already-parsed ledger record arrays and returns plain objects — none opens a file, spawns a
 * process, or reads process.env except DEFAULT_STREAK_THRESHOLD's one module-level constant (same
 * `Number(process.env.X) || N` idiom already used by catalog-gate.mjs::DEFAULT_BOOTSTRAP_RESERVE_USDC).
 *
 * INV-NO-JUDGMENT: this is pure bookkeeping over the ALREADY-deterministic `kind` enum index.mjs
 * itself assigns via if-else on exitCode/timedOut/notFound — never a new judgment.
 * INV-LOOPDETECT-SEPARATE: `loop_detect` already has its own consecutive-streak + exponential
 * cooldown (index.mjs lines 180-284); it is explicitly excluded from computeSlotHealth's subset by a
 * `kind`-membership check, regardless of whether its (shared) `slot` field matches.
 *
 * See specs/behavioral-spec.md and specs/verification-architecture.md
 * (anicca-project/.vcsdd/features/anicca-harness-tooluse-health/) for the full requirement text.
 */

// REQ-R5's documented default: same `Number(process.env.X) || N` fallback idiom already used for
// DEFAULT_BOOTSTRAP_RESERVE_USDC in catalog-gate.mjs.
export const DEFAULT_STREAK_THRESHOLD = Number(process.env.HARNESS_HEALTH_STREAK_THRESHOLD) || 5;

const CLEAN_KINDS = new Set(['wake', 'narrate', 'shutdown']);
// R2's slot-health subset: `loop_detect` is deliberately NOT a member of this set even though its
// records carry a `slot` field (index.mjs:281) — INV-LOOPDETECT-SEPARATE.
const SLOT_HEALTH_KINDS = new Set(['wake', 'skill_missing', 'skill_timeout', 'skill_error']);
// R3's brain-transport streak reset set — narrower than CLEAN_KINDS (shutdown never resets it,
// consistent with behavioral-spec.md R3's literal text: "reset by any record whose kind ∈ {wake, narrate}").
const BRAIN_TRANSPORT_RESET_KINDS = new Set(['wake', 'narrate']);

/**
 * R1 — classifyLayer(record): maps `record.kind` to exactly one health layer. Fail-safe: any
 * unrecognized kind (including `loop_detect`, which is deliberately out of this mapping per
 * INV-LOOPDETECT-SEPARATE) maps to 'unknown', never throws.
 *
 * @param {{kind?: string}} record
 * @returns {'clean'|'brain_transport'|'tool_missing'|'tool_timeout'|'tool_logic'|'unknown'}
 */
export function classifyLayer(record) {
  const kind = record && record.kind;
  if (CLEAN_KINDS.has(kind)) return 'clean';
  if (kind === 'wake_error') return 'brain_transport';
  if (kind === 'skill_missing') return 'tool_missing';
  if (kind === 'skill_timeout') return 'tool_timeout';
  if (kind === 'skill_error') return 'tool_logic';
  return 'unknown';
}

/**
 * R2 — computeSlotHealth(records, slot): per-slot tool-call health over the subset of `records`
 * carrying that exact `slot` value AND `kind` ∈ SLOT_HEALTH_KINDS (loop_detect excluded regardless
 * of its own `slot` field — INV-LOOPDETECT-SEPARATE). `records` is assumed chronologically ordered
 * (the same order `readLedgerLines`/`recentLedgerLines` already produce).
 *
 * @param {object[]} records
 * @param {string} slot
 * @returns {{slot:string,wakes:number,failures:number,failureRate:number,consecutiveFailureStreak:number,lastFailureLayer:string|null,lastFailureTs:number|null,lastFailureWakeId:string|null}|null}
 */
export function computeSlotHealth(records, slot) {
  const arr = Array.isArray(records) ? records : [];
  const subset = arr.filter((r) => r && r.slot === slot && SLOT_HEALTH_KINDS.has(r.kind));
  if (subset.length === 0) return null;

  const wakes = subset.length;
  let failures = 0;
  let lastFailureLayer = null;
  let lastFailureTs = null;
  let lastFailureWakeId = null;

  for (const r of subset) {
    const layer = classifyLayer(r);
    if (layer !== 'clean') {
      failures += 1;
      lastFailureLayer = layer;
      lastFailureTs = r.ts != null ? r.ts : null;
      lastFailureWakeId = r.wake_id != null ? r.wake_id : null;
    }
  }

  let consecutiveFailureStreak = 0;
  for (let i = subset.length - 1; i >= 0; i--) {
    if (classifyLayer(subset[i]) === 'clean') break;
    consecutiveFailureStreak += 1;
  }

  return {
    slot,
    wakes,
    failures,
    failureRate: failures / wakes,
    consecutiveFailureStreak,
    lastFailureLayer,
    lastFailureTs,
    lastFailureWakeId,
  };
}

/**
 * R3 — computeBrainTransportHealth(records): loop-level health of ALL `wake_error` records (which
 * never carry `slot` — R1) across the WHOLE ledger, never conflated with any single slot's health.
 * The trailing streak is scanned over the WHOLE `records` array (not just the wake_error subset)
 * because its reset condition depends on OTHER kinds (`wake`/`narrate`) that only exist outside that
 * subset; any other kind (skill_error, skill_missing, skill_timeout, loop_detect, shutdown) is
 * skipped while scanning — it neither counts nor resets the streak.
 *
 * @param {object[]} records
 * @returns {{failures:number,consecutiveFailureStreak:number,lastFailureTs:number|null,lastFailureWakeId:string|null}}
 */
export function computeBrainTransportHealth(records) {
  const arr = Array.isArray(records) ? records : [];
  const wakeErrors = arr.filter((r) => r && r.kind === 'wake_error');
  const failures = wakeErrors.length;

  let consecutiveFailureStreak = 0;
  for (let i = arr.length - 1; i >= 0; i--) {
    const r = arr[i];
    if (!r) continue;
    if (r.kind === 'wake_error') {
      consecutiveFailureStreak += 1;
      continue;
    }
    if (BRAIN_TRANSPORT_RESET_KINDS.has(r.kind)) break;
    // any other kind: skip, does not count and does not reset
  }

  const last = wakeErrors[wakeErrors.length - 1];
  return {
    failures,
    consecutiveFailureStreak,
    lastFailureTs: last ? (last.ts != null ? last.ts : null) : null,
    lastFailureWakeId: last ? (last.wake_id != null ? last.wake_id : null) : null,
  };
}

/**
 * R5 — shouldEscalate(consecutiveFailureStreak, threshold): pure boundary predicate, never invokes
 * any repair action itself (R10).
 *
 * @param {number} consecutiveFailureStreak
 * @param {number} threshold
 * @returns {boolean}
 */
export function shouldEscalate(consecutiveFailureStreak, threshold) {
  return Number(consecutiveFailureStreak) >= Number(threshold);
}

const RECOVERY_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

/**
 * R10 — decideRecoveryAction: pure recovery routing for one owner.  It returns a plan only;
 * callers own the existing retry/reclaim/escalation mechanisms and must preserve sibling owners.
 * No process, browser, provider, ledger, or notification side effect is permitted here.
 *
 * @param {{ownerId?: string, health?: object, retryAttempts?: number, retryLimit?: number,
 *   streakThreshold?: number}} input
 * @returns {{action:string,ownerId:string|null,slot:string|null,reason:string,retryAttempt:number,
 *   preserveSiblings:true}}
 */
export function decideRecoveryAction(input = {}) {
  const ownerId = typeof input.ownerId === 'string' && RECOVERY_ID.test(input.ownerId)
    ? input.ownerId : null;
  const health = input.health && typeof input.health === 'object' && !Array.isArray(input.health)
    ? input.health : null;
  const slot = health && typeof health.slot === 'string' && RECOVERY_ID.test(health.slot)
    ? health.slot : null;
  const retryAttempts = input.retryAttempts == null ? 0 : input.retryAttempts;
  const retryLimit = input.retryLimit == null ? 2 : input.retryLimit;
  const threshold = input.streakThreshold == null ? DEFAULT_STREAK_THRESHOLD : input.streakThreshold;
  const validNumbers = [health?.failures, health?.consecutiveFailureStreak,
    retryAttempts, retryLimit, threshold].every((value) => (
    Number.isSafeInteger(value) && value >= 0
  ));
  if (!ownerId || !slot || !health || !validNumbers || retryLimit < 1
    || retryAttempts > retryLimit || threshold < 1) {
    return Object.freeze({
      action: 'block', ownerId, slot, reason: 'invalid_recovery_input',
      retryAttempt: Number.isSafeInteger(retryAttempts) && retryAttempts >= 0 ? retryAttempts : 0,
      preserveSiblings: true,
    });
  }
  if (health.failures === 0 && health.consecutiveFailureStreak === 0) {
    return Object.freeze({
      action: 'continue', ownerId, slot, reason: 'healthy', retryAttempt: retryAttempts,
      preserveSiblings: true,
    });
  }
  if (retryAttempts >= retryLimit) {
    return Object.freeze({
      action: 'escalate_repair', ownerId, slot, reason: 'retry_budget_exhausted',
      retryAttempt: retryAttempts, preserveSiblings: true,
    });
  }
  if (shouldEscalate(health.consecutiveFailureStreak, threshold)) {
    return Object.freeze({
      action: 'escalate_repair', ownerId, slot, reason: 'failure_streak_threshold',
      retryAttempt: retryAttempts, preserveSiblings: true,
    });
  }
  return Object.freeze({
    action: 'retry_owner', ownerId, slot, reason: 'bounded_retry',
    retryAttempt: retryAttempts + 1, preserveSiblings: true,
  });
}

/**
 * R4 — computeHarnessHealth(records, opts): whole-ledger report shape covering every distinct slot
 * value present in the R2 subset (SLOT_HEALTH_KINDS), plus loop-level brain-transport health, each
 * entry annotated with R5's `escalate`. Never throws, even for empty/absent `records`.
 *
 * `now` is an optional epoch-ms (or Date) override for `generatedAt`'s wall-clock stamp — the same
 * test-injection idiom this codebase already uses elsewhere (ANICCA_BALANCE_OVERRIDE, CLAUDE_BIN);
 * defaults to Date.now() when omitted. Not part of the R1-R5 deterministic contract itself.
 *
 * @param {object[]} records
 * @param {{streakThreshold?: number, now?: number|Date}} [opts]
 * @returns {{perSlot: Record<string, object>, brainTransport: object, generatedAt: string}}
 */
export function computeHarnessHealth(records, opts = {}) {
  const arr = Array.isArray(records) ? records : [];
  const { streakThreshold, now } = opts || {};
  const threshold = streakThreshold != null ? streakThreshold : DEFAULT_STREAK_THRESHOLD;

  const slots = [];
  for (const r of arr) {
    if (r && SLOT_HEALTH_KINDS.has(r.kind) && r.slot != null && !slots.includes(r.slot)) {
      slots.push(r.slot);
    }
  }

  const perSlot = {};
  for (const slot of slots) {
    const health = computeSlotHealth(arr, slot);
    perSlot[slot] = { ...health, escalate: shouldEscalate(health.consecutiveFailureStreak, threshold) };
  }

  const brainHealth = computeBrainTransportHealth(arr);
  const brainTransport = { ...brainHealth, escalate: shouldEscalate(brainHealth.consecutiveFailureStreak, threshold) };

  return {
    perSlot,
    brainTransport,
    generatedAt: new Date(now != null ? now : Date.now()).toISOString(),
  };
}

/**
 * R6 helper — capFailureDetail(text): whitespace-collapse + cap at 4000 chars, the SAME shared pure
 * step index.mjs::runOneWake applies identically to BOTH the tool_missing/tool_timeout/tool_logic
 * branch (already-redacted skillResult.output) and the brain_transport branch (its own
 * redactPrivateKeyPatterns(err.message) output) before appending to harness-failures.jsonl. Distinct
 * from — and never applied to — the existing 900-char `result` field on ledger.jsonl
 * (INV-NO-PROMPT-REGRESSION).
 *
 * @param {unknown} text
 * @returns {string}
 */
export function capFailureDetail(text) {
  const s = typeof text === 'string' ? text : String(text == null ? '' : text);
  return s.replace(/\s+/g, ' ').slice(0, 4000);
}
