// test/inngest.test.js — Inngest scheduling layer tests (node:test style, no real network)
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

// ──────────────────────────────────────────────────────────────────────────────
// SECTION A: per-user functions exist in scheduler.js
// ──────────────────────────────────────────────────────────────────────────────

test("scheduler exports wakeUserOnce as a function", () => {
  // Set required env so scheduler.js require() does not throw on startup
  process.env.LM_CALL_SECRET = process.env.LM_CALL_SECRET || "test_secret";
  const sched = require("../scheduler.js");
  assert.strictEqual(typeof sched.wakeUserOnce, "function", "wakeUserOnce must be exported");
});

test("scheduler exports travelUserOnce as a function", () => {
  process.env.LM_CALL_SECRET = process.env.LM_CALL_SECRET || "test_secret";
  const sched = require("../scheduler.js");
  assert.strictEqual(typeof sched.travelUserOnce, "function", "travelUserOnce must be exported");
});

test("scheduler exports askUserOnce as a function", () => {
  process.env.LM_CALL_SECRET = process.env.LM_CALL_SECRET || "test_secret";
  const sched = require("../scheduler.js");
  assert.strictEqual(typeof sched.askUserOnce, "function", "askUserOnce must be exported");
});

test("scheduler exports listPaidUsers as a function", () => {
  process.env.LM_CALL_SECRET = process.env.LM_CALL_SECRET || "test_secret";
  const sched = require("../scheduler.js");
  assert.strictEqual(typeof sched.listPaidUsers, "function", "listPaidUsers must be exported");
});

test("scheduler exports getUserByUid as a function (FIND-004)", () => {
  process.env.LM_CALL_SECRET = process.env.LM_CALL_SECRET || "test_secret";
  const sched = require("../scheduler.js");
  assert.strictEqual(typeof sched.getUserByUid, "function", "getUserByUid must be exported");
});

// ──────────────────────────────────────────────────────────────────────────────
// SECTION B: Inngest client module
// ──────────────────────────────────────────────────────────────────────────────

test("inngest/client.js exports an inngest object", () => {
  const { inngest } = require("../inngest/client.js");
  assert.ok(inngest, "inngest export must exist");
  // The Inngest SDK object has a send method for dispatching events
  assert.strictEqual(typeof inngest.send, "function", "inngest.send must be a function");
});

// ──────────────────────────────────────────────────────────────────────────────
// SECTION B2: server.js uses inngest/node adapter — FIND-002(a)
// ──────────────────────────────────────────────────────────────────────────────

test("server.js imports serve from inngest/node (not inngest/express) — FIND-002", () => {
  const src = fs.readFileSync(path.join(__dirname, "../server.js"), "utf8");
  assert.ok(
    src.includes("inngest/node"),
    "server.js must import from inngest/node (raw Node http adapter)"
  );
  assert.ok(
    !src.includes("inngest/express"),
    "server.js must NOT import from inngest/express"
  );
});

// ──────────────────────────────────────────────────────────────────────────────
// SECTION C: Inngest functions module — sweeper fan-out behaviour
// ──────────────────────────────────────────────────────────────────────────────

test("inngest/functions.js exports a functions array", () => {
  const mod = require("../inngest/functions.js");
  assert.ok(Array.isArray(mod.functions), "functions export must be an array");
  assert.strictEqual(mod.functions.length, 8, "must export exactly 8 Inngest functions");
  const investment = mod.functions.find((fn) => fn.opts && fn.opts.id === "investment-cloud-dry-run");
  assert.ok(investment);
  assert.deepStrictEqual(investment.opts.triggers, [{ cron: "*/5 * * * *" }]);
});

test("cloud-job is tenant-serialized and triggered only by lm/cloud.job", () => {
  const mod = require("../inngest/functions.js");
  const cloud = mod.functions.find((fn) => fn.opts && fn.opts.id === "cloud-job");
  assert.ok(cloud);
  assert.deepStrictEqual(cloud.opts.triggers, [{ event: "lm/cloud.job" }]);
  assert.deepStrictEqual(cloud.opts.concurrency, {
    key: "event.data.tenant_id",
    limit: 1,
  });
});

