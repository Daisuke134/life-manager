"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { getCalendar } = require("./index.js");
const { makeComposioCalendar } = require("./calendar-composio.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const ACCOUNT_ID = "ca-selected-123";

function fixture(controlState) {
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
          calendar_enable_pending: controlState.enablePending,
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
