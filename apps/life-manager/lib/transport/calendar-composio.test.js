"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { getCalendar } = require("./index.js");
const { makeComposioCalendar } = require("./calendar-composio.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const ACCOUNT_ID = "ca-selected-123";

function fixture(controlState) {
  controlState = { billingEntitled: true, ...controlState };
  const providerCalls = [];
  const controlReads = [];
  const fetchImpl = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const method = init.method || "GET";
    if (parsed.hostname === "supabase.example" && parsed.pathname.endsWith("/lm_users")) {
      return { ok: true, status: 200, json: async () => [{
        uid: UID,
        telegram_chat_id: null,
        calendar_provider: "composio_gcal",
        calendar_connected_account_id: ACCOUNT_ID,
        calendar_enable_pending: Boolean(controlState.enablePending),
      }] };
    }
    if (parsed.hostname === "supabase.example" && parsed.pathname.endsWith("/lm_panel_preferences")) {
      return { ok: true, status: 200, json: async () => [{
        daily_automation_enabled: controlState.dailyAutomationEnabled,
        calendar_disconnect_pending: controlState.disconnectPending,
      }] };
    }
    if (parsed.hostname === "backend.composio.dev") {
      providerCalls.push({ path: parsed.pathname, method, body: init.body && JSON.parse(init.body) });
      const items = parsed.pathname.endsWith("GOOGLECALENDAR_EVENTS_LIST") ? [{ id: "event-1" }] : [];
      return { ok: true, status: 200, json: async () => ({ successful: true, data: { items } }) };
    }
    throw new Error(`unexpected request: ${parsed.pathname}`);
  };
  return {
    providerCalls,
    controlReads,
    calendar: makeComposioCalendar({
      apiKey: "provider-key",
      supaUrl: "https://supabase.example",
      supaKey: "service-role-key",
      fetchImpl,
      readWebTravelControlStateImpl: async () => { controlReads.push("read"); return { ...controlState }; },
      recordCall: async () => true,
    }),
  };
}

test("Web Calendar create and patch make no provider call while paused or pending", async () => {
  for (const controlState of [
    { dailyAutomationEnabled: false, disconnectPending: false, enablePending: false },
    { dailyAutomationEnabled: true, disconnectPending: true, enablePending: false },
    { dailyAutomationEnabled: true, disconnectPending: false, enablePending: true },
  ]) {
    const f = fixture(controlState);
    const create = await f.calendar.createEvent(UID, { summary: "Travel" }, { expectedCalendarAccountId: ACCOUNT_ID });
    const patch = await f.calendar.patchEvent(UID, { eventId: "event-1" }, { expectedCalendarAccountId: ACCOUNT_ID });

    assert.equal(create.effect, "no_effect");
    assert.equal(patch.successful, false);
    assert.equal(f.providerCalls.length, 0);
    assert.equal(f.controlReads.length, 2);
  }
});

test("Web Calendar event listing remains available while automation is paused", async () => {
  const f = fixture({ dailyAutomationEnabled: false, disconnectPending: true, enablePending: false });
  const events = await f.calendar.listEventsRaw(UID, {
    timeMin: "2030-01-01T00:00:00.000Z",
    timeMax: "2030-01-08T00:00:00.000Z",
    strict: true,
    expectedCalendarAccountId: ACCOUNT_ID,
  });

  assert.deepEqual(events, [{ id: "event-1" }]);
  assert.equal(f.providerCalls.length, 1);
  assert.match(f.providerCalls[0].path, /GOOGLECALENDAR_EVENTS_LIST/);
  assert.equal(f.controlReads.length, 0);
});

