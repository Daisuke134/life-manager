"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { assertWebUserUnbound, createWebCalendarStore, handleWebCalendarRequest } = require("./web-calendar.js");
const { handleWebTravelRequest } = require("./web-travel.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";
const OTHER_UID = "lm_22222222-2222-4222-8222-222222222222";
const ORIGIN = "https://life.example";
const STATE = "s".repeat(43);

function makeRequest(method, url, { origin, contentType, csrf, body } = {}) {
  const rawBody = body === undefined ? "" : JSON.stringify(body);
  return {
    method,
    url,
    testBody: body,
    headers: {
      ...(origin ? { origin } : {}),
      ...(contentType ? { "content-type": contentType } : {}),
      ...(csrf ? { "x-lm-web-csrf": csrf } : {}),
    },
    async *[Symbol.asyncIterator]() {
      if (rawBody) yield Buffer.from(rawBody);
    },
  };
}

function makeResponse() {
  return {
    status: 0,
    headers: {},
    body: "",
    writeHead(status, headers = {}) { this.status = status; this.headers = { ...this.headers, ...headers }; },
    setHeader(name, value) { this.headers[name] = value; },
    end(body = "") { this.body = String(body); },
  };
}

async function call(method, url, options = {}, request = {}) {
  const response = makeResponse();
  await handleWebCalendarRequest(makeRequest(method, url, request), response, options);
  return response;
}

function options(overrides = {}) {
  return {
    publicOrigin: ORIGIN,
    supaUrl: "https://supabase.example",
    supaKey: "service-role-key",
    env: { COMPOSIO_API_KEY: "provider-key", COMPOSIO_GCAL_AUTH_CONFIG: "google-calendar" },
    resolveWebUserImpl: async () => ({ uid: UID, subject: "subject", email: "user@example.test", csrf: "csrf-token" }),
    assertWebUserUnboundImpl: async () => true,
    readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: null, disconnectPending: false, enablePending: false }),
    fetchImpl: async () => ({ ok: true, json: async () => [{ uid: UID, telegram_chat_id: null, calendar_provider: null, calendar_connected_account_id: null }] }),
    readJsonImpl: async (req) => req.testBody === undefined ? {} : req.testBody,
    composioCalendarAccountsImpl: async () => [],
    ...overrides,
  };
}

function makeStaleCalendarHarness({ selectedId = "ca-stale-123", selectedResponse, accounts = [] } = {}) {
  const state = {
    row: {
      uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal",
      calendar_connected_account_id: selectedId,
    },
    accountListReads: 0,
    providerAccountReads: [],
    providerPatches: [],
    bindings: [],
    oauth: [],
  };
  const response = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
  const fetchImpl = async (input, init = {}) => {
    const url = new URL(String(input));
    const method = init.method || "GET";
    if (url.hostname === "supabase.example") {
      if (url.pathname.endsWith("/rpc/bind_lm_web_calendar_account")) {
        const body = JSON.parse(init.body || "{}");
        state.bindings.push(body);
        if (body.p_expected_calendar_provider !== state.row.calendar_provider
          || body.p_expected_calendar_account_id !== state.row.calendar_connected_account_id) {
          return response({ message: "calendar_account_changed" }, 400);
        }
        state.row.calendar_provider = "composio_gcal";
        state.row.calendar_connected_account_id = body.p_connected_account_id;
        return response(true);
      }
      if (url.pathname.endsWith("/lm_users")) return response([{ ...state.row }]);
    }
    if (url.hostname === "backend.composio.dev") {
      if (url.pathname.endsWith("/api/v3/connected_accounts")) {
        state.accountListReads++;
        return response({ items: accounts });
      }
      if (url.pathname.includes("/api/v3.1/connected_accounts/")) {
        const accountId = decodeURIComponent(url.pathname.split("/").at(-1));
        state.providerAccountReads.push(accountId);
        if (accountId === selectedId) return typeof selectedResponse === "function"
          ? selectedResponse() : selectedResponse;
        const account = accounts.find((item) => item.id === accountId);
        return account ? response(account) : response({ message: "not found" }, 404);
      }
      if (url.pathname.endsWith("/status") && method === "PATCH") {
        state.providerPatches.push(JSON.parse(init.body || "{}").enabled);
        return response({});
      }
    }
    throw new Error(`unexpected stale Calendar request: ${url.hostname}${url.pathname}`);
  };
  const opts = options({
    fetchImpl,
    composioCalendarAccountsImpl: undefined,
    webCalendarStore: {
      createWebOAuthState: async () => { state.oauth.push("state"); return true; },
      attachWebOAuthAccount: async (_scope, _digest, accountId) => { state.oauth.push(`attached:${accountId}`); return true; },
    },
    startCalendarOAuthImpl: async () => {
      state.oauth.push("oauth");
      return { connectedAccountId: "ca-new-456", redirectUrl: "https://accounts.example/connect" };
    },
  });
  return { opts, state, response };
}

