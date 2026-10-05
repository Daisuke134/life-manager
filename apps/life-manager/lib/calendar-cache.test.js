"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");

const { makeCachedCalendar, cacheKey, DEFAULT_TTL_MS } = require("./calendar-cache.js");

const WINDOW = {
  timeMin: "2026-07-18T09:00:20.000Z",
  timeMax: "2026-07-18T10:00:40.000Z",
  maxResults: 50,
};

function fakeCalendar() {
  const calls = { list: 0, create: 0, patch: 0 };
  const inner = {
    kind: "fake",
    ready: () => true,
    async listEventsRaw(uid, input) {
      calls.list += 1;
      return [{ uid, input, call: calls.list }];
    },
    async createEvent(uid, input) {
      calls.create += 1;
      return { successful: true, uid, input };
    },
    async patchEvent(uid, input) {
      calls.patch += 1;
      return { successful: true, uid, input };
    },
  };
  return { inner, calls };
}

// ── The bug this file exists to prevent ─────────────────────────────────────────────────────────
// The 60-second scheduler tick derives timeMin/timeMax from `now` (lib/events.js:37). While the key
// bucketed by MINUTE, every tick minted a fresh key, so a 5-minute TTL could never be reached and
// this cache never hit once in production (spec §3.2: 20,488 composio_call in 2026-07, over the
// DEGRADE_AT budget). The key's resolution must equal the TTL, so consecutive ticks share a key.
function isoZ(ms) {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
}

// Exactly what fetchUpcomingEvents builds for a given tick: an 18-hour horizon anchored on `now`.
function tickWindow(nowMs, horizonH = 18) {
  return { timeMin: isoZ(nowMs), timeMax: isoZ(nowMs + horizonH * 3600 * 1000), maxResults: 50 };
}

const TICK_0 = Date.parse("2026-08-01T09:00:20.000Z");

test("★ two scheduler ticks 60s apart hit the transport ONCE, not twice", async () => {
  const { inner, calls } = fakeCalendar();
  let now = TICK_0;
  const calendar = makeCachedCalendar(inner, { now: () => now, ttlMs: DEFAULT_TTL_MS });

  await calendar.listEventsRaw("u1", tickWindow(now));
  now += 60_000;
  await calendar.listEventsRaw("u1", tickWindow(now));

  assert.equal(calls.list, 1, "the second tick must reuse the first tick's answer within the TTL");
});

test("★ five consecutive 60s ticks inside one 5-minute TTL hit the transport ONCE", async () => {
  const { inner, calls } = fakeCalendar();
  let now = TICK_0;
  const calendar = makeCachedCalendar(inner, { now: () => now, ttlMs: DEFAULT_TTL_MS });

  for (let i = 0; i < 5; i += 1) {
    await calendar.listEventsRaw("u1", tickWindow(now));
    now += 60_000;
  }

  assert.equal(calls.list, 1);
});

test("ticks further apart than the TTL do fetch again", async () => {
  const { inner, calls } = fakeCalendar();
  let now = TICK_0;
  const calendar = makeCachedCalendar(inner, { now: () => now, ttlMs: DEFAULT_TTL_MS });

  await calendar.listEventsRaw("u1", tickWindow(now));
  now += DEFAULT_TTL_MS + 60_000;
  await calendar.listEventsRaw("u1", tickWindow(now));

  assert.equal(calls.list, 2, "a stale-by-more-than-TTL window must be refetched");
});

test("different horizons at the same instant stay different cache entries", async () => {
  const { inner, calls } = fakeCalendar();
  const now = TICK_0;
  const calendar = makeCachedCalendar(inner, { now: () => now, ttlMs: DEFAULT_TTL_MS });

  await calendar.listEventsRaw("u1", tickWindow(now, 6));
  await calendar.listEventsRaw("u1", tickWindow(now, 18));

  assert.equal(calls.list, 2, "a 6h caller must never be served an 18h answer, or vice versa");
  assert.notEqual(cacheKey("u1", tickWindow(now, 6), DEFAULT_TTL_MS), cacheKey("u1", tickWindow(now, 18), DEFAULT_TTL_MS));
});

test("ttlMs=0 means no caching: every call reaches the transport", async () => {
  const { inner, calls } = fakeCalendar();
  let now = TICK_0;
  const calendar = makeCachedCalendar(inner, { now: () => now, ttlMs: 0 });

  await calendar.listEventsRaw("u1", tickWindow(now));
  await calendar.listEventsRaw("u1", tickWindow(now)); // same instant, same window
  now += 1_000;
  await calendar.listEventsRaw("u1", tickWindow(now));

  assert.equal(calls.list, 3);
});

