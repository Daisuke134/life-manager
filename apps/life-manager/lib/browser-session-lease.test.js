"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createMemoryBrowserSessionLeaseStore,
  createBrowserSessionLeaseCoordinator,
} = require("./browser-session-lease.js");

test("shared browser lease admits one owner and rejects a second owner", async () => {
  const store = createMemoryBrowserSessionLeaseStore();
  const lease = createBrowserSessionLeaseCoordinator(store, {
    now: () => 1_800_000_000_000,
    ttlMs: 600_000,
    releaseProviderSession: async () => true,
  });

  const first = await lease.acquire({ tenantId: "tenant-a", ownerId: "job-a" });
  await lease.attach({ ...first, sessionId: "provider-a" });

  await assert.rejects(
    lease.acquire({ tenantId: "tenant-a", ownerId: "job-b" }),
    /Browser session lease unavailable/i,
  );
  assert.equal(await lease.isOwner({ ...first, sessionId: "provider-a" }), true);
});

test("stale browser lease releases its exact provider session once before takeover", async () => {
  let now = 1_800_000_000_000;
  const releases = [];
  const store = createMemoryBrowserSessionLeaseStore();
  const lease = createBrowserSessionLeaseCoordinator(store, {
    now: () => now,
    ttlMs: 600_000,
    async releaseProviderSession(sessionId) {
      releases.push(sessionId);
      return true;
    },
  });
  const first = await lease.acquire({ tenantId: "tenant-a", ownerId: "job-a" });
  await lease.attach({ ...first, sessionId: "provider-stale" });

  now += 600_001;
  const second = await lease.acquire({ tenantId: "tenant-a", ownerId: "job-b" });
  await lease.attach({ ...second, sessionId: "provider-fresh" });

  assert.deepEqual(releases, ["provider-stale"]);
  assert.equal(await lease.isOwner({ ...first, sessionId: "provider-stale" }), false);
  assert.equal(await lease.isOwner({ ...second, sessionId: "provider-fresh" }), true);
  assert.equal(await lease.reapExpired(), 0);
});

test("failed stale provider cleanup stays fail-closed", async () => {
  let now = 1_800_000_000_000;
  const store = createMemoryBrowserSessionLeaseStore();
  const lease = createBrowserSessionLeaseCoordinator(store, {
    now: () => now,
    ttlMs: 600_000,
    releaseProviderSession: async () => false,
  });
  const first = await lease.acquire({ tenantId: "tenant-a", ownerId: "job-a" });
  await lease.attach({ ...first, sessionId: "provider-stale" });
  now += 600_001;

  await assert.rejects(
    lease.acquire({ tenantId: "tenant-a", ownerId: "job-b" }),
    /stale provider session release failed/i,
  );
  await assert.rejects(
    lease.acquire({ tenantId: "tenant-a", ownerId: "job-b" }),
    /Browser session lease unavailable/i,
  );
});
