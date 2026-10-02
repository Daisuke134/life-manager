"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const SQL = fs.readFileSync(path.join(
  __dirname,
  "../migrations/2026-07-27-lm-financial-reports.sql",
), "utf8");

test("REPORT-1 binds one public agent wallet to one tenant without storing a key", () => {
  assert.match(SQL, /ALTER TABLE public\.lm_users[\s\S]*ADD COLUMN IF NOT EXISTS agent_wallet_address text/i);
  assert.match(SQL, /agent_wallet_address IS NULL\s+OR agent_wallet_address ~ '\^0x\[0-9a-fA-F\]\{40\}\$'/i);
  assert.match(SQL, /CREATE UNIQUE INDEX IF NOT EXISTS lm_users_agent_wallet_address_key/i);
  assert.match(SQL, /WHERE agent_wallet_address IS NOT NULL/i);
  assert.doesNotMatch(SQL, /private.?key|mnemonic|seed.?phrase/i);
});

test("REPORT-1 receipt identity is tenant, kind, and local period", () => {
  assert.match(SQL, /CREATE TABLE IF NOT EXISTS public\.lm_financial_report_receipts/i);
  assert.match(SQL, /uid text NOT NULL REFERENCES public\.lm_users\(uid\) ON DELETE CASCADE/i);
  assert.match(SQL, /report_kind text NOT NULL CHECK \(report_kind IN \('daily', 'weekly'\)\)/i);
  assert.match(SQL, /period_key text NOT NULL/i);
  assert.match(SQL, /PRIMARY KEY \(uid, report_kind, period_key\)/i);
  assert.match(SQL, /snapshot jsonb NOT NULL CHECK \(jsonb_typeof\(snapshot\) = 'object'\)/i);
  assert.match(SQL, /snapshot_hash text NOT NULL CHECK \(\s*length\(snapshot_hash\) = 64/i);
  assert.match(SQL, /telegram_message_id bigint/i);
  assert.match(SQL, /status text NOT NULL CHECK \(status IN \('pending', 'sent', 'failed'\)\)/i);
});

test("REPORT-1 receipts are RLS-protected and only service_role can mutate them", () => {
  assert.match(SQL, /ALTER TABLE public\.lm_financial_report_receipts ENABLE ROW LEVEL SECURITY/i);
  assert.match(SQL, /REVOKE ALL ON TABLE public\.lm_financial_report_receipts\s+FROM PUBLIC, anon, authenticated/i);
  assert.match(SQL, /GRANT SELECT, INSERT, UPDATE ON TABLE public\.lm_financial_report_receipts\s+TO service_role/i);
  assert.doesNotMatch(SQL, /GRANT[^;]*DELETE[^;]*lm_financial_report_receipts/i);
  assert.match(SQL, /CREATE POLICY lm_financial_report_service_select/i);
  assert.match(SQL, /CREATE POLICY lm_financial_report_service_insert/i);
  assert.match(SQL, /CREATE POLICY lm_financial_report_service_update/i);
});

test("REPORT-1 aggregates high-volume API cost inside Postgres with tenant and half-open bounds", () => {
  assert.match(SQL, /CREATE OR REPLACE FUNCTION public\.lm_financial_cost_totals/i);
  assert.match(SQL, /WHERE lm_api_cost\.uid = p_uid/i);
  assert.match(SQL, /ts >= p_period_start AND ts < p_period_end/i);
  assert.match(SQL, /COALESCE\(sum\(est_usd\)/i);
  assert.match(SQL, /SECURITY DEFINER\s+SET search_path = public, pg_temp/i);
  assert.match(SQL, /REVOKE ALL ON FUNCTION public\.lm_financial_cost_totals\(text, timestamptz, timestamptz\)/i);
  assert.match(SQL, /GRANT EXECUTE ON FUNCTION public\.lm_financial_cost_totals\(text, timestamptz, timestamptz\)\s+TO service_role/i);
});

test("CFO provider cost settlement migration adds nullable actual and receipt dimensions", () => {
  const sql = fs.readFileSync(path.join(__dirname,
    "../migrations/2026-10-02-lm-provider-cost-settlement.sql"), "utf8");
  assert.match(sql, /ADD COLUMN IF NOT EXISTS provider text/i);
  assert.match(sql, /ADD COLUMN IF NOT EXISTS sku text/i);
  assert.match(sql, /ADD COLUMN IF NOT EXISTS actual_usd numeric/i);
  assert.match(sql, /billing_status.*estimated.*settled.*unknown.*not_applicable/is);
  assert.match(sql, /source_receipt_ref text/i);
  assert.doesNotMatch(sql, /DROP TABLE|TRUNCATE/i);
  assert.match(sql, /CREATE OR REPLACE FUNCTION public\.lm_provider_cost_summary/i);
  assert.match(sql, /settled_cost_usd/i);
  assert.match(sql, /unknown_count/i);
  assert.match(sql, /GRANT EXECUTE ON FUNCTION public\.lm_provider_cost_summary[\s\S]*service_role/i);
});
