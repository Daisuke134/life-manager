"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const vm = require("node:vm");
const { captureWebAttribution, consumeWebAttribution } = require("./web-attribution.js");
const { handleWebAuthRequest } = require("./web-auth.js");
const { renderWebPage } = require("./web-page.js");

const SUPABASE_URL = "https://travel-test.supabase.co";
const CALLBACK_ORIGIN = "https://life-manager.example.test";
const SUBJECT = "11111111-2222-4333-8444-555555555555";
const VERIFIED_UID = `lm_${SUBJECT}`;
const SERVICE_KEY = `test.${Buffer.from(JSON.stringify({ role: "service_role" })).toString("base64url")}.sig`;
const SECRET = "server-only-lm-uid-secret";
const NOW = Date.parse("2026-10-06T00:00:00.000Z");
const TTL_MS = 30 * 24 * 60 * 60 * 1000;

function response(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return body; },
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
  if (options.expires) attrs.push(`Expires=${new Date(options.expires).toUTCString()}`);
  if (options.httpOnly) attrs.push("HttpOnly");
  if (options.secure) attrs.push("Secure");
  if (options.sameSite) attrs.push(`SameSite=${options.sameSite}`);
  return attrs.join("; ");
}

function makeFlow(initialRows = [], behavior = {}) {
  const events = [];
  const rows = initialRows.map((row) => structuredClone(row));
  const client = {
    cookieMethods: null,
    auth: {
      async signInWithOAuth(input) {
        events.push(["signInWithOAuth", input]);
        client.cookieMethods.setAll([{
          name: "lm-web-auth-code-verifier",
          value: "pkce-verifier",
          options: { path: "/", httpOnly: true, secure: true, sameSite: "lax" },
        }]);
        return { data: { url: "https://travel-test.supabase.co/auth/v1/authorize?provider=google" }, error: null };
      },
      async exchangeCodeForSession(code) {
        events.push(["exchangeCodeForSession", code]);
        client.cookieMethods.setAll([{
          name: "lm-web-auth.0",
          value: "verified-session-chunk",
          options: { path: "/", httpOnly: true, secure: true, sameSite: "lax" },
        }]);
        return { data: { session: { access_token: "test-session" } }, error: null };
      },
      async getUser() {
        events.push(["getUser"]);
        return { data: { user: {
          id: SUBJECT,
          email: "verified@example.test",
          app_metadata: { provider: "google", providers: ["google"] },
          identities: [{ provider: "google", id: SUBJECT }],
        } }, error: null };
      },
      async signOut() { return { error: null }; },
    },
  };
  const ssr = {
    createServerClient(url, key, options) {
      assert.equal(url, SUPABASE_URL);
      assert.notEqual(key, SERVICE_KEY);
      client.cookieMethods = options.cookies;
      return client;
    },
    parseCookieHeader,
    serializeCookieHeader,
  };
  const calls = [];
  const fetch = async (input, init = {}) => {
    const url = new URL(input);
    const method = String(init.method || "GET").toUpperCase();
    const headers = init.headers || {};
    calls.push({ url, method, headers, body: init.body });
    const uidFilter = url.searchParams.get("uid") || "";
    const uid = uidFilter.startsWith("eq.") ? decodeURIComponent(uidFilter.slice(3)) : "";
    if (method === "GET") {
      const selected = String(url.searchParams.get("select") || "uid").split(",");
      const result = rows.filter((row) => row.uid === uid).map((row) => Object.fromEntries(
        selected.map((key) => [key, row[key]]),
      ));
      events.push(["db:GET", url.searchParams.toString()]);
      return response(200, result);
    }
    if (method === "POST") {
      const inserted = JSON.parse(init.body);
      if (!rows.some((row) => row.uid === inserted.uid)) rows.push({ ...inserted, telegram_chat_id: null });
      events.push(["db:POST", inserted]);
      return response(201, null);
    }
    if (method === "PATCH") {
      const patch = JSON.parse(init.body);
      events.push(["db:PATCH", url.searchParams.toString(), patch]);
      const row = rows.find((candidate) => candidate.uid === uid);
      if (behavior.patchMode === "delete") {
        if (row) rows.splice(rows.indexOf(row), 1);
        return response(200, []);
      }
      if (behavior.patchMode === "telegram-bound") {
        if (row) row.telegram_chat_id = "chat-existing";
        return response(200, []);
      }
      if (behavior.patchMode === "zero") return response(200, []);
      if (row && url.searchParams.get("web_first_touch") === "is.null"
        && url.searchParams.get("telegram_chat_id") === "is.null"
        && row.web_first_touch == null && row.telegram_chat_id == null) {
        Object.assign(row, patch);
        return response(200, [{
          uid: row.uid,
          telegram_chat_id: row.telegram_chat_id,
          web_first_touch: row.web_first_touch,
        }]);
      }
      return response(200, []);
    }
    return response(405, { message: "unsupported method" });
  };
  const options = {
    env: {
      SUPABASE_URL,
      SUPABASE_ANON_KEY: "public-anon-key",
      SUPABASE_SERVICE_ROLE_KEY: SERVICE_KEY,
      LM_UID_SECRET: SECRET,
      NODE_ENV: "production",
    },
    publicOrigin: CALLBACK_ORIGIN,
    ssr,
    fetch,
  };
  return { events, rows, calls, client, options };
}

