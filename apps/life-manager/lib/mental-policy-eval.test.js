"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { validateDecisionRow, scorePolicyRows, comparePolicyReplays } = require("./mental-policy-eval.js");

const BASE = {
  uid: "u1", policyVersion: "v1", profileVersion: "p1", sourceOutcomeId: null,
  candidateQuoteIds: ["q1"], selectedQuoteId: "q1", silenceReason: null,
  calendarBusy: false, window: "morning_orientation", telegramMessageId: "1",
  locale: "ja", family: "affirmation", localDay: "2026-09-18", observedAt: "2026-09-18T00:00:00Z",
};

test("decision row is closed, provenance-safe, and allows silence", () => {
  assert.deepEqual(validateDecisionRow(BASE), BASE);
  assert.deepEqual(validateDecisionRow({ ...BASE, selectedQuoteId: null, telegramMessageId: null, silenceReason: "calendar-busy" }).silenceReason, "calendar-busy");
  assert.throws(() => validateDecisionRow({ ...BASE, raw_mail_body: "secret" }), /unknown/);
  assert.equal(validateDecisionRow({ ...BASE, calendarBusy: true }).calendarBusy, true);
});

test("offline scorecard counts only observable operational violations", () => {
  const rows = [
    BASE,
    { ...BASE, telegramMessageId: "2", selectedQuoteId: "q1", observedAt: "2026-09-18T01:00:00Z" },
    { ...BASE, window: "midday_awareness", family: "mindfulness_inquiry", candidateQuoteIds: ["q2"], selectedQuoteId: "q2", telegramMessageId: "3", observedAt: "2026-09-18T04:00:00Z" },
  ];
  const score = scorePolicyRows(rows);
  assert.equal(score.delivered, 3);
  assert.equal(score.duplicate_template, 1);
  assert.equal(score.cap_overflow, 0);
  assert.equal(score.busy_send, 0);
  assert.equal(score.unsupported_locale, 0);
});

test("offline scorecard counts busy sends and unsupported locale instead of rejecting the observations", () => {
  const score = scorePolicyRows([
    { ...BASE, calendarBusy: true },
    { ...BASE, locale: "fr" },
  ]);
  assert.equal(score.busy_send, 1);
  assert.equal(score.unsupported_locale, 1);
});

test("policy comparison accepts only lower safety violations without losing material reports", () => {
  const oldRows = [{ ...BASE, telegramMessageId: "1" }, { ...BASE, telegramMessageId: "2", observedAt: "2026-09-18T01:00:00Z" }];
  const newRows = [{ ...BASE, telegramMessageId: "1" }, { ...BASE, window: "midday_awareness", family: "mindfulness_inquiry", candidateQuoteIds: ["q2"], selectedQuoteId: "q2", telegramMessageId: "2", observedAt: "2026-09-18T04:00:00Z" }];
  assert.equal(comparePolicyReplays(oldRows, newRows).promote, true);
  assert.equal(comparePolicyReplays(oldRows, [], { oldMaterialReports: 1, newMaterialReports: 0 }).promote, false);
});

test("replay fixtures cover verified outcomes, ambiguity, meeting suppression, cap, and an ordinary day", () => {
  const rows = [
    { ...BASE, sourceOutcomeId: "rejection-1", selectedQuoteId: "q-rejection", candidateQuoteIds: ["q-rejection"], telegramMessageId: "11" },
    { ...BASE, sourceOutcomeId: "offer-1", selectedQuoteId: "q-offer", candidateQuoteIds: ["q-offer"], family: "manifestation", window: "evening_direction", localDay: "2026-09-18", telegramMessageId: "12" },
    { ...BASE, sourceOutcomeId: "interview-1", selectedQuoteId: "q-interview", candidateQuoteIds: ["q-interview"], family: "affirmation", window: "morning_orientation", localDay: "2026-09-19", telegramMessageId: "13", observedAt: "2026-09-19T00:00:00Z" },
    { ...BASE, sourceOutcomeId: "ambiguous-1", selectedQuoteId: null, telegramMessageId: null, silenceReason: "outcome-not-verified" },
    { ...BASE, selectedQuoteId: null, telegramMessageId: null, silenceReason: "calendar-busy", calendarBusy: true },
    { ...BASE, selectedQuoteId: null, telegramMessageId: null, silenceReason: "daily-cap-reached", localDay: "2026-09-18" },
    { ...BASE, selectedQuoteId: null, telegramMessageId: null, silenceReason: "outside-opportunity-window", localDay: "2026-09-20", observedAt: "2026-09-20T00:00:00Z" },
  ];
  const score = scorePolicyRows(rows);
  assert.equal(score.delivered, 3);
  assert.equal(score.silence, 4);
  assert.equal(score.busy_send, 0);
  assert.equal(score.cap_overflow, 0);
});

test("local-day and fourteen-day template accounting do not use UTC day alone", () => {
  const rows = [
    { ...BASE, localDay: "2026-09-18", observedAt: "2026-09-17T15:00:00Z", telegramMessageId: "1" },
    { ...BASE, localDay: "2026-09-18", observedAt: "2026-09-18T00:00:00Z", telegramMessageId: "2" },
    { ...BASE, localDay: "2026-10-03", observedAt: "2026-10-02T15:00:00Z", telegramMessageId: "3" },
  ];
  const score = scorePolicyRows(rows);
  assert.equal(score.cap_overflow, 0);
  assert.equal(score.duplicate_template, 1);
});

test("cap overflow is counted from the explicit local day", () => {
  const rows = [1, 2, 3, 4].map((id) => ({
    ...BASE,
    selectedQuoteId: `q${id}`,
    candidateQuoteIds: [`q${id}`],
    telegramMessageId: String(id),
    localDay: "2026-09-18",
    observedAt: `2026-09-18T0${id}:00:00Z`,
  }));
  assert.equal(scorePolicyRows(rows).cap_overflow, 1);
});
