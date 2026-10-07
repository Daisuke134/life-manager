"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { buildTodaySnapshot, handleWebTravelRequest, runInitialWebTravelScan } = require("./web-travel.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const OTHER_UID = "lm_22222222-2222-4222-8222-222222222222";
const ORIGIN = "https://life.example";
const NOW = Date.parse("2030-01-01T08:00:00+09:00");
const ENABLE_CLAIM_ID = "d901bdde-e5ce-4c7c-9b73-6d9f8fc24e2f";
const ENABLE_CLAIMED_AT = "2030-01-01T07:00:00.000Z";

function markEnablePending(row) {
  row.calendar_enable_pending = true;
  row.calendar_enable_claim_id = ENABLE_CLAIM_ID;
  row.calendar_enable_claimed_at = ENABLE_CLAIMED_AT;
}

function makeRequest(method, url, { body, origin, contentType, csrf } = {}) {
  return {
    method,
    url,
    testBody: body,
    headers: {
      ...(origin ? { origin } : {}),
      ...(contentType ? { "content-type": contentType } : {}),
      ...(csrf ? { "x-lm-web-csrf": csrf } : {}),
    },
  };
}

function makeResponse() {
  return {
    status: 0,
    headers: {},
    body: "",
    writeHead(status, headers = {}) { this.status = status; this.headers = { ...this.headers, ...headers }; },
    end(body = "") { this.body = String(body); },
  };
}

function event(id = "event-1", location = "渋谷ヒカリエ") {
  return {
    id,
    summary: "打ち合わせ",
    location,
    start: { dateTime: "2030-01-01T10:00:00+09:00", timeZone: "Asia/Tokyo" },
    end: { dateTime: "2030-01-01T11:00:00+09:00", timeZone: "Asia/Tokyo" },
  };
}

function travelBlock() {
  return {
    id: "travel-1",
    summary: "[Travel] 🚆 Home→渋谷ヒカリエ",
    location: "渋谷ヒカリエ",
    start: { dateTime: "2030-01-01T09:35:00+09:00", timeZone: "Asia/Tokyo" },
    end: { dateTime: "2030-01-01T10:00:00+09:00", timeZone: "Asia/Tokyo" },
    reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
  };
}

function fixture(overrides = {}) {
  const row = {
    uid: UID,
    telegram_chat_id: null,
    calendar_provider: "composio_gcal",
    calendar_connected_account_id: "ca-selected-123",
    calendar_enable_pending: false,
    calendar_enable_claim_id: null,
    calendar_enable_claimed_at: null,
    home_address: null,
    trial_expires_at: null,
    paid: false,
    web_initial_scan_completed_at: null,
    web_first_travel_at: null,
  };
  const events = [event()];
  const calendarReads = [];
  const sequence = [];
  const scanRpcCalls = [];
  const controlRpcCalls = [];
  const travelExpectedAccountIds = [];
  let preference = {
    call_enabled: false,
    notifications_enabled: false,
    daily_automation_enabled: false,
    calendar_disconnect_pending: false,
  };
  const disconnectCalls = [];
  let providerStatus = "ACTIVE";
  let travelCalls = 0;
  const fetchImpl = async (url, init = {}) => {
    const requestUrl = new URL(String(url));
    if (requestUrl.pathname.endsWith("/rpc/record_lm_web_initial_scan")) {
      const body = JSON.parse(init.body || "{}");
      scanRpcCalls.push(body);
      if (body.p_uid !== UID || body.p_calendar_account_id !== row.calendar_connected_account_id) {
        return { ok: false, status: 400, json: async () => ({ message: "calendar_account_changed" }) };
      }
      if (row.calendar_enable_pending || preference && preference.calendar_disconnect_pending) {
        return { ok: false, status: 400, json: async () => ({ message: "calendar_operation_pending" }) };
      }
      row.web_initial_scan_completed_at ||= body.p_completed_at;
      row.web_first_travel_at ||= body.p_first_travel_at;
      return { ok: true, status: 200, json: async () => true };
    }
    if (requestUrl.pathname.endsWith("/rpc/control_lm_web_travel")) {
      sequence.push(`control_rpc:${JSON.parse(init.body || "{}").p_action}`);
      const body = JSON.parse(init.body || "{}");
      controlRpcCalls.push(body);
      if (body.p_uid !== UID || body.p_calendar_account_id !== (row.calendar_connected_account_id || null)) {
        return { ok: false, status: 400, json: async () => ({ message: "calendar_account_changed" }) };
      }
      if (body.p_action === "pause" && !preference) {
        preference = { call_enabled: false, notifications_enabled: false, daily_automation_enabled: false, calendar_disconnect_pending: false };
      } else if (body.p_action === "disconnect_begin" && !preference) {
        preference = { call_enabled: false, notifications_enabled: false, daily_automation_enabled: false, calendar_disconnect_pending: true };
      } else if (!preference) {
        return { ok: false, status: 400, json: async () => ({ message: "preference_missing" }) };
      } else if (body.p_action === "pause") preference.daily_automation_enabled = false;
      else if (body.p_action === "resume") {
        if (preference.calendar_disconnect_pending) {
          return { ok: false, status: 400, json: async () => ({ message: "calendar_disconnect_pending" }) };
        }
        preference.daily_automation_enabled = true;
      } else if (body.p_action === "disconnect_begin") {
        preference.daily_automation_enabled = false;
        preference.calendar_disconnect_pending = true;
      } else if (body.p_action === "disconnect_finish") {
        if (!preference.calendar_disconnect_pending || providerStatus !== "DISABLED") {
          return { ok: false, status: 400, json: async () => ({ message: "calendar_disconnect_pending" }) };
        }
        preference.daily_automation_enabled = false;
        preference.calendar_disconnect_pending = false;
      } else if (body.p_action === "disconnect") preference.daily_automation_enabled = false;
      else return { ok: false, status: 400, json: async () => ({ message: "invalid_action" }) };
      if (body.p_action === "disconnect" || body.p_action === "disconnect_finish") {
        row.calendar_provider = null;
        row.calendar_connected_account_id = null;
      }
      return { ok: true, status: 200, json: async () => true };
    }
    if (requestUrl.pathname.endsWith("/lm_users")) {
      sequence.push("user_row");
      assert.equal((requestUrl.searchParams.get("select") || "").includes("call_time_zone"), false);
      return { ok: true, status: 200, json: async () => row.telegram_chat_id == null ? [{ ...row }] : [] };
    }
    if (requestUrl.pathname.endsWith("/lm_panel_preferences")) {
      sequence.push("preference_read");
      assert.match(requestUrl.searchParams.get("select") || "", /daily_automation_enabled/);
      return { ok: true, status: 200, json: async () => preference ? [{ ...preference }] : [] };
    }
    throw new Error(`unexpected service request: ${requestUrl.pathname}`);
  };
  const opts = {
    publicOrigin: ORIGIN,
    supaUrl: "https://supabase.example",
    supaKey: "service-role-key",
    env: { COMPOSIO_API_KEY: "provider-key" },
    nowMs: NOW,
    resolveWebUserImpl: async () => ({ uid: UID, subject: "subject", email: "user@example.test", csrf: "csrf-token" }),
    assertWebUserUnboundImpl: async (uid) => { sequence.push("unbound"); assert.equal(uid, UID); return true; },
    composioCalendarAccountStatusImpl: async (scope, accountId) => {
      sequence.push("calendar_status");
      assert.deepEqual(scope, { uid: UID });
      assert.equal(accountId, row.calendar_connected_account_id);
      return providerStatus;
    },
    composioCalendarDisconnectImpl: async (scope, providerOpts) => {
      sequence.push("calendar_disconnect");
      disconnectCalls.push({ scope, connectedAccountId: providerOpts.connectedAccountId });
      assert.deepEqual(scope, { uid: UID });
      providerStatus = "DISABLED";
      return { provider: "calendar", state: "action_required" };
    },
    fetchImpl,
    readJsonImpl: async (req) => req.testBody,
    calendar: {
      async listEventsRaw(uid, bounds) {
        sequence.push("calendar_read");
        calendarReads.push(bounds);
        assert.equal(uid, UID);
        assert.equal(bounds.strict, true);
        return events.slice();
      },
    },
    travelUserOnceImpl: async (user, deps = {}) => {
      sequence.push("travel");
      travelCalls++;
      assert.equal(user.uid, UID);
      assert.equal(user.daily_automation_enabled, false);
      assert.equal(user.home_address, row.home_address);
      assert.equal(deps.initialScan, true);
      travelExpectedAccountIds.push(user.expectedCalendarAccountId);
      const inserted = !events.some((item) => String(item.summary || "").startsWith("[Travel]"));
      if (inserted) events.push(travelBlock());
      return inserted ? {
        inserted: 1,
        outboundReports: [{
          eventId: "event-1",
          leaveMs: Date.parse("2030-01-01T09:35:00+09:00"),
          arriveMs: Date.parse("2030-01-01T10:00:00+09:00"),
        }],
      } : { inserted: 0, outboundReports: [] };
    },
    ...overrides,
  };
  return { events, fetchImpl, opts, row, scanRpcCalls, controlRpcCalls, disconnectCalls, get preference() { return preference; }, set preference(value) { preference = value; }, sequence, calendarReads, travelExpectedAccountIds,
    get providerStatus() { return providerStatus; }, set providerStatus(value) { providerStatus = value; },
    get travelCalls() { return travelCalls; } };
}

