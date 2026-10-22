"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { getCalendar } = require("./index.js");
const { makeComposioCalendar } = require("./calendar-composio.js");
const { fillTravel } = require("../travel.js");
const { createHash } = require("node:crypto");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const ACCOUNT_ID = "ca-selected-123";

function durableUpdateFixture(uid = "hybrid-update-fixture") {
  const accountHash = createHash("sha256").update(JSON.stringify([uid, ACCOUNT_ID])).digest("hex");
  const state = { uid, writes: [], dispatches: [], ledger: [], stages: [],
    user: { uid, telegram_chat_id: uid === UID ? null : 123,
      calendar_provider: "composio_gcal", calendar_connected_account_id: ACCOUNT_ID },
    account: { id: ACCOUNT_ID, user_id: uid, toolkit_slug: "googlecalendar", status: "ACTIVE" },
    controls: { dailyAutomationEnabled: true, billingEntitled: true, disconnectPending: false, enablePending: false },
    response: { ok: true, status: 200, body: { status: 200, data: { id: "travel-helper-1" } } },
    args: { calendar_id: "primary", event_id: "travel-helper-1", summary: "[Travel] changed",
      start: { dateTime: "2030-01-01T09:30:00Z", timeZone: "UTC" },
      end: { dateTime: "2030-01-01T10:00:00Z", timeZone: "UTC" }, location: "Fixture venue",
      description: "original marker must survive", reminders: { useDefault: true }, attendees: [] },
  };
  state.options = { expectedEtag: '"etag-before"',
    ...(uid === UID ? { expectedCalendarAccountId: ACCOUNT_ID } : {}),
    travelWriteContext: { schema_version: 1, request_id: "1".repeat(64), marker_request_id: "2".repeat(64),
      source_event_hash: "3".repeat(64), source_event_version: "4".repeat(64), request_fingerprint: "5".repeat(64),
      prior_request_fingerprint: "6".repeat(64), account_ref_hash: accountHash, provider_event_id: "travel-helper-1",
      leg: "go", phase: "dispatching", command: "calendar.update", effect: "unknown", retryable: false,
      runtime_trace: { schema_version: 1, status: "unlinked" } },
    beforeDispatch: async (details) => { state.stages.push("dispatch"); state.dispatches.push(details); return true; },
  };
  state.calendar = makeComposioCalendar({ apiKey: "fixture-key", supaUrl: "https://supabase.example", supaKey: "fixture-service",
    readWebTravelControlStateImpl: async () => state.controls,
    recordCall: async (_uid, tool, details) => { state.ledger.push({ tool, ...details }); return true; },
    fetchImpl: async (input, init = {}) => {
      const url = new URL(String(input));
      if (url.hostname === "supabase.example") {
        assert.equal(init.method || "GET", "GET");
        if (uid !== UID) assert.equal(url.searchParams.has("telegram_chat_id"), false);
        return { ok: true, json: async () => state.user ? [state.user] : [] };
      }
      if (url.pathname.includes("/connected_accounts/")) {
        state.stages.push("account");
        return { ok: true, json: async () => state.account };
      }
      state.stages.push("provider");
      state.writes.push({ url: String(url), method: init.method, body: JSON.parse(init.body) });
      if (state.response.transportError) throw new Error("private transport detail");
      return { ok: state.response.ok, status: state.response.status, json: async () => {
        if (state.response.unreadable) throw new Error("private response detail");
        return state.response.body;
      } };
    },
  });
  state.patch = () => state.calendar.patchEvent(uid, state.args, state.options);
  return state;
}

