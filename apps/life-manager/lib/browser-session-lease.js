"use strict";

const crypto = require("node:crypto");

const ID = /^[a-z0-9][a-z0-9._:-]{0,199}$/i;

function validId(value, label) {
  const text = String(value || "");
  if (!ID.test(text)) throw new Error(`Browser session lease ${label} invalid`);
  return text;
}

function validLease(value) {
  if (
    !value || typeof value !== "object"
    || !ID.test(String(value.tenantId || ""))
    || !ID.test(String(value.ownerId || ""))
    || !/^[a-f0-9-]{16,64}$/i.test(String(value.leaseToken || ""))
  ) throw new Error("Browser session lease identity invalid");
  return value;
}

function createMemoryBrowserSessionLeaseStore() {
  const rows = new Map();
  return {
    async claim(input) {
      if (rows.has(input.tenantId)) return false;
      rows.set(input.tenantId, {
        tenant_id: input.tenantId,
        owner_id: input.ownerId,
        lease_token: input.leaseToken,
        session_id: null,
        expires_at_ms: input.expiresAtMs,
        state: "active",
        cleanup_token: null,
      });
      return true;
    },
    async attach(input) {
      const row = rows.get(input.tenantId);
      if (!row || row.state !== "active" || row.owner_id !== input.ownerId
        || row.lease_token !== input.leaseToken || row.session_id !== null) return false;
      row.session_id = input.sessionId;
      row.expires_at_ms = input.expiresAtMs;
      return true;
    },
    async takeExpired(input) {
      const row = [...rows.values()].find((candidate) =>
        candidate.state === "active" && candidate.expires_at_ms <= input.nowMs);
      if (!row) return null;
      row.state = "cleaning";
      row.cleanup_token = input.cleanupToken;
      return { ...row };
    },
    async finishCleanup(input) {
      const row = rows.get(input.tenantId);
      if (!row || row.state !== "cleaning" || row.lease_token !== input.leaseToken
        || row.cleanup_token !== input.cleanupToken) return false;
      rows.delete(input.tenantId);
      return true;
    },
    async release(input) {
      const row = rows.get(input.tenantId);
      if (!row || row.state !== "active" || row.owner_id !== input.ownerId
        || row.lease_token !== input.leaseToken
        || row.session_id !== (input.sessionId || null)) return false;
      rows.delete(input.tenantId);
      return true;
    },
    async isOwner(input) {
      const row = rows.get(input.tenantId);
      return Boolean(row && row.state === "active" && row.owner_id === input.ownerId
        && row.lease_token === input.leaseToken
        && row.session_id === (input.sessionId || null));
    },
    snapshot() { return [...rows.values()].map((row) => ({ ...row })); },
  };
}

function createBrowserSessionLeaseCoordinator(store, options = {}) {
  for (const method of ["claim", "attach", "takeExpired", "finishCleanup", "release", "isOwner"]) {
    if (!store || typeof store[method] !== "function") {
      throw new Error(`Browser session lease store missing ${method}`);
    }
  }
  const now = typeof options.now === "function" ? options.now : Date.now;
  const ttlMs = Number(options.ttlMs || 10 * 60 * 1000);
  if (!Number.isSafeInteger(ttlMs) || ttlMs < 30_000 || ttlMs > 60 * 60 * 1000) {
    throw new Error("Browser session lease TTL invalid");
  }
  if (typeof options.releaseProviderSession !== "function") {
    throw new Error("Browser session lease provider release unavailable");
  }
  const token = typeof options.token === "function" ? options.token : crypto.randomUUID;

  const coordinator = {
    async reapExpired(limit = 16) {
      let released = 0;
      while (released < limit) {
        const cleanupToken = token();
        const stale = await store.takeExpired({ nowMs: now(), cleanupToken });
        if (!stale) break;
        if (stale.session_id) {
          const providerReleased = await options.releaseProviderSession(stale.session_id);
          if (providerReleased !== true) {
            throw new Error("Browser stale provider session release failed");
          }
        }
        const cleared = await store.finishCleanup({
          tenantId: stale.tenant_id,
          leaseToken: stale.lease_token,
          cleanupToken,
        });
        if (!cleared) throw new Error("Browser stale session lease cleanup lost ownership");
        released += 1;
      }
      return released;
    },
    async acquire(input = {}) {
      const tenantId = validId(input.tenantId, "tenant");
      const ownerId = validId(input.ownerId, "owner");
      await coordinator.reapExpired();
      const leaseToken = token();
      const expiresAtMs = now() + ttlMs;
      const acquired = await store.claim({ tenantId, ownerId, leaseToken, expiresAtMs });
      if (!acquired) throw new Error("Browser session lease unavailable");
      return Object.freeze({ tenantId, ownerId, leaseToken, expiresAtMs });
    },
    async attach(input = {}) {
      const lease = validLease(input);
      const sessionId = validId(input.sessionId, "session");
      const attached = await store.attach({
        ...lease,
        sessionId,
        expiresAtMs: now() + ttlMs,
      });
      if (!attached) throw new Error("Browser session lease attach lost ownership");
      return Object.freeze({ ...lease, sessionId });
    },
    async release(input = {}) {
      const lease = validLease(input);
      return store.release({ ...lease, sessionId: input.sessionId || null });
    },
    async isOwner(input = {}) {
      const lease = validLease(input);
      return store.isOwner({ ...lease, sessionId: input.sessionId || null });
    },
  };
  return Object.freeze(coordinator);
}

module.exports = {
  createMemoryBrowserSessionLeaseStore,
  createBrowserSessionLeaseCoordinator,
};
