"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const SQL = fs.readFileSync(path.join(__dirname, "../migrations/2026-09-18-lm-mental-message-family.sql"), "utf8");
const DECISION_SQL_PATH = path.join(__dirname, "../migrations/2026-09-18-lm-mental-decision-log.sql");

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

test("mental decision migration stores closed send/silence provenance and replay keys", () => {
  const decisionSql = fs.readFileSync(DECISION_SQL_PATH, "utf8");
  assert.match(decisionSql, /CREATE TABLE IF NOT EXISTS public\.lm_mental_decision_log/);
  assert.match(decisionSql, /decision_key text NOT NULL UNIQUE/);
  assert.match(decisionSql, /candidate_quote_ids jsonb NOT NULL/);
  assert.match(decisionSql, /status IN \('planned', 'silence', 'delivered', 'send_failed'\)/);
  assert.match(decisionSql, /telegram_message_id text/);
  assert.match(decisionSql, /ALTER TABLE public\.lm_mental_decision_log ENABLE ROW LEVEL SECURITY/);
  assert.match(decisionSql, /CREATE INDEX IF NOT EXISTS/);
});

test("mental quiet-hours migration adds a bounded explicit per-user source", () => {
  const quietSql = fs.readFileSync(path.join(__dirname, "../migrations/2026-09-18-lm-mental-quiet-hours.sql"), "utf8");
  assert.match(quietSql, /ADD COLUMN IF NOT EXISTS mental_quiet_start_minute integer/);
  assert.match(quietSql, /ADD COLUMN IF NOT EXISTS mental_quiet_end_minute integer/);
  assert.match(quietSql, /mental_quiet_start_minute.*BETWEEN 0 AND 1440/s);
  assert.match(quietSql, /mental_quiet_end_minute.*BETWEEN 0 AND 1440/s);
  assert.match(quietSql, /mutate_lm_panel_preferences[\s\S]*mental_quiet_start_minute/);
});
