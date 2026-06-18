// TDD (RED first) for planner.js pure logic — schedules calls at 15/10/5 before LEAVE time.
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const P = require("../planner");

test("toneFor escalates: 15=calm, 10=firm, 5=harsh", () => {
  assert.equal(P.toneFor(15), "calm");
  assert.equal(P.toneFor(10), "firm");
  assert.equal(P.toneFor(5), "harsh");
});

test("isTravel detects 🚆移動 / [Travel] blocks", () => {
  assert.equal(P.isTravel("🚆 移動 自宅→大崎"), true);
  assert.equal(P.isTravel("[Travel] MUIT"), true);
  assert.equal(P.isTravel("MUIT 出社"), false);
});

test("leaveTimeMs = the travel block ending at the event start (travel included), else event start", () => {
  const ev = { id: "e1", summary: "MUIT", start: { dateTime: "2026-06-18T10:00:00+09:00" } };
  const block = { id: "t1", summary: "🚆 移動 自宅→大崎", start: { dateTime: "2026-06-18T09:30:00+09:00" }, end: { dateTime: "2026-06-18T10:00:00+09:00" } };
  // with a matching travel block → leave = 09:30
  assert.equal(P.leaveTimeMs(ev, [ev, block]), Date.parse("2026-06-18T09:30:00+09:00"));
  // no travel block → leave = the event start itself (e.g. 起床/就寝 at home)
  assert.equal(P.leaveTimeMs(ev, [ev]), Date.parse("2026-06-18T10:00:00+09:00"));
});

test("safeName makes a deterministic ascii-safe job slug", () => {
  assert.match(P.safeName("MUIT 出社 #5"), /^[A-Za-z0-9-]+$/);
});
