// travel-return.test.js — unit + integration tests for REQ-15: RETURN-trip travel block.
// Pure helper: returnDecision(ev, next, home) — geometry decision, no I/O.
// Integration: fillTravel with fake calendar + injected directionsMinutes — proves wiring (FIND-002).
// Idempotency: two fillTravel runs produce no duplicate return blocks (FIND-003).
// Run: node --test apps/life-call/lib/travel-return.test.js
"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { returnDecision, fillTravel, directionsMinutes } = require("./travel.js");

const HOME = "新宿区南元町15-27";
const VENUE = "渋谷ヒカリエ8F";
const VENUE2 = "東京駅八重洲口";

// Millisecond helper: build a timestamp at hour H (JST = UTC+9)
const ms = (h) => Date.parse(`2026-06-20T${String(h).padStart(2, "0")}:00:00+09:00`);

// ── CASE (a): last event of day — next is null → RETURN inserted ──────────────────────────────────
test("(a) last event of day (next=null) → return inserted, origin=venue", () => {
  const ev   = { summary: "Dentist", location: VENUE, startMs: ms(14), endMs: ms(15) };
  const d = returnDecision(ev, null, HOME);
  assert.equal(d.insert, true,   "should insert return block");
  assert.equal(d.origin, VENUE,  "return origin must be the event venue");
  assert.equal(d.reason, "return-needed");
});

// ── CASE (b): next event back-to-back (within 90min) at a real venue → NO return ─────────────────
test("(b) next event starts within 90min at a real venue → NO return (they travel venue→next-venue)", () => {
  const ev   = { summary: "Morning mtg", location: VENUE,  startMs: ms(9),  endMs: ms(10) };
  const next = { summary: "Lunch meet",  location: VENUE2, startMs: ms(11), endMs: ms(12) }; // 60min after ev.end
  const d = returnDecision(ev, next, HOME);
  assert.equal(d.insert, false, "back-to-back real-venue next → no return block");
  assert.ok(d.reason === "next-back-to-back-venue", `expected next-back-to-back-venue, got ${d.reason}`);
});

// ── CASE (c): next event >90min later → RETURN inserted (user goes home in between) ──────────────
test("(c) next event starts >90min later → return inserted", () => {
  const ev   = { summary: "Workshop", location: VENUE,  startMs: ms(9),  endMs: ms(10) };
  const next = { summary: "Dinner",   location: VENUE2, startMs: ms(13), endMs: ms(15) }; // 3h gap
  const d = returnDecision(ev, next, HOME);
  assert.equal(d.insert, true,  "3h gap → return block needed");
  assert.equal(d.origin, VENUE, "return origin is the workshop venue");
});

// ── CASE (d): venue === home (norm-compare) → no return ───────────────────────────────────────────
test("(d) event venue is home → no return (already there)", () => {
  const ev = { summary: "Remote work", location: HOME, startMs: ms(10), endMs: ms(11) };
  const d = returnDecision(ev, null, HOME);
  assert.equal(d.insert, false, "venue equals home → skip");
  assert.equal(d.reason, "same-location");
});

test("(d) venue equals home with spacing differences → no return", () => {
  const ev = { summary: "Nap", location: " 新宿区南元町15-27 ", startMs: ms(13), endMs: ms(14) };
  const d = returnDecision(ev, null, HOME);
  assert.equal(d.insert, false);
  assert.equal(d.reason, "same-location");
});

// ── CASE (e): online / no-location event → no return ─────────────────────────────────────────────
test("(e) event with no location → no return", () => {
  const ev = { summary: "Zoom call", location: "", startMs: ms(10), endMs: ms(11) };
  const d = returnDecision(ev, null, HOME);
  assert.equal(d.insert, false);
  assert.equal(d.reason, "no-location");
});

test("(e) event is a [Travel] helper block → no return", () => {
  const ev = { summary: "[Travel] 🚆 A→B", location: VENUE, startMs: ms(10), endMs: ms(11) };
  const d = returnDecision(ev, null, HOME);
  assert.equal(d.insert, false);
  assert.equal(d.reason, "travel-block");
});

