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

test("agent-selected same-day work origin overrides the home fallback for an evening event", () => {
  const office = "MUIT 生駒";
  const prev = { summary: "Work", location: office, startMs: ms(9), endMs: ms(17), timezone: "Asia/Tokyo" };
  const ev = { summary: "Dinner", location: "渋谷ヒカリエ", startMs: ms(19), timezone: "Asia/Tokyo" };
  assert.deepEqual(travelDecision(ev, prev, HOME, office), {
    insert: true, origin: office, reason: "travel-needed",
  });
});

test("back-to-back: prev ends ≤90min before, different place → origin=prev with no saved home", () => {
  const prev = { location: "MUIT 生駒", endMs: ms(17) };
  const ev = { summary: "😴 Sleep", location: HOME, startMs: ms(18) }; // 60min after prev
  const d = travelDecision(ev, prev, "");
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
        reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
      }];
    },
  });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].uid, "uid-1");
  assert.equal(requests[0].bounds.timeMin, "2029-12-30T21:00:00Z");
  assert.equal(requests[0].bounds.timeMax, "2030-01-07T23:00:00Z");
  assert.equal(events[0].id, "event-1");
  assert.equal(events[0].location, "Shibuya");
  assert.equal(events[0].startMs, Date.parse("2030-01-01T10:00:00+09:00"));
  assert.equal(events[0].endMs, Date.parse("2030-01-01T11:00:00+09:00"));
  assert.deepEqual(events[0].reminders, { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] });
});

test("shared event reader carries the expected account into its Calendar operation", async () => {
  let bounds;
  await listEvents7d("uid-web", "unused", Date.parse("2030-01-01T08:00:00+09:00"), {
    async listEventsRaw(_uid, input) { bounds = input; return []; },
  }, null, { strict: true, expectedCalendarAccountId: "ca-expected" });
  assert.equal(bounds.expectedCalendarAccountId, "ca-expected");
});

test("shared event reader exposes only an ownership flag for Life Manager Travel blocks", async () => {
  const events = await listEvents7d("uid-web", "unused", Date.parse("2030-01-01T08:00:00+09:00"), {
    async listEventsRaw() { return [{
      id: "travel-owned", summary: "[Travel] 🚆 Home→Venue", location: "Venue",
      description: "Auto-inserted by Life Manager — adjust if the route is wrong.",
      start: { dateTime: "2030-01-01T09:35:00+09:00", timeZone: "Asia/Tokyo" },
      end: { dateTime: "2030-01-01T10:00:00+09:00", timeZone: "Asia/Tokyo" },
      reminders: { useDefault: true, overrides: [] },
    }]; },
  });
  assert.equal(events[0].lifeManagerGeneratedTravel, true);
  assert.equal(Object.hasOwn(events[0], "description"), false);
});

test("Travel event uses one five-minute buffer and safe attendee/meeting defaults", async () => {
  const startsAt = Date.parse("2030-01-01T10:00:00+09:00");
  const nowMs = Date.parse("2030-01-01T08:00:00+09:00");
  const created = [];
  let eventReadOptions;
  const calendar = {
    async listEventsRaw(_uid, options) {
      eventReadOptions = options;
      return [{
        id: "event-1", summary: "Meeting", location: "Shibuya",
        start: { dateTime: new Date(startsAt).toISOString() },
        end: { dateTime: new Date(startsAt + 60 * 60_000).toISOString() },
      }];
    },
    async createEvent(_uid, args, options) { created.push({ args, options }); return { successful: true }; },
  };
  await fillTravel("uid-1", {
    mapsKey: "fixture-map-key", home: "Home", nowMs, calendar, expectedCalendarAccountId: "ca-expected",
    allowWebInitialScan: true,
    _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => isReturn ? null : 20,
  });
  assert.equal(created.length, 1);
  assert.equal(eventReadOptions.expectedCalendarAccountId, "ca-expected");
  assert.equal(created[0].options.expectedCalendarAccountId, "ca-expected");
  assert.equal(created[0].options.allowWebInitialScan, true);
  assert.equal(Date.parse(`${created[0].args.start_datetime}Z`), startsAt - 25 * 60_000);
  assert.equal(created[0].args.event_duration_hour, 0);
  assert.equal(created[0].args.event_duration_minutes, 25);
  assert.equal(created[0].args.send_updates, "none");
  assert.deepEqual(created[0].args.reminders, { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] });
  assert.equal(created[0].args.exclude_organizer, true);
  assert.equal(created[0].args.create_meeting_room, false);
});

test("legacy Calendar travel writes do not gain a Web-only popup reminder", async () => {
  const startsAt = Date.parse("2030-01-01T10:00:00+09:00");
  const created = [];
  const calendar = {
    async listEventsRaw() { return [{
      id: "event-telegram", summary: "Meeting", location: "Shibuya",
      start: { dateTime: new Date(startsAt).toISOString() },
      end: { dateTime: new Date(startsAt + 60 * 60_000).toISOString() },
    }]; },
    async createEvent(_uid, args) { created.push(args); return { successful: true }; },
  };
  await fillTravel("telegram-user", {
    mapsKey: "fixture-map-key", home: "Home", nowMs: Date.parse("2030-01-01T08:00:00+09:00"), calendar,
    _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => isReturn ? null : 20,
  });
  assert.equal(created.length, 1);
  assert.equal(Object.hasOwn(created[0], "reminders"), false);
});

async function withTravelClaimStore(run) {
  const originalFetch = globalThis.fetch;
  const claims = new Set();
  const rows = new Map();
  const deletes = [];
  globalThis.fetch = async (input, init = {}) => {
    const url = new URL(String(input));
    if (url.pathname !== "/rest/v1/lm_travel_log") throw new Error("unexpected test fetch");
    const body = init.body ? JSON.parse(init.body) : null;
    const eventKey = body?.event_key || url.searchParams.get("event_key")?.replace(/^eq\./, "");
    const leg = body?.leg || (url.searchParams.get("leg")?.startsWith("eq.") ? url.searchParams.get("leg").slice(3) : null);
    const key = `${eventKey}:${leg}`;
    if (init.method === "POST") {
      if (claims.has(key)) return { status: 409 };
      claims.add(key);
      rows.set(key, structuredClone(body));
      return { status: 201 };
    }
    if (!init.method || init.method === "GET") return { ok: true, status: 200, json: async () =>
      [...rows.values()].filter((row) => row.uid === url.searchParams.get("uid")?.replace(/^eq\./, "")
        && row.event_key === eventKey && (!leg || row.leg === leg)).map((row) => structuredClone(row)) };
    if (init.method === "PATCH") {
      const row = rows.get(key);
      const requestId = url.searchParams.get("calendar_write_receipt->>request_id")?.replace(/^eq\./, "");
      const matched = row && row.calendar_write_receipt?.request_id === requestId;
      if (matched) Object.assign(row, structuredClone(body));
      return { ok: true, status: 200, json: async () => matched ? [structuredClone(row)] : [] };
    }
    if (init.method === "DELETE") {
      deletes.push(key);
      claims.delete(key);
      rows.delete(key);
      return { status: 204 };
    }
    throw new Error("unexpected travel log method");
  };
  try { await run({ claims, deletes, rows }); }
  finally { globalThis.fetch = originalFetch; }
}

