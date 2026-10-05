"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");
const {
  createWebAuthClient,
  createWebCsrfToken,
  ensureWebUser,
  handleWebAuthRequest,
  resolveWebUser,
} = require("./web-auth.js");

const SUPABASE_URL = "https://travel-test.supabase.co";
const CALLBACK_ORIGIN = "https://life-manager.example.test";
const SUBJECT = "11111111-2222-4333-8444-555555555555";
const WEB_UID = `lm_${SUBJECT}`;
const SERVICE_KEY = `test.${Buffer.from(JSON.stringify({ role: "service_role" })).toString("base64url")}.sig`;
const ANON_KEY = "public-anon-key";

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return body; },
    async text() { return JSON.stringify(body); },
  };
}

function makeResponse() {
  const headers = Object.create(null);
  return {
    headers,
    statusCode: null,
    body: "",
    headersSent: false,
    writeHead(status, values = {}) {
      this.statusCode = status;
      for (const [name, value] of Object.entries(values)) headers[name.toLowerCase()] = value;
      this.headersSent = true;
    },
    setHeader(name, value) { headers[String(name).toLowerCase()] = value; },
    getHeader(name) { return headers[String(name).toLowerCase()]; },
    end(body = "") { this.body = String(body); this.headersSent = true; },
  };
}

function parseCookieHeader(header) {
  return String(header || "").split(";").map((part) => part.trim()).filter(Boolean).map((part) => {
    const splitAt = part.indexOf("=");
    return { name: splitAt < 0 ? part : part.slice(0, splitAt), value: splitAt < 0 ? "" : part.slice(splitAt + 1) };
  });
}

function serializeCookieHeader(name, value, options = {}) {
  const attrs = [`${name}=${value}`, `Path=${options.path || "/"}`];
  if (options.maxAge !== undefined) attrs.push(`Max-Age=${options.maxAge}`);
  if (options.httpOnly) attrs.push("HttpOnly");
  if (options.secure) attrs.push("Secure");
  if (options.sameSite) attrs.push(`SameSite=${options.sameSite}`);
  return attrs.join("; ");
}

function makeSsr(client, calls = []) {
  return {
    createServerClient(url, key, options) {
      calls.push({ url, key, options });
      client.cookieMethods = options.cookies;
      client.supabaseOptions = options;
      return client;
    },
    parseCookieHeader,
    serializeCookieHeader,
  };
}

function makeClient({ exchange, user, signInUrl = "https://travel-test.supabase.co/auth/v1/authorize?provider=google", events = [] } = {}) {
  return {
    cookieMethods: null,
    supabaseOptions: null,
    auth: {
      async signInWithOAuth(input) {
        events.push(["signInWithOAuth", input]);
        return { data: { url: signInUrl }, error: null };
      },
      async exchangeCodeForSession(code) {
        events.push(["exchangeCodeForSession", code]);
        return exchange ? exchange(code, this.client.cookieMethods) : { data: { session: null }, error: new Error("unexpected exchange") };
      },
      async getUser() {
        events.push(["getUser"]);
        return { data: { user: user === undefined ? { id: SUBJECT, email: "verified@example.test" } : user }, error: null };
      },
      async signOut(options) {
        events.push(["signOut", options]);
        this.client.cookieMethods.setAll([{
          name: "lm-web-auth",
          value: "",
          options: { path: "/", maxAge: 0, httpOnly: true },
        }]);
        return { error: null };
      },
      client: null,
    },
  };
}

function authClient(config = {}) {
  const client = makeClient(config);
  client.auth.client = client;
  return client;
}

function authOptions(client, extra = {}) {
  const calls = [];
  return {
    calls,
    options: {
      env: {
        SUPABASE_URL,
        SUPABASE_ANON_KEY: ANON_KEY,
        SUPABASE_SERVICE_ROLE_KEY: SERVICE_KEY,
        LM_UID_SECRET: "csrf-secret",
        NODE_ENV: "test",
      },
      publicOrigin: CALLBACK_ORIGIN,
      ssr: makeSsr(client, calls),
      ...extra,
    },
  };
}