test("ttlMs=0 keeps no state: concurrent identical calls are not deduped either", async () => {
  const { inner, calls } = fakeCalendar();
  const calendar = makeCachedCalendar(inner, { now: () => TICK_0, ttlMs: 0 });
  const window = tickWindow(TICK_0);

  // In-flight sharing IS a cache. With caching off, nothing may be retained between these two.
  await Promise.all([calendar.listEventsRaw("u1", window), calendar.listEventsRaw("u1", window)]);

  assert.equal(calls.list, 2);
});

test("ttlMs=0 buckets nothing: distinct instants keep distinct keys (no divide-by-zero collapse)", () => {
  const a = cacheKey("u1", tickWindow(TICK_0), 0);
  const b = cacheKey("u1", tickWindow(TICK_0 + 1_000), 0);
  const same = cacheKey("u1", tickWindow(TICK_0), 0);

  assert.equal(a, same);
  assert.notEqual(a, b);
  for (const key of [a, b]) {
    assert.ok(!/NaN|Infinity/.test(key), `ttl=0 key must not contain NaN/Infinity: ${key}`);
  }
});

test("an unparseable date falls back to its raw string instead of NaN", () => {
  const key = cacheKey("u1", { timeMin: "not-a-date", timeMax: undefined }, DEFAULT_TTL_MS);

  assert.equal(key, "u1|not-a-date|");
});

test("the key's bucket width follows the TTL it is given, with no second knob", () => {
  // Same pair of instants: 60s apart. A 5-minute TTL must collapse them; a 30-second TTL must not.
  const w1 = tickWindow(TICK_0);
  const w2 = tickWindow(TICK_0 + 60_000);

  assert.equal(cacheKey("u1", w1, 300_000), cacheKey("u1", w2, 300_000));
  assert.notEqual(cacheKey("u1", w1, 30_000), cacheKey("u1", w2, 30_000));
});

test("same uid and minute-rounded window is fetched once within TTL", async () => {
  const { inner, calls } = fakeCalendar();
  const calendar = makeCachedCalendar(inner, { now: () => 1_000, ttlMs: 300_000 });

  const first = await calendar.listEventsRaw("u1", WINDOW);
  const second = await calendar.listEventsRaw("u1", {
    ...WINDOW,
    timeMin: "2026-07-18T09:00:50.000Z",
    timeMax: "2026-07-18T10:00:59.000Z",
  });

  assert.equal(calls.list, 1);
  assert.strictEqual(second, first);
});

test("expired entry is fetched again", async () => {
  let now = 1_000;
  const { inner, calls } = fakeCalendar();
  const calendar = makeCachedCalendar(inner, { now: () => now, ttlMs: 300_000 });

  await calendar.listEventsRaw("u1", WINDOW);
  now += 300_000;
  await calendar.listEventsRaw("u1", WINDOW);

  assert.equal(calls.list, 2);
});

test("createEvent invalidates every cached window for that uid", async () => {
  const { inner, calls } = fakeCalendar();
  const calendar = makeCachedCalendar(inner, { now: () => 1_000 });

  await calendar.listEventsRaw("u1", WINDOW);
  await calendar.listEventsRaw("u1", {
    ...WINDOW,
    timeMin: "2026-07-18T12:00:00.000Z",
    timeMax: "2026-07-18T13:00:00.000Z",
  });
  await calendar.createEvent("u1", { summary: "new event" });
  await calendar.listEventsRaw("u1", WINDOW);

  assert.equal(calls.create, 1);
  assert.equal(calls.list, 3);
});

test("patchEvent invalidates that uid without invalidating another uid", async () => {
  const { inner, calls } = fakeCalendar();
  const calendar = makeCachedCalendar(inner, { now: () => 1_000 });

  await calendar.listEventsRaw("u1", WINDOW);
  await calendar.listEventsRaw("u2", WINDOW);
  await calendar.patchEvent("u1", { event_id: "e1", summary: "changed" });
  await calendar.listEventsRaw("u1", WINDOW);
  await calendar.listEventsRaw("u2", WINDOW);

  assert.equal(calls.patch, 1);
  assert.equal(calls.list, 3);
});

test("different uids use different cache keys", async () => {
  const { inner, calls } = fakeCalendar();
  const calendar = makeCachedCalendar(inner, { now: () => 1_000 });

  await calendar.listEventsRaw("u1", WINDOW);
  await calendar.listEventsRaw("u2", WINDOW);

  assert.equal(calls.list, 2);
});

