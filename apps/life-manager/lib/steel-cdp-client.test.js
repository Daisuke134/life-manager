// steel-cdp-client.test.js — the self-hosted steel-browser rail (§10.0-12). Routes pinned against
// steel-dev/steel-browser api/src/modules/sessions/sessions.routes.ts + steel-browser-plugin.ts
// (prefix "/v1"): GET /v1/health, POST /v1/sessions, POST /v1/sessions/:id/release. There is NO
// DELETE /v1/sessions — a test that asserted one would be pinning a route that does not exist.
// Run: node --test lib/steel-cdp-client.test.js
"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { makeSteelCdpClient, STEEL_BASE_URL, READ_FORM_EXPRESSION } = require("./steel-cdp-client.js");
const {
  browserCastPublicUrl,
  createBrowserCastTicket,
  steelCastUrl,
  verifyBrowserCastTicket,
} = require("../server.js");

function fakeFetch(handler) {
  const calls = [];
  const impl = async (url, opts = {}) => {
    calls.push({ url, method: (opts.method || "GET").toUpperCase(), body: opts.body ? JSON.parse(opts.body) : null });
    return handler(url, opts);
  };
  impl.calls = calls;
  return impl;
}

const ok = (json) => ({ ok: true, status: 200, json: async () => json, text: async () => JSON.stringify(json) });

test("the private-networking base URL is the Railway internal service, never a public domain", () => {
  assert.equal(STEEL_BASE_URL, "http://steel-browser.railway.internal:8080");
});

test("createSession posts /v1/sessions and returns the CDP websocket url", async () => {
  const fetchImpl = fakeFetch(() => ok({ id: "abc", websocketUrl: "ws://steel-browser.railway.internal:8080/", status: "live" }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({}) });
  const session = await client.createSession();

  assert.deepEqual(session, { id: "abc", websocketUrl: "ws://steel-browser.railway.internal:8080/" });
  assert.equal(fetchImpl.calls[0].url, "http://steel-browser.railway.internal:8080/v1/sessions");
  assert.equal(fetchImpl.calls[0].method, "POST");
});

