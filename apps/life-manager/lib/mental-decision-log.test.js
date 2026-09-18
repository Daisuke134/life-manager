"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  DECISION_POLICY_VERSION,
  buildDecisionRow,
  recordMentalDecision,
  completeMentalDecision,
  failMentalDecision,
} = require("./mental-decision-log.js");

const SUPA = { url: "https://supa.example", key: "service" };

const BASE = {
  uid: "u1",
  policyVersion: DECISION_POLICY_VERSION,
  profileVersion: "profile-1",
  sourceOutcomeId: null,
  candidateQuoteIds: ["q1"],
  selectedQuoteId: "q1",
  silenceReason: null,
  calendarBusy: false,
  window: "morning_orientation",
  telegramMessageId: null,
  locale: "ja",
  family: "affirmation",
  localDay: "2026-09-18",
  observedAt: "2026-09-18T00:00:00.000Z",
};

test("buildDecisionRow creates a deterministic replay key and keeps provider text out", () => {
  const row = buildDecisionRow(BASE);
  assert.match(row.decisionKey, /^[0-9a-f]{64}$/);
  assert.equal(row.status, "planned");
  assert.equal(row.uid, "u1");
  assert.equal("text" in row, false);
});

test("silence decision is durable with a closed reason and no Telegram ID", async () => {
  let request;
  const result = await recordMentalDecision({
    ...BASE,
    candidateQuoteIds: [],
    selectedQuoteId: null,
    silenceReason: "calendar-busy",
    status: "silence",
  }, SUPA, async (url, init) => {
    request = { url, init };
    return { status: 201, ok: true, json: async () => [] };
  });
  assert.equal(result.recorded, true);
  assert.equal(result.duplicate, false);
  const body = JSON.parse(request.init.body);
  assert.equal(body.status, "silence");
  assert.equal(body.silence_reason, "calendar-busy");
  assert.equal(body.telegram_message_id, null);
  assert.doesNotMatch(request.init.body, /subject|body|snippet|mood|text/);
});

test("replaying the same decision key is quiet and never creates a second row", async () => {
  const result = await recordMentalDecision({ ...BASE, status: "planned" }, SUPA, async () => ({ status: 409, ok: false }));
  assert.equal(result.recorded, false);
  assert.equal(result.duplicate, true);
  assert.match(result.decisionKey, /^[0-9a-f]{64}$/);
});

test("planned decision completes once with the provider Telegram ID", async () => {
  const calls = [];
  const row = buildDecisionRow(BASE);
  const complete = await completeMentalDecision(row.decisionKey, "901", SUPA, async (url, init) => {
    calls.push({ url, init });
    return { status: 204, ok: true };
  });
  assert.equal(complete, true);
  assert.match(calls[0].url, /decision_key=eq\./);
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    status: "delivered",
    telegram_message_id: "901",
    updated_at: calls[0].init.body ? JSON.parse(calls[0].init.body).updated_at : undefined,
  });
});

test("failed provider delivery closes the decision without pretending it was sent", async () => {
  let request;
  const ok = await failMentalDecision("a".repeat(64), "telegram-send-failed", SUPA, async (url, init) => {
    request = { url, init };
    return { status: 204, ok: true };
  });
  assert.equal(ok, true);
  assert.deepEqual(JSON.parse(request.init.body), {
    status: "send_failed",
    selected_quote_id: null,
    silence_reason: "telegram-send-failed",
    telegram_message_id: null,
    updated_at: JSON.parse(request.init.body).updated_at,
  });
});