test("cloud-job handler passes tenant/job identifiers only through one durable step", async () => {
  const { makeCloudJobHandler } = require("../inngest/functions.js");
  const calls = [];
  const handler = makeCloudJobHandler(async (value) => {
    calls.push(value);
    return { disposition: "completed" };
  });
  const { step, calls: stepCalls } = fakeStep();

  const result = await handler({
    event: { data: { tenant_id: "tenant-a", job_id: "job-a" } },
    step,
  });

  assert.deepStrictEqual(result, { disposition: "completed" });
  assert.deepStrictEqual(calls, [{ tenant_id: "tenant-a", job_id: "job-a" }]);
  assert.deepStrictEqual(stepCalls.run, ["dispatch-cloud-job"]);
});

// Helper: build a fake step object that records calls
function fakeStep() {
  const calls = { run: [], sendEvent: [] };
  const step = {
    run: async (label, fn) => {
      calls.run.push(label);
      return fn();
    },
    sendEvent: async (name, events) => {
      calls.sendEvent.push({ name, events });
      return events;
    },
  };
  return { step, calls };
}

// ── Single-writer guard (FIND-003) ───────────────────────────────────────────

test("sweep-wake handler does NOTHING (no sendEvent) when LIFE_RUN_LOOPS is unset — FIND-003", async () => {
  const { makeSweepWakeHandler } = require("../inngest/functions.js");

  const fakeUsers = [{ uid: "uid-aaa" }];
  // Simulate env where LIFE_RUN_LOOPS is NOT "false" (in-process loops are ON)
  const handler = makeSweepWakeHandler(async () => fakeUsers, { getEnv: () => ({}) });
  const { step, calls } = fakeStep();

  await handler({ step });

  assert.strictEqual(calls.sendEvent.length, 0, "must not call sendEvent when in-process loops are on");
});

test("sweep-travel handler does NOTHING (no sendEvent) when LIFE_RUN_LOOPS is 'true' — FIND-003", async () => {
  const { makeSweepTravelHandler } = require("../inngest/functions.js");

  const fakeUsers = [{ uid: "uid-bbb" }];
  const handler = makeSweepTravelHandler(async () => fakeUsers, { getEnv: () => ({ LIFE_RUN_LOOPS: "true" }) });
  const { step, calls } = fakeStep();

  await handler({ step });

  assert.strictEqual(calls.sendEvent.length, 0, "must not call sendEvent when LIFE_RUN_LOOPS=true");
});

test("sweep-ask handler does NOTHING (no sendEvent) when LIFE_RUN_LOOPS is unset — FIND-003", async () => {
  const { makeSweepAskHandler } = require("../inngest/functions.js");

  const fakeUsers = [{ uid: "uid-ccc" }];
  const handler = makeSweepAskHandler(async () => fakeUsers, { getEnv: () => ({}) });
  const { step, calls } = fakeStep();

  await handler({ step });

  assert.strictEqual(calls.sendEvent.length, 0, "must not call sendEvent when in-process loops are on");
});

test("sweep-wake handler fans out when LIFE_RUN_LOOPS=false — FIND-003", async () => {
  const { makeSweepWakeHandler } = require("../inngest/functions.js");

  const fakeUsers = [
    { uid: "uid-aaa", phone: "+810000000000" },
    { uid: "uid-bbb", phone: "+810000000000" },
  ];
  const handler = makeSweepWakeHandler(
    async () => fakeUsers,
    { getEnv: () => ({ LIFE_RUN_LOOPS: "false", INNGEST_SIGNING_KEY: "test-signing-key" }) }
  );
  const { step, calls } = fakeStep();

  await handler({ step });

  assert.ok(calls.run.some((l) => l === "list"), "step.run('list') must be called");
  assert.strictEqual(calls.sendEvent.length, 1, "step.sendEvent called once (fan-out)");
  const [fanOut] = calls.sendEvent;
  assert.strictEqual(fanOut.events.length, 2, "must fan-out exactly 2 events (one per user)");
  assert.ok(
    fanOut.events.every((e) => e.name === "lm/wake.user"),
    "every fan-out event must be named lm/wake.user"
  );
});

