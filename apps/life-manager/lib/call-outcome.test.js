"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  CALL_OUTCOMES,
  classifyCallOutcome,
} = require("./call-outcome.js");
const { recordTelnyxWakeOutcome } = require("./telnyx-receipt.js");
const migrationPath = path.join(__dirname, "../migrations/2026-09-17-lm-wake-call-outcome.sql");

test("timeout with zero connected seconds is a no-answer reminder", () => {
  assert.equal(classifyCallOutcome({ connectedSeconds: 0, hangupCause: "timeout" }), CALL_OUTCOMES.NO_ANSWER);
});

test("human or uncertain AMD is a conversation even when the call is short", () => {
  assert.equal(classifyCallOutcome({ amdResult: "human", connectedSeconds: 1 }), CALL_OUTCOMES.CONVERSATION);
  assert.equal(classifyCallOutcome({ amdResult: "not_sure", connectedSeconds: 0 }), CALL_OUTCOMES.CONVERSATION);
});

test("busy or rejected calls are dial failures", () => {
  assert.equal(classifyCallOutcome({ connectedSeconds: 0, hangupCause: "user_busy" }), CALL_OUTCOMES.DIAL_FAILED);
  assert.equal(classifyCallOutcome({ connectedSeconds: 0, hangupCause: "rejected" }), CALL_OUTCOMES.DIAL_FAILED);
});

test("positive duration without a human or terminal cause stays unknown", () => {
  assert.equal(classifyCallOutcome({ connectedSeconds: 12, hangupCause: "normal_clearing" }), null);
});

test("machine AMD is no-answer even when voicemail connected for positive seconds", () => {
  assert.equal(classifyCallOutcome({ amdResult: "machine", connectedSeconds: 120, hangupCause: "timeout" }), CALL_OUTCOMES.NO_ANSWER);
});

test("outcome RPC posts the exact tenant-scoped evidence", async () => {
  const calls = [];
  const result = await recordTelnyxWakeOutcome({
    uid: "tenant-a",
    eventKey: "event-a|10",
    claimToken: "claim-a",
    callControlId: "v2:call-a",
    callOutcome: CALL_OUTCOMES.NO_ANSWER,
    hangupCause: "timeout",
    connectedSeconds: 0,
  }, {
    supaUrl: "https://supa.example",
    supaKey: "service-role",
    fetchImpl: async (url, init) => {
      calls.push({ url: String(url), init });
      return { ok: true, status: 200, json: async () => 1 };
    },
  });
  assert.deepEqual(result, { ok: true, matched: 1 });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://supa.example/rest/v1/rpc/record_lm_wake_telnyx_outcome");
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    p_uid: "tenant-a",
    p_event_key: "event-a|10",
    p_claim_token: "claim-a",
    p_telnyx_call_control_id: "v2:call-a",
    p_call_outcome: CALL_OUTCOMES.NO_ANSWER,
    p_hangup_cause: "timeout",
    p_connected_seconds: 0,
  });
});

test("outcome RPC falls back to the existing AMD column when the new RPC is not deployed", async () => {
  const calls = [];
  const result = await recordTelnyxWakeOutcome({
    uid: "tenant-a", eventKey: "event-a|10", claimToken: "claim-a", callControlId: "v2:call-a",
    callOutcome: CALL_OUTCOMES.NO_ANSWER, hangupCause: "timeout", connectedSeconds: 0,
  }, {
    supaUrl: "https://supa.example", supaKey: "service-role",
    fetchImpl: async (url, init) => {
      calls.push({ url: String(url), init });
      if (String(url).includes("/rpc/record_lm_wake_telnyx_outcome")) {
        return { ok: false, status: 404, json: async () => ({}) };
      }
      return { ok: true, status: 200, json: async () => [{ event_key: "event-a|10" }] };
    },
  });
  assert.deepEqual(result, { ok: true, matched: 1, legacy: true });
  assert.equal(calls.length, 2);
  assert.equal(calls[1].url, "https://supa.example/rest/v1/lm_wake_miss");
  assert.equal(calls[1].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[1].init.body).uid, "tenant-a");
  assert.deepEqual(JSON.parse(calls[1].init.body).event_key, "event-a|10");
  assert.deepEqual(JSON.parse(calls[1].init.body).reason, "no_answer");
});

test("outcome RPC rejects invalid outcome without fetching", async () => {
  let fetches = 0;
  const result = await recordTelnyxWakeOutcome({
    uid: "tenant-a", eventKey: "event-a", claimToken: "claim-a", callControlId: "call-a",
    callOutcome: "answered_but_unknown",
  }, {
    supaUrl: "https://supa.example", supaKey: "service-role",
    fetchImpl: async () => { fetches += 1; throw new Error("must not fetch"); },
  });
  assert.deepEqual(result, { ok: false, matched: 0, error: "invalid_outcome" });
  assert.equal(fetches, 0);
});

test("outcome migration is bounded, tenant-owned, and replay-safe", () => {
  const sql = fs.readFileSync(migrationPath, "utf8");
  assert.match(sql, /ADD COLUMN IF NOT EXISTS call_outcome\s+text/i);
  assert.match(sql, /ADD COLUMN IF NOT EXISTS telnyx_hangup_cause\s+text/i);
  assert.match(sql, /ADD COLUMN IF NOT EXISTS telnyx_call_duration_seconds\s+integer/i);
  assert.match(sql, /CHECK\s*\(call_outcome\s+IS NULL OR call_outcome IN \('conversation', 'no_answer', 'dial_failed'\)\)/i);
  assert.match(sql, /CREATE OR REPLACE FUNCTION public\.record_lm_wake_telnyx_outcome/i);
  assert.match(sql, /uid\s*=\s*p_uid[\s\S]*event_key\s*=\s*p_event_key[\s\S]*claim_token\s*=\s*p_claim_token/i);
  assert.match(sql, /p_telnyx_call_control_id[\s\S]*telnyx_call_control_id/i);
  assert.match(sql, /call_outcome\s*=\s*CASE/i);
  assert.match(sql, /GRANT EXECUTE ON FUNCTION public\.record_lm_wake_telnyx_outcome/i);
});