test("durable Travel update PATCH preserves the helper marker and waits for owned readback", async (t) => {
  for (const uid of ["hybrid-update-fixture", UID]) await t.test(uid === UID ? "Web return" : "Hybrid go", async () => {
    const f = durableUpdateFixture(uid);
    if (uid === UID) f.options.travelWriteContext.leg = "return";
    const result = await f.patch();
    assert.equal(result.effect, "unknown");
    assert.equal(result.successful, false);
    assert.deepEqual(f.stages, ["account", "dispatch", "provider"]);
    assert.deepEqual(f.dispatches, [{ account_ref_hash: f.options.travelWriteContext.account_ref_hash, command: "calendar.update" }]);
    assert.deepEqual(f.writes, [{ url: "https://backend.composio.dev/api/v3.1/tools/execute/proxy", method: "POST", body: {
      user_id: uid, connected_account_id: ACCOUNT_ID,
      endpoint: "https://www.googleapis.com/calendar/v3/calendars/primary/events/travel-helper-1", method: "PATCH",
      parameters: [{ name: "If-Match", value: '"etag-before"', type: "header" },
        { name: "sendUpdates", value: "none", type: "query" }],
      body: { summary: "[Travel] changed", start: f.args.start, end: f.args.end, location: "Fixture venue" },
    } }]);
    assert.equal(result.writeReceipt.command, "calendar.update");
    assert.equal(result.writeReceipt.phase, "response");
    assert.equal(result.writeReceipt.provider_event_id, "travel-helper-1");
    assert.equal(result.writeReceipt.next_action, "owned_readback");
    assert.equal(result.writeReceipt.retryable, false);
    assert.equal(f.ledger[0].outcome, "unknown");
    assert.equal(f.ledger[0].travelWrite.marker_request_id, "2".repeat(64));
    assert.equal(f.ledger[0].travelWrite.prior_request_fingerprint, "6".repeat(64));
  });
});

test("durable Travel update rejects unsafe etags and receipt inputs before dispatch", async (t) => {
  const scenarios = [
    ["missing etag", f => { delete f.options.expectedEtag; }],
    ["empty etag", f => { f.options.expectedEtag = ""; }],
    ["wildcard etag", f => { f.options.expectedEtag = "*"; }],
    ["header injection", f => { f.options.expectedEtag = '"etag"\r\nInjected: true'; }],
    ["different helper", f => { f.options.travelWriteContext.provider_event_id = "other-helper"; }],
    ["invalid helper", f => { f.args.event_id = "../other"; f.options.travelWriteContext.provider_event_id = "../other"; }],
    ["missing account hash", f => { delete f.options.travelWriteContext.account_ref_hash; }],
    ["wrong command", f => { f.options.travelWriteContext.command = "calendar.create"; }],
    ["old effect", f => { f.options.travelWriteContext.effect = "verified"; }],
    ["invalid request", f => { f.options.travelWriteContext.request_id = "private source detail"; }],
    ["missing marker", f => { delete f.options.travelWriteContext.marker_request_id; }],
    ["invalid prior fingerprint", f => { f.options.travelWriteContext.prior_request_fingerprint = "not-a-hash"; }],
    ["reused marker", f => { f.options.travelWriteContext.marker_request_id = f.options.travelWriteContext.request_id; }],
    ["missing callback", f => { delete f.options.beforeDispatch; }],
    ["missing context", f => { delete f.options.travelWriteContext; }],
  ];
  for (const [name, change] of scenarios) await t.test(name, async () => {
    const f = durableUpdateFixture();
    change(f);
    const result = await f.patch();
    assert.equal(result.successful, false);
    assert.equal(f.writes.length, 0);
    assert.equal(f.dispatches.length, 0);
    assert.equal(JSON.stringify(f.ledger).includes("private"), false);
  });
});

test("durable Travel update revalidates tenant ACTIVE account and existing Web controls", async (t) => {
  const scenarios = [
    ["missing binding", f => { f.user = null; }],
    ["changed binding", f => { f.user.calendar_connected_account_id = "ca-other"; }],
    ["changed hash", f => { f.options.travelWriteContext.account_ref_hash = "a".repeat(64); }],
    ["other tenant", f => { f.account.user_id = "other-owner"; }],
    ["inactive", f => { f.account.status = "EXPIRED"; }],
    ["Web pause", f => { f.controls.dailyAutomationEnabled = false; }],
    ["Web Telegram row", f => { f.user.telegram_chat_id = 123; }],
  ];
  for (const [name, change] of scenarios) await t.test(name, async () => {
    const f = durableUpdateFixture(name.startsWith("Web") ? UID : undefined);
    change(f);
    assert.equal((await f.patch()).effect, "no_effect");
    assert.equal(f.writes.length, 0);
    assert.equal(f.dispatches.length, 0);
  });
});

