// TDD for the NOTIFY motion-gate: late = (travel start passed + GRACE) AND not already moved.
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const N = require("../notify");

const T = 1_000_000_000_000; // an arbitrary travel-start instant

test("not late the instant the travel block starts (grace window)", () => {
  assert.equal(N.isLateRisk({ travelStartMs: T, nowMs: T + 60_000, graceMs: 5 * 60_000 }), false);
});

test("late only after the grace window passes", () => {
  assert.equal(N.isLateRisk({ travelStartMs: T, nowMs: T + 6 * 60_000, graceMs: 5 * 60_000 }), true);
});

test("never late if the user already moved (left home)", () => {
  assert.equal(N.isLateRisk({ travelStartMs: T, nowMs: T + 60 * 60_000, graceMs: 5 * 60_000, moved: true }), false);
});

test("extractApproval accepts a realistic vocab (EN+JA), not just ok/はい", () => {
  for (const yes of ["OK", "yes please", "go", "sure send it", "了解", "承知しました", "送って", "お願いします"]) {
    assert.equal(N.extractApproval(yes), true, `should approve: ${yes}`);
  }
  for (const no of ["no", "wait", "あとで", "ダメ"]) {
    assert.equal(N.extractApproval(no), false, `should NOT approve: ${no}`);
  }
});
