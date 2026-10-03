#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");

const { importContentObject, resolveContentObject } = require("../lib/content-object-store.js");
const { resolveDataRoot } = require("../lib/runtime-paths.js");

const PRODUCTS = Object.freeze([
  Object.freeze({ product_id: "anicca-ios", app_id: "6755129214", app_name: "Daily Affirmations - Anicca", request_id: "04c74879-547f-4e35-b231-1fafd485801d", bootstrap_day: "2026-08-23", bootstrap_reports: Object.freeze([
    Object.freeze({ report_id: "r3-04c74879-547f-4e35-b231-1fafd485801d", report_name: "App Downloads Standard", instance_id: "402ad6b2-ddd8-4f84-a1b6-17ea8cbd3a37", processing_date: "2026-08-22", segments: Object.freeze(["078c2b3b-fac3-4923-8141-8191bb769c85", "d24b3d7a-e22e-4c14-9e7f-1af24756fb97"]) }),
    Object.freeze({ report_id: "r15-04c74879-547f-4e35-b231-1fafd485801d", report_name: "App Store Discovery and Engagement Detailed", instance_id: "f6ea9447-20e5-4910-9378-eb18c9ba4ec3", processing_date: "2026-08-21", segments: Object.freeze(["da95c273-a951-46d4-ae13-3bd2b32efe06"]) }),
  ]) }),
  Object.freeze({ product_id: "honne-ai", app_id: "6759667221", app_name: "Honne", request_id: "c7c05836-181e-49cc-ae71-b57b7a0b466e", bootstrap_day: "2026-08-23", campaign_token: "honne_en_base_20260823" }),
]);
const ASC_ENV = Object.freeze({ ...process.env, ASC_BYPASS_KEYCHAIN: "true", ASC_TIMEOUT: "90s" });

const exec = promisify(execFile);

async function ascJson(args) {
  const { stdout } = await exec("asc", args, { encoding: "utf8", env: ASC_ENV, maxBuffer: 32 * 1024 * 1024 });
  return JSON.parse(stdout);
}

function rows(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const headers = lines[0].split("\t");
  return lines.slice(1).filter(Boolean).map((line) => Object.fromEntries(headers.map((header, index) => [header, line.split("\t")[index] || ""])));
}

function sum(input, predicate, field = "Counts") {
  return input.filter(predicate).reduce((total, row) => total + Number(row[field] || 0), 0);
}

function measured(value, source) { return { status: "measured", value, source }; }
function unavailable(reason) { return { status: "unavailable", value: null, reason }; }

function derivedRate(numerator, denominator, numeratorName, denominatorName) {
  if (!numerator || numerator.status !== "measured") {
    return unavailable(`source_metric_unavailable:${numeratorName}`);
  }
  if (!denominator || denominator.status !== "measured") {
    return unavailable(`source_metric_unavailable:${denominatorName}`);
  }
  const numeratorValue = Number(numerator.value);
  const denominatorValue = Number(denominator.value);
  if (!Number.isFinite(numeratorValue) || !Number.isFinite(denominatorValue)
    || numeratorValue < 0 || denominatorValue < 0) {
    return unavailable("source_metric_invalid");
  }
  if (denominatorValue === 0) return unavailable("denominator_zero");
  return {
    status: "measured",
    value: Number((numeratorValue / denominatorValue).toFixed(6)),
    numerator: numeratorValue,
    denominator: denominatorValue,
  };
}

function derivedFunnelRates(metrics = {}) {
  return {
    impression_to_page_view: derivedRate(
      metrics.unique_product_page_views, metrics.unique_impressions,
      "unique_product_page_views", "unique_impressions",
    ),
    page_view_to_install: derivedRate(
      metrics.first_time_downloads, metrics.unique_product_page_views,
      "first_time_downloads", "unique_product_page_views",
    ),
    impression_to_install: derivedRate(
      metrics.first_time_downloads, metrics.unique_impressions,
      "first_time_downloads", "unique_impressions",
    ),
  };
}