function makeRestFetch(initialRows = []) {
  const rows = initialRows.map((row) => structuredClone(row));
  const calls = [];
  const fetch = async (input, init = {}) => {
    const url = new URL(input);
    const method = String(init.method || "GET").toUpperCase();
    const headers = init.headers || {};
    calls.push({ url: url.toString(), method, headers, body: init.body });
    const uidFilter = url.searchParams.get("uid") || "";
    const uid = uidFilter.startsWith("eq.") ? uidFilter.slice(3) : "";
    if (method === "GET") {
      const selected = String(url.searchParams.get("select") || "uid").split(",");
      const result = rows.filter((row) => row.uid === uid).map((row) => Object.fromEntries(
        selected.map((key) => [key, row[key]]),
      ));
      return response(200, result);
    }
    if (method === "POST") {
      const inserted = JSON.parse(init.body);
      if (!rows.some((row) => row.uid === inserted.uid)) rows.push({ ...inserted, telegram_chat_id: null });
      return response(201, null);
    }
    return response(405, { message: "unsupported method" });
  };
  return { fetch, rows, calls };
}

function callbackRequest({ code = "valid-code", cookie = "lm-web-auth-code-verifier=pkce-verifier", query = "", body = null } = {}) {
  return {
    method: "GET",
    url: `/auth/google/callback?code=${encodeURIComponent(code)}${query}`,
    headers: { cookie, host: "life-manager.example.test" },
    body,
  };
}

function setCookieHeaders(res) {
  const value = res.getHeader("set-cookie");
  return Array.isArray(value) ? value : value ? [value] : [];
}

function finalCookieValue(res, name) {
  const prefix = `${name}=`;
  const matching = setCookieHeaders(res).filter((header) => String(header).startsWith(prefix));
  if (!matching.length) return null;
  return String(matching.at(-1)).slice(prefix.length).split(";", 1)[0];
}

test("exchange requires PKCE verifier and verified Supabase subject", async () => {
  const missingClient = authClient();
  const missingFetch = makeRestFetch();
  const missingRes = makeResponse();
  const missingOpts = authOptions(missingClient, { fetch: missingFetch.fetch });
  await handleWebAuthRequest(callbackRequest({ cookie: "other=value" }), missingRes, missingOpts.options);
  assert.equal(missingRes.statusCode, 400);
  assert.deepEqual(missingFetch.calls, []);
  assert.deepEqual(missingClient.auth.client.supabaseOptions, null);
  assert.doesNotMatch(setCookieHeaders(missingRes).join("\n"), /lm-web-auth(?:=|-code-verifier=)[^;\n]+/);

  for (const code of ["invalid-code", "replayed-code"]) {
    const events = [];
    const client = authClient({
      events,
      exchange: async (seenCode) => {
        assert.equal(seenCode, code);
        return { data: { session: null }, error: new Error("invalid or replayed code") };
      },
    });
    const db = makeRestFetch();
    const res = makeResponse();
    const fixture = authOptions(client, { fetch: db.fetch });
    await handleWebAuthRequest(callbackRequest({ code }), res, fixture.options);
    assert.equal(res.statusCode, 401);
    assert.deepEqual(events.map(([name]) => name), ["exchangeCodeForSession"]);
    assert.deepEqual(db.calls, []);
    assert.doesNotMatch(setCookieHeaders(res).join("\n"), /lm-web-auth=[^;\n]+/);
  }

  const unverifiedEvents = [];
  const unverifiedClient = authClient({
    events: unverifiedEvents,
    user: null,
    exchange: async (_code, cookies) => {
      cookies.setAll([{ name: "lm-web-auth", value: "unverified-session", options: { path: "/", httpOnly: true } }]);
      return { data: { session: { access_token: "unverified-session" } }, error: null };
    },
  });
  const unverifiedDb = makeRestFetch();
  const unverifiedRes = makeResponse();
  const unverifiedFixture = authOptions(unverifiedClient, { fetch: unverifiedDb.fetch });
  await handleWebAuthRequest(callbackRequest(), unverifiedRes, unverifiedFixture.options);
  assert.equal(unverifiedRes.statusCode, 401);
  assert.deepEqual(unverifiedEvents.map(([name]) => name), ["exchangeCodeForSession", "getUser", "signOut"]);
  assert.deepEqual(unverifiedDb.calls, []);
  assert.equal(finalCookieValue(unverifiedRes, "lm-web-auth"), "");
});

