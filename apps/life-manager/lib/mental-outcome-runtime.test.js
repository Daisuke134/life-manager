"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { handleVerifiedOutcome } = require("./mental-outcome-runtime.js");

const NOW = Date.parse("2026-09-17T12:00:00+09:00");
const OUTCOME = {
  sourceOutcomeId: "gmail:msg-1", kind: "rejection", company: "Example社",
  role: "Software Engineer", verifiedAt: NOW - 10 * 60_000,
  evidenceRef: "gmail-message://msg-1",
};

function deps(overrides = {}) {
  const sent = [];
  const recorded = [];
  return {
    sent,
    recorded,
    base: {
      user: { uid: "u1", telegram_chat_id: "7" },
      nowMs: NOW,
      calendarBusy: false,
      sentTodayCount: 0,
      lastSentMs: null,
      sentOutcomeIds: [],
      profile: { locale: "ja", themes: ["self-worth"], tones: ["gentle"], avoidThemes: [] },
      telegramToken: "tg",
      sendMessage: async (_token, _chat, text) => { sent.push(text); return { ok: true, result: { message_id: "tg-1" } }; },
      recordOutcomeSend: async (row) => { recorded.push(row); return true; },
      ...overrides,
    },
  };
}

test("verified outcome sends only the selected catalog text and records provenance", async () => {
  const d = deps();
  const result = await handleVerifiedOutcome(OUTCOME, d.base);
  assert.equal(result.decision, "send");
  assert.equal(result.delivered, true);
  assert.equal(d.sent.length, 1);
  assert.equal(d.sent[0], "今の自分で、十分だよ。");
  assert.deepEqual(d.recorded, [{
    uid: "u1", sourceOutcomeId: "gmail:msg-1", evidenceRef: "gmail-message://msg-1",
    quoteId: "antara:enough-now:ja", telegramMessageId: "tg-1",
  }]);
});

test("suppressed outcome sends and records nothing", async () => {
  const d = deps({ calendarBusy: true });
  const result = await handleVerifiedOutcome(OUTCOME, d.base);
  assert.deepEqual(result, { decision: "suppress", reason: "calendar-busy" });
  assert.equal(d.sent.length, 0);
  assert.equal(d.recorded.length, 0);
});

test("Telegram failure does not record a mental outcome send", async () => {
  const d = deps({ sendMessage: async () => ({ ok: false }) });
  const result = await handleVerifiedOutcome(OUTCOME, d.base);
  assert.equal(result.decision, "send");
  assert.equal(result.delivered, false);
  assert.equal(d.recorded.length, 0);
});
