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
  assert.equal(requests[0].bounds.timeMin, "2029-12-31T23:00:00Z");
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
    _directionsMinutes: async (_from, _to, _key, _anchor, _now, isReturn) => isReturn ? null : 20,
  });
  assert.equal(created.length, 1);
  assert.equal(eventReadOptions.expectedCalendarAccountId, "ca-expected");
  assert.equal(created[0].options.expectedCalendarAccountId, "ca-expected");
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
    calls, reads,
    async listEventsRaw(_uid, options) {
      reads.push(options);
      readCount++;
      return readCount === 1 ? [original] : readback(calls[0]?.args, original);
    },
    async createEvent(_uid, args, options) {
      calls.push({ args, options });
      return { successful: false, effect: "unknown" };
    },
  };
}

function createdTravelRow(args) {
  const startMs = Date.parse(`${args.start_datetime}Z`);
  const durationMs = (args.event_duration_hour * 60 + args.event_duration_minutes) * 60000;
  return {
    id: "travel-readback", summary: args.summary, location: args.location,
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
        const body = JSON.parse(init.body);
        providerCalls.push(body);
        if (url.pathname.endsWith("/GOOGLECALENDAR_EVENTS_LIST")) {
          listCalls++;
          const items = [original];
          if (listCalls > 1 && createArgs) {
            const startMs = Date.parse(createArgs.start.dateTime);
            const endMs = Date.parse(createArgs.end.dateTime);
            items.push({ id: "created-after-write", summary: createArgs.summary, location: createArgs.location,
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