// ── CASE (f): home is unknown/null/empty → no return ─────────────────────────────────────────────
test("(f) home is null → no return", () => {
  const ev = { summary: "Workshop", location: VENUE, startMs: ms(9), endMs: ms(10) };
  const d = returnDecision(ev, null, null);
  assert.equal(d.insert, false);
  assert.equal(d.reason, "no-home");
});

test("(f) home is empty string → no return", () => {
  const ev = { summary: "Workshop", location: VENUE, startMs: ms(9), endMs: ms(10) };
  const d = returnDecision(ev, null, "");
  assert.equal(d.insert, false);
  assert.equal(d.reason, "no-home");
});

// ── CASE (g): dedup — next is a [Travel] block immediately after ev.end → no second insert ───────
test("(g) dedup: next event is a return [Travel] block right after ev.end → no insert", () => {
  const ev   = { summary: "Dentist", location: VENUE, startMs: ms(14), endMs: ms(15) };
  // A [Travel] block starts at ev.end (return block already present)
  const next = { summary: "[Travel] 🚆 渋谷ヒカリエ8→新宿区南元", location: HOME, startMs: ms(15), endMs: ms(16) };
  const d = returnDecision(ev, next, HOME);
  assert.equal(d.insert, false, "return travel block already in slot → dedup");
  assert.equal(d.reason, "already-has-return-block");
});

// ── Boundary: next has no location → treated as no-venue → return inserted ───────────────────────
test("next event has no location (online/no-venue) → return inserted (next is not a real venue)", () => {
  const ev   = { summary: "Dentist", location: VENUE, startMs: ms(14), endMs: ms(15) };
  const next = { summary: "Zoom standup", location: "", startMs: ms(15), endMs: ms(16) }; // no venue
  const d = returnDecision(ev, next, HOME);
  assert.equal(d.insert, true, "next has no real venue → return to home");
});

// ── Boundary: next is exactly 90min after ev.end (edge of boundary) ───────────────────────────────
test("next starts exactly 90min after ev.end → NO return (≤90min → back-to-back)", () => {
  const ev   = { summary: "Dentist", location: VENUE,  startMs: ms(14), endMs: ms(15) };
  // ev ends at ms(15). Exactly 90min later = ms(15) + 90*60*1000
  const nextStart = ms(15) + 90 * 60 * 1000;
  const next = { summary: "Dinner", location: VENUE2, startMs: nextStart };
  const d = returnDecision(ev, next, HOME);
  assert.equal(d.insert, false, "exactly 90min → still back-to-back → no return");
});

test("next starts 91min after ev.end → return inserted (just past 90min boundary)", () => {
  const ev   = { summary: "Dentist", location: VENUE,  startMs: ms(14), endMs: ms(15) };
  const nextStart = ms(15) + 91 * 60 * 1000;
  const next = { summary: "Dinner", location: VENUE2, startMs: nextStart };
  const d = returnDecision(ev, next, HOME);
  assert.equal(d.insert, true, "91min gap → return needed");
});

// ── returnDecision must handle missing endMs gracefully ───────────────────────────────────────────
test("event with missing endMs → no return (cannot compute return start time)", () => {
  const ev = { summary: "Dentist", location: VENUE, startMs: ms(14) }; // no endMs
  const d = returnDecision(ev, null, HOME);
  assert.equal(d.insert, false);
  assert.equal(d.reason, "no-end-time");
});

// ══════════════════════════════════════════════════════════════════════════════════════════════════
// TIER-2 INTEGRATION TESTS (FIND-002) — prove fillTravel wires returnDecision + createTravelBlock
// ══════════════════════════════════════════════════════════════════════════════════════════════════
//
// Fake calendar factory: returns a calendar object that satisfies the contract used by fillTravel.
// listEventsRaw returns whatever eventRows we provide; createEvent records the call and returns
// { successful: true }.
//
function makeFakeCalendar(eventRows) {
  const created = [];
  return {
    _created: created,
    async listEventsRaw(_uid, _opts) { return eventRows; },
    async createEvent(_uid, payload) {
      created.push({ ...payload });
      return { successful: true };
    },
  };
}

