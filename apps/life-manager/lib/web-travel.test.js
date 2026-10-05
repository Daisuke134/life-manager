"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { buildTodaySnapshot, completeWebTravelSetup, handleWebTravelRequest } = require("./web-travel.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const OTHER_UID = "lm_22222222-2222-4222-8222-222222222222";
const ORIGIN = "https://life.example";
const NOW = Date.parse("2030-01-01T08:00:00+09:00");
const TRIAL_EXPIRES_AT = "2030-01-04T00:00:00.000Z";

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
  };
}

function fixture(overrides = {}) {
  const row = {
    uid: UID,
    telegram_chat_id: null,
    calendar_provider: "composio_gcal",
    calendar_connected_account_id: "ca-selected-123",
    home_address: null,
    trial_expires_at: null,
    paid: false,
  };
  const events = [event()];
  const calendarReads = [];
  const sequence = [];
  const rpcCalls = [];
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
  let preferenceWrites = 0;
  let travelCalls = 0;
  const fetchImpl = async (url, init = {}) => {
    const requestUrl = new URL(String(url));
    if (requestUrl.pathname.endsWith("/rpc/complete_lm_web_travel_setup")) {
      sequence.push("rpc");
      const body = JSON.parse(init.body || "{}");
      rpcCalls.push(body);
      if (body.p_calendar_account_id !== row.calendar_connected_account_id) {
        return { ok: false, status: 400, json: async () => ({ message: "calendar_account_changed" }) };
      }
      if (preference && preference.calendar_disconnect_pending) {
        return { ok: false, status: 400, json: async () => ({ message: "calendar_disconnect_pending" }) };
      }
      row.home_address = body.p_home_address;
      row.trial_expires_at ||= TRIAL_EXPIRES_AT;
      if (!preference) preference = { call_enabled: false, notifications_enabled: false, daily_automation_enabled: true, calendar_disconnect_pending: false };
      preference.call_enabled = false;
      preference.notifications_enabled = false;
      preferenceWrites++;
      return { ok: true, status: 200, json: async () => ({ trial_expires_at: row.trial_expires_at }) };
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
    travelUserOnceImpl: async (user) => {
      sequence.push("travel");
      travelCalls++;
      assert.equal(user.uid, UID);
      assert.equal(user.daily_automation_enabled, true);
      assert.equal(user.home_address, row.home_address);
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
  return { events, fetchImpl, opts, row, rpcCalls, controlRpcCalls, disconnectCalls, get preference() { return preference; }, set preference(value) { preference = value; }, sequence, calendarReads, travelExpectedAccountIds,
    get providerStatus() { return providerStatus; }, set providerStatus(value) { providerStatus = value; },
    get preferenceWrites() { return preferenceWrites; }, get travelCalls() { return travelCalls; } };
}

async function call(fixtureValue, method, url, requestOptions = {}) {
  const response = makeResponse();
  await handleWebTravelRequest(makeRequest(method, url, requestOptions), response, fixtureValue.opts);
  return response;
}

test("setup stores home and starts one trial only for active unbound web user", async () => {
  const f = fixture();
  f.preference = null;
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "  自宅住所  " },
  });

  assert.equal(response.status, 200);
  assert.equal(f.row.home_address, "自宅住所");
  assert.equal(f.row.trial_expires_at, TRIAL_EXPIRES_AT);
  assert.deepEqual(f.rpcCalls, [{ p_uid: UID, p_home_address: "自宅住所", p_calendar_account_id: "ca-selected-123" }]);
  assert.equal(f.travelCalls, 1);
  assert.deepEqual(f.travelExpectedAccountIds, ["ca-selected-123"]);
  assert.equal(f.calendarReads[0].expectedCalendarAccountId, "ca-selected-123");
  assert.ok(f.sequence.indexOf("calendar_status") < f.sequence.indexOf("rpc"));
  assert.ok(f.sequence.indexOf("rpc") < f.sequence.indexOf("travel"));
  assert.equal(f.sequence[f.sequence.indexOf("travel") - 2], "unbound");
  assert.equal(f.sequence[f.sequence.indexOf("travel") - 1], "preference_read");
  assert.ok(f.sequence.indexOf("travel") < f.sequence.indexOf("calendar_read"));
  const result = JSON.parse(response.body);
  assert.equal(result.setupState, "ready");
  assert.equal(result.syncState, "travel_added");
  assert.equal(result.departureAt, "2030-01-01T00:35:00.000Z");
});