test("durable Travel update requires a successful durable dispatch callback", async (t) => {
  for (const throws of [false, true]) await t.test(throws ? "callback throws" : "CAS lost", async () => {
    const f = durableUpdateFixture();
    f.options.beforeDispatch = async () => { if (throws) throw new Error("private CAS detail"); return false; };
    const result = await f.patch();
    assert.equal(result.effect, "unknown");
    assert.equal(result.writeReceipt.error_class, "receipt_not_durable");
    assert.equal(result.writeReceipt.provider_event_id, "travel-helper-1");
    assert.equal(f.writes.length, 0);
    assert.equal(JSON.stringify(f.ledger).includes("private"), false);
  });
});

test("durable Travel update keeps the known helper fenced unless the proxy proves an upstream rejection", async (t) => {
  const scenarios = [
    ["412", { ok: true, status: 200, body: { status: 412 } }, "no_effect"],
    ["400", { ok: true, status: 200, body: { status: 400 } }, "no_effect"],
    ["outer 500", { ok: false, status: 500, body: { status: 412 } }, "unknown"],
    ["outer 401", { ok: false, status: 401, body: { status: 412 } }, "unknown"],
    ["string status", { ok: true, status: 200, body: { status: "412" } }, "unknown"],
    ["missing status", { ok: true, status: 200, body: { data: { id: "travel-helper-1" } } }, "unknown"],
    ["other helper", { ok: true, status: 200, body: { status: 200, data: { id: "other-helper" } } }, "unknown"],
    ["unreadable", { ok: true, status: 200, unreadable: true }, "unknown"],
    ["timeout", { transportError: true }, "unknown"],
  ];
  for (const [name, response, effect] of scenarios) await t.test(name, async () => {
    const f = durableUpdateFixture();
    f.response = response;
    const result = await f.patch();
    assert.equal(result.effect, effect);
    assert.equal(result.successful, false);
    assert.equal(result.writeReceipt.command, "calendar.update");
    assert.equal(result.writeReceipt.provider_event_id, "travel-helper-1");
    assert.equal(result.writeReceipt.next_action, effect === "no_effect" ? "none" : "owned_readback");
    assert.equal(f.writes.length, 1);
    assert.equal(f.dispatches.length, 1);
    assert.equal(JSON.stringify(f.ledger).includes("private"), false);
  });
});

test("owned point GET uses the exact Hybrid account and direct proxy event, including a bare cancellation", async () => {
  for (const cancelled of [false, true]) {
    const uid = "hybrid-point-fixture", eventId = "event-point_20300101T000000Z";
    const accountHash = createHash("sha256").update(JSON.stringify([uid, ACCOUNT_ID])).digest("hex");
    const event = { id: eventId, status: cancelled ? "cancelled" : "confirmed" };
    const proxyCalls = [], ledger = [];
    const calendar = makeComposioCalendar({
      apiKey: "fixture", supaUrl: "https://supabase.example", supaKey: "fixture",
      readWebTravelControlStateImpl: async () => assert.fail("point read must not enter Web mutation controls"),
      recordCall: async (_uid, tool, details) => { ledger.push({ tool, ...details }); return false; },
      fetchImpl: async (input, init = {}) => {
        const url = new URL(String(input));
        assert.equal(["PATCH", "DELETE"].includes(init.method), false);
        if (url.hostname === "supabase.example") {
          assert.equal(url.searchParams.has("telegram_chat_id"), false);
          return { ok: true, json: async () => [{ uid, telegram_chat_id: 123,
            calendar_provider: "composio_gcal", calendar_connected_account_id: ACCOUNT_ID }] };
        }
        if (url.pathname.includes("/connected_accounts/")) return { ok: true, json: async () => ({
          id: ACCOUNT_ID, user_id: uid, toolkit_slug: "googlecalendar", status: "ACTIVE" }) };
        proxyCalls.push({ url: String(url), method: init.method, body: JSON.parse(init.body) });
        return { ok: true, status: 200, json: async () => ({ status: 200, data: event }) };
      },
    });
    assert.deepEqual(await calendar.getOwnedEvent(uid, eventId, { accountRefHash: accountHash }), event);
    assert.deepEqual(proxyCalls, [{ url: "https://backend.composio.dev/api/v3.1/tools/execute/proxy", method: "POST",
      body: { connected_account_id: ACCOUNT_ID, user_id: uid,
        endpoint: `https://www.googleapis.com/calendar/v3/calendars/primary/events/${eventId}`, method: "GET" } }]);
    assert.equal(ledger.length, 1);
    assert.equal(ledger[0].outcome, "success");
  }
});

