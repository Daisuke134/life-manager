"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  HONNE_JA_SLOTS,
  honneJaDueSlot,
  marketingVideoDaySlots,
  zonedSlotInstant,
  marketingVideoDueSlots,
} = require("./honne-ja-shadow-schedule.js");
const {
  buildMarketingVideoGenerationJob,
} = require("./marketing-video-generation-adapter.js");

// The legacy owner ai.anicca.reelclaw-honne-ja fires at StartCalendarInterval
// 12:30 and 21:30 local (verified read-only via plutil). A drift from that
// cadence must fail this suite, not ship silently.
test("shadow slots are exactly the legacy launchd cadence 12:30 and 21:30", () => {
  assert.deepEqual([...HONNE_JA_SLOTS], ["12:30", "21:30"]);
  assert.ok(Object.isFrozen(HONNE_JA_SLOTS));
});

test("before the first slot of the local day no slot is due", () => {
  // 2026-07-30T03:29:00Z = 12:29 JST
  assert.equal(honneJaDueSlot(Date.parse("2026-07-30T03:29:00Z")), null);
  // 2026-07-29T15:30:00Z = 2026-07-30 00:30 JST — a fresh local day, before 12:30
  assert.equal(honneJaDueSlot(Date.parse("2026-07-29T15:30:00Z")), null);
});

test("between 12:30 and 21:29 JST the due slot is today's 12:30 exact UTC instant", () => {
  assert.equal(
    honneJaDueSlot(Date.parse("2026-07-30T03:30:00Z")),
    "2026-07-30T03:30:00.000Z",
  );
  // 21:29 JST still belongs to the 12:30 slot
  assert.equal(
    honneJaDueSlot(Date.parse("2026-07-30T12:29:00Z")),
    "2026-07-30T03:30:00.000Z",
  );
});

test("from 21:30 JST to end of local day the due slot is today's 21:30 exact UTC instant", () => {
  assert.equal(
    honneJaDueSlot(Date.parse("2026-07-30T12:30:00Z")),
    "2026-07-30T12:30:00.000Z",
  );
  // 23:59 JST
  assert.equal(
    honneJaDueSlot(Date.parse("2026-07-30T14:59:00Z")),
    "2026-07-30T12:30:00.000Z",
  );
});

test("marketingVideoDueSlots enumerates all elapsed same-day slots in schedule order", () => {
  assert.deepEqual(
    marketingVideoDueSlots(Date.parse("2026-07-30T06:05:00Z"), "Asia/Tokyo", ["10:00", "15:00", "20:00"]),
    ["2026-07-30T01:00:00.000Z", "2026-07-30T06:00:00.000Z"],
  );
  assert.deepEqual(
    marketingVideoDueSlots(Date.parse("2026-07-29T15:05:00Z"), "Asia/Tokyo", ["10:00", "15:00", "20:00"]),
    [],
  );
});

test("marketingVideoDaySlots enumerates configured future slots on the same JST day", () => {
  assert.deepEqual(
    marketingVideoDaySlots(Date.parse("2026-10-10T08:55:00.000Z"), "Asia/Tokyo", ["08:00", "16:00", "22:37"]),
    ["2026-10-09T23:00:00.000Z", "2026-10-10T07:00:00.000Z", "2026-10-10T13:37:00.000Z"],
  );
});

test("the due slot instant satisfies the generation job's exact-instant contract", () => {
  const slot = honneJaDueSlot(Date.parse("2026-07-30T05:00:00Z"));
  const job = buildMarketingVideoGenerationJob({
    tenantId: "tenant-a",
    productId: "honne-ai",
    formatId: "reelclaw",
    locale: "ja",
    slot,
    packRef: `object://sha256/${"a".repeat(64)}`,
    mediaRefs: [`object://sha256/${"b".repeat(64)}`],
  });
  assert.equal(job.input_refs.slot_ref, `schedule-slot://${slot}`);
});

test("two ticks inside the same slot window resolve to the same instant (idempotent identity)", () => {
  assert.equal(
    honneJaDueSlot(Date.parse("2026-07-30T03:31:00Z")),
    honneJaDueSlot(Date.parse("2026-07-30T09:00:00Z")),
  );
});

test("time zone parameter is honoured, including zones with DST", () => {
  // 13:00 EDT (UTC-4) on 2026-07-30 → the 12:30 local slot = 16:30Z
  assert.equal(
    honneJaDueSlot(Date.parse("2026-07-30T17:00:00Z"), "America/New_York"),
    "2026-07-30T16:30:00.000Z",
  );
});

test("zonedSlotInstant rejects malformed slots and invalid clocks", () => {
  const clock = { year: 2026, month: 7, day: 30 };
  assert.throws(() => zonedSlotInstant(clock, "25:99", "Asia/Tokyo"), /slot/i);
  assert.throws(() => zonedSlotInstant(clock, "", "Asia/Tokyo"), /slot/i);
  assert.throws(() => honneJaDueSlot(Number.NaN), /time/i);
});