test("interactive debugger copies Steel HTML but replaces its private cast URL", async () => {
  const privateUrl = "ws://steel-browser.railway.internal:8080/v1/sessions/cast";
  const publicUrl = `wss://life-call-production.up.railway.app/api/panel/money-printer/browser/cast/payload.${"s".repeat(43)}`;
  const source = `<iframe></iframe><script>const ws=${JSON.stringify(privateUrl)}</script>`;
  let calls = 0;
  const client = makeSteelCdpClient({
    fetchImpl: async () => {
      calls += 1;
      return calls === 1
        ? ok({ id: "steel-1", status: "live" })
        : { ok: true, status: 200, text: async () => source };
    },
  });
  const html = await client.getInteractiveDebugger("steel-1", publicUrl);
  assert.match(html, new RegExp(publicUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.doesNotMatch(html, /railway\.internal|ws:\/\//i);
});

test("browser cast ticket is short-lived, scoped, tamper-evident, and Railway-only", () => {
  const now = 1_788_300_000_000;
  const secret = "s".repeat(64);
  const input = {
    uid: `webmcp-guest-${"a".repeat(24)}`,
    browserJobId: "11111111-1111-4111-8111-111111111111",
    expiresAt: now + 120_000,
  };
  const ticket = createBrowserCastTicket(input, secret);
  assert.match(ticket, /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}$/);
  assert.deepEqual(verifyBrowserCastTicket(ticket, secret, now), input);
  const tampered = `${ticket.slice(0, -1)}${ticket.endsWith("x") ? "y" : "x"}`;
  assert.equal(verifyBrowserCastTicket(tampered, secret, now), null);
  assert.equal(verifyBrowserCastTicket(ticket, "x".repeat(64), now), null);
  assert.deepEqual(verifyBrowserCastTicket(ticket, secret, now + 120_001), { expired: true });
  assert.equal(
    browserCastPublicUrl(ticket, { RAILWAY_PUBLIC_DOMAIN: "life-call-production.up.railway.app" }),
    `wss://life-call-production.up.railway.app/api/panel/money-printer/browser/cast/${encodeURIComponent(ticket)}`,
  );
  assert.throws(() => browserCastPublicUrl(ticket, { RAILWAY_PUBLIC_DOMAIN: "aniccaai.com" }), /domain/i);
});

test("takeover proxy binds the private Steel cast to its owned session", () => {
  assert.equal(
    steelCastUrl("steel-1"),
    "ws://steel-browser.railway.internal:8080/v1/sessions/cast?sessionId=steel-1",
  );
  assert.equal(
    steelCastUrl("steel-1", { tabInfo: "true" }),
    "ws://steel-browser.railway.internal:8080/v1/sessions/cast?sessionId=steel-1&tabInfo=true",
  );
  assert.equal(
    steelCastUrl("steel-1", { pageId: "ABC123" }),
    "ws://steel-browser.railway.internal:8080/v1/sessions/cast?sessionId=steel-1&pageId=ABC123",
  );
  for (const invalid of ["", "../foreign", "steel/foreign", "a?token=secret"]) {
    assert.throws(() => steelCastUrl(invalid), /session/i);
  }
  assert.throws(() => steelCastUrl("steel-1", { pageId: "../foreign" }), /session/i);
});

test("createRawSession leaves the private Steel CDP endpoint unattached for Stagehand", async () => {
  let connectCalls = 0;
  const fetchImpl = fakeFetch(() => ok({
    id: "raw-1",
    websocketUrl: "ws://steel-browser.railway.internal:8080/",
    status: "live",
  }));
  const client = makeSteelCdpClient({
    fetchImpl,
    connectCdp: async () => {
      connectCalls += 1;
      return {};
    },
  });
  assert.deepEqual(await client.createRawSession(), {
    id: "raw-1",
    websocketUrl: "ws://steel-browser.railway.internal:8080/",
  });
  assert.equal(connectCalls, 0, "Stagehand, not the deterministic booking client, owns this CDP socket");
});

test("the session contract binds a local launch and strips contract metadata from Steel", async () => {
  const fetchImpl = fakeFetch(() => ok({
    id: "local-1",
    websocketUrl: "ws://steel:3000/",
    status: "live",
  }));
  const client = makeSteelCdpClient({
    baseUrl: "http://steel:3000/",
    fetchImpl,
    connectCdp: async () => ({}),
    sessionConfig: {
      scope: { tenantId: "tenant-a", ownerId: "owner-a", provider: "lancers" },
      storage: { origins: ["https://lancers.jp"], cookieNames: ["session"] },
    },
  });
  const session = await client.createRawSession({
    blockAds: true,
    browserSession: {
      scope: { tenantId: "tenant-a", ownerId: "owner-a", provider: "lancers" },
      storage: { origins: ["https://lancers.jp"], cookieNames: ["session"] },
    },
  });

  assert.deepEqual(session, { id: "local-1", websocketUrl: "ws://steel:3000/" });
  assert.equal(client.baseUrl, "http://steel:3000");
  assert.equal(client.sessionContract.endpoint, "http://steel:3000");
  assert.deepEqual(fetchImpl.calls[0].body, { blockAds: true });
});

test("a launch whose CDP socket leaves the configured host is released and rejected", async () => {
  const fetchImpl = fakeFetch((url) => url.endsWith("/release")
    ? ok({ success: true })
    : ok({ id: "local-2", websocketUrl: "ws://other:3000/", status: "live" }));
  const client = makeSteelCdpClient({
    baseUrl: "http://steel:3000",
    fetchImpl,
    connectCdp: async () => ({}),
  });

  await assert.rejects(() => client.createRawSession(), /endpoint host/i);
  assert.deepEqual(fetchImpl.calls.map((call) => call.url), [
    "http://steel:3000/v1/sessions",
    "http://steel:3000/v1/sessions/local-2/release",
  ]);
});

test("getSessionContext exports and validates the complete Steel browser context", async () => {
  const context = {
    cookies: [{
      name: "sid",
      value: "opaque",
      domain: "auth.example",
      path: "/",
      secure: true,
      httpOnly: true,
    }],
    localStorage: { "https://auth.example": { theme: "dark" } },
    sessionStorage: {},
    indexedDB: {},
  };
  const fetchImpl = fakeFetch(() => ok(context));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({}) });

  assert.deepEqual(await client.getSessionContext("abc"), context);
  assert.equal(
    fetchImpl.calls[0].url,
    "http://steel-browser.railway.internal:8080/v1/sessions/abc/context",
  );
  assert.equal(fetchImpl.calls[0].method, "GET");
});