test("Web first Travel write reaches the exact account only with persisted one-shot scan eligibility", async () => {
  const allowed = fixture({ dailyAutomationEnabled: false, disconnectPending: false,
    enablePending: false, initialScanAllowed: true });
  const created = await allowed.calendar.createEvent(UID, { summary: "[Travel] first value" }, {
    expectedCalendarAccountId: ACCOUNT_ID,
    allowWebInitialScan: true,
  });
  assert.equal(created.effect, "created");
  assert.equal(allowed.providerCalls.length, 1);
  assert.match(allowed.providerCalls[0].path, /GOOGLECALENDAR_CREATE_EVENT/);

  const blocked = fixture({ dailyAutomationEnabled: false, disconnectPending: false,
    enablePending: false, initialScanAllowed: false });
  const rejected = await blocked.calendar.createEvent(UID, { summary: "[Travel] first value" }, {
    expectedCalendarAccountId: ACCOUNT_ID,
    allowWebInitialScan: true,
  });
  assert.equal(rejected.effect, "no_effect");
  assert.equal(blocked.providerCalls.length, 0);

  const disconnecting = fixture({ dailyAutomationEnabled: false, disconnectPending: true,
    enablePending: false, initialScanAllowed: true });
  const fenced = await disconnecting.calendar.createEvent(UID, { summary: "[Travel] first value" }, {
    expectedCalendarAccountId: ACCOUNT_ID,
    allowWebInitialScan: true,
  });
  assert.equal(fenced.effect, "no_effect");
  assert.equal(disconnecting.providerCalls.length, 0);
});

test("Web initial scan can patch a Travel reminder only for its exact persisted one-shot account", async () => {
  const allowed = fixture({ dailyAutomationEnabled: false, disconnectPending: false,
    enablePending: false, initialScanAllowed: true });
  const result = await allowed.calendar.patchEvent(UID, {
    calendar_id: "primary", event_id: "travel-existing",
    reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
    send_updates: "none",
  }, { expectedCalendarAccountId: ACCOUNT_ID, allowWebInitialScan: true });

  assert.equal(result.successful, true);
  assert.equal(result.effect, "updated");
  assert.equal(allowed.providerCalls.length, 1);
  assert.match(allowed.providerCalls[0].path, /GOOGLECALENDAR_PATCH_EVENT/);
  assert.equal(allowed.providerCalls[0].body.user_id, UID);
  assert.equal(allowed.providerCalls[0].body.connected_account_id, ACCOUNT_ID);
  assert.deepEqual(allowed.providerCalls[0].body.arguments.reminders,
    { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] });

  const blocked = fixture({ dailyAutomationEnabled: false, disconnectPending: false,
    enablePending: false, initialScanAllowed: false });
  const rejected = await blocked.calendar.patchEvent(UID, {
    calendar_id: "primary", event_id: "travel-existing",
    reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
  }, { expectedCalendarAccountId: ACCOUNT_ID, allowWebInitialScan: true });
  assert.equal(rejected.successful, false);
  assert.equal(blocked.providerCalls.length, 0);
});

test("Web Calendar write is blocked when latest persisted billing entitlement ended", async () => {
  const f = fixture({ dailyAutomationEnabled: true, billingEntitled: false,
    disconnectPending: false, enablePending: false });
  const result = await f.calendar.createEvent(UID, { summary: "[Travel] next event" }, {
    expectedCalendarAccountId: ACCOUNT_ID,
  });
  assert.equal(result.effect, "no_effect");
  assert.equal(f.providerCalls.length, 0);
});