function makeEnableHarness(startCalendarImpl = async (state) => {
  state.providerStatus = "ACTIVE";
  return { provider: "calendar", state: "connected" };
}) {
  const state = {
    row: {
      uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal",
      calendar_connected_account_id: "ca-selected", calendar_enable_pending: false,
      calendar_enable_claim_id: null, calendar_enable_claimed_at: null,
      home_address: "home", trial_expires_at: null, paid: false,
    },
    preference: {
      call_enabled: false, notifications_enabled: false,
      daily_automation_enabled: true, calendar_disconnect_pending: false,
    },
    providerStatus: "DISABLED",
    calls: [],
    providerEnableCalls: 0,
    providerDisableCalls: 0,
    recoverCalls: 0,
    finishClaimIds: [],
    beginClaimIds: [],
    lastIssuedClaimId: null,
  };
  const fetchImpl = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const method = init.method || "GET";
    if (parsed.pathname.endsWith("/rpc/begin_lm_web_calendar_enable")) {
      state.calls.push("begin_enable");
      const body = JSON.parse(init.body || "{}");
      if (state.preference.calendar_disconnect_pending) {
        return { ok: false, status: 400, json: async () => ({ message: "calendar_disconnect_pending" }) };
      }
      const claimId = body.p_claim_id || "2e59df08-f437-44fd-bbe9-5d835ba467f0";
      state.beginClaimIds.push(body.p_claim_id || null);
      state.row.calendar_enable_pending = true;
      state.row.calendar_enable_claim_id = claimId;
      state.row.calendar_enable_claimed_at = new Date().toISOString();
      state.lastIssuedClaimId = claimId;
      return { ok: true, status: 200, json: async () => true };
    }
    if (parsed.pathname.endsWith("/rpc/recover_lm_web_calendar_enable")) {
      state.calls.push("recover_enable");
      state.recoverCalls++;
      const body = JSON.parse(init.body || "{}");
      const claimedAt = Date.parse(state.row.calendar_enable_claimed_at || "");
      if (!state.row.calendar_enable_pending || body.p_expected_claim_id !== state.row.calendar_enable_claim_id
        || !Number.isFinite(claimedAt) || Date.now() - claimedAt < 120_000
        || state.preference.calendar_disconnect_pending) {
        return { ok: true, status: 200, json: async () => false };
      }
      state.row.calendar_enable_claim_id = body.p_new_claim_id;
      state.row.calendar_enable_claimed_at = new Date().toISOString();
      state.lastIssuedClaimId = body.p_new_claim_id;
      return { ok: true, status: 200, json: async () => true };
    }
    if (parsed.pathname.endsWith("/rpc/finish_lm_web_calendar_enable")) {
      state.calls.push("finish_enable");
      const body = JSON.parse(init.body || "{}");
      state.finishClaimIds.push(body.p_claim_id || null);
      if (!state.row.calendar_enable_pending
        || (body.p_claim_id && body.p_claim_id !== state.row.calendar_enable_claim_id)) {
        return { ok: true, status: 200, json: async () => false };
      }
      state.row.calendar_enable_pending = false;
      state.row.calendar_enable_claim_id = null;
      state.row.calendar_enable_claimed_at = null;
      return { ok: true, status: 200, json: async () => true };
    }
    if (parsed.pathname.endsWith("/rpc/bind_lm_web_calendar_account")) {
      state.calls.push("bind");
      if (state.preference.calendar_disconnect_pending || state.row.calendar_enable_pending) {
        return { ok: false, status: 400, json: async () => ({ message: "calendar_operation_pending" }) };
      }
      const body = JSON.parse(init.body || "{}");
      if (body.p_expected_calendar_provider !== state.row.calendar_provider
        || body.p_expected_calendar_account_id !== state.row.calendar_connected_account_id) {
        return { ok: false, status: 400, json: async () => ({ message: "calendar_account_changed" }) };
      }
      state.row.calendar_provider = "composio_gcal";
      state.row.calendar_connected_account_id = body.p_connected_account_id;
      return { ok: true, status: 200, json: async () => true };
    }
    if (parsed.pathname.endsWith("/rpc/control_lm_web_travel")) {
      const body = JSON.parse(init.body || "{}");
      state.calls.push(`control_${body.p_action}`);
      if (body.p_action === "disconnect_begin") {
        if (state.row.calendar_enable_pending) {
          return { ok: false, status: 400, json: async () => ({ message: "calendar_enable_pending" }) };
        }
        state.preference.daily_automation_enabled = false;
        state.preference.calendar_disconnect_pending = true;
        return { ok: true, status: 200, json: async () => true };
      }
      return { ok: false, status: 400, json: async () => ({ message: "unexpected_control_action" }) };
    }
    if (parsed.pathname.endsWith("/lm_panel_preferences")) {
      return { ok: true, status: 200, json: async () => [{ ...state.preference }] };
    }
    if (parsed.pathname.endsWith("/lm_users")) {
      if (method === "PATCH") {
        state.calls.push("direct_patch");
        Object.assign(state.row, JSON.parse(init.body || "{}"));
        return { ok: true, status: 200, json: async () => [{ ...state.row }] };
      }
      return { ok: true, status: 200, json: async () => [{ ...state.row }] };
    }
    throw new Error(`unexpected service request: ${parsed.pathname}`);
  };
  const opts = options({
    fetchImpl,
    readWebTravelControlStateImpl: async () => ({
      dailyAutomationEnabled: state.preference.daily_automation_enabled,
      disconnectPending: state.preference.calendar_disconnect_pending,
      enablePending: state.row.calendar_enable_pending,
      ...(state.row.calendar_enable_pending ? {
        enableClaimId: state.row.calendar_enable_claim_id,
        enableClaimedAt: state.row.calendar_enable_claimed_at,
      } : {}),
    }),
    composioCalendarAccountStatusImpl: async (scope, accountId) => {
      assert.deepEqual(scope, { uid: UID });
      assert.equal(accountId, state.row.calendar_connected_account_id);
      state.calls.push(`provider_status:${state.providerStatus}`);
      return state.providerStatus;
    },
    composioCalendarStartImpl: async (scope, providerOpts) => {
      assert.deepEqual(scope, { uid: UID });
      assert.equal(providerOpts.connectedAccountId, "ca-selected");
      state.providerEnableCalls++;
      state.calls.push("provider_enable");
      return startCalendarImpl(state, scope, providerOpts);
    },
    composioCalendarDisconnectImpl: async (scope, providerOpts) => {
      assert.deepEqual(scope, { uid: UID });
      assert.equal(providerOpts.connectedAccountId, "ca-selected");
      state.providerDisableCalls++;
      state.calls.push("provider_disable");
      state.providerStatus = "INACTIVE";
      return { provider: "calendar", state: "action_required" };
    },
  });
  return { state, opts };
}

async function callTravelControl(opts, action) {
  const response = makeResponse();
  await handleWebTravelRequest({
    method: "POST",
    url: "/api/lm-web/travel/control",
    testBody: { action },
    headers: { origin: ORIGIN, "content-type": "application/json", "x-lm-web-csrf": "csrf-token" },
  }, response, opts);
  return response;
}

test("calendar status is connected only for the persisted exact ACTIVE account", async () => {
  const row = { uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" };
  let writes = 0, accountReads = 0, aggregateReads = 0;
  const fetchImpl = async (_url, init = {}) => {
    if (init.method === "PATCH") writes++;
    return { ok: true, json: async () => [{ ...row }] };
  };
  const connected = await call("GET", "/api/lm-web/calendar/status", options({
    fetchImpl,
    composioCalendarStatusImpl: async () => { aggregateReads++; return "ACTIVE"; },
    composioCalendarAccountStatusImpl: async (scope, id) => {
      accountReads++;
      assert.deepEqual(scope, { uid: UID });
      assert.equal(id, "ca-selected");
      return "ACTIVE";
    },
  }));
  assert.equal(connected.status, 200);
  assert.deepEqual(JSON.parse(connected.body), { connected: true, state: "connected" });
  assert.deepEqual([writes, accountReads, aggregateReads], [0, 1, 0]);

  const unbound = await call("GET", "/api/lm-web/calendar/status", options({
    fetchImpl: async () => ({ ok: true, json: async () => [{ uid: UID, telegram_chat_id: null, calendar_provider: null, calendar_connected_account_id: null }] }),
    composioCalendarStatusImpl: async () => "ACTIVE",
  }));
  assert.equal(unbound.status, 200);
  assert.deepEqual(JSON.parse(unbound.body), { connected: false, state: "action_required" });

  let reads = 0;
  const rebound = await call("GET", "/api/lm-web/calendar/status", options({
    fetchImpl: async () => ({ ok: true, json: async () => [
      reads++ === 0 ? { ...row } : { ...row, calendar_connected_account_id: "ca-rebound" },
    ] }),
    composioCalendarAccountStatusImpl: async () => "ACTIVE",
  }));
  assert.deepEqual(JSON.parse(rebound.body), { connected: false, state: "action_required" });
  assert.equal(reads, 2, "status rereads the marker after the exact provider check");

  for (const statusValue of ["DISABLED", "MISSING"]) {
    const response = await call("GET", "/api/lm-web/calendar/status", options({
      fetchImpl,
      composioCalendarAccountStatusImpl: async () => statusValue,
    }));
    assert.equal(response.status, 200);
    assert.deepEqual(JSON.parse(response.body), { connected: false, state: "action_required" });
  }
  for (const failure of [new Error("provider_ambiguous"), new Error("provider_ownership")]) {
    let forbiddenWrites = 0;
    const response = await call("GET", "/api/lm-web/calendar/status", options({
      fetchImpl: async (_url, init = {}) => {
        if (init.method === "PATCH") forbiddenWrites++;
        return { ok: true, json: async () => [{ ...row }] };
      },
      composioCalendarAccountStatusImpl: async () => { throw failure; },
    }));
    assert.equal(response.status, 502, "ambiguous and foreign accounts fail closed");
    assert.equal(forbiddenWrites, 0, "GET status must remain read-only");
  }
});

test("Calendar status exposes an enable-pending retry even after provider is ACTIVE", async () => {
  const row = { uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" };
  let providerReads = 0;
  const response = await call("GET", "/api/lm-web/calendar/status", options({
    fetchImpl: async () => ({ ok: true, json: async () => [{ ...row }] }),
    readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: false, disconnectPending: false,
      enablePending: true, enableClaimId: "2e59df08-f437-44fd-bbe9-5d835ba467f0",
      enableClaimedAt: "2026-10-06T03:00:00.000Z" }),
    composioCalendarAccountStatusImpl: async (scope, accountId) => {
      providerReads++;
      assert.deepEqual(scope, { uid: UID });
      assert.equal(accountId, "ca-selected");
      return "ACTIVE";
    },
  }));

  assert.equal(response.status, 200);
  assert.deepEqual(JSON.parse(response.body), { connected: false, state: "enable_pending", enablePending: true });
  assert.equal(providerReads, 1);
});