test("getSessionContext fails closed for missing ids, unknown keys, oversized contexts, and Steel errors", async () => {
  const missingFetch = fakeFetch(() => ok({}));
  const missingClient = makeSteelCdpClient({ fetchImpl: missingFetch, connectCdp: async () => ({}) });
  await assert.rejects(() => missingClient.getSessionContext(""), /session id/i);
  assert.equal(missingFetch.calls.length, 0, "an invalid id never reaches Steel");

  const unknownClient = makeSteelCdpClient({
    fetchImpl: fakeFetch(() => ok({ cookies: [], accessTokens: {} })),
    connectCdp: async () => ({}),
  });
  await assert.rejects(() => unknownClient.getSessionContext("abc"), /browser auth context invalid/i);

  const oversizedClient = makeSteelCdpClient({
    fetchImpl: fakeFetch(() => ok({
      localStorage: { "https://auth.example": { payload: "x".repeat(1024 * 1024) } },
    })),
    connectCdp: async () => ({}),
  });
  await assert.rejects(() => oversizedClient.getSessionContext("abc"), /browser auth context invalid/i);

  const responseSecret = "raw-cookie-value-must-not-leak";
  const failedClient = makeSteelCdpClient({
    fetchImpl: fakeFetch(() => ({
      ok: false,
      status: 502,
      text: async () => responseSecret,
    })),
    connectCdp: async () => ({}),
  });
  const failure = await failedClient.getSessionContext("abc").then(() => null, (error) => error);
  assert.match(String(failure && failure.message), /502/);
  assert.doesNotMatch(String(failure && failure.message), new RegExp(responseSecret));
});

test("createRawSession injects only an explicitly supplied sessionContext", async () => {
  const context = {
    cookies: [{ name: "sid", value: "opaque", domain: "auth.example", path: "/" }],
  };
  const fetchImpl = fakeFetch(() => ok({
    id: "raw-auth",
    websocketUrl: "ws://steel-browser.railway.internal:8080/",
    status: "live",
  }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({}) });

  await client.createRawSession({ blockAds: true, sessionContext: context });

  assert.deepEqual(fetchImpl.calls[0].body, { blockAds: true, sessionContext: context });
  assert.equal(Object.hasOwn(fetchImpl.calls[0].body, "persist"), false);
  assert.equal(Object.hasOwn(fetchImpl.calls[0].body, "userDataDir"), false);
});

test("createRawSession rejects shared-profile persistence options before calling Steel", async () => {
  for (const forbidden of [{ persist: true }, { userDataDir: "/tmp/shared-profile" }]) {
    const fetchImpl = fakeFetch(() => ok({}));
    const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({}) });
    await assert.rejects(() => client.createRawSession(forbidden), /persistent Steel profiles/i);
    assert.equal(fetchImpl.calls.length, 0);
  }
});

test("a failed context-bearing launch never echoes Steel response bodies", async () => {
  const rawSecret = "reflected-cookie-secret";
  const fetchImpl = fakeFetch(() => ({
    ok: false,
    status: 400,
    text: async () => `invalid sessionContext value=${rawSecret}`,
  }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({}) });

  const error = await client.createRawSession({
    sessionContext: {
      cookies: [{ name: "sid", value: rawSecret, domain: "auth.example", path: "/" }],
    },
  }).then(() => null, (failure) => failure);

  assert.match(String(error && error.message), /400/);
  assert.doesNotMatch(String(error && error.message), new RegExp(rawSecret));
});

