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
  assert.doesNotMatch(sql, /GRANT EXECUTE[\s\S]*(anon|authenticated)/i);
});

function periodSummarySql() {
  const migrationPath = path.join(__dirname,
    "../migrations/2026-10-07-lm-usage-cost-period-summary.sql");
  assert.ok(fs.existsSync(migrationPath), "COST-02 period-summary migration is missing");
  return fs.readFileSync(migrationPath, "utf8");
}

function periodSummaryColumns(sql) {
  const match = sql.match(/RETURNS TABLE\s*\(([\s\S]*?)\)\s*LANGUAGE/i);
  assert.ok(match, "COST-02 must declare a table result");
  return match[1];
}

test("COST-02 period summary is bounded to one tenant and a half-open period", () => {
  const sql = periodSummarySql();
  assert.match(sql, /CREATE OR REPLACE FUNCTION public\.lm_usage_cost_period_summary\s*\(\s*p_period_start timestamptz,\s*p_period_end timestamptz,\s*p_tenant_id text\s*\)/i);
  assert.match(sql, /kind\s*=\s*'provider_usage'/i);
  assert.match(sql, /uid\s*=\s*p_tenant_id/i);
  assert.match(sql, /ts\s*>=\s*p_period_start/i);
  assert.match(sql, /ts\s*<\s*p_period_end/i);
  assert.doesNotMatch(sql, /p_tenant_id\s+IS\s+NULL|OR\s+uid\s*=\s*p_tenant_id/i);
});

test("COST-02 groups provider, SKU, and operation with event, request, cache, and unit counts", () => {
  const sql = periodSummarySql();
  const columns = periodSummaryColumns(sql);
  for (const field of ["provider", "sku", "operation", "event_count", "request_count",
    "cache_hit_count", "cache_miss_count", "provider_units"]) {
    assert.match(columns, new RegExp(`\\b${field}\\b`, "i"));
  }
  assert.match(sql, /meta\s*->>\s*'provider'/i);
  assert.match(sql, /meta\s*->>\s*'sku'/i);
  assert.match(sql, /meta\s*->>\s*'operation'/i);
  assert.match(sql, /GROUP BY[\s\S]*provider[\s\S]*sku[\s\S]*operation/i);
  assert.match(sql, /sum\(quantity\)/i);
  assert.match(sql, /cache_hit/i);
});

test("COST-02 keeps unknown costs nullable and separates settled, unknown, and not-applicable events", () => {
  const sql = periodSummarySql();
  const columns = periodSummaryColumns(sql);
  for (const field of ["estimated_cost_usd", "settled_cost_usd", "unknown_estimate_event_count",
    "unknown_actual_event_count", "not_applicable_count"]) {
    assert.match(columns, new RegExp(`\\b${field}\\b`, "i"));
  }
  assert.match(sql, /sum\(est_usd\)\s+FILTER\s*\(\s*WHERE/i);
  assert.doesNotMatch(sql, /COALESCE\s*\(\s*sum\(est_usd\)/i);
  assert.match(sql, /sum\(actual_usd\)\s+FILTER\s*\(\s*WHERE[\s\S]*billing_status\s*=\s*'settled'[\s\S]*actual_usd\s*>=\s*0/i);
  assert.match(sql, /jsonb_typeof\(meta\s*->\s*'actual_usd'\)\s*=\s*'number'/i);
  assert.match(sql, /estimate_status/i);
  assert.match(sql, /billing_status/i);
  assert.match(sql, /settled/i);
  assert.match(sql, /unknown_estimate_event_count[\s\S]*unavailable|unavailable[\s\S]*unknown_estimate_event_count/i);
  assert.match(sql, /unknown_actual_event_count[\s\S]*billing_status|billing_status[\s\S]*unknown_actual_event_count/i);
  assert.match(sql, /not_applicable_count[\s\S]*not_applicable|not_applicable[\s\S]*not_applicable_count/i);
});

test("COST-02 RPC is executable only by service_role and leaves COST-01 intact", () => {
  const sql = periodSummarySql();
  assert.match(sql, /REVOKE ALL ON FUNCTION public\.lm_usage_cost_period_summary\(timestamptz, timestamptz, text\)\s+FROM PUBLIC, anon, authenticated/i);
  assert.match(sql, /GRANT EXECUTE ON FUNCTION public\.lm_usage_cost_period_summary\(timestamptz, timestamptz, text\)\s+TO service_role/i);
  assert.doesNotMatch(sql, /GRANT EXECUTE[\s\S]*(anon|authenticated)/i);
  assert.doesNotMatch(sql, /DROP FUNCTION[^;]*lm_usage_cost_summary/i);
});
