"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const SQL = fs.readFileSync(path.join(__dirname, "../migrations/2026-09-18-lm-mental-message-family.sql"), "utf8");

test("V1 mental receipt migration is additive, idempotent, and closes family/window values", () => {
  assert.match(SQL, /ADD COLUMN IF NOT EXISTS family/);
  assert.match(SQL, /ADD COLUMN IF NOT EXISTS template_id/);
  assert.match(SQL, /ADD COLUMN IF NOT EXISTS local_day/);
  assert.match(SQL, /ADD COLUMN IF NOT EXISTS ["']?window["']?\s+text/);
  assert.match(SQL, /UPDATE public\.lm_mental_send_log/);
  assert.match(SQL, /lm_mental_send_log_family_check/);
  assert.match(SQL, /lm_mental_send_log_window_check/);
  assert.match(SQL, /morning_orientation/);
  assert.match(SQL, /midday_awareness/);
  assert.match(SQL, /evening_direction/);
  assert.match(SQL, /IF NOT EXISTS \(SELECT 1 FROM pg_constraint/);
  assert.match(SQL, /CREATE INDEX IF NOT EXISTS/);
});
