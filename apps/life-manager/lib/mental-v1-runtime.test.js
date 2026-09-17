"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { mentalV1UserOnce } = require("./mental-v1-runtime.js");

const NOW = Date.parse("2026-09-18T08:00:00+09:00");
const USER = { uid: "u1", telegram_chat_id: "7", call_time_zone: "Asia/Tokyo" };

function deps(overrides = {}) {
  const sent = [];
  const recorded = [];
  return {
    sent,
    recorded,
    base: {
      fetchUpcomingEvents: async () => [],
      readSendState: async () => ({ sentTodayCount: 0, lastSentMs: null, sentFamilies: [], recentQuoteIds: [] }),
      recordSend: async (row) => { recorded.push(row); return true; },
      sendMessage: async (_token, _chat, text) => { sent.push(text); return { ok: true, result: { message_id: 901 } }; },
      profile: { locale: "ja", themes: ["self-worth"], tones: ["gentle"], avoidThemes: [] },
      telegramToken: "tg",
      ...overrides,
    },
  };
}

test("V1 sends a plain morning catalog affirmation and records its window", async () => {
  const d = deps();
  const result = await mentalV1UserOnce(USER, NOW, d.base);
  assert.equal(result.decision, "send");
  assert.equal(result.window, "morning_orientation");
  assert.equal(result.family, "affirmation");
  assert.equal(result.delivered, true);
  assert.equal(d.sent.length, 1);
  assert.deepEqual(d.recorded, [{
    uid: "u1", trigger: "morning_orientation", family: "affirmation",
    templateId: result.templateId, localDay: "2026-09-18", window: "morning_orientation", telegramMessageId: "901",
  }]);
  assert.doesNotMatch(d.sent[0], /返信|教えて|押して|ボタン/);
});

test("V1 suppresses during a current Calendar event and never reads event story fields", async () => {
  const d = deps({
    fetchUpcomingEvents: async () => [{ startMs: NOW - 1000, endMs: NOW + 600000, summary: "private", attendees: ["x"] }],
  });
  const result = await mentalV1UserOnce(USER, NOW, d.base);
  assert.deepEqual(result, { decision: "suppress", reason: "calendar-busy" });
  assert.equal(d.sent.length, 0);
});

test("V1 fails closed on unreadable send history and missing timezone", async () => {
  const unreadable = deps({ readSendState: async () => { throw new Error("down"); } });
  assert.equal((await mentalV1UserOnce(USER, NOW, unreadable.base)).reason, "send-history-unavailable");
  const noZone = deps();
  assert.equal((await mentalV1UserOnce({ ...USER, call_time_zone: null }, NOW, noZone.base)).reason, "no-timezone");
});

test("V1 does not create a fourth message when the cap or gap is exhausted", async () => {
  const cap = deps({ readSendState: async () => ({ sentTodayCount: 3, lastSentMs: null, sentFamilies: [], recentQuoteIds: [] }) });
  assert.equal((await mentalV1UserOnce(USER, NOW, cap.base)).reason, "daily-cap-reached");
  const gap = deps({ readSendState: async () => ({ sentTodayCount: 1, lastSentMs: NOW - 1, sentFamilies: [], recentQuoteIds: [] }) });
  assert.equal((await mentalV1UserOnce(USER, NOW, gap.base)).reason, "too-soon-after-last");
});