// Build a raw calendar event row (what listEventsRaw returns before mapping).
function rawEv({ summary, location, startH, endH }) {
  const start = `2026-06-20T${String(startH).padStart(2, "0")}:00:00+09:00`;
  const end   = `2026-06-20T${String(endH).padStart(2, "0")}:00:00+09:00`;
  return { summary, location, start: { dateTime: start }, end: { dateTime: end } };
}

// Stub for directionsMinutes: always returns a fixed travel time so no network calls.
// We override the module-level function via the calendar injection + module re-require pattern.
// Instead, we inject a directionsMinutes stub by passing it through the options object with
// a custom key that fillTravel will use when provided (see integration shim below).
//
// Since fillTravel doesn't accept a directionsMinutes override directly, we use a thin wrapper
// approach: we re-require travel.js as a fresh module with the real directionsMinutes replaced.
// Node's module cache makes direct monkey-patching of the export the simplest approach here.
const travelModule = require("./travel.js");

// ── Integration (a): last event of day → return [Travel] block created at ev.endMs ──────────────
test("[INTEGRATION][FIND-002](a) last event of day → fillTravel creates a return [Travel] block starting at ev.endMs", async () => {
  // Single physical event, no subsequent event.
  const cal = makeFakeCalendar([
    rawEv({ summary: "Dentist", location: VENUE, startH: 14, endH: 15 }),
  ]);

  // Inject directionsMinutes stub: always returns 30 min so the block gets created.
  const origDirections = travelModule.directionsMinutes;
  // Monkey-patch for this test only (restored in finally).
  travelModule.__test_directionsMinutesFn = async () => 30;
  // We need fillTravel to use our stub. Because directionsMinutes is a module-level closure,
  // the cleanest approach without refactoring fillTravel's signature is to temporarily replace
  // the exported symbol and have fillTravel call it via the export object.
  // fillTravel calls directionsMinutes directly (not via exports), so we need a different path.
  // Use the `_directionsMinutes` injection pattern: pass a fake via the `calendar` shim
  // by wrapping fillTravel with a version that stubs the Directions API via the fake calendar.
  //
  // Since fillTravel calls the module-level directionsMinutes, we patch the module export
  // AND expose a way to override it. The simplest correct approach: temporarily replace
  // the function on the module object and then restore it. Note: this works because
  // Node's module system gives us a reference to the same object.
  //
  // The correct hook: travel.js calls `directionsMinutes` as a local binding (not exports.X),
  // so we cannot patch from outside. Instead, we expose a test seam via the `_forTest` option
  // that fillTravel reads when present. We add that seam: see fillTravel implementation.
  //
  // For this test, we use the real directionsMinutes with a fake mapsKey — it will return null
  // (network call fails in test env), causing skipped. Instead we need to provide the seam.
  //
  // APPROACH: Add a `_directionsMinutes` option to fillTravel (test seam, documented as
  // private). This is the idiomatic Node.js test injection pattern (dependency injection via
  // opts). The seam is already required: FIND-002 says "injected directionsMinutes".
  // We update fillTravel to accept this, then test it here.
  //
  // For now this test calls fillTravel with the real path, expecting skip (null directions).
  // The real integration test below uses the seam after we add it to fillTravel.
  void origDirections; // lint: used above for reference

  // Since we're adding the `_directionsMinutes` seam to fillTravel, call it here.
  const result = await fillTravel("uid1", {
    home: HOME,
    mapsKey: "fake-key",
    nowMs: Date.parse("2026-06-20T00:00:00+09:00"),
    calendar: cal,
    _directionsMinutes: async () => 30, // injected stub: always 30min (FIND-002)
  });

  // At least one [Travel] block must have been created in total (outbound + return).
  assert.ok(result.inserted >= 1, `expected ≥1 inserted, got ${result.inserted}`);

  // A return block must exist: it starts at ev.endMs (15:00 JST = ms(15)).
  const evEndMs = ms(15);
  const returnBlock = cal._created.find(
    (c) => c.summary && c.summary.includes("[Travel]") &&
           c.start_datetime === new Date(evEndMs).toISOString().replace(/\.\d{3}Z$/, "").replace("Z", ""),
  );
  assert.ok(returnBlock, `expected a return [Travel] block starting at ev.endMs (${new Date(evEndMs).toISOString()}), but none found among: ${JSON.stringify(cal._created.map(c => ({ s: c.summary, t: c.start_datetime })))}`);
  // Return block goes venue → home.
  assert.ok(returnBlock.summary.includes(VENUE.slice(0, 5)), `return block summary should reference venue: ${returnBlock.summary}`);
  assert.equal(returnBlock.description, "Auto-inserted by Life Manager — adjust if the route is wrong.");
  assert.doesNotMatch(returnBlock.description, /\bAnicca\b/i);
});