test("ignores client uid and paid fields", async () => {
  const f = fixture();
  f.preference = null;
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN,
    contentType: "application/json",
    csrf: "csrf-token",
    body: { homeAddress: "自宅住所", uid: OTHER_UID, paid: true, telegram_chat_id: "attacker", phone: "+819000000000" },
  });

  assert.equal(response.status, 200);
  assert.deepEqual(f.rpcCalls, [{ p_uid: UID, p_home_address: "自宅住所", p_calendar_account_id: "ca-selected-123" }]);
  assert.equal(f.row.paid, false);
  assert.equal(f.row.telegram_chat_id, null);
});

test("calendar readback must be ACTIVE before setup writes", async () => {
  let rpcCount = 0, travelCount = 0, eventReads = 0;
  const f = fixture({
    composioCalendarAccountStatusImpl: async () => "DISABLED",
    travelUserOnceImpl: async () => { travelCount++; },
    fetchImpl: async (url, init = {}) => {
      if (String(url).includes("/rpc/complete_lm_web_travel_setup")) rpcCount++;
      return fixture().fetchImpl(url, init);
    },
    calendar: { async listEventsRaw() { eventReads++; return []; } },
  });
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "自宅住所" },
  });

  assert.equal(response.status, 409);
  assert.equal(rpcCount, 0);
  assert.equal(travelCount, 0);
  assert.equal(eventReads, 0);
});

test("setup during pending disconnect makes no home, trial, preference, or Travel mutation", async () => {
  const f = fixture();
  f.preference.daily_automation_enabled = false;
  f.preference.calendar_disconnect_pending = true;
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "自宅住所" },
  });

  assert.equal(response.status, 409);
  assert.equal(JSON.parse(response.body).error, "disconnect_pending");
  assert.equal(f.row.home_address, null);
  assert.equal(f.row.trial_expires_at, null);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.preference.calendar_disconnect_pending, true);
  assert.equal(f.preferenceWrites, 0);
  assert.equal(f.travelCalls, 0);
});

test("setup preserves an existing pause and does not dispatch immediate Travel", async () => {
  const f = fixture();
  f.preference.daily_automation_enabled = false;
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "自宅住所" },
  });

  assert.equal(response.status, 200);
  assert.equal(f.row.home_address, "自宅住所");
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.travelCalls, 0);
});

test("setup rechecks persisted pause after Calendar ACTIVE readback before Travel dispatch", async () => {
  const f = fixture();
  f.preference.daily_automation_enabled = true;
  let statusReads = 0;
  f.opts.composioCalendarAccountStatusImpl = async (scope, accountId) => {
    statusReads++;
    assert.deepEqual(scope, { uid: UID });
    assert.equal(accountId, f.row.calendar_connected_account_id);
    if (statusReads === 2) f.preference.daily_automation_enabled = false;
    return "ACTIVE";
  };
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "自宅住所" },
  });

  assert.equal(response.status, 200);
  assert.equal(statusReads >= 2, true);
  assert.equal(f.preference.daily_automation_enabled, false);
  assert.equal(f.travelCalls, 0);
});

test("home address length is validated before provider activity or setup RPC", async () => {
  const f = fixture();
  const response = await call(f, "POST", "/api/lm-web/setup", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "x".repeat(241) },
  });
  assert.equal(response.status, 400);
  assert.equal(f.rpcCalls.length, 0);
  assert.equal(f.sequence.includes("calendar_status"), false);
  assert.equal(f.travelCalls, 0);
});

test("missing home and a locationless next event remain actionable states", async () => {
  const missingHome = fixture({ calendar: { async listEventsRaw() { return [event()]; } } });
  const noHomeSnapshot = await buildTodaySnapshot(UID, missingHome.opts);
  assert.equal(noHomeSnapshot.setupState, "needs_home");
  assert.equal(noHomeSnapshot.nextEvent.location, "渋谷ヒカリエ");
  assert.equal(noHomeSnapshot.travelBlock, null);

  const locationless = fixture({ calendar: { async listEventsRaw() { return [event("event-no-location", "")]; } } });
  locationless.row.home_address = "自宅住所";
  const locationlessSnapshot = await buildTodaySnapshot(UID, locationless.opts);
  assert.equal(locationlessSnapshot.setupState, "ready");
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
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "自宅住所" },
  });
  const result = JSON.parse(response.body);
  assert.equal(response.status, 200);
  assert.equal(result.setupState, "sync_pending");
  assert.equal(result.syncState, "sync_pending");
  assert.equal(result.travelBlock, null);
  assert.equal(result.departureAt, null);
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
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "自宅住所" },
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
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "自宅住所" },
  });
  const result = JSON.parse(response.body);

  assert.equal(response.status, 200);
  assert.equal(result.nextEvent.id, "event-1");
  assert.notEqual(result.travelBlock.endMs, result.nextEvent.startMs);
  assert.equal(result.syncState, "travel_verified");
});

