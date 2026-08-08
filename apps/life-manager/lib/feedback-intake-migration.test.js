"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");


test("feedback migration is service-only and has no raw identity/content columns", () => {
  const sql = fs.readFileSync(
    path.join(__dirname, "../migrations/2026-07-24-lm-feedback-intake.sql"),
    "utf8",
  );
  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.lm_feedback_intake/i);
  assert.match(sql, /UNIQUE\s*\(source_ref\)/i);
  assert.match(sql, /REVOKE ALL ON TABLE public\.lm_feedback_intake FROM PUBLIC/i);
  assert.match(sql, /REVOKE ALL ON SEQUENCE public\.lm_feedback_intake_id_seq FROM PUBLIC/i);
  assert.doesNotMatch(sql, /\b(raw_text|chat_id|telegram_chat_id|user_id|uid|actor_id|email|phone)\b/i);
});


test("product-learning migration requires all issue evidence fields together", () => {
  const sql = fs.readFileSync(
    path.join(__dirname, "../migrations/2026-08-07-lm-feedback-product-learning.sql"),
    "utf8",
  );
  for (const field of [
    "source_event_id",
    "user_segment",
    "opportunity",
    "desired_outcome",
    "evidence",
    "proposed_assumption_test",
    "success_metric",
  ]) assert.match(sql, new RegExp(`\\b${field}\\b`));
  assert.match(sql, /lm_feedback_intake_product_learning_complete/i);
  assert.doesNotMatch(sql, /\b(raw_text|chat_id|telegram_chat_id|user_id|uid|actor_id|email|phone)\b/i);
});
