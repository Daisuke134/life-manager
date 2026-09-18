"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { mentalV1UserOnce, normalizeQuietHours } = require("./mental-v1-runtime.js");

const NOW = Date.parse("2026-09-18T08:00:00+09:00");
const USER = { uid: "u1", telegram_chat_id: "7", call_time_zone: "Asia/Tokyo" };

test("quiet-hours source accepts only a complete bounded per-user pair", () => {
  assert.deepEqual(normalizeQuietHours({ mental_quiet_start_minute: 22 * 60, mental_quiet_end_minute: 7 * 60 }), { start: 1320, end: 420 });
  assert.equal(normalizeQuietHours({ mental_quiet_start_minute: null, mental_quiet_end_minute: null }), null);
  assert.equal(normalizeQuietHours({ mental_quiet_start_minute: 22 * 60 }), null);
  assert.equal(normalizeQuietHours({ mental_quiet_start_minute: -1, mental_quiet_end_minute: 420 }), null);
});

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

test("V1 persists a planned decision and completes it with the Telegram receipt", async () => {
  const decisions = [];
  const completions = [];
  const d = deps({
    recordDecision: async (row) => {
      decisions.push(row);
      return { recorded: true, duplicate: false, decisionKey: "a".repeat(64) };
    },
    completeDecision: async (key, messageId) => {
      completions.push({ key, messageId });
      return true;
    },
  });
  const result = await mentalV1UserOnce(USER, NOW, d.base);
  assert.equal(result.delivered, true);
  assert.equal(decisions.length, 1);
  assert.equal(decisions[0].status, "planned");
  assert.equal(decisions[0].selectedQuoteId, result.templateId);
  assert.deepEqual(completions, [{ key: "a".repeat(64), messageId: "901" }]);
});

test("V1 persists an in-window silence decision without sending", async () => {
  const decisions = [];
  const d = deps({
    fetchUpcomingEvents: async () => [{ startMs: NOW - 1000, endMs: NOW + 600000 }],
    recordDecision: async (row) => {
      decisions.push(row);
      return { recorded: true, duplicate: false, decisionKey: "b".repeat(64) };
    },
  });
  const result = await mentalV1UserOnce(USER, NOW, d.base);
  assert.equal(result.reason, "calendar-busy");
  assert.equal(decisions.length, 1);
  assert.equal(decisions[0].status, "silence");
  assert.equal(decisions[0].silenceReason, "calendar-busy");
  assert.equal(d.sent.length, 0);
});

test("V1 suppresses during a current Calendar event and never reads event story fields", async () => {
  const d = deps({
    fetchUpcomingEvents: async () => [{ startMs: NOW - 1000, endMs: NOW + 600000, summary: "private", attendees: ["x"] }],
  });
  const result = await mentalV1UserOnce(USER, NOW, d.base);
  assert.equal(result.decision, "suppress");
  assert.equal(result.reason, "calendar-busy");
  assert.equal(result.window, "morning_orientation");
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

test("V1 canary allowlist suppresses every tenant outside the explicit UID set", async () => {
  const d = deps({ allowedUids: ["another-user"] });
  const result = await mentalV1UserOnce(USER, NOW, d.base);
  assert.deepEqual(result, { decision: "suppress", reason: "mental-v1-not-allowlisted" });
  assert.equal(d.sent.length, 0);
});

test("V1 reads explicit profile tags before selecting catalog text", async () => {
  const d = deps({ readProfile: async () => ({ themes: ["courage"], tones: ["gentle"], avoidThemes: [], goals: [], weights: { courage: 1 } }) });
  const result = await mentalV1UserOnce(USER, NOW, d.base);
  assert.equal(result.templateId, "antara:courage-quiet:ja");
});

test("V1 stops routine delivery when the trusted safety owner declares imminent self-harm", async () => {
  const d = deps({ safetyVerdict: "imminent_self_harm" });
  const result = await mentalV1UserOnce(USER, NOW, d.base);
  assert.deepEqual(result, { decision: "suppress", reason: "explicit-imminent-self-harm" });
  assert.equal(d.sent.length, 0);
});