test("releaseSession posts the verified per-session release route", async () => {
  const fetchImpl = fakeFetch(() => ok({ success: true }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({}) });
  await client.releaseSession("abc");
  assert.equal(fetchImpl.calls[0].url, "http://steel-browser.railway.internal:8080/v1/sessions/abc/release");
  assert.equal(fetchImpl.calls[0].method, "POST");
});

test("a failed session launch throws rather than returning a phantom session", async () => {
  const fetchImpl = fakeFetch(() => ({ ok: false, status: 503, text: async () => "service_unavailable" }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({}) });
  await assert.rejects(() => client.createSession(), /503/);
});

test("health checks the verified /v1/health route", async () => {
  const fetchImpl = fakeFetch(() => ok({ status: "ok" }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({}) });
  assert.equal(await client.health(), true);
  assert.equal(fetchImpl.calls[0].url, "http://steel-browser.railway.internal:8080/v1/health");
});

test("page work runs over the session's CDP connection and reads real form fields", async () => {
  const evaluated = [];
  const connectCdp = async (websocketUrl) => ({
    websocketUrl,
    async evaluate(expression) { evaluated.push(expression); return FORM; },
    async close() { evaluated.push("close"); },
  });
  const FORM = {
    submitSelector: "form button[type=submit]",
    fields: [{ selector: "#name", label: "お名前", name: "name", type: "text", required: true }],
  };
  const fetchImpl = fakeFetch(() => ok({ id: "abc", websocketUrl: "ws://steel-browser.railway.internal:8080/", status: "live" }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp });

  await client.createSession();
  const form = await client.readForm("abc");
  assert.deepEqual(form, FORM);
  assert.equal(evaluated.length, 1);
  assert.match(evaluated[0], /querySelectorAll/);
});

test("releaseSession also closes the CDP connection so the single OSS session is really free", async () => {
  let closed = 0;
  const connectCdp = async () => ({ async evaluate() { return null; }, async close() { closed += 1; } });
  const fetchImpl = fakeFetch(() => ok({ id: "abc", websocketUrl: "ws://steel-browser.railway.internal:8080/", status: "live" }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp });
  await client.createSession();
  await client.readForm("abc");
  await client.releaseSession("abc");
  assert.equal(closed, 1);
});

// ─── review findings ────────────────────────────────────────────────────────────────────────────

// 🔴 Finding 5: connect() throwing AFTER POST /v1/sessions succeeded leaks the ONE session the OSS
// build allows — every later booking for every user then fails to launch.
test("a CDP connect failure releases the session it had already created", async () => {
  const fetchImpl = fakeFetch((url) => (url.endsWith("/release")
    ? ok({ success: true })
    : ok({ id: "abc", websocketUrl: "ws://steel-browser.railway.internal:8080/", status: "live" })));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => { throw new Error("connect ECONNREFUSED"); } });

  const error = await client.createSession().then(() => null, (e) => e);
  assert.match(String(error && error.message), /ECONNREFUSED/);
  assert.equal(error.sessionId, "abc", "the orphaned session id rides on the error");
  assert.equal(error.sessionReleased, true);
  assert.ok(
    fetchImpl.calls.some((c) => c.url.endsWith("/v1/sessions/abc/release") && c.method === "POST"),
    `expected a release of the orphaned session, got ${JSON.stringify(fetchImpl.calls.map((c) => c.url))}`,
  );
});

test("a per-session release failure falls back to the release-ALL route", async () => {
  const fetchImpl = fakeFetch((url) => {
    if (url.endsWith("/v1/sessions/abc/release")) return { ok: false, status: 500, text: async () => "boom" };
    if (url.endsWith("/v1/sessions")) return ok({ id: "abc", websocketUrl: "ws://steel-browser.railway.internal:8080/", status: "live" });
    return ok({ success: true });
  });
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({ async close() {} }) });
  await client.createSession();
  assert.equal(await client.releaseSession("abc"), true);
  assert.ok(
    fetchImpl.calls.some((c) => c.url === "http://steel-browser.railway.internal:8080/v1/sessions/release"),
    "a stuck session blocks everyone, so release-all is the fallback",
  );
});

