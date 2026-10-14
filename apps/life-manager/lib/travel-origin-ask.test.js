"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  answerTravelOriginAsk,
  askTick,
  askTravelOriginOnce,
  readTravelOriginAskState,
  travelOriginAskKey,
} = require("./ask.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const SUPA_URL = "https://db.example";
const SUPA_KEY = "fixture-service-role";
const EVENT = {
  id: "calendar-event-1",
  summary: "Dinner",
  location: "Venue",
  startIso: "2030-01-01T19:00:00+09:00",
};
const CANDIDATES = [
  { id: "home", location: "Home", source: "saved_home" },
  { id: "office", location: "MUIT 生駒", source: "repeated_calendar_location" },
];

function response(status, body = []) {
  return { ok: status >= 200 && status < 300, status, async json() { return body; } };
}

function matches(row, params) {
  for (const [key, expected] of params) {
    if (["select", "limit"].includes(key)) continue;
    const actual = key === "question_context->>replyChannel"
      ? row.question_context && row.question_context.replyChannel
      : row[key];
    if (expected === "is.null" && actual != null) return false;
    if (expected === "not.is.null" && actual == null) return false;
    if (expected.startsWith("eq.") && String(actual) !== expected.slice(3)) return false;
  }
  return true;
}

function makeAskStore() {
  const rows = [];
  const fetchImpl = async (input, init = {}) => {
    const url = new URL(String(input));
    const method = String(init.method || "GET");
    if (url.pathname !== "/rest/v1/lm_ask_log") throw new Error(`unexpected path ${url.pathname}`);
    if (method === "GET") return response(200, rows.filter((row) => matches(row, url.searchParams)));
    if (method === "POST") {
      const row = JSON.parse(init.body);
      if (rows.some((old) => old.uid === row.uid && old.event_id === row.event_id)) return response(409);
      rows.push({ asked_at: "2030-01-01T00:00:00Z", answered_at: null, ...row });
      return response(201);
    }
    const index = rows.findIndex((row) => matches(row, url.searchParams));
    if (method === "PATCH") {
      if (index < 0) return response(200, []);
      Object.assign(rows[index], JSON.parse(init.body));
      return response(200, [rows[index]]);
    }
    if (method === "DELETE") {
      if (index >= 0) rows.splice(index, 1);
      return response(204);
    }
    throw new Error(`unexpected method ${method}`);
  };
  return { rows, fetchImpl };
}

test("travel-origin ask is event-scoped, typed, and sent once on Telegram", async () => {
  const store = makeAskStore();
  const sends = [];
  const options = {
    supaUrl: SUPA_URL,
    supaKey: SUPA_KEY,
    fetchImpl: store.fetchImpl,
    telegramChatId: "12345",
    telegramToken: "fixture-bot-token",
    sendTelegram: async (_token, chatId, text) => {
      sends.push({ chatId, text });
      return { ok: true };
    },
  };

  const first = await askTravelOriginOnce(UID, EVENT, EVENT.id, CANDIDATES, options);
  const replay = await askTravelOriginOnce(UID, EVENT, EVENT.id, CANDIDATES, options);

  assert.deepEqual(first, { kind: "pending", sent: true });
  assert.deepEqual(replay, { kind: "pending", sent: false });
  assert.equal(sends.length, 1);
  assert.equal(sends[0].chatId, "12345");
  assert.match(sends[0].text, /Dinner/);
  assert.match(sends[0].text, /MUIT 生駒/);
  assert.equal(store.rows.length, 1);
  assert.equal(store.rows[0].event_id, travelOriginAskKey(EVENT.id));
  assert.notEqual(store.rows[0].event_id, EVENT.id, "the earlier Calendar-location ask row must remain intact");
  assert.equal(store.rows[0].question_type, "travel_origin");
  assert.equal(store.rows[0].question_context.calendarEventId, EVENT.id);
  assert.equal(store.rows[0].question_context.replyChannel, "telegram");
  assert.equal(store.rows[0].question_context.candidates.length, 2);
});

test("travel-origin reply stores only a whitelisted candidate for the next travel tick", async () => {
  const store = makeAskStore();
  const options = {
    supaUrl: SUPA_URL,
    supaKey: SUPA_KEY,
    fetchImpl: store.fetchImpl,
    telegramChatId: "12345",
    telegramToken: "fixture-bot-token",
    sendTelegram: async () => ({ ok: true }),
  };
  await askTravelOriginOnce(UID, EVENT, EVENT.id, CANDIDATES, options);
  const row = store.rows[0];
  const answer = await answerTravelOriginAsk(UID, row, "MUIT 生駒", {
    channel: "telegram",
    nowMs: Date.parse("2030-01-01T17:40:00+09:00"),
    matchReply: async (text, matchOptions) => {
      assert.equal(text, "MUIT 生駒");
      assert.deepEqual(matchOptions.candidates, CANDIDATES);
      return { kind: "selected", candidateId: "office", location: "MUIT 生駒" };
    },
    supaUrl: SUPA_URL,
    supaKey: SUPA_KEY,
    fetchImpl: store.fetchImpl,
  });

  assert.deepEqual(answer, { kind: "answered", location: "MUIT 生駒", event: "Dinner" });
  assert.equal(row.answered_at, "2030-01-01T08:40:00.000Z");
  assert.equal(row.answer_value, "MUIT 生駒");
  assert.equal(row.answer_source, "telegram");
  assert.deepEqual(await readTravelOriginAskState(UID, EVENT.id, {
    supaUrl: SUPA_URL, supaKey: SUPA_KEY, fetchImpl: store.fetchImpl,
  }), { kind: "answered", location: "MUIT 生駒" });
});

test("ambiguous iMessage send stays claimed and blocks a second travel-origin ask", async () => {
  const store = makeAskStore();
  const sends = [];
  const options = {
    supaUrl: SUPA_URL,
    supaKey: SUPA_KEY,
    fetchImpl: store.fetchImpl,
    imessageSenderId: "+819012345678",
    imessageSend: async (_sender, text) => {
      sends.push(text);
      return { ok: false, effectUnknown: true, reason: "timeout_after_send" };
    },
  };
  const first = await askTravelOriginOnce(UID, EVENT, EVENT.id, CANDIDATES, options);
  const next = { ...EVENT, id: "calendar-event-2", summary: "Another dinner" };
  const result = await askTravelOriginOnce(UID, next, next.id, CANDIDATES, options);

  assert.deepEqual(first, { kind: "pending", sent: false });
  assert.deepEqual(result, { kind: "pending", sent: false });
  assert.equal(sends.length, 1);
  assert.equal(store.rows.length, 1);
});

test("readTravelOriginAskState distinguishes no question, pending, and answered", async () => {
  const store = makeAskStore();
  assert.deepEqual(await readTravelOriginAskState(UID, EVENT.id, {
    supaUrl: SUPA_URL, supaKey: SUPA_KEY, fetchImpl: store.fetchImpl,
  }), { kind: "none" });
  await askTravelOriginOnce(UID, EVENT, EVENT.id, CANDIDATES, {
    supaUrl: SUPA_URL, supaKey: SUPA_KEY, fetchImpl: store.fetchImpl,
    telegramChatId: "12345", telegramToken: "fixture-bot-token",
    sendTelegram: async () => ({ ok: true }),
  });
  assert.deepEqual(await readTravelOriginAskState(UID, EVENT.id, {
    supaUrl: SUPA_URL, supaKey: SUPA_KEY, fetchImpl: store.fetchImpl,
  }), { kind: "pending" });
});

test("the location ask loop waits while a travel-origin question is pending", async () => {
  const already = new Set();
  already.pendingTravelOrigin = true;
  let resolveCalls = 0;
  const result = await askTick(UID, {
    composioKey: "fixture-composio", supaUrl: SUPA_URL, supaKey: SUPA_KEY,
    nowMs: Date.parse("2030-01-01T00:00:00Z"),
    listEvents: async () => [{ id: "event-missing-location", summary: "Lunch", location: "",
      start: { dateTime: "2030-01-01T12:00:00+09:00" } }],
    askedSet: async () => already,
    resolve: async () => { resolveCalls++; return { kind: "ask" }; },
  });

  assert.deepEqual(result, { autofilled: 0, asked: 0, resolved: 0 });
  assert.equal(resolveCalls, 0);
});
