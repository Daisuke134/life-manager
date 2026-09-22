"use strict";

const assert = require("node:assert/strict");
const http = require("node:http");
const test = require("node:test");

const { handlePanelApiRequest } = require("./panel-api.js");

const SESSION = "panel-session-a";
const SCOPE = Object.freeze({ uid: "tenant-a", chatId: "101", csrf: "csrf-a" });
const ORIGIN = "https://panel.example";

function projection(overrides = {}) {
  return {
    created: false,
    tenant_id: "tenant-a",
    goal_ref: "goal-portfolio://tenant-a/financial-continuity?revision=1",
    job_ref: "runtime-job://tenant-a/goal%3Afinancial-continuity%3Ar1",
    status: "queued",
    receipt_ref: null,
    ...overrides,
  };
}

async function withServer(service, run, overrides = {}) {
  const server = http.createServer((req, res) => {
    Promise.resolve(handlePanelApiRequest(req, res, {
      nowMs: Date.parse("2026-09-22T12:00:00.000Z"),
      panelOrigin: ORIGIN,
      sessionScopeImpl: async (session) => session === SESSION ? SCOPE : null,
      cloudGoalService: service,
      ...overrides,
    })).catch((error) => {
      res.writeHead(500, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: error.message }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    return await run(`http://127.0.0.1:${server.address().port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

async function request(base, path = "goals", options = {}) {
  const response = await fetch(`${base}/api/panel/${path}`, {
    method: options.method || "GET",
    headers: {
      Cookie: `lm_panel_session=${options.session === false ? "bad" : SESSION}`,
      ...(options.headers || {}),
    },
    body: options.body,
  });
  return { response, body: await response.json() };
}

function postHeaders(overrides = {}) {
  return {
    origin: ORIGIN,
    "content-type": "application/json",
    "x-lm-csrf": SCOPE.csrf,
    "idempotency-key": "cloud-goal-01",
    ...overrides,
  };
}

test("Goal GET reads only the authenticated session projection", async () => {
  const calls = [];
  await withServer({
    async read(input) { calls.push(input); return projection(); },
    async start() { throw new Error("must not start"); },
  }, async (base) => {
    const result = await request(base);
    assert.equal(result.response.status, 200);
    assert.deepEqual(result.body, projection());
    const override = await request(base, "goals?tenant_id=tenant-b");
    assert.equal(override.response.status, 400);
    assert.deepEqual(override.body, { error: "invalid_goal_request" });
  });
  assert.deepEqual(calls, [{ session: SESSION }]);
});

test("Goal POST accepts exactly an empty JSON body and starts durable work", async () => {
  const calls = [];
  await withServer({
    async read() { throw new Error("must not read"); },
    async start(input) { calls.push(input); return projection({ created: true }); },
  }, async (base) => {
    const result = await request(base, "goals", {
      method: "POST",
      headers: postHeaders(),
      body: "{}",
    });
    assert.equal(result.response.status, 200);
    assert.deepEqual(result.body, projection({ created: true }));
  });
  assert.deepEqual(calls, [{ session: SESSION, nowMs: Date.parse("2026-09-22T12:00:00.000Z") }]);
});

test("Goal POST rejects caller fields, missing JSON, Origin, CSRF, and idempotency before start", async () => {
  let starts = 0;
  const service = {
    async read() { return projection(); },
    async start() { starts += 1; return projection({ created: true }); },
  };
  await withServer(service, async (base) => {
    const cases = [
      { headers: postHeaders(), body: JSON.stringify({ goal: "make money" }), status: 400 },
      { headers: postHeaders({ "content-type": "text/plain" }), body: "{}", status: 415 },
      { headers: postHeaders({ origin: "https://evil.example" }), body: "{}", status: 403 },
      { headers: postHeaders({ "x-lm-csrf": "bad" }), body: "{}", status: 403 },
      { headers: postHeaders({ "idempotency-key": "bad" }), body: "{}", status: 400 },
    ];
    for (const item of cases) {
      const result = await request(base, "goals", { method: "POST", headers: item.headers, body: item.body });
      assert.equal(result.response.status, item.status);
    }
  });
  assert.equal(starts, 0);
});

test("Goal API rejects missing sessions and fails closed on service or projection drift", async () => {
  const service = {
    async read() { return projection(); },
    async start() { return projection({ created: true }); },
  };
  await withServer(service, async (base) => {
    const unauthorized = await request(base, "goals", { session: false });
    assert.equal(unauthorized.response.status, 401);
  });
  await withServer({ ...service, read: async () => projection({ tenant_id: "tenant-b" }) }, async (base) => {
    const foreign = await request(base);
    assert.equal(foreign.response.status, 502);
    assert.deepEqual(foreign.body, { error: "goal_unavailable" });
  });
  await withServer({ ...service, read: async () => { throw new Error("database secret detail"); } }, async (base) => {
    const unavailable = await request(base);
    assert.equal(unavailable.response.status, 502);
    assert.deepEqual(unavailable.body, { error: "goal_unavailable" });
  });
});