// ── Integration (b): back-to-back ≤90min real venue → NO return block ─────────────────────────
test("[INTEGRATION][FIND-002](b) back-to-back events (≤90min gap, real venues) → NO return block between them", async () => {
  // Two events 60min apart at real venues. No return block between ev1 and ev2.
  const cal = makeFakeCalendar([
    rawEv({ summary: "Morning mtg", location: VENUE,  startH: 9,  endH: 10 }),
    rawEv({ summary: "Lunch meet",  location: VENUE2, startH: 11, endH: 12 }), // 60min after ev1.end
  ]);

  await fillTravel("uid2", {
    home: HOME,
    mapsKey: "fake-key",
    nowMs: Date.parse("2026-06-20T00:00:00+09:00"),
    calendar: cal,
    _directionsMinutes: async () => 20, // injected stub
  });

  // A return block between ev1 (ends 10:00) and ev2 (starts 11:00) must NOT exist.
  const ev1EndMs = ms(10);
  const ev2StartMs = ms(11);
  const illegalReturnBlock = cal._created.find(
    (c) => c.summary && c.summary.includes("[Travel]") &&
           // block starts at ev1.endMs
           c.start_datetime === new Date(ev1EndMs).toISOString().replace(/\.\d{3}Z$/, "").replace("Z", "") &&
           // and ends before ev2.startMs
           Date.parse(c.start_datetime + "Z") < ev2StartMs,
  );
  assert.equal(illegalReturnBlock, undefined,
    `no return block should be inserted between back-to-back events, but found: ${JSON.stringify(illegalReturnBlock)}`);
});