async function call(fixtureValue, method, url, requestOptions = {}) {
  const response = makeResponse();
  await handleWebTravelRequest(makeRequest(method, url, requestOptions), response, fixtureValue.opts);
  return response;
}

test("initial Web setup accepts no home and does not start a trial or recurring automation", async () => {
  const f = fixture();
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 200);
  assert.equal(f.row.home_address, null);
  assert.equal(f.row.trial_expires_at, null);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.travelCalls, 1);
});

test("zero-block setup can explicitly rescan after the user adds a location and then offer trial", async () => {
  let f;
  let addTravel = false;
  let scans = 0;
  f = fixture({ travelUserOnceImpl: async (_user, deps) => {
    scans++;
    assert.equal(deps.initialScan, true);
    if (!addTravel) return { inserted: 0, outboundReports: [] };
    f.events.push(travelBlock());
    return { inserted: 1, outboundReports: [{ eventId: "event-1",
      leaveMs: Date.parse("2030-01-01T09:35:00+09:00"),
      arriveMs: Date.parse("2030-01-01T10:00:00+09:00") }] };
  } });
  const first = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });
  assert.equal(JSON.parse(first.body).scanState, "zero_blocks");
  assert.ok(f.row.web_initial_scan_completed_at);
  assert.equal(f.row.web_first_travel_at, null);
  assert.equal(scans, 1);

  addTravel = true;
  f.row.home_address = "Home";
  const second = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { rescan: true },
  });
  const result = JSON.parse(second.body);
  assert.equal(second.status, 200);
  assert.equal(result.scanState, "complete");
  assert.equal(result.checkoutAvailable, true);
  assert.ok(f.row.web_first_travel_at);
  assert.equal(scans, 2);
  assert.equal(f.scanRpcCalls.length, 2);
});

test("billing-inactive Web page avoids further Calendar event reads", async () => {
  let eventReads = 0;
  const f = fixture({ listEvents7dImpl: async () => { eventReads++; return [event()]; } });
  f.row.web_initial_scan_completed_at = "2030-01-01T00:00:00.000Z";
  f.row.web_first_travel_at = "2030-01-01T00:00:00.000Z";
  f.row.stripe_subscription_id = "sub-canceled";
  f.row.paid = false;
  f.row.plan_status = "canceled";

  const snapshot = await buildTodaySnapshot(UID, f.opts);

  assert.equal(snapshot.setupState, "billing_inactive");
  assert.equal(eventReads, 0);
  assert.equal(snapshot.subscriptionCheckoutAvailable, true);
});

