// wake-filter.test.js — #69 importance filter (travel-only default) + leave-time anchor (never-late).
// Run: node --test apps/life-call/lib/wake-filter.test.js
"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { isHelperBlock, shouldWake, departureMs, resolveDeparture, originFor } = require("./wake-filter.js");

const HOME = "新宿区南元町15-27";
const at = (h) => Date.parse(`2026-06-21T${String(h).padStart(2, "0")}:00:00+09:00`);

// ── isHelperBlock ────────────────────────────────────────────────────────────────────────────────
test("isHelperBlock: our own blocks are not commitments", () => {
  assert.equal(isHelperBlock("[Travel] 🚆 A→B"), true);
  assert.equal(isHelperBlock("🚆 移動 A→B"), true);
  assert.equal(isHelperBlock("[PENDING] ask"), true);
  assert.equal(isHelperBlock("[APPLIED] x"), true);
  assert.equal(isHelperBlock("渋谷で打合せ"), false);
});

// ── shouldWake: all timed events by default; explicit travel-only remains available ────────────────
test("travel-only: real venue ≠ home → WAKE", () => {
  assert.equal(shouldWake({ summary: "打合せ", location: "渋谷ヒカリエ", startMs: at(14) }, HOME, "travel-only"), true);
});
test("travel-only: at-home event (location == home) → skip", () => {
  assert.equal(shouldWake({ summary: "🧘 Meditation", location: HOME, startMs: at(6) }, HOME, "travel-only"), false);
});
test("travel-only: home with spacing diff → still skip", () => {
  assert.equal(shouldWake({ summary: "😴 Sleep", location: " 新宿区南元町15-27 ", startMs: at(23) }, HOME, "travel-only"), false);
});
test("travel-only: no location (routine/phone task) → skip", () => {
  assert.equal(shouldWake({ summary: "call mom", location: "", startMs: at(10) }, HOME, "travel-only"), false);
});
test("travel-only: helper block → skip even if it has a location", () => {
  assert.equal(shouldWake({ summary: "[Travel] 🚆 A→B", location: "somewhere", startMs: at(10) }, HOME, "travel-only"), false);
});
test("travel-only: home unknown → cannot tell → skip (let ask-loop resolve home)", () => {
  assert.equal(shouldWake({ summary: "打合せ", location: "渋谷", startMs: at(10) }, "", "travel-only"), false);
});

// ── shouldWake: all-events (opt-in) ────────────────────────────────────────────────────────────────
test("all-events: routine at home → WAKE (user opted into everything)", () => {
  assert.equal(shouldWake({ summary: "🧘 Meditation", location: HOME, startMs: at(6) }, HOME, "all-events"), true);
});
test("all-events: still never wakes for a helper block", () => {
  assert.equal(shouldWake({ summary: "[Travel] 🚆 A→B", location: "x", startMs: at(6) }, HOME, "all-events"), false);
});
test("an opted-in phone user receives timed events when the policy is omitted or unknown", () => {
  assert.equal(shouldWake({ summary: "🧘", location: HOME, startMs: at(6) }, HOME), true);
  assert.equal(shouldWake({ summary: "🧘", location: HOME, startMs: at(6) }, HOME, "garbage"), true);
});

// ── departureMs: leave-time anchor ─────────────────────────────────────────────────────────────────
test("departureMs: a [Travel] block ending at event start → its START is the departure", () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const travel = { summary: "[Travel] 🚆 home→渋谷", startMs: at(13), endMs: at(14) }; // 13:00→14:00
  assert.equal(departureMs(ev, [travel, ev]), at(13));
});
test("departureMs: no travel block → fall back to event start", () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  assert.equal(departureMs(ev, [ev]), at(14));
});
test("departureMs: a [Travel] block NOT ending at event start is ignored", () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const travel = { summary: "[Travel] 🚆 x→y", startMs: at(11), endMs: at(12) }; // unrelated, ends 12:00
  assert.equal(departureMs(ev, [travel, ev]), at(14));
});
test("departureMs: non-helper event ending at start is NOT treated as travel", () => {
  const ev = { summary: "打合せ2", location: "渋谷", startMs: at(14) };
  const prev = { summary: "打合せ1", location: "新宿", startMs: at(13), endMs: at(14) }; // real back-to-back
  assert.equal(departureMs(ev, [prev, ev]), at(14)); // only [Travel] helper blocks set departure
});

