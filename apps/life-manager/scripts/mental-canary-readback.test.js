"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { evaluateCanaryRows } = require("./mental-canary-readback.js");

test("canary evaluator counts only V1 rows and enforces cap, spacing, family, and template replay", () => {
  const rows = [
    { sent_at: "2026-09-18T00:00:00Z", family: "affirmation", template_id: "q1", local_day: "2026-09-18", window: "morning_orientation", telegram_message_id: "1" },
    { sent_at: "2026-09-18T04:00:00Z", family: "mindfulness_inquiry", template_id: "q2", local_day: "2026-09-18", window: "midday_awareness", telegram_message_id: "2" },
    { sent_at: "2026-09-18T12:00:00Z", family: "manifestation", template_id: "q3", local_day: "2026-09-18", window: "evening_direction", telegram_message_id: "3" },
    { sent_at: "2026-09-17T00:00:00Z", family: "legacy", template_id: "pre_event", local_day: "2026-09-17", window: "legacy", telegram_message_id: "old" },
  ];
  const result = evaluateCanaryRows(rows, Date.parse("2026-09-18T13:00:00Z"));
  assert.equal(result.v1_count, 3);
  assert.equal(result.legacy_count, 1);
  assert.deepEqual(result.daily_counts, { "2026-09-18": 3 });
  assert.equal(result.max_daily_count, 3);
  assert.equal(result.min_gap_ms, 4 * 60 * 60 * 1000);
  assert.equal(result.family_repeats, 0);
  assert.equal(result.template_repeats, 0);
  assert.equal(result.windows.morning_orientation, 1);
  assert.equal(result.windows.midday_awareness, 1);
  assert.equal(result.windows.evening_direction, 1);
  assert.equal(result.pass, true);
});

test("canary evaluator fails duplicate family/template and over-cap days", () => {
  const rows = [
    { sent_at: "2026-09-18T00:00:00Z", family: "affirmation", template_id: "q1", local_day: "2026-09-18", window: "morning_orientation", telegram_message_id: "1" },
    { sent_at: "2026-09-18T00:10:00Z", family: "affirmation", template_id: "q1", local_day: "2026-09-18", window: "morning_orientation", telegram_message_id: "2" },
    { sent_at: "2026-09-18T00:20:00Z", family: "mindfulness_inquiry", template_id: "q2", local_day: "2026-09-18", window: "midday_awareness", telegram_message_id: "3" },
    { sent_at: "2026-09-18T00:30:00Z", family: "manifestation", template_id: "q3", local_day: "2026-09-18", window: "evening_direction", telegram_message_id: "4" },
  ];
  const result = evaluateCanaryRows(rows, Date.parse("2026-09-18T01:00:00Z"));
  assert.equal(result.pass, false);
  assert.equal(result.max_daily_count, 4);
  assert.equal(result.family_repeats, 1);
  assert.equal(result.template_repeats, 1);
  assert.equal(result.min_gap_ms, 10 * 60 * 1000);
});

test("canary evaluator does not call an empty natural canary a pass", () => {
  assert.equal(evaluateCanaryRows([], Date.now()).pass, false);
});
