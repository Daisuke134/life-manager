"use strict";

// Matches connector-candidate-outcome.js's EVENT_REF: this module suppresses
// terminal candidates for every provider that classifier covers, not luma
// alone. A luma-only regex here silently let connpass terminal outcomes pass
// through unsuppressed forever (the same connpass event kept getting
// re-selected every wake because checkedAttempt() would have thrown had a
// connpass attempt even reached this module).
const EVENT_REF = /^(?:luma-event:\/\/event\/[A-Za-z0-9_-]+|connpass-event:\/\/event\/[1-9][0-9]*)$/;
const OUTCOMES = new Set([
  "verified_success",
  "known_no_effect",
  "unknown_effect",
  "recovery_required",
]);
const FORM_REEVALUATION_CODES = new Set([
  "LUMA_FORM_INPUT_REQUIRED",
  "LUMA_REQUIRED_PROFILE_FIELD_UNAVAILABLE",
]);
const CAPABILITY_VERSION = /^[a-z0-9][a-z0-9._-]{0,63}$/;

function invalid() {
  throw new Error("Connector candidate suppression invalid");
}

function exactInstant(value) {
  const text = String(value || "").trim();
  const milliseconds = Date.parse(text);
  if (!Number.isFinite(milliseconds) || new Date(milliseconds).toISOString() !== text) invalid();
  return milliseconds;
}

function checkedAttempt(attempt) {
  if (
    !attempt || typeof attempt !== "object" || Array.isArray(attempt)
    || !EVENT_REF.test(String(attempt.event_ref || ""))
    || !OUTCOMES.has(attempt.outcome)
    || !/^[A-Za-z0-9_:-]{1,100}$/.test(String(attempt.safe_reason || ""))
    || !(attempt.retry_after === null || typeof attempt.retry_after === "string")
    || !(attempt.capability_version == null || CAPABILITY_VERSION.test(attempt.capability_version))
  ) invalid();
  const observedAt = exactInstant(attempt.observed_at);
  const retryAfter = attempt.retry_after === null ? null : exactInstant(attempt.retry_after);
  return { ...attempt, capability_version: attempt.capability_version || null, observedAt, retryAfter };
}

function latestCandidateAttempts(input = {}) {
  const now = exactInstant(input.now);
  if (!Array.isArray(input.attempts) || input.attempts.length > 10_000) invalid();
  const latest = new Map();
  for (const raw of input.attempts) {
    const attempt = checkedAttempt(raw);
    const previous = latest.get(attempt.event_ref);
    if (!previous || attempt.observedAt > previous.observedAt) latest.set(attempt.event_ref, attempt);
  }
  return Object.freeze({ now, latest });
}

function activeSuppressedEventRefs(input = {}) {
  const { now, latest } = latestCandidateAttempts(input);
  const capabilityVersion = input.capabilityVersion == null ? null : String(input.capabilityVersion);
  if (capabilityVersion !== null && !CAPABILITY_VERSION.test(capabilityVersion)) invalid();
  const suppressed = new Set();
  for (const attempt of latest.values()) {
    if (
      attempt.outcome === "known_no_effect"
      && (attempt.retryAfter === null || attempt.retryAfter > now)
      && !(
        capabilityVersion !== null
        && FORM_REEVALUATION_CODES.has(attempt.safe_reason)
        && attempt.capability_version !== capabilityVersion
      )
    ) suppressed.add(attempt.event_ref);
  }
  return suppressed;
}

module.exports = { activeSuppressedEventRefs, latestCandidateAttempts };