test("a release that fails BOTH ways still throws rather than claiming the slot is free", async () => {
  const fetchImpl = fakeFetch(() => ({ ok: false, status: 500, text: async () => "boom" }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp: async () => ({ async close() {} }) });
  await assert.rejects(() => client.releaseSession("abc"), /release failed/);
});

test("waitForLoad rides through to the CDP connection", async () => {
  const seen = [];
  const connectCdp = async () => ({ async waitForLoad(timeoutMs) { seen.push(timeoutMs); return { loaded: true }; }, async close() {} });
  const fetchImpl = fakeFetch(() => ok({ id: "abc", websocketUrl: "ws://steel-browser.railway.internal:8080/", status: "live" }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp });
  await client.createSession();
  assert.deepEqual(await client.waitForLoad("abc", 1234), { loaded: true });
  assert.deepEqual(seen, [1234]);
});

// ─── the page-side probe, run against a stub DOM ────────────────────────────────────────────────
// No jsdom in this service, and the probe is deliberately selector-POOR precisely so it can be
// exercised without one: every query it makes is a plain tag list.
function node(tag, attrs = {}, children = []) {
  const el = {
    tagName: tag.toUpperCase(),
    attrs: { ...attrs },
    children: [],
    parentElement: null,
    get id() { return this.attrs.id || ""; },
    get name() { return this.attrs.name || ""; },
    get type() { return this.attrs.type || ""; },
    get className() { return this.attrs.class || ""; },
    get htmlFor() { return this.attrs.for || ""; },
    get required() { return this.attrs.required === true; },
    get maxLength() { return this.attrs.maxlength === undefined ? -1 : Number(this.attrs.maxlength); },
    get textContent() { return String(this.attrs.text || "") + this.children.map((c) => c.textContent).join(""); },
    getAttribute(key) {
      const value = this.attrs[key];
      if (value === undefined) return null;
      return value === true ? "" : String(value);
    },
    querySelectorAll(selector) {
      const tags = selector.split(",").map((part) => part.trim().toUpperCase());
      const out = [];
      const walk = (n) => { for (const child of n.children) { if (tags.includes(child.tagName)) out.push(child); walk(child); } };
      walk(this);
      return out;
    },
  };
  for (const child of children) { child.parentElement = el; el.children.push(child); }
  return el;
}

function readForm(bodyChildren) {
  const html = node("html", {}, [node("body", {}, bodyChildren)]);
  const body = html.children[0];
  const document = {
    documentElement: html,
    body,
    get forms() { return body.querySelectorAll("form"); },
    querySelectorAll: (selector) => body.querySelectorAll(selector),
    querySelector: (selector) => body.querySelectorAll(selector)[0] || null,
  };
  // eslint-disable-next-line no-new-func
  return new Function("document", "CSS", `return ${READ_FORM_EXPRESSION};`)(document, { escape: (s) => String(s) });
}

// 🔴 Finding 9: the old fallback returned 'form button[type="submit"], form input[type="submit"]' even
// when the control it FOUND was a <button> with no type — a selector that could never match it.
test("the submit selector describes the control that was actually found", () => {
  const form = node("form", {}, [
    node("input", { type: "text", name: "name" }),
    node("button", { text: "送信" }), // no id, no type — the case the old fallback could not express
  ]);
  const result = readForm([form]);
  assert.ok(result.submitSelector, "a submit control was found");
  assert.doesNotMatch(result.submitSelector, /,/, "never a comma-list that may resolve to another element");
  assert.match(result.submitSelector, /button(?::nth-of-type\(\d+\))?$/, `got ${result.submitSelector}`);
});

test("an id'd submit control still gets the cheap id selector", () => {
  const form = node("form", {}, [
    node("input", { type: "text", name: "name" }),
    node("button", { type: "submit", id: "go", text: "送信" }),
  ]);
  assert.equal(readForm([form]).submitSelector, "#go");
});

