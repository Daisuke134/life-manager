"use strict";
// The 60s tick is NOT periodic: the same tick runs the late/mental/care/diet organs under a per-user
// timeout, and a redeploy restarts the process — so a tick can land minutes after a wake threshold.
// A window-bound gate ("fire only inside T-min ±~2min") lost that call FOREVER. These tests pin the
// catch-up contract instead: a passed threshold still rings, at most ONE dial per event per tick, the
// superseded coarser level is CLAIMED so it cannot ring late, and past LATE_CUTOFF_MIN nobody is rung
// at all (that territory belongs to the late-notice organ).
// Run: node --test test/wake-catchup.test.js
const { test } = require("node:test");
const assert = require("node:assert");

process.env.LM_CALL_SECRET = "unit_secret";
process.env.PUBLIC_WSS = "wss://life-call.invalid";

const { wakeUserOnce, wakeCallOnce, LATE_CUTOFF_MIN } = require("../scheduler.js");

const MINUTE = 60_000;
const EVENT_START_ISO = "2026-08-05T14:00:00+09:00";
const EVENT_START_MS = Date.parse(EVENT_START_ISO);
const TRAVEL_MIN = 35;
const DEPARTURE_MS = EVENT_START_MS; // legacy test name; wake calls now use the event start
const TEST_PHONE = "+99900000000";

const USER = {
  paid: true,
  uid: "catchup-user",
  name: "Catchup User",
  phone: TEST_PHONE,
  home_address: "東京都渋谷区",
  call_language: "ja",
  daily_automation_enabled: true,
  call_enabled: true,
  notifications_enabled: false, // silences the late/diet/precepts/relations legs — this file is wakes only
};

const EVENT = {
  id: "catchup-event",
  summary: "新宿で打ち合わせ",
  location: "新宿",
  startMs: EVENT_START_MS,
  startIso: EVENT_START_ISO,
  endMs: EVENT_START_MS + 60 * MINUTE,
};

// Deps are injected exactly the way test/daily-journey-contract.test.js injects them: the real
// wakeUserOnce runs, only its I/O edges are controlled.
function harness({ dial } = {}) {
  const held = new Set();
  const claimed = [];
  const dialed = [];
  const released = [];
  const missed = [];
  const deps = {
    recordDailyPoll: async () => true,
    fetchUpcomingEvents: async () => [{ ...EVENT }],
    mental: async () => null,
    care: async () => ({ status: "already_scanned" }),
    mapsKey: "catchup-maps-key",
    directionsMinutes: async () => TRAVEL_MIN,
    claimWake: async (_uid, key) => {
      claimed.push(key);
      if (held.has(key)) return false;
      held.add(key);
      return true;
    },
    placeCall: async ({ streamUrl }) => {
      const params = new URL(streamUrl, "https://life-manager.invalid").searchParams;
      dialed.push({ urgency: params.get("urgency"), level: params.get("wakeEventKey").split("|").at(-1) });
      return dial ? dial(dialed.length) : { ok: true, ccid: `catchup-call-${dialed.length}` };
    },
    releaseWake: async (_uid, key) => { released.push(key); held.delete(key); },
    recordWakeMiss: async (_uid, miss) => { missed.push(miss); return { ok: true }; },
    alertLowBalance: async () => {},
  };
  return { deps, held, claimed, dialed, released, missed };
}

test("a tick one minute after T-5 still places one call before the event", async () => {
  const h = harness();
  await wakeUserOnce(USER, DEPARTURE_MS - 4 * MINUTE, h.deps);
  assert.deepEqual(h.dialed, [{ urgency: "harsh", level: "5" }], "the missed threshold still rings, once");
});

test("an on-time sequence still rings T-10 first and T-5 on a later tick", async () => {
  const h = harness();
  await wakeUserOnce(USER, DEPARTURE_MS - 15 * MINUTE, h.deps);
  await wakeUserOnce(USER, DEPARTURE_MS - 10 * MINUTE, h.deps);
  await wakeUserOnce(USER, DEPARTURE_MS - 10 * MINUTE, h.deps); // a repeat tick must not re-ring
  await wakeUserOnce(USER, DEPARTURE_MS - 5 * MINUTE, h.deps);
  await wakeUserOnce(USER, DEPARTURE_MS - 5 * MINUTE, h.deps);
  assert.deepEqual(h.dialed, [
    { urgency: "firm", level: "10" },
    { urgency: "harsh", level: "5" },
  ], "two calls, in escalating order");
  assert.equal(h.held.size, 2, "exactly the two (event, level) claims are held");
});

