"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
  parseWriterStartPayload,
  bindWriterAttribution,
} = require("./writer-attribution.js");

test("writer attribution accepts only a deterministic 32-hex Telegram start token", () => {
  assert.equal(
    parseWriterStartPayload("/start wr_0123456789abcdef0123456789abcdef"),
    "0123456789abcdef0123456789abcdef",
  );
  assert.equal(parseWriterStartPayload("/start lp"), null);
  assert.equal(parseWriterStartPayload("/start wr_not-a-token"), null);
  assert.equal(parseWriterStartPayload("/startfoo wr_123e4567-e89b-12d3-a456-426614174000"), null);
});

test("writer attribution binding is idempotent and tenant scoped", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 204 };
  };

  assert.equal(
    await bindWriterAttribution(
      "tenant-1", "0123456789abcdef0123456789abcdef",
      "https://supabase.example", "service-key", fetchImpl,
    ),
    true,
  );
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /lm_users\?uid=eq\.tenant-1&writer_attribution_ref=is\.null$/);
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    writer_attribution_ref: "0123456789abcdef0123456789abcdef",
  });
  assert.equal(calls[0].options.method, "PATCH");
});

test("migration adds an optional indexed tenant attribution key", () => {
  const sql = fs.readFileSync(path.resolve(__dirname, "../migrations/2026-09-19-writer-attribution-token.sql"), "utf8");
  assert.match(sql, /ADD COLUMN IF NOT EXISTS writer_attribution_ref text/i);
  assert.match(sql, /CREATE INDEX IF NOT EXISTS lm_users_writer_attribution_ref_idx/i);
});