function responseCookies(res) {
  const value = res.getHeader("set-cookie");
  return Array.isArray(value) ? value.map(String) : value ? [String(value)] : [];
}

function cookieValue(headers, name) {
  const prefix = `${name}=`;
  const matching = headers.filter((header) => header.startsWith(prefix));
  return matching.length ? matching.at(-1).slice(prefix.length).split(";", 1)[0] : null;
}

function oauthCallback(cookie) {
  return {
    method: "GET",
    url: "/auth/google/callback?code=verified-code",
    headers: {
      host: "life-manager.example.test",
      cookie: ["lm-web-auth-code-verifier=pkce-verifier", cookie].filter(Boolean).join("; "),
    },
  };
}

test("preserves signed first-touch through Google OAuth", async () => {
  const flow = makeFlow([{
    uid: VERIFIED_UID,
    telegram_chat_id: null,
    paid: false,
    stripe_customer_id: "cus-existing",
    stripe_subscription_id: "sub-existing",
    plan_status: "trialing",
    web_first_touch: null,
  }]);
  const start = makeResponse();
  await handleWebAuthRequest({
    method: "GET",
    url: "/auth/google?utm_source=instagram&utm_medium=social&utm_campaign=october-travel",
    headers: { host: "life-manager.example.test" },
  }, start, flow.options);

  assert.equal(start.statusCode, 302);
  const startCookies = responseCookies(start);
  assert.ok(startCookies.some((header) => header.startsWith("lm-web-auth-code-verifier=")), "OAuth PKCE cookie remains set");
  const attributionCookie = cookieValue(startCookies, "lm-web-attribution");
  assert.ok(attributionCookie, "first-touch cookie is set");
  assert.ok(startCookies.some((header) => header.startsWith("lm-web-attribution=")
    && /Max-Age=2592000/.test(header) && /HttpOnly/.test(header) && /Secure/.test(header) && /SameSite=Lax/i.test(header)));
  assert.deepEqual(consumeWebAttribution(attributionCookie, SECRET, Date.now()), {
    utm_source: "instagram",
    utm_medium: "social",
    utm_campaign: "october-travel",
  });

  const callback = makeResponse();
  await handleWebAuthRequest(oauthCallback(`lm-web-attribution=${attributionCookie}`), callback, flow.options);

  assert.equal(callback.statusCode, 302);
  assert.equal(callback.getHeader("location"), "/lm?start_calendar=1");
  const patch = flow.calls.find((call) => call.method === "PATCH");
  assert.ok(patch, "callback stores attribution on the existing user row");
  assert.equal(patch.url.pathname, "/rest/v1/lm_users");
  assert.equal(patch.url.searchParams.get("uid"), `eq.${VERIFIED_UID}`);
  assert.equal(patch.url.searchParams.get("web_first_touch"), "is.null");
  assert.equal(patch.url.searchParams.get("telegram_chat_id"), "is.null");
  assert.deepEqual(JSON.parse(patch.body), { web_first_touch: {
    utm_source: "instagram",
    utm_medium: "social",
    utm_campaign: "october-travel",
  } });
  assert.ok(flow.events.findIndex(([name]) => name === "getUser") < flow.events.findIndex(([name]) => name === "db:PATCH"));
  assert.equal(flow.rows[0].paid, false);
  assert.equal(flow.rows[0].stripe_customer_id, "cus-existing");
  assert.equal(flow.rows[0].stripe_subscription_id, "sub-existing");
  assert.equal(flow.rows[0].plan_status, "trialing");
  const callbackCookies = responseCookies(callback);
  assert.ok(callbackCookies.some((header) => header.startsWith("lm-web-auth.0=verified-session-chunk")), "SSR session cookie survives attribution cleanup");
  assert.equal(cookieValue(callbackCookies, "lm-web-attribution"), "", "consumed cookie is expired");
});

