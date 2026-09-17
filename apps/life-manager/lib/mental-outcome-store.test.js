"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { readOutcomeSendState, recordOutcomeSend } = require("./mental-outcome-store.js");

const SUPA = { url: "https://supabase.example", key: "service" };
const ROW = { uid: "u1", sourceOutcomeId: "gmail:1", evidenceRef: "gmail-message://1", quoteId: "q1", telegramMessageId: "tg-1" };

test("outcome send store reads dedupe state without exposing raw mail", async () => {
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(url);
    return { ok: true, json: async () => [
      { source_outcome_id: "gmail:1", sent_at: "2026-09-17T02:00:00.000Z" },
      { source_outcome_id: "gmail:2", sent_at: "2026-09-17T01:00:00.000Z" },
    ] };
  };
  const result = await readOutcomeSendState("u1", Date.parse("2026-09-17T03:00:00.000Z"), SUPA, fetchImpl);
  assert.deepEqual(result.sentOutcomeIds, ["gmail:1", "gmail:2"]);
  assert.equal(result.sentTodayCount, 2);
  assert.match(calls[0], /select=source_outcome_id,sent_at/);
  assert.doesNotMatch(calls[0], /body|subject|snippet/);
});

test("outcome send store appends only structured provenance", async () => {
  let request;
  const fetchImpl = async (url, init) => { request = { url, init }; return { status: 201, ok: true }; };
  assert.equal(await recordOutcomeSend(ROW, SUPA, fetchImpl), true);
  const body = JSON.parse(request.init.body);
  assert.deepEqual(body, {
    uid: "u1", source_outcome_id: "gmail:1", evidence_ref: "gmail-message://1",
    quote_id: "q1", telegram_message_id: "tg-1",
  });
  assert.doesNotMatch(request.init.body, /subject|body|snippet/);
});

test("outcome send store fails closed on unavailable Supabase", async () => {
  assert.deepEqual(await readOutcomeSendState("u1", Date.now(), null, async () => ({ ok: true })), {
    sentOutcomeIds: [], sentTodayCount: 0, lastSentMs: null,
  });
  assert.equal(await recordOutcomeSend(ROW, null, async () => ({ status: 201 })), false);
});

test("strict outcome state lookup throws instead of permitting a duplicate", async () => {
  await assert.rejects(
    readOutcomeSendState("u1", Date.now(), SUPA, async () => ({ ok: false, status: 503 }), { strict: true }),
    /outcome send state lookup failed/,
  );
});
