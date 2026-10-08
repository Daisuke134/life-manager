"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

let resolveIMessageReply;
try { ({ resolveIMessageReply } = require("./telegram-reply.js")); } catch {}

const uid = "lm_12345678-1234-4234-8234-123456789abc";
const senderId = "+819012345678";
const linkedUser = {
  uid,
  telegram_chat_id: null,
  web_message_imessage_sender_id: senderId,
  calendar_provider: "composio_gcal",
  calendar_connected_account_id: "cal_test_123",
  gmail_account_id: null,
  paid: true,
  plan_status: "active",
};
const event = {
  id: "event-lunch",
  summary: "Lunch with Mai",
  start: { dateTime: "2030-01-01T12:00:00+09:00" },
  location: "",
  recurringEventId: null,
};

function askRow(overrides = {}) {
  return {
    uid,
    event_id: event.id,
    reply_token: "reply_token_fixture_123",
    question_type: "calendar_location",
    question_context: { replyChannel: "imessage", summary: event.summary, start: event.start.dateTime },
    answer_value: null,
    answered_at: null,
    ...overrides,
  };
}

test("iMessage reply requires a matching linked Web sender before reading Calendar", async () => {
  assert.equal(typeof resolveIMessageReply, "function", "the iMessage reply resolver must exist");
  let calendarReads = 0;
  const result = await resolveIMessageReply(uid, senderId, "渋谷駅", {
    linkedUser: { ...linkedUser, uid: "lm_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
    pendingAsksImpl: async () => [askRow()],
    calendar: { async listEventsRaw() { calendarReads += 1; return [event]; } },
  });
  assert.equal(result.filled, false);
  assert.equal(calendarReads, 0);
});

test("iMessage free-text location reply can update only a pending asked event once", async () => {
  assert.equal(typeof resolveIMessageReply, "function", "the iMessage reply resolver must exist");
  let pending = [askRow()];
  let currentEvent = { ...event };
  const patches = [];
  const resolutions = [];
  const result = await resolveIMessageReply(uid, senderId, "渋谷駅", {
    linkedUser,
    pendingAsksImpl: async (requestedUid) => { assert.equal(requestedUid, uid); return pending; },
    calendar: {
      async listEventsRaw(requestedUid) { assert.equal(requestedUid, uid); return [{ ...currentEvent }]; },
      async patchEvent(requestedUid, patch) { assert.equal(requestedUid, uid); patches.push(patch); currentEvent = { ...currentEvent, ...patch }; return { successful: true }; },
    },
    match: async (text, candidates) => {
      assert.equal(text, "渋谷駅");
      assert.deepEqual(candidates.map((candidate) => candidate.id), [event.id]);
      return { eventId: event.id, location: "東京都渋谷区" };
    },
    markLocationAnsweredImpl: async (requestedUid, row, update) => {
      resolutions.push({ requestedUid, eventId: row.event_id, update });
      pending = [];
      return true;
    },
    remember: async () => true,
  });
  assert.deepEqual(result, { filled: true, event: event.summary, location: "東京都渋谷区" });
  assert.deepEqual(patches, [{ calendar_id: "primary", event_id: event.id, location: "東京都渋谷区" }]);
  assert.equal(resolutions.length, 1);
  const replay = await resolveIMessageReply(uid, senderId, "渋谷駅", {
    linkedUser,
    pendingAsksImpl: async () => pending,
    calendar: { async listEventsRaw() { throw new Error("a replay without a pending ask must not read Calendar"); } },
  });
  assert.equal(replay.filled, false);
  assert.equal(patches.length, 1);
});

test("iMessage online answer resolves a pending online question without a Calendar write", async () => {
  assert.equal(typeof resolveIMessageReply, "function", "the iMessage reply resolver must exist");
  const updates = [];
  const result = await resolveIMessageReply(uid, senderId, "オンライン", {
    linkedUser,
    pendingAsksImpl: async () => [askRow({ question_type: "calendar_online" })],
    calendar: { async listEventsRaw() { throw new Error("online answer needs no Calendar write"); } },
    markOnlineAnswerImpl: async (requestedUid, row, update) => { updates.push([requestedUid, row.event_id, update]); return true; },
  });
  assert.equal(result.online, true);
  assert.deepEqual(updates[0].slice(0, 2), [uid, event.id]);
  assert.equal(updates[0][2].answer_value, "online");
});

test("iMessage offline answer asks for a location and then resolves that pending follow-up", async () => {
  assert.equal(typeof resolveIMessageReply, "function", "the iMessage reply resolver must exist");
  let pending = [askRow({ question_type: "calendar_online" })];
  let currentEvent = { ...event };
  const patches = [];
  const offline = await resolveIMessageReply(uid, senderId, "対面", {
    linkedUser,
    pendingAsksImpl: async () => pending,
    markOfflineFollowupImpl: async (requestedUid, row, update) => {
      assert.equal(requestedUid, uid);
      assert.equal(row.event_id, event.id);
      assert.equal(update.answer_value, "offline");
      pending = [askRow({ question_type: "calendar_online", answer_value: "offline", question_context: { replyChannel: "imessage", summary: event.summary, awaitingLocation: true } })];
      return true;
    },
    calendar: { async listEventsRaw() { throw new Error("offline choice alone must not read Calendar"); } },
  });
  assert.equal(offline.needsLocation, true);

  const location = await resolveIMessageReply(uid, senderId, "渋谷駅", {
    linkedUser,
    pendingAsksImpl: async () => pending,
    calendar: {
      async listEventsRaw(requestedUid) { assert.equal(requestedUid, uid); return [{ ...currentEvent }]; },
      async patchEvent(requestedUid, patch) { assert.equal(requestedUid, uid); patches.push(patch); currentEvent = { ...currentEvent, ...patch }; return { successful: true }; },
    },
    match: async (_text, candidates) => ({ eventId: candidates[0].id, location: "東京都渋谷区" }),
    markLocationAnsweredImpl: async () => { pending = []; return true; },
    remember: async () => true,
  });
  assert.equal(location.filled, true);
  assert.equal(patches.length, 1);
});

test("iMessage reply with no pending ask does not access Calendar or infer an update", async () => {
  assert.equal(typeof resolveIMessageReply, "function", "the iMessage reply resolver must exist");
  let calendarReads = 0;
  const result = await resolveIMessageReply(uid, senderId, "渋谷駅", {
    linkedUser,
    pendingAsksImpl: async () => [],
    calendar: { async listEventsRaw() { calendarReads += 1; return [event]; } },
  });
  assert.equal(result.filled, false);
  assert.equal(calendarReads, 0);
});

test("iMessage reply after Web billing entitlement ends cannot read or write Calendar", async () => {
  assert.equal(typeof resolveIMessageReply, "function", "the iMessage reply resolver must exist");
  let pendingAskReads = 0;
  let calendarReads = 0;
  const result = await resolveIMessageReply(uid, senderId, "渋谷駅", {
    linkedUser: {
      ...linkedUser,
      paid: false,
      plan_status: "trialing",
      web_trial_payment_method_present: true,
      trial_expires_at: "2029-12-31T00:00:00.000Z",
    },
    nowMs: Date.parse("2030-01-01T00:00:00.000Z"),
    pendingAsksImpl: async () => { pendingAskReads += 1; return [askRow()]; },
    calendar: { async listEventsRaw() { calendarReads += 1; return [event]; } },
  });
  assert.deepEqual(result, { filled: false, reason: "billing_inactive" });
  assert.equal(pendingAskReads, 0);
  assert.equal(calendarReads, 0);
});
