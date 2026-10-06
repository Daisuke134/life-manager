"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

test("geocode migration restricts its table without revoking shared private-schema access", () => {
  const sql = fs.readFileSync(path.join(__dirname,
    "../migrations/2026-10-06-lm-geocode-cache.sql"), "utf8");

  assert.doesNotMatch(sql,
    /REVOKE\s+ALL\s+ON\s+SCHEMA\s+private\s+FROM[^;]*\bservice_role\b/i);
  assert.match(sql,
    /REVOKE\s+ALL\s+ON\s+TABLE\s+private\.lm_geocode_cache\s+FROM\s+PUBLIC,\s*anon,\s*authenticated,\s*service_role/i);
  assert.match(sql, /GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.lm_geocode_cache_get[\s\S]*?TO\s+service_role/i);
  assert.match(sql, /GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.lm_geocode_cache_upsert[\s\S]*?TO\s+service_role/i);
});