test("owned point GET rejects missing or changed ownership before the event request", async () => {
  for (const scenario of ["missing", "changed", "inactive", "wrong-tenant", "failed", "missing-hash", "invalid-id"]) {
    let eventReads = 0;
    const uid = "hybrid-point-fixture";
    const accountHash = createHash("sha256").update(JSON.stringify([uid, ACCOUNT_ID])).digest("hex");
    const calendar = makeComposioCalendar({ apiKey: "fixture", supaUrl: "https://supabase.example", supaKey: "fixture",
      recordCall: () => false,
      fetchImpl: async (input, init = {}) => {
        const url = new URL(String(input));
        assert.equal(["PATCH", "DELETE"].includes(init.method), false);
        if (url.hostname === "supabase.example") return { ok: true, json: async () => scenario === "missing" ? [] : [{
          uid, calendar_provider: "composio_gcal", calendar_connected_account_id: scenario === "changed" ? "ca-other" : ACCOUNT_ID }] };
        if (url.pathname.includes("/connected_accounts/")) return { ok: scenario !== "failed", json: async () => ({
          id: ACCOUNT_ID, user_id: scenario === "wrong-tenant" ? "another-tenant" : uid,
          toolkit_slug: "googlecalendar", status: scenario === "inactive" ? "EXPIRED" : "ACTIVE" }) };
        eventReads++;
        throw new Error("unexpected event request");
      },
    });
    await assert.rejects(() => calendar.getOwnedEvent(uid, scenario === "invalid-id" ? "../event" : "event-id",
      { accountRefHash: scenario === "missing-hash" ? undefined : accountHash }), /calendar owned event read failed/);
    assert.equal(eventReads, 0, scenario);
  }
});

test("owned point GET separates proxy failure, upstream status, unreadable data and a different event ID", async () => {
  const uid = "hybrid-point-fixture", eventId = "event-id";
  const accountHash = createHash("sha256").update(JSON.stringify([uid, ACCOUNT_ID])).digest("hex");
  const cases = [
    { status: 404, data: { error: { message: "private provider response" } } },
    { status: 410, data: { error: { errors: [{ reason: "deleted" }] } } },
    { status: 500 }, { data: { id: eventId } }, { status: "200", data: { id: eventId } },
    { status: 200, data: null }, { status: 200, data: [] }, { status: 200, data: { id: "other" } },
    { status: 200, data: { response_data: { id: eventId } } },
    { outerError: true, status: 200, data: { id: eventId } }, { unreadable: true }, { transportError: true },
  ];
  for (const item of cases) {
    const ledger = [];
    const calendar = makeComposioCalendar({ apiKey: "fixture", supaUrl: "https://supabase.example", supaKey: "fixture",
      recordCall: (_uid, _tool, details) => { ledger.push(details); return true; },
      fetchImpl: async (input) => {
        const url = new URL(String(input));
        if (url.hostname === "supabase.example") return { ok: true, json: async () => [{ uid,
          calendar_provider: "composio_gcal", calendar_connected_account_id: ACCOUNT_ID }] };
        if (url.pathname.includes("/connected_accounts/")) return { ok: true, json: async () => ({
          id: ACCOUNT_ID, user_id: uid, toolkit_slug: "googlecalendar", status: "ACTIVE" }) };
        if (item.transportError) throw new Error("private transport detail");
        return { ok: !item.outerError, status: item.outerError ? 403 : 200,
          json: async () => { if (item.unreadable) throw new Error("private parse detail"); return item; } };
      },
    });
    await assert.rejects(() => calendar.getOwnedEvent(uid, eventId, { accountRefHash: accountHash }),
      (error) => error.message === "calendar owned event read failed");
    assert.equal(ledger.length, 1);
    assert.equal(ledger[0].outcome, "unknown");
    assert.equal(JSON.stringify(ledger).includes("private"), false);
  }
});

