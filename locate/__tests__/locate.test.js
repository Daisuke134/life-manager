// locate.test.js — unit tests for the pure cadence + motion cores of life/locate.
//   node --test skills/life/locate/__tests__/locate.test.js
//
// Proves: (1) the 15/14/13 + 5-EMERGENCY schedule cadence, and
//         (2) the MOVING stop-condition for the keep-calling live-location loop.

const { test } = require("node:test");
const assert = require("node:assert");

const {
  haversineM,
  hasMoved,
  scheduleDueCalls,
  schedulePlan,
  runLiveLocationLoop,
  runScheduleLoop,
} = require("../locate");

// ── haversineM ────────────────────────────────────────────────────────────────

test("haversineM ~0 for identical points", () => {
  assert.ok(haversineM(35.68, 139.76, 35.68, 139.76) < 0.001);
});

test("haversineM ~111km per degree of latitude", () => {
  const d = haversineM(35.0, 139.0, 36.0, 139.0);
  assert.ok(d > 110000 && d < 112000, `got ${d}`);
});

// ── hasMoved (the ONLY stop condition for live-location calling) ───────────────

test("hasMoved=false when displacement below threshold (still home)", () => {
  const origin = { lat: 35.68000, lon: 139.76000 };
  const fresh = { lat: 35.68050, lon: 139.76050 }; // ~70m
  assert.equal(hasMoved(origin, fresh, 300), false);
});

test("hasMoved=true when displacement exceeds threshold (actually moving)", () => {
  const origin = { lat: 35.68000, lon: 139.76000 };
  const fresh = { lat: 35.68500, lon: 139.76500 }; // ~700m
  assert.equal(hasMoved(origin, fresh, 300), true);
});

test("hasMoved=false on missing/invalid fixes (never a false stop)", () => {
  assert.equal(hasMoved(null, { lat: 1, lon: 1 }, 300), false);
  assert.equal(hasMoved({ lat: 1, lon: 1 }, null, 300), false);
  assert.equal(hasMoved({ lat: "x", lon: 1 }, { lat: 1, lon: 1 }, 300), false);
});

// ── scheduleDueCalls (15 / 14 / 13 before + 5-min EMERGENCY) ───────────────────

const START = Date.UTC(2026, 5, 16, 9, 0, 0); // event starts 09:00Z
const M = 60_000;
const TICK = 30_000;

test("call is due at T-15, T-14, T-13 and T-5 (EMERGENCY)", () => {
  for (const off of [15, 14, 13, 5]) {
    const at = START - off * M;
    const due = scheduleDueCalls({ nowMs: at, eventStartMs: START, already: [], tickMs: TICK });
    assert.equal(due.length, 1, `offset ${off} should fire`);
    assert.equal(due[0].offsetMin, off);
    assert.equal(due[0].emergency, off === 5, `offset ${off} emergency flag`);
  }
});

test("T-5 is flagged emergency, T-15/14/13 are not", () => {
  const five = scheduleDueCalls({ nowMs: START - 5 * M, eventStartMs: START, already: [], tickMs: TICK });
  assert.equal(five[0].emergency, true);
  const fifteen = scheduleDueCalls({ nowMs: START - 15 * M, eventStartMs: START, already: [], tickMs: TICK });
  assert.equal(fifteen[0].emergency, false);
});

test("no call is due at T-20 (before cadence) or T-9 (between 13 and 5)", () => {
  assert.equal(scheduleDueCalls({ nowMs: START - 20 * M, eventStartMs: START, already: [], tickMs: TICK }).length, 0);
  assert.equal(scheduleDueCalls({ nowMs: START - 9 * M, eventStartMs: START, already: [], tickMs: TICK }).length, 0);
});

test("already-fired offsets are not re-dialed (each slot fires once)", () => {
  const at = START - 15 * M;
  const due = scheduleDueCalls({ nowMs: at, eventStartMs: START, already: [15], tickMs: TICK });
  assert.equal(due.length, 0);
});

test("schedulePlan yields exactly 4 fires ordered 15,14,13,5 with one emergency", () => {
  const plan = schedulePlan(START);
  assert.equal(plan.length, 4);
  assert.deepEqual(plan.map((p) => p.offsetMin), [15, 14, 13, 5]);
  assert.equal(plan.filter((p) => p.emergency).length, 1);
  assert.equal(plan[3].emergency, true); // last fire = 5-min emergency
});

// ── runScheduleLoop (no live location): fires all four, EMERGENCY included ──────

test("runScheduleLoop fires 15/14/13 + 5-EMERGENCY exactly once each", async () => {
  // Drive a virtual clock from T-16min to past the event; tick = 1min.
  let clock = START - 16 * M;
  const tickMs = M;
  const calls = [];
  const r = await runScheduleLoop({
    dryRun: true,
    eventStartMs: START,
    tickMs,
    now: () => clock,
    dial: ({ reason }) => calls.push(reason),
    sleep: async () => { clock += tickMs; },
  });
  assert.deepEqual(r.fired, [15, 14, 13, 5]);
  assert.equal(calls.length, 4);
  assert.equal(calls.filter((c) => c.includes("EMERGENCY")).length, 1);
  assert.ok(calls.some((c) => c.includes("T-5min EMERGENCY")));
});

// ── runLiveLocationLoop: keeps calling until MOVED, ignoring pickup ─────────────

test("live loop KEEPS calling while stationary, stops only when moved", async () => {
  const origin = { lat: 35.680, lon: 139.760 };
  // Stay put for 3 polls, then jump ~700m on the 4th.
  const seq = [
    { lat: 35.680, lon: 139.760 },  // origin read
    { lat: 35.680, lon: 139.760 },  // still
    { lat: 35.6805, lon: 139.7605 },// ~70m — still NOT moving
    { lat: 35.680, lon: 139.760 },  // still
    { lat: 35.6850, lon: 139.7650 },// ~700m — MOVED
  ];
  let i = 0;
  const calls = [];
  const r = await runLiveLocationLoop({
    dryRun: true,
    thresholdM: 300,
    maxAttempts: 30,
    getLocation: () => seq[Math.min(i++, seq.length - 1)],
    dial: ({ reason }) => calls.push(reason),
    sleep: async () => {},
  });
  assert.equal(r.stopped, "moved");
  assert.ok(calls.length >= 2, `kept calling while stationary, got ${calls.length}`);
});

test("live loop ignores a PICKUP — pickup never stops it, only motion does", async () => {
  // dial() always 'succeeds' (pickup), yet the user never moves → loop runs to max.
  const fixed = { lat: 35.680, lon: 139.760 };
  let calls = 0;
  const r = await runLiveLocationLoop({
    dryRun: true,
    thresholdM: 300,
    maxAttempts: 4,
    getLocation: () => fixed,            // never moves
    dial: () => { calls++; return 0; },  // 0 = call answered/success
    sleep: async () => {},
  });
  assert.equal(r.stopped, "max-attempts");
  assert.equal(calls, 4, "answered calls must NOT stop the loop");
});

test("live loop no-ops when there is no location fix", async () => {
  const r = await runLiveLocationLoop({
    dryRun: true,
    getLocation: () => null,
    dial: () => assert.fail("must not dial without a fix"),
    sleep: async () => {},
  });
  assert.equal(r.stopped, "no-location");
  assert.equal(r.attempts, 0);
});