test("Web Travel reminder writes use Calendar proxy and verify the exact popup reminder", async () => {
  const calls = [];
  let proxyResponseStatus = "success";
  const calendar = makeComposioCalendar({
    apiKey: "provider-key",
    supaUrl: "https://supabase.example",
    supaKey: "service-role-key",
    readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: true, billingEntitled: true, disconnectPending: false, enablePending: false }),
    fetchImpl: async (url, init = {}) => {
      const parsed = new URL(String(url));
      if (parsed.hostname === "supabase.example" && parsed.pathname.endsWith("/lm_users")) {
        return { ok: true, status: 200, json: async () => [{ uid: UID, telegram_chat_id: null,
          calendar_provider: "composio_gcal", calendar_connected_account_id: ACCOUNT_ID }] };
      }
      if (parsed.hostname === "supabase.example" && parsed.pathname.endsWith("/lm_panel_preferences")) {
        return { ok: true, status: 200, json: async () => [{ daily_automation_enabled: true,
          calendar_disconnect_pending: false }] };
      }
      calls.push({ url: parsed.toString(), body: JSON.parse(init.body || "{}") });
      assert.match(parsed.pathname, /\/api\/v3\.1\/tools\/execute\/proxy$/);
      if (proxyResponseStatus === "rejected") {
        return { ok: false, status: 400, json: async () => ({ error: "invalid parameters" }) };
      }
      if (proxyResponseStatus === "ambiguous") {
        return { ok: false, status: 429, json: async () => ({ error: "rate limited" }) };
      }
      return { ok: true, status: 200, json: async () => ({
        status: 200,
        data: { id: "gcal-event-1", reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] } },
      }) };
    },
    recordCall: async () => true,
  });

  const result = await calendar.createEvent(UID, {
    summary: "[Travel] Home→Office",
    start_datetime: "2030-01-01T00:00:00",
    event_duration_minutes: 25,
    location: "Office",
    description: "Auto travel block",
    reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
    send_updates: "none",
  }, { expectedCalendarAccountId: ACCOUNT_ID });

  assert.equal(result.effect, "created");
  assert.equal(result.successful, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].body.endpoint, "https://www.googleapis.com/calendar/v3/calendars/primary/events");
  assert.equal(calls[0].body.method, "POST");
  assert.equal(calls[0].body.connected_account_id, ACCOUNT_ID);
  assert.deepEqual(calls[0].body.body.reminders, { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] });
  assert.equal(calls[0].body.parameters[0].type, "query");
  assert.equal(calls[0].body.parameters[0].value, "none");

  proxyResponseStatus = "rejected";
  const rejected = await calendar.createEvent(UID, {
    summary: "[Travel] Home→Office",
    start_datetime: "2030-01-01T00:00:00",
    event_duration_minutes: 25,
    location: "Office",
    description: "Auto travel block",
    reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
    send_updates: "none",
  }, { expectedCalendarAccountId: ACCOUNT_ID });
  assert.equal(rejected.effect, "no_effect");
  assert.equal(rejected.successful, false);
  assert.equal(calls.length, 2);

  proxyResponseStatus = "ambiguous";
  const ambiguous = await calendar.createEvent(UID, {
    summary: "[Travel] Home→Office",
    start_datetime: "2030-01-01T00:00:00",
    event_duration_minutes: 25,
    location: "Office",
    description: "Auto travel block",
    reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
    send_updates: "none",
  }, { expectedCalendarAccountId: ACCOUNT_ID });
  assert.equal(ambiguous.effect, "unknown");
  assert.equal(ambiguous.successful, false);
  assert.equal(calls.length, 3);
});

