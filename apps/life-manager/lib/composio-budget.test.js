"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { ComposioBudgetGuard, intervalForCount } = require("./composio-budget.js");
const { makeComposioCalendar } = require("./transport/calendar-composio.js");

test("Composio budget boundaries: alert at 18,000 and soft-degrade only at 19,500", () => {
  assert.deepEqual(intervalForCount(17999), { alert: false, intervalMs: 60000 });
  assert.deepEqual(intervalForCount(18000), { alert: true, intervalMs: 60000 });
  assert.deepEqual(intervalForCount(19499), { alert: true, intervalMs: 60000 });
  assert.deepEqual(intervalForCount(19500), { alert: true, intervalMs: 300000 });
});

test("Composio admin alert is throttled for six hours", async () => {
  const sent = [];
  const guard = new ComposioBudgetGuard({ sendAlert: async (count) => sent.push(count) });
  await guard.update(18000, 0);
  await guard.update(19000, 6 * 60 * 60 * 1000 - 1);
  await guard.update(19001, 6 * 60 * 60 * 1000);
  assert.deepEqual(sent, [18000, 19001]);
});

test("Composio soft-degrade recovers when the monthly count resets", async () => {
  const guard = new ComposioBudgetGuard({ sendAlert: async () => {} });
  assert.equal((await guard.update(19500, 0)).intervalMs, 300000);
  assert.equal((await guard.update(0, 1)).intervalMs, 60000);
});

test("Composio success records managed trace without changing the request or return value", async () => {
  const original = global.fetch;
  const requests = [];
  const records = [];
  global.fetch = async (url, options) => {
    requests.push({ url, options });
    return { json: async () => ({ successful: true, data: { items: [] } }) };
  };
  try {
    const calendar = makeComposioCalendar({
      apiKey: "k",
      runtimeEnv: {
        LIFE_MANAGER_LOOP_ID: "managed-calendar-loop",
        LIFE_MANAGER_OWNER_ID: "managed-calendar-owner",
        LIFE_MANAGER_RUN_ID: "managed-run-1",
        LIFE_MANAGER_OCCURRENCE_ID: "managed-calendar-loop:managed-occurrence-1",
        LIFE_MANAGER_RELEASE_SHA: "a".repeat(40),
        RAILWAY_SERVICE_NAME: "life-call",
        RAILWAY_GIT_COMMIT_SHA: "b".repeat(40),
      },
      recordCall: async (uid, tool, trace) => records.push({ uid, tool, trace }),
    });
    assert.deepEqual(await calendar.listEventsRaw("u1", {}), []);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, "https://backend.composio.dev/api/v3/tools/execute/GOOGLECALENDAR_EVENTS_LIST");
    assert.equal(requests[0].options.method, "POST");
    assert.deepEqual(JSON.parse(requests[0].options.body), {
      user_id: "u1",
      arguments: { calendarId: "primary", singleEvents: true, orderBy: "startTime" },
    });
    assert.deepEqual(records, [{
      uid: "u1",
      tool: "GOOGLECALENDAR_EVENTS_LIST",
      trace: {
        outcome: "success",
        runtimeTrace: {
          schema_version: 1,
          status: "linked",
          tenant_id: "u1",
          loop_id: "managed-calendar-loop",
          owner_id: "managed-calendar-owner",
          run_id: "managed-run-1",
          occurrence_id: "managed-calendar-loop:managed-occurrence-1",
          release_sha: "a".repeat(40),
        },
      },
    }]);
    const resilient = makeComposioCalendar({ apiKey: "k", recordCall: async () => { throw new Error("ledger down"); } });
    assert.deepEqual(await resilient.listEventsRaw("u1", {}), []);
  } finally { global.fetch = original; }
});

test("life-call fallback creates unique owner-prefixed traces only when managed context is absent", async () => {
  const original = global.fetch;
  const records = [];
  global.fetch = async () => ({ json: async () => ({ successful: true, data: { items: [] } }) });
  try {
    const calendar = makeComposioCalendar({
      apiKey: "k",
      runtimeEnv: { RAILWAY_SERVICE_NAME: "life-call", RAILWAY_GIT_COMMIT_SHA: "c".repeat(40) },
      recordCall: async (uid, tool, trace) => records.push(trace),
    });
    await calendar.listEventsRaw("u1", {});
    await calendar.listEventsRaw("u1", {});

    assert.equal(records.length, 2);
    for (const { runtimeTrace } of records) {
      assert.equal(runtimeTrace.status, "partial");
      assert.equal(runtimeTrace.owner_id, "life-call-calendar");
      assert.equal(runtimeTrace.release_sha, "c".repeat(40));
      assert.equal(Object.hasOwn(runtimeTrace, "loop_id"), false);
      assert.deepEqual(runtimeTrace.missing_fields, ["loop_id"]);
      assert.match(runtimeTrace.occurrence_id, /^life-call-calendar:/);
    }
    assert.notEqual(records[0].runtimeTrace.run_id, records[1].runtimeTrace.run_id);
    assert.notEqual(records[0].runtimeTrace.occurrence_id, records[1].runtimeTrace.occurrence_id);
  } finally { global.fetch = original; }
});

