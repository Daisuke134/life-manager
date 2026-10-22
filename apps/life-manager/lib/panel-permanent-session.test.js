"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const http = require("node:http");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");

const auth = require("./panel-auth.js");
const panelApi = require("./panel-api.js");
const { executeUserCommand } = require("./user-command.js");
const { renderPanelPage } = require("./panel-ui.js");
const discovery = require("./feature-discovery.js");
const { readRuntimePreferences } = require("./runtime-preferences.js");

const secret = (byte) => Buffer.alloc(32, byte).toString("base64url");
const hash = (value) => crypto.createHash("sha256").update(value).digest("hex");
const jsonResponse = (body, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

async function withServer(handler, run) {
  const server = http.createServer((req, res) => Promise.resolve(handler(req, res)).catch((error) => {
    if (!res.headersSent) res.writeHead(error.status || 500, { "content-type": "text/plain" });
    if (!res.writableEnded) res.end(error.message);
  }));
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try { return await run(`http://127.0.0.1:${server.address().port}`); }
  finally { await new Promise((resolve) => server.close(resolve)); }
}

function sessionRpcMachine() {
  const current = new Map();
  const families = new Map();
  const calls = [];
  const seed = (raw, uid, chatId, nowMs = 0) => {
    const h = hash(raw);
    current.set(h, { hash: h, uid, chatId: String(chatId), family: h, createdAt: nowMs, idle: nowMs + 30 * 86400000, absolute: nowMs + 180 * 86400000, revoked: false });
    families.set(h, new Set([h]));
  };
  const fetchImpl = async (url, init = {}) => {
    const name = String(url).split("/rpc/")[1] || "";
    const body = init.body ? JSON.parse(init.body) : {};
    calls.push({ name, body });
    if (name === "resolve_lm_panel_session") {
      const row = current.get(body.p_session_hash);
      if (!row) return jsonResponse([]);
      if (row.revoked && row.pending) {
        return jsonResponse([{ uid: row.uid, chat_id: row.chatId, family_id: row.family, rotated: true, accepted_child_hash: row.pending, accepted_child_seed: row.pendingSeed, cookie_max_age: 2592000 }]);
      }
      if (row.revoked) return jsonResponse([]);
      if (body.p_child_hash) {
        row.revoked = true; row.pending = body.p_child_hash; row.pendingSeed = body.p_child_seed;
        const child = { ...row, hash: body.p_child_hash, revoked: false, pending: null };
        current.set(body.p_child_hash, child);
        families.get(row.family).add(body.p_child_hash);
        return jsonResponse([{ uid: row.uid, chat_id: row.chatId, family_id: row.family, rotated: true, accepted_child_hash: body.p_child_hash, accepted_child_seed: body.p_child_seed, cookie_max_age: 2592000 }]);
      }
      return jsonResponse([{ uid: row.uid, chat_id: row.chatId, family_id: row.family, rotated: false, cookie_max_age: 2592000 }]);
    }
    if (name === "revoke_lm_panel_session") {
      const row = current.get(body.p_session_hash);
      if (row) for (const candidate of current.values()) if (candidate.family === row.family) { candidate.revoked = true; candidate.pending = null; candidate.pendingSeed = null; }
      return jsonResponse(true);
    }
    if (name === "revoke_lm_panel_sessions_for_tenant") {
      for (const row of current.values()) if (row.uid === body.p_uid && row.chatId === String(body.p_chat_id)) { row.revoked = true; row.pending = null; }
      return jsonResponse(true);
    }
    throw new Error(`unexpected rpc ${name}`);
  };
  return { current, calls, seed, fetchImpl };
}

test("B1 real /panel keeps +25h cookie usable, rotates, renders login HTML when absent, and bootstrap remains query-free", async () => {
  const old = secret(1), now = Date.parse("2026-07-22T01:00:00Z");
  const calls = [];
  await withServer((req, res) => auth.handlePanelRequest(req, res, {
    supaUrl: "https://db.example", supaKey: "service", botUsername: "LifeManagerBotbot",
    now: () => new Date(now), randomBytes: () => Buffer.alloc(32, 2),
    fetchImpl: async (url, init = {}) => {
      calls.push({ url: String(url), init });
      if (String(url).endsWith("/rpc/resolve_lm_panel_session")) return jsonResponse([{ uid: "u1", chat_id: "101", rotated: true }]);
      if (String(url).endsWith("/lm_panel_sessions")) return jsonResponse({}, 201);
      if (String(url).endsWith("/lm_panel_device_challenges")) return jsonResponse({}, 201);
      return jsonResponse([]);
    },
  }), async (base) => {
    const live = await fetch(`${base}/panel`, { headers: { cookie: `lm_panel_session=${old}` }, redirect: "manual" });
    assert.equal(live.status, 200);
    const setCookie = live.headers.get("set-cookie") || "";
    const rawReplacement = setCookie.match(/__Host-lm_panel_session=([^;]+)/)?.[1] || "";
    const rotationCall = calls.find((call) => call.url.endsWith("/rpc/resolve_lm_panel_session"));
    assert.equal(hash(rawReplacement), JSON.parse(rotationCall.init.body).p_child_hash);
    const missing = await fetch(`${base}/panel`);
    assert.equal(missing.status, 200);
    assert.match(missing.headers.get("content-type") || "", /text\/html/);
    const login = await missing.text();
    assert.match(login, /data-device-code="[2-9A-HJ-NP-Z]{8}"/);
    assert.match(login, /Open (?:this panel )?inside Telegram/i);
    assert.doesNotMatch(login, /https:\/\/t\.me\/|new dashboard link|\?t=/i);
    const boot = await fetch(`${base}/panel?t=${secret(9)}`, { redirect: "manual" });
    assert.equal(boot.status, 303); assert.equal(boot.headers.get("location"), "/panel");
  });
  assert.ok(calls.some((call) => call.url.endsWith("/rpc/resolve_lm_panel_session")));
});

test("B1 resolver sends hashes only and concurrent rotation leaves at most one replacement", async () => {
  assert.equal(typeof auth.resolvePanelSession, "function");
  const machine = sessionRpcMachine(), old = secret(3), seedBytes = secret(4); machine.seed(old, "u1", "101");
  const opts = { supaUrl: "https://db.example", supaKey: "service", fetchImpl: machine.fetchImpl, randomBytes: () => Buffer.alloc(32, 4) };
  const settled = await Promise.allSettled([auth.resolvePanelSession(old, opts), auth.resolvePanelSession(old, opts)]);
  assert.equal(settled.filter((item) => item.status === "fulfilled" && item.value).length, 2);
  assert.equal([...machine.current.values()].filter((row) => row.family === hash(old) && !row.revoked).length, 1);
  assert.equal(machine.calls[0].body.p_session_hash, hash(old));
  assert.equal(machine.calls[0].body.p_child_seed, hash(seedBytes));
  assert.equal(hash(settled[0].value.replacement), machine.calls[0].body.p_child_hash);
  assert.doesNotMatch(JSON.stringify(machine.calls), new RegExp(old));
});

test("B1 resolver retry recovers the committed child, old candidate fails, and tenant revoke isolates peers", async () => {
  assert.equal(typeof auth.resolvePanelSession, "function");
  assert.equal(typeof auth.revokePanelSessionsForTenant, "function");
  const machine = sessionRpcMachine(), old = secret(5), child = secret(6), peer = secret(7);
  machine.seed(old, "u1", "101"); machine.seed(peer, "u2", "202");
  const opts = { supaUrl: "https://db.example", supaKey: "service", fetchImpl: machine.fetchImpl, randomBytes: () => Buffer.alloc(32, 6) };
  const first = await auth.resolvePanelSession(old, opts); // emulate a lost HTTP response after atomic rotation
  const retried = await auth.resolvePanelSession(old, { ...opts, randomBytes: () => Buffer.alloc(32, 8) });
  const retryChild = first.replacement;
  assert.equal(retried.replacement, retryChild);
  assert.equal(await auth.resolvePanelSession(child, opts), null);
  assert.equal((await auth.resolvePanelSession(retryChild, { ...opts, randomBytes: () => Buffer.alloc(32, 9) })).uid, "u1");
  await auth.revokePanelSessionsForTenant({ uid: "u1", chatId: "101" }, opts);
  assert.equal(await auth.resolvePanelSession(retryChild, opts), null);
  assert.equal((await auth.resolvePanelSession(peer, opts)).uid, "u2");
  assert.deepEqual(machine.calls.find((call) => call.name === "revoke_lm_panel_sessions_for_tenant").body, { p_uid: "u1", p_chat_id: "101" });
});

test("B1 real logout route requires POST exact origin and CSRF, revokes exact hash, clears cookie, and negatives do not mutate", async () => {
  const raw = secret(10), revokes = [], familyId = "00000000-0000-4000-8000-000000000010";
  const familyCsrf = auth.sha256(`${familyId}:panel-family-csrf`);
  await withServer((req, res) => auth.handlePanelRequest(req, res, {
    panelOrigin: "https://life.example", supaUrl: "https://db.example", supaKey: "service",
    fetchImpl: async (url, init = {}) => {
      if (String(url).includes("resolve_lm_panel_session")) return jsonResponse([{ uid: "u1", chat_id: "101", family_id: familyId, rotated: false, cookie_max_age: 2592000 }]);
      if (String(url).includes("revoke_lm_panel_session")) revokes.push(JSON.parse(init.body));
      return jsonResponse(true);
    },
  }), async (base) => {
    for (const request of [
      { method: "GET" },
      { method: "POST", headers: { origin: "https://evil.example", "x-lm-csrf": familyCsrf } },
      { method: "POST", headers: { origin: "https://life.example", "x-lm-csrf": "bad" } },
    ]) await fetch(`${base}/panel/logout`, { ...request, headers: { cookie: `__Host-lm_panel_session=${raw}`, ...(request.headers || {}) }, redirect: "manual" });
    assert.equal(revokes.length, 0);
    const ok = await fetch(`${base}/panel/logout`, { method: "POST", headers: { cookie: `__Host-lm_panel_session=${raw}`, origin: "https://life.example", "x-lm-csrf": familyCsrf }, redirect: "manual" });
    assert.equal(ok.status, 303); assert.equal(ok.headers.get("location"), "/panel"); assert.match(ok.headers.get("set-cookie") || "", /Max-Age=0/);
  });
  assert.deepEqual(revokes, [{ p_session_hash: hash(raw) }]);
});

test("B2 production getUserByUid fetches preferences and OFF reaches wake/travel/ask as zero actions while peer remains enabled", async () => {
  const oldUrl = process.env.SUPABASE_URL, oldKey = process.env.SUPABASE_SERVICE_ROLE_KEY, oldFetch = global.fetch;
  process.env.SUPABASE_URL = "https://db.example"; process.env.SUPABASE_SERVICE_ROLE_KEY = "service";
  global.fetch = async (url) => {
    const value = String(url);
    if (value.includes("lm_users")) return jsonResponse([{ uid: value.includes("u-off") ? "u-off" : "u-on", telegram_chat_id: "101", phone: "+811", paid: true }]);
    if (value.includes("lm_panel_preferences")) return jsonResponse(value.includes("u-off") ? [{ call_enabled: false, daily_automation_enabled: false, notifications_enabled: false }] : [{ call_enabled: true, daily_automation_enabled: true, notifications_enabled: true }]);
    throw new Error(value);
  };
  try {
    delete require.cache[require.resolve("../scheduler.js")]; const scheduler = require("../scheduler.js");
    const off = await scheduler.getUserByUid("u-off"), on = await scheduler.getUserByUid("u-on");
    assert.equal(off.call_enabled, false); assert.equal(off.daily_automation_enabled, false); assert.equal(off.notifications_enabled, false);
    assert.equal(on.call_enabled, true);
    const actions = [];
    await scheduler.wakeUserOnce(off, { call: async () => actions.push("call") });
    await scheduler.travelUserOnce(off, { sendMessage: async () => actions.push("travel") });
    await scheduler.askUserOnce(off, { sendMessage: async () => actions.push("ask") });
    assert.deepEqual(actions, []);
  } finally { global.fetch = oldFetch; if (oldUrl == null) delete process.env.SUPABASE_URL; else process.env.SUPABASE_URL = oldUrl; if (oldKey == null) delete process.env.SUPABASE_SERVICE_ROLE_KEY; else process.env.SUPABASE_SERVICE_ROLE_KEY = oldKey; }
});

test("B2 default discovery selector fetches preferences, blocks OFF user, keeps peer active, and fails closed on preference 500", async () => {
  const sends = [];
  const fake = async (url) => {
    const value = String(url), uid = value.includes("u-off") ? "u-off" : value.includes("u-bad") ? "u-bad" : "u-on";
    if (value.includes("lm_panel_preferences")) return uid === "u-bad" ? jsonResponse({}, 500) : jsonResponse([{ notifications_enabled: uid === "u-on" }]);
    return jsonResponse([{ uid, telegram_chat_id: uid, last_discovery_at: null, payout_destination: null }]);
  };
  const deps = { supaUrl: "https://db.example", supaKey: "service", fetchImpl: fake, getLiveLocation: async () => null, sendMessage: async (_t, chat) => { sends.push(chat); return { ok: true }; }, saveDiscovery: async () => true };
  assert.equal((await discovery.runDiscoveryForUid("u-off", 1, deps)).sent, false);
  assert.equal((await discovery.runDiscoveryForUid("u-bad", 1, deps)).sent, false);
  assert.equal((await discovery.runDiscoveryForUid("u-on", 1, deps)).sent, true);
  assert.deepEqual(sends, ["u-on"]);
});

test("B3 rebound session cannot render page or claim OAuth/provider state", async () => {
  const raw = secret(11); let claims = 0, providers = 0;
  const fetchImpl = async (url) => {
    const value = String(url);
    if (value.includes("resolve_lm_panel_session")) return jsonResponse([]);
    if (value.endsWith("/lm_panel_device_challenges")) return jsonResponse({}, 201);
    if (value.includes("lm_panel_sessions")) return jsonResponse([{ uid: "u1", chat_id: "old-chat" }]);
    if (value.includes("lm_users")) return jsonResponse([]);
    throw new Error(value);
  };
  await withServer((req, res) => auth.handlePanelRequest(req, res, { supaUrl: "https://db.example", supaKey: "service", fetchImpl }), async (base) => {
    const response = await fetch(`${base}/panel`, { headers: { cookie: `lm_panel_session=${raw}` } });
    assert.match(await response.text(), /data-device-code="[2-9A-HJ-NP-Z]{8}"/); assert.equal(response.status, 200);
  });
  const req = { method: "GET", url: `/panel/oauth/calendar?state=${secret(12)}`, headers: { cookie: `lm_panel_session=${raw}` } };
  const res = { status: 0, writeHead(code) { this.status = code; }, end() {} };
  await panelApi.handlePanelOAuthCallback(req, res, { supaUrl: "https://db.example", supaKey: "service", fetchImpl, commandStore: { claimOAuthState: async () => { claims++; return true; }, assertCurrentScope: async () => false }, composioKey: "test", calendarStatus: async () => { providers++; return "ACTIVE"; } });
  assert.equal(res.status, 401); assert.equal(claims, 0); assert.equal(providers, 0);
});

test("B4 reconnect rejects account substitution and fake ACTIVE-but-disabled readback", async () => {
  const account = (id, extra = {}) => ({ id, user_id: "u1", toolkit: { slug: "googlecalendar" }, status: "INACTIVE", is_disabled: true, enabled: false, ...extra });
  for (const [readback, error] of [
    [account("ca-other", { status: "ACTIVE", is_disabled: false, enabled: true }), /provider_account_mismatch/],
    [account("ca-original", { status: "ACTIVE", is_disabled: true, enabled: true }), /provider_status_unknown/],
  ]) {
    const calls = [], sequence = [jsonResponse(account("ca-original")), jsonResponse({}), jsonResponse(readback)];
    await assert.rejects(panelApi.composioCalendarStart({ uid: "u1", chatId: "101" }, {
      connectedAccountId: "ca-original", composioKey: "k",
      fetchImpl: async (url, init = {}) => { calls.push([String(url), init.method || "GET"]); return sequence.shift(); },
    }), error);
    assert.deepEqual(calls.map(([url, method]) => [new URL(url).pathname, method]), [
      ["/api/v3.1/connected_accounts/ca-original", "GET"],
      ["/api/v3/connected_accounts/ca-original/status", "PATCH"],
      ["/api/v3.1/connected_accounts/ca-original", "GET"],
    ]);
  }
});

test("B4 disconnect rollback verifies exact account and full enabled truth before claiming unchanged", async () => {
  const account = (id, extra = {}) => ({ id, user_id: "u1", toolkit: { slug: "googlecalendar" }, status: "ACTIVE", is_disabled: false, enabled: true, ...extra });
  const calls = [], sequence = [jsonResponse({ items: [account("A")] }), jsonResponse({}), jsonResponse({ items: [account("B")] }), jsonResponse({}), jsonResponse({ items: [account("A", { is_disabled: true })] })];
  await assert.rejects(panelApi.composioCalendarDisconnect({ uid: "u1", chatId: "101" }, { composioKey: "k", fetchImpl: async (url, init = {}) => { calls.push({ url: String(url), init }); return sequence.shift(); } }), /provider_rollback_failed/);
  assert.match(calls[1].url, /\/A\/status$/); assert.match(calls[3].url, /\/A\/status$/); assert.deepEqual(JSON.parse(calls[3].init.body), { enabled: true });
});

test("B5 scoped settings and rendered controls expose different timezone/language/wake/live calendar truth and command through shared endpoint", async () => {
  const html = renderPanelPage();
  for (const setting of ["call_language", "call_time_zone", "wake_policy"]) assert.match(html, new RegExp(`data-(?:action|setting)=["']${setting}`));
  assert.match(html, /\/api\/panel\/commands/);
  const models = [];
  for (const [uid, chatId, language, zone, wake, calendar] of [["u1", "101", "ja", "Asia/Tokyo", "travel-only", "ACTIVE"], ["u2", "202", "en", "Europe/London", "all-events", "DISABLED"]]) {
    const store = { readUser: async () => ({ uid, telegram_chat_id: chatId, call_language: language, wake_policy: wake, calendar_provider: "stale" }), readPreferences: async () => ({ call_time_zone: zone }), readLocation: async () => null };
    models.push(await require("./user-command.js").buildControlCenter({ uid, chatId }, { store, calendarStatus: async () => calendar }));
  }
  assert.notEqual(models[0].settings.call_time_zone, models[1].settings.call_time_zone); assert.notEqual(models[0].settings.call_language, models[1].settings.call_language); assert.notEqual(models[0].connections.calendar.state, models[1].connections.calendar.state);
});

test("B5 language timezone and wake controls dispatch through the real shared command HTTP handler with scoped results", async () => {
  const state = { call_language: "en", call_time_zone: "UTC", wake_policy: "travel-only" };
  const store = {
    async readUser() { return { uid: "u1", telegram_chat_id: "101", ...state }; },
    async readPreferences() { return { call_time_zone: state.call_time_zone }; },
    async readReceipt() { return null; }, async claimReceipt() { return true; }, async finishReceipt() {},
    async patchUser(_scope, patch) { Object.assign(state, patch); return { ...state }; },
    async patchPreferences(_scope, patch) { Object.assign(state, patch); return { ...state }; },
  };
  await withServer((req, res) => panelApi.handlePanelApiRequest(req, res, {
    panelOrigin: "https://life.example", sessionScopeImpl: async () => ({ uid: "u1", chatId: "101", csrf: "csrf-value" }), commandStore: store,
  }), async (base) => {
    for (const [setting, value] of [["call_language", "ja"], ["call_time_zone", "Asia/Tokyo"], ["wake_policy", "all-events"]]) {
      const response = await fetch(`${base}/api/panel/commands`, { method: "POST", headers: { "content-type": "application/json", origin: "https://life.example", "x-lm-csrf": "csrf-value", "idempotency-key": `control-${setting}` }, body: JSON.stringify({ type: "setting.set", setting, value }) });
      assert.equal(response.status, 200);
    }
  });
  assert.deepEqual(state, { call_language: "ja", call_time_zone: "Asia/Tokyo", wake_policy: "all-events" });
});

test("B6 oversize real request settles once, mutates zero times, and late socket error is handled", async () => {
  const req = new EventEmitter(); let mutations = 0, responses = 0, body = "";
  Object.assign(req, { method: "POST", url: "/api/panel/commands", headers: { "content-type": "application/json", origin: "https://life.example", "x-lm-csrf": "csrf-value", "idempotency-key": "oversize-0001" } });
  const res = { writeHead() { responses++; }, end(value) { body += value || ""; } };
  const pending = panelApi.handlePanelApiRequest(req, res, { panelOrigin: "https://life.example", sessionScopeImpl: async () => ({ uid: "u1", chatId: "101", csrf: "csrf-value" }), commandStore: {}, executeCommandImpl: async () => { mutations++; } });
  await new Promise((resolve) => setImmediate(resolve));
  req.emit("data", Buffer.alloc(32 * 1024 + 1)); req.emit("data", Buffer.alloc(4096)); req.emit("end"); await pending;
  assert.equal(responses, 1); assert.match(body, /command_failed/); assert.equal(mutations, 0); assert.equal(req.listenerCount("data"), 0);
  assert.doesNotThrow(() => req.emit("error", new Error("late socket error")));
});

test("B3/B5 rebind between command validation and write performs zero scoped mutation", async () => {
  let binding = "101", writes = 0;
  const store = {
    async readUser() { return { uid: "u1", telegram_chat_id: binding }; },
    async readReceipt() { return null; }, async claimReceipt() { binding = "999"; return true; }, async finishReceipt() {},
    async patchPreferences() { writes++; return {}; }, async patchUser() { writes++; return {}; },
  };
  await assert.rejects(executeUserCommand({ uid: "u1", chatId: "101" }, { type: "setting.set", setting: "call_enabled", value: false }, { store, idempotencyKey: "rebind-0001" }), /scope_mismatch/);
  assert.equal(writes, 0);
});

test("B1/B3 additive session and mutation RPCs remain RLS service-role-only", () => {
  const sql = fs.readFileSync(path.join(__dirname, "../migrations/2026-07-22-lm-panel-durable-sessions.sql"), "utf8");
  for (const name of ["resolve_lm_panel_session", "revoke_lm_panel_session", "revoke_lm_panel_sessions_for_tenant", "mutate_lm_panel_preferences", "mutate_lm_panel_user"]) {
    assert.match(sql, new RegExp(`REVOKE ALL ON FUNCTION public\\.${name}[\\s\\S]*FROM PUBLIC, anon, authenticated`, "i"));
    assert.match(sql, new RegExp(`GRANT EXECUTE ON FUNCTION public\\.${name}[\\s\\S]*TO service_role`, "i"));
  }
  assert.match(sql, /ALTER TABLE public\.lm_panel_sessions ENABLE ROW LEVEL SECURITY/i);
  assert.doesNotMatch(sql, /GRANT EXECUTE[^;]+TO (?:anon|authenticated)/i);
});

test("B1 sessionUid and runtime preference transport/json failures fail closed", async () => {
  const raw = secret(20);
  assert.equal(await auth.sessionUid(raw, { supaUrl: "https://db.example", supaKey: "k", randomBytes: () => Buffer.alloc(32, 21), fetchImpl: async () => jsonResponse([{ uid: "u20", chat_id: "20", rotated: false }]) }), "u20");
  assert.equal(await readRuntimePreferences("u1", { supaUrl: "https://db.example", supaKey: "k", fetchImpl: async () => { throw new Error("offline"); } }), null);
  assert.equal(await readRuntimePreferences("u1", { supaUrl: "https://db.example", supaKey: "k", fetchImpl: async () => ({ ok: true, json: async () => { throw new Error("bad json"); } }) }), null);
});

test("B2 discovery production selectors cover list/save success and transport failure without sending", async () => {
  const opts = { supaUrl: "https://db.example", supaKey: "k", fetchImpl: async () => jsonResponse([{ uid: "u1", telegram_chat_id: "101" }]) };
  assert.equal((await discovery.listDiscoveryUsers(opts)).length, 1);
  assert.equal(await discovery.saveDiscovery("u1", 1, "location", { ...opts, fetchImpl: async () => jsonResponse({}) }), true);
  assert.deepEqual(await discovery.listDiscoveryUsers({ ...opts, fetchImpl: async () => { throw new Error("offline"); } }), []);
  assert.equal(await discovery.saveDiscovery("u1", 1, "location", { ...opts, fetchImpl: async () => { throw new Error("offline"); } }), false);
});

test("B3 command store keeps every read/write/OAuth operation scoped and uses atomic mutation RPCs", async () => {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    const value = String(url); calls.push({ value, init });
    if (value.includes("lm_users?") && !init.method) return jsonResponse([{ uid: "u1", telegram_chat_id: "101" }]);
    if (value.includes("lm_panel_preferences?") && !init.method) return jsonResponse([{ call_enabled: true }]);
    if (value.includes("lm_user_locations?") && !init.method) return jsonResponse([{ observed_at: "2026-07-22T00:00:00Z" }]);
    if (value.includes("lm_panel_command_receipts?") && !init.method) return jsonResponse([{ request_hash: "h", status: "succeeded", result: { ok: true } }]);
    if (value.includes("create_lm_panel_oauth_state")) return jsonResponse(true);
    if (value.includes("claim_lm_panel_oauth_state")) return jsonResponse(true);
    return jsonResponse([{ ok: true }], init.method === "POST" ? 201 : 200);
  };
  const store = panelApi.createSupabaseCommandStore({ supaUrl: "https://db.example", supaKey: "k", fetchImpl });
  const scope = { uid: "u1", chatId: "101" };
  assert.equal(await store.assertCurrentScope(scope), true);
  await store.readUser(scope); await store.readPreferences(scope); await store.readLocation(scope); await store.readReceipt(scope, "receipt-01");
  await store.claimReceipt(scope, "receipt-01", { requestHash: "h", commandType: "setting.set", status: "pending" });
  await store.finishReceipt(scope, "receipt-01", { status: "succeeded", result: { ok: true } });
  await store.patchPreferences(scope, { call_enabled: false }); await store.patchUser(scope, { wake_policy: "all-events" });
  await store.mutatePreferences(scope, { call_enabled: false }); await store.mutateUser(scope, { call_language: "ja" });
  await store.createOAuthState(scope, { stateHash: "h", provider: "calendar", expiresAt: "2099-01-01T00:00:00Z" });
  assert.equal(await store.claimOAuthState(scope, "h"), true);
  for (const call of calls.filter((item) => item.init.method && item.init.method !== "GET")) assert.doesNotMatch(call.init.body || "", /raw-secret/);
  assert.ok(calls.some((call) => call.value.endsWith("/rpc/mutate_lm_panel_preferences")));
  assert.ok(calls.some((call) => call.value.endsWith("/rpc/mutate_lm_panel_user")));
  assert.ok(calls.some((call) => call.value.endsWith("/rpc/create_lm_panel_oauth_state")));
});

test("B3 command store turns a false atomic OAuth claim into a conflict", async () => {
  const store = panelApi.createSupabaseCommandStore({
    supaUrl: "https://db.example", supaKey: "k",
    fetchImpl: async () => jsonResponse(false),
  });
  await assert.rejects(store.createOAuthState({ uid: "u1", chatId: "101" }, {
    stateHash: "a".repeat(64), provider: "calendar", expiresAt: "2099-01-01T00:00:00Z",
  }), (error) => error && error.message === "oauth_state_in_progress" && error.status === 409);
});