// ── departureMs tolerance window (travel.js caps duration at 59min → endMs can be ~1min before start) ──
test("departureMs: block ending 1min BEFORE start (59min cap) still matches", () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const block = { summary: "[Travel] 🚆", startMs: at(13), endMs: at(14) - 60000 }; // ends 13:59
  assert.equal(departureMs(ev, [block, ev]), at(13));
});
test("departureMs: block ending 30s AFTER start (echo drift) still matches", () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const block = { summary: "[Travel] 🚆", startMs: at(13), endMs: at(14) + 30000 };
  assert.equal(departureMs(ev, [block, ev]), at(13));
});
test("departureMs: block ending 5min before start is OUTSIDE the window → ignored", () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const block = { summary: "[Travel] 🚆", startMs: at(13), endMs: at(14) - 5 * 60000 };
  assert.equal(departureMs(ev, [block, ev]), at(14));
});
test("departureMs: with two candidate blocks, the LATEST-starting is chosen", () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const early = { summary: "[Travel] 🚆 stale", startMs: at(12), endMs: at(14) };
  const late = { summary: "[Travel] 🚆 fresh", startMs: at(13), endMs: at(14) };
  assert.equal(departureMs(ev, [early, late, ev]), at(13));
});

// ── resolveDeparture: never-late inline fallback when NO travel block exists yet ──────────────────────
test("resolveDeparture: travel block present → uses block start (no directions call)", async () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const block = { summary: "[Travel] 🚆", startMs: at(13), endMs: at(14) };
  let called = false;
  const dep = await resolveDeparture(ev, [block, ev], { home: HOME, directionsFn: async () => { called = true; return 99; } });
  assert.equal(dep, at(13));
  assert.equal(called, false); // block present → never hits the network
});
test("resolveDeparture: NO block → computes leave inline = start - (travel+buffer)", async () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const dep = await resolveDeparture(ev, [ev], { home: HOME, bufferMin: 5, directionsFn: async () => 30 });
  assert.equal(dep, at(14) - (30 + 5) * 60000); // 13:25 — woken before the real leave, not at event start
});
test("resolveDeparture: NO block + directions returns null → conservative event-start", async () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const dep = await resolveDeparture(ev, [ev], { home: HOME, directionsFn: async () => null });
  assert.equal(dep, at(14));
});
test("resolveDeparture: NO block + no directionsFn/home → event-start (no crash)", async () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  assert.equal(await resolveDeparture(ev, [ev], {}), at(14));
  assert.equal(await resolveDeparture(ev, [ev], { home: HOME }), at(14));
});
test("resolveDeparture: directionsFn throws → event-start (never crash the tick)", async () => {
  const ev = { summary: "打合せ", location: "渋谷", startMs: at(14) };
  const dep = await resolveDeparture(ev, [ev], { home: HOME, directionsFn: async () => { throw new Error("boom"); } });
  assert.equal(dep, at(14));
});

// ── inline fallback origin-awareness (the residual the gate flagged) ──────────────────────────────────
test("originFor: back-to-back prev venue (gap ≤90min) → prev location, not home", () => {
  const prev = { summary: "前の打合せ", location: "横浜", startMs: at(12), endMs: at(13) };
  const ev = { summary: "次", location: "渋谷", startMs: at(14) }; // 60min after prev
  assert.equal(originFor(ev, [prev, ev], HOME), "横浜");
});
test("originFor: prev far in time (>90min gap) → home", () => {
  const prev = { summary: "朝の用事", location: "横浜", startMs: at(8), endMs: at(9) };
  const ev = { summary: "次", location: "渋谷", startMs: at(14) }; // 5h after prev
  assert.equal(originFor(ev, [prev, ev], HOME), HOME);
});
test("originFor: a [Travel] helper is never used as origin", () => {
  const helper = { summary: "[Travel] 🚆", location: "どこか", startMs: at(13), endMs: at(13.5) };
  const ev = { summary: "次", location: "渋谷", startMs: at(14) };
  assert.equal(originFor(ev, [helper, ev], HOME), HOME);
});
test("resolveDeparture: back-to-back → inline uses PREV venue as origin (not home)", async () => {
  const prev = { summary: "前", location: "横浜", startMs: at(12), endMs: at(13) };
  const ev = { summary: "次", location: "渋谷", startMs: at(14) };
  let originSeen = null;
  const dep = await resolveDeparture(ev, [prev, ev], {
    home: HOME, bufferMin: 5, directionsFn: async (src) => { originSeen = src; return 40; },
  });
  assert.equal(originSeen, "横浜");                 // computed FROM the previous venue, not home
  assert.equal(dep, at(14) - (40 + 5) * 60000);     // leave 45min before = never-late from the far venue
});

test("resolveDeparture passes the stable event identity and go purpose to the shared route fact", async () => {
  const ev = { id: "gcal-event-1", summary: "次", location: "渋谷", startMs: at(14) };
  let options;
  await resolveDeparture(ev, [ev], {
    home: HOME,
    routeFn: async (...args) => { options = args[6]; return { durationSeconds: 600 }; },
    uid: "tenant", timezone: "Asia/Tokyo",
  });
  assert.equal(options.eventId, "gcal-event-1");
  assert.equal(options.purpose, "go");
});