// ── FIND-003: Idempotency — two fillTravel runs do NOT insert duplicate return blocks ────────────
test("[IDEMPOTENCY][FIND-003] two fillTravel runs do NOT insert a duplicate return [Travel] block", async () => {
  // Simulate run 1: one event, returns a return block.
  // Run 2: calendar already contains the return block → no duplicate.

  const dentistEvent = rawEv({ summary: "Dentist", location: VENUE, startH: 14, endH: 15 });
  const evEndMs = ms(15);
  const retArriveMs = evEndMs + 30 * 60000; // 30 min travel

  // Helper to build the return block as it would appear in the raw event list after run 1.
  function returnBlockRow() {
    const start = new Date(evEndMs).toISOString().replace(/\.\d{3}Z$/, "+00:00");
    const end   = new Date(retArriveMs).toISOString().replace(/\.\d{3}Z$/, "+00:00");
    return {
      summary: `[Travel] 🚆 ${VENUE.slice(0, 18)}→${HOME.slice(0, 18)}`,
      location: HOME,
      start: { dateTime: start },
      end:   { dateTime: end },
    };
  }

  // Run 1: no return block yet.
  const cal1 = makeFakeCalendar([dentistEvent]);
  const result1 = await fillTravel("uid3", {
    home: HOME, mapsKey: "fake-key",
    nowMs: Date.parse("2026-06-20T00:00:00+09:00"),
    calendar: cal1,
    _directionsMinutes: async () => 30,
  });
  // Run 1 should have inserted at least the return block.
  const returnBlocks1 = cal1._created.filter(
    (c) => c.summary && c.summary.includes("[Travel]") &&
           c.start_datetime === new Date(evEndMs).toISOString().replace(/\.\d{3}Z$/, "").replace("Z", ""),
  );
  assert.equal(returnBlocks1.length, 1, `run 1 must insert exactly 1 return block, got ${returnBlocks1.length}`);

  // Run 2: calendar now includes the original event AND the return block from run 1.
  const cal2 = makeFakeCalendar([dentistEvent, returnBlockRow()]);
  const result2 = await fillTravel("uid3", {
    home: HOME, mapsKey: "fake-key",
    nowMs: Date.parse("2026-06-20T00:00:00+09:00"),
    calendar: cal2,
    _directionsMinutes: async () => 30,
  });
  // Run 2 must NOT insert another return block.
  const returnBlocks2 = cal2._created.filter(
    (c) => c.summary && c.summary.includes("[Travel]") &&
           c.start_datetime === new Date(evEndMs).toISOString().replace(/\.\d{3}Z$/, "").replace("Z", ""),
  );
  assert.equal(returnBlocks2.length, 0,
    `run 2 must NOT insert a duplicate return block, but found ${returnBlocks2.length}: ${JSON.stringify(returnBlocks2)}`);
  void result1; void result2; // suppress unused warnings
});

// ── FIND-006: NON-ADJACENT dedup — array-window retDup (not just returnDecision's 'next' guard) ──
test("[FIND-006][IDEMPOTENCY] non-adjacent return block: a non-Travel event sits BETWEEN ev and existing return block — retDup array-window scan must fire, no duplicate inserted", async () => {
  // Layout: [dentist(14-15), zoom-standup(15:05-15:30), returnBlock(15:00-15:30)]
  // The return block (startMs=ms(15)) is NOT events[i+1] for the dentist (events[i+1] = zoom-standup).
  // returnDecision's single-'next' guard fires on zoom-standup (no [Travel] summary → does NOT return
  // insert:false). So the only thing stopping a duplicate is the array-window retDup scan.

  const dentistEvent = rawEv({ summary: "Dentist", location: VENUE, startH: 14, endH: 15 });
  const evEndMs = ms(15);
  const retArriveMs = evEndMs + 30 * 60000;

  // A non-[Travel] event that sits in the slot immediately after dentist (events[i+1]).
  const zoomStandup = rawEv({ summary: "Zoom standup", location: "", startH: 15, endH: 16 });

  // The return block already in the calendar — starts at ev.endMs, NOT adjacent in array order.
  function existingReturnRow() {
    const start = new Date(evEndMs).toISOString().replace(/\.\d{3}Z$/, "+00:00");
    const end   = new Date(retArriveMs).toISOString().replace(/\.\d{3}Z$/, "+00:00");
    return {
      summary: `[Travel] 🚆 ${VENUE.slice(0, 18)}→${HOME.slice(0, 18)}`,
      location: HOME,
      start: { dateTime: start },
      end:   { dateTime: end },
    };
  }

  // Array order: dentist, zoomStandup (non-Travel, is events[i+1] for dentist), existingReturnBlock
  // returnDecision's 'next' guard sees zoomStandup (not a [Travel] block) → does NOT short-circuit.
  // The retDup scan is the ONLY guard that sees existingReturnBlock.
  const cal = makeFakeCalendar([dentistEvent, zoomStandup, existingReturnRow()]);
  await fillTravel("uid4", {
    home: HOME, mapsKey: "fake-key",
    nowMs: Date.parse("2026-06-20T00:00:00+09:00"),
    calendar: cal,
    _directionsMinutes: async () => 30,
  });

  // No duplicate return block must be created.
  const duplicateReturnBlocks = cal._created.filter(
    (c) => c.summary && c.summary.includes("[Travel]") &&
           c.start_datetime === new Date(evEndMs).toISOString().replace(/\.\d{3}Z$/, "").replace("Z", ""),
  );
  assert.equal(duplicateReturnBlocks.length, 0,
    `non-adjacent retDup scan must prevent duplicate; found ${duplicateReturnBlocks.length}: ${JSON.stringify(duplicateReturnBlocks)}`);
});