test("an empty inner result remains an empty array", async () => {
  const inner = {
    async listEventsRaw() { return []; },
    async createEvent() { return { successful: true }; },
    async patchEvent() { return { successful: true }; },
  };
  const calendar = makeCachedCalendar(inner, { now: () => 1_000 });

  assert.deepEqual(await calendar.listEventsRaw("u1", WINDOW), []);
});

test("a cached failure stays strict after a non-strict caller first receives an empty array", async () => {
  const readError = new Error("calendar unavailable");
  const calls = [];
  const inner = {
    async listEventsRaw(_uid, input = {}) {
      calls.push(input);
      if (input.strict) throw readError;
      return [];
    },
  };
  const calendar = makeCachedCalendar(inner, { now: () => 1_000, ttlMs: 300_000 });

  assert.deepEqual(await calendar.listEventsRaw("u1", WINDOW), []);
  await assert.rejects(calendar.listEventsRaw("u1", { ...WINDOW, strict: true }), (error) => error === readError);
  assert.equal(calls.length, 1, "both callers share one underlying read");
  assert.equal(calls[0].strict, true, "cached reads ask the transport to preserve failures");
});

test("a cached failure maps to empty for a non-strict caller after a strict caller throws", async () => {
  const readError = new Error("calendar unavailable");
  const calls = [];
  const inner = {
    async listEventsRaw(_uid, input = {}) {
      calls.push(input);
      if (input.strict) throw readError;
      return [];
    },
  };
  const calendar = makeCachedCalendar(inner, { now: () => 1_000, ttlMs: 300_000 });

  await assert.rejects(calendar.listEventsRaw("u1", { ...WINDOW, strict: true }), (error) => error === readError);
  assert.deepEqual(await calendar.listEventsRaw("u1", WINDOW), []);
  assert.equal(calls.length, 1, "the failed outcome remains cached for the TTL");
});

test("concurrent mixed strict callers share one failed read but receive caller-specific results", async () => {
  const readError = new Error("calendar unavailable");
  const calls = [];
  let rejectRead;
  const pendingRead = new Promise((_, reject) => { rejectRead = reject; });
  const inner = {
    listEventsRaw(_uid, input = {}) {
      calls.push(input);
      return pendingRead;
    },
  };
  const calendar = makeCachedCalendar(inner, { now: () => 1_000, ttlMs: 300_000 });
  const nonStrict = calendar.listEventsRaw("u1", WINDOW).then(
    (items) => ({ ok: true, items }),
    (error) => ({ ok: false, error }),
  );
  const strict = calendar.listEventsRaw("u1", { ...WINDOW, strict: true }).then(
    (items) => ({ ok: true, items }),
    (error) => ({ ok: false, error }),
  );

  await new Promise(setImmediate);
  assert.equal(calls.length, 1, "concurrent callers share one in-flight transport read");
  assert.equal(calls[0].strict, true);
  rejectRead(readError);
  const [nonStrictResult, strictResult] = await Promise.all([nonStrict, strict]);

  assert.deepEqual(nonStrictResult, { ok: true, items: [] });
  assert.equal(strictResult.ok, false);
  assert.strictEqual(strictResult.error, readError);
  assert.equal(calls.length, 1);
});

test("getCalendar shares the cached wrapper unless LM_CAL_CACHE=off", () => {
  const beforeCache = process.env.LM_CAL_CACHE;
  const beforeTransport = process.env.LIFE_TRANSPORT;
  delete process.env.LIFE_TRANSPORT;
  delete process.env.LM_CAL_CACHE;
  try {
    const { getCalendar } = require("./transport/index.js");
    const first = getCalendar({ kind: "composio", apiKey: "calendar-cache-wiring-test" });
    const second = getCalendar({ kind: "composio", apiKey: "calendar-cache-wiring-test" });
    assert.strictEqual(second, first);

    process.env.LM_CAL_CACHE = "off";
    const rawFirst = getCalendar({ kind: "composio", apiKey: "calendar-cache-wiring-test" });
    const rawSecond = getCalendar({ kind: "composio", apiKey: "calendar-cache-wiring-test" });
    assert.notStrictEqual(rawSecond, rawFirst);
  } finally {
    if (beforeCache == null) delete process.env.LM_CAL_CACHE;
    else process.env.LM_CAL_CACHE = beforeCache;
    if (beforeTransport == null) delete process.env.LIFE_TRANSPORT;
    else process.env.LIFE_TRANSPORT = beforeTransport;
  }
});