test("Calendar start recovers one exact ACTIVE account after callback binding was interrupted", async () => {
  const row = { uid: UID, telegram_chat_id: null, calendar_provider: null, calendar_connected_account_id: null };
  const methods = [], oauth = [];
  const response = await call("POST", "/api/lm-web/calendar/start", options({
    fetchImpl: async (_url, init = {}) => {
      const method = init.method || "GET";
      methods.push(method);
      if (String(_url).includes("/rpc/bind_lm_web_calendar_account")) {
        const body = JSON.parse(init.body || "{}");
        row.calendar_provider = "composio_gcal";
        row.calendar_connected_account_id = body.p_connected_account_id;
        return { ok: true, json: async () => true };
      }
      return { ok: true, json: async () => [{ ...row }] };
    },
    composioCalendarAccountsImpl: async (scope) => {
      assert.deepEqual(scope, { uid: UID });
      return [{ id: "ca-recovered", user_id: UID, toolkit: { slug: "googlecalendar" }, status: "ACTIVE", is_disabled: false }];
    },
    composioCalendarAccountStatusImpl: async (scope, id) => {
      assert.deepEqual(scope, { uid: UID });
      assert.equal(id, "ca-recovered");
      return "ACTIVE";
    },
    composioCalendarStatusImpl: async () => { throw new Error("recovery must inspect account rows"); },
    webCalendarStore: {
      createWebOAuthState: async () => { oauth.push("create"); return true; },
      attachWebOAuthAccount: async () => { oauth.push("attach"); return true; },
    },
    startCalendarOAuthImpl: async () => { oauth.push("oauth"); throw new Error("recovered account must skip OAuth"); },
  }), { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { uid: OTHER_UID, connectedAccountId: "ca-client" } });

  assert.equal(response.status, 200);
  assert.deepEqual(JSON.parse(response.body), { connected: true, state: "connected" });
  assert.equal(row.calendar_provider, "composio_gcal");
  assert.equal(row.calendar_connected_account_id, "ca-recovered");
  assert.deepEqual(methods, ["GET", "GET", "POST", "GET"]);
  assert.deepEqual(oauth, []);
});

test("Calendar start does not bind ambiguous ACTIVE accounts", async () => {
  const row = { uid: UID, telegram_chat_id: null, calendar_provider: null, calendar_connected_account_id: null };
  let writes = 0, oauth = 0;
  const response = await call("POST", "/api/lm-web/calendar/start", options({
    fetchImpl: async (_url, init = {}) => {
      if (init.method === "PATCH") writes++;
      return { ok: true, json: async () => [{ ...row }] };
    },
    composioCalendarAccountsImpl: async () => [
      { id: "ca-one", user_id: UID, toolkit: { slug: "googlecalendar" }, status: "ACTIVE" },
      { id: "ca-two", user_id: UID, toolkit: { slug: "googlecalendar" }, status: "ACTIVE" },
    ],
    webCalendarStore: { createWebOAuthState: async () => { oauth++; return true; } },
    startCalendarOAuthImpl: async () => { oauth++; return { connectedAccountId: "ca-new", redirectUrl: "https://accounts.example/connect" }; },
  }), { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {} });
  assert.equal(response.status, 502);
  assert.equal(writes, 0);
  assert.equal(oauth, 0);
  assert.equal(row.calendar_connected_account_id, null);
});

test("Web eligibility rereads the exact row and rejects a later Telegram binding", async () => {
  const queries = [];
  const row = (telegramChatId) => ({ ok: true, json: async () => [{ uid: UID, telegram_chat_id: telegramChatId }] });
  const opts = {
    supaUrl: "https://supabase.example",
    supaKey: "service-role-key",
    fetchImpl: async (url) => { queries.push(String(url)); return row(null); },
  };
  assert.equal(await assertWebUserUnbound(UID, opts), true);
  opts.fetchImpl = async (url) => { queries.push(String(url)); return row("101"); };
  assert.equal(await assertWebUserUnbound(UID, opts), false);
  opts.fetchImpl = async (url) => { queries.push(String(url)); return { ok: true, json: async () => [{ uid: UID }] }; };
  assert.equal(await assertWebUserUnbound(UID, opts), false);
  assert.equal(queries.length, 3);
  assert.ok(queries.every((url) => url.includes(`uid=eq.${UID}`)));
  assert.ok(queries.every((url) => url.includes("telegram_chat_id=is.null")));
});

test("Web state RPCs pass only verified uid and state hash", async () => {
  const state = "r".repeat(43);
  const digest = crypto.createHash("sha256").update(state).digest("hex");
  const calls = [];
  const store = createWebCalendarStore({
    supaUrl: "https://supabase.example",
    supaKey: "service-role-key",
    fetchImpl: async (url, init) => {
      calls.push([String(url), JSON.parse(init.body)]);
      const result = calls.length === 3 ? "ca-created" : true;
      return { ok: true, json: async () => result };
    },
  });
  await store.createWebOAuthState({ uid: UID }, { stateHash: digest, provider: "calendar", expiresAt: "2030-01-01T00:00:00.000Z" });
  assert.equal(await store.attachWebOAuthAccount({ uid: UID }, digest, "ca-created"), true);
  assert.equal(await store.claimWebOAuthAccount({ uid: UID }, digest), "ca-created");
  assert.deepEqual(calls.map(([url]) => url.split("/").pop()), [
    "create_lm_web_calendar_oauth_state",
    "attach_lm_web_calendar_oauth_account",
    "claim_lm_web_calendar_oauth_account",
  ]);
  assert.ok(calls.every(([, body]) => body.p_uid === UID && !("p_chat_id" in body)));
  assert.ok(calls.every(([, body]) => JSON.stringify(body).includes(digest)));
  assert.ok(calls.every(([, body]) => !JSON.stringify(body).includes(state)));
});

