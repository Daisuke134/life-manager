"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

test("COST-01 migration exposes bounded daily tenant/provider/feature aggregates", () => {
  const sql = fs.readFileSync(path.join(__dirname,
    "../migrations/2026-09-06-lm-usage-cost-summary.sql"), "utf8");
  assert.match(sql, /CREATE OR REPLACE FUNCTION public\.lm_usage_cost_summary/i);
  assert.match(sql, /date_trunc\('day',\s*ts\)/i);
  assert.match(sql, /meta->>'provider'/i);
  assert.match(sql, /meta->>'feature'/i);
  assert.match(sql, /meta->>'outcome'/i);
  assert.match(sql, /meta->>'failure_class'/i);
  assert.match(sql, /meta->>'cache_hit'/i);
  assert.match(sql, /kind = 'provider_usage'/i);
  assert.match(sql, /GRANT EXECUTE[\s\S]*service_role/i);
  assert.ok(sql.split("\n").filter((line) => /^GRANT EXECUTE/i.test(line))
    .every((line) => !/(anon|authenticated)/i.test(line)));
  assert.match(sql, /CREATE OR REPLACE FUNCTION public\.lm_provider_budget_summary/i);
  assert.match(sql, /cache_hits/i);
  assert.match(sql, /unknown_count/i);
});

test("provider lane migration exposes tenant-bound unknown-cost readback", () => {
  const sql = fs.readFileSync(path.join(__dirname,
    "../migrations/2026-10-03-lm-provider-lane-summary.sql"), "utf8");
  assert.match(sql, /CREATE OR REPLACE FUNCTION public\.lm_provider_lane_summary/i);
  assert.match(sql, /p_tenant_id\s+text/i);
  assert.match(sql, /unknown_count/i);
  assert.match(sql, /meta->>'actual_status'/i);
  assert.match(sql, /GRANT EXECUTE[\s\S]*service_role/i);
  assert.ok(sql.split("\n").filter((line) => /^GRANT EXECUTE/i.test(line))
    .every((line) => !/(anon|authenticated)/i.test(line)));
});
