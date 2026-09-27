"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { selectSlidePack } = require("./marketing-slide-pack-rotation.js");

const NOW = "2026-09-28T10:00:00.000Z";

function pack(id, familyId, createdAt = "2026-09-01T00:00:00.000Z") {
  return { packRef: `object://sha256/${id.padEnd(64, "0")}`, mediaRefs: [], captionRef: `object://sha256/${id}c`.padEnd(64, "0"), approvalRef: `object://sha256/${id}a`.padEnd(64, "0"), familyId, createdAt };
}

test("selectSlidePack picks an unposted candidate when nothing has ever posted", () => {
  const candidates = [pack("1", "hook-question"), pack("2", "listicle")];
  const picked = selectSlidePack({ candidates, postedHistory: [], metrics: [], now: NOW });
  assert.ok(picked);
  assert.equal(candidates.some((c) => c.packRef === picked.packRef), true);
});

test("selectSlidePack never repeats a pack posted within minDaysBetweenRepeat", () => {
  const a = pack("1", "hook-question");
  const b = pack("2", "listicle");
  const postedHistory = [{ packRef: a.packRef, postedAt: "2026-09-27T10:00:00.000Z" }];
  const picked = selectSlidePack({ candidates: [a, b], postedHistory, metrics: [], minDaysBetweenRepeat: 7, now: NOW });
  assert.equal(picked.packRef, b.packRef);
});

test("selectSlidePack returns a repeat once minDaysBetweenRepeat has elapsed", () => {
  const a = pack("1", "hook-question");
  const postedHistory = [{ packRef: a.packRef, postedAt: "2026-09-01T00:00:00.000Z" }];
  const picked = selectSlidePack({ candidates: [a], postedHistory, metrics: [], minDaysBetweenRepeat: 7, now: NOW });
  assert.equal(picked.packRef, a.packRef);
});

test("selectSlidePack returns null when every candidate was posted too recently", () => {
  const a = pack("1", "hook-question");
  const postedHistory = [{ packRef: a.packRef, postedAt: "2026-09-28T09:00:00.000Z" }];
  const picked = selectSlidePack({ candidates: [a], postedHistory, metrics: [], minDaysBetweenRepeat: 7, now: NOW });
  assert.equal(picked, null);
});

test("selectSlidePack deprioritizes families that scored below the metrics median (explore/exploit)", () => {
  const strong = pack("1", "hook-question");
  const weak = pack("2", "myth-vs-fact");
  const metrics = [
    { familyId: "hook-question", score: 90 },
    { familyId: "hook-question", score: 80 },
    { familyId: "myth-vs-fact", score: 10 },
    { familyId: "myth-vs-fact", score: 5 },
  ];
  const picked = selectSlidePack({ candidates: [weak, strong], postedHistory: [], metrics, now: NOW });
  assert.equal(picked.packRef, strong.packRef);
});

test("selectSlidePack explores an unused family before repeating an above-median one that already posted", () => {
  const used = pack("1", "hook-question");
  const unused = pack("2", "listicle");
  const postedHistory = [{ packRef: used.packRef, postedAt: "2026-09-01T00:00:00.000Z" }];
  const metrics = [{ familyId: "hook-question", score: 90 }, { familyId: "listicle", score: 90 }];
  const picked = selectSlidePack({ candidates: [used, unused], postedHistory, metrics, minDaysBetweenRepeat: 1, now: NOW });
  assert.equal(picked.packRef, unused.packRef);
});

test("selectSlidePack is deterministic given the same snapshot (slot-retry idempotency support)", () => {
  const candidates = [pack("1", "a"), pack("2", "b"), pack("3", "c")];
  const first = selectSlidePack({ candidates, postedHistory: [], metrics: [], now: NOW });
  const second = selectSlidePack({ candidates, postedHistory: [], metrics: [], now: NOW });
  assert.equal(first.packRef, second.packRef);
});

test("selectSlidePack rejects a non-array candidates argument", () => {
  assert.throws(() => selectSlidePack({ candidates: null, now: NOW }), /candidates/);
});

test("selectSlidePack rejects an invalid clock", () => {
  assert.throws(() => selectSlidePack({ candidates: [], now: "not-a-date" }), /clock/);
});