test("unauthenticated and foreign web users cause no Calendar or database effect", async () => {
  let provider = 0, claims = 0, writes = 0, eventReads = 0;
  const unauthenticated = options({
    resolveWebUserImpl: async () => null,
    composioCalendarStatusImpl: async () => { provider++; return "ACTIVE"; },
    webCalendarStore: { claimWebOAuthAccount: async () => { claims++; return "ca-a"; } },
    fetchImpl: async () => { writes++; throw new Error("unauthenticated request must not use database"); },
    calendarEventsImpl: async () => { eventReads++; },
  });
  const status = await call("GET", "/api/lm-web/calendar/status", unauthenticated);
  const callback = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, unauthenticated);
  assert.equal(status.status, 401);
  assert.equal(callback.status, 401);
  assert.deepEqual([provider, claims, writes, eventReads], [0, 0, 0, 0]);

  const foreignScopes = [];
  const foreign = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, options({
    webCalendarStore: { claimWebOAuthAccount: async (scope, hash) => { foreignScopes.push([scope, hash]); return null; } },
    composioCalendarAccountStatusImpl: async () => { provider++; return "ACTIVE"; },
    fetchImpl: async () => { writes++; throw new Error("foreign state must not use database"); },
  }), { });
  assert.equal(foreign.status, 403);
  assert.deepEqual(foreignScopes, [[{ uid: UID }, crypto.createHash("sha256").update(STATE).digest("hex")]]);
  assert.deepEqual([provider, writes, eventReads], [0, 0, 0]);
});

test("a Web cookie is rejected after its uid becomes Telegram-bound", async () => {
  let provider = 0;
  const response = await call("GET", "/api/lm-web/calendar/status", options({
    assertWebUserUnboundImpl: async (uid) => { assert.equal(uid, UID); return false; },
    composioCalendarStatusImpl: async () => { provider++; return "ACTIVE"; },
  }));
  assert.equal(response.status, 403);
  assert.equal(provider, 0);
});

test("row rebind after auth is rechecked before Calendar provider reads", async () => {
  let rowReads = 0, providerReads = 0;
  const response = await call("POST", "/api/lm-web/calendar/start", options({
    assertWebUserUnboundImpl: async () => ++rowReads === 1,
    composioCalendarStatusImpl: async () => { providerReads++; return "MISSING"; },
  }), { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {} });
  assert.equal(response.status, 403);
  assert.equal(rowReads, 2);
  assert.equal(providerReads, 0);
});

test("callback rechecks row after one-time claim before Calendar provider read", async () => {
  let rowReads = 0, claims = 0, providerReads = 0, writes = 0;
  const response = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, options({
    assertWebUserUnboundImpl: async () => ++rowReads === 1,
    webCalendarStore: { claimWebOAuthAccount: async () => { claims++; return "ca-selected"; } },
    composioCalendarAccountStatusImpl: async () => { providerReads++; return "ACTIVE"; },
    fetchImpl: async () => { writes++; throw new Error("rebound row must not be mutated"); },
  }));
  assert.equal(response.status, 403);
  assert.deepEqual([rowReads, claims, providerReads, writes], [2, 1, 0, 0]);
});

test("web OAuth state is single-use and unique per uid", async () => {
  let creates = 0, attaches = 0, starts = 0;
  const hashes = [];
  const store = {
    async createWebOAuthState(scope, state) {
      creates++;
      assert.deepEqual(scope, { uid: UID });
      assert.equal(state.provider, "calendar");
      assert.match(state.stateHash, /^[a-f0-9]{64}$/);
      hashes.push(state.stateHash);
      return creates === 1;
    },
    async attachWebOAuthAccount(scope, stateHash, id) {
      attaches++;
      assert.deepEqual(scope, { uid: UID });
      assert.equal(stateHash, hashes[0]);
      assert.equal(id, "ca-created");
      return true;
    },
  };
  const opts = options({
    webCalendarStore: store,
    randomBytes: () => Buffer.alloc(32, 7),
    nowMs: 1000,
    composioCalendarStatusImpl: async (scope) => { assert.deepEqual(scope, { uid: UID }); return "MISSING"; },
    startCalendarOAuthImpl: async (scope, state, deps) => {
      starts++;
      assert.deepEqual(scope, { uid: UID });
      assert.equal(state.length, 43);
      assert.equal(deps.calendarCallbackPath, "/lm/oauth/calendar/callback");
      return { connectedAccountId: "ca-created", redirectUrl: "https://accounts.example/connect" };
    },
  });
  const request = { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: { uid: OTHER_UID, connectedAccountId: "ca-foreign" } };
  const first = await call("POST", "/api/lm-web/calendar/start", opts, request);
  const second = await call("POST", "/api/lm-web/calendar/start", opts, request);
  assert.equal(first.status, 200);
  assert.deepEqual(JSON.parse(first.body), { connected: false, state: "action_required", redirectUrl: "https://accounts.example/connect" });
  assert.equal(second.status, 409);
  assert.deepEqual([creates, attaches, starts], [2, 1, 1]);
  assert.equal(hashes[0], crypto.createHash("sha256").update(Buffer.alloc(32, 7).toString("base64url")).digest("hex"));
  assert.notEqual(hashes[0], Buffer.alloc(32, 7).toString("base64url"));
});

test("Calendar start requires exact Origin, JSON, and Web CSRF", async () => {
  let provider = 0, stateCreates = 0;
  const opts = options({
    composioCalendarStatusImpl: async () => { provider++; return "MISSING"; },
    webCalendarStore: { createWebOAuthState: async () => { stateCreates++; return true; } },
  });
  for (const [request, expectedStatus] of [
    [{ contentType: "application/json", csrf: "csrf-token", body: {} }, 403],
    [{ origin: "https://attacker.example", contentType: "application/json", csrf: "csrf-token", body: {} }, 403],
    [{ origin: ORIGIN, contentType: "text/plain", csrf: "csrf-token", body: {} }, 415],
    [{ origin: ORIGIN, contentType: "application/json", csrf: "wrong", body: {} }, 403],
  ]) {
    const response = await call("POST", "/api/lm-web/calendar/start", opts, request);
    assert.equal(response.status, expectedStatus);
  }
  assert.deepEqual([provider, stateCreates], [0, 0]);
});