// ── PII fan-out: only { uid } in event.data — FIND-004 ──────────────────────

test("sweep-wake fans out ONLY { uid } not full user row — FIND-004", async () => {
  const { makeSweepWakeHandler } = require("../inngest/functions.js");

  const fakeUsers = [
    { uid: "uid-pii-1", phone: "+810000000000", home_address: "secret address", access_token: "tok123" },
  ];
  const handler = makeSweepWakeHandler(
    async () => fakeUsers,
    { getEnv: () => ({ LIFE_RUN_LOOPS: "false", INNGEST_SIGNING_KEY: "test-signing-key" }) }
  );
  const { step, calls } = fakeStep();

  await handler({ step });

  const [fanOut] = calls.sendEvent;
  const eventData = fanOut.events[0].data;
  assert.deepStrictEqual(eventData, { uid: "uid-pii-1" }, "fan-out data must contain ONLY uid, not phone/tokens/address");
  assert.ok(!eventData.phone, "phone must not be in fan-out payload");
  assert.ok(!eventData.home_address, "home_address must not be in fan-out payload");
  assert.ok(!eventData.access_token, "tokens must not be in fan-out payload");
});

test("sweep-travel fans out ONLY { uid } — FIND-004", async () => {
  const { makeSweepTravelHandler } = require("../inngest/functions.js");

  const fakeUsers = [
    { uid: "uid-pii-2", phone: "+810000000000", home_address: "private" },
  ];
  const handler = makeSweepTravelHandler(
    async () => fakeUsers,
    { getEnv: () => ({ LIFE_RUN_LOOPS: "false", INNGEST_SIGNING_KEY: "test-signing-key" }) }
  );
  const { step, calls } = fakeStep();

  await handler({ step });

  const eventData = calls.sendEvent[0].events[0].data;
  assert.deepStrictEqual(eventData, { uid: "uid-pii-2" });
});

test("sweep-ask fans out ONLY { uid } — FIND-004", async () => {
  const { makeSweepAskHandler } = require("../inngest/functions.js");

  const fakeUsers = [
    { uid: "uid-pii-3", phone: "+810000000000" },
  ];
  const handler = makeSweepAskHandler(
    async () => fakeUsers,
    { getEnv: () => ({ LIFE_RUN_LOOPS: "false", INNGEST_SIGNING_KEY: "test-signing-key" }) }
  );
  const { step, calls } = fakeStep();

  await handler({ step });

  const eventData = calls.sendEvent[0].events[0].data;
  assert.deepStrictEqual(eventData, { uid: "uid-pii-3" });
});

// ── Sweeper edge: empty user list → 0 sendEvent — FIND-002(b) ────────────────

test("sweep-wake with empty user list → 0 sendEvent calls — FIND-002", async () => {
  const { makeSweepWakeHandler } = require("../inngest/functions.js");

  const handler = makeSweepWakeHandler(
    async () => [],
    { getEnv: () => ({ LIFE_RUN_LOOPS: "false", INNGEST_SIGNING_KEY: "test-signing-key" }) }
  );
  const { step, calls } = fakeStep();

  await handler({ step });

  // FIND-103: the sweeper guards `if (!users || !users.length) return;` BEFORE step.sendEvent,
  // so an empty user list fans out NOTHING — sendEvent is never called (not even with []).
  assert.strictEqual(calls.sendEvent.length, 0, "empty user list → no sendEvent at all");
});