test("after-work Travel uses the agent-selected same-day office candidate", async () => {
  await withTravelClaimStore(async () => {
    const office = "MUIT 生駒";
    const sourceRows = [
      { id: "office-morning", summary: "Work", location: office,
        start: { dateTime: "2030-01-01T09:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T10:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "office-midday", summary: "Team", location: office,
        start: { dateTime: "2030-01-01T12:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T13:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "office-afternoon", summary: "Work", location: office,
        start: { dateTime: "2030-01-01T15:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T17:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "travel-helper", summary: "[Travel] 🚆 Office→Other", location: "Helper-only location",
        start: { dateTime: "2030-01-01T17:20:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T17:30:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "dinner", summary: "Dinner", location: "渋谷ヒカリエ",
        start: { dateTime: "2030-01-01T19:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T20:00:00+09:00", timeZone: "Asia/Tokyo" } },
    ];
    const routeCalls = [];
    const outboundTargets = [];
    const allowanceCalls = [];
    const created = [];
    let originCandidates = [];
    const calendar = {
      async listEventsRaw(_uid, bounds) {
        const min = Date.parse(bounds.timeMin);
        return sourceRows.filter((event) => Date.parse(event.end.dateTime) >= min);
      },
      async createEvent(_uid, args) { created.push(args); return { successful: true }; },
    };
    const options = {
      home: HOME,
      geminiKey: "fixture-gemini-key",
      timezone: "Asia/Tokyo",
      nowMs: Date.parse("2030-01-01T17:30:00+09:00"),
      calendar,
      supaUrl: "https://db.example",
      supaKey: "fixture",
      _directionsMinutes: async (from, to, _key, _anchor, _now, isReturn) => {
        if (!isReturn) outboundTargets.push(to);
        if (to === "渋谷ヒカリエ" && !isReturn) routeCalls.push(from);
        return isReturn ? null : 40;
      },
      _reserveManagedAction: async (_uid, eventKey) => {
        allowanceCalls.push(eventKey);
        return { allowed: true, reservationToken: eventKey };
      },
      _completeManagedAction: async () => true,
      _releaseManagedAction: async () => true,
      _readTravelOriginAskState: async () => ({ kind: "none" }),
      _agentResolveTravelOrigin: async (_event, options) => {
        originCandidates = options.candidates;
        const candidate = options.candidates.find((item) => item.location === office);
        assert.equal(candidate.source, "repeated_calendar_location");
        assert.equal(options.candidates.some((item) => item.location === "Helper-only location"), false);
        return { kind: "selected", candidateId: candidate.id };
      },
    };
    const result = await fillTravel("tenant-after-work", options);
    const replay = await fillTravel("tenant-after-work", options);
    assert.ok(originCandidates.some((candidate) => candidate.location === office));
    assert.deepEqual(routeCalls, [office, office]);
    assert.deepEqual(outboundTargets, ["渋谷ヒカリエ", "渋谷ヒカリエ"]);
    assert.equal(allowanceCalls.length, 4, "only the future event may reserve route usage on each run");
    assert.equal(result.inserted, 1);
    assert.equal(replay.inserted, 0);
    assert.equal(created.length, 1);
  });
});

test("unresolved origin asks once, holds outbound routing, then uses the reply", async () => {
  await withTravelClaimStore(async () => {
    const office = "MUIT 生駒";
    const sourceRows = [
      { id: "office-morning", summary: "Work", location: office,
        start: { dateTime: "2030-01-01T09:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T10:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "office-midday", summary: "Team", location: office,
        start: { dateTime: "2030-01-01T12:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T13:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "office-afternoon", summary: "Work", location: office,
        start: { dateTime: "2030-01-01T14:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T15:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "dinner", summary: "Dinner", location: "Venue",
        start: { dateTime: "2030-01-01T19:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T20:00:00+09:00", timeZone: "Asia/Tokyo" } },
    ];
    const outboundOrigins = [];
    const created = [];
    let askState = { kind: "none" };
    let originAgentCalls = 0;
    let askCalls = 0;
    const calendar = {
      async listEventsRaw(_uid, bounds) {
        const min = Date.parse(bounds.timeMin);
        return sourceRows.filter((event) => Date.parse(event.end.dateTime) >= min);
      },
      async createEvent(_uid, args) { created.push(args); return { successful: true }; },
    };
    const options = {
      home: HOME,
      geminiKey: "fixture-gemini-key",
      timezone: "Asia/Tokyo",
      nowMs: Date.parse("2030-01-01T17:30:00+09:00"),
      calendar,
      supaUrl: "https://db.example",
      supaKey: "fixture",
      _directionsMinutes: async (from, _to, _key, _anchor, _now, isReturn) => {
        if (!isReturn) outboundOrigins.push(from);
        return 30;
      },
      _reserveManagedAction: async (_uid, eventKey) => ({ allowed: true, reservationToken: eventKey }),
      _completeManagedAction: async () => true,
      _releaseManagedAction: async () => true,
      _readTravelOriginAskState: async (_uid, eventKey) => {
        assert.equal(eventKey, "dinner");
        return askState;
      },
      _agentResolveTravelOrigin: async () => {
        originAgentCalls++;
        return { kind: "unresolved" };
      },
      _askTravelOrigin: async (_uid, event, eventKey, candidates) => {
        assert.equal(event.id, "dinner");
        assert.equal(eventKey, "dinner");
        assert.ok(candidates.some((candidate) => candidate.location === office));
        askCalls++;
        askState = { kind: "pending" };
        return { kind: "pending", sent: true };
      },
    };

    await fillTravel("tenant-origin-question", options);
    await fillTravel("tenant-origin-question", options);
    assert.deepEqual(outboundOrigins, [], "never create an outbound block from a guessed home while the question is pending");
    assert.equal(askCalls, 1, "replay must not send another question");
    assert.equal(originAgentCalls, 1, "a pending question suppresses repeated model calls");

    askState = { kind: "answered", location: office };
    await fillTravel("tenant-origin-question", options);
    assert.deepEqual(outboundOrigins, [office]);
    assert.equal(askCalls, 1);
    assert.equal(created.length, 2, "the return leg remains independently eligible while the outbound waits");
  });
});

test("unreadable origin ask state fails closed before outbound routing", async () => {
  await withTravelClaimStore(async () => {
    const office = "MUIT 生駒";
    const sourceRows = [
      { id: "office-one", summary: "Work", location: office,
        start: { dateTime: "2030-01-01T09:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T10:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "office-two", summary: "Team", location: office,
        start: { dateTime: "2030-01-01T12:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T13:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "office-three", summary: "Work", location: office,
        start: { dateTime: "2030-01-01T14:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T15:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "dinner", summary: "Dinner", location: "Venue",
        start: { dateTime: "2030-01-01T19:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T20:00:00+09:00", timeZone: "Asia/Tokyo" } },
    ];
    const outboundOrigins = [];
    const calendar = {
      async listEventsRaw() { return sourceRows; },
      async createEvent() { return { successful: true }; },
    };
    const options = {
      home: HOME,
      geminiKey: "fixture-gemini-key",
      timezone: "Asia/Tokyo",
      nowMs: Date.parse("2030-01-01T17:30:00+09:00"),
      calendar,
      supaUrl: "https://db.example",
      supaKey: "fixture",
      _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => {
        if (!isReturn) outboundOrigins.push(_from);
        return isReturn ? null : 40;
      },
      _readTravelOriginAskState: async () => { throw new Error("ledger unavailable"); },
      _agentResolveTravelOrigin: async () => ({ kind: "selected", candidateId: "home" }),
      _askTravelOrigin: async () => assert.fail("do not send when ask-state read failed"),
    };
    await fillTravel("tenant-origin-ledger-down", options);
    await fillTravel("tenant-origin-ledger-unconfigured", {
      ...options,
      supaUrl: undefined,
      supaKey: undefined,
      _readTravelOriginAskState: undefined,
    });
    assert.deepEqual(outboundOrigins, []);
  });
});

test("ongoing Calendar event skips outbound routing but keeps its return route", async () => {
  await withTravelClaimStore(async () => {
    const sourceRows = [
      { id: "ongoing-event", summary: "Dinner", location: "Venue",
        start: { dateTime: "2030-01-01T17:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T18:00:00+09:00", timeZone: "Asia/Tokyo" } },
    ];
    const routeCalls = [];
    const allowanceCalls = [];
    const created = [];
    const calendar = {
      async listEventsRaw() { return sourceRows; },
      async createEvent(_uid, args) { created.push(args); return { successful: true }; },
    };
    const result = await fillTravel("tenant-ongoing-event", {
      home: HOME,
      timezone: "Asia/Tokyo",
      nowMs: Date.parse("2030-01-01T17:30:00+09:00"),
      calendar,
      supaUrl: "https://db.example",
      supaKey: "fixture",
      _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => {
        routeCalls.push(isReturn ? "return" : "outbound");
        return isReturn ? 30 : 40;
      },
      _reserveManagedAction: async (_uid, eventKey) => {
        allowanceCalls.push(eventKey);
        return { allowed: true, reservationToken: eventKey };
      },
      _completeManagedAction: async () => true,
      _releaseManagedAction: async () => true,
    });

    assert.deepEqual(routeCalls, ["return"]);
    assert.equal(allowanceCalls.length, 1);
    assert.equal(result.inserted, 1);
    assert.equal(created.length, 1);
  });
});

test("event starting at now skips origin resolution and outbound routing but keeps its return route", async () => {
  await withTravelClaimStore(async () => {
    const office = "MUIT 生駒";
    const sourceRows = [
      { id: "office-morning", summary: "Work", location: office,
        start: { dateTime: "2030-01-01T09:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T10:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "office-midday", summary: "Team", location: office,
        start: { dateTime: "2030-01-01T12:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T13:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "office-afternoon", summary: "Work", location: office,
        start: { dateTime: "2030-01-01T14:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T15:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "event-now", summary: "Dinner", location: "Venue",
        start: { dateTime: "2030-01-01T17:30:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T18:00:00+09:00", timeZone: "Asia/Tokyo" } },
    ];
    const routeCalls = [];
    const allowanceCalls = [];
    const created = [];
    let originResolutions = 0;
    const calendar = {
      async listEventsRaw() { return sourceRows; },
      async createEvent(_uid, args) { created.push(args); return { successful: true }; },
    };
    const result = await fillTravel("tenant-event-now", {
      home: HOME,
      geminiKey: "fixture-gemini-key",
      timezone: "Asia/Tokyo",
      nowMs: Date.parse("2030-01-01T17:30:00+09:00"),
      calendar,
      supaUrl: "https://db.example",
      supaKey: "fixture",
      _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => {
        routeCalls.push(isReturn ? "return" : "outbound");
        return isReturn ? 30 : 40;
      },
      _reserveManagedAction: async (_uid, eventKey) => {
        allowanceCalls.push(eventKey);
        return { allowed: true, reservationToken: eventKey };
      },
      _completeManagedAction: async () => true,
      _releaseManagedAction: async () => true,
      _agentResolveTravelOrigin: async () => {
        originResolutions++;
        return { kind: "selected", candidateId: "repeated-location" };
      },
    });

    assert.equal(originResolutions, 0);
    assert.deepEqual(routeCalls, ["return"]);
    assert.equal(allowanceCalls.length, 1);
    assert.equal(result.inserted, 1);
    assert.equal(created.length, 1);
  });
});

test("previous-day location is not offered as the origin for today's event", async () => {
  await withTravelClaimStore(async () => {
    const sourceRows = [
      { id: "yesterday-office", summary: "Work", location: "Yesterday Office",
        start: { dateTime: "2029-12-31T15:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2029-12-31T17:00:00+09:00", timeZone: "Asia/Tokyo" } },
      { id: "today-event", summary: "Dinner", location: "Venue",
        start: { dateTime: "2030-01-01T19:00:00+09:00", timeZone: "Asia/Tokyo" },
        end: { dateTime: "2030-01-01T20:00:00+09:00", timeZone: "Asia/Tokyo" } },
    ];
    const origins = [];
    const calendar = {
      async listEventsRaw(_uid, bounds) {
        const min = Date.parse(bounds.timeMin);
        return sourceRows.filter((event) => Date.parse(event.end.dateTime) >= min);
      },
      async createEvent() { return { successful: true }; },
    };
    await fillTravel("tenant-cross-day-origin", {
      home: HOME,
      geminiKey: "fixture-gemini-key",
      timezone: "Asia/Tokyo",
      nowMs: Date.parse("2030-01-01T17:30:00+09:00"),
      calendar,
      _directionsMinutes: async (from, to, _key, _anchor, _now, isReturn) => {
        if (to === "Venue" && !isReturn) origins.push(from);
        return isReturn ? null : 40;
      },
      _agentResolveTravelOrigin: async () => assert.fail("previous-day events must not become candidates"),
    });
    assert.deepEqual(origins, [HOME]);
  });
});

function makeUnknownGoCalendar(readback = () => []) {
  const calls = [];
  const reads = [];
  let readCount = 0;
  const original = {
    id: "event-go-unknown", summary: "Meeting", location: "Venue",
    start: { dateTime: "2030-01-01T10:00:00+09:00" },
    end: { dateTime: "2030-01-01T11:00:00+09:00" },
  };
  return {
    kind: "composio", calls, reads,
    async listEventsRaw(_uid, options) {
      reads.push(options);
      readCount++;
      return readCount === 1 ? [original] : readback(calls[0]?.args, original);
    },
    async listOwnedEvents(_uid, options) {
      reads.push({ ...options, strict: true });
      return readback(calls[0]?.args, original);
    },
    async createEvent(uid, args, options) {
      calls.push({ args, options });
      const { createHash } = require("node:crypto");
      await options.beforeDispatch({ account_ref_hash: createHash("sha256").update(JSON.stringify([uid, "ca-expected"])).digest("hex"),
        command: "calendar.create" });
      return { successful: false, effect: "unknown", writeReceipt: { phase: "response", effect: "unknown",
        http_status: 200, error_class: "unconfirmed_response", provider_event_id: null } };
    },
  };
}

function createdTravelRow(args) {
  const startMs = Date.parse(`${args.start_datetime}Z`);
  const durationMs = (args.event_duration_hour * 60 + args.event_duration_minutes) * 60000;
  return {
    id: "travel-readback", summary: args.summary, location: args.location, description: args.description,
    start: { dateTime: new Date(startMs).toISOString() },
    end: { dateTime: new Date(startMs + durationMs).toISOString() },
    reminders: args.reminders,
  };
}

const GO_TRAVEL_OPTIONS = {
  home: "Home", mapsKey: "fixture", nowMs: Date.parse("2030-01-01T08:00:00+09:00"),
  expectedCalendarAccountId: "ca-expected", supaUrl: "https://db.example", supaKey: "fixture",
  _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => isReturn ? null : 20,
};

async function withDurableTravelFixture(run) {
  const { makeComposioCalendar } = require("./transport/calendar-composio.js");
  const originalFetch = globalThis.fetch;
  const uid = "hybrid-receipt-fixture";
  const accountId = "ca-hybrid-fixture";
  const source = { id: "synthetic-source", updated: "2030-01-01T00:00:00Z", summary: "Fixture meeting", location: "Fixture venue",
    start: { dateTime: "2030-01-01T10:00:00Z" }, end: { dateTime: "2030-01-01T11:00:00Z" } };
  const rows = new Map();
  const creates = [];
  const deletes = [];
  const ledger = [];
  const updates = [];
  const state = { visible: true, response: "timeout", rejectPhase: null, wrongTenant: false,
    extraRows: [], omitMarker: false, readError: false, hideClaimReads: 0, conflicts: 0, phaseAtDispatch: null,
    ledgerSaved: true, onDispatch: null, rejectDelete: false };
  const clone = (value) => structuredClone(value);
  const fetchImpl = async (input, init = {}) => {
    const url = new URL(String(input));
    const method = init.method || "GET";
    const body = init.body && JSON.parse(init.body);
    const response = (value, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => clone(value) });
    if (url.hostname === "db.example") {
      if (url.pathname.endsWith("/lm_users")) return response([{ uid, telegram_chat_id: 123,
        calendar_provider: "composio_gcal", calendar_connected_account_id: accountId }]);
      assert.equal(url.pathname, "/rest/v1/lm_travel_log");
      const eventKey = body?.event_key || url.searchParams.get("event_key")?.replace(/^eq\./, "");
      const leg = body?.leg || (url.searchParams.get("leg")?.startsWith("eq.") ? url.searchParams.get("leg").slice(3) : null);
      const key = `${eventKey}:${leg}`;
      if (method === "POST") {
        if (rows.has(key)) { state.conflicts++; return response(null, 409); }
        rows.set(key, clone(body));
        return response(null, 201);
      }
      if (method === "PATCH") {
        updates.push(clone(body.calendar_write_receipt));
        if (body.calendar_write_receipt?.phase === state.rejectPhase) return response(null, 503);
        const row = rows.get(key);
        const requestId = url.searchParams.get("calendar_write_receipt->>request_id")?.replace(/^eq\./, "");
        if (!row || row.uid !== uid || row.calendar_write_receipt?.request_id !== requestId) return response([]);
        const phase = url.searchParams.get("calendar_write_receipt->>phase")?.replace(/^eq\./, "");
        if (phase && row.calendar_write_receipt.phase !== phase) return response([]);
        const effect = url.searchParams.get("calendar_write_receipt->>effect");
        if (effect === "eq.unknown" && row.calendar_write_receipt.effect !== "unknown") return response([]);
        Object.assign(row, clone(body));
        return response([row]);
      }
      if (method === "DELETE") {
        deletes.push(key);
        if (state.rejectDelete) return response(null, 503);
        const row = rows.get(key);
        const requestId = url.searchParams.get("calendar_write_receipt->>request_id")?.replace(/^eq\./, "");
        if (requestId) assert.equal(url.searchParams.get("calendar_write_receipt->>effect"), "eq.no_effect");
        if (requestId && (row?.calendar_write_receipt?.request_id !== requestId
          || row.calendar_write_receipt.effect !== "no_effect")) return response(null, 204);
        rows.delete(key); return response(null, 204);
      }
      if (state.hideClaimReads-- > 0) return response([]);
      return response([...rows.values()].filter((row) => row.uid === uid && row.event_key === eventKey && (!leg || row.leg === leg)));
    }
    assert.equal(url.hostname, "backend.composio.dev", "fixture must never reach another host");
    if (url.pathname.includes("/connected_accounts/")) return response({ id: accountId,
      user_id: state.wrongTenant ? "other-tenant" : uid, toolkit_slug: "googlecalendar", status: "ACTIVE" });
    if (url.pathname.endsWith("GOOGLECALENDAR_EVENTS_LIST")) {
      if (state.readError && creates.length) throw new Error("synthetic read failure");
      return response({ successful: true, data: { items: [source, ...(state.visible ? creates.map((args) => ({
        ...createdTravelRow(args), ...(state.omitMarker ? { description: "User-created travel" } : {}),
      })) : []), ...state.extraRows] } });
    }
    assert.equal(url.pathname.endsWith("GOOGLECALENDAR_CREATE_EVENT"), true);
    creates.push(clone(body.arguments));
    state.phaseAtDispatch = clone(rows.get("synthetic-source:go")?.calendar_write_receipt);
    if (state.onDispatch) await state.onDispatch();
    if (state.response === "timeout") throw new Error("synthetic post-dispatch timeout");
    if (state.response === "validation") return response({ error: "invalid parameters" }, 400);
    if (state.response === "unclassified-4xx") return response({ error: "opaque rejection" }, 400);
    return response({ successful: true, data: { id: "travel-readback" } });
  };
  globalThis.fetch = fetchImpl;
  const calendar = makeComposioCalendar({ apiKey: "fixture", supaUrl: "https://db.example", supaKey: "fixture",
    fetchImpl, recordCall: async (_uid, tool, details) => { ledger.push({ tool, ...details }); return state.ledgerSaved; } });
  const options = { home: "Fixture home", mapsKey: "fixture", nowMs: Date.parse("2030-01-01T08:00:00Z"),
    calendar, supaUrl: "https://db.example", supaKey: "fixture",
    _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => isReturn ? null : 20 };
  try { await run({ uid, source, rows, creates, deletes, ledger, updates, state, calendar, options }); }
  finally { globalThis.fetch = originalFetch; }
}

test("CLD02 Hybrid unknown create is verified only by its durable owned marker receipt", async () => {
  await withDurableTravelFixture(async (f) => {
    const result = await fillTravel(f.uid, f.options);
    assert.equal(result.verified, 1);
    assert.equal(result.inserted, 0);
    const receipt = f.rows.get("synthetic-source:go").calendar_write_receipt;
    assert.equal(f.state.phaseAtDispatch.phase, "dispatching");
    for (const field of ["request_id", "source_event_hash", "source_event_version", "request_fingerprint", "account_ref_hash"]) {
      assert.match(receipt[field], /^[a-f0-9]{64}$/);
    }
    assert.equal(receipt.effect, "verified");
    assert.equal(receipt.provider_event_id, "travel-readback");
    assert.equal(receipt.readback, "exact_one");
    assert.equal(receipt.leg, "go");
    assert.equal(JSON.stringify(receipt).includes("Fixture venue"), false);
    assert.equal(JSON.stringify(receipt).includes("Fixture meeting"), false);
    assert.equal(JSON.stringify(receipt).includes("fixture-service"), false);
    const createCost = f.ledger.find((entry) => entry.tool === "GOOGLECALENDAR_CREATE_EVENT");
    assert.equal(createCost.travelWrite.request_id, receipt.request_id);
    assert.equal(createCost.travelWrite.source_event_version, receipt.source_event_version);
    assert.equal(createCost.travelWrite.account_ref_hash, receipt.account_ref_hash);
    assert.deepEqual(f.deletes, []);
  });
});

test("CLD02 claim409 reconciles a prior dispatch read-only, including a stop before response persistence", async () => {
  await withDurableTravelFixture(async (f) => {
    f.state.visible = false;
    f.state.rejectPhase = "response";
    await fillTravel(f.uid, f.options);
    assert.equal(f.rows.get("synthetic-source:go").calendar_write_receipt.phase, "dispatching");
    f.state.rejectPhase = null;
    // The normal cached view still lacks the helper; the owned readback sees the provider result.
    const initialList = f.calendar.listEventsRaw;
    f.calendar.listEventsRaw = async () => [structuredClone(f.source)];
    f.state.visible = true;
    f.state.hideClaimReads = 1; // simulate a concurrent insert after the initial claim read
    const result = await fillTravel(f.uid, f.options);
    f.calendar.listEventsRaw = initialList;
    assert.equal(result.verified, 1);
    assert.equal(f.state.conflicts, 1);
    assert.equal(f.creates.length, 1);
    assert.deepEqual(f.deletes, []);
    const replay = await fillTravel(f.uid, f.options);
    assert.equal(replay.inserted, 0);
    assert.equal(f.creates.length, 1);
  });
});

test("CLD02 absent, ambiguous, missing-marker, wrong-tenant, or failed readback retains unknown without replay", async () => {
  for (const scenario of ["absent", "ambiguous", "missing-marker", "wrong-tenant", "failed"]) {
    await withDurableTravelFixture(async (f) => {
      f.state.visible = false;
      await fillTravel(f.uid, f.options);
      f.state.visible = scenario !== "absent";
      f.state.omitMarker = scenario === "missing-marker";
      f.state.wrongTenant = scenario === "wrong-tenant";
      f.state.readError = scenario === "failed";
      if (scenario === "ambiguous") f.state.extraRows = [createdTravelRow(f.creates[0])];
      f.calendar.listEventsRaw = async () => [structuredClone(f.source)];
      const result = await fillTravel(f.uid, f.options);
      assert.equal(result.verified, 0, scenario);
      assert.equal(result.inserted, 0, scenario);
      assert.equal(f.rows.get("synthetic-source:go").calendar_write_receipt.effect, "unknown", scenario);
      assert.equal(f.creates.length, 1, scenario);
      assert.deepEqual(f.deletes, [], scenario);
    });
  }
});

test("CLD02 dispatch requires durable proof, and old or changed-source claims remain fenced", async () => {
  for (const scenario of ["pre-dispatch-stop", "legacy", "changed-source", "wrong-row-tenant"]) {
    await withDurableTravelFixture(async (f) => {
      if (scenario === "pre-dispatch-stop") f.state.rejectPhase = "dispatching";
      if (scenario === "legacy") f.rows.set("synthetic-source:go", { uid: f.uid, event_key: f.source.id, leg: "go" });
      if (scenario === "changed-source" || scenario === "wrong-row-tenant") {
        f.state.visible = false;
        await fillTravel(f.uid, f.options);
        if (scenario === "changed-source") f.source.updated = "2030-01-01T00:01:00Z";
        else f.rows.get("synthetic-source:go").uid = "another-tenant";
      }
      const before = f.creates.length;
      const result = await fillTravel(f.uid, f.options);
      assert.equal(result.inserted, 0, scenario);
      assert.equal(result.verified, 0, scenario);
      assert.equal(f.creates.length, before, scenario);
      assert.deepEqual(f.deletes, [], scenario);
    });
  }
});

test("CLD02 a late unknown response cannot overwrite another wake's verified receipt", async () => {
  await withDurableTravelFixture(async (f) => {
    f.state.onDispatch = async () => {
      const concurrent = await fillTravel(f.uid, f.options);
      assert.equal(concurrent.verified, 1);
      f.state.visible = false;
    };
    await fillTravel(f.uid, f.options);
    assert.equal(f.rows.get("synthetic-source:go").calendar_write_receipt.effect, "verified");
    assert.equal(f.creates.length, 1);
    assert.deepEqual(f.deletes, []);
  });
});

test("CLD02 exact validation rejection releases its durable attempt; opaque rejection stays unknown", async () => {
  for (const scenario of ["validation", "validation-ledger-failed", "unclassified-4xx"]) {
    await withDurableTravelFixture(async (f) => {
      f.state.visible = false;
      f.state.response = scenario.startsWith("validation") ? "validation" : scenario;
      f.state.ledgerSaved = scenario !== "validation-ledger-failed";
      await fillTravel(f.uid, f.options);
      const receipt = f.updates.findLast((update) => update.phase === "response");
      assert.equal(receipt.http_status, 400);
      assert.equal(receipt.effect, scenario === "unclassified-4xx" ? "unknown" : "no_effect");
      assert.equal(receipt.error_class, scenario === "unclassified-4xx" ? "unclassified_response" : "provider_validation");
      assert.equal(f.deletes.length, scenario.startsWith("validation") ? 1 : 0);
      if (scenario === "unclassified-4xx") {
        const before = f.creates.length;
        await fillTravel(f.uid, f.options);
        assert.equal(f.creates.length, before);
      }
    });
  }
});

test("CLD02 proven no-effect releases despite best-effort cost failure and retries a failed scoped delete", async () => {
  for (const scenario of ["cost-failed", "delete-failed"]) {
    await withDurableTravelFixture(async (f) => {
      f.state.visible = false;
      f.state.response = "validation";
      f.state.ledgerSaved = scenario !== "cost-failed";
      f.state.rejectDelete = scenario === "delete-failed";
      await fillTravel(f.uid, f.options);
      if (scenario === "cost-failed") assert.equal(f.rows.has("synthetic-source:go"), false);
      else assert.equal(f.rows.get("synthetic-source:go").calendar_write_receipt.effect, "no_effect");
      f.state.rejectDelete = false;
      f.state.ledgerSaved = true;
      f.state.response = "timeout";
      f.calendar.listEventsRaw = async () => [structuredClone(f.source)];
      await fillTravel(f.uid, f.options);
      assert.equal(f.creates.length, 2, scenario);
      assert.equal(f.rows.get("synthetic-source:go").calendar_write_receipt.effect, "unknown", scenario);
      await fillTravel(f.uid, f.options);
      assert.equal(f.creates.length, 2, "an uncertain new attempt must stay fenced");
    });
  }
});

test("CLD02 official source revision overrides a stale ordinary reader before verifying its helper", async () => {
  for (const scenario of ["changed", "cancelled", "absent"]) {
    await withDurableTravelFixture(async (f) => {
      f.state.visible = false;
      await fillTravel(f.uid, f.options);
      const cached = structuredClone(f.source);
      f.calendar.listEventsRaw = async () => [cached];
      f.state.visible = true;
      const ownedList = f.calendar.listOwnedEvents.bind(f.calendar);
      f.calendar.listOwnedEvents = async (...args) => (await ownedList(...args))
        .filter((event) => scenario !== "absent" || event.id !== f.source.id)
        .map((event) => event.id !== f.source.id ? event : scenario === "changed"
          ? { ...event, start: { dateTime: "2030-01-01T12:00:00Z" } }
          : scenario === "cancelled" ? { ...event, status: "cancelled" } : event);
      const result = await fillTravel(f.uid, f.options);
      assert.equal(result.verified, 0, scenario);
      assert.equal(f.rows.get("synthetic-source:go").calendar_write_receipt.effect, "unknown", scenario);
      assert.equal(f.creates.length, 1, scenario);
      assert.deepEqual(f.deletes, [], scenario);
    });
  }
});

test("CLD02 an unresolved claim's reconciliation does not dispatch the Web reminder repair", async () => {
  await withTravelClaimStore(async ({ deletes }) => {
    const calendar = makeUnknownGoCalendar((args, original) => {
      const helper = createdTravelRow(args);
      helper.reminders = { useDefault: true };
      return [original, helper];
    });
    let patches = 0;
    calendar.patchEvent = async () => { patches++; return { successful: true, effect: "updated" }; };
    await fillTravel("web-unknown-repair", { ...GO_TRAVEL_OPTIONS, calendar });
    await fillTravel("web-unknown-repair", { ...GO_TRAVEL_OPTIONS, calendar });
    assert.equal(patches, 0);
    assert.equal(calendar.calls.length, 1);
    assert.deepEqual(deletes, []);
  });
});

test("Web initial scan repairs one Life Manager Travel duplicate's missing departure popup without creating another block", async () => {
  const eventRows = [
    { id: "travel-existing", summary: "[Travel] 🚆 Origin→Venue", location: "Venue",
      description: "Auto-inserted by Life Manager — adjust if the route is wrong.",
      start: { dateTime: "2030-01-01T09:35:00+09:00" },
      end: { dateTime: "2030-01-01T10:00:00+09:00" },
      reminders: { useDefault: true, overrides: [] } },
    { id: "event-next", summary: "Meeting", location: "Venue",
      start: { dateTime: "2030-01-01T10:00:00+09:00" },
      end: { dateTime: "2030-01-01T11:00:00+09:00" } },
  ];
  const patches = [];
  const creates = [];
  let reads = 0;
  const calendar = {
    async listEventsRaw() { reads++; return eventRows; },
    async patchEvent(uid, args, options) {
      patches.push({ uid, args, options });
      const existing = eventRows.find((event) => event.id === args.event_id);
      existing.reminders = args.reminders;
      return { successful: true, effect: "updated" };
    },
    async createEvent(_uid, args) { creates.push(args); return { successful: true }; },
  };

  const result = await fillTravel("tenant-web-reminder", {
    ...GO_TRAVEL_OPTIONS, calendar, allowWebInitialScan: true,
  });

  assert.equal(patches.length, 1);
  assert.equal(patches[0].uid, "tenant-web-reminder");
  assert.deepEqual(patches[0].args, {
    calendar_id: "primary", event_id: "travel-existing",
    reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
    send_updates: "none",
  });
  assert.deepEqual(patches[0].options, { expectedCalendarAccountId: "ca-expected", allowWebInitialScan: true });
  assert.equal(reads, 2);
  assert.equal(result.inserted, 0);
  assert.equal(result.verified, 1);
  assert.equal(creates.length, 0);
});

test("Web initial scan repairs an exact generated duplicate reminder without a saved origin", async () => {
  const eventRows = [
    { id: "travel-existing-no-home", summary: "[Travel] 🚆 Origin→Venue", location: "Venue",
      description: "Auto-inserted by Life Manager — adjust if the route is wrong.",
      start: { dateTime: "2030-01-01T09:35:00+09:00" },
      end: { dateTime: "2030-01-01T10:00:00+09:00" },
      reminders: { useDefault: true, overrides: [] } },
    { id: "event-next-no-home", summary: "Meeting", location: "Venue",
      start: { dateTime: "2030-01-01T10:00:00+09:00" },
      end: { dateTime: "2030-01-01T11:00:00+09:00" } },
  ];
  const patches = [];
  const creates = [];
  let reads = 0;
  const calendar = {
    async listEventsRaw() { reads++; return eventRows; },
    async patchEvent(uid, args, options) {
      patches.push({ uid, args, options });
      const existing = eventRows.find((event) => event.id === args.event_id);
      existing.reminders = args.reminders;
      return { successful: true, effect: "updated" };
    },
    async createEvent(_uid, args) { creates.push(args); return { successful: true }; },
  };

  const result = await fillTravel("tenant-web-reminder-without-home", {
    ...GO_TRAVEL_OPTIONS, home: "", calendar, allowWebInitialScan: true,
  });

  assert.equal(patches.length, 1);
  assert.equal(patches[0].uid, "tenant-web-reminder-without-home");
  assert.deepEqual(patches[0].args, {
    calendar_id: "primary", event_id: "travel-existing-no-home",
    reminders: { useDefault: false, overrides: [{ method: "popup", minutes: 0 }] },
    send_updates: "none",
  });
  assert.deepEqual(patches[0].options, { expectedCalendarAccountId: "ca-expected", allowWebInitialScan: true });
  assert.equal(reads, 2);
  assert.equal(result.inserted, 0);
  assert.equal(result.verified, 1);
  assert.equal(creates.length, 0);
});

test("Web initial scan does not patch an unowned or ambiguous Travel duplicate", async () => {
  for (const scenario of [
    { name: "unowned", blocks: [{ id: "manual-travel", description: "Personal travel note" }] },
    { name: "ambiguous", blocks: [
      { id: "travel-one", description: "Auto-inserted by Life Manager — adjust if the route is wrong." },
      { id: "travel-two", description: "Auto-inserted by Life Manager — adjust if the route is wrong." },
    ] },
  ]) {
    const eventRows = [
      ...scenario.blocks.map((block, i) => ({ ...block,
        id: block.id, summary: `[Travel] 🚆 Origin→Venue`, location: "Venue",
        start: { dateTime: i ? "2030-01-01T09:34:00+09:00" : "2030-01-01T09:35:00+09:00" },
        end: { dateTime: i ? "2030-01-01T09:59:00+09:00" : "2030-01-01T10:00:00+09:00" },
        reminders: { useDefault: true, overrides: [] },
      })),
      { id: "event-next", summary: "Meeting", location: "Venue",
        start: { dateTime: "2030-01-01T10:00:00+09:00" },
        end: { dateTime: "2030-01-01T11:00:00+09:00" } },
    ];
    const patches = [];
    const creates = [];
    const calendar = {
      async listEventsRaw() { return eventRows; },
      async patchEvent(_uid, args) { patches.push(args); return { successful: true }; },
      async createEvent(_uid, args) { creates.push(args); return { successful: true }; },
    };
    const result = await fillTravel(`tenant-web-${scenario.name}`, {
      ...GO_TRAVEL_OPTIONS, calendar, allowWebInitialScan: true,
    });
    assert.equal(patches.length, 0, scenario.name);
    assert.equal(creates.length, 0, scenario.name);
    assert.equal(result.verified, 0, scenario.name);
  }
});

test("legacy Telegram tenant never patches an existing Life Manager Travel reminder", async () => {
  const eventRows = [
    { id: "telegram-travel", summary: "[Travel] 🚆 Origin→Venue", location: "Venue",
      description: "Auto-inserted by Life Manager — adjust if the route is wrong.",
      start: { dateTime: "2030-01-01T09:35:00+09:00" },
      end: { dateTime: "2030-01-01T10:00:00+09:00" },
      reminders: { useDefault: true, overrides: [] } },
    { id: "event-telegram", summary: "Meeting", location: "Venue",
      start: { dateTime: "2030-01-01T10:00:00+09:00" },
      end: { dateTime: "2030-01-01T11:00:00+09:00" } },
  ];
  const patches = [];
  const { expectedCalendarAccountId: _ignoredAccount, ...legacyOptions } = GO_TRAVEL_OPTIONS;
  const calendar = {
    async listEventsRaw() { return eventRows; },
    async patchEvent(_uid, args) { patches.push(args); return { successful: true }; },
    async createEvent() { assert.fail("an existing Telegram Travel block must prevent a duplicate"); },
  };

  const result = await fillTravel("telegram-tenant", { ...legacyOptions, calendar });

  assert.equal(patches.length, 0);
  assert.equal(result.inserted, 0);
  assert.equal(result.verified, 0);
});

test("unroutable venue fallback passes the exact tenant and usage writer to the location agent", async () => {
  await withTravelClaimStore(async () => {
    let resolveOptions = null;
    const usageWriter = async () => true;
    await fillTravel("tenant-web-route-fallback", {
      ...GO_TRAVEL_OPTIONS,
      calendar: makeUnknownGoCalendar(),
      geminiKey: "fixture-gemini-key",
      _directionsMinutes: async () => null,
      _agentResolveLocation: async (_event, options) => {
        resolveOptions = options;
        return { kind: "ask" };
      },
      _recordUsageEvent: usageWriter,
    });
    assert.equal(resolveOptions.uid, "tenant-web-route-fallback");
    assert.equal(resolveOptions.recordUsageEvent, usageWriter);
  });
});

test("keeps GO claim after an unknown create result and does not replay the Calendar write", async () => {
  await withTravelClaimStore(async ({ claims, deletes }) => {
    const calendar = makeUnknownGoCalendar();
    const first = await fillTravel("tenant-go", { ...GO_TRAVEL_OPTIONS, calendar });
    const second = await fillTravel("tenant-go", { ...GO_TRAVEL_OPTIONS, calendar });
    assert.equal(first.inserted, 0);
    assert.equal(first.verified, 0);
    assert.equal(second.inserted, 0);
    assert.equal(calendar.calls.length, 1);
    assert.equal(claims.has("event-go-unknown:go"), true);
    assert.deepEqual(deletes, []);
    assert.equal(calendar.reads[1].strict, true);
    assert.equal(calendar.reads[1].expectedCalendarAccountId, "ca-expected");
    assert.equal(calendar.calls[0].options.expectedCalendarAccountId, "ca-expected");
  });
});

test("one exact strict GO readback is verified without reporting a travel addition", async () => {
  await withTravelClaimStore(async ({ claims, deletes }) => {
    const calendar = makeUnknownGoCalendar((args, original) => {
      const row = createdTravelRow(args);
      row.location = " vEnUe ";
      return [original, row];
    });
    const result = await fillTravel("tenant-go-verified", { ...GO_TRAVEL_OPTIONS, calendar });
    assert.equal(result.inserted, 0);
    assert.equal(result.verified, 1);
    assert.deepEqual(result.outboundReports, []);
    assert.equal(claims.has("event-go-unknown:go"), true);
    assert.deepEqual(deletes, []);
  });
});

test("summary, start, end, or destination mismatch is not an exact GO readback", async () => {
  const mismatch = [
    (row) => ({ ...row, summary: `${row.summary} ` }),
    (row) => ({ ...row, start: { dateTime: new Date(Date.parse(row.start.dateTime) + 1).toISOString() } }),
    (row) => ({ ...row, end: { dateTime: new Date(Date.parse(row.end.dateTime) + 1).toISOString() } }),
    (row) => ({ ...row, location: "Other venue" }),
  ];
  for (const alter of mismatch) {
    await withTravelClaimStore(async ({ claims, deletes }) => {
      const calendar = makeUnknownGoCalendar((args, original) => [original, alter(createdTravelRow(args))]);
      const result = await fillTravel("tenant-go-mismatch", { ...GO_TRAVEL_OPTIONS, calendar });
      assert.equal(result.verified, 0);
      assert.equal(result.inserted, 0);
      assert.equal(claims.has("event-go-unknown:go"), true);
      assert.deepEqual(deletes, []);
    });
  }
});

test("failed, empty, or ambiguous GO readback keeps an unknown claim", async () => {
  const cases = [
    { name: "failed", readback: () => { throw new Error("strict read failed"); } },
    { name: "empty", readback: () => [] },
    { name: "ambiguous", readback: (args, original) => [original, createdTravelRow(args), createdTravelRow(args)] },
  ];
  for (const scenario of cases) {
    await withTravelClaimStore(async ({ claims, deletes }) => {
      const calendar = makeUnknownGoCalendar(scenario.readback);
      const result = await fillTravel(`tenant-go-${scenario.name}`, { ...GO_TRAVEL_OPTIONS, calendar });
      assert.equal(result.verified, 0, scenario.name);
      assert.equal(result.inserted, 0, scenario.name);
      assert.equal(claims.has("event-go-unknown:go"), true, scenario.name);
      assert.deepEqual(deletes, [], scenario.name);
    });
  }
});

test("a definite GO no-effect rejection releases only the GO claim", async () => {
  await withTravelClaimStore(async ({ claims, deletes }) => {
    const calendar = {
      async listEventsRaw() { return [{ id: "event-go-unknown", summary: "Meeting", location: "Venue",
        start: { dateTime: "2030-01-01T10:00:00+09:00" }, end: { dateTime: "2030-01-01T11:00:00+09:00" } }]; },
      async createEvent(_uid, args) {
        return args.summary.includes("Home→Venue")
          ? { successful: false, effect: "no_effect" }
          : { successful: true, effect: "created" };
      },
    };
    const result = await fillTravel("tenant-go-rejected", {
      ...GO_TRAVEL_OPTIONS, _directionsMinutes: async () => 20, calendar,
    });
    assert.equal(result.inserted, 1);
    assert.deepEqual(deletes, ["event-go-unknown:go"]);
    assert.equal(claims.has("event-go-unknown:go"), false);
    assert.equal(claims.has("event-go-unknown:return"), true);
  });
});

test("strict readback after an unknown Composio create does not reuse cached pre-write events", async () => {
  const { makeComposioCalendar } = require("./transport/calendar-composio.js");
  const { makeCachedCalendar } = require("./calendar-cache.js");
  await withTravelClaimStore(async ({ claims, deletes }) => {
    const nowMs = Date.parse("2030-01-01T08:00:00+09:00");
    const original = {
      id: "event-cached-write", summary: "Meeting", location: "Venue",
      start: { dateTime: "2030-01-01T10:00:00+09:00" },
      end: { dateTime: "2030-01-01T11:00:00+09:00" },
    };
    const providerCalls = [];
    let listCalls = 0;
    let createArgs;
    const inner = makeComposioCalendar({
      apiKey: "fixture-key", supaUrl: "https://db.example", supaKey: "fixture-service",
      expectedCalendarAccountId: "ca-expected", recordCall: () => false,
      fetchImpl: async (input, init = {}) => {
        const url = new URL(String(input));
        if (url.hostname === "db.example") return { ok: true, status: 200, json: async () => [{
          uid: "tenant-cached", telegram_chat_id: null, calendar_provider: "composio_gcal",
          calendar_connected_account_id: "ca-expected",
        }] };
        if (url.pathname.endsWith("/connected_accounts/ca-expected")) return { ok: true, status: 200, json: async () => ({
          id: "ca-expected", user_id: "tenant-cached", toolkit_slug: "googlecalendar", status: "ACTIVE",
        }) };
        const body = JSON.parse(init.body);
        providerCalls.push(body);
        if (url.pathname.endsWith("/GOOGLECALENDAR_EVENTS_LIST")) {
          listCalls++;
          const items = [original];
          if (listCalls > 1 && createArgs) {
            const startMs = Date.parse(createArgs.start.dateTime);
            const endMs = Date.parse(createArgs.end.dateTime);
            items.push({ id: "created-after-write", summary: createArgs.summary, location: createArgs.location,
              description: createArgs.description,
              start: { dateTime: new Date(startMs).toISOString() },
              end: { dateTime: new Date(endMs).toISOString() },
              reminders: createArgs.reminders });
          }
          return { ok: true, status: 200, json: async () => ({ successful: true, data: { items } }) };
        }
        createArgs = body.body;
        return { ok: true, status: 200, json: async () => ({ successful: false, error: "unconfirmed create" }) };
      },
    });
    const calendar = makeCachedCalendar(inner, { ttlMs: 300_000, now: () => nowMs });
    const result = await fillTravel("tenant-cached", {
      home: "Home", mapsKey: "fixture", nowMs, calendar, supaUrl: "https://db.example", supaKey: "fixture",
      expectedCalendarAccountId: "ca-expected",
      _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => isReturn ? null : 20,
    });
    assert.equal(result.verified, 1);
    assert.equal(result.inserted, 0);
    assert.equal(listCalls, 2, "unknown write invalidates the cached pre-write event list before strict readback");
    assert.ok(providerCalls.every((body) => body.connected_account_id === "ca-expected"), "read and write stay pinned to Task 6's account");
    assert.equal(claims.has("event-cached-write:go"), true);
    assert.deepEqual(deletes, []);
  });
});
