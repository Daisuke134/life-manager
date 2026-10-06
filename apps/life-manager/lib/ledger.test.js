"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ledgerPath = path.join(__dirname, "ledger.js");

function ledger() {
  assert.ok(fs.existsSync(ledgerPath), "lib/ledger.js must exist");
  delete require.cache[require.resolve(ledgerPath)];
  return require(ledgerPath);
}

test("LM-7 migration creates only the additive lm_api_cost ledger", () => {
  const sqlPath = path.join(__dirname, "../migrations/2026-07-18-lm-api-cost.sql");
  assert.ok(fs.existsSync(sqlPath), "LM-7 migration must exist");
  const sql = fs.readFileSync(sqlPath, "utf8").replace(/\s+/g, " ").trim().toLowerCase();
  assert.match(sql, /create table if not exists lm_api_cost \(id bigint generated always as identity primary key, ts timestamptz default now\(\), uid text, kind text, quantity numeric, unit text, est_usd numeric, meta jsonb\)/);
  assert.doesNotMatch(sql, /\b(drop|truncate|alter)\b/);
});

test("recordCost inserts the normalized row through Supabase REST", async () => {
  const calls = [];
  const fetchImpl = async (...args) => {
    calls.push(args);
    return { ok: true, status: 201 };
  };
  const ok = await ledger().recordCost({
    uid: "u1", kind: "telnyx_call", quantity: 90, unit: "seconds",
    estUsd: 0.003, meta: { event: "wake" },
  }, { supaUrl: "https://db.example", supaKey: "service", fetchImpl });

  assert.equal(ok, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "https://db.example/rest/v1/lm_api_cost");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers.Prefer, "return=minimal");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    uid: "u1", kind: "telnyx_call", quantity: 90, unit: "seconds",
    est_usd: 0.003, meta: {
      event: "wake", provider: null, sku: null, operation: "telnyx_call",
      currency: "USD", actual_usd: null, billing_status: "estimated",
      pricing_version: null, estimate_status: "estimated",
    },
  });
});

test("recordCost preserves unavailable measurements and separates estimate from actual", async () => {
  let body;
  const ok = await ledger().recordCost({
    uid: "u1", kind: "composio_call", quantity: null, unit: "call", estUsd: null,
    meta: { provider: "composio", operation: "EVENTS_LIST", billing_status: "estimated" },
  }, {
    supaUrl: "https://db.example", supaKey: "service",
    fetchImpl: async (_url, init) => { body = JSON.parse(init.body); return { ok: true, status: 201 }; },
  });

  assert.equal(ok, true);
  assert.equal(body.quantity, null);
  assert.equal(body.est_usd, null);
  assert.equal(body.meta.provider, "composio");
  assert.equal(body.meta.operation, "EVENTS_LIST");
  assert.equal(body.meta.currency, "USD");
  assert.equal(body.meta.actual_usd, null);
  assert.equal(body.meta.billing_status, "unknown");
  assert.equal(body.meta.estimate_status, "unavailable");
  assert.equal(body.meta.pricing_version, null);
});

