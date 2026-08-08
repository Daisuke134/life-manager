"use strict";

const { test } = require("node:test");
const assert = require("node:assert");

process.env.LM_CALL_SECRET = "unit_secret";
process.env.PUBLIC_WSS = "wss://life-call.invalid";
process.env.SUPABASE_URL = "http://supa.invalid";
process.env.SUPABASE_SERVICE_ROLE_KEY = "service-role-key";

const { wakeCallOnce, recordWakeCall } = require("../scheduler.js");

const MINUTE = 60_000;
const EVENT_START_ISO = "2026-08-06T14:00:00+09:00";
const EVENT_START_MS = Date.parse(EVENT_START_ISO);
const USER = {
  uid: "ledger-user", name: "Ledger User", phone: "+810000000000",
  home_address: "東京都渋谷区", call_language: "ja",
  daily_automation_enabled: true, call_enabled: true, notifications_enabled: false,
};
const EVENT = {
  id: "ledger-event", summary: "新宿で打ち合わせ", location: "新宿",
  startMs: EVENT_START_MS, startIso: EVENT_START_ISO,
  endMs: EVENT_START_MS + 60 * MINUTE,
};

test("the wake ledger update writes the provider call id against the claimed event", async () => {
  const requests = [];
  const result = await recordWakeCall(USER.uid, `${USER.uid}|${EVENT_START_ISO}|10`, "v2:provider-call-10", {
    fetchImpl: async (url, init) => {
      requests.push({ url: String(url), init });
      return { ok: true, status: 204 };
    },
  });
  assert.deepEqual(result, { ok: true });
  assert.equal(requests[0].init.method, "PATCH");
  assert.deepEqual(JSON.parse(requests[0].init.body), { provider_call_id: "v2:provider-call-10" });
  assert.match(requests[0].url, /event_key=eq\.ledger-user%7C2026-08-06T14%3A00%3A00%2B09%3A00%7C10/);
});

test("a successful pre-event dial persists its provider call id in the wake ledger", async () => {
  const recorded = [];
  await wakeCallOnce(USER, EVENT_START_MS - 5 * MINUTE, {
    fetchUpcomingEvents: async () => [EVENT],
    directionsMinutes: async () => 0,
    claimWake: async () => "claim-token",
    placeCall: async () => ({ ok: true, ccid: "v2:provider-call-5" }),
    recordWakeCall: async (...args) => { recorded.push(args); return { ok: true }; },
  });
  assert.deepEqual(recorded, [[USER.uid, `${USER.uid}|${EVENT_START_ISO}|5`, "v2:provider-call-5"]]);
});

test("a calendar failure records the cause instead of failing silently", async () => {
  const errors = [];
  const originalError = console.error;
  console.error = (...args) => errors.push(args.join(" "));
  try {
    await wakeCallOnce(USER, EVENT_START_MS - 5 * MINUTE, {
      fetchUpcomingEvents: async () => { throw new Error("calendar provider unavailable"); },
    });
  } finally {
    console.error = originalError;
  }
  assert.ok(errors.some((line) => /calendar provider unavailable/.test(line)));
});
