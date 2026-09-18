"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { readMentalSendState, recordMentalSend } = require("./mental-send-log.js");

const SUPA = { url: "https://supa.example", key: "service" };

test("V1 send state reads family, template, and window receipts", async () => {
  const calls = [];
  const state = await readMentalSendState("u1", Date.parse("2026-09-18T12:00:00Z"), SUPA, async (url) => {
    calls.push(url);
    return { ok: true, json: async () => [
      { sent_at: "2026-09-18T10:00:00Z", family: "affirmation", template_id: "q1", window: "morning_orientation" },
      { sent_at: "2026-09-17T10:00:00Z", family: "mindfulness_inquiry", template_id: "q2", window: "midday_awareness" },
    ] };
  }, { strict: true });
  assert.equal(state.sentTodayCount, 1);
  assert.equal(state.lastSentMs, Date.parse("2026-09-18T10:00:00Z"));
  assert.deepEqual(state.sentFamilies.sort(), ["affirmation"]);
  assert.deepEqual(state.recentQuoteIds.sort(), ["q1", "q2"]);
  assert.match(calls[0], /family,template_id,local_day,window/);
});

test("V1 keeps a fourteen-day template history separate from the rolling cap", async () => {
  const nowMs = Date.parse("2026-09-19T12:00:00Z");
  const state = await readMentalSendState("u1", nowMs, SUPA, async (url) => {
    assert.match(url, /sent_at=gte\./);
    return { ok: true, json: async () => [
      { sent_at: "2026-09-19T10:00:00Z", family: "affirmation", template_id: "today", window: "morning_orientation" },
      { sent_at: "2026-09-18T10:00:00Z", family: "affirmation", template_id: "yesterday", window: "morning_orientation" },
      { sent_at: "2026-09-05T10:00:00Z", family: "affirmation", template_id: "expired", window: "morning_orientation" },
    ] };
  }, { strict: true });
  assert.equal(state.sentTodayCount, 1);
  assert.deepEqual(state.recentQuoteIds.sort(), ["today", "yesterday"]);
});

test("V1 send receipt persists only structured metadata", async () => {
  let request;
  const ok = await recordMentalSend("u1", {
    trigger: "morning_orientation", family: "affirmation", templateId: "q1",
    localDay: "2026-09-18", window: "morning_orientation",
  }, 42, SUPA, async (url, init) => { request = { url, init }; return { status: 201 }; });
  assert.equal(ok, true);
  assert.deepEqual(JSON.parse(request.init.body), {
    uid: "u1", trigger: "morning_orientation", family: "affirmation", template_id: "q1",
    local_day: "2026-09-18", window: "morning_orientation", telegram_message_id: "42",
  });
  assert.doesNotMatch(request.init.body, /body|subject|snippet|mood/);
});

test("strict V1 history fails closed when the store is unreadable", async () => {
  await assert.rejects(
    readMentalSendState("u1", Date.now(), SUPA, async () => ({ ok: false, status: 503 }), { strict: true }),
    /mental send state lookup failed/,
  );
});
