#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { homedir } = require("node:os");

const { importContentObject, resolveContentObject } = require("../lib/content-object-store.js");
const { resolveDataRoot } = require("../lib/runtime-paths.js");

const PRODUCTS = Object.freeze(["anicca-ios", "honne-ai"]);
const METRICS = Object.freeze(["trial_starts", "active_subscriptions", "renewals", "cancellations", "proceeds_usd"]);
const CUSTOMER_APPS = Object.freeze([
  Object.freeze({ product_id: "anicca-ios", credential_service: "revenuecat-anicca-ios-sdk", app_id: "app511ef26659" }),
  Object.freeze({ product_id: "honne-ai", credential_service: "revenuecat-honne-ios-sdk", app_id: "app3bbd298d22" }),
]);
const CUSTOMER_CHARTS = Object.freeze(["customers_new", "customers_active"]);
const REVENUECAT_BASE = "https://api.revenuecat.com/v2";

function unavailable(reason) {
  return { status: "unavailable", value: null, reason };
}

function exactCredential(credentials, service) {
  const matches = credentials.filter((row) => row && row.service === service);
  if (matches.length !== 1) throw new Error("credential_binding_invalid");
  return matches[0];
}

function revenueCatBindingsFromCredentials(input) {
  if (!input || !Array.isArray(input.credentials)) throw new Error("credential_store_invalid");
  const apiKey = exactCredential(input.credentials, "revenuecat-mobile-existing-deployment").api_key;
  if (typeof apiKey !== "string" || !apiKey.trim()) throw new Error("credential_missing");
  return {
    apiKey,
    apps: CUSTOMER_APPS.map(({ product_id, credential_service, app_id }) => {
      const projectId = exactCredential(input.credentials, credential_service).project_id;
      if (typeof projectId !== "string" || !projectId.trim()) throw new Error("project_binding_invalid");
      return { product_id, project_id: projectId, app_id };
    }),
  };
}

function loadRevenueCatBindings(credentialsPath = path.join(homedir(), ".local/share/anicca/credentials.json")) {
  return revenueCatBindingsFromCredentials(JSON.parse(fs.readFileSync(credentialsPath, "utf8")));
}