function summarize(product, downloads, engagement, metadata, detailedDownloads = []) {
  if (!downloads.length || !engagement.length) return pending(product, "empty_report");
  const dates = [...downloads, ...engagement].map((row) => row.Date).filter(Boolean).sort();
  const expectedApp = (row) => !row["App Apple Identifier"] || row["App Apple Identifier"] === product.app_id;
  if (![...downloads, ...engagement].every(expectedApp)) {
    const observed = [...new Set([...downloads, ...engagement].map((row) => row["App Apple Identifier"] || "missing"))];
    throw new Error(`${product.product_id} ASC app identity mismatch: ${observed.join(",")}`);
  }
  const downloadSource = "app_store_connect_app_downloads_standard";
  const engagementSource = "app_store_connect_discovery_engagement_detailed";
  const campaignDownloads = product.campaign_token ? detailedDownloads.filter((row) => row.Campaign === product.campaign_token && row["Download Type"] === "First-time download") : [];
  const campaignEngagement = product.campaign_token ? engagement.filter((row) => row.Campaign === product.campaign_token) : [];
  const campaignUnavailable = () => unavailable(product.campaign_token ? "campaign_not_observed_or_privacy_threshold" : "campaign_not_configured");
  const baseMetrics = {
      product_id: product.product_id,
    app_id: product.app_id,
    app_name: product.app_name,
    identity_source: "analytics_report_request_app_id",
    source_status: "measured",
    attribution_status: "unattributed",
    attribution_reason: "campaign_not_configured",
    confidence: "official_product_total_no_campaign",
    data_from: dates[0] || null,
    data_to: dates.at(-1) || null,
    reports: metadata,
    campaign_id: product.campaign_token || null,
    campaign_status: campaignDownloads.length || campaignEngagement.length ? "measured" : "unavailable",
    metrics: {
      first_time_downloads: measured(sum(downloads, (row) => row["Download Type"] === "First-time download"), downloadSource),
      redownloads: measured(sum(downloads, (row) => row["Download Type"] === "Redownload"), downloadSource),
      updates: measured(sum(downloads, (row) => ["Auto-update", "Manual update"].includes(row["Download Type"])), downloadSource),
      total_downloads: measured(sum(downloads, (row) => ["First-time download", "Redownload"].includes(row["Download Type"])), downloadSource),
      impressions: measured(sum(engagement, (row) => row.Event === "Impression"), engagementSource),
      unique_impressions: measured(sum(engagement, (row) => row.Event === "Impression", "Unique Counts"), engagementSource),
      product_page_views: measured(sum(engagement, (row) => row.Event === "Page View" && row["Page Type"] === "Product page"), engagementSource),
      unique_product_page_views: measured(sum(engagement, (row) => row.Event === "Page View" && row["Page Type"] === "Product page", "Unique Counts"), engagementSource),
      campaign_first_time_downloads: campaignDownloads.length ? measured(sum(campaignDownloads, () => true), "app_store_connect_app_downloads_detailed") : campaignUnavailable(),
      campaign_impressions: campaignEngagement.length ? measured(sum(campaignEngagement, (row) => row.Event === "Impression"), "app_store_connect_discovery_engagement_detailed") : campaignUnavailable(),
    },
  };
  baseMetrics.metrics = { ...baseMetrics.metrics, ...derivedFunnelRates(baseMetrics.metrics) };
  return baseMetrics;
}

function pending(product, reason = "report_pending") {
  return {
    product_id: product.product_id,
    app_id: product.app_id,
    app_name: product.app_name,
    source_status: "unavailable",
    attribution_status: "unattributed",
    attribution_reason: "campaign_not_configured",
    confidence: "none",
    data_from: null,
    data_to: null,
    reports: [],
    campaign_id: product.campaign_token || null,
    campaign_status: "unavailable",
    metrics: Object.fromEntries(["first_time_downloads", "redownloads", "updates", "total_downloads", "impressions", "unique_impressions", "product_page_views", "unique_product_page_views", "campaign_first_time_downloads", "campaign_impressions", "impression_to_page_view", "page_view_to_install", "impression_to_install"].map((name) => [name, unavailable(reason)])),
  };
}

function sourceFailureReason(error) {
  const message = String(error && error.message || error || "");
  if (/required or expired agreement|missing or has expired|agreement/i.test(message)) return "asc_agreement_required";
  if (/403|forbidden|insufficient permissions/i.test(message)) return "asc_permission_denied";
  if (/deadline exceeded|timeout/i.test(message)) return "source_timeout";
  return "source_unavailable";
}

async function latestDaily(reportId) {
  const links = (await ascJson(["analytics", "reports", "links", "--report-id", reportId, "--output", "json"])).data;
  const candidates = await Promise.all(links.slice(-16).map(async ({ id }) => {
    const value = await ascJson(["analytics", "instances", "view", "--instance-id", id, "--output", "json"]);
    return { id, ...value.data.attributes };
  }));
  return candidates.filter((instance) => instance.granularity === "DAILY").sort((a, b) => a.processingDate.localeCompare(b.processingDate)).at(-1) || null;
}

