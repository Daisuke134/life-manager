"use strict";

const USER_VISIBLE_EVENT_KINDS = Object.freeze(new Set([
  "human_action_required",
  "urgent_safety",
  "material_outcome",
  "persistent_blocker",
]));
const ROUTINE_EVENT_KINDS = Object.freeze(new Set([
  "wake_completed",
  "retry_scheduled",
  "health_check",
  "evaluation_finished",
]));

const EVENT_KIND = /^[a-z][a-z0-9_]{0,63}$/u;

function normalizeEventKind(value) {
  return typeof value === "string" && EVENT_KIND.test(value) ? value : "unknown";
}

/**
 * Decide whether one internal event may cross the user-notification boundary.
 * This function is pure: delivery, deduplication, and retry belong to the outbox.
 */
function decideNotification(event = {}) {
  const eventKind = normalizeEventKind(event && typeof event === "object" ? event.event_kind : null);
  if (USER_VISIBLE_EVENT_KINDS.has(eventKind)) {
    return Object.freeze({ event_kind: eventKind, visibility: "user_visible", reason: eventKind });
  }
  return Object.freeze({
    event_kind: eventKind,
    visibility: "internal_only",
    reason: eventKind === "unknown" || !ROUTINE_EVENT_KINDS.has(eventKind)
      ? "unknown_event_kind"
      : "routine",
  });
}

module.exports = { decideNotification, ROUTINE_EVENT_KINDS, USER_VISIBLE_EVENT_KINDS };
