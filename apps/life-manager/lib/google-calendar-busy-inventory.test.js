"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  inspectGoogleCalendarBusyInventory,
  isVerifiedGoogleCalendarBusyInventory,
} = require("./google-calendar-busy-inventory.js");

const WINDOW = Object.freeze({
  timeMin: "2026-08-02T00:00:00+09:00",
  timeMax: "2026-08-23T00:00:00+09:00",
  timeZone: "Asia/Tokyo",
  now: "2026-08-02T01:00:00.000Z",
});

function transport(overrides = {}) {
  return {
    async listCalendarsRaw() {
      return [{ id: "primary" }, { id: "work" }, { id: "school" }];
    },
    async listAllEventsRaw() {
      return [
        {
          CalendarID: "work", id: "meeting-1", status: "confirmed", summary: "Private meeting",
          location: "Private office", start: { dateTime: "2026-08-05T09:00:00+09:00" },
          end: { dateTime: "2026-08-05T10:00:00+09:00" },
        },
        {
          CalendarID: "school", id: "all-day-1", status: "confirmed", summary: "Private all day",
          start: { date: "2026-08-06" }, end: { date: "2026-08-07" },
        },
        {
          CalendarID: "primary", id: "free-1", status: "confirmed", transparency: "transparent",
          start: { dateTime: "2026-08-05T11:00:00+09:00" }, end: { dateTime: "2026-08-05T12:00:00+09:00" },
        },
        {
          CalendarID: "primary", id: "cancelled-1", status: "cancelled",
          start: { dateTime: "2026-08-05T13:00:00+09:00" }, end: { dateTime: "2026-08-05T14:00:00+09:00" },
        },
      ];
    },
    ...overrides,
  };
}

test("reads every calendar and emits reference-only timed and all-day busy intervals", async () => {
  const calls = [];
  const base = transport();
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: {
      async listCalendarsRaw(options) { calls.push(["calendars", options]); return base.listCalendarsRaw(); },
      async listAllEventsRaw(uid, options) { calls.push(["events", uid, options]); return base.listAllEventsRaw(); },
    },
  });
  assert.equal(result.calendar_count, 3);
  assert.equal(result.source_event_count, 4);
  assert.equal(result.busy_event_count, 2);
  assert.equal(result.excluded_event_count, 2);
  assert.equal(result.busy_intervals[0].kind, "timed");
  assert.equal(result.busy_intervals[0].start_at, "2026-08-05T00:00:00.000Z");
  assert.equal(result.busy_intervals[0].end_at, "2026-08-05T01:00:00.000Z");
  assert.equal(result.busy_intervals[1].kind, "all_day");
  assert.equal(result.busy_intervals[1].start_date, "2026-08-06");
  assert.equal(result.busy_intervals[1].end_date, "2026-08-07");
  assert.match(result.busy_intervals[0].calendar_ref, /^calendar-evidence:\/\/google\/calendar\/[0-9a-f]{64}$/);
  assert.match(result.busy_intervals[0].event_ref, /^calendar-evidence:\/\/google\/event\/[0-9a-f]{64}$/);
  assert.doesNotMatch(JSON.stringify(result), /primary|work|school|meeting-1|Private meeting|Private office/);
  assert.equal(isVerifiedGoogleCalendarBusyInventory(result), true);
  assert.equal(isVerifiedGoogleCalendarBusyInventory(structuredClone(result)), false);
  assert.deepEqual(calls, [
    ["calendars", { strict: true }],
    ["events", "dais-local", {
      timeMin: WINDOW.timeMin, timeMax: WINDOW.timeMax, maxResults: 2500, strict: true,
    }],
  ]);
});

