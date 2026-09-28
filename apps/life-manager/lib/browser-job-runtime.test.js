"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  completeBrowserHandoff,
  runNextBrowserJob,
  startBrowserJobLoop,
} = require("./browser-job-runtime.js");

const JOB = Object.freeze({
  id: "job-1",
  uid: "u-1",
  telegram_chat_id: "42",
  goal: "find and register",
  locale: "en",
});

const AUTH_JOB = Object.freeze({
  ...JOB,
  goal: "Open https://auth.example/account",
  requires_login: true,
  principal_kind: "user_provided",
});

function successfulDeps(overrides = {}) {
  const traces = [];
  return {
    traces,
    claimJob: async () => JOB,
    appendTrace: async (_id, stage) => { traces.push(stage); },
    finishJob: async () => true,
    sendMessage: async () => ({ ok: true, result: { message_id: 77 } }),
    sendPhoto: async () => ({ ok: true, result: { message_id: 78 } }),
    telegramToken: "token",
    driver: {
      openSession: async () => ({ id: "s1", websocketUrl: "ws://steel-browser.railway.internal:8080/" }),
      discoverAndAct: async () => ({
        selectedUrl: "https://fresh.example/done",
        selectedOrigin: "https://fresh.example",
        selectionReason: "matched",
        action: "registered",
        sideEffectStarted: true,
      }),
      readProviderReceipt: async () => ({
        confirmed: true,
        status: "registered",
        confirmationId: "r1",
        currentUrl: "https://fresh.example/done",
      }),
      captureEvidence: async () => ({
        mimeType: "image/png",
        bytes: Buffer.from("cloud-png"),
      }),
      releaseSession: async () => ({ released: true }),
    },
    ...overrides,
  };
}

test("the cloud worker claims one durable job and runs the complete generic browser task", async () => {
  const deps = successfulDeps();
  const result = await runNextBrowserJob(deps);
  assert.equal(result.status, "completed");
  assert.equal(result.selected_url, "https://fresh.example/done");
  assert.equal(result.telegram_message_id, "77");
  assert.equal(result.steel_released, true);
});

test("no queued job constructs no browser and causes no side effect", async () => {
  const result = await runNextBrowserJob({
    claimJob: async () => null,
    driver: { openSession: async () => { throw new Error("must not run"); } },
  });
  assert.deepEqual(result, { status: "idle" });
});

test("the worker injects agent-owned identity only when constructing the browser driver", async () => {
  let driverOptions;
  const deps = successfulDeps({
    driver: undefined,
    agentEmail: "browser-owner@example.test",
    agentName: "Browser Owner",
    makeDriver(options) {
      driverOptions = options;
      return successfulDeps().driver;
    },
  });
  const result = await runNextBrowserJob(deps);
  assert.equal(result.status, "completed");
  assert.equal(driverOptions.agentEmail, "browser-owner@example.test");
  assert.equal(driverOptions.agentName, "Browser Owner");
  assert.doesNotMatch(JSON.stringify(result), /browser-owner@example\.test/i);
});

