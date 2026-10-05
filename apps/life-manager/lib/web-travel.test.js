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
  const travelExpectedAccountIds = [];
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
      row.home_address = body.p_home_address;
      row.trial_expires_at ||= TRIAL_EXPIRES_AT;
      preferenceWrites++;
      return { ok: true, status: 200, json: async () => ({ trial_expires_at: row.trial_expires_at }) };
    }
    if (requestUrl.pathname.endsWith("/lm_users")) {
      sequence.push("user_row");
      assert.equal((requestUrl.searchParams.get("select") || "").includes("call_time_zone"), false);
      return { ok: true, status: 200, json: async () => [{ ...row }] };
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
      return "ACTIVE";
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
  return { events, fetchImpl, opts, row, rpcCalls, sequence, calendarReads, travelExpectedAccountIds,
    get preferenceWrites() { return preferenceWrites; }, get travelCalls() { return travelCalls; } };
}

async function call(fixtureValue, method, url, requestOptions = {}) {
  const response = makeResponse();
  await handleWebTravelRequest(makeRequest(method, url, requestOptions), response, fixtureValue.opts);
  return response;
}

test("setup stores home and starts one trial only for active unbound web user", async () => {
  const f = fixture();
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
  assert.equal(f.sequence[f.sequence.indexOf("travel") - 1], "unbound");
  assert.ok(f.sequence.indexOf("travel") < f.sequence.indexOf("calendar_read"));
  const result = JSON.parse(response.body);
  assert.equal(result.setupState, "ready");
  assert.equal(result.syncState, "travel_added");
  assert.equal(result.departureAt, "2030-01-01T00:35:00.000Z");
});

test("ignores client uid and paid fields", async () => {
  const f = fixture();
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

test("missing Calendar helper readback remains pending", async () => {
  let travelAttempts = 0;
  const f = fixture({ travelUserOnceImpl: async () => { travelAttempts++; return { inserted: 1 }; }, calendar: { async listEventsRaw() { return [event()]; } } });
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