const { makeSweepWakeHandler, makeSweepTravelHandler, makeSweepAskHandler } = require("../inngest/functions.js");
for (const makeHandler of [makeSweepWakeHandler, makeSweepTravelHandler, makeSweepAskHandler]) {
  test(`${makeHandler.name} is a no-op for the standalone missing-Inngest fallback`, async () => {
    const handler = makeHandler(async () => [{ uid: "fallback-user" }], {
      getEnv: () => ({ LIFE_RUN_LOOPS: "off", LM_DEPLOYMENT_ROLE: "", INNGEST_SIGNING_KEY: " \t\n" }),
    });
    const { step, calls } = fakeStep();
    await handler({ step });
    assert.equal(calls.sendEvent.length, 0);
    assert.equal(calls.run.length, 0);
  });
}

test("sweep-wake fans out in trimmed Inngest dev mode while standalone loops stay off", async () => {
  const { makeSweepWakeHandler } = require("../inngest/functions.js");
  const handler = makeSweepWakeHandler(async () => [{ uid: "dev-user" }], {
    getEnv: () => ({ LIFE_RUN_LOOPS: "off", INNGEST_DEV: " 1 " }),
  });
  const { step, calls } = fakeStep();
  await handler({ step });
  assert.equal(calls.sendEvent.length, 1);
  assert.deepStrictEqual(calls.sendEvent[0].events[0].data, { uid: "dev-user" });
});

// ──────────────────────────────────────────────────────────────────────────────
// SECTION D: per-user handler functions invoke the right per-user fn via re-fetch
// ──────────────────────────────────────────────────────────────────────────────

test("wake-user handler re-fetches user by uid then invokes wakeUserOnce — FIND-004", async () => {
  const { makeWakeUserHandler } = require("../inngest/functions.js");

  const fullUser = { uid: "uid-fff", phone: "+1555000111", home_address: "123 Main St" };
  let fetchCalledWith = null;
  let wakeCalledWith = null;

  const stubGetUser = async (uid) => { fetchCalledWith = uid; return fullUser; };
  const stubWakeUserOnce = async (u, nowMs) => { wakeCalledWith = { u, nowMs }; };

  const handler = makeWakeUserHandler(stubWakeUserOnce, stubGetUser);
  const { step } = fakeStep();

  const before = Date.now();
  await handler({ event: { data: { uid: "uid-fff" } }, step });
  const after = Date.now();

  assert.strictEqual(fetchCalledWith, "uid-fff", "getUserByUid must be called with the uid from event.data");
  assert.deepStrictEqual(wakeCalledWith.u, fullUser, "wakeUserOnce receives the re-fetched full user row");
  assert.ok(
    wakeCalledWith.nowMs >= before && wakeCalledWith.nowMs <= after,
    "wakeUserOnce receives a current timestamp"
  );
});

test("travel-user handler re-fetches user then invokes travelUserOnce — FIND-004", async () => {
  const { makeTravelUserHandler } = require("../inngest/functions.js");

  const fullUser = { uid: "uid-ggg", phone: "+819001234" };
  let travelCalledWith = null;

  const stubGetUser = async () => fullUser;
  const stub = async (u) => { travelCalledWith = u; };

  const handler = makeTravelUserHandler(stub, stubGetUser);
  const { step } = fakeStep();

  await handler({ event: { data: { uid: "uid-ggg" } }, step });
  assert.deepStrictEqual(travelCalledWith, fullUser);
});

test("ask-user handler re-fetches user then invokes askUserOnce — FIND-004", async () => {
  const { makeAskUserHandler } = require("../inngest/functions.js");

  const fullUser = { uid: "uid-hhh", phone: "+819005678" };
  let askCalledWith = null;

  const stubGetUser = async () => fullUser;
  const stub = async (u) => { askCalledWith = u; };

  const handler = makeAskUserHandler(stub, stubGetUser);
  const { step } = fakeStep();

  await handler({ event: { data: { uid: "uid-hhh" } }, step });
  assert.deepStrictEqual(askCalledWith, fullUser);
});