test("setup RPC rejects a Calendar account changed after ACTIVE readback", async () => {
  const f = fixture();
  f.opts.composioCalendarAccountStatusImpl = async (scope, accountId) => {
    assert.deepEqual(scope, { uid: UID });
    assert.equal(accountId, "ca-selected-123");
    f.row.calendar_connected_account_id = "ca-replaced-456";
    return "ACTIVE";
  };

  await assert.rejects(
    () => completeWebTravelSetup(UID, "自宅住所", f.opts),
    (error) => error.status === 409 && error.code === "calendar_account_changed",
  );
  assert.deepEqual(f.rpcCalls, [{ p_uid: UID, p_home_address: "自宅住所", p_calendar_account_id: "ca-selected-123" }]);
  assert.equal(f.row.home_address, null);
  assert.equal(f.row.trial_expires_at, null);
  assert.equal(f.preferenceWrites, 0);
});

test("repeated setup keeps one trial and shared travel replay yields one helper", async () => {
  const f = fixture();
  f.preference = null;
  const request = {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { homeAddress: "自宅住所" },
  };
  await call(f, "POST", "/api/lm-web/setup", request);
  const firstTrial = f.row.trial_expires_at;
  await call(f, "POST", "/api/lm-web/setup", request);

  assert.equal(f.row.trial_expires_at, firstTrial);
  assert.equal(f.travelCalls, 2, "each committed setup invokes the shared owner once");
  assert.equal(f.events.filter((item) => String(item.summary || "").startsWith("[Travel]")).length, 1);
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

test("setup RPC locks and updates only the Web-owned setup fields", () => {
  const sql = fs.readFileSync(path.join(__dirname, "../migrations/2026-10-06-lm-web-travel-setup.sql"), "utf8");
  assert.match(sql, /FOR UPDATE/i);
  assert.match(sql, /telegram_chat_id\s+IS\s+NULL/i);
  assert.match(sql, /calendar_provider\s+IS\s+DISTINCT\s+FROM\s+'composio_gcal'/i);
  assert.match(sql, /calendar_connected_account_id/i);
  assert.match(sql, /p_calendar_account_id\s+text/i);
  assert.match(sql, /p_calendar_account_id\s+IS\s+NULL/i);
  assert.match(sql, /p_calendar_account_id\s*!~\s*'\^\[A-Za-z0-9_\-\]\{3,128\}\$'/i);
  assert.match(sql, /user_row\.calendar_connected_account_id\s+IS\s+DISTINCT\s+FROM\s+p_calendar_account_id/i);
  assert.ok(sql.indexOf("user_row.calendar_connected_account_id IS DISTINCT FROM p_calendar_account_id")
    < sql.indexOf("UPDATE public.lm_users"), "the locked account match must precede all setup writes");
  assert.match(sql, /trial_expires_at\s*=\s*coalesce\s*\([^;]*now\(\)\s*\+\s*interval\s+'3 days'/is);
  assert.match(sql, /home_address\s*=\s*home_value/i);
  assert.match(sql, /call_enabled\s*=\s*false/i);
  assert.match(sql, /notifications_enabled\s*=\s*false/i);
  assert.match(sql, /daily_automation_enabled\s*=\s*true/i);
  assert.doesNotMatch(sql, /\bpaid\b|\bphone\s*=|tg_onboard_stage|telegram_chat_id\s*=/i);
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
  assert.deepEqual(JSON.parse(response.body), { dailyAutomationEnabled: false, disconnectPending: false, calendarBound: true });
});

test("resume requires a saved home and the exact selected ACTIVE Calendar account", async () => {
  const noHome = fixture();
  const noHomeResponse = await call(noHome, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "resume" },
  });
  assert.equal(noHomeResponse.status, 409);
  assert.equal(JSON.parse(noHomeResponse.body).error, "home_required");
  assert.deepEqual(noHome.controlRpcCalls, []);

  const inactive = fixture({ composioCalendarAccountStatusImpl: async () => "DISABLED" });
  inactive.row.home_address = "自宅住所";
  const inactiveResponse = await call(inactive, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "resume" },
  });
  assert.equal(inactiveResponse.status, 409);
  assert.equal(JSON.parse(inactiveResponse.body).error, "calendar_not_active");
  assert.deepEqual(inactive.controlRpcCalls, []);

  const active = fixture();
  active.row.home_address = "自宅住所";
  const activeResponse = await call(active, "POST", "/api/lm-web/travel/control", {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { action: "resume" },
  });
  assert.equal(activeResponse.status, 200);
  assert.equal(active.preference.daily_automation_enabled, true);
  assert.deepEqual(active.controlRpcCalls, [{ p_uid: UID, p_calendar_account_id: "ca-selected-123", p_action: "resume" }]);
  assert.deepEqual(JSON.parse(activeResponse.body), { dailyAutomationEnabled: true, disconnectPending: false, calendarBound: true });
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
  assert.deepEqual(JSON.parse(response.body), { dailyAutomationEnabled: false, disconnectPending: false, calendarBound: false });
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

test("travel-control RPC locks, verifies the NULL-Telegram user and account, and updates only Web-owned fields", () => {
  const sql = fs.readFileSync(path.join(__dirname, "../migrations/2026-10-06-z-lm-web-travel-controls.sql"), "utf8");
  assert.match(sql, /ADD COLUMN IF NOT EXISTS calendar_disconnect_pending boolean NOT NULL DEFAULT false/i);
  assert.match(sql, /FOR UPDATE/i);
  assert.match(sql, /telegram_chat_id\s+IS\s+NULL/i);
  assert.match(sql, /calendar_connected_account_id\s+IS\s+DISTINCT\s+FROM\s+p_calendar_account_id/i);
  assert.match(sql, /calendar_provider\s+IS\s+DISTINCT\s+FROM\s+'composio_gcal'/i);
  assert.match(sql, /p_action\s*=\s*'disconnect_begin'/i);
  assert.match(sql, /p_action\s*=\s*'disconnect_finish'/i);
  assert.match(sql, /calendar_disconnect_pending\s*=\s*true/i);
  assert.match(sql, /calendar_disconnect_pending\s*=\s*false/i);
  assert.match(sql, /VALUES\s*\(p_uid, false, false, false, true\)/i);
  assert.match(sql, /ON CONFLICT\s*\(uid\) DO UPDATE SET\s+daily_automation_enabled = false,\s+calendar_disconnect_pending = true/i);
  assert.match(sql, /VALUES\s*\(p_uid, false, false, false, false\)/i);
  assert.match(sql, /ON CONFLICT\s*\(uid\) DO UPDATE SET daily_automation_enabled = false/i);
  assert.match(sql, /calendar_disconnect_pending\s+THEN\s+RAISE EXCEPTION 'calendar_disconnect_pending'/i);
  assert.match(sql, /IF p_action = 'pause' THEN[\s\S]*?INSERT INTO public\.lm_panel_preferences[\s\S]*?VALUES\s*\(p_uid, false, false, false, false\)\s+ON CONFLICT\s*\(uid\) DO UPDATE SET daily_automation_enabled = false;/i);
  assert.match(sql, /calendar_provider\s*=\s*NULL/i);
  assert.match(sql, /calendar_connected_account_id\s*=\s*NULL/i);
  const controlSql = sql.slice(0, sql.indexOf("CREATE OR REPLACE FUNCTION public.complete_lm_web_travel_setup"));
  assert.doesNotMatch(controlSql, /\bpaid\b|\btrial_expires_at\s*=|\bhome_address\s*=|\bcall_enabled\s*=|\bnotifications_enabled\s*=/i);
  assert.ok(sql.search(/user_row\.calendar_connected_account_id\s+IS DISTINCT FROM p_calendar_account_id/i)
    < sql.indexOf("UPDATE public.lm_panel_preferences"), "the locked account match must precede preference writes");
  const setupSql = sql.slice(sql.indexOf("CREATE OR REPLACE FUNCTION public.complete_lm_web_travel_setup"));
  assert.notEqual(setupSql, sql, "the ordered controls migration must reapply setup with the fence");
  assert.match(setupSql, /preference_row\.calendar_disconnect_pending/i);
  assert.match(setupSql, /IF preference_exists THEN[\s\S]*?SET call_enabled = false,[\s\S]*?notifications_enabled = false/i);
  assert.doesNotMatch(setupSql, /UPDATE public\.lm_panel_preferences[\s\S]*daily_automation_enabled\s*=/i);
  assert.match(setupSql, /preference_exists\s+AND\s+preference_row\.calendar_disconnect_pending[\s\S]*?RAISE EXCEPTION 'calendar_disconnect_pending'/i);
  assert.ok(setupSql.indexOf("RAISE EXCEPTION 'calendar_disconnect_pending'") < setupSql.indexOf("UPDATE public.lm_users"),
    "the pending fence must be checked before address or trial updates");
  assert.match(setupSql, /VALUES\s*\(p_uid, false, false, true, false\)/i);
  assert.doesNotMatch(setupSql, /ON CONFLICT\s*\(uid\)\s*DO UPDATE SET[\s\S]*daily_automation_enabled\s*=\s*true/i);
});