test("rejects tampered or expired attribution without blocking sign-in", async () => {
  const query = new URLSearchParams("utm_source=x&utm_campaign=fall");
  const signed = captureWebAttribution(query, SECRET, NOW);
  const [payload, signature] = signed.split(".");
  const tampered = `${payload}.${signature[0] === "0" ? "1" : "0"}${signature.slice(1)}`;
  assert.equal(consumeWebAttribution(tampered, SECRET, NOW), null);
  assert.equal(consumeWebAttribution(signed, SECRET, NOW + TTL_MS + 1), null);
  assert.equal(consumeWebAttribution(signed, "different-secret", NOW), null);

  for (const cookie of [
    `lm-web-attribution=${tampered}`,
    null,
    `lm-web-attribution=${captureWebAttribution(query, SECRET, Date.now() - TTL_MS - 1)}`,
  ]) {
    const flow = makeFlow([{ uid: VERIFIED_UID, telegram_chat_id: null, paid: false, web_first_touch: null }]);
    const res = makeResponse();
    await handleWebAuthRequest(oauthCallback(cookie), res, flow.options);
    assert.equal(res.statusCode, 302, "invalid attribution does not reject a verified sign-in");
    assert.equal(flow.calls.some((call) => call.method === "PATCH"), false, "invalid attribution causes no write");
    assert.equal(flow.rows[0].web_first_touch, null);
  }

  const bounded = consumeWebAttribution(captureWebAttribution(new URLSearchParams([
    ["utm_source", "x"],
    ["utm_medium", "social"],
    ["utm_id", "must-not-pass"],
    ["utm_content", "z".repeat(241)],
  ]), SECRET, NOW), SECRET, NOW);
  assert.deepEqual(bounded, { utm_source: "x", utm_medium: "social" }, "unknown and oversized values are discarded");
});

test("keeps first touch immutable", async () => {
  const firstTouch = { utm_source: "instagram", utm_campaign: "first-campaign" };
  const flow = makeFlow([{ uid: VERIFIED_UID, telegram_chat_id: null, paid: false, web_first_touch: firstTouch }]);
  const cookie = captureWebAttribution(new URLSearchParams("utm_source=x&utm_campaign=second-campaign"), SECRET, Date.now());
  const res = makeResponse();
  await handleWebAuthRequest(oauthCallback(`lm-web-attribution=${cookie}`), res, flow.options);

  assert.equal(res.statusCode, 302);
  assert.deepEqual(flow.rows[0].web_first_touch, firstTouch);
  assert.equal(flow.calls.filter((call) => call.method === "PATCH").length, 1);
  assert.equal(flow.calls.find((call) => call.method === "PATCH").url.searchParams.get("web_first_touch"), "is.null");
});