// ── Per-user fn: missing/unknown uid → no-op, no throw — FIND-002(b) ─────────

test("wake-user handler: unknown uid (getUserByUid → null) → no-op, no throw — FIND-002", async () => {
  const { makeWakeUserHandler } = require("../inngest/functions.js");

  let wakeCalled = false;
  const stubGetUser = async () => null; // uid not found
  const stubWakeOnce = async () => { wakeCalled = true; };

  const handler = makeWakeUserHandler(stubWakeOnce, stubGetUser);
  const { step } = fakeStep();

  // Must not throw
  await assert.doesNotReject(async () => {
    await handler({ event: { data: { uid: "uid-unknown" } }, step });
  });
  assert.strictEqual(wakeCalled, false, "wakeUserOnce must NOT be called when uid not found");
});

test("travel-user handler: unknown uid → no-op, no throw — FIND-002", async () => {
  const { makeTravelUserHandler } = require("../inngest/functions.js");

  let travelCalled = false;
  const stubGetUser = async () => null;
  const stub = async () => { travelCalled = true; };

  const handler = makeTravelUserHandler(stub, stubGetUser);
  const { step } = fakeStep();

  await assert.doesNotReject(async () => {
    await handler({ event: { data: { uid: "uid-unknown" } }, step });
  });
  assert.strictEqual(travelCalled, false);
});

test("ask-user handler: unknown uid → no-op, no throw — FIND-002", async () => {
  const { makeAskUserHandler } = require("../inngest/functions.js");

  let askCalled = false;
  const stubGetUser = async () => null;
  const stub = async () => { askCalled = true; };

  const handler = makeAskUserHandler(stub, stubGetUser);
  const { step } = fakeStep();

  await assert.doesNotReject(async () => {
    await handler({ event: { data: { uid: "uid-unknown" } }, step });
  });
  assert.strictEqual(askCalled, false);
});

test("wake-user handler: missing uid in event.data → no-op, no throw — FIND-002", async () => {
  const { makeWakeUserHandler } = require("../inngest/functions.js");

  let wakeCalled = false;
  const stubGetUser = async () => ({ uid: "x" });
  const stubWakeOnce = async () => { wakeCalled = true; };

  const handler = makeWakeUserHandler(stubWakeOnce, stubGetUser);
  const { step } = fakeStep();

  await assert.doesNotReject(async () => {
    await handler({ event: { data: {} }, step }); // no uid
  });
  assert.strictEqual(wakeCalled, false, "must not call wakeOnce when uid is missing");
});

// ──────────────────────────────────────────────────────────────────────────────
// SECTION E: concurrency config on per-user functions
// ──────────────────────────────────────────────────────────────────────────────

test("wake-user Inngest function has concurrency key 'event.data.uid'", () => {
  const { functions } = require("../inngest/functions.js");
  const wakeUser = functions.find((f) => f.opts && f.opts.id === "wake-user");
  assert.ok(wakeUser, "wake-user function must exist in the exported array");
  const conc = wakeUser.opts.concurrency;
  assert.ok(conc, "wake-user must have concurrency configured");
  const key = Array.isArray(conc) ? conc[0].key : conc.key;
  assert.strictEqual(key, "event.data.uid", "concurrency key must be event.data.uid");
});

test("travel-user Inngest function has concurrency key 'event.data.uid'", () => {
  const { functions } = require("../inngest/functions.js");
  const fn = functions.find((f) => f.opts && f.opts.id === "travel-user");
  assert.ok(fn, "travel-user function must exist");
  const conc = fn.opts.concurrency;
  const key = Array.isArray(conc) ? conc[0].key : conc.key;
  assert.strictEqual(key, "event.data.uid");
});