test("Calendar start resumes only the uid's selected account after exact ACTIVE readback", async () => {
  let accountStatus = 0, resumes = 0, oauth = 0;
  let providerStatus = "DISABLED";
  const writes = [];
  const response = await call("POST", "/api/lm-web/calendar/start", options({
    composioCalendarStatusImpl: async (scope) => { assert.deepEqual(scope, { uid: UID }); return providerStatus; },
    composioCalendarAccountStatusImpl: async (scope, id) => {
      accountStatus++;
      assert.deepEqual(scope, { uid: UID });
      assert.equal(id, "ca-selected");
      return providerStatus;
    },
    composioCalendarStartImpl: async (scope, provider) => {
      resumes++;
      assert.deepEqual(scope, { uid: UID });
      assert.equal(provider.connectedAccountId, "ca-selected");
      providerStatus = "ACTIVE";
      return { provider: "calendar", state: "connected" };
    },
    startCalendarOAuthImpl: async () => { oauth++; throw new Error("existing selected account was resumed"); },
    fetchImpl: async (url, init = {}) => {
      writes.push([init.method || "GET", String(url)]);
      if (String(url).endsWith("/rpc/begin_lm_web_calendar_enable")
        || String(url).endsWith("/rpc/finish_lm_web_calendar_enable")) return { ok: true, json: async () => true };
      return { ok: true, json: async () => [{ uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" }] };
    },
  }), { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {} });
  assert.equal(response.status, 200);
  assert.deepEqual(JSON.parse(response.body), { connected: true, state: "connected" });
  assert.deepEqual([accountStatus, resumes, oauth], [2, 1, 0]);
  assert.deepEqual(writes.map(([method]) => method), ["GET", "GET", "POST", "POST", "GET"]);
  assert.match(writes[2][1], /begin_lm_web_calendar_enable$/);
  assert.match(writes[3][1], /finish_lm_web_calendar_enable$/);
});

test("Web Calendar start does not enable an EXPIRED selected account with disabled flags", async () => {
  const row = { uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" };
  let providerPatches = 0;
  let providerEnabled = false;
  const response = await call("POST", "/api/lm-web/calendar/start", options({
    composioCalendarAccountStatusImpl: async () => "DISABLED",
    fetchImpl: async (input, init = {}) => {
      const url = new URL(String(input));
      if (url.hostname === "backend.composio.dev") {
        if (url.pathname.endsWith("/status") && init.method === "PATCH") {
          providerPatches++;
          providerEnabled = JSON.parse(init.body || "{}").enabled === true;
          return { ok: true, status: 200, json: async () => ({}) };
        }
        return { ok: true, status: 200, json: async () => providerEnabled ? {
          id: "ca-selected", user_id: UID, toolkit_slug: "googlecalendar",
          status: "ACTIVE", is_disabled: false, enabled: true,
        } : {
          id: "ca-selected", user_id: UID, toolkit_slug: "googlecalendar",
          status: "EXPIRED", is_disabled: true, enabled: false,
        } };
      }
      if (url.pathname.endsWith("/rpc/begin_lm_web_calendar_enable")
        || url.pathname.endsWith("/rpc/finish_lm_web_calendar_enable")) {
        return { ok: true, status: 200, json: async () => true };
      }
      return { ok: true, status: 200, json: async () => [{ ...row }] };
    },
  }), { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {} });

  assert.notEqual(response.status, 200);
  assert.equal(providerPatches, 0);
});

test("Calendar start recovers an exact EXPIRED binding to one ACTIVE account without enabling the stale ID", async () => {
  const staleId = "ca-stale-123";
  const activeId = "ca-active-456";
  const active = {
    id: activeId, user_id: UID, toolkit_slug: "googlecalendar",
    status: "ACTIVE", is_disabled: false, enabled: true,
  };
  const h = makeStaleCalendarHarness({
    selectedId: staleId,
    selectedResponse: () => ({ ok: true, status: 200, json: async () => ({
      id: staleId, user_id: UID, toolkit_slug: "googlecalendar",
      status: "EXPIRED", is_disabled: false, enabled: true,
    }) }),
    accounts: [active],
  });

  const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 200);
  assert.deepEqual(JSON.parse(response.body), { connected: true, state: "connected" });
  assert.deepEqual(h.state.providerAccountReads, [staleId, activeId]);
  assert.deepEqual(h.state.providerPatches, []);
  assert.equal(h.state.row.calendar_connected_account_id, activeId);
  assert.equal(h.state.bindings.length, 1);
  assert.equal(h.state.bindings[0].p_expected_calendar_account_id, staleId);
  assert.deepEqual(h.state.oauth, []);
});

test("Calendar start begins fresh OAuth after exact selected-account 404 without stale enable", async () => {
  const staleId = "ca-deleted-123";
  const h = makeStaleCalendarHarness({
    selectedId: staleId,
    selectedResponse: () => ({ ok: false, status: 404, json: async () => ({ message: "not found" }) }),
  });

  const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 200);
  assert.deepEqual(JSON.parse(response.body), {
    connected: false, state: "action_required", redirectUrl: "https://accounts.example/connect",
  });
  assert.deepEqual(h.state.providerPatches, []);
  assert.equal(h.state.bindings.length, 0);
  assert.equal(h.state.row.calendar_connected_account_id, staleId);
  assert.deepEqual(h.state.oauth, ["state", "oauth", "attached:ca-new-456"]);
});

test("provider errors and mismatched/unknown stale bindings do not start OAuth or bind", async () => {
  const staleId = "ca-stale-123";
  const cases = [
    () => ({ ok: false, status: 503, json: async () => ({ message: "unavailable" }) }),
    () => ({ ok: true, status: 200, json: async () => ({
      id: staleId, user_id: UID, toolkit_slug: "googlecalendar",
      status: "INITIATED", is_disabled: false, enabled: false,
    }) }),
    () => ({ ok: true, status: 200, json: async () => ({
      id: staleId, user_id: OTHER_UID, toolkit_slug: "googlecalendar", status: "EXPIRED",
    }) }),
    () => ({ ok: true, status: 200, json: async () => ({
      id: "ca-other-999", user_id: UID, toolkit_slug: "googlecalendar", status: "EXPIRED",
    }) }),
  ];
  for (const selectedResponse of cases) {
    const h = makeStaleCalendarHarness({ selectedId: staleId, selectedResponse });
    const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
      origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
    });

    assert.equal(response.status, 502);
    assert.equal(h.state.accountListReads, 0);
    assert.equal(h.state.providerPatches.length, 0);
    assert.equal(h.state.bindings.length, 0);
    assert.deepEqual(h.state.oauth, []);
    assert.equal(h.state.row.calendar_connected_account_id, staleId);
  }
});

