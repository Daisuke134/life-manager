// V1 MENTAL still reads a lookback window so the shared event cache remains truthful, but the
// production message selector receives only opaque timing intervals. Event titles, locations,
// attendees, and derived "important/intense" judgments are not mental inputs.
"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
process.env.SUPABASE_URL = process.env.SUPABASE_URL || "https://db.example";
process.env.SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "service";
const scheduler = require("../scheduler.js");

const NOW = Date.parse("2026-07-26T00:00:00Z");
const USER = { uid: "u-look", telegram_chat_id: "1", phone: "+81", call_enabled: false, notifications_enabled: true };
// a 110-min block that ended 10 min ago: exactly what between_events needs to see
const ENDED = { summary: "deep work", location: null, startMs: NOW - 120 * 60000, endMs: NOW - 10 * 60000, startIso: "x", endIso: "y" };
const FUTURE = { summary: "later", location: "渋谷", startMs: NOW + 3 * 3600000, endMs: NOW + 4 * 3600000, startIso: "f", endIso: "g" };

function deps(overrides = {}) {
  return {
    recordDailyPoll: async () => true,
    ...overrides,
  };
}

test("the tick fetch asks for a lookback window at least as wide as the trough", async () => {
  let opts = null;
  await scheduler.wakeUserOnce(USER, NOW, {
    ...deps(),
    fetchUpcomingEvents: async (_uid, o) => { opts = o; return []; },
    mental: async () => null,
    lateNotice: async () => null,
  });
  assert.ok(opts, "fetchUpcomingEvents was called");
  assert.ok(opts.lookbackMs >= 30 * 60000, `lookbackMs must cover TROUGH_AFTER_MS, got ${opts.lookbackMs}`);
});

test("MENTAL sees timing intervals without event-story judgments; late-notice sees only the future", async () => {
  let mentalEvents = null, lateEvents = null;
  await scheduler.wakeUserOnce(USER, NOW, {
    ...deps(),
    fetchUpcomingEvents: async () => [ENDED, FUTURE],
    lateNotice: async (_u, _n, d) => { lateEvents = d.events; return null; },
    // mentalDeps hands events to the organ via its own fetchUpcomingEvents closure (already shaped)
    mental: async (_u, _n, d) => { mentalEvents = await d.fetchUpcomingEvents(); return null; },
  });
  assert.ok(Array.isArray(mentalEvents), "mental received events");
  assert.equal(mentalEvents.length, 2, "mental sees ended + future");
  const endedShaped = mentalEvents.find((e) => e.endMs === ENDED.endMs);
  assert.ok(endedShaped, "the ended block reaches MENTAL");
  assert.equal(endedShaped.important, undefined, "V1 does not derive event importance");
  assert.equal(endedShaped.intense, undefined, "V1 does not derive event intensity");
  assert.equal(endedShaped.location, undefined, "V1 does not pass event location");
  assert.ok(Array.isArray(lateEvents), "lateNotice received events");
  assert.equal(lateEvents.length, 1, "lateNotice keeps the strict-future list");
  assert.equal(lateEvents[0].startMs, FUTURE.startMs);
});