test("Composio calls with no verified unit rate are stored as unknown, not free", async () => {
  const env = new Map(["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    .map((name) => [name, process.env[name]]));
  const originalFetch = globalThis.fetch;
  const ledgerRows = [];
  process.env.SUPABASE_URL = "https://supabase.example";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "test-service-role-key";
  globalThis.fetch = async (url, init = {}) => {
    assert.equal(String(url), "https://supabase.example/rest/v1/lm_api_cost");
    ledgerRows.push(JSON.parse(init.body));
    return { ok: true, status: 201 };
  };
  try {
    const calendar = makeComposioCalendar({
      apiKey: "provider-key",
      resolveConnectedAccountId: async () => ACCOUNT_ID,
      fetchImpl: async () => ({ ok: true, status: 200,
        json: async () => ({ successful: true, data: { items: [] } }) }),
    });
    await calendar.listEventsRaw(UID, {
      timeMin: "2030-01-01T00:00:00.000Z",
      timeMax: "2030-01-08T00:00:00.000Z",
    });

    assert.equal(ledgerRows.length, 1);
    assert.equal(ledgerRows[0].est_usd, null);
    assert.equal(ledgerRows[0].meta.provider, "composio");
    assert.equal(ledgerRows[0].meta.operation, "GOOGLECALENDAR_EVENTS_LIST");
    assert.equal(ledgerRows[0].meta.actual_usd, null);
    assert.equal(ledgerRows[0].meta.billing_status, "unknown");
    assert.equal(ledgerRows[0].meta.estimate_status, "unavailable");
    assert.equal(ledgerRows[0].meta.pricing_version, null);
  } finally {
    globalThis.fetch = originalFetch;
    for (const [name, value] of env) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }
});

test("getCalendar passes the production Supabase config to real Web control reads", async () => {
  const envNames = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "LM_CAL_CACHE", "LIFE_TRANSPORT", "LIFE_CAL_TRANSPORT"];
  const previous = new Map(envNames.map((name) => [name, process.env[name]]));
  const controlState = { dailyAutomationEnabled: true, disconnectPending: false, enablePending: false };
  const providerCalls = [];
  const preferenceReads = [];
  const fetchImpl = async (input, init = {}) => {
    const url = new URL(String(input));
    if (url.hostname === "supabase.example") {
      if (url.pathname.endsWith("/lm_users")) {
        return { ok: true, status: 200, json: async () => [{
          uid: UID,
          telegram_chat_id: null,
          calendar_provider: "composio_gcal",
          calendar_connected_account_id: ACCOUNT_ID,
          web_first_travel_at: "2030-01-01T00:00:00.000Z",
          trial_expires_at: null,
          plan_status: "active",
          paid: true,
          web_billing_cancel_at_period_end: false,
          calendar_enable_pending: controlState.enablePending,
          calendar_enable_claim_id: controlState.enablePending ? "d901bdde-e5ce-4c7c-9b73-6d9f8fc24e2f" : null,
          calendar_enable_claimed_at: controlState.enablePending ? "2030-01-01T07:00:00.000Z" : null,
        }] };
      }
      if (url.pathname.endsWith("/lm_panel_preferences")) {
        preferenceReads.push({ ...controlState });
        return { ok: true, status: 200, json: async () => [{
          daily_automation_enabled: controlState.dailyAutomationEnabled,
          calendar_disconnect_pending: controlState.disconnectPending,
        }] };
      }
    }
    if (url.hostname === "backend.composio.dev") {
      providerCalls.push(url.pathname);
      return { ok: true, status: 200, json: async () => ({ successful: true, data: {} }) };
    }
    throw new Error(`unexpected request: ${url.hostname}${url.pathname}`);
  };

  Object.assign(process.env, {
    SUPABASE_URL: "https://supabase.example",
    SUPABASE_SERVICE_ROLE_KEY: "test-service-role-key",
    LM_CAL_CACHE: "off",
    LIFE_TRANSPORT: "composio",
    LIFE_CAL_TRANSPORT: "composio",
  });
  try {
    const calendar = getCalendar({
      apiKey: "provider-key",
      expectedCalendarAccountId: ACCOUNT_ID,
      fetchImpl,
      recordCall: async () => true,
    });
    const create = await calendar.createEvent(UID, { summary: "Travel" }, { expectedCalendarAccountId: ACCOUNT_ID });
    const patch = await calendar.patchEvent(UID, { eventId: "event-1" }, { expectedCalendarAccountId: ACCOUNT_ID });
    assert.equal(create.effect, "created");
    assert.equal(patch.successful, true);
    assert.deepEqual(providerCalls, [
      "/api/v3/tools/execute/GOOGLECALENDAR_CREATE_EVENT",
      "/api/v3/tools/execute/GOOGLECALENDAR_PATCH_EVENT",
    ]);

    for (const nextState of [
      { dailyAutomationEnabled: false, disconnectPending: false, enablePending: false },
      { dailyAutomationEnabled: true, disconnectPending: true, enablePending: false },
      { dailyAutomationEnabled: true, disconnectPending: false, enablePending: true },
    ]) {
      Object.assign(controlState, nextState);
      assert.equal((await calendar.createEvent(UID, { summary: "Travel" }, { expectedCalendarAccountId: ACCOUNT_ID })).effect, "no_effect");
      assert.equal((await calendar.patchEvent(UID, { eventId: "event-1" }, { expectedCalendarAccountId: ACCOUNT_ID })).successful, false);
    }
    assert.equal(providerCalls.length, 2);
    assert.equal(preferenceReads.length, 8);
  } finally {
    for (const [name, value] of previous) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }
});