test("ask-user Inngest function has concurrency key 'event.data.uid'", () => {
  const { functions } = require("../inngest/functions.js");
  const fn = functions.find((f) => f.opts && f.opts.id === "ask-user");
  assert.ok(fn, "ask-user function must exist");
  const conc = fn.opts.concurrency;
  const key = Array.isArray(conc) ? conc[0].key : conc.key;
  assert.strictEqual(key, "event.data.uid");
});

// ──────────────────────────────────────────────────────────────────────────────
// SECTION F: server.js mounts /api/inngest (structural check via source read)
// ──────────────────────────────────────────────────────────────────────────────

test("server.js source contains the /api/inngest mount", () => {
  const src = fs.readFileSync(path.join(__dirname, "../server.js"), "utf8");
  assert.ok(
    src.includes("/api/inngest"),
    "server.js must mount the Inngest serve handler at /api/inngest"
  );
});

test("server.js source still contains /ws (WebSocket bridge not removed)", () => {
  const src = fs.readFileSync(path.join(__dirname, "../server.js"), "utf8");
  assert.ok(src.includes("/ws"), "server.js must keep the /ws WebSocket bridge");
});

test("server.js source still contains LIFE_RUN_LOOPS gate (in-process path preserved)", () => {
  const src = fs.readFileSync(path.join(__dirname, "../server.js"), "utf8");
  assert.ok(
    src.includes("LIFE_RUN_LOOPS"),
    "server.js must keep the LIFE_RUN_LOOPS gate so both paths coexist"
  );
});

// ──────────────────────────────────────────────────────────────────────────────
// SECTION G: inngestServeAllowed — fail-closed prod auth (FIND-005)
// ──────────────────────────────────────────────────────────────────────────────

test("inngestServeAllowed returns true in dev (INNGEST_DEV=1) even without signing key — FIND-005", () => {
  const { inngestServeAllowed } = require("../server.js");
  const result = inngestServeAllowed({ INNGEST_DEV: "1" });
  assert.strictEqual(result, true, "dev mode must always allow serving");
});

test("inngestServeAllowed accepts trimmed INNGEST_DEV=1 via the shared predicate", () => {
  const { inngestServeAllowed } = require("../server.js");
  assert.strictEqual(inngestServeAllowed({ INNGEST_DEV: " 1 " }), true);
});

test("inngestServeAllowed returns true in dev with INNGEST_DEV=1 and signing key present — FIND-005", () => {
  const { inngestServeAllowed } = require("../server.js");
  const result = inngestServeAllowed({ INNGEST_DEV: "1", INNGEST_SIGNING_KEY: "sk-abc" });
  assert.strictEqual(result, true, "dev+key must allow serving");
});

test("inngestServeAllowed returns false in prod (no INNGEST_DEV) when signing key missing — FIND-005", () => {
  const { inngestServeAllowed } = require("../server.js");
  const result = inngestServeAllowed({}); // no INNGEST_DEV, no INNGEST_SIGNING_KEY
  assert.strictEqual(result, false, "prod without signing key must fail closed");
});

test("inngestServeAllowed rejects a whitespace-only signing key — shared predicate", () => {
  const { inngestServeAllowed } = require("../server.js");
  assert.strictEqual(inngestServeAllowed({ INNGEST_SIGNING_KEY: " \t\n" }), false);
});

test("inngestServeAllowed returns false when INNGEST_DEV is not '1' and key is missing — FIND-005", () => {
  const { inngestServeAllowed } = require("../server.js");
  const result = inngestServeAllowed({ INNGEST_DEV: "0" });
  assert.strictEqual(result, false, "INNGEST_DEV=0 is not dev mode; must fail closed");
});

test("inngestServeAllowed returns true in prod when signing key is set — FIND-005", () => {
  const { inngestServeAllowed } = require("../server.js");
  const result = inngestServeAllowed({ INNGEST_SIGNING_KEY: "signkey-xyz" });
  assert.strictEqual(result, true, "prod with signing key must allow serving");
});
