"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  WINDOWS,
  DAILY_CAP,
  MIN_GAP_MS,
  evaluateMentalOpportunity,
  deterministicMinute,
} = require("./mental-opportunity.js");

const JST = 9;
const NOW = Date.parse("2026-09-18T08:00:00+09:00");

function input(overrides = {}) {
  return {
    uid: "u1",
    nowMs: NOW,
    tzOffsetH: JST,
    sentTodayCount: 0,
    lastSentMs: null,
    sentFamilies: [],
    recentQuoteIds: [],
    eligibleQuoteIds: null,
    calendarBusy: false,
    quietHours: null,
    profile: { themes: ["self-worth"], tones: ["gentle"], avoidThemes: [] },
    ...overrides,
  };
}

test("morning local window opens an affirmation opportunity", () => {
  const result = evaluateMentalOpportunity(input());
  assert.equal(result.decision, "send");
  assert.equal(result.window, "morning_orientation");
  assert.equal(result.family, "affirmation");
});

test("outside all windows stays silent", () => {
  const result = evaluateMentalOpportunity(input({ nowMs: Date.parse("2026-09-18T10:00:00+09:00") }));
  assert.deepEqual(result, { decision: "suppress", reason: "outside-opportunity-window" });
});

test("missing timezone, busy calendar, quiet hours, cap, and spacing suppress", () => {
  assert.equal(evaluateMentalOpportunity(input({ tzOffsetH: null })).reason, "no-timezone");
  const busy = evaluateMentalOpportunity(input({ calendarBusy: true }));
  assert.equal(busy.reason, "calendar-busy");
  assert.equal(busy.window, "morning_orientation");
  assert.equal(evaluateMentalOpportunity(input({ quietHours: { start: 0, end: 1440 } })).reason, "quiet-hours");
  assert.equal(evaluateMentalOpportunity(input({ sentTodayCount: DAILY_CAP })).reason, "daily-cap-reached");
  assert.equal(evaluateMentalOpportunity(input({ lastSentMs: NOW - MIN_GAP_MS + 1 })).reason, "too-soon-after-last");
});

test("same family and same template are not repeated", () => {
  assert.equal(evaluateMentalOpportunity(input({ sentFamilies: ["affirmation"] })).reason, "family-already-sent");
  assert.equal(evaluateMentalOpportunity(input({
    eligibleQuoteIds: ["antara:enough-now:ja"],
    recentQuoteIds: ["antara:enough-now:ja"],
  })).reason, "no-eligible-quote");
});

test("the deterministic minute is stable per user/day/window and differs by identity", () => {
  const a = deterministicMinute("u1", "2026-09-18", "morning_orientation", WINDOWS.morning_orientation);
  const b = deterministicMinute("u1", "2026-09-18", "morning_orientation", WINDOWS.morning_orientation);
  const c = deterministicMinute("u2", "2026-09-18", "morning_orientation", WINDOWS.morning_orientation);
  assert.equal(a, b);
  assert.ok(a >= WINDOWS.morning_orientation.start && a < WINDOWS.morning_orientation.end);
  assert.ok(c >= WINDOWS.morning_orientation.start && c < WINDOWS.morning_orientation.end);
});