test("expired legacy Web trial stops Calendar reads but leaves paid restart available", async () => {
  let eventReads = 0;
  const f = fixture({ listEvents7dImpl: async () => { eventReads++; return [event()]; } });
  f.row.web_initial_scan_completed_at = "2029-12-01T00:00:00.000Z";
  f.row.web_first_travel_at = "2029-12-01T00:00:00.000Z";
  f.row.trial_expires_at = "2029-12-04T00:00:00.000Z";
  const snapshot = await buildTodaySnapshot(UID, f.opts);
  assert.equal(snapshot.setupState, "billing_inactive");
  assert.equal(snapshot.subscriptionCheckoutAvailable, true);
  assert.equal(eventReads, 0);
});

test("saved Travel offer and active subscription screens do not reread Calendar events", async () => {
  for (const [setupState, billing] of [
    ["trial_offer", { stripe_subscription_id: null, paid: false, plan_status: null }],
    ["trial_active", { stripe_subscription_id: "sub-trial", paid: true, plan_status: "trialing",
      trial_expires_at: "2030-01-08T00:00:00.000Z" }],
    ["subscribed", { stripe_subscription_id: "sub-paid", paid: true, plan_status: "active" }],
  ]) {
    let eventReads = 0;
    const f = fixture({ listEvents7dImpl: async () => { eventReads++; return [event()]; } });
    f.row.web_initial_scan_completed_at = "2030-01-01T00:00:00.000Z";
    f.row.web_first_travel_at = "2030-01-01T00:00:00.000Z";
    Object.assign(f.row, billing);
    const snapshot = await buildTodaySnapshot(UID, f.opts);
    assert.equal(snapshot.setupState, setupState);
    assert.equal(eventReads, 0);
  }
});

test("zero-block initial scan is recorded without a first Travel timestamp or trial", async () => {
  const f = fixture({
    travelUserOnceImpl: async (_user, _deps) => ({ inserted: 0, verified: 0, outboundReports: [] }),
  });
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 200);
  const result = JSON.parse(response.body);
  assert.equal(result.setupState, "no_eligible_events");
  assert.equal(result.checkoutAvailable, false);
  assert.ok(f.row.web_initial_scan_completed_at);
  assert.equal(f.row.web_first_travel_at, null);
  assert.equal(f.row.trial_expires_at, null);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.scanRpcCalls[0].p_first_travel_at, null);
});

test("uncertain Calendar write is not recorded as first value", async () => {
  const f = fixture({
    travelUserOnceImpl: async () => ({
      inserted: 1,
      verified: 0,
      outboundReports: [{ eventId: "event-1", leaveMs: 1, arriveMs: 2 }],
    }),
  });
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 200);
  const result = JSON.parse(response.body);
  assert.equal(result.scanState, "pending");
  assert.equal(result.checkoutAvailable, false);
  assert.equal(f.row.web_initial_scan_completed_at, null);
  assert.equal(f.row.web_first_travel_at, null);
  assert.equal(f.scanRpcCalls.length, 0);
});

test("repeated initial setup reuses the confirmed Travel block and keeps one scan receipt", async () => {
  const f = fixture();
  const request = {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  };
  const first = await call(f, "POST", "/api/lm-web/setup", request);
  const second = await call(f, "POST", "/api/lm-web/setup", request);

  assert.equal(first.status, 200);
  assert.equal(second.status, 200);
  assert.equal(f.travelCalls, 1);
  assert.equal(f.scanRpcCalls.length, 1);
  assert.ok(f.row.web_first_travel_at);
  assert.equal(f.row.trial_expires_at, null);
  assert.equal(f.preference.daily_automation_enabled, false);
});

test("initial scan stays pending and offers no trial if the Travel popup reminder is not read back", async () => {
  const f = fixture();
  const block = travelBlock();
  delete block.reminders;
  f.events.push(block);
  f.opts.travelUserOnceImpl = async () => ({ inserted: 1, outboundReports: [] });

  const result = await runInitialWebTravelScan(UID, f.opts);

  assert.equal(result.scanState, "pending");
  assert.equal(result.checkoutAvailable, false);
  assert.equal(f.row.web_first_travel_at, null);
});

test("setup ignores client-controlled address and billing fields", async () => {
  const f = fixture();
  f.preference = null;
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN,
    contentType: "application/json",
    csrf: "csrf-token",
    body: { homeAddress: "forged address", uid: OTHER_UID, paid: true, telegram_chat_id: "attacker" },
  });

  assert.equal(response.status, 200);
  assert.equal(f.row.home_address, null);
  assert.equal(f.row.trial_expires_at, null);
  assert.equal(f.row.paid, false);
  assert.equal(f.row.telegram_chat_id, null);
  assert.equal(f.scanRpcCalls.length, 1);
  assert.equal(f.scanRpcCalls[0].p_uid, UID);
  assert.equal(f.scanRpcCalls[0].p_calendar_account_id, "ca-selected-123");
  assert.equal(f.preference.daily_automation_enabled, false);
  const result = JSON.parse(response.body);
  assert.equal(result.setupState, "trial_offer");
  assert.equal(result.checkoutAvailable, true);
  assert.equal(result.confirmedTravelBlockCount, 1);
});

test("Calendar readback must be ACTIVE before the initial scan", async () => {
  let stateWrites = 0, travelCount = 0, eventReads = 0;
  const f = fixture({
    composioCalendarAccountStatusImpl: async () => "DISABLED",
    travelUserOnceImpl: async () => { travelCount++; },
    fetchImpl: async (url, init = {}) => {
      if (String(url).includes("/rpc/record_lm_web_initial_scan")) stateWrites++;
      return fixture().fetchImpl(url, init);
    },
    calendar: { async listEventsRaw() { eventReads++; return []; } },
  });
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 409);
  assert.equal(stateWrites, 0);
  assert.equal(travelCount, 0);
  assert.equal(eventReads, 0);
});

test("initial scan stays fenced during pending Calendar disconnect", async () => {
  const f = fixture();
  f.preference.daily_automation_enabled = false;
  f.preference.calendar_disconnect_pending = true;
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 409);
  assert.equal(JSON.parse(response.body).error, "disconnect_pending");
  assert.equal(f.row.home_address, null);
  assert.equal(f.row.trial_expires_at, null);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.preference.calendar_disconnect_pending, true);
  assert.equal(f.travelCalls, 0);
  assert.equal(f.scanRpcCalls.length, 0);
});