test("zero-row update accepts only a read-back immutable first-touch winner", async () => {
  const firstTouch = { utm_source: "instagram", utm_campaign: "earlier-winner" };
  const flow = makeFlow([{ uid: VERIFIED_UID, telegram_chat_id: null, paid: false, web_first_touch: firstTouch }]);
  const cookie = captureWebAttribution(new URLSearchParams("utm_source=x&utm_campaign=concurrent"), SECRET, Date.now());
  const res = makeResponse();
  await handleWebAuthRequest(oauthCallback(`lm-web-attribution=${cookie}`), res, flow.options);

  assert.equal(res.statusCode, 302);
  assert.deepEqual(flow.rows[0].web_first_touch, firstTouch);
  assert.ok(flow.calls.some((call) => call.method === "GET"
    && call.url.searchParams.get("select") === "uid,telegram_chat_id,web_first_touch"), "zero-row update reads back the exact user row");
  assert.equal(cookieValue(responseCookies(res), "lm-web-attribution"), "", "verified immutable winner permits cookie cleanup");
});

test("zero-row update retains attribution unless readback verifies storage", async () => {
  const cases = [
    { name: "still-null row", patchMode: "zero", rows: [{ uid: VERIFIED_UID, telegram_chat_id: null, paid: false, web_first_touch: null }] },
    { name: "missing row", patchMode: "delete", rows: [{ uid: VERIFIED_UID, telegram_chat_id: null, paid: false, web_first_touch: null }] },
    { name: "Telegram-bound row", patchMode: "telegram-bound", rows: [{ uid: VERIFIED_UID, telegram_chat_id: null, paid: false, web_first_touch: null }] },
  ];
  for (const fixture of cases) {
    const flow = makeFlow(fixture.rows, { patchMode: fixture.patchMode });
    const cookie = captureWebAttribution(new URLSearchParams("utm_source=x"), SECRET, Date.now());
    const res = makeResponse();
    await handleWebAuthRequest(oauthCallback(`lm-web-attribution=${cookie}`), res, flow.options);

    assert.equal(res.statusCode, 302, `${fixture.name}: valid login continues`);
    assert.ok(flow.calls.some((call) => call.method === "GET"
      && call.url.searchParams.get("select") === "uid,telegram_chat_id,web_first_touch"), `${fixture.name}: exact row readback attempted`);
    assert.equal(responseCookies(res).some((header) => header.startsWith("lm-web-attribution=")), false,
      `${fixture.name}: unverified save keeps the browser's signed cookie`);
  }
});

test("Web Checkout uses the server session and never exposes a static payment URL or client uid", () => {
  const html = renderWebPage({
    user: { uid: VERIFIED_UID, csrf: "csrf-token" },
    snapshot: { setupState: "trial_offer", checkoutAvailable: true, paid: false },
    stripePaymentLink: "https://buy.stripe.com/example",
    query: { uid: "lm_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
  });
  assert.match(html, /\/api\/lm-web\/checkout/);
  assert.doesNotMatch(html, /buy\.stripe\.com/);
  assert.doesNotMatch(html, /client_reference_id=|uid=lm_aaaaaaaa/);
});

test("carries only approved UTM values from /lm to the Google sign-in link", () => {
  const html = renderWebPage({});
  assert.match(html, /id="lm-sign-in"/);
  const script = html.match(/<script>([\s\S]*?)<\/script>/);
  assert.ok(script);
  const link = {
    href: "/auth/google",
    getAttribute(name) { return name === "href" ? "/auth/google" : null; },
  };
  vm.runInNewContext(script[1], {
    URL,
    URLSearchParams,
    document: {
      getElementById(id) { return id === "lm-sign-in" ? link : null; },
      querySelector() { return null; },
    },
    window: { location: { href: "https://life-manager.example.test/lm?utm_source=instagram&utm_campaign=travel&utm_id=discard" } },
  });

  const destination = new URL(link.href, CALLBACK_ORIGIN);
  assert.equal(destination.pathname, "/auth/google");
  assert.equal(destination.searchParams.get("utm_source"), "instagram");
  assert.equal(destination.searchParams.get("utm_campaign"), "travel");
  assert.equal(destination.searchParams.has("utm_id"), false);
});
