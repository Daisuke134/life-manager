"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");

const { runAniccaCarouselCanary } = require("./anicca-larry-ja-canary.js");

test("production canary rejects a wall-clock slot before the first JST slot", async () => {
  const offSchedule = "2026-10-08T15:04:52.789Z"; // 2026-10-09 00:04 JST
  await assert.rejects(
    runAniccaCarouselCanary(["run-en-affirmation-production", "--slot", offSchedule], {
      env: {},
      now: () => offSchedule,
    }),
    (error) => error && error.code === "OFF_SCHEDULE_SLOT",
  );
});

test("production canary rejects execution time when a configured slot is already due", async () => {
  const now = "2026-10-08T01:05:00.000Z"; // 10:05 JST; canonical slot is 10:00 JST
  await assert.rejects(
    runAniccaCarouselCanary(["run-en-affirmation-production", "--slot", now], {
      env: {},
      now: () => now,
    }),
    (error) => error && error.code === "OFF_SCHEDULE_SLOT",
  );
});

test("production canary accepts an earlier configured slot today for catch-up", async () => {
  const missedSlot = "2026-10-08T00:15:00.000Z"; // 09:15 JST
  const now = "2026-10-08T06:20:00.000Z"; // 15:20 JST; the 14:15 slot is now latest.
  await assert.rejects(
    runAniccaCarouselCanary(["run-en-affirmation-tiktok-production", "--slot", missedSlot], {
      env: {},
      now: () => now,
    }),
    (error) => error && error.code !== "OFF_SCHEDULE_SLOT" && /LM_DATA_DIR/.test(error.message),
  );
});

test("direct production canary CLI requires the rotating slot and daily fences", () => {
  const script = path.join(__dirname, "anicca-larry-ja-canary.js");
  const slot = "2026-10-08T15:04:52.789Z";
  const result = spawnSync(process.execPath, [
    script,
    "run-en-affirmation-production",
    "--slot",
    slot,
  ], { encoding: "utf8", timeout: 5000, env: { PATH: process.env.PATH } });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /rotating runner/i);
});