test("initial scan stays fenced during pending Calendar enable", async () => {
  const f = fixture();
  markEnablePending(f.row);
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 409);
  assert.equal(JSON.parse(response.body).error, "calendar_enable_pending");
  assert.equal(f.row.home_address, null);
  assert.equal(f.row.trial_expires_at, null);
  assert.equal(f.travelCalls, 0);
  assert.equal(f.scanRpcCalls.length, 0);
});

test("initial scan rechecks the selected ACTIVE Calendar after pausing automation", async () => {
  const f = fixture();
  f.preference.daily_automation_enabled = true;
  let statusReads = 0;
  f.opts.composioCalendarAccountStatusImpl = async (scope, accountId) => {
    statusReads++;
    assert.deepEqual(scope, { uid: UID });
    assert.equal(accountId, f.row.calendar_connected_account_id);
    return "ACTIVE";
  };
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 200);
  assert.equal(statusReads >= 2, true);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.travelCalls, 1);
  assert.equal(f.travelExpectedAccountIds[0], "ca-selected-123");
});

test("no-home onboarding stays on the one-time scan path and locationless events get no guessed block", async () => {
  const noHome = fixture({ calendar: { async listEventsRaw() { return [event()]; } } });
  const noHomeSnapshot = await buildTodaySnapshot(UID, noHome.opts);
  assert.equal(noHomeSnapshot.setupState, "needs_initial_scan");
  assert.equal(noHomeSnapshot.nextEvent.location, "渋谷ヒカリエ");
  assert.equal(noHomeSnapshot.travelBlock, null);

  const locationless = fixture({ calendar: { async listEventsRaw() { return [event("event-no-location", "")]; } } });
  locationless.row.web_initial_scan_completed_at = "2030-01-01T00:00:00.000Z";
  const locationlessSnapshot = await buildTodaySnapshot(UID, locationless.opts);
  assert.equal(locationlessSnapshot.setupState, "no_eligible_events");
  assert.equal(locationlessSnapshot.nextEvent.location, "");
  assert.equal(locationlessSnapshot.travelBlock, null);
  assert.equal(locationlessSnapshot.departureAt, null);
});

test("Today uses the next event's validated timezone instead of the UTC Travel helper", async () => {
  const nextStart = NOW + 2 * 60 * 60_000;
  const next = {
    id: "event-zone",
    summary: "Los Angeles meeting",
    location: "Los Angeles",
    startIso: new Date(nextStart).toISOString(),
    timezone: "America/Los_Angeles",
    startMs: nextStart,
    endMs: nextStart + 60 * 60_000,
  };
  const helper = {
    id: "travel-zone",
    summary: "[Travel] Home→Los Angeles",
    location: "Los Angeles",
    startIso: new Date(nextStart - 30 * 60_000).toISOString(),
    timezone: "UTC",
    startMs: nextStart - 30 * 60_000,
    endMs: nextStart,
  };
  const f = fixture({ listEvents7dImpl: async () => [helper, next] });
  f.row.home_address = "Home";

  const snapshot = await buildTodaySnapshot(UID, f.opts);

  assert.equal(snapshot.displayTimeZone, "America/Los_Angeles");
  assert.equal(snapshot.travelBlock.timezone, "UTC");
});

test("Today leaves missing or non-IANA event timezones for browser-local formatting", async () => {
  for (const timezone of ["", "+09:00", "Not/IANA"]) {
    const nextStart = NOW + 60 * 60_000;
    const f = fixture({ listEvents7dImpl: async () => [{
      id: `event-${timezone || "missing"}`,
      summary: "Meeting",
      location: "Office",
      startIso: new Date(nextStart).toISOString(),
      timezone,
      startMs: nextStart,
      endMs: nextStart + 60 * 60_000,
    }] });
    f.row.home_address = "Home";

    const snapshot = await buildTodaySnapshot(UID, f.opts);

    assert.equal(snapshot.displayTimeZone, null, `timezone ${timezone || "(missing)"}`);
  }
});

test("Today counts only upcoming seven-day non-Travel events without a location", async () => {
  const item = (id, offsetMs, { summary = "Meeting", location = "", timezone = "America/Los_Angeles" } = {}) => ({
    id,
    summary,
    location,
    startIso: new Date(NOW + offsetMs).toISOString(),
    timezone,
    startMs: NOW + offsetMs,
    endMs: NOW + offsetMs + 60 * 60_000,
  });
  const f = fixture({ listEvents7dImpl: async () => [
    item("past", -60 * 60_000),
    item("next", 60 * 60_000),
    item("later-missing", 2 * 86400_000),
    item("located", 3 * 86400_000, { location: "Office" }),
    item("travel", 4 * 86400_000, { summary: "[Travel] commute" }),
    item("outside-window", 8 * 86400_000),
  ] });
  f.row.home_address = "Home";

  const snapshot = await buildTodaySnapshot(UID, f.opts);

  assert.equal(snapshot.missingLocationCount, 2);
});

test("missing Calendar helper readback remains pending", async () => {
  let travelAttempts = 0;
  const f = fixture({ travelUserOnceImpl: async () => { travelAttempts++; return { inserted: 1 }; }, calendar: { async listEventsRaw() { return [event()]; } } });
  f.preference = null;
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });
  const result = JSON.parse(response.body);
  assert.equal(response.status, 200);
  assert.equal(result.scanState, "pending");
  assert.equal(result.checkoutAvailable, false);
  assert.equal(result.confirmedTravelBlockCount, 0);
  assert.equal(f.row.web_initial_scan_completed_at, null);
  assert.equal(f.row.web_first_travel_at, null);
  assert.equal(travelAttempts, 1);
});

test("duplicate matching Travel helpers remain pending with no reported block", async () => {
  const f = fixture();
  f.row.home_address = "自宅住所";
  f.events.push(travelBlock(), { ...travelBlock(), id: "travel-2" });

  const snapshot = await buildTodaySnapshot(UID, f.opts);
  assert.equal(snapshot.setupState, "sync_pending");
  assert.equal(snapshot.travelBlock, null);
  assert.equal(snapshot.departureAt, null);
});