// 🟡 Finding 16: a booking page usually carries a search box and a login panel too. The FIRST form is
// a coin flip; the form the booking vocabulary recognises is the one we came for.
test("the form with the most mapped fields wins, not the first one on the page", () => {
  const search = node("form", { id: "search" }, [node("input", { type: "text", name: "q", id: "q" })]);
  const login = node("form", { id: "login" }, [
    node("input", { type: "text", name: "userid", id: "uid" }),
    node("input", { type: "password", name: "pw", id: "pw" }),
  ]);
  const booking = node("form", { id: "booking" }, [
    node("label", { for: "n", text: "お名前" }),
    node("input", { type: "text", name: "name", id: "n" }),
    node("label", { for: "t", text: "電話番号" }),
    node("input", { type: "tel", name: "tel", id: "t" }),
    node("label", { for: "d", text: "ご希望日時" }),
    node("input", { type: "datetime-local", name: "dt", id: "d" }),
    node("button", { type: "submit", id: "go", text: "予約する" }),
  ]);
  const result = readForm([search, login, booking]);
  assert.deepEqual(result.fields.map((f) => f.selector), ["#n", "#t", "#d"]);
  assert.equal(result.submitSelector, "#go");
  assert.equal(result.formsScanned, 3);
  assert.equal(result.mappedFieldCount, 3);
});

// 🟡 Finding 17: 必須 is usually a span or a class, not the HTML required attribute. A requirement we
// can SEE is a requirement — and an unfillable one then ends the attempt instead of submitting blind.
test("a 必須 marker in the label counts as required even without the HTML attribute", () => {
  const form = node("form", {}, [
    node("label", { for: "n", text: "お名前" }, [node("span", { class: "req", text: "必須" })]),
    node("input", { type: "text", name: "name", id: "n" }),
    node("label", { for: "m", text: "ご相談内容" }),
    node("input", { type: "text", name: "memo", id: "m" }),
    node("button", { type: "submit", id: "go", text: "送信" }),
  ]);
  const byId = Object.fromEntries(readForm([form]).fields.map((f) => [f.selector, f]));
  assert.equal(byId["#n"].required, true, "the 必須 marker is a requirement");
  assert.equal(byId["#m"].required, false, "an unmarked field is not invented into one");
});

// 🟡 Finding 12 (probe half): maxlength has to reach the executor, or it cannot refuse to truncate.
test("the probe reports maxlength so the U8 identification is never silently truncated", () => {
  const form = node("form", {}, [
    node("label", { for: "n", text: "お名前" }),
    node("input", { type: "text", name: "name", id: "n", maxlength: 10 }),
    node("label", { for: "e", text: "メールアドレス" }),
    node("input", { type: "email", name: "email", id: "e" }),
    node("button", { type: "submit", id: "go", text: "送信" }),
  ]);
  const byId = Object.fromEntries(readForm([form]).fields.map((f) => [f.selector, f]));
  assert.equal(byId["#n"].maxLength, 10);
  assert.equal(byId["#e"].maxLength, null);
});

// The executor reads THIS exact string as "the click was provably never dispatched" and reports a
// clean honest_failure off it. If the page-side wording ever drifts, that failure silently becomes a
// possibly_booked instead — so the coupling is pinned here rather than left to memory.
test("the submit helper throws the sentinel the executor keys its zero-submits failure on", async () => {
  const { SUBMIT_NOT_FOUND_MESSAGE } = require("./steel-cdp-client.js");
  const { SUBMIT_NEVER_DISPATCHED } = require("./care-booking-executor.js");
  assert.match(SUBMIT_NOT_FOUND_MESSAGE, SUBMIT_NEVER_DISPATCHED, "the two ends of the contract still agree");

  let expression = null;
  const connectCdp = async () => ({ async evaluate(source) { expression = source; return true; }, async close() {} });
  const fetchImpl = fakeFetch(() => ok({ id: "abc", websocketUrl: "ws://steel-browser.railway.internal:8080/", status: "live" }));
  const client = makeSteelCdpClient({ fetchImpl, connectCdp });
  await client.createSession();
  await client.submit("abc", "#go");
  assert.ok(expression.includes(JSON.stringify(SUBMIT_NOT_FOUND_MESSAGE)), "the page throws the sentinel, not a paraphrase");
  assert.ok(expression.indexOf("throw") < expression.indexOf("click"), "and it throws BEFORE dispatching a click");
});
