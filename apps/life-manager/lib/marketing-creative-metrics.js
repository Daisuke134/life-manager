"use strict";

const fs = require("node:fs");
const path = require("node:path");

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const LOCALE = /^[a-z]{2}(?:-[A-Z]{2})?$/;
const PROVIDER_POST_ID = /^[A-Za-z0-9._:-]{1,200}$/;

function identifier(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!IDENTIFIER.test(text)) throw new Error(`${label} is invalid`);
  return text;
}

function locale(value) {
  const text = String(value || "");
  if (!LOCALE.test(text)) throw new Error("creative metric locale is invalid");
  return text;
}

function exactInstant(value, label) {
  const text = String(value || "");
  const date = new Date(text);
  if (!Number.isFinite(date.getTime()) || date.toISOString() !== text) {
    throw new Error(`${label} is invalid`);
  }
  return text;
}

function ledgerPath(dataDir) {
  return path.join(dataDir, "marketing", "creative-metrics.jsonl");
}

// Records one observed performance sample for a hook (creative variant). Idempotent per
// provider_post_id: callers should skip a post already present in readCreativeMetrics()
// before calling this again (see scripts/record-creative-metrics.js).
function recordCreativeMetric(dataDir, input = {}) {
  const row = {
    schema_version: 1,
    kind: "marketing_creative_metric",
    tenant_id: identifier(input.tenantId, "creative metric tenant"),
    product_id: identifier(input.productId, "creative metric product"),
    format_id: identifier(input.formatId, "creative metric format"),
    locale: locale(input.locale),
    hook_id: identifier(input.hookId, "creative metric hook"),
    provider_post_id: (() => {
      const text = String(input.providerPostId || "");
      if (!PROVIDER_POST_ID.test(text)) throw new Error("creative metric provider_post_id is invalid");
      return text;
    })(),
    score: (() => {
      const value = Number(input.score);
      if (!Number.isFinite(value) || value < 0) throw new Error("creative metric score is invalid");
      return value;
    })(),
    observed_at: exactInstant(input.observedAt, "creative metric observed_at"),
  };
  const file = ledgerPath(dataDir);
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  fs.appendFileSync(file, `${JSON.stringify(row)}\n`, { mode: 0o600 });
  fs.chmodSync(file, 0o600);
  return row;
}

function readCreativeMetrics(dataDir) {
  const file = ledgerPath(dataDir);
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .filter((row) => row && row.kind === "marketing_creative_metric");
}

// Returns a historyProvider-shaped { list } that marketing-video-generation-adapter's
// execute() can call to bias hook selection toward hooks with a better recorded score.
function createCreativeMetricsProvider(dataDir) {
  return {
    async list({ tenantId, productId, formatId, locale: localeId }) {
      const rows = readCreativeMetrics(dataDir).filter((row) => (
        row.tenant_id === tenantId
        && row.product_id === productId
        && row.format_id === formatId
        && row.locale === localeId
      ));
      const byHook = new Map();
      for (const row of rows) {
        const bucket = byHook.get(row.hook_id) || [];
        bucket.push(row.score);
        byHook.set(row.hook_id, bucket);
      }
      return [...byHook.entries()].map(([hookId, scores]) => ({
        hook_id: hookId,
        score: scores.reduce((sum, value) => sum + value, 0) / scores.length,
      }));
    },
  };
}

module.exports = {
  createCreativeMetricsProvider,
  ledgerPath,
  readCreativeMetrics,
  recordCreativeMetric,
};