test("unrelated outbound report cannot turn a verified helper into travel_added", async () => {
  let f;
  f = fixture({ travelUserOnceImpl: async () => {
    f.events.push(travelBlock());
    return {
      inserted: 1,
      outboundReports: [{ eventId: "event-other", leaveMs: Date.parse("2030-01-01T09:35:00+09:00"), arriveMs: NOW }],
    };
  } });
  f.preference = null;
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });
  const result = JSON.parse(response.body);
  assert.equal(response.status, 200);
  assert.equal(result.travelBlock.id, "travel-1");
  assert.equal(result.syncState, "travel_verified");
});

test("travel_added requires the report arrival to match the helper end time", async () => {
  let f;
  f = fixture({ travelUserOnceImpl: async () => {
    const helper = travelBlock();
    helper.end.dateTime = "2030-01-01T09:59:30+09:00";
    f.events.push(helper);
    return {
      inserted: 1,
      outboundReports: [{
        eventId: "event-1",
        leaveMs: Date.parse("2030-01-01T09:35:00+09:00"),
        arriveMs: Date.parse("2030-01-01T10:00:00+09:00"),
      }],
    };
  } });
  f.preference = null;
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });
  const result = JSON.parse(response.body);

  assert.equal(response.status, 200);
  assert.equal(result.nextEvent.id, "event-1");
  assert.notEqual(result.travelBlock.endMs, result.nextEvent.startMs);
  assert.equal(result.syncState, "travel_verified");
});

test("initial scan rejects a Calendar account changed after ACTIVE readback", async () => {
  const f = fixture();
  f.opts.composioCalendarAccountStatusImpl = async (scope, accountId) => {
    assert.deepEqual(scope, { uid: UID });
    assert.equal(accountId, "ca-selected-123");
    f.row.calendar_connected_account_id = "ca-replaced-456";
    return "ACTIVE";
  };

  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });
  assert.equal(response.status, 409);
  assert.equal(JSON.parse(response.body).error, "calendar_account_changed");
  assert.equal(f.travelCalls, 0);
  assert.equal(f.scanRpcCalls.length, 0);
  assert.equal(f.row.home_address, null);
  assert.equal(f.row.trial_expires_at, null);
});

test("today rechecks Web eligibility before its strict Calendar read", async () => {
  const f = fixture();
  f.row.home_address = "自宅住所";
  await buildTodaySnapshot(UID, f.opts);
  const calendarReadIndex = f.sequence.indexOf("calendar_read");
  assert.ok(calendarReadIndex > 0);
  assert.equal(f.sequence[calendarReadIndex - 1], "unbound");
  assert.ok(f.sequence.slice(0, calendarReadIndex).includes("calendar_status"));
});

test("today event read carries the exact ACTIVE account into the Calendar adapter", async () => {
  const f = fixture();
  await buildTodaySnapshot(UID, f.opts);
  assert.equal(f.calendarReads.length, 1);
  assert.equal(f.calendarReads[0].expectedCalendarAccountId, "ca-selected-123");
});

test("travel controls reject missing or wrong Origin, CSRF, and forged identity fields", async () => {
  const f = fixture();
  const path = "/api/lm-web/travel/control";
  const missingOrigin = await call(f, "POST", path, {
    contentType: "application/json", csrf: "csrf-token", body: { action: "pause" },
  });
  const wrongOrigin = await call(f, "POST", path, {
    origin: "https://attacker.example", contentType: "application/json", csrf: "csrf-token", body: { action: "pause" },
  });
  const wrongCsrf = await call(f, "POST", path, {
    origin: ORIGIN, contentType: "application/json", csrf: "wrong", body: { action: "pause" },
  });
  const forged = await call(f, "POST", path, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token",
    body: { action: "pause", uid: OTHER_UID, connectedAccountId: "ca-attacker-999" },
  });

  assert.equal(missingOrigin.status, 403);
  assert.equal(wrongOrigin.status, 403);
  assert.equal(wrongCsrf.status, 403);
  assert.equal(forged.status, 400);
  assert.deepEqual(f.controlRpcCalls, []);
  assert.deepEqual(f.disconnectCalls, []);
});

test("travel control rejects same-character-length multibyte CSRF without effects", async () => {
  const f = fixture();
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN,
    contentType: "application/json",
    csrf: "é123456789",
    body: { action: "pause" },
  });

  assert.equal("csrf-token".length, "é123456789".length);
  assert.equal(response.status, 403);
  assert.deepEqual(f.controlRpcCalls, []);
  assert.deepEqual(f.disconnectCalls, []);
});

test("travel controls reject Telegram-bound users", async () => {
  const f = fixture();
  f.row.telegram_chat_id = "telegram-bound";
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "pause" },
  });

  assert.equal(response.status, 403);
  assert.deepEqual(f.controlRpcCalls, []);
  assert.deepEqual(f.disconnectCalls, []);
});

test("pause changes only persisted daily automation preference", async () => {
  const f = fixture();
  f.row.home_address = "自宅住所";
  f.preference.daily_automation_enabled = true;
  const before = { ...f.row };
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "pause" },
  });

  assert.equal(response.status, 200);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.row.home_address, before.home_address);
  assert.equal(f.row.trial_expires_at, before.trial_expires_at);
  assert.equal(f.row.calendar_connected_account_id, before.calendar_connected_account_id);
  assert.deepEqual(f.controlRpcCalls, [{ p_uid: UID, p_calendar_account_id: "ca-selected-123", p_action: "pause" }]);
  assert.deepEqual(JSON.parse(response.body), { dailyAutomationEnabled: false, disconnectPending: false, enablePending: false, calendarBound: true });
});