test("owned Hybrid readback validates the saved exact ACTIVE account without binding backfill or Web controls", async () => {
  const calls = [];
  const uid = "hybrid-fixture";
  const accountHash = createHash("sha256").update(JSON.stringify([uid, ACCOUNT_ID])).digest("hex");
  const calendar = makeComposioCalendar({
    apiKey: "fixture-key", supaUrl: "https://supabase.example", supaKey: "fixture-service",
    recordCall: () => false,
    readWebTravelControlStateImpl: async () => assert.fail("readback must not enter Web mutation controls"),
    fetchImpl: async (input, init = {}) => {
      const url = new URL(String(input));
      calls.push({ url, method: init.method || "GET", body: init.body && JSON.parse(init.body) });
      if (url.hostname === "supabase.example") {
        assert.equal(url.searchParams.has("telegram_chat_id"), false);
        return { ok: true, json: async () => [{ uid, telegram_chat_id: 123,
          calendar_provider: "composio_gcal", calendar_connected_account_id: ACCOUNT_ID }] };
      }
      if (url.pathname.endsWith(`/connected_accounts/${ACCOUNT_ID}`)) {
        return { ok: true, json: async () => ({ id: ACCOUNT_ID, user_id: uid, toolkit_slug: "googlecalendar", status: "ACTIVE" }) };
      }
      assert.equal(url.pathname.endsWith("GOOGLECALENDAR_EVENTS_LIST"), true);
      const body = JSON.parse(init.body);
      assert.equal(body.connected_account_id, ACCOUNT_ID);
      return { ok: true, json: async () => ({ successful: true, data: body.arguments.pageToken
        ? { items: [{ id: "second" }] } : { items: [{ id: "first" }], nextPageToken: "page-2" } }) };
    },
  });
  const items = await calendar.listOwnedEvents(uid, { accountRefHash: accountHash,
    timeMin: "2030-01-01T00:00:00Z", timeMax: "2030-01-08T00:00:00Z" });
  assert.deepEqual(items.map((item) => item.id), ["first", "second"]);
  assert.equal(calls.some((call) => ["PATCH", "DELETE"].includes(call.method)), false);
  assert.equal(calls.filter((call) => call.method === "POST").length, 2);
});

test("owned readback rejects missing, changed, inactive, or another tenant's account before reading Calendar", async () => {
  for (const scenario of ["missing", "changed", "inactive", "wrong-tenant", "failed"]) {
    let eventReads = 0;
    const uid = "hybrid-fixture";
    const accountHash = createHash("sha256").update(JSON.stringify([uid, ACCOUNT_ID])).digest("hex");
    const calendar = makeComposioCalendar({
      apiKey: "fixture", supaUrl: "https://supabase.example", supaKey: "fixture", recordCall: () => false,
      fetchImpl: async (input, init = {}) => {
        const url = new URL(String(input));
        assert.equal(["PATCH", "DELETE"].includes(init.method), false);
        if (url.hostname === "supabase.example") return { ok: true, json: async () => scenario === "missing" ? [] : [{
          uid, calendar_provider: "composio_gcal", calendar_connected_account_id: scenario === "changed" ? "ca-other" : ACCOUNT_ID,
        }] };
        if (url.pathname.includes("/connected_accounts/")) return { ok: scenario !== "failed", json: async () => ({
          id: ACCOUNT_ID, user_id: scenario === "wrong-tenant" ? "another-tenant" : uid,
          toolkit_slug: "googlecalendar", status: scenario === "inactive" ? "EXPIRED" : "ACTIVE",
        }) };
        eventReads++;
        throw new Error("unexpected Calendar read");
      },
    });
    await assert.rejects(calendar.listOwnedEvents(uid, { accountRefHash: accountHash }));
    assert.equal(eventReads, 0, scenario);
  }
});

test("durable dispatch cannot bypass the existing Web null-Telegram ownership guard", async () => {
  let providerCalls = 0;
  let dispatches = 0;
  const calendar = makeComposioCalendar({ apiKey: "fixture", supaUrl: "https://supabase.example", supaKey: "fixture",
    recordCall: () => true,
    fetchImpl: async (input) => {
      if (new URL(String(input)).hostname !== "supabase.example") { providerCalls++; throw new Error("unexpected provider request"); }
      return { ok: true, json: async () => [{ uid: UID, telegram_chat_id: 123,
        calendar_provider: "composio_gcal", calendar_connected_account_id: ACCOUNT_ID }] };
    },
  });
  const result = await calendar.createEvent(UID, { summary: "Synthetic travel" }, {
    expectedCalendarAccountId: ACCOUNT_ID, beforeDispatch: async () => { dispatches++; return true; },
  });
  assert.equal(result.effect, "no_effect");
  assert.equal(dispatches, 0);
  assert.equal(providerCalls, 0);
});

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
      if (parsed.pathname.endsWith("/tools/execute/proxy")) {
        return { ok: true, status: 200, json: async () => ({ status: 200, data: {
          id: "travel-existing", reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
        } }) };
      }
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