test("the durable worker passes exact job identity and only a closed provider receipt through the auth lifecycle", async () => {
  const rawCookie = "raw-cookie-secret";
  const rawProviderError = "raw-provider-error";
  const rawReleaseContext = "raw-release-context";
  const traces = [];
  let openInput;
  let releaseInput;
  const baseDriver = successfulDeps().driver;
  const driver = {
    ...baseDriver,
    openSession: async (input) => {
      openInput = input;
      return { id: "s1", websocketUrl: "ws://steel-browser.railway.internal:8080/" };
    },
    readProviderReceipt: async () => ({
      confirmed: true,
      status: "account open",
      confirmationId: "receipt-1",
      currentUrl: "https://auth.example/account",
      handoffRequired: false,
      context: { cookies: [{ value: rawCookie }] },
      error: rawProviderError,
    }),
    releaseSession: async (sessionId, options) => {
      releaseInput = { sessionId, options };
      return {
        released: true,
        origin: "https://auth.example",
        principal_kind: "user_provided",
        auth_context_loaded: true,
        auth_context_saved: true,
        auth_context_invalidated: false,
        context_sha256: "a".repeat(64),
        key_version: 1,
        context: { cookies: [{ value: rawReleaseContext }] },
        error: rawProviderError,
      };
    },
  };
  const deps = successfulDeps({
    claimJob: async () => AUTH_JOB,
    appendTrace: async (_id, stage, meta) => { traces.push({ stage, meta }); },
    driver,
  });

  const result = await runNextBrowserJob(deps);

  assert.deepEqual(openInput, {
    uid: "u-1",
    ownerId: "job-1",
    goal: "Open https://auth.example/account",
    requiresLogin: true,
    principalKind: "user_provided",
  });
  assert.deepEqual(releaseInput, {
    sessionId: "s1",
    options: {
      providerReceipt: {
        confirmed: true,
        status: "account open",
        confirmation_id: "receipt-1",
        current_url: "https://auth.example/account",
        handoff_required: false,
        handoff_reason: null,
      },
    },
  });
  assert.deepEqual(
    traces.filter((entry) => entry.stage.startsWith("auth_context_")),
    [
      {
        stage: "auth_context_loaded",
        meta: {
          origin: "https://auth.example",
          principal_kind: "user_provided",
          loaded: true,
        },
      },
      {
        stage: "auth_context_saved",
        meta: {
          origin: "https://auth.example",
          principal_kind: "user_provided",
          saved: true,
          context_sha256: "a".repeat(64),
          key_version: 1,
        },
      },
    ],
  );
  const serialized = JSON.stringify({ result, traces });
  for (const secret of [rawCookie, rawProviderError, rawReleaseContext]) {
    assert.doesNotMatch(serialized, new RegExp(secret));
  }
});

test("the loop has an overlap guard so a slow browser job cannot be claimed twice", async () => {
  let claims = 0;
  let resolveClaim;
  const claimWait = new Promise((resolve) => { resolveClaim = resolve; });
  const scheduled = [];
  const loop = startBrowserJobLoop({
    enabled: true,
    intervalMs: 1000,
    setTimeoutImpl: (fn) => { scheduled.push(fn); return scheduled.length; },
    clearTimeoutImpl: () => {},
    runOnce: async () => {
      claims += 1;
      await claimWait;
    },
  });
  const first = loop.runNow();
  const second = loop.runNow();
  await Promise.resolve();
  assert.equal(claims, 1);
  resolveClaim();
  await Promise.all([first, second]);
  loop.close();
});

test("one held Steel session blocks another claim and completes through the same driver", async () => {
  let claims = 0;
  let releases = 0;
  const driver = {
    hasHeldSession: () => true,
    async readHeldReceipt(id) {
      assert.equal(id, "steel-1");
      return { confirmed: true, status: "application submitted", currentUrl: "https://work.mercor.com/application" };
    },
    async releaseSession(id, options) {
      releases += 1;
      assert.equal(id, "steel-1");
      assert.equal(options.providerReceipt.confirmed, true);
      return { released: true, auth_context_saved: true, context_sha256: "a".repeat(64), key_version: 1 };
    },
  };
  assert.deepEqual(await runNextBrowserJob({ driver, claimJob: async () => { claims += 1; return JOB; } }), { status: "handoff_waiting" });
  assert.equal(claims, 0);
  const completed = await completeBrowserHandoff("steel-1", "approve", { driver });
  assert.equal(completed.providerReceipt.confirmed, true);
  assert.equal(completed.release.released, true);
  assert.equal(releases, 1);
});

test("an expired held Steel session is released before the next durable claim", async () => {
  let held = true;
  let cleanups = 0;
  let claims = 0;
  const driver = {
    hasHeldSession: () => held,
    async releaseExpiredSessions() { cleanups += 1; held = false; return 1; },
  };

  const result = await runNextBrowserJob({
    driver,
    claimJob: async () => { claims += 1; return null; },
  });

  assert.deepEqual(result, { status: "idle" });
  assert.equal(cleanups, 1);
  assert.equal(claims, 1);
});