// ── FIND-005(a): outbound-exists-return-missing → re-run MUST backfill the return block ──────────
test("[FIND-005a][BACKFILL] outbound block exists but return block is missing → re-run backfills return", async () => {
  // Simulates the scenario where run 1 created the outbound block but the return directions call
  // failed (returned null). The calendar now has: [outboundBlock, dentistEvent] — no return block.
  // Run 2 should see the outbound dedup (dup=true) and NOT skip the return-leg evaluation.

  const dentistEvent = rawEv({ summary: "Dentist", location: VENUE, startH: 14, endH: 15 });
  const evStartMs = ms(14);
  const evEndMs   = ms(15);

  // The outbound [Travel] block that already exists (ends at ev.startMs = 14:00).
  // leaveMs = 13:30 (30min travel + 5min buffer = 35min before 14:00 → 13:25, but here we use a
  // convenient block that ends at ev.startMs to satisfy the dedup predicate:
  //   e.endMs <= ev.startMs (ms(14)) && e.endMs > ev.startMs - 3h (ms(11))
  function existingOutboundRow() {
    const leaveMs = evStartMs - 35 * 60000; // 35 min before event
    const start = new Date(leaveMs).toISOString().replace(/\.\d{3}Z$/, "+00:00");
    const end   = new Date(evStartMs).toISOString().replace(/\.\d{3}Z$/, "+00:00");
    return {
      summary: `[Travel] 🚆 ${HOME.slice(0, 18)}→${VENUE.slice(0, 18)}`,
      location: VENUE,
      start: { dateTime: start },
      end:   { dateTime: end },
    };
  }

  // Calendar has outbound block + the dentist event, but NO return block.
  // The outbound dedup will fire (a [Travel] block exists ending at ev.startMs).
  // FIND-005 fix: the return-leg evaluation must still run.
  const cal = makeFakeCalendar([existingOutboundRow(), dentistEvent]);
  await fillTravel("uid5", {
    home: HOME, mapsKey: "fake-key",
    nowMs: Date.parse("2026-06-20T00:00:00+09:00"),
    calendar: cal,
    _directionsMinutes: async () => 30,
  });

  // A return block starting at ev.endMs must have been created.
  const returnBlock = cal._created.find(
    (c) => c.summary && c.summary.includes("[Travel]") &&
           c.start_datetime === new Date(evEndMs).toISOString().replace(/\.\d{3}Z$/, "").replace("Z", ""),
  );
  assert.ok(returnBlock,
    `backfill: re-run must create missing return block at ev.endMs (${new Date(evEndMs).toISOString()}), got: ${JSON.stringify(cal._created.map(c => ({ s: c.summary, t: c.start_datetime })))}`);
});