test("raw_create_uses_boolean_send_updates_false", async () => {
  for (const [input, expected] of [["none", false], [false, false], [true, true], [null, null], [undefined, undefined]]) {
    const f = fixture({ dailyAutomationEnabled: true, disconnectPending: false, enablePending: false });
    const args = Object.freeze({ summary: "Travel fixture", ...(input === undefined ? {} : { send_updates: input }) });
    const result = await f.calendar.createEvent(UID, args);

    assert.equal(result.effect, "created");
    assert.equal(f.providerCalls.length, 1);
    assert.equal(f.providerCalls[0].path, "/api/v3/tools/execute/GOOGLECALENDAR_CREATE_EVENT");
    assert.equal(f.providerCalls[0].body.connected_account_id, ACCOUNT_ID);
    assert.equal(f.providerCalls[0].body.arguments.send_updates, expected);
    assert.equal(args.send_updates, input);
  }
});

test("web_proxy_create_and_reminder_patch_keep_sendUpdates_none", async () => {
  for (const sendUpdates of ["none", false]) {
    const f = fixture({ dailyAutomationEnabled: true, disconnectPending: false, enablePending: false });
    const reminders = { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] };
    const created = await f.calendar.createEvent(UID, {
      summary: "Travel fixture", start_datetime: "2030-01-01T00:00:00",
      event_duration_minutes: 25, reminders, send_updates: sendUpdates,
    }, { expectedCalendarAccountId: ACCOUNT_ID });
    const patched = await f.calendar.patchEvent(UID, {
      calendar_id: "primary", event_id: "travel-existing", reminders, send_updates: sendUpdates,
    }, { expectedCalendarAccountId: ACCOUNT_ID });

    assert.equal(created.effect, "created");
    assert.equal(patched.effect, "updated");
    assert.equal(f.providerCalls.length, 2);
    assert.deepEqual(f.providerCalls.map((call) => call.body.method), ["POST", "PATCH"]);
    for (const call of f.providerCalls) {
      assert.equal(call.path, "/api/v3.1/tools/execute/proxy");
      assert.equal(call.body.connected_account_id, ACCOUNT_ID);
      assert.deepEqual(call.body.parameters, [{ name: "sendUpdates", value: "none", type: "query" }]);
    }
  }
});

test("go_and_return_share_the_transport_contract", async () => {
  const f = fixture({ dailyAutomationEnabled: true, disconnectPending: false, enablePending: false });
  const result = await fillTravel(UID, {
    home: "Fixture home", mapsKey: "fixture-key", nowMs: Date.parse("2030-01-01T08:00:00Z"),
    calendar: { ...f.calendar, listEventsRaw: async () => [{
      id: "fixture-event", summary: "Fixture meeting", location: "Fixture venue",
      start: { dateTime: "2030-01-01T10:00:00Z" }, end: { dateTime: "2030-01-01T11:00:00Z" },
    }] },
    _directionsMinutes: async () => 10,
  });

  assert.equal(result.inserted, 2);
  assert.equal(f.providerCalls.length, 2);
  assert.deepEqual(f.providerCalls.map((call) => call.body.arguments.location), ["Fixture venue", "Fixture home"]);
  for (const call of f.providerCalls) {
    assert.equal(call.path, "/api/v3/tools/execute/GOOGLECALENDAR_CREATE_EVENT");
    assert.equal(call.body.connected_account_id, ACCOUNT_ID);
    assert.equal(call.body.arguments.send_updates, false);
  }
});

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
  assert.equal(allowed.providerCalls[0].path, "/api/v3.1/tools/execute/proxy");
  assert.equal(allowed.providerCalls[0].body.endpoint,
    "https://www.googleapis.com/calendar/v3/calendars/primary/events/travel-existing");
  assert.equal(allowed.providerCalls[0].body.method, "PATCH");
  assert.equal(allowed.providerCalls[0].body.connected_account_id, ACCOUNT_ID);
  assert.deepEqual(allowed.providerCalls[0].body.parameters,
    [{ name: "sendUpdates", value: "none", type: "query" }]);
  assert.deepEqual(allowed.providerCalls[0].body.body,
    { reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] } });

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