test("Calendar start refuses a pending disconnect before provider enable or OAuth", async () => {
  const row = { uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" };
  let providerReads = 0, enables = 0, oauthStarts = 0, writes = 0;
  const response = await call("POST", "/api/lm-web/calendar/start", options({
    fetchImpl: async (_url, init = {}) => {
      if (init.method === "PATCH") writes++;
      return { ok: true, json: async () => [{ ...row }] };
    },
    readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: false, disconnectPending: true, enablePending: false }),
    composioCalendarAccountStatusImpl: async () => { providerReads++; return "DISABLED"; },
    composioCalendarStartImpl: async () => { enables++; return { provider: "calendar", state: "connected" }; },
    webCalendarStore: { createWebOAuthState: async () => { writes++; return true; } },
    startCalendarOAuthImpl: async () => { oauthStarts++; return { connectedAccountId: "ca-new", redirectUrl: "https://accounts.example/connect" }; },
  }), { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {} });

  assert.equal(response.status, 409);
  assert.deepEqual([providerReads, enables, oauthStarts, writes], [0, 0, 0, 0]);
});

test("Calendar start enable claim excludes concurrent disconnect begin", async () => {
  let providerStarted;
  const started = new Promise((resolve) => { providerStarted = resolve; });
  let releaseProvider;
  const providerGate = new Promise((resolve) => { releaseProvider = resolve; });
  const h = makeEnableHarness(async (state) => {
    providerStarted();
    await providerGate;
    state.providerStatus = "ACTIVE";
    return { provider: "calendar", state: "connected" };
  });
  const startPromise = call("POST", "/api/lm-web/calendar/start", h.opts, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });
  await started;
  const disconnectResponse = await callTravelControl(h.opts, "disconnect");
  releaseProvider();
  const startResponse = await startPromise;

  assert.equal(disconnectResponse.status, 409);
  assert.equal(JSON.parse(disconnectResponse.body).error, "calendar_enable_pending");
  assert.equal(h.state.providerDisableCalls, 0);
  assert.equal(startResponse.status, 200);
  assert.equal(h.state.row.calendar_enable_pending, false);
  assert.ok(h.state.calls.indexOf("begin_enable") < h.state.calls.indexOf("provider_enable"));
  assert.ok(h.state.calls.indexOf("provider_status:ACTIVE") < h.state.calls.indexOf("finish_enable"));
});

test("Calendar start does not reuse a retained enable claim for a second provider enable", async () => {
  let providerStarted;
  const started = new Promise((resolve) => { providerStarted = resolve; });
  let releaseProvider;
  const providerGate = new Promise((resolve) => { releaseProvider = resolve; });
  const h = makeEnableHarness(async (state) => {
    if (state.providerEnableCalls === 1) {
      providerStarted();
      await providerGate;
      state.providerStatus = "ACTIVE";
    }
    return { provider: "calendar", state: "connected" };
  });
  const request = { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {} };
  const first = call("POST", "/api/lm-web/calendar/start", h.opts, request);
  await started;

  const second = await call("POST", "/api/lm-web/calendar/start", h.opts, request);

  assert.equal(second.status, 409);
  assert.equal(JSON.parse(second.body).error, "calendar_enable_pending");
  assert.equal(h.state.providerEnableCalls, 1);
  releaseProvider();
  assert.equal((await first).status, 200);
});

test("enable retry clears its claim only after exact ACTIVE readback", async () => {
  const h = makeEnableHarness(async () => ({ provider: "calendar", state: "connected" }));
  const request = { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {} };
  const first = await call("POST", "/api/lm-web/calendar/start", h.opts, request);
  assert.notEqual(first.status, 200);
  assert.equal(h.state.row.calendar_enable_pending, true);

  h.state.providerStatus = "ACTIVE";
  const retry = await call("POST", "/api/lm-web/calendar/start", h.opts, request);

  assert.equal(retry.status, 200);
  assert.equal(h.state.row.calendar_enable_pending, false);
  assert.equal(h.state.providerEnableCalls, 1);
  assert.ok(h.state.calls.indexOf("provider_status:ACTIVE") < h.state.calls.lastIndexOf("finish_enable"));
});

test("Calendar start bounds its final ACTIVE readback", async () => {
  const h = makeEnableHarness();
  const statusSignals = [];
  const originalStatus = h.opts.composioCalendarAccountStatusImpl;
  h.opts.composioCalendarAccountStatusImpl = async (scope, accountId, providerOpts = {}) => {
    statusSignals.push(providerOpts.signal);
    return originalStatus(scope, accountId, providerOpts);
  };
  const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 200);
  assert.equal(statusSignals.length, 2);
  assert.equal(statusSignals[0], undefined, "the pre-claim status read has no enable lease");
  assert.ok(statusSignals[1] instanceof AbortSignal, "the post-enable readback has a bounded signal");
});

test("Calendar enable uses a server UUID and finishes only the matching claim", async () => {
  const h = makeEnableHarness();
  const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 200);
  assert.match(h.state.beginClaimIds[0], /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
  assert.deepEqual(h.state.finishClaimIds, [h.state.beginClaimIds[0]]);
});

test("a known pre-PATCH Calendar failure releases its matching claim without changing preferences", async () => {
  const h = makeEnableHarness(async () => {
    const error = new Error("provider_failed");
    error.calendarEnableEffect = "no_effect";
    throw error;
  });
  const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 502);
  assert.equal(h.state.row.calendar_enable_pending, false);
  assert.equal(h.state.row.calendar_enable_claim_id, null);
  assert.equal(h.state.preference.daily_automation_enabled, true);
  assert.deepEqual(h.state.finishClaimIds, [h.state.beginClaimIds[0]]);
});

test("an unknown post-dispatch Calendar failure retains its claim", async () => {
  const h = makeEnableHarness(async () => {
    const error = new Error("provider timeout");
    error.calendarEnableEffect = "unknown";
    throw error;
  });
  const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 502);
  assert.equal(h.state.row.calendar_enable_pending, true);
  assert.equal(h.state.row.calendar_enable_claim_id, h.state.beginClaimIds[0]);
  assert.deepEqual(h.state.finishClaimIds, []);
});

test("Calendar start refuses a non-expired DISABLED claim without provider enable", async () => {
  const h = makeEnableHarness();
  h.state.row.calendar_enable_pending = true;
  h.state.row.calendar_enable_claim_id = "d901bdde-e5ce-4c7c-9b73-6d9f8fc24e2f";
  h.state.row.calendar_enable_claimed_at = new Date().toISOString();
  const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 409);
  assert.equal(h.state.recoverCalls, 1);
  assert.equal(h.state.providerEnableCalls, 0);
  assert.equal(h.state.row.calendar_enable_claim_id, "d901bdde-e5ce-4c7c-9b73-6d9f8fc24e2f");
});

test("a stale DISABLED Calendar claim rotates once before one provider enable", async () => {
  const h = makeEnableHarness();
  const oldClaimId = "d901bdde-e5ce-4c7c-9b73-6d9f8fc24e2f";
  h.state.row.calendar_enable_pending = true;
  h.state.row.calendar_enable_claim_id = oldClaimId;
  h.state.row.calendar_enable_claimed_at = new Date(Date.now() - 120_001).toISOString();
  const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
    origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
  });

  assert.equal(response.status, 200);
  assert.equal(h.state.recoverCalls, 1);
  assert.equal(h.state.providerEnableCalls, 1);
  assert.notEqual(h.state.lastIssuedClaimId, oldClaimId);
  assert.deepEqual(h.state.finishClaimIds, [h.state.lastIssuedClaimId]);
  assert.equal(h.state.row.calendar_enable_pending, false);
  assert.ok(h.state.calls.indexOf("recover_enable") < h.state.calls.indexOf("provider_enable"));
});