test("OAuth start keeps the PKCE verifier cookie separate from the authenticated session cookie", async () => {
  const events = [];
  const client = authClient({ events });
  let receivedCookies;
  client.auth.signInWithOAuth = async (input) => {
    events.push(["signInWithOAuth", input]);
    receivedCookies = client.cookieMethods.getAll();
    client.cookieMethods.setAll([{
      name: "lm-web-auth-code-verifier",
      value: "pkce-verifier",
      options: { path: "/", httpOnly: true },
    }]);
    return { data: { url: "https://travel-test.supabase.co/auth/v1/authorize?provider=google" }, error: null };
  };
  const res = makeResponse();
  const fixture = authOptions(client);
  await handleWebAuthRequest({ method: "GET", url: "/auth/google", headers: { host: "life-manager.example.test", cookie: "existing=old" } }, res, fixture.options);

  assert.equal(res.statusCode, 302);
  assert.equal(res.getHeader("location"), "https://travel-test.supabase.co/auth/v1/authorize?provider=google");
  assert.equal(fixture.calls[0].key, ANON_KEY);
  assert.equal(fixture.calls[0].options.auth.flowType, "pkce");
  assert.equal(fixture.calls[0].options.cookieOptions.name, "lm-web-auth");
  assert.deepEqual(receivedCookies, [{ name: "existing", value: "old" }]);
  assert.match(setCookieHeaders(res).join("\n"), /lm-web-auth-code-verifier=pkce-verifier/);
  assert.doesNotMatch(setCookieHeaders(res).join("\n"), /lm-web-auth=/);
  const [, input] = events[0];
  assert.equal(input.provider, "google");
  assert.equal(input.options.redirectTo, `${CALLBACK_ORIGIN}/auth/google/callback`);
});

test("ignores client tenant fields and derives lm uid from subject", async () => {
  const events = [];
  const client = authClient({
    events,
    exchange: async (_code, cookies) => {
      cookies.setAll([
        { name: "lm-web-auth", value: "verified-session", options: { path: "/", httpOnly: true } },
        { name: "lm-web-auth-code-verifier", value: "", options: { path: "/", maxAge: 0 } },
        { name: "unrelated-cookie", value: "preserve", options: { path: "/" } },
      ]);
      return { data: { session: { access_token: "verified-session" } }, error: null };
    },
  });
  const db = makeRestFetch();
  const res = makeResponse();
  const fixture = authOptions(client, { fetch: db.fetch });
  const req = callbackRequest({
    query: "&uid=lm_attacker&email=attacker%40example.test&chat_id=999&paid=true",
    body: { uid: "lm_body_attacker", chat_id: "998", paid: true },
  });
  await handleWebAuthRequest(req, res, fixture.options);

  assert.equal(res.statusCode, 302);
  assert.equal(res.getHeader("location"), "/lm");
  assert.equal(finalCookieValue(res, "lm-web-auth"), "verified-session");
  assert.equal(finalCookieValue(res, "lm-web-auth-code-verifier"), "");
  assert.equal(finalCookieValue(res, "unrelated-cookie"), "preserve");
  assert.deepEqual(events.map(([name]) => name), ["exchangeCodeForSession", "getUser"]);
  const post = db.calls.find((call) => call.method === "POST");
  assert.ok(post);
  assert.deepEqual(JSON.parse(post.body), { uid: WEB_UID });
  assert.equal(post.headers.Prefer, "resolution=ignore-duplicates,return=minimal");
  assert.equal(post.headers.apikey, SERVICE_KEY);
  assert.notEqual(fixture.calls[0].key, SERVICE_KEY);
  assert.equal(db.rows.length, 1);
  assert.deepEqual(db.rows[0], { uid: WEB_UID, telegram_chat_id: null });

  const resolveEvents = [];
  const resolveClient = authClient({ events: resolveEvents });
  const resolveFixture = authOptions(resolveClient);
  const resolved = await resolveWebUser({
    method: "GET",
    url: "/api/lm/travel?uid=lm_attacker",
    headers: { cookie: "lm-web-auth=existing-session" },
    query: { uid: "lm_attacker" },
    body: { uid: "lm_body_attacker", paid: true },
  }, makeResponse(), { ...resolveFixture.options, csrfSecret: "csrf-secret" });
  assert.deepEqual(resolved, {
    uid: WEB_UID,
    subject: SUBJECT,
    email: "verified@example.test",
    csrf: createWebCsrfToken(WEB_UID, "csrf-secret"),
  });
  assert.deepEqual(resolveEvents.map(([name]) => name), ["getUser"]);
});

