"use strict";

const { localDay, localMinuteOfDay } = require("./user-tz.js");

const WINDOWS = Object.freeze({
  morning_orientation: Object.freeze({ start: 7 * 60 + 30, end: 9 * 60 + 30, family: "affirmation" }),
  midday_awareness: Object.freeze({ start: 12 * 60, end: 15 * 60, family: "mindfulness_inquiry" }),
  evening_direction: Object.freeze({ start: 20 * 60 + 30, end: 22 * 60 + 30, family: "manifestation" }),
});
const WINDOW_ORDER = Object.freeze(["morning_orientation", "midday_awareness", "evening_direction"]);
const DAILY_CAP = 3;
const MIN_GAP_MS = 3 * 60 * 60 * 1000;

function deterministicMinute(uid, day, window, bounds) {
  let hash = 0x811c9dc5;
  for (const character of `${uid}:${day}:${window}`) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return bounds.start + (hash % Math.max(1, bounds.end - bounds.start));
}

function inQuietHours(minute, quietHours) {
  if (!quietHours) return false;
  const start = Number(quietHours.start);
  const end = Number(quietHours.end);
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || start > 1440 || end < 0 || end > 1440) return false;
  if (start === end) return true;
  return start < end ? minute >= start && minute < end : minute >= start || minute < end;
}

function validateInput(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("input must be an object");
  if (!input.uid || !Number.isFinite(input.nowMs)) throw new Error("uid and nowMs are required");
  if (input.tzOffsetH !== null && !Number.isFinite(input.tzOffsetH)) throw new Error("tzOffsetH must be finite or null");
  if (!Number.isInteger(input.sentTodayCount) || input.sentTodayCount < 0) throw new Error("sentTodayCount must be a non-negative integer");
  if (input.lastSentMs !== null && !Number.isFinite(input.lastSentMs)) throw new Error("lastSentMs must be null or finite");
  if (!Array.isArray(input.sentFamilies) || !Array.isArray(input.recentQuoteIds)) throw new Error("send history must be arrays");
  if (input.eligibleQuoteIds !== null && !Array.isArray(input.eligibleQuoteIds)) throw new Error("eligibleQuoteIds must be an array or null");
  return input;
}

function evaluateMentalOpportunity(input) {
  validateInput(input);
  if (input.tzOffsetH === null) return { decision: "suppress", reason: "no-timezone" };
  const minute = localMinuteOfDay(input.nowMs, input.tzOffsetH);
  if (input.sentTodayCount >= DAILY_CAP) return { decision: "suppress", reason: "daily-cap-reached" };
  if (input.lastSentMs !== null && input.nowMs - input.lastSentMs < MIN_GAP_MS) {
    return { decision: "suppress", reason: "too-soon-after-last" };
  }
  if (input.calendarBusy) return { decision: "suppress", reason: "calendar-busy" };
  if (inQuietHours(minute, input.quietHours)) return { decision: "suppress", reason: "quiet-hours" };
  const window = WINDOW_ORDER.find((name) => minute >= WINDOWS[name].start && minute < WINDOWS[name].end);
  if (!window) return { decision: "suppress", reason: "outside-opportunity-window" };
  const spec = WINDOWS[window];
  if (input.sentFamilies.includes(spec.family)) return { decision: "suppress", reason: "family-already-sent" };
  if (Array.isArray(input.eligibleQuoteIds)
      && input.eligibleQuoteIds.every((id) => input.recentQuoteIds.includes(id))) {
    return { decision: "suppress", reason: "no-eligible-quote" };
  }
  const day = localDay(input.nowMs, input.tzOffsetH);
  return {
    decision: "send",
    window,
    family: spec.family,
    localDay: day,
    scheduledMinute: deterministicMinute(input.uid, day, window, spec),
  };
}

module.exports = { WINDOWS, WINDOW_ORDER, DAILY_CAP, MIN_GAP_MS, deterministicMinute, inQuietHours, validateInput, evaluateMentalOpportunity };
