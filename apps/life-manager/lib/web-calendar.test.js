"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { assertWebUserUnbound, createWebCalendarStore, handleWebCalendarRequest } = require("./web-calendar.js");

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
    fetchImpl: async () => ({ ok: true, json: async () => [{ uid: UID, telegram_chat_id: null, calendar_provider: null, calendar_connected_account_id: null }] }),
    readJsonImpl: async (req) => req.testBody === undefined ? {} : req.testBody,
    composioCalendarAccountsImpl: async () => [],
    ...overrides,
  };
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

test("Calendar start recovers one exact ACTIVE account after callback binding was interrupted", async () => {
  const row = { uid: UID, telegram_chat_id: null, calendar_provider: null, calendar_connected_account_id: null };
  const methods = [], oauth = [];
  const response = await call("POST", "/api/lm-web/calendar/start", options({
    fetchImpl: async (_url, init = {}) => {
      const method = init.method || "GET";
      methods.push(method);
      if (method === "PATCH") Object.assign(row, JSON.parse(init.body));
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
  assert.deepEqual(methods.filter((method) => method === "PATCH"), ["PATCH"]);
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
  const writes = [];
  const response = await call("POST", "/api/lm-web/calendar/start", options({
    composioCalendarStatusImpl: async (scope) => { assert.deepEqual(scope, { uid: UID }); return "DISABLED"; },
    composioCalendarAccountStatusImpl: async (scope, id) => {
      accountStatus++;
      assert.deepEqual(scope, { uid: UID });
      assert.equal(id, "ca-selected");
      return "DISABLED";
    },
    composioCalendarStartImpl: async (scope, provider) => {
      resumes++;
      assert.deepEqual(scope, { uid: UID });
      assert.equal(provider.connectedAccountId, "ca-selected");
      return { provider: "calendar", state: "connected" };
    },
    startCalendarOAuthImpl: async () => { oauth++; throw new Error("existing selected account was resumed"); },
    fetchImpl: async (url, init = {}) => {
      writes.push([init.method || "GET", String(url)]);
      if (init.method === "PATCH") return { ok: true, json: async () => [{ uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" }] };
      return { ok: true, json: async () => [{ uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" }] };
    },
  }), { origin: ORIGIN, contentType: "application/json", csrf: "csrf-token", body: {} });
  assert.equal(response.status, 200);
  assert.deepEqual(JSON.parse(response.body), { connected: true, state: "connected" });
  assert.deepEqual([accountStatus, resumes, oauth], [1, 1, 0]);
  assert.deepEqual(writes.map(([method]) => method), ["GET", "GET", "PATCH", "GET"]);
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
      fetchImpl: async () => { writes++; throw new Error("foreign/inactive account must not mutate lm_users"); },
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
      if (init.method === "PATCH") return { ok: true, json: async () => [{ uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" }] };
      return { ok: true, json: async () => [{ uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" }] };
    },
    calendarEventsImpl: async () => { throw new Error("callback must not read Calendar events"); },
  }));
  assert.equal(response.status, 303);
  assert.equal(response.headers.Location, "/lm");
  assert.equal(response.headers["cache-control"], "no-store");
  assert.equal(calls[0][0], "claim");
  assert.deepEqual(calls[0][1], { uid: UID });
  assert.equal(calls[0][2], crypto.createHash("sha256").update(STATE).digest("hex"));
  assert.deepEqual(calls[1], ["provider", { uid: UID }, "ca-selected"]);
  assert.equal(calls[2][0], "PATCH");
  assert.match(calls[2][1], /uid=eq\.lm_11111111/);
  assert.match(calls[2][1], /telegram_chat_id=is\.null/);
  assert.equal(calls[2][2].calendar_provider, "composio_gcal");
  assert.equal(calls[2][2].calendar_connected_account_id, "ca-selected");
  assert.deepEqual(Object.keys(calls[2][2]).sort(), ["calendar_connected_account_id", "calendar_provider", "updated_at"]);
  assert.equal(calls[3][0], "GET", "binding is independently read back after the write");
});

test("callback replay does not repeat provider read or lm_users mutation", async () => {
  let claims = 0, providers = 0, writes = 0;
  const opts = options({
    webCalendarStore: { claimWebOAuthAccount: async () => ++claims === 1 ? "ca-selected" : null },
    composioCalendarAccountStatusImpl: async () => { providers++; return "ACTIVE"; },
    fetchImpl: async (_url, init = {}) => {
      writes++;
      return { ok: true, json: async () => init.method === "PATCH"
        ? [{ uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" }]
        : [{ uid: UID, telegram_chat_id: null, calendar_provider: "composio_gcal", calendar_connected_account_id: "ca-selected" }] };
    },
  });
  const first = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, opts);
  const replay = await call("GET", `/lm/oauth/calendar/callback?state=${STATE}`, opts);
  assert.equal(first.status, 303);
  assert.equal(replay.status, 403);
  assert.deepEqual([claims, providers, writes], [2, 1, 2]);
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