test("refuses Web session for Telegram-bound uid without changing row", async () => {
  const existing = {
    uid: WEB_UID,
    telegram_chat_id: "telegram-chat-77",
    paid: true,
    stripe_customer_id: "cus_keep_exactly",
    stripe_subscription_id: "sub_keep_exactly",
    stripe_price_id: "price_keep_exactly",
    email: "existing@example.test",
  };
  const before = structuredClone(existing);
  const events = [];
  const client = authClient({
    events,
    exchange: async (_code, cookies) => {
      cookies.setAll([{ name: "lm-web-auth", value: "temporary-session", options: { path: "/", httpOnly: true } }]);
      return { data: { session: { access_token: "temporary-session" } }, error: null };
    },
  });
  const db = makeRestFetch([existing]);
  const res = makeResponse();
  const fixture = authOptions(client, { fetch: db.fetch });
  await handleWebAuthRequest(callbackRequest(), res, fixture.options);

  assert.equal(res.statusCode, 403);
  assert.notEqual(res.getHeader("location"), "/lm");
  assert.deepEqual(events.map(([name]) => name), ["exchangeCodeForSession", "getUser", "signOut"]);
  assert.deepEqual(db.rows[0], before);
  assert.equal(db.calls.filter((call) => call.method === "POST").length, 0);
  assert.equal(finalCookieValue(res, "lm-web-auth"), "");

  const directDb = makeRestFetch([existing]);
  await assert.rejects(ensureWebUser(WEB_UID, {
    supabaseUrl: SUPABASE_URL,
    serviceRoleKey: SERVICE_KEY,
    fetch: directDb.fetch,
  }), /telegram-bound/i);
  assert.deepEqual(directDb.rows[0], before);
  assert.equal(directDb.calls.filter((call) => call.method === "POST").length, 0);
});

test("existing unbound rows are kept as-is and new rows use insert-only conflict-ignore", async () => {
  const existing = {
    uid: WEB_UID,
    telegram_chat_id: null,
    paid: true,
    stripe_customer_id: "cus_preserved",
    stripe_subscription_id: "sub_preserved",
  };
  const before = structuredClone(existing);
  const existingDb = makeRestFetch([existing]);
  await ensureWebUser(WEB_UID, { supabaseUrl: SUPABASE_URL, serviceRoleKey: SERVICE_KEY, fetch: existingDb.fetch });
  assert.deepEqual(existingDb.rows[0], before);
  assert.equal(existingDb.calls.filter((call) => call.method === "POST").length, 0);

  const newDb = makeRestFetch();
  await ensureWebUser(WEB_UID, { supabaseUrl: SUPABASE_URL, serviceRoleKey: SERVICE_KEY, fetch: newDb.fetch });
  const post = newDb.calls.find((call) => call.method === "POST");
  assert.deepEqual(JSON.parse(post.body), { uid: WEB_UID });
  assert.equal(post.headers.Prefer, "resolution=ignore-duplicates,return=minimal");
  assert.equal(newDb.calls.filter((call) => call.method === "GET").length, 2);
});

test("missing public Supabase anon key fails closed without using the service key", async () => {
  let created = false;
  const ssr = makeSsr(authClient());
  ssr.createServerClient = () => { created = true; throw new Error("must not create client"); };
  assert.throws(() => createWebAuthClient({}, makeResponse(), {
    env: { SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY: SERVICE_KEY },
    ssr,
  }), /SUPABASE_ANON_KEY/i);
  assert.equal(created, false);
  assert.throws(() => createWebAuthClient({}, makeResponse(), {
    env: { SUPABASE_URL, SUPABASE_ANON_KEY: SERVICE_KEY },
    ssr,
  }), /public key/i);
  assert.equal(created, false);

  const res = makeResponse();
  await handleWebAuthRequest({ method: "GET", url: "/auth/google", headers: { host: "life-manager.example.test" } }, res, {
    env: { SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY: SERVICE_KEY },
    ssr,
  });
  assert.equal(res.statusCode, 503);
  assert.equal(created, false);

  const callbackClient = authClient();
  const callbackDb = makeRestFetch();
  const callbackRes = makeResponse();
  const callbackFixture = authOptions(callbackClient, { fetch: callbackDb.fetch });
  callbackFixture.options.env = { SUPABASE_URL, SUPABASE_ANON_KEY: ANON_KEY, LM_UID_SECRET: "csrf-secret" };
  await handleWebAuthRequest(callbackRequest(), callbackRes, callbackFixture.options);
  assert.equal(callbackRes.statusCode, 503);
  assert.equal(callbackFixture.calls.length, 0);
  assert.deepEqual(callbackDb.calls, []);
  assert.equal(finalCookieValue(callbackRes, "lm-web-auth"), null);
});

test("CSRF token is deterministic, uid-bound HMAC-SHA256 and requires a secret", () => {
  const token = createWebCsrfToken(WEB_UID, "secret");
  assert.match(token, /^[0-9a-f]{64}$/);
  assert.notEqual(token, createWebCsrfToken("lm_aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "secret"));
  assert.notEqual(token, createWebCsrfToken(WEB_UID, "another-secret"));
  assert.throws(() => createWebCsrfToken(WEB_UID, ""), /secret/i);
});