async function revenueCatJson(url, apiKey) {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${apiKey}`, Accept: "application/json" },
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`provider_http_${response.status}`);
  return response.json();
}

function dateOffset(date, days) {
  const epoch = Date.parse(`${date}T00:00:00.000Z`);
  if (!Number.isFinite(epoch)) throw new Error("report_day_invalid");
  return new Date(epoch + days * 86_400_000).toISOString().slice(0, 10);
}

function revenueCatWindow(reportDay) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(reportDay || "")) || dateOffset(reportDay, 0) !== reportDay) {
    throw new Error("reportDay is invalid");
  }
  const dataTo = dateOffset(reportDay, -1);
  return { data_from: dateOffset(dataTo, -27), data_to: dataTo };
}

function unavailableCustomerChart(chart, window, reason, appId = null) {
  return {
    chart,
    status: "unavailable",
    value: null,
    reason,
    aggregation: chart === "customers_new" ? "sum_daily" : "average_daily",
    unit: chart === "customers_new" ? "customers" : "customers_per_day",
    source: "revenuecat_charts_v3",
    app_id: appId,
    filter: appId ? { name: "first_app_id", values: [appId] } : null,
    data_from: window.data_from,
    data_to: window.data_to,
    resolution: "day",
    realtime: true,
    series: [],
  };
}

function customerChartFromResponse(chart, body, window, appId) {
  const unavailableChart = (reason, series = []) => ({
    ...unavailableCustomerChart(chart, window, reason, appId),
    series,
    ...(body && typeof body === "object" ? { evidence_sha256: crypto.createHash("sha256").update(JSON.stringify(body)).digest("hex") } : {}),
  });
  const dataStart = Date.parse(`${window.data_from}T00:00:00.000Z`) / 1000;
  const dataEnd = Date.parse(`${window.data_to}T00:00:00.000Z`) / 1000;
  if (!body || body.resolution !== "day" || body.start_date !== dataStart || body.end_date !== dataEnd
    || !Array.isArray(body.measures) || body.measures.length !== 1 || !Array.isArray(body.values)) {
    return unavailableChart("chart_response_invalid");
  }
  const displayName = body.measures[0]?.display_name;
  if (typeof displayName !== "string" || !displayName) return unavailableChart("chart_measure_unavailable");
  const series = body.values.map((row) => {
    if (!row || row.measure !== 0 || !Number.isInteger(row.cohort) || row.cohort < dataStart || row.cohort > dataEnd || typeof row.incomplete !== "boolean"
      || typeof row.value !== "number" || !Number.isFinite(row.value) || row.value < 0) return null;
    const date = new Date(row.cohort * 1000);
    if (date.toISOString().slice(11) !== "00:00:00.000Z") return null;
    return { date: date.toISOString().slice(0, 10), value: row.value, incomplete: row.incomplete };
  });
  if (series.some((row) => row === null)) return unavailableChart("chart_value_invalid");
  const expectedDates = Array.from({ length: 28 }, (_, index) => dateOffset(window.data_from, index));
  if (series.length !== expectedDates.length || series.some((row, index) => row.date !== expectedDates[index])) {
    return unavailableChart("chart_period_coverage_incomplete", series);
  }
  if (series.some((row) => row.incomplete)) return unavailableChart("chart_period_incomplete", series);
  if (body.unsupported_params && (Array.isArray(body.unsupported_params) ? body.unsupported_params.length : true)) return unavailableChart("chart_scope_unsupported", series);
  const aggregation = chart === "customers_new" ? "total" : "average";
  const value = body.summary?.[aggregation]?.[displayName];
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return unavailableChart("chart_summary_unavailable", series);
  const expectedAggregate = chart === "customers_new"
    ? series.reduce((total, row) => total + row.value, 0)
    : series.reduce((total, row) => total + row.value, 0) / series.length;
  if (Math.abs(expectedAggregate - value) > (chart === "customers_new" ? 0.000001 : 0.011)) return unavailableChart("chart_summary_mismatch", series);
  return {
    chart,
    status: "measured",
    value,
    aggregation: chart === "customers_new" ? "sum_daily" : "average_daily",
    unit: chart === "customers_new" ? "customers" : "customers_per_day",
    source: "revenuecat_charts_v3",
    app_id: appId,
    filter: { name: "first_app_id", values: [appId] },
    data_from: window.data_from,
    data_to: window.data_to,
    resolution: "day",
    realtime: true,
    evidence_sha256: crypto.createHash("sha256").update(JSON.stringify(body)).digest("hex"),
    series,
  };
}

function apiUnavailableReason(error, stage) {
  if (["AbortError", "TimeoutError"].includes(error?.name)) return "provider_timeout";
  const status = /^provider_http_(400|401|403|404|423|429|500|503)$/.exec(String(error?.message || ""));
  return status ? status[0] : (stage === "options" ? "chart_options_unavailable" : "chart_query_failed");
}

async function fetchRevenueCatCustomerActivity({ reportDay, observedAt, bindings = null, requestJson = revenueCatJson }) {
  const window = revenueCatWindow(reportDay);
  let selected = bindings;
  try {
    selected = selected || loadRevenueCatBindings();
    if (!selected || typeof selected.apiKey !== "string" || !selected.apiKey.trim() || !Array.isArray(selected.apps)) throw new Error("credential_binding_invalid");
  } catch {
    selected = null;
  }
  const products = [];
  const optionCache = new Map();
  for (const productId of PRODUCTS) {
    const app = selected?.apps.find((candidate) => candidate.product_id === productId && candidate.app_id && candidate.project_id);
    const charts = {};
    for (const chart of CUSTOMER_CHARTS) {
      if (!app) {
        charts[chart] = unavailableCustomerChart(chart, window, "credential_binding_unavailable");
        continue;
      }
      const optionKey = `${app.project_id}:${chart}`;
      let optionsPromise = optionCache.get(optionKey);
      if (!optionsPromise) {
        const optionsUrl = new URL(`${REVENUECAT_BASE}/projects/${encodeURIComponent(app.project_id)}/charts/${chart}/options`);
        optionsUrl.searchParams.set("realtime", "true");
        optionsPromise = requestJson(optionsUrl.toString(), selected.apiKey).catch((error) => ({ error, stage: "options" }));
        optionCache.set(optionKey, optionsPromise);
      }
      const optionsResult = await optionsPromise;
      if (optionsResult?.error) {
        charts[chart] = unavailableCustomerChart(chart, window, apiUnavailableReason(optionsResult.error, "options"), app.app_id);
        continue;
      }
      const filter = optionsResult?.filters?.find((candidate) => candidate.id === "first_app_id");
      const appOption = filter?.options?.find((candidate) => candidate.id === app.app_id);
      if (!appOption) {
        charts[chart] = unavailableCustomerChart(chart, window, "chart_app_filter_unavailable", app.app_id);
        continue;
      }
      const dailyResolution = optionsResult?.resolutions?.find((candidate) => candidate.id === "0" && candidate.display_name === "day");
      if (!dailyResolution) {
        charts[chart] = unavailableCustomerChart(chart, window, "chart_daily_resolution_unavailable", app.app_id);
        continue;
      }
      const dataUrl = new URL(`${REVENUECAT_BASE}/projects/${encodeURIComponent(app.project_id)}/charts/${chart}`);
      dataUrl.searchParams.set("start_date", window.data_from);
      dataUrl.searchParams.set("end_date", window.data_to);
      dataUrl.searchParams.set("resolution", dailyResolution.id);
      dataUrl.searchParams.set("expand_periods", "false");
      dataUrl.searchParams.set("realtime", "true");
      dataUrl.searchParams.set("filters", JSON.stringify([{ name: "first_app_id", values: [app.app_id] }]));
      let body;
      try {
        body = await requestJson(dataUrl.toString(), selected.apiKey);
      } catch (error) {
        charts[chart] = unavailableCustomerChart(chart, window, apiUnavailableReason(error, "data"), app.app_id);
        continue;
      }
      charts[chart] = customerChartFromResponse(chart, body, window, app.app_id);
    }
    const statuses = Object.values(charts).map((chart) => chart.status);
    products.push({
      product_id: productId,
      project_id: app?.project_id || null,
      app_id: app?.app_id || null,
      source_status: statuses.every((status) => status === "measured") ? "measured" : statuses.some((status) => status === "measured") ? "partial" : "unavailable",
      observed_at: observedAt,
      data_from: window.data_from,
      data_to: window.data_to,
      charts,
    });
  }
  return { source: "revenuecat_charts_v3", report_day: reportDay, observed_at: observedAt, ...window, products };
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

function persistRevenueCatSubscriptions(dataDir = resolveDataRoot(process.env), reportDay, observedAt = new Date().toISOString(), customerActivity = null) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(reportDay || ""))) throw new Error("reportDay is required");
  const directory = path.join(dataDir, "tenants/dais-local/marketing/attribution/revenuecat", reportDay);
  const pointer = path.join(directory, "subscriptions.json");
  if (fs.statSync(pointer, { throwIfNoEntry: false })?.isFile()) return { ...JSON.parse(fs.readFileSync(pointer, "utf8")), created: false, pointer };
  const ascFile = ascPointer(dataDir, reportDay);
  if (!ascFile) throw new Error("ASC acquisition input is missing");
  const asc = JSON.parse(fs.readFileSync(ascFile, "utf8"));
  resolveContentObject(asc.snapshot_ref, { objectDir: path.join(dataDir, "objects") });
  const products = PRODUCTS.map((productId) => {
    const product = readProduct(dataDir, productId);
    const activity = customerActivity?.products?.find((row) => row.product_id === productId);
    if (!activity) return product;
    const metric = (chart) => {
      const { status, value, reason, aggregation, unit, source, data_from, data_to, evidence_sha256 } = activity.charts[chart];
      return { status, value, ...(reason ? { reason } : {}), aggregation, unit, source, data_from, data_to, ...(evidence_sha256 ? { evidence_sha256 } : {}) };
    };
    return {
      ...product,
      customer_activity: activity,
      customer_activity_status: activity.source_status,
      metrics: { ...product.metrics, customers_new: metric("customers_new"), customers_active: metric("customers_active") },
    };
  });
  const activityStatuses = products.map((row) => row.customer_activity_status || "unavailable");
  const customerActivityStatus = activityStatuses.length === PRODUCTS.length && activityStatuses.every((status) => status === "measured")
    ? "measured"
    : activityStatuses.some((status) => status === "measured" || status === "partial") ? "partial" : "unavailable";
  const snapshot = {
    schema_version: 1,
    kind: "marketing_revenuecat_subscriptions",
    tenant_id: "dais-local",
    report_day: reportDay,
    observed_at: observedAt,
    asc_ref: asc.snapshot_ref,
    ...(customerActivity ? { customer_activity_source: customerActivity.source, customer_activity_status: customerActivityStatus } : {}),
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

async function persistRevenueCatSubscriptionsDaily(dataDir = resolveDataRoot(process.env), reportDay, observedAt = new Date().toISOString(), options = {}) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(reportDay || ""))) throw new Error("reportDay is required");
  const pointer = path.join(dataDir, "tenants/dais-local/marketing/attribution/revenuecat", reportDay, "subscriptions.json");
  if (fs.statSync(pointer, { throwIfNoEntry: false })?.isFile()) return { ...JSON.parse(fs.readFileSync(pointer, "utf8")), created: false, pointer };
  const activity = await fetchRevenueCatCustomerActivity({ reportDay, observedAt, ...options });
  return persistRevenueCatSubscriptions(dataDir, reportDay, observedAt, activity);
}

if (require.main === module) {
  const reportDay = process.argv[2] || new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  persistRevenueCatSubscriptionsDaily(resolveDataRoot(process.env), reportDay).then((result) => {
    process.stdout.write(`${JSON.stringify({ created: result.created, snapshot_ref: result.snapshot_ref, products: result.products.map(({ product_id, source_status, customer_activity_status }) => ({ product_id, source_status, customer_activity_status })) })}\n`);
  }).catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}

module.exports = { CUSTOMER_APPS, CUSTOMER_CHARTS, METRICS, PRODUCTS, fetchRevenueCatCustomerActivity, missingProduct, persistRevenueCatSubscriptions, persistRevenueCatSubscriptionsDaily, readProduct, revenueCatBindingsFromCredentials, validateMetric };
