"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");

const {
  assertBrowserSession,
  createBrowserSessionConfig,
  normalizeBrowserEndpoint,
  normalizeStoragePolicy,
} = require("./session-contract.cjs");

const SCOPE = {
  tenantId: "tenant-a",
  ownerId: "owner-a",
  provider: "coconala",
};

const STORAGE = {
  origins: ["https://coconala.com"],
  cookieNames: ["session"],
  localStorageKeys: ["theme"],
  sessionStorageKeys: ["csrf"],
};

test("local and private cloud Steel endpoints use one normalized endpoint contract", () => {
  assert.equal(normalizeBrowserEndpoint("http://127.0.0.1:9222/"), "http://127.0.0.1:9222");
  assert.equal(normalizeBrowserEndpoint("http://steel:3000/"), "http://steel:3000");
  assert.equal(
    normalizeBrowserEndpoint("http://steel-browser.railway.internal:8080/"),
    "http://steel-browser.railway.internal:8080",
  );
});

test("public endpoints require an explicit HTTPS opt-in and never accept URL credentials", () => {
  assert.throws(
    () => normalizeBrowserEndpoint("https://steel.example.com"),
    /private endpoint/i,
  );
  assert.equal(
    normalizeBrowserEndpoint("https://steel.example.com/", { allowPublicEndpoint: true }),
    "https://steel.example.com",
  );
  for (const value of [
    "http://steel.example.com",
    "https://user:secret@steel.example.com",
    "https://steel.example.com/?token=secret",
    "https://steel.example.com/v1",
  ]) {
    assert.throws(() => normalizeBrowserEndpoint(value, { allowPublicEndpoint: true }), /endpoint/i);
  }
});

test("storage policy is an explicit provider allowlist with no wildcard or secret values", () => {
  assert.deepEqual(normalizeStoragePolicy(STORAGE), {
    origins: ["https://coconala.com"],
    cookie_names: ["session"],
    local_storage_keys: ["theme"],
    session_storage_keys: ["csrf"],
  });
  assert.throws(
    () => normalizeStoragePolicy({ ...STORAGE, origins: ["*"] }),
    /origin/i,
  );
  assert.throws(
    () => normalizeStoragePolicy({ ...STORAGE, cookieNames: ["*"] }),
    /cookie/i,
  );
  assert.throws(
    () => normalizeStoragePolicy({ ...STORAGE, localStorageKeys: ["auth_token"] }),
    /storage key/i,
  );
});

test("headless is the default; headed mode is only legal for human gates or diagnostics", () => {
  const automatic = createBrowserSessionConfig({ scope: SCOPE, storage: STORAGE });
  assert.equal(automatic.mode, "headless");
  assert.equal(automatic.headless, true);
  assert.throws(
    () => createBrowserSessionConfig({ scope: SCOPE, storage: STORAGE, mode: "headed" }),
    /headed.*human_gate.*diagnostic/i,
  );
  const handoff = createBrowserSessionConfig({
    scope: SCOPE,
    storage: STORAGE,
    mode: "headed",
    purpose: "human_gate",
  });
  assert.equal(handoff.headless, false);
  assert.equal(handoff.purpose, "human_gate");
});

test("session config binds tenant, owner, provider, limits, and storage without mutable aliases", () => {
  const config = createBrowserSessionConfig({
    endpoint: "http://steel:3000",
    scope: SCOPE,
    storage: STORAGE,
    limits: { maxPages: 2, timeoutMs: 20_000, idleTimeoutMs: 60_000 },
  });
  assert.deepEqual(config.scope, {
    tenant_id: "tenant-a",
    owner_id: "owner-a",
    provider: "coconala",
  });
  assert.deepEqual(config.limits, {
    max_pages: 2,
    timeout_ms: 20_000,
    idle_timeout_ms: 60_000,
  });
  assert.equal(Object.isFrozen(config), true);
  assert.equal(Object.isFrozen(config.scope), true);
  assert.equal(Object.isFrozen(config.storage), true);
});

test("a session endpoint must stay on the configured private Steel host", () => {
  const config = createBrowserSessionConfig({
    endpoint: "http://steel:3000",
    scope: SCOPE,
    storage: STORAGE,
  });
  assert.deepEqual(
    assertBrowserSession(
      { id: "steel-session-1", websocketUrl: "ws://steel:3000/" },
      config,
    ),
    { id: "steel-session-1", websocket_url: "ws://steel:3000/" },
  );
  assert.throws(
    () => assertBrowserSession(
      { id: "steel-session-1", websocketUrl: "ws://other:3000/" },
      config,
    ),
    /endpoint host/i,
  );
  assert.throws(
    () => assertBrowserSession(
      { id: "steel-session-1", websocketUrl: "ws://user:secret@steel:3000/" },
      config,
    ),
    /websocket/i,
  );
});