test("real-shaped Life Manager travel block (marker summary + auto-insert description) is excluded", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [
          {
            CalendarID: "primary", id: "travel-1", status: "confirmed",
            summary: "[Travel] 🚆 新宿区南元町15-27→KOPI KALYAN Tokyo（コピカリアン トーキョー）",
            description: "Auto-inserted by Life Manager — adjust if the route is wrong.",
            start: { dateTime: "2026-08-05T08:00:00+09:00" }, end: { dateTime: "2026-08-05T08:30:00+09:00" },
          },
        ];
      },
    }),
  });
  assert.equal(result.source_event_count, 1);
  assert.equal(result.busy_event_count, 0);
  assert.equal(result.excluded_event_count, 1);
});

test("summary matches the travel marker but description is missing/different — stays busy", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [
          {
            CalendarID: "primary", id: "not-travel-1", status: "confirmed",
            summary: "[Travel] 🚆 新宿区南元町15-27→KOPI KALYAN Tokyo（コピカリアン トーキョー）",
            start: { dateTime: "2026-08-05T08:00:00+09:00" }, end: { dateTime: "2026-08-05T08:30:00+09:00" },
          },
          {
            CalendarID: "primary", id: "not-travel-2", status: "confirmed",
            summary: "[Travel] 🚆 新宿区南元町15-27→KOPI KALYAN Tokyo（コピカリアン トーキョー）",
            description: "Some other note",
            start: { dateTime: "2026-08-05T09:00:00+09:00" }, end: { dateTime: "2026-08-05T09:30:00+09:00" },
          },
        ];
      },
    }),
  });
  assert.equal(result.source_event_count, 2);
  assert.equal(result.busy_event_count, 2);
  assert.equal(result.excluded_event_count, 0);
});

test("description matches the auto-insert sentence but summary is a normal title — stays busy", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [
          {
            CalendarID: "primary", id: "not-travel-3", status: "confirmed",
            summary: "Team standup",
            description: "Auto-inserted by Life Manager — adjust if the route is wrong.",
            start: { dateTime: "2026-08-05T08:00:00+09:00" }, end: { dateTime: "2026-08-05T08:30:00+09:00" },
          },
        ];
      },
    }),
  });
  assert.equal(result.source_event_count, 1);
  assert.equal(result.busy_event_count, 1);
  assert.equal(result.excluded_event_count, 0);
});

test("a normal event with neither travel signal is unaffected", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [
          {
            CalendarID: "primary", id: "normal-1", status: "confirmed", summary: "Dentist",
            start: { dateTime: "2026-08-05T08:00:00+09:00" }, end: { dateTime: "2026-08-05T08:30:00+09:00" },
          },
        ];
      },
    }),
  });
  assert.equal(result.busy_event_count, 1);
  assert.equal(result.excluded_event_count, 0);
});

test("an event Dais (self) declined is excluded, even though Google still returns it", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [
          {
            CalendarID: "primary", id: "declined-1", status: "confirmed", summary: "Optional sync",
            start: { dateTime: "2026-08-05T09:00:00+09:00" }, end: { dateTime: "2026-08-05T10:00:00+09:00" },
            attendees: [
              { email: "someone@example.com", responseStatus: "accepted" },
              { email: "keiodaisuke@gmail.com", self: true, responseStatus: "declined" },
            ],
          },
        ];
      },
    }),
  });
  assert.equal(result.busy_event_count, 0);
  assert.equal(result.excluded_event_count, 1);
});

test("an event Dais (self) accepted, or has not responded to, stays busy", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [
          {
            CalendarID: "primary", id: "accepted-1", status: "confirmed",
            start: { dateTime: "2026-08-05T09:00:00+09:00" }, end: { dateTime: "2026-08-05T10:00:00+09:00" },
            attendees: [{ email: "keiodaisuke@gmail.com", self: true, responseStatus: "accepted" }],
          },
          {
            CalendarID: "primary", id: "needs-action-1", status: "confirmed",
            start: { dateTime: "2026-08-05T11:00:00+09:00" }, end: { dateTime: "2026-08-05T12:00:00+09:00" },
            attendees: [{ email: "keiodaisuke@gmail.com", self: true, responseStatus: "needsAction" }],
          },
        ];
      },
    }),
  });
  assert.equal(result.busy_event_count, 2);
  assert.equal(result.excluded_event_count, 0);
});