test("Today keeps exact MISSING and EXPIRED Calendar bindings actionable", async () => {
  const { composioCalendarAccountStatus } = require("./panel-api.js");
  for (const providerState of ["MISSING", "EXPIRED"]) {
    const f = fixture();
    const serviceFetch = f.opts.fetchImpl;
    f.opts.composioCalendarAccountStatusImpl = composioCalendarAccountStatus;
    f.opts.fetchImpl = async (input, init = {}) => {
      const url = new URL(String(input));
      if (url.hostname === "backend.composio.dev") {
        if (providerState === "MISSING") {
          return { ok: false, status: 404, json: async () => ({ message: "not found" }) };
        }
        return { ok: true, status: 200, json: async () => ({
          id: f.row.calendar_connected_account_id,
          user_id: UID,
          toolkit_slug: "googlecalendar",
          status: "EXPIRED",
          is_disabled: false,
          enabled: true,
        }) };
      }
      return serviceFetch(input, init);
    };

    const snapshot = await buildTodaySnapshot(UID, f.opts);

    assert.equal(snapshot.setupState, "needs_calendar");
    assert.equal(snapshot.calendarState, "action_required");
    assert.equal(snapshot.calendarBound, true);
    assert.equal(f.calendarReads.length, 0);
  }
});

test("resume allows no saved home but requires the exact selected ACTIVE Calendar account", async () => {
  const noHome = fixture();
  Object.assign(noHome.row, { web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_subscription_id: "sub-active", paid: true, plan_status: "active" });
  const noHomeResponse = await call(noHome, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "resume" },
  });
  assert.equal(noHomeResponse.status, 200);
  assert.equal(noHome.row.home_address, null);
  assert.equal(noHome.preference.daily_automation_enabled, true);
  assert.deepEqual(noHome.controlRpcCalls, [{ p_uid: UID, p_calendar_account_id: "ca-selected-123", p_action: "resume" }]);

  const inactive = fixture({ composioCalendarAccountStatusImpl: async () => "DISABLED" });
  Object.assign(inactive.row, { web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_subscription_id: "sub-active", paid: true, plan_status: "active" });
  const inactiveResponse = await call(inactive, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "resume" },
  });
  assert.equal(inactiveResponse.status, 409);
  assert.equal(JSON.parse(inactiveResponse.body).error, "calendar_not_active");
  assert.deepEqual(inactive.controlRpcCalls, []);

  const active = fixture();
  Object.assign(active.row, { web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_subscription_id: "sub-active", paid: true, plan_status: "active" });
  const activeResponse = await call(active, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "resume" },
  });
  assert.equal(activeResponse.status, 200);
  assert.equal(active.preference.daily_automation_enabled, true);
  assert.deepEqual(active.controlRpcCalls, [{ p_uid: UID, p_calendar_account_id: "ca-selected-123", p_action: "resume" }]);
  assert.deepEqual(JSON.parse(activeResponse.body), { dailyAutomationEnabled: true, disconnectPending: false, enablePending: false, calendarBound: true });
});

test("resume cannot enable Calendar reads before a verified paid trial or active subscription", async () => {
  let statusReads = 0;
  const f = fixture({ composioCalendarAccountStatusImpl: async () => { statusReads++; return "ACTIVE"; } });
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "resume" },
  });
  assert.equal(response.status, 409);
  assert.equal(JSON.parse(response.body).error, "billing_required");
  assert.equal(statusReads, 0);
  assert.deepEqual(f.controlRpcCalls, []);
});

test("resume is rejected while Calendar enable readback is pending", async () => {
  const f = fixture();
  Object.assign(f.row, { web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_subscription_id: "sub-active", paid: true, plan_status: "active" });
  f.row.home_address = "自宅住所";
  markEnablePending(f.row);

  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "resume" },
  });

  assert.equal(response.status, 409);
  assert.equal(JSON.parse(response.body).error, "calendar_enable_pending");
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.deepEqual(f.controlRpcCalls, []);
});

test("Today snapshot exposes retained Calendar enable claim with controls paused", async () => {
  const f = fixture();
  markEnablePending(f.row);
  const snapshot = await buildTodaySnapshot(UID, f.opts);

  assert.equal(snapshot.enablePending, true);
  assert.equal(snapshot.dailyAutomationEnabled, false);
  assert.equal(snapshot.disconnectPending, false);
});

test("disconnect pauses first, disables and clears only the selected account", async () => {
  const f = fixture();
  f.preference.daily_automation_enabled = true;
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "disconnect" },
  });

  assert.equal(response.status, 200);
  const sequence = f.sequence.slice(f.sequence.indexOf("control_rpc:disconnect_begin"), f.sequence.indexOf("control_rpc:disconnect_finish") + 1);
  assert.ok(sequence.indexOf("control_rpc:disconnect_begin") < sequence.indexOf("preference_read"));
  assert.ok(sequence.indexOf("preference_read") < sequence.indexOf("calendar_disconnect"));
  assert.ok(sequence.indexOf("calendar_disconnect") < sequence.indexOf("calendar_status"));
  assert.ok(sequence.indexOf("calendar_status") < sequence.indexOf("control_rpc:disconnect_finish"));
  assert.deepEqual(f.disconnectCalls, [{ scope: { uid: UID }, connectedAccountId: "ca-selected-123" }]);
  assert.deepEqual(f.controlRpcCalls, [
    { p_uid: UID, p_calendar_account_id: "ca-selected-123", p_action: "disconnect_begin" },
    { p_uid: UID, p_calendar_account_id: "ca-selected-123", p_action: "disconnect_finish" },
  ]);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.preference.calendar_disconnect_pending, false);
  assert.equal(f.row.calendar_provider, null);
  assert.equal(f.row.calendar_connected_account_id, null);
  assert.deepEqual(JSON.parse(response.body), { dailyAutomationEnabled: false, disconnectPending: false, enablePending: false, calendarBound: false });
});

