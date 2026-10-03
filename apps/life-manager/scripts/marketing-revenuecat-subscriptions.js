#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const { importContentObject, resolveContentObject } = require("../lib/content-object-store.js");
const { resolveDataRoot } = require("../lib/runtime-paths.js");
const { PRODUCTS: ASC_PRODUCTS } = require("./marketing-asc-acquisition.js");

const PRODUCTS = Object.freeze(ASC_PRODUCTS.map(({ product_id }) => product_id));
const METRICS = Object.freeze(["trial_starts", "active_subscriptions", "renewals", "cancellations", "proceeds_usd"]);

function unavailable(reason) {
  return { status: "unavailable", value: null, reason };
}

function missingProduct(productId) {
  return {
    product_id: productId,
    source: "product_pack_input",
    source_status: "unavailable",
    observed_at: null,
    data_from: null,
    data_to: null,
    metrics: Object.fromEntries(METRICS.map((name) => [name, unavailable("product_pack_observation_missing")])),
  };
}

function validateMetric(productId, name, metric) {
  if (!metric || !["measured", "unavailable"].includes(metric.status)) {
    throw new Error(`${productId} ${name} status is invalid`);
  }
  if (metric.status === "unavailable") {
    if (metric.value !== null) throw new Error(`${productId} ${name} unavailable value must be null`);
    if (!metric.reason) throw new Error(`${productId} ${name} unavailable reason is required`);
  } else if (typeof metric.value !== "number" || !Number.isFinite(metric.value)) {
    throw new Error(`${productId} ${name} measured value must be finite`);
  }
  return metric;
}

function readProduct(dataDir, productId) {
  const file = path.join(dataDir, "tenants/dais-local/product-packs/metrics/revenuecat", `${productId}.json`);
  if (!fs.statSync(file, { throwIfNoEntry: false })?.isFile()) return missingProduct(productId);
  const input = JSON.parse(fs.readFileSync(file, "utf8"));
  if (input.kind !== "product_revenuecat_observation" || input.schema_version !== 1) throw new Error(`${productId} product observation contract mismatch`);
  if (input.product_id !== productId) throw new Error(`${productId} product identity mismatch: ${input.product_id}`);
  if (!Number.isFinite(Date.parse(input.observed_at))) throw new Error(`${productId} observed_at is invalid`);
  if (!input.source || !["measured", "partial", "unavailable"].includes(input.source_status)) throw new Error(`${productId} source metadata is invalid`);
  const metrics = Object.fromEntries(METRICS.map((name) => [name, validateMetric(productId, name, input.metrics?.[name])]));
  const statuses = new Set(Object.values(metrics).map(({ status }) => status));
  if (input.source_status === "measured" && statuses.has("unavailable")) throw new Error(`${productId} measured source contains unavailable metric`);
  if (input.source_status === "unavailable" && statuses.has("measured")) throw new Error(`${productId} unavailable source contains measured metric`);
  return {
    product_id: productId,
    source: input.source,
    source_status: input.source_status,
    observed_at: input.observed_at,
    data_from: input.data_from || null,
    data_to: input.data_to || null,
    attribution_status: "unattributed",
    attribution_reason: "campaign_not_configured",
    transaction_truth: "revenuecat_receipt_observation",
    proceeds_truth: "revenuecat_estimate_not_store_settlement",
    metrics,
  };
}

function ascPointer(dataDir, reportDay) {
  const exact = path.join(dataDir, "tenants/dais-local/marketing/attribution/asc", reportDay, "acquisition.json");
  if (fs.statSync(exact, { throwIfNoEntry: false })?.isFile()) return exact;
  const root = path.dirname(path.dirname(exact));
  const candidates = fs.statSync(root, { throwIfNoEntry: false })?.isDirectory()
    ? fs.readdirSync(root).sort().reverse().map((day) => path.join(root, day, "acquisition.json"))
    : [];
  return candidates.find((file) => fs.statSync(file, { throwIfNoEntry: false })?.isFile()) || null;
}

function persistRevenueCatSubscriptions(dataDir = resolveDataRoot(process.env), reportDay, observedAt = new Date().toISOString()) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(reportDay || ""))) throw new Error("reportDay is required");
  const directory = path.join(dataDir, "tenants/dais-local/marketing/attribution/revenuecat", reportDay);
  const pointer = path.join(directory, "subscriptions.json");
  if (fs.statSync(pointer, { throwIfNoEntry: false })?.isFile()) return { ...JSON.parse(fs.readFileSync(pointer, "utf8")), created: false, pointer };
  const ascFile = ascPointer(dataDir, reportDay);
  if (!ascFile) throw new Error("ASC acquisition input is missing");
  const asc = JSON.parse(fs.readFileSync(ascFile, "utf8"));
  resolveContentObject(asc.snapshot_ref, { objectDir: path.join(dataDir, "objects") });
  const products = PRODUCTS.map((productId) => readProduct(dataDir, productId));
  const snapshot = {
    schema_version: 1,
    kind: "marketing_revenuecat_subscriptions",
    tenant_id: "dais-local",
    report_day: reportDay,
    observed_at: observedAt,
    asc_ref: asc.snapshot_ref,
    products,
    attribution: { status: "unattributed", reason: "campaign_not_configured", timing_inference_allowed: false },
  };
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const candidate = path.join(directory, `.candidate-${process.pid}.json`);
  fs.writeFileSync(candidate, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600 });
  const imported = importContentObject(candidate, { objectDir: path.join(dataDir, "objects") });
  fs.unlinkSync(candidate);
  const value = { ...snapshot, snapshot_ref: imported.ref };
  const temporary = `${pointer}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(temporary, pointer);
  return { ...value, created: true, pointer };
}

if (require.main === module) {
  const reportDay = process.argv[2] || new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const result = persistRevenueCatSubscriptions(resolveDataRoot(process.env), reportDay);
  process.stdout.write(`${JSON.stringify({ created: result.created, snapshot_ref: result.snapshot_ref, products: result.products.map(({ product_id, source_status }) => ({ product_id, source_status })) })}\n`);
}

module.exports = { METRICS, PRODUCTS, missingProduct, persistRevenueCatSubscriptions, readProduct, validateMetric };