test("partial managed context is not completed from Railway and other services stay unlinked", async () => {
  const original = global.fetch;
  const records = [];
  global.fetch = async () => ({ json: async () => ({ successful: true, data: { items: [] } }) });
  try {
    const partialManaged = makeComposioCalendar({
      apiKey: "k",
      runtimeEnv: {
        LIFE_MANAGER_LOOP_ID: "managed-loop",
        RAILWAY_SERVICE_NAME: "life-call",
        RAILWAY_GIT_COMMIT_SHA: "d".repeat(40),
      },
      recordCall: async (uid, tool, trace) => records.push(trace.runtimeTrace),
    });
    const otherService = makeComposioCalendar({
      apiKey: "k",
      runtimeEnv: { RAILWAY_SERVICE_NAME: "unrelated-service", RAILWAY_GIT_COMMIT_SHA: "e".repeat(40) },
      recordCall: async (uid, tool, trace) => records.push(trace.runtimeTrace),
    });
    await partialManaged.listEventsRaw("u1", {});
    await otherService.listEventsRaw("u1", {});

    assert.deepEqual(records[0], {
      schema_version: 1,
      status: "partial",
      tenant_id: "u1",
      loop_id: "managed-loop",
      owner_id: "managed-loop",
      missing_fields: ["run_id", "occurrence_id", "release_sha"],
    });
    assert.deepEqual(records[1], {
      schema_version: 1,
      status: "unlinked",
      tenant_id: "u1",
      missing_fields: ["loop_id", "owner_id", "run_id", "occurrence_id", "release_sha"],
    });
  } finally { global.fetch = original; }
});

test("Composio outcome follows the API successful flag and excludes Calendar contents", async () => {
  const original = global.fetch;
  const responses = [
    { successful: true, data: { items: [{ id: "event-1", summary: "private calendar title" }] } },
    { successful: false, error: "provider rejected operation" },
    { data: { opaque: true } },
  ];
  const records = [];
  let call = 0;
  global.fetch = async () => ({ json: async () => responses[call++] });
  try {
    const calendar = makeComposioCalendar({
      apiKey: "k",
      runtimeEnv: {},
      recordCall: async (uid, tool, trace) => records.push({ tool, trace }),
    });
    assert.deepEqual(await calendar.listEventsRaw("u1", {}), [{ id: "event-1", summary: "private calendar title" }]);
    assert.deepEqual(await calendar.createEvent("u1", {}), responses[1]);
    assert.deepEqual(await calendar.patchEvent("u1", {}), responses[2]);
    assert.deepEqual(records.map(({ trace }) => trace.outcome), ["success", "failure", "unknown"]);
    assert.equal(JSON.stringify(records).includes("private calendar title"), false);
    assert.equal(JSON.stringify(records).includes("provider rejected operation"), false);
  } finally { global.fetch = original; }
});

test("a post-response parsing exception records unknown and keeps the existing non-fatal result", async () => {
  const original = global.fetch;
  const records = [];
  global.fetch = async () => ({ json: async () => { throw new Error("response body unavailable"); } });
  try {
    const calendar = makeComposioCalendar({
      apiKey: "k",
      runtimeEnv: {},
      recordCall: async (uid, tool, trace) => records.push(trace),
    });
    assert.deepEqual(await calendar.patchEvent("u1", {}), { successful: false });
    assert.equal(records.length, 1);
    assert.equal(records[0].outcome, "unknown");
  } finally { global.fetch = original; }
});

test("default recordCost row persists Composio outcome and runtime trace in meta", async () => {
  const originalFetch = global.fetch;
  const originalSupaUrl = process.env.SUPABASE_URL;
  const originalSupaKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  const requests = [];
  global.fetch = async (url, options) => {
    requests.push({ url: String(url), options });
    return { ok: true, json: async () => ({ successful: true, data: { items: [] } }) };
  };
  process.env.SUPABASE_URL = "https://supa.test";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "fake-test-role-key";
  try {
    const calendar = makeComposioCalendar({
      apiKey: "fake-composio-key",
      resolveConnectedAccountId: async () => null,
      runtimeEnv: {
        LIFE_MANAGER_LOOP_ID: "ledger-calendar-loop",
        LIFE_MANAGER_OWNER_ID: "ledger-calendar-owner",
        LIFE_MANAGER_RUN_ID: "ledger-run-1",
        LIFE_MANAGER_OCCURRENCE_ID: "ledger-calendar-loop:ledger-occurrence-1",
        LIFE_MANAGER_RELEASE_SHA: "f".repeat(40),
      },
    });
    assert.deepEqual(await calendar.listEventsRaw("u1", {}), []);
    assert.deepEqual(requests.map(({ url }) => url), [
      "https://backend.composio.dev/api/v3/tools/execute/GOOGLECALENDAR_EVENTS_LIST",
      "https://supa.test/rest/v1/lm_api_cost",
    ]);
    assert.equal(requests[1].options.method, "POST");
    assert.deepEqual(JSON.parse(requests[1].options.body), {
      uid: "u1",
      kind: "composio_call",
      quantity: 1,
      unit: "call",
      est_usd: 0,
      meta: {
        tool: "GOOGLECALENDAR_EVENTS_LIST",
        outcome: "success",
        runtime_trace: {
          schema_version: 1,
          status: "linked",
          tenant_id: "u1",
          loop_id: "ledger-calendar-loop",
          owner_id: "ledger-calendar-owner",
          run_id: "ledger-run-1",
          occurrence_id: "ledger-calendar-loop:ledger-occurrence-1",
          release_sha: "f".repeat(40),
        },
      },
    });
  } finally {
    global.fetch = originalFetch;
    if (originalSupaUrl === undefined) delete process.env.SUPABASE_URL;
    else process.env.SUPABASE_URL = originalSupaUrl;
    if (originalSupaKey === undefined) delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    else process.env.SUPABASE_SERVICE_ROLE_KEY = originalSupaKey;
  }
});
