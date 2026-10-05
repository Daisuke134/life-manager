// travel.test.js — unit guards for travelDecision (the home→home noise fix).
// Run: node --test apps/life-call/lib/travel.test.js
"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { claimTravel, fillTravel, listEvents7d, travelDecision } = require("./travel.js");

const HOME = "新宿区南元町15-27";
const ms = (h) => Date.parse(`2026-06-20T${String(h).padStart(2, "0")}:00:00+09:00`);

test("home→home (at-home activity, origin=home) → NO travel block", () => {
  const ev = { summary: "🧘 Meditation", location: HOME, startMs: ms(6) };
  const d = travelDecision(ev, null, HOME);
  assert.equal(d.insert, false);
  assert.equal(d.reason, "same-location");
});

test("home location with spacing differences still counts as same → skip", () => {
  const ev = { summary: "😴 Sleep", location: " 新宿区南元町15-27 ", startMs: ms(23) };
  assert.equal(travelDecision(ev, null, HOME).insert, false);
});

test("event with no location → skip", () => {
  const ev = { summary: "Call mom", location: "", startMs: ms(10) };
  assert.equal(travelDecision(ev, null, HOME).reason, "helper-or-no-location");
});

test("[Travel] helper block itself → skip", () => {
  const ev = { summary: "[Travel] 🚆 A→B", location: "somewhere", startMs: ms(10) };
  assert.equal(travelDecision(ev, null, HOME).insert, false);
});

test("home unknown → skip (no-origin), leave for ask-loop", () => {
  const ev = { summary: "Meeting", location: "渋谷ヒカリエ", startMs: ms(10) };
  assert.equal(travelDecision(ev, null, "").reason, "no-origin");
});

test("home → real venue → INSERT, origin=home", () => {
  const ev = { summary: "松竹 ネタ見せ", location: "新宿1-36-4", startMs: ms(18) };
  const d = travelDecision(ev, null, HOME);
  assert.equal(d.insert, true);
  assert.equal(d.origin, HOME);
});

test("back-to-back: prev ends ≤90min before, different place → origin=prev (office→home travel)", () => {
  const prev = { location: "MUIT 生駒", endMs: ms(17) };
  const ev = { summary: "😴 Sleep", location: HOME, startMs: ms(18) }; // 60min after prev
  const d = travelDecision(ev, prev, HOME);
  assert.equal(d.insert, true);          // genuine travel home from the office
  assert.equal(d.origin, "MUIT 生駒");
});

test("prev far (>90min gap) → origin falls back to home → home→home skip", () => {
  const prev = { location: "MUIT 生駒", endMs: ms(12) };
  const ev = { summary: "😴 Sleep", location: HOME, startMs: ms(18) }; // 6h after prev
  assert.equal(travelDecision(ev, prev, HOME).reason, "same-location");
});

test("null/undefined ev → skip (no crash)", () => {
  assert.equal(travelDecision(null, null, HOME).insert, false);
  assert.equal(travelDecision(undefined, null, HOME).insert, false);
});

test("same-venue back-to-back (prev location == ev location, != home) → skip", () => {
  const prev = { location: "渋谷ヒカリエ", endMs: ms(13) };
  const ev = { summary: "打ち合わせ2", location: "渋谷ヒカリエ", startMs: ms(14) };
  assert.equal(travelDecision(ev, prev, HOME).reason, "same-location");
});

test("prev is a [Travel] helper block → not used as origin (falls back to home)", () => {
  const prev = { summary: "[Travel] 🚆 A→B", location: "somewhere-else", endMs: ms(17) };
  const ev = { summary: "😴 Sleep", location: HOME, startMs: ms(18) };
  // origin must NOT leak from the [Travel] block; falls back to home → home→home skip
  assert.equal(travelDecision(ev, prev, HOME).reason, "same-location");
});

test("replayed lm_travel_log claim prevents a duplicate helper for the same event leg", async () => {
  const originalFetch = global.fetch;
  const statuses = [201, 409];
  const calls = [];
  global.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return { status: statuses.shift() };
  };
  try {
    assert.equal(await claimTravel("uid-1", "event-1", "go", "https://supa.example", "service-key"), true);
    assert.equal(await claimTravel("uid-1", "event-1", "go", "https://supa.example", "service-key"), false);
    assert.equal(calls.length, 2);
    assert.ok(calls.every(({ url }) => url.endsWith("/lm_travel_log")));
    assert.ok(calls.every(({ init }) => JSON.parse(init.body).uid === "uid-1"));
    assert.ok(calls.every(({ init }) => JSON.parse(init.body).event_key === "event-1"));
    assert.ok(calls.every(({ init }) => JSON.parse(init.body).leg === "go"));
  } finally { global.fetch = originalFetch; }
});

test("shared event reader exposes the existing normalized seven-day calendar query", async () => {
  const requests = [];
  const nowMs = Date.parse("2030-01-01T08:00:00+09:00");
  const events = await listEvents7d("uid-1", "unused", nowMs, {
    async listEventsRaw(uid, bounds) {
      requests.push({ uid, bounds });
      return [{
        id: "event-1", summary: "Meeting", location: "Shibuya",
        start: { dateTime: "2030-01-01T10:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T11:00:00+09:00", timeZone: "Asia/Tokyo" },
      }];
    },
  });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].uid, "uid-1");
  assert.equal(requests[0].bounds.timeMin, "2029-12-31T23:00:00Z");
  assert.equal(requests[0].bounds.timeMax, "2030-01-07T23:00:00Z");
  assert.equal(events[0].id, "event-1");
  assert.equal(events[0].location, "Shibuya");
  assert.equal(events[0].startMs, Date.parse("2030-01-01T10:00:00+09:00"));
  assert.equal(events[0].endMs, Date.parse("2030-01-01T11:00:00+09:00"));
});

test("Travel event uses one five-minute buffer and safe attendee/meeting defaults", async () => {
  const startsAt = Date.parse("2030-01-01T10:00:00+09:00");
  const nowMs = Date.parse("2030-01-01T08:00:00+09:00");
  const created = [];
  const calendar = {
    async listEventsRaw() {
      return [{
        id: "event-1", summary: "Meeting", location: "Shibuya",
        start: { dateTime: new Date(startsAt).toISOString() },
        end: { dateTime: new Date(startsAt + 60 * 60_000).toISOString() },
      }];
    },
    async createEvent(_uid, args) { created.push(args); return { successful: true }; },
  };
  await fillTravel("uid-1", {
    mapsKey: "fixture-map-key", home: "Home", nowMs, calendar,
    _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => isReturn ? null : 20,
  });
  assert.equal(created.length, 1);
  assert.equal(Date.parse(`${created[0].start_datetime}Z`), startsAt - 25 * 60_000);
  assert.equal(created[0].event_duration_hour, 0);
  assert.equal(created[0].event_duration_minutes, 25);
  assert.equal(created[0].send_updates, "none");
  assert.equal(created[0].exclude_organizer, true);
  assert.equal(created[0].create_meeting_room, false);
});
