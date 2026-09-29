"use strict";
// HARD-4 per-tenant isolation — a throw while processing ONE tenant must NOT prevent the others from being
// processed in the same in-process tick (matches the Inngest per-user isolation used in production).
// Run: node --test test/tenant-isolation.test.js
const { test } = require("node:test");
const assert = require("node:assert");
const { forEachUserSafe, tick, travelTick, askTickAll } = require("../scheduler.js");
const { createCloudRuntimeDispatcher } = require("../lib/cloud-runtime-dispatcher.js");

test("forEachUserSafe: a throwing tenant does NOT stop the others", async () => {
  const processed = [];
  await forEachUserSafe(
    [{ uid: "aaaaaaaaaaaa" }, { uid: "bbbbbbbbbbbb" }, { uid: "cccccccccccc" }],
    "test",
    (u) => { if (u.uid.startsWith("b")) throw new Error("boom"); processed.push(u.uid); },
  );
  assert.deepStrictEqual(processed, ["aaaaaaaaaaaa", "cccccccccccc"], "a and c processed despite b throwing");
});

test("forEachUserSafe: an async rejection for one tenant is contained too", async () => {
  const processed = [];
  await forEachUserSafe(
    [{ uid: "u1" }, { uid: "u2" }, { uid: "u3" }],
    "test",
    async (u) => { if (u.uid === "u2") return Promise.reject(new Error("async boom")); processed.push(u.uid); },
  );
  assert.deepStrictEqual(processed, ["u1", "u3"]);
});

test("forEachUserSafe: all-ok processes every tenant in order", async () => {
  const processed = [];
  await forEachUserSafe([{ uid: "x" }, { uid: "y" }], "test", (u) => { processed.push(u.uid); });
  assert.deepStrictEqual(processed, ["x", "y"]);
});

test("forEachUserSafe: empty list is a no-op (no throw)", async () => {
  await forEachUserSafe([], "test", () => { throw new Error("should not be called"); });
  await forEachUserSafe(null, "test", () => { throw new Error("should not be called"); });
});

test("forEachUserSafe: a malformed user row (no uid) is contained, others continue", async () => {
  const processed = [];
  await forEachUserSafe([{ uid: "ok1" }, null, { uid: "ok2" }], "test",
    (u) => { processed.push(u.uid); }); // null → fn throws on u.uid → contained
  assert.deepStrictEqual(processed, ["ok1", "ok2"]);
});

// FIND-001: prove the PUBLIC loops actually route through isolation (not just the helper) — a future revert
// to a raw `for...await XUserOnce(u)` in any loop would fail THESE tests, not pass silently.
test("FIND-001: tick() isolates a throwing tenant (others still processed)", async () => {
  const processed = [];
  await tick({ listUsers: async () => [{ uid: "tA" }, { uid: "tB" }, { uid: "tC" }], now: 0,
    wake: (u) => { if (u.uid === "tB") throw new Error("boom"); processed.push(u.uid); } });
  assert.deepStrictEqual(processed, ["tA", "tC"]);
});
test("FIND-001: travelTick() isolates a throwing tenant", async () => {
  process.env.COMPOSIO_API_KEY = "x"; process.env.GOOGLE_API_KEY = "y";
  const processed = [];
  await travelTick({ listUsers: async () => [{ uid: "a" }, { uid: "b" }],
    travel: (u) => { if (u.uid === "a") throw new Error("boom"); processed.push(u.uid); } });
  assert.deepStrictEqual(processed, ["b"]);
});
test("FIND-001: askTickAll() isolates a throwing tenant", async () => {
  process.env.COMPOSIO_API_KEY = "x"; process.env.GEMINI_API_KEY = "y"; process.env.SUPABASE_URL = "http://x";
  const processed = [];
  await askTickAll({ listUsers: async () => [{ uid: "a" }, { uid: "b" }],
    ask: (u) => { if (u.uid === "a") throw new Error("boom"); processed.push(u.uid); } });
  assert.deepStrictEqual(processed, ["b"]);
});

// FIND-002: a HANG (never-resolving) in one tenant is abandoned after the per-user timeout; others proceed.
test("FIND-002: a hanging tenant is abandoned after the timeout, others still processed", async () => {
  const processed = [];
  await forEachUserSafe([{ uid: "hang" }, { uid: "ok" }], "test",
    (u) => (u.uid === "hang" ? new Promise(() => {}) : Promise.resolve(processed.push(u.uid))),
    50);
  assert.deepStrictEqual(processed, ["ok"], "hung tenant abandoned after 50ms, ok processed");
});

test("cloud dispatch isolates a forged tenant while another tenant still invokes exactly once", async () => {
  const sha = "a".repeat(40);
  const invokes = [];
  const make = (tenantId, ref) => createCloudRuntimeDispatcher({
    releaseSha: sha, runtimeArn: "arn:runtime", requestedCostUsdMicros: 1,
    async readTenant() { return { tenant_id: tenantId, release_sha: sha, status: "active", plan_version: "free-v1" }; },
    async recoverExpired() { return {}; },
    async readJob() { return { tenant_id: tenantId, job_id: "job", status: "queued", attempt: 1, wake_id: "wake", input_refs: { task_ref: ref } }; },
    async readBudget() { return { settledCostUsdMicros: 0, reservedCostUsdMicros: 0, activationCreditRemainingUsdMicros: 1_000_000 }; },
    decideAdmission() { return { decision: "allow" }; },
    async acquireLease() { return { acquired: true }; },
    runtimeClient: { async invoke() { invokes.push(tenantId); return { disposition: "completed" }; } },
  });
  const results = await Promise.allSettled([
    make("tenant-a", "lm-resource://state/tenant-b/forged").dispatch({ tenant_id: "tenant-a", job_id: "job" }),
    make("tenant-c", "lm-resource://state/tenant-c/valid").dispatch({ tenant_id: "tenant-c", job_id: "job" }),
  ]);
  assert.equal(results[0].status, "rejected");
  assert.equal(results[1].status, "fulfilled");
  assert.deepStrictEqual(invokes, ["tenant-c"]);
});
