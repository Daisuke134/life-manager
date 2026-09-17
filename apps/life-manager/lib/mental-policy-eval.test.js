"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { validateDecisionRow, scorePolicyRows, comparePolicyReplays } = require("./mental-policy-eval.js");

const BASE = {
  uid: "u1", policyVersion: "v1", profileVersion: "p1", sourceOutcomeId: null,
  candidateQuoteIds: ["q1"], selectedQuoteId: "q1", silenceReason: null,
  calendarBusy: false, window: "morning_orientation", telegramMessageId: "1",
  locale: "ja", family: "affirmation", observedAt: "2026-09-18T00:00:00Z",
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