test("concurrent stale Calendar enable recovery has only one provider owner", async () => {
  const h = makeEnableHarness();
  const oldClaimId = "d901bdde-e5ce-4c7c-9b73-6d9f8fc24e2f";
  h.state.row.calendar_enable_pending = true;
  h.state.row.calendar_enable_claim_id = oldClaimId;
  h.state.row.calendar_enable_claimed_at = new Date(Date.now() - 120_001).toISOString();
  let statusReads = 0;
  let releaseReads;
  const readsReady = new Promise((resolve) => { releaseReads = resolve; });
  h.opts.composioCalendarAccountStatusImpl = async () => {
    statusReads++;
    if (statusReads === 2) releaseReads();
    if (statusReads <= 2) {
      await readsReady;
      return "DISABLED";
    }
    return h.state.providerStatus;
  };
  const request = { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {} };
  const [first, second] = await Promise.all([
    call("POST", "/api/lm-web/calendar/start", h.opts, request),
    call("POST", "/api/lm-web/calendar/start", h.opts, request),
  ]);

  assert.ok([first.status, second.status].includes(200));
  assert.equal(h.state.recoverCalls, 2);
  assert.equal(h.state.providerEnableCalls, 1);
  assert.equal(h.state.row.calendar_enable_pending, false);
  assert.notEqual(h.state.lastIssuedClaimId, oldClaimId);
});

test("expired MISSING or EXPIRED claims release before user-initiated reauthorization", async () => {
  for (const providerStatus of ["MISSING", "EXPIRED"]) {
    const h = makeEnableHarness();
    const oldClaimId = "d901bdde-e5ce-4c7c-9b73-6d9f8fc24e2f";
    h.state.row.calendar_enable_pending = true;
    h.state.row.calendar_enable_claim_id = oldClaimId;
    h.state.row.calendar_enable_claimed_at = new Date(Date.now() - 120_001).toISOString();
    h.state.providerStatus = providerStatus;
    h.opts.webCalendarStore = {
      createWebOAuthState: async () => true,
      attachWebOAuthAccount: async () => true,
    };
    h.opts.startCalendarOAuthImpl = async () => ({
      connectedAccountId: "ca-new-456",
      redirectUrl: "https://accounts.example/connect",
    });
    const response = await call("POST", "/api/lm-web/calendar/start", h.opts, {
      origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {},
    });

    assert.equal(response.status, 200, providerStatus);
    assert.deepEqual(JSON.parse(response.body), {
      connected: false, state: "action_required", redirectUrl: "https://accounts.example/connect",
    });
    assert.equal(h.state.providerEnableCalls, 0, `${providerStatus} stale account is never enabled`);
    assert.equal(h.state.row.calendar_enable_pending, false);
    assert.equal(h.state.row.calendar_connected_account_id, "ca-selected");
  }
});

test("Calendar callback rejects disconnect pending before consuming state or reading provider", async () => {
  let claims = 0, providerReads = 0, writes = 0;
  const response = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, options({
    readWebTravelControlStateImpl: async () => ({ dailyAutomationEnabled: false, disconnectPending: true, enablePending: false }),
    webCalendarStore: { claimWebOAuthAccount: async () => { claims++; return "ca-selected"; } },
    composioCalendarAccountStatusImpl: async () => { providerReads++; return "ACTIVE"; },
    fetchImpl: async (_url, init = {}) => { if (init.method === "PATCH") writes++; return { ok: true, json: async () => [] }; },
  }));

  assert.equal(response.status, 403);
  assert.deepEqual([claims, providerReads, writes], [0, 0, 0]);
});

test("OAuth binding RPC rejects a disconnect that starts after provider ACTIVE readback", async () => {
  const h = makeEnableHarness(async () => ({ provider: "calendar", state: "connected" }));
  h.state.row.calendar_provider = null;
  h.state.row.calendar_connected_account_id = null;
  h.state.providerStatus = "ACTIVE";
  h.opts.webCalendarStore = { claimWebOAuthAccount: async () => "ca-created" };
  h.opts.readWebTravelControlStateImpl = async () => ({ dailyAutomationEnabled: true, disconnectPending: false, enablePending: false });
  h.opts.composioCalendarAccountStatusImpl = async (scope, accountId) => {
    assert.deepEqual(scope, { uid: UID });
    assert.equal(accountId, "ca-created");
    h.state.preference.calendar_disconnect_pending = true;
    return "ACTIVE";
  };
  const response = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, h.opts);

  assert.notEqual(response.status, 303);
  assert.equal(h.state.row.calendar_connected_account_id, null);
  assert.ok(h.state.calls.includes("bind"));
});

test("callback rejects foreign or inactive connected account", async () => {
  let providerReads = 0, writes = 0, eventReads = 0;
  const store = { claimWebOAuthAccount: async (scope) => { assert.deepEqual(scope, { uid: UID }); return "ca-selected"; } };
  for (const outcome of ["DISABLED", new Error("provider_ownership")]) {
    const response = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, options({
      webCalendarStore: store,
      composioCalendarAccountStatusImpl: async (scope, accountId) => {
        providerReads++;
        assert.deepEqual(scope, { uid: UID });
        assert.equal(accountId, "ca-selected");
        if (outcome instanceof Error) throw outcome;
        return outcome;
      },
      fetchImpl: async (url, init = {}) => {
        if (String(url).includes("/rpc/bind_lm_web_calendar_account")) writes++;
        return { ok: true, json: async () => [{ uid: UID, telegram_chat_id: null, calendar_provider: null, calendar_connected_account_id: null }] };
      },
      calendarEventsImpl: async () => { eventReads++; },
    }));
    assert.equal(response.status, 403);
  }
  assert.deepEqual([providerReads, writes, eventReads], [2, 0, 0]);
});

test("callback rejects missing, malformed, or ambiguous state before claim", async () => {
  let claims = 0, providers = 0, writes = 0;
  const opts = options({
    webCalendarStore: { claimWebOAuthAccount: async () => { claims++; return "ca-selected"; } },
    composioCalendarAccountStatusImpl: async () => { providers++; return "ACTIVE"; },
    fetchImpl: async () => { writes++; throw new Error("invalid state must not mutate lm_users"); },
  });
  for (const url of [
    "/lm/oauth/calendar/callback",
    "/lm/oauth/calendar/callback?state=bad",
    `/lm/oauth/calendar/callback?state=${STATE}&state=${STATE}`,
    `/lm/oauth/calendar/callback?state=${STATE}&state[]=x`,
    `/lm/oauth/calendar/callback?state=${STATE}&state[extra]=x`,
    `/lm/oauth/calendar/callback?state=${STATE}&State[]=x`,
  ]) {
    const response = await call("GET", url, opts);
    assert.equal(response.status, 403);
  }
  assert.deepEqual([claims, providers, writes], [0, 0, 0]);
});