test("uncertain provider readback leaves the exact binding and persisted pause in place", async () => {
  const f = fixture({
    composioCalendarDisconnectImpl: async (scope, providerOpts) => {
      f.sequence.push("calendar_disconnect");
      f.disconnectCalls.push({ scope, connectedAccountId: providerOpts.connectedAccountId });
      throw new Error("provider_readback_failed");
    },
  });
  f.preference.daily_automation_enabled = true;
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "disconnect" },
  });

  assert.equal(response.status, 502);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.preference.calendar_disconnect_pending, true);
  assert.equal(f.row.calendar_connected_account_id, "ca-selected-123");
  assert.deepEqual(f.controlRpcCalls, [{ p_uid: UID, p_calendar_account_id: "ca-selected-123", p_action: "disconnect_begin" }]);
  assert.deepEqual(JSON.parse(response.body), { error: "control_unavailable", automationPaused: true });
});

test("Today reports persisted pause state and exact binding presence", async () => {
  const f = fixture();
  f.preference.daily_automation_enabled = false;
  const snapshot = await buildTodaySnapshot(UID, f.opts);

  assert.equal(snapshot.dailyAutomationEnabled, false);
  assert.equal(snapshot.calendarBound, true);
});

test("concurrent resume is rejected while disconnect is waiting on provider confirmation", async () => {
  const f = fixture();
  Object.assign(f.row, { web_first_travel_at: "2030-01-01T00:00:00.000Z", stripe_subscription_id: "sub-active", paid: true, plan_status: "active" });
  f.row.home_address = "自宅住所";
  f.preference.daily_automation_enabled = true;
  let providerStarted;
  const started = new Promise((resolve) => { providerStarted = resolve; });
  let releaseProvider;
  const providerGate = new Promise((resolve) => { releaseProvider = resolve; });
  let pendingDuringProvider;
  f.opts.composioCalendarDisconnectImpl = async (scope, providerOpts) => {
    f.sequence.push("calendar_disconnect");
    f.disconnectCalls.push({ scope, connectedAccountId: providerOpts.connectedAccountId });
    pendingDuringProvider = f.preference.calendar_disconnect_pending;
    providerStarted();
    await providerGate;
    f.providerStatus = "DISABLED";
    return { provider: "calendar", state: "action_required" };
  };

  const disconnectPromise = call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "disconnect" },
  });
  await started;
  const resumeResponse = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "resume" },
  });
  releaseProvider();
  const disconnectResponse = await disconnectPromise;

  assert.equal(pendingDuringProvider, true);
  assert.equal(resumeResponse.status, 409);
  assert.equal(JSON.parse(resumeResponse.body).error, "disconnect_pending");
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(disconnectResponse.status, 200);
});

test("Calendar event read failure retains persisted automation and disconnect fence state", async () => {
  const f = fixture();
  f.row.home_address = "自宅住所";
  f.preference.daily_automation_enabled = false;
  f.preference.calendar_disconnect_pending = true;
  f.opts.listEvents7dImpl = async () => { throw new Error("calendar_readback_failed"); };
  const snapshot = await buildTodaySnapshot(UID, f.opts);

  assert.equal(snapshot.setupState, "sync_pending");
  assert.equal(snapshot.dailyAutomationEnabled, false);
  assert.equal(snapshot.disconnectPending, true);
  assert.equal(snapshot.calendarBound, true);
});

test("disconnect retry resolves a previously disabled exact account and clears the fence", async () => {
  const f = fixture({
    composioCalendarDisconnectImpl: async () => { throw new Error("provider_readback_failed"); },
  });
  f.row.home_address = "自宅住所";
  const request = {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "disconnect" },
  };
  const first = await call(f, "POST", "/api/lm-web/travel/control", request);
  assert.equal(first.status, 502);
  assert.equal(f.preference.calendar_disconnect_pending, true);
  assert.equal(f.row.calendar_connected_account_id, "ca-selected-123");

  f.providerStatus = "DISABLED";
  f.opts.composioCalendarDisconnectImpl = async (scope, providerOpts) => {
    f.disconnectCalls.push({ scope, connectedAccountId: providerOpts.connectedAccountId });
    return { provider: "calendar", state: "action_required" };
  };
  const retry = await call(f, "POST", "/api/lm-web/travel/control", request);

  assert.equal(retry.status, 200);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.preference.calendar_disconnect_pending, false);
  assert.equal(f.row.calendar_connected_account_id, null);
  assert.deepEqual(f.controlRpcCalls.map((item) => item.p_action), ["disconnect_begin", "disconnect_begin", "disconnect_finish"]);
});

test("a delayed Web disconnect readback cannot re-enable Calendar after a concurrent retry finishes", async () => {
  const { composioCalendarAccountStatus, composioCalendarDisconnect } = require("./panel-api.js");
  const f = fixture();
  f.row.home_address = "自宅住所";
  f.preference.daily_automation_enabled = true;
  let firstReadbackStarted;
  const readbackStarted = new Promise((resolve) => { firstReadbackStarted = resolve; });
  let releaseReadback;
  const readbackGate = new Promise((resolve) => { releaseReadback = resolve; });
  const timeline = [];
  let providerDisabled = false;
  let accountReads = 0;
  const serviceFetch = f.opts.fetchImpl;
  f.opts.fetchImpl = async (input, init = {}) => {
    const url = new URL(String(input));
    if (url.hostname === "backend.composio.dev") {
      const method = init.method || "GET";
      if (url.pathname.endsWith("/status") && method === "PATCH") {
        const enabled = JSON.parse(init.body || "{}").enabled;
        timeline.push(`patch:${enabled}`);
        providerDisabled = enabled === false;
        if (providerDisabled) f.providerStatus = "DISABLED";
        return { ok: true, status: 200, json: async () => ({}) };
      }
      if (url.pathname.includes("/connected_accounts/")) {
        accountReads++;
        if (accountReads === 2) {
          firstReadbackStarted();
          await readbackGate;
          timeline.push("first_readback_unknown");
          return { ok: true, status: 200, json: async () => ({
            id: "ca-selected-123", user_id: UID, toolkit_slug: "googlecalendar",
            status: "EXPIRED", is_disabled: false, enabled: true,
          }) };
        }
        const account = providerDisabled ? {
          id: "ca-selected-123", user_id: UID, toolkit_slug: "googlecalendar",
          status: "INACTIVE", is_disabled: true, enabled: false,
        } : {
          id: "ca-selected-123", user_id: UID, toolkit_slug: "googlecalendar",
          status: "ACTIVE", is_disabled: false, enabled: true,
        };
        timeline.push(`read:${accountReads}:${account.status}`);
        return { ok: true, status: 200, json: async () => account };
      }
      throw new Error(`unexpected provider request: ${url.pathname}`);
    }
    if (url.pathname.endsWith("/rpc/control_lm_web_travel")
      && JSON.parse(init.body || "{}").p_action === "disconnect_finish") timeline.push("disconnect_finish");
    return serviceFetch(input, init);
  };
  f.opts.composioCalendarDisconnectImpl = composioCalendarDisconnect;
  f.opts.composioCalendarAccountStatusImpl = composioCalendarAccountStatus;
  const request = {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "disconnect" },
  };

  const firstDisconnect = call(f, "POST", "/api/lm-web/travel/control", request);
  await readbackStarted;
  const retryResponse = await call(f, "POST", "/api/lm-web/travel/control", request);
  assert.equal(retryResponse.status, 200);
  assert.equal(f.preference.calendar_disconnect_pending, false);
  assert.equal(f.row.calendar_connected_account_id, null);

  releaseReadback();
  const firstResponse = await firstDisconnect;

  assert.equal(firstResponse.status, 502);
  const finishIndex = timeline.indexOf("disconnect_finish");
  assert.ok(finishIndex >= 0);
  assert.doesNotMatch(timeline.slice(finishIndex + 1).join(","), /patch:true/);
  assert.deepEqual(timeline.filter((item) => item.startsWith("patch:")), ["patch:false"]);
});

