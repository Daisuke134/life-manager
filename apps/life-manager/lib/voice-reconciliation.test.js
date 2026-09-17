"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { reconcileStaleVoiceAllowances } = require("./voice-reconciliation.js");

const TOKEN = "11111111-1111-4111-8111-111111111111";
const row = (key) => ({ uid: "tenant-a", call_key: key, period_start: "2026-09-01",
  reservation_token: TOKEN, reserved_seconds: 120 });
const cdr = (session, overrides = {}) => ({ telnyx_session_id: session, record_type: "call-control",
  direction: "outbound", finished_at: "2026-09-17T00:00:00Z", connected: 0, completed: 0,
  call_sec: 0, billed_sec: 0, dest_number: "+99900000001", caller_number: "+99900000000",
  connection_id: "connection-a", ...overrides });

function transport(rows, records, { removeSettled = false } = {}) {
  const completions = [];
  const fetchImpl = async (input, options = {}) => {
    const url = new URL(input);
    let data;
    if (url.pathname.endsWith("/lm_voice_allowance_ledger")) {
      const offset = Number(url.searchParams.get("offset"));
      const limit = Number(url.searchParams.get("limit"));
      data = rows.slice(offset, offset + limit);
    }
    else if (url.pathname.endsWith("/lm_wake_log")) {
      const key = url.searchParams.get("event_key").slice(3);
      data = [{ telnyx_call_control_id: `control-${key}`, telnyx_call_session_id: `session-${key}` }];
    } else if (url.pathname.endsWith("/detail_records")) {
      const matches = records[url.searchParams.get("filter[telnyx_session_id]")] || [];
      data = { data: matches, meta: { total_results: matches.length } };
    } else if (url.pathname.endsWith("/complete_lm_voice_allowance")) {
      const body = JSON.parse(options.body);
      completions.push(body);
      if (removeSettled) {
        const index = rows.findIndex((item) => item.call_key === body.p_call_key);
        if (index >= 0) rows.splice(index, 1);
      }
      data = { allowed: true, usedSeconds: 0, limitSeconds: 3600, allowedSeconds: 0,
        periodStart: "2026-09-01", resetAt: "2026-10-01" };
    } else throw new Error(`unexpected request: ${url.pathname}`);
    return { ok: true, json: async () => data };
  };
  return { fetchImpl, completions };
}

const config = { supaUrl: "https://db.example", supaKey: "secret", telnyxKey: "telnyx-secret",
  nowMs: Date.parse("2026-09-17T01:00:00Z") };

test("finished zero-second and answered CDRs settle exact connected seconds through the owner RPC", async () => {
  const mock = transport([row("no-answer"), row("answered")], {
    "session-no-answer": [cdr("session-no-answer")],
    "session-answered": [cdr("session-answered", { connected: 1, completed: 1, call_sec: 37, billed_sec: 60 })],
  });
  const result = await reconcileStaleVoiceAllowances({ ...config, fetchImpl: mock.fetchImpl });
  assert.deepEqual(result, { checked: 2, settled: 2, errors: 0, nextOffset: 0 });
  assert.deepEqual(mock.completions.map((body) => body.p_connected_seconds), [0, 37]);
  assert.ok(mock.completions.every((body) => body.p_reservation_token === TOKEN));
});

test("missing, duplicate, or mismatched CDRs leave accepted reservations untouched", async () => {
  const mock = transport([row("missing"), row("duplicate"), row("wrong-session"), row("too-long")], {
    "session-duplicate": [cdr("session-duplicate"), cdr("session-duplicate")],
    "session-wrong-session": [cdr("another-session")],
    "session-too-long": [cdr("session-too-long", { connected: 1, completed: 1, call_sec: 121 })],
  });
  const result = await reconcileStaleVoiceAllowances({ ...config, fetchImpl: mock.fetchImpl });
  assert.deepEqual(result, { checked: 4, settled: 0, errors: 0, nextOffset: 0 });
  assert.equal(mock.completions.length, 0);
});

test("a failed CDR does not block later rows when settlement shrinks the page", async () => {
  const mock = transport([row("error"), row("good"), row("later")], {
    "session-good": [cdr("session-good")], "session-later": [cdr("session-later")],
  }, { removeSettled: true });
  const fetchImpl = async (input, options) => {
    const url = new URL(input);
    if (url.searchParams.get("filter[telnyx_session_id]") === "session-error") {
      return { ok: false, status: 503, json: async () => ({}) };
    }
    return mock.fetchImpl(input, options);
  };
  const first = await reconcileStaleVoiceAllowances({ ...config, fetchImpl, pageSize: 2 });
  assert.deepEqual(first, { checked: 2, settled: 1, errors: 1, nextOffset: 0 });
  const second = await reconcileStaleVoiceAllowances({ ...config, fetchImpl, pageSize: 2, offset: first.nextOffset });
  assert.deepEqual(second, { checked: 2, settled: 1, errors: 1, nextOffset: 0 });
});

test("a stuck completion RPC times out so reconciliation can run again", async () => {
  const mock = transport([row("stuck")], { "session-stuck": [cdr("session-stuck")] });
  const fetchImpl = (input, options) => {
    if (!String(input).endsWith("/complete_lm_voice_allowance")) return mock.fetchImpl(input, options);
    return new Promise((_, reject) => options.signal.addEventListener("abort", () => reject(new Error("timeout"))));
  };
  const result = await reconcileStaleVoiceAllowances({ ...config, fetchImpl, timeoutMs: 10 });
  assert.deepEqual(result, { checked: 1, settled: 0, errors: 1, nextOffset: 0 });
});

test("Telnyx rate limiting stops this batch and retries its page next time", async () => {
  const mock = transport([row("limited"), row("later")], {
    "session-later": [cdr("session-later")],
  });
  const fetchImpl = (input, options) => {
    if (new URL(input).searchParams.get("filter[telnyx_session_id]") === "session-limited") {
      return Promise.resolve({ ok: false, status: 429, json: async () => ({}) });
    }
    return mock.fetchImpl(input, options);
  };
  const result = await reconcileStaleVoiceAllowances({ ...config, fetchImpl, pageSize: 2 });
  assert.deepEqual(result, { checked: 2, settled: 0, errors: 1, nextOffset: 0 });
  assert.equal(mock.completions.length, 0);
});

test("permanently unmatched old rows do not starve newer rows", async () => {
  const mock = transport([row("old-a"), row("old-b"), row("new")], {
    "session-new": [cdr("session-new")],
  });
  const first = await reconcileStaleVoiceAllowances({ ...config, fetchImpl: mock.fetchImpl, pageSize: 2 });
  assert.deepEqual(first, { checked: 2, settled: 0, errors: 0, nextOffset: 2 });
  const second = await reconcileStaleVoiceAllowances({ ...config, fetchImpl: mock.fetchImpl,
    pageSize: 2, offset: first.nextOffset });
  assert.deepEqual(second, { checked: 1, settled: 1, errors: 0, nextOffset: 0 });
});
