// In-process calendar read cache for the 60-second scheduler tick. This cache is intentionally
// non-persistent: a Railway restart only causes the next read to fetch from the inner transport.
"use strict";

const DEFAULT_TTL_MS = 5 * 60_000;

function configuredTtlMs(explicitTtlMs) {
  const candidate = explicitTtlMs == null ? Number(process.env.LM_CAL_CACHE_TTL_MS) : Number(explicitTtlMs);
  return Number.isFinite(candidate) && candidate >= 0 ? candidate : DEFAULT_TTL_MS;
}

// The key's resolution IS the TTL — one number decides both, deliberately (spec §3.2). It used to
// bucket by a hardcoded minute while the TTL was five, and callers derive timeMin/timeMax from
// `now` (lib/events.js:37), so every 60-second scheduler tick minted a key the TTL's own answer
// could never be found under: a cache that structurally never hit. Two knobs will always drift back
// into that bug, so there is no separate bucket-width setting and there must never be one.
//
// widthMs <= 0 (TTL of 0 = "no caching", which configuredTtlMs accepts on purpose) means NO
// bucketing: the exact instant is the key. That is the honest reading of a zero-width bucket, and
// it avoids both the divide-by-zero (Infinity/NaN) and the opposite failure of collapsing every
// window into one key — a key that, with caching off, would be a lie waiting to be served.
function timeBucket(value, widthMs) {
  const epochMs = Date.parse(value);
  if (!Number.isFinite(epochMs)) return String(value == null ? "" : value); // unparseable → raw
  return widthMs > 0 ? Math.floor(epochMs / widthMs) : epochMs;
}

function cacheKey(uid, { timeMin, timeMax } = {}, ttlMs) {
  // Same resolver as makeCachedCalendar, so a standalone call and the wrapper agree by construction.
  const widthMs = configuredTtlMs(ttlMs);
  return [uid, timeBucket(timeMin, widthMs), timeBucket(timeMax, widthMs)].join("|");
}

function forCaller(outcome, input) {
  if (outcome.ok) return outcome.items;
  if (input.strict === true) throw outcome.error;
  return [];
}

function makeCachedCalendar(inner, opts = {}) {
  const ttlMs = configuredTtlMs(opts.ttlMs);
  const now = opts.now || Date.now;
  const entries = new Map();

  function invalidateUid(uid) {
    for (const [key, entry] of entries) {
      if (entry.uid === uid) entries.delete(key);
    }
  }

  return {
    ...inner,
    async listEventsRaw(uid, input = {}) {
      // ttlMs=0 is "no caching", so store nothing at all. Without this the entries Map would take a
      // row per call that no later call can ever read (a zero TTL expires instantly) and nothing
      // evicts — a slow leak in the one mode whose whole point is to keep no state.
      if (ttlMs <= 0) return inner.listEventsRaw(uid, input);

      // The SAME resolved ttlMs that decides expiry below also sets the key's width — one number.
      const key = cacheKey(uid, input, ttlMs);
      const timestamp = now();
      const hit = entries.get(key);
      if (hit && timestamp - hit.fetchedAt < ttlMs) return forCaller(await hit.promise, input);

      const promise = Promise.resolve()
        .then(() => inner.listEventsRaw(uid, { ...input, strict: true }))
        .then(
          (items) => ({ ok: true, items }),
          (error) => ({ ok: false, error }),
        );
      const entry = { uid, fetchedAt: timestamp, promise };
      entries.set(key, entry);
      return forCaller(await promise, input);
    },
    async createEvent(uid, input) {
      const result = await inner.createEvent(uid, input);
      invalidateUid(uid);
      return result;
    },
    async patchEvent(uid, input) {
      const result = await inner.patchEvent(uid, input);
      invalidateUid(uid);
      return result;
    },
  };
}

module.exports = { makeCachedCalendar, cacheKey, DEFAULT_TTL_MS };