test("callback claims once, checks exact ACTIVE owner, and reads back the binding", async () => {
  const calls = [];
  const row = { uid: UID, telegram_chat_id: null, calendar_provider: null, calendar_connected_account_id: null };
  const store = {
    async claimWebOAuthAccount(scope, hash) {
      calls.push(["claim", scope, hash]);
      return "ca-selected";
    },
  };
  const response = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}&connectedAccountId=untrusted`, options({
    webCalendarStore: store,
    composioCalendarAccountStatusImpl: async (scope, id) => {
      calls.push(["provider", scope, id]);
      return "ACTIVE";
    },
    fetchImpl: async (url, init = {}) => {
      calls.push([init.method || "GET", String(url), init.body && JSON.parse(init.body)]);
      if (String(url).includes("/rpc/bind_lm_web_calendar_account")) {
        row.calendar_provider = "composio_gcal";
        row.calendar_connected_account_id = "ca-selected";
        return { ok: true, json: async () => true };
      }
      return { ok: true, json: async () => [{ ...row }] };
    },
    calendarEventsImpl: async () => { throw new Error("callback must not read Calendar events"); },
  }));
  assert.equal(response.status, 303);
  assert.equal(response.headers.Location, "/lm?initial_scan=1");
  assert.equal(response.headers["cache-control"], "no-store");
  assert.equal(calls[0][0], "claim");
  assert.deepEqual(calls[0][1], { uid: UID });
  assert.equal(calls[0][2], crypto.createHash("sha256").update(STATE).digest("hex"));
  assert.equal(calls[1][0], "GET", "the expected binding is read before provider verification");
  assert.deepEqual(calls[2], ["provider", { uid: UID }, "ca-selected"]);
  assert.equal(calls[3][0], "POST");
  assert.match(calls[3][1], /rpc\/bind_lm_web_calendar_account$/);
  assert.deepEqual(calls[3][2], {
    p_uid: UID,
    p_connected_account_id: "ca-selected",
    p_expected_calendar_provider: null,
    p_expected_calendar_account_id: null,
  });
  assert.equal(calls[4][0], "GET", "binding is independently read back after the atomic write");
});

test("callback replay does not repeat provider read or lm_users mutation", async () => {
  let claims = 0, providers = 0, writes = 0, reads = 0;
  const row = { uid: UID, telegram_chat_id: null, calendar_provider: null, calendar_connected_account_id: null };
  const opts = options({
    webCalendarStore: { claimWebOAuthAccount: async () => ++claims === 1 ? "ca-selected" : null },
    composioCalendarAccountStatusImpl: async () => { providers++; return "ACTIVE"; },
    fetchImpl: async (url, init = {}) => {
      if (String(url).includes("/rpc/bind_lm_web_calendar_account")) {
        writes++;
        row.calendar_provider = "composio_gcal";
        row.calendar_connected_account_id = "ca-selected";
        return { ok: true, json: async () => true };
      }
      reads++;
      return { ok: true, json: async () => [{ ...row }] };
    },
  });
  const first = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, opts);
  const replay = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, opts);
  assert.equal(first.status, 303);
  assert.equal(replay.status, 403);
  assert.deepEqual([claims, providers, writes, reads], [2, 1, 1, 2]);
});

test("SQL keeps Web NULL scope separate from existing non-null Telegram scope", () => {
  const migration = fs.readFileSync(path.join(__dirname, "../migrations/2026-10-06-lm-web-calendar-oauth.sql"), "utf8");
  const telegramMigration = fs.readFileSync(path.join(__dirname, "../migrations/2026-08-27-lm-panel-oauth-atomic.sql"), "utf8");
  const telegramAccountMigration = fs.readFileSync(path.join(__dirname, "../migrations/2026-09-11-lm-calendar-account-binding.sql"), "utf8");
  assert.match(migration, /ALTER TABLE public\.lm_panel_oauth_states[\s\S]*ALTER COLUMN chat_id DROP NOT NULL/);
  assert.match(migration, /UNIQUE INDEX[\s\S]*ON public\.lm_panel_oauth_states\s*\(uid\)[\s\S]*chat_id IS NULL[\s\S]*used_at IS NULL/);
  assert.match(migration, /state\.chat_id IS NULL/);
  assert.match(migration, /users\.telegram_chat_id IS NULL/);
  assert.match(migration, /create_lm_web_calendar_oauth_state/);
  assert.match(migration, /attach_lm_web_calendar_oauth_account/);
  assert.match(migration, /claim_lm_web_calendar_oauth_account/);
  assert.match(telegramMigration, /p_chat_id IS NULL OR p_chat_id = ''/);
  assert.match(telegramMigration + telegramAccountMigration, /state\.chat_id = p_chat_id/);
  assert.match(telegramMigration, /telegram_chat_id::text = p_chat_id/);
});

test("Calendar enable migration owns and recovers a claim only by token and database lease", () => {
  const sql = fs.readFileSync(path.join(__dirname, "../migrations/2026-10-06-z-lm-web-travel-controls.sql"), "utf8");
  const beginAt = sql.indexOf("CREATE OR REPLACE FUNCTION public.begin_lm_web_calendar_enable");
  const recoverAt = sql.indexOf("CREATE OR REPLACE FUNCTION public.recover_lm_web_calendar_enable");
  const finishAt = sql.indexOf("CREATE OR REPLACE FUNCTION public.finish_lm_web_calendar_enable");
  const bindAt = sql.indexOf("CREATE OR REPLACE FUNCTION public.bind_lm_web_calendar_account");
  const begin = sql.slice(beginAt, recoverAt);
  const recover = sql.slice(recoverAt, finishAt);
  const finish = sql.slice(finishAt, bindAt);

  assert.match(sql, /ADD COLUMN IF NOT EXISTS calendar_enable_claim_id uuid/i);
  assert.match(sql, /ADD COLUMN IF NOT EXISTS calendar_enable_claimed_at timestamptz/i);
  assert.match(begin, /p_claim_id uuid/i);
  assert.match(begin, /calendar_enable_claim_id\s*=\s*p_claim_id/i);
  assert.match(begin, /calendar_enable_claimed_at\s*=\s*now\(\)/i);
  assert.match(recover, /p_expected_claim_id uuid/i);
  assert.match(recover, /p_new_claim_id uuid/i);
  assert.match(recover, /FOR UPDATE/i);
  assert.match(recover, /calendar_enable_claim_id\s+IS DISTINCT FROM\s+p_expected_claim_id/i);
  assert.match(recover, /calendar_enable_claimed_at[\s\S]*interval\s+'120 seconds'/i);
  assert.match(recover, /calendar_enable_claim_id\s*=\s*p_new_claim_id/i);
  assert.match(finish, /p_claim_id uuid/i);
  assert.match(finish, /IF p_claim_id IS NULL THEN RAISE EXCEPTION 'calendar_enable_claim_invalid'/i);
  assert.match(finish, /calendar_enable_claim_id\s*=\s*p_claim_id/i);
});