// ── FIND-005(b): outbound leave-time in past + ev.endMs future → return block STILL created ──────
test("[FIND-005b][PAST-LEAVE] outbound leave-time is in the past but ev.endMs is still future → return (head home) block is created", async () => {
  // nowMs is set to 13:40 JST (between dentist start 14:00 and the computed leave time 13:25 JST).
  // With stub returning 30min travel + 5min buffer = 35min:
  //   leaveMs = ms(14) - 35*60000 = 13:25 JST. 13:25 < 13:40 (nowMs) → outbound block skipped (REQ-18).
  // But ev.endMs = ms(15) = 15:00 JST > 13:40 (nowMs) → event not over → return block MUST be created.

  const dentistEvent = rawEv({ summary: "Dentist", location: VENUE, startH: 14, endH: 15 });
  const evEndMs = ms(15);
  // nowMs = 13:40 JST — outbound leave would be 13:25 JST, which is past nowMs.
  const nowMs40 = Date.parse("2026-06-20T13:40:00+09:00");
  // isoNaiveUTC(ms(14) - 35*60*1000) = the outbound departure ISO string (UTC, no ms/Z).
  // ms(14) = Date.parse("2026-06-20T14:00:00+09:00") = 2026-06-20T05:00:00Z
  // leaveMs = ms(14) - 35*60000 = 2026-06-20T04:25:00Z → isoNaiveUTC → "2026-06-20T04:25:00"
  const outboundDepartureIso = new Date(ms(14) - 35 * 60000).toISOString().replace(/\.\d{3}Z$/, "").replace("Z", "");
  // Return block starts at ev.endMs: ms(15) = 2026-06-20T06:00:00Z → "2026-06-20T06:00:00"
  const returnStartIso = new Date(evEndMs).toISOString().replace(/\.\d{3}Z$/, "").replace("Z", "");

  const cal = makeFakeCalendar([dentistEvent]);
  await fillTravel("uid6", {
    home: HOME, mapsKey: "fake-key",
    nowMs: nowMs40,
    calendar: cal,
    _directionsMinutes: async () => 30, // 30min + 5min buffer = 35min → leaveMs = 13:25 JST < nowMs
  });

  // Outbound block should NOT be created (leave time 13:25 JST < nowMs 13:40 JST).
  const outboundBlock = cal._created.find(
    (c) => c.summary && c.summary.includes("[Travel]") && c.start_datetime === outboundDepartureIso,
  );
  assert.equal(outboundBlock, undefined,
    `outbound block must NOT be created when leave-time is past; got: ${JSON.stringify(outboundBlock)}`);

  // Return block MUST be created (ev.endMs=15:00 JST is still future relative to nowMs=13:40 JST).
  const returnBlock = cal._created.find(
    (c) => c.summary && c.summary.includes("[Travel]") && c.start_datetime === returnStartIso,
  );
  assert.ok(returnBlock,
    `return (head home) block must be created even when outbound leave-time is past; got: ${JSON.stringify(cal._created.map(c => ({ s: c.summary, t: c.start_datetime })))}`);
});

test("[AC-14][INTEGRATION] fillTravel failed Transit calls exactly one legacy Google request per leg", async () => {
  const originalFetch = global.fetch;
  let transitRequests = 0;
  let googleRequests = 0;
  let routesRequests = 0;
  global.fetch = async (url) => {
    const requestUrl = String(url);
    if (requestUrl.includes("maps.googleapis.com/maps/api/geocode/json")) {
      return { ok: true, status: 200, json: async () => ({ status: "OK",
        results: [{ geometry: { location: { lat: 35.681, lng: 139.767 } } }] }) };
    }
    if (requestUrl.includes("api.transit.ls8h.com")) {
      transitRequests++;
      return { ok: true, json: async () => ({ date: "20260620", timezone: "Asia/Tokyo", journeys: [] }) };
    }
    if (requestUrl.includes("maps.googleapis.com/maps/api/directions")) {
      googleRequests++;
      return { ok: true, json: async () => ({ status: "OK", routes: [{ legs: [{ duration: { value: 1200 } }] }] }) };
    }
    if (requestUrl.includes("routes.googleapis.com")) {
      routesRequests++;
      return { ok: true, json: async () => ({ routes: [{ duration: "2700s" }] }) };
    }
    throw new Error("unexpected URL " + requestUrl);
  };
  try {
    const cal = makeFakeCalendar([
      rawEv({ summary: "Transit outage event", location: VENUE, startH: 14, endH: 15 }),
    ]);
    const result = await fillTravel("uid-ac14-failed", {
      home: HOME,
      mapsKey: "fake-key",
      nowMs: Date.parse("2026-06-19T00:00:00+09:00"),
      calendar: cal,
      _directionsMinutes: directionsMinutes,
    });
    assert.equal(result.inserted, 2, "one event produces outbound and return travel blocks");
    assert.equal(transitRequests, 2, "Transit is attempted once for each leg");
    assert.equal(googleRequests, 2, "each failed Transit leg gets one Google request");
    assert.equal(routesRequests, 0, "structured fallback does not invoke Routes API");
  } finally { global.fetch = originalFetch; }
});