test("recordCost logs and resolves false when Supabase fails", async () => {
  const errors = [];
  const result = await ledger().recordCost({ uid: "u1", kind: "x", quantity: 1, meta: {
    runtime_trace: { loop_id: "loop-1", owner_id: "owner-1", run_id: "run-1",
      occurrence_id: "loop-1:run-1", release_sha: "a".repeat(40) },
  } }, {
    supaUrl: "https://db.example", supaKey: "service",
    fetchImpl: async () => { throw new Error("offline"); },
    log: (value) => errors.push(value),
  });
  assert.equal(result, false);
  assert.equal(errors.length, 1);
  const diagnostic = JSON.parse(errors[0]);
  assert.equal(diagnostic.event, "lm_api_cost_write_failed");
  assert.equal(diagnostic.kind, "x");
  assert.equal(diagnostic.owner_id, "owner-1");
  assert.equal(diagnostic.loop_id, "loop-1");
  assert.equal(diagnostic.run_id, "run-1");
  assert.equal(diagnostic.occurrence_id, "loop-1:run-1");
  assert.equal(diagnostic.release_sha, "a".repeat(40));
  assert.equal(diagnostic.phase, "cost_ledger_write");
  assert.equal(diagnostic.command, "supabase_post_lm_api_cost");
  assert.equal(diagnostic.effect, "effect_unknown");
  assert.equal(diagnostic.retryable, false);
  assert.equal(diagnostic.next_action, "readback_before_retry");
  assert.doesNotMatch(errors[0], /offline|service|https:\/\//);
});

test("recordDailyComposioPoll uses a DB day query and inserts at most one row", async () => {
  const requests = [];
  const responses = [
    { ok: true, status: 200, json: async () => [] },
    { ok: true, status: 201 },
    { ok: true, status: 200, json: async () => [{ id: 9 }] },
  ];
  const opts = {
    supaUrl: "https://db.example", supaKey: "service",
    nowMs: Date.parse("2026-07-18T12:34:56Z"),
    fetchImpl: async (...args) => { requests.push(args); return responses.shift(); },
  };

  assert.equal(await ledger().recordDailyComposioPoll("u1", opts), true);
  assert.equal(await ledger().recordDailyComposioPoll("u1", opts), false);
  assert.equal(requests.length, 3);
  assert.match(requests[0][0], /kind=eq\.composio_poll/);
  assert.match(requests[0][0], /uid=eq\.u1/);
  assert.match(requests[0][0], /ts=gte\.2026-07-18T00%3A00%3A00\.000Z/);
  assert.match(requests[0][0], /ts=lt\.2026-07-19T00%3A00%3A00\.000Z/);
  assert.equal(requests[1][1].method, "POST");
  const pollRow = JSON.parse(requests[1][1].body);
  assert.equal(pollRow.est_usd, null);
  assert.equal(pollRow.meta.provider, "composio");
  assert.equal(pollRow.meta.operation, "daily_usage_poll");
  assert.equal(pollRow.meta.actual_usd, null);
  assert.equal(pollRow.meta.billing_status, "unknown");
  assert.equal(requests[2][1].method, undefined);
});

test("monthlyComposioCallCount reads the exact monthly composio_call count", async () => {
  const requests = [];
  const count = await ledger().monthlyComposioCallCount({ nowMs: Date.parse("2026-07-21T12:00:00Z"),
    supaUrl: "https://db.example", supaKey: "service",
    fetchImpl: async (...args) => { requests.push(args); return { ok: true, headers: { get: () => "0-0/19500" } }; } });
  assert.equal(count, 19500);
  assert.match(requests[0][0], /kind=eq\.composio_call/);
  assert.match(requests[0][0], /ts=gte\.2026-07-01/);
});

test("businessSummary is pure and groups calls and total cost per uid", () => {
  const rows = [
    { ts: "2026-07-18T10:00:00Z", uid: "u1", kind: "telnyx_call", quantity: "90", est_usd: "0.003" },
    { ts: "2026-07-18T10:00:00Z", uid: "u1", kind: "gemini_live", quantity: 90, est_usd: 0.0345 },
    { ts: "2026-07-17T10:00:00Z", uid: "u2", kind: "telnyx_call", quantity: 30, est_usd: 0.001 },
    { ts: "2026-06-01T10:00:00Z", uid: "old", kind: "telnyx_call", quantity: 600, est_usd: 9 },
  ];
  const frozen = JSON.parse(JSON.stringify(rows));
  const summary = ledger().businessSummary(30, rows, Date.parse("2026-07-18T12:00:00Z"));

  assert.deepEqual(summary, {
    calls: 2,
    call_minutes: 2,
    est_cost_usd: 0.0385,
    per_uid: {
      u1: { calls: 1, call_minutes: 1.5, est_cost_usd: 0.0375 },
      u2: { calls: 1, call_minutes: 0.5, est_cost_usd: 0.001 },
    },
  });
  assert.deepEqual(rows, frozen);
});

test("production bridge and scheduler contain all three LM-7 recording points", () => {
  const server = fs.readFileSync(path.join(__dirname, "../server.js"), "utf8");
  const scheduler = fs.readFileSync(path.join(__dirname, "../scheduler.js"), "utf8");
  assert.match(server, /kind:\s*["']telnyx_call["']/);
  assert.match(server, /kind:\s*["']gemini_live["']/);
  assert.match(scheduler, /recordDailyComposioPoll/);
});
