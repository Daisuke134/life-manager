"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { decideMentalOutcome } = require("./mental-outcome.js");

const NOW = Date.parse("2026-09-17T12:00:00+09:00");
const PROFILE = { themes: ["self-worth"], tones: ["gentle"], avoidThemes: [] };
const REJECTION = {
  sourceOutcomeId: "gmail:msg-1",
  kind: "rejection",
  company: "Example社",
  role: "Software Engineer",
  verifiedAt: NOW - 10 * 60_000,
  evidenceRef: "gmail-message://msg-1",
};

test("verified rejection selects a supportive catalog quote without reading mail text", () => {
  const result = decideMentalOutcome({
    outcome: REJECTION, nowMs: NOW, calendarBusy: false,
    sentTodayCount: 0, lastSentMs: null, sentOutcomeIds: [], profile: PROFILE,
  });
  assert.equal(result.decision, "send");
  assert.equal(result.sourceOutcomeId, "gmail:msg-1");
  assert.ok(result.quote.text);
  assert.equal(result.company, undefined);
});

test("unknown or unverified outcome never creates a mental message", () => {
  for (const outcome of [{ ...REJECTION, kind: "unknown" }, { ...REJECTION, verifiedAt: null }]) {
    assert.deepEqual(decideMentalOutcome({ outcome, nowMs: NOW, calendarBusy: false,
      sentTodayCount: 0, lastSentMs: null, sentOutcomeIds: [], profile: PROFILE }),
    { decision: "suppress", reason: "outcome-not-verified" });
  }
});

test("meeting, duplicate, spacing, and cap suppress the optional mental line", () => {
  const base = { outcome: REJECTION, nowMs: NOW, sentTodayCount: 0, lastSentMs: null,
    sentOutcomeIds: [], profile: PROFILE };
  assert.equal(decideMentalOutcome({ ...base, calendarBusy: true }).reason, "calendar-busy");
  assert.equal(decideMentalOutcome({ ...base, calendarBusy: false, sentOutcomeIds: [REJECTION.sourceOutcomeId] }).reason, "outcome-already-served");
  assert.equal(decideMentalOutcome({ ...base, calendarBusy: false, lastSentMs: NOW - 60 * 60_000 }).reason, "too-soon-after-last");
  assert.equal(decideMentalOutcome({ ...base, calendarBusy: false, sentTodayCount: 3 }).reason, "daily-cap-reached");
});

test("verified offer and interview outcomes use their own approved families", () => {
  for (const kind of ["offer", "interview"]) {
    const result = decideMentalOutcome({
      outcome: { ...REJECTION, sourceOutcomeId: `gmail:${kind}`, kind },
      nowMs: NOW, calendarBusy: false, sentTodayCount: 0,
      lastSentMs: null, sentOutcomeIds: [], profile: { themes: ["courage"], tones: ["direct"], avoidThemes: [] },
    });
    assert.equal(result.decision, "send");
    assert.ok(result.quote.family === "affirmation" || result.quote.family === "manifestation");
  }
});