test("another attendee declining never frees Dais's own event", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [
          {
            CalendarID: "primary", id: "guest-declined-1", status: "confirmed",
            start: { dateTime: "2026-08-05T09:00:00+09:00" }, end: { dateTime: "2026-08-05T10:00:00+09:00" },
            attendees: [
              { email: "keiodaisuke@gmail.com", self: true, responseStatus: "accepted" },
              { email: "someone@example.com", responseStatus: "declined" },
            ],
          },
        ];
      },
    }),
  });
  assert.equal(result.busy_event_count, 1);
  assert.equal(result.excluded_event_count, 0);
});

test("a personal event with no attendees array is unaffected by the declined check", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [
          {
            CalendarID: "primary", id: "solo-1", status: "confirmed",
            start: { dateTime: "2026-08-05T09:00:00+09:00" }, end: { dateTime: "2026-08-05T10:00:00+09:00" },
          },
        ];
      },
    }),
  });
  assert.equal(result.busy_event_count, 1);
});

test("a malformed attendees value fails closed", async () => {
  await assert.rejects(inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [{
          CalendarID: "primary", id: "malformed-1", status: "confirmed",
          start: { dateTime: "2026-08-05T09:00:00+09:00" }, end: { dateTime: "2026-08-05T10:00:00+09:00" },
          attendees: "not-an-array",
        }];
      },
    }),
  }), /calendar busy inventory invalid/i);
});

test("no title or description ever appears on a returned busy interval, travel or otherwise", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listAllEventsRaw() {
        return [
          {
            CalendarID: "primary", id: "kept-1", status: "confirmed", summary: "Secret meeting title",
            description: "Secret meeting notes",
            start: { dateTime: "2026-08-05T08:00:00+09:00" }, end: { dateTime: "2026-08-05T08:30:00+09:00" },
          },
        ];
      },
    }),
  });
  assert.equal(result.busy_intervals.length, 1);
  assert.deepEqual(Object.keys(result.busy_intervals[0]).sort(), ["calendar_ref", "end_at", "event_ref", "kind", "start_at"]);
  assert.doesNotMatch(JSON.stringify(result), /Secret meeting/);
});

test("empty calendars are valid only when both exhaustive reads succeed", async () => {
  const result = await inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({
      async listCalendarsRaw() { return []; },
      async listAllEventsRaw() { return []; },
    }),
  });
  assert.equal(result.calendar_count, 0);
  assert.equal(result.source_event_count, 0);
  assert.equal(result.busy_event_count, 0);
});

test("unknown calendars, duplicate events, malformed intervals, and provider errors fail closed", async () => {
  const cases = [
    [{ CalendarID: "unknown", id: "e", status: "confirmed", start: { dateTime: "2026-08-05T09:00:00+09:00" }, end: { dateTime: "2026-08-05T10:00:00+09:00" } }],
    [
      { CalendarID: "work", id: "e", status: "confirmed", start: { dateTime: "2026-08-05T09:00:00+09:00" }, end: { dateTime: "2026-08-05T10:00:00+09:00" } },
      { CalendarID: "work", id: "e", status: "confirmed", start: { dateTime: "2026-08-05T11:00:00+09:00" }, end: { dateTime: "2026-08-05T12:00:00+09:00" } },
    ],
    [{ CalendarID: "work", id: "e", status: "confirmed", start: { dateTime: "bad" }, end: { dateTime: "also-bad" } }],
  ];
  for (const events of cases) await assert.rejects(inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({ async listAllEventsRaw() { return events; } }),
  }), /calendar busy inventory invalid/i);
  await assert.rejects(inspectGoogleCalendarBusyInventory({
    ...WINDOW,
    calendar: transport({ async listCalendarsRaw() { throw new Error("provider down"); } }),
  }), /calendar busy inventory unavailable/i);
});