test("each timed event rings at event T-10 and T-5 with separate paid-action identities", async () => {
  const h = harness();
  const actions = new Set();
  let routes = 0;
  h.deps.directionsMinutes = async () => { routes++; return TRAVEL_MIN; };
  h.deps.reserveManagedAction = async (_uid, key) => {
    if (actions.has(key)) return { allowed: false };
    actions.add(key);
    return { allowed: true, periodStart: "2026-08-01",
      reservationToken: "11111111-1111-4111-8111-111111111111" };
  };
  h.deps.releaseManagedAction = async () => ({ allowed: true });
  await wakeCallOnce(USER, EVENT_START_MS - 10 * MINUTE, h.deps);
  await wakeCallOnce(USER, EVENT_START_MS - 5 * MINUTE, h.deps);
  assert.deepEqual(h.dialed.map((call) => call.level), ["10", "5"]);
  assert.equal(actions.size, 2, "both reminders have independent allowance identities");
  assert.equal(routes, 0, "the phone schedule does not wait for a travel route");
});

test("a paid user receives a timed event call even without a location or wake policy", async () => {
  const h = harness();
  h.deps.fetchUpcomingEvents = async () => [{ ...EVENT, location: "" }];
  await wakeCallOnce(USER, EVENT_START_MS - 10 * MINUTE, h.deps);
  assert.deepEqual(h.dialed.map((call) => call.level), ["10"]);
});

test("two distinct events starting together keep separate call claims", async () => {
  const h = harness();
  h.deps.fetchUpcomingEvents = async () => [
    { ...EVENT, id: "first-event" },
    { ...EVENT, id: "second-event", summary: "別の予定" },
  ];
  await wakeCallOnce(USER, EVENT_START_MS - 10 * MINUTE, h.deps);
  assert.equal(h.dialed.length, 2);
  assert.equal(h.held.size, 2);
});

test("one tick with both levels due places ONE call and claims the coarser level without ringing", async () => {
  const h = harness();
  await wakeUserOnce(USER, DEPARTURE_MS - 4 * MINUTE, h.deps); // T-10 passed, T-5 due, same tick
  assert.deepEqual(h.dialed, [{ urgency: "harsh", level: "5" }], "only the most urgent level rings");
  assert.deepEqual([...h.held].map((k) => k.split("|").at(-1)).sort(), ["10", "5"],
    "the superseded T-10 is claimed so a later tick cannot resurrect it");
  assert.equal(h.missed.length, 1, "the missed T-10 is recorded rather than silently claimed");
  assert.equal(h.missed[0].reason, "missed_level");
  await wakeUserOnce(USER, DEPARTURE_MS - 3 * MINUTE, h.deps);
  assert.equal(h.dialed.length, 1, "the superseded level stays silent on every later tick");
});

test("an event after its start places no call at all", async () => {
  assert.equal(LATE_CUTOFF_MIN, 0, "the cutoff is the event start");
  const h = harness();
  await wakeUserOnce(USER, DEPARTURE_MS + 16 * MINUTE, h.deps);
  assert.deepEqual(h.dialed, [], "past the cutoff the late-notice organ owns this, not a wake call");
  assert.deepEqual(h.claimed, [], "and no claim is burned on the way out");
});

test("a dial failure releases its claim so the next tick retries", async () => {
  const h = harness({ dial: (n) => (n === 1 ? { ok: false, error: "balance too low" } : { ok: true, ccid: `retry-${n}` }) });
  await wakeUserOnce(USER, DEPARTURE_MS - 5 * MINUTE, h.deps);
  assert.deepEqual(h.released.map((k) => k.split("|").at(-1)), ["5"], "the failed level's claim is released");
  await wakeUserOnce(USER, DEPARTURE_MS - 4 * MINUTE, h.deps);
  assert.deepEqual(h.dialed, [
    { urgency: "harsh", level: "5" },
    { urgency: "harsh", level: "5" },
  ], "the next tick retries the same level");
});