test("disconnect before home setup seeds safe preferences without enabling automation", async () => {
  const f = fixture();
  f.preference = null;
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "disconnect" },
  });

  assert.equal(response.status, 200);
  assert.deepEqual(f.preference, {
    call_enabled: false,
    notifications_enabled: false,
    daily_automation_enabled: false,
    calendar_disconnect_pending: false,
  });
  assert.equal(f.row.calendar_connected_account_id, null);
});

test("pause before home setup seeds safe preferences without enabling automation", async () => {
  const f = fixture();
  f.preference = null;
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "pause" },
  });

  assert.equal(response.status, 200);
  assert.deepEqual(f.preference, {
    call_enabled: false,
    notifications_enabled: false,
    daily_automation_enabled: false,
    calendar_disconnect_pending: false,
  });
  assert.equal(f.row.calendar_connected_account_id, "ca-selected-123");
});

test("disconnect begin preserves existing call and notification preferences", async () => {
  const f = fixture();
  f.preference.call_enabled = true;
  f.preference.notifications_enabled = true;
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "disconnect" },
  });

  assert.equal(response.status, 200);
  assert.equal(f.preference.call_enabled, true);
  assert.equal(f.preference.notifications_enabled, true);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.preference.calendar_disconnect_pending, false);
});

test("pause preserves existing call and notification preferences", async () => {
  const f = fixture();
  f.preference.call_enabled = true;
  f.preference.notifications_enabled = true;
  const response = await call(f, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "pause" },
  });

  assert.equal(response.status, 200);
  assert.equal(f.preference.call_enabled, true);
  assert.equal(f.preference.notifications_enabled, true);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.preference.calendar_disconnect_pending, false);
});

test("Web initial-scan migration records only exact-tenant scan state and does not start a trial", () => {
  const controls = fs.readFileSync(path.join(__dirname, "../migrations/2026-10-06-z-lm-web-travel-controls.sql"), "utf8");
  assert.match(controls, /CREATE OR REPLACE FUNCTION public\.control_lm_web_travel/i);
  assert.match(controls, /telegram_chat_id\s+IS\s+NULL/i);
  assert.match(controls, /calendar_connected_account_id\s+IS\s+DISTINCT\s+FROM\s+p_calendar_account_id/i);
  const sql = fs.readFileSync(path.join(__dirname, "../migrations/2026-10-08-lm-web-initial-scan.sql"), "utf8");
  assert.match(sql, /ADD COLUMN IF NOT EXISTS web_initial_scan_completed_at timestamptz/i);
  assert.match(sql, /ADD COLUMN IF NOT EXISTS web_first_travel_at timestamptz/i);
  assert.match(sql, /CREATE OR REPLACE FUNCTION public\.record_lm_web_initial_scan/i);
  assert.match(sql, /WHERE uid = p_uid AND telegram_chat_id IS NULL/i);
  assert.match(sql, /calendar_connected_account_id IS DISTINCT FROM p_calendar_account_id/i);
  assert.match(sql, /calendar_disconnect_pending/i);
  assert.match(sql, /calendar_enable_pending/i);
  assert.match(sql, /GRANT EXECUTE ON FUNCTION public\.record_lm_web_initial_scan[^;]* TO service_role/i);
  assert.match(sql, /CREATE OR REPLACE FUNCTION public\.control_lm_web_travel/i);
  const controlSql = sql.slice(sql.indexOf("CREATE OR REPLACE FUNCTION public.control_lm_web_travel"),
    sql.indexOf("REVOKE ALL ON FUNCTION public.control_lm_web_travel"));
  assert.doesNotMatch(controlSql, /home_required|nullif\(trim\(user_row\.home_address\)/i);
  assert.doesNotMatch(sql, /trial_expires_at\s*=\s*coalesce\s*\([^;]*3 days/i);
  const scanSql = sql.slice(sql.indexOf("CREATE OR REPLACE FUNCTION public.record_lm_web_initial_scan"),
    sql.indexOf("REVOKE ALL ON FUNCTION public.record_lm_web_initial_scan"));
  assert.doesNotMatch(scanSql, /event_title|event_location|home_address/i);
  const legacySetupSql = sql.slice(sql.indexOf("CREATE OR REPLACE FUNCTION public.complete_lm_web_travel_setup"));
  assert.doesNotMatch(legacySetupSql, /trial_expires_at\s*=\s*coalesce\s*\([^;]*3 days/i);
  assert.doesNotMatch(legacySetupSql, /ON CONFLICT\s*\(uid\)\s*DO UPDATE SET[\s\S]*daily_automation_enabled\s*=\s*true/i);
});