async function downloadReport(requestId, reportId, reportName, directory) {
  const daily = await latestDaily(reportId);
  if (!daily) return null;
  const segments = (await ascJson(["analytics", "instances", "links", "--instance-id", daily.id, "--output", "json"])).data;
  if (!segments?.length) return null;
  const output = await Promise.all(segments.map(async (segment, index) => {
    const file = path.join(directory, `${reportId}-${index}.csv`);
    await exec("asc", ["analytics", "download", "--request-id", requestId, "--instance-id", daily.id, "--segment-id", segment.id, "--decompress", "--output", file], { env: ASC_ENV });
    return rows(fs.readFileSync(file, "utf8"));
  }));
  return { rows: output.flat(), metadata: { report_id: reportId, report_name: reportName, instance_id: daily.id, processing_date: daily.processingDate, granularity: daily.granularity } };
}

async function downloadKnown(requestId, report, directory) {
  const output = await Promise.all(report.segments.map(async (segmentId, index) => {
    const file = path.join(directory, `${report.report_id}-${index}.csv`);
    await exec("asc", ["analytics", "download", "--request-id", requestId, "--instance-id", report.instance_id, "--segment-id", segmentId, "--decompress", "--output", file], { env: ASC_ENV });
    return rows(fs.readFileSync(file, "utf8"));
  }));
  return { rows: output.flat(), metadata: { report_id: report.report_id, report_name: report.report_name, instance_id: report.instance_id, processing_date: report.processing_date, granularity: "DAILY" } };
}

async function collectProduct(product, reportDay) {
  if (product.bootstrap_day === reportDay && !product.bootstrap_reports) return pending(product);
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), `lm-asc-${product.product_id}-`));
  try {
    const bootstrap = product.bootstrap_day === reportDay ? await Promise.all(product.bootstrap_reports.map((report) => downloadKnown(product.request_id, report, directory))) : null;
    const [downloaded, detailed, engaged] = bootstrap ? [bootstrap[0], null, bootstrap[1]] : await Promise.all([
        downloadReport(product.request_id, `r3-${product.request_id}`, "App Downloads Standard", directory),
        downloadReport(product.request_id, `r4-${product.request_id}`, "App Downloads Detailed", directory),
        downloadReport(product.request_id, `r15-${product.request_id}`, "App Store Discovery and Engagement Detailed", directory),
      ]);
    if (!downloaded || !engaged) return pending(product);
    return summarize(product, downloaded.rows, engaged.rows, [downloaded.metadata, ...(detailed ? [detailed.metadata] : []), engaged.metadata], detailed?.rows || []);
  } catch (error) {
    if (/not found|404|no analytics report instances/i.test(String(error.message))) return pending(product);
    return pending(product, sourceFailureReason(error));
  } finally { fs.rmSync(directory, { recursive: true }); }
}

function jstDay(now = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now).map(({ type, value }) => [type, value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

async function persistAscAcquisition(dataDir = resolveDataRoot(process.env), reportDay = jstDay(), collector = collectProduct) {
  const directory = path.join(dataDir, "tenants/dais-local/marketing/attribution/asc", reportDay);
  const pointer = path.join(directory, "acquisition.json");
  if (fs.existsSync(pointer)) return { ...JSON.parse(fs.readFileSync(pointer, "utf8")), created: false, pointer };
  const lineagePointer = path.join(dataDir, "tenants/dais-local/marketing/attribution/lineage.json");
  const lineage = JSON.parse(fs.readFileSync(lineagePointer, "utf8"));
  resolveContentObject(lineage.snapshot_ref, { objectDir: path.join(dataDir, "objects") });
  const products = await Promise.all(PRODUCTS.map((product) => collector(product, reportDay)));
  const snapshot = { schema_version: 1, kind: "marketing_asc_acquisition", tenant_id: "dais-local", report_day: reportDay, lineage_ref: lineage.snapshot_ref, products, rows: lineage.rows.map((row) => ({ product_id: row.product_id, account_id: row.account_id, platform: row.platform, provider_post_id: row.provider_post_id, public_url: row.public_url, campaign_id: row.campaign_id, acquisition_status: "unattributed", acquisition_reason: "campaign_not_configured", product_observation_status: products.find((product) => product.product_id === row.product_id).source_status })) };
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

if (require.main === module) persistAscAcquisition().then((result) => process.stdout.write(`${JSON.stringify(result)}\n`)).catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
module.exports = { PRODUCTS, collectProduct, derivedFunnelRates, pending, persistAscAcquisition, rows, sourceFailureReason, summarize };