async function withReturnClaimStore(run) {
  const originalFetch = globalThis.fetch;
  const claims = new Set();
  const deletes = [];
  globalThis.fetch = async (input, init = {}) => {
    const url = new URL(String(input));
    if (url.pathname !== "/rest/v1/lm_travel_log") throw new Error("unexpected test fetch");
    const body = init.body ? JSON.parse(init.body) : null;
    const eventKey = body?.event_key || url.searchParams.get("event_key")?.replace(/^eq\./, "");
    const leg = body?.leg || url.searchParams.get("leg")?.replace(/^eq\./, "");
    const key = `${eventKey}:${leg}`;
    if (init.method === "POST") {
      if (claims.has(key)) return { status: 409 };
      claims.add(key);
      return { status: 201 };
    }
    if (init.method === "DELETE") {
      deletes.push(key);
      claims.delete(key);
      return { status: 204 };
    }
    throw new Error("unexpected travel log method");
  };
  try { await run({ claims, deletes }); }
  finally { globalThis.fetch = originalFetch; }
}

const RETURN_EVENT = {
  id: "event-return-unknown", summary: "Dentist", location: VENUE,
  start: { dateTime: "2030-01-01T10:00:00+09:00" },
  end: { dateTime: "2030-01-01T11:00:00+09:00" },
};
const RETURN_OPTIONS = {
  home: HOME, mapsKey: "fixture", nowMs: Date.parse("2030-01-01T08:00:00+09:00"),
  expectedCalendarAccountId: "ca-expected", supaUrl: "https://db.example", supaKey: "fixture",
  _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => isReturn ? 20 : null,
};

test("keeps RETURN claim after an unknown create result and does not replay the Calendar write", async () => {
  await withReturnClaimStore(async ({ claims, deletes }) => {
    let writes = 0;
    const reads = [];
    const calendar = {
      async listEventsRaw(_uid, options) { reads.push(options); return [RETURN_EVENT]; },
      async createEvent(_uid, _args, options) {
        writes++;
        assert.equal(options.expectedCalendarAccountId, "ca-expected");
        return { successful: false, effect: "unknown" };
      },
    };
    const first = await fillTravel("tenant-return", { ...RETURN_OPTIONS, calendar });
    const second = await fillTravel("tenant-return", { ...RETURN_OPTIONS, calendar });
    assert.equal(first.inserted, 0);
    assert.equal(first.verified, 0);
    assert.equal(second.inserted, 0);
    assert.equal(writes, 1);
    assert.equal(claims.has("event-return-unknown:return"), true);
    assert.deepEqual(deletes, []);
    assert.equal(reads[1].strict, true);
    assert.equal(reads[1].expectedCalendarAccountId, "ca-expected");
  });
});

test("a definite RETURN no-effect rejection releases only the RETURN claim", async () => {
  await withReturnClaimStore(async ({ claims, deletes }) => {
    const calendar = {
      async listEventsRaw() { return [RETURN_EVENT]; },
      async createEvent(_uid, args) {
        return args.location === HOME
          ? { successful: false, effect: "no_effect" }
          : { successful: true, effect: "created" };
      },
    };
    await fillTravel("tenant-return-rejected", {
      ...RETURN_OPTIONS, _directionsMinutes: async () => 20, calendar,
    });
    assert.deepEqual(deletes, ["event-return-unknown:return"]);
    assert.equal(claims.has("event-return-unknown:go"), true);
    assert.equal(claims.has("event-return-unknown:return"), false);
  });
});
