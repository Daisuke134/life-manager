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
  Object.freeze({ product_id: "anicca-ios", app_id: "6755129214", app_name: "Daily Affirmations - Anicca", label: "Anicca iOS", request_id: "04c74879-547f-4e35-b231-1fafd485801d", bootstrap_day: "2026-08-23", bootstrap_reports: Object.freeze([
    Object.freeze({ report_id: "r3-04c74879-547f-4e35-b231-1fafd485801d", report_name: "App Downloads Standard", instance_id: "402ad6b2-ddd8-4f84-a1b6-17ea8cbd3a37", processing_date: "2026-08-22", segments: Object.freeze(["078c2b3b-fac3-4923-8141-8191bb769c85", "d24b3d7a-e22e-4c14-9e7f-1af24756fb97"]) }),
    Object.freeze({ report_id: "r15-04c74879-547f-4e35-b231-1fafd485801d", report_name: "App Store Discovery and Engagement Detailed", instance_id: "f6ea9447-20e5-4910-9378-eb18c9ba4ec3", processing_date: "2026-08-21", segments: Object.freeze(["da95c273-a951-46d4-ae13-3bd2b32efe06"]) }),
  ]) }),
  Object.freeze({ product_id: "honne-ai", app_id: "6759667221", app_name: "Honne", label: "Honne AI", request_id: "c7c05836-181e-49cc-ae71-b57b7a0b466e", bootstrap_day: "2026-08-23", campaign_token: "honne_en_base_20260823" }),
  Object.freeze({ product_id: "dhamma-quotes", app_id: "6757726663", app_name: "Dhamma Quotes", label: "Dhamma Quotes", request_id: "25b5906d-025b-4b9d-8226-dc1ea25bd13f" }),
  Object.freeze({ product_id: "sleep-reset", app_id: "6762143790", app_name: "For Better Sleep - Sleep Reset", label: "For Better Sleep", request_id: "f4f4e486-d5cd-4b16-9d06-a1850fc9a477" }),
  Object.freeze({ product_id: "studio-cherie", app_id: "6766485903", app_name: "STUDIO CHERIE", label: "Studio Cherie", request_id: "b1c18c4e-77f3-4b63-bee4-259353531c3d" }),
  Object.freeze({ product_id: "thankful", app_id: "6759514159", app_name: "Thankful - Gratitude Journal", label: "Thankful", request_id: "a1149f87-b22a-42cb-85a8-324eb54d2f1a" }),
]);
const ASC_ENV = Object.freeze({ ...process.env, ASC_BYPASS_KEYCHAIN: "true", ASC_TIMEOUT: "90s" });
const DAY_MS = 24 * 60 * 60 * 1000;
const D7_MEASURE = "cohort-download-to-paid-rate";

const exec = promisify(execFile);

async function ascJson(args) {
  const { stdout } = await exec("asc", ["--read-only", ...args], { encoding: "utf8", env: ASC_ENV, maxBuffer: 32 * 1024 * 1024 });
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

function rateUnavailable(reason, sourceRefs = []) {
  return { status: "unavailable", value: null, reason, numerator: null, denominator: null, source_refs: sourceRefs };
}

function reportSourceRef(report) {
  return `asc-report:${report.report_id}:${report.instance_id}:${report.processing_date}`;
}

function derivedRate(numerator, denominator, numeratorName, denominatorName, sourceRefs = []) {
  if (!numerator || numerator.status !== "measured") {
    return rateUnavailable(`source_metric_unavailable:${numeratorName}`, sourceRefs);
  }
  if (!denominator || denominator.status !== "measured") {
    return rateUnavailable(`source_metric_unavailable:${denominatorName}`, sourceRefs);
  }
  const numeratorValue = Number(numerator.value);
  const denominatorValue = Number(denominator.value);
  if (!Number.isFinite(numeratorValue) || !Number.isFinite(denominatorValue)
    || numeratorValue < 0 || denominatorValue < 0) {
    return rateUnavailable("source_metric_invalid", sourceRefs);
  }
  if (denominatorValue === 0) return { ...rateUnavailable("denominator_zero", sourceRefs), numerator: numeratorValue, denominator: 0 };
  return {
    status: "measured",
    value: Number((numeratorValue / denominatorValue).toFixed(6)),
    numerator: numeratorValue,
    denominator: denominatorValue,
    source_refs: sourceRefs,
  };
}

function derivedFunnelRates(metrics = {}, sourceRefs = {}) {
  return {
    impression_to_page_view: derivedRate(
      metrics.unique_product_page_views, metrics.unique_impressions,
      "unique_product_page_views", "unique_impressions",
      sourceRefs.impression_to_page_view || [],
    ),
    page_view_to_install: derivedRate(
      metrics.first_time_downloads, metrics.unique_product_page_views,
      "first_time_downloads", "unique_product_page_views",
      sourceRefs.page_view_to_install || [],
    ),
    impression_to_install: derivedRate(
      metrics.first_time_downloads, metrics.unique_impressions,
      "first_time_downloads", "unique_impressions",
      sourceRefs.impression_to_install || [],
    ),
    install_to_paid: metrics.install_to_paid || rateUnavailable("paid_customer_cohort_unavailable", sourceRefs.install_to_paid || []),
  };
}

function exactDownloadCounts(product, downloadRows, cohortDate) {
  const cohortRows = downloadRows.filter((row) => row.Date === cohortDate);
  if (!cohortRows.length) return { error: "cohort_denominator_unavailable" };
  if (cohortRows.some((row) => row["App Apple Identifier"] !== product.app_id)) return { error: "cohort_app_mismatch" };
  let firstTimeDownloads = 0;
  let redownloads = 0;
  for (const row of cohortRows) {
    if (!["First-time download", "Redownload"].includes(row["Download Type"])) continue;
    const raw = String(row.Counts ?? "").trim().replace(/,/g, "");
    if (!/^\d+$/.test(raw) || !Number.isSafeInteger(Number(raw))) return { error: "cohort_download_count_invalid" };
    if (row["Download Type"] === "First-time download") firstTimeDownloads += Number(raw);
    else redownloads += Number(raw);
  }
  if (!Number.isSafeInteger(firstTimeDownloads) || !Number.isSafeInteger(redownloads)) return { error: "cohort_download_count_invalid" };
  if (redownloads > 0) return { error: "redownloads_present", denominator: firstTimeDownloads, redownloads };
  if (firstTimeDownloads === 0) return { error: "denominator_zero", denominator: 0, redownloads };
  return { denominator: firstTimeDownloads, redownloads };
}

function uniquePayerCount(providerRate, denominator) {
  if (typeof providerRate !== "number" || !Number.isFinite(providerRate) || providerRate < 0 || providerRate > 100) {
    return { error: "cohort_rate_invalid" };
  }
  const text = String(providerRate);
  if (/[eE]/.test(text)) return { error: "cohort_rate_precision_invalid" };
  const precision = Math.min(text.includes(".") ? text.split(".")[1].length : 0, 8);
  const scale = 10 ** precision;
  const roundedProviderRate = Math.round(providerRate * scale);
  const estimate = providerRate * denominator / 100;
  const start = Math.max(0, Math.floor(estimate) - 2);
  const end = Math.min(denominator, Math.ceil(estimate) + 2);
  const candidates = [];
  for (let count = start; count <= end; count += 1) {
    if (Math.round((100 * count / denominator) * scale) === roundedProviderRate) candidates.push(count);
  }
  if (!candidates.length) return { error: "cohort_rate_unreconcilable" };
  if (candidates.length !== 1) return { error: "cohort_rate_ambiguous" };
  return { value: candidates[0], precision };
}

function installToPaidD7(product, cohortResponse, downloadRows, cohortDate, observedAt, report) {
  const cohortRef = `asc-web-cohort:${product.app_id}:${cohortDate}:d7`;
  const sourceRefs = [report && report.report_id && report.instance_id ? reportSourceRef(report) : null, cohortRef].filter(Boolean);
  const failed = (reason, extras = {}) => ({
    ...rateUnavailable(reason, sourceRefs),
    cohort_date: cohortDate,
    cohort_window_days: 7,
    experimental: true,
    observed_at: observedAt,
    ...extras,
  });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(cohortDate || "")) || !Number.isFinite(Date.parse(`${cohortDate}T00:00:00Z`))) return failed("cohort_date_invalid");
  const counts = exactDownloadCounts(product, downloadRows, cohortDate);
  if (counts.error) return failed(counts.error, { sample_size: counts.denominator ?? null, redownloads: counts.redownloads ?? null });
  const countContext = { sample_size: counts.denominator, redownloads: counts.redownloads };
  const cohortStart = Date.parse(`${cohortDate}T00:00:00Z`);
  const observedTimestamp = Date.parse(observedAt);
  if (!Number.isFinite(observedTimestamp)) return failed("cohort_observation_time_invalid", countContext);
  if (observedTimestamp < cohortStart + 8 * DAY_MS) return failed("cohort_immature", countContext);
  if (!cohortResponse || cohortResponse.appId !== product.app_id) return failed("cohort_app_mismatch", countContext);
  if (cohortResponse.startDate !== cohortDate || cohortResponse.endDate !== cohortDate || cohortResponse.frequency !== "day"
    || !cohortResponse.measures?.includes(D7_MEASURE) || !cohortResponse.periods?.includes("d7")) return failed("cohort_query_mismatch", countContext);
  const results = cohortResponse.result?.results;
  const dates = results?.date;
  const periods = results?.period;
  const values = results?.[D7_MEASURE];
  if (!Array.isArray(dates) || !Array.isArray(periods) || !Array.isArray(values) || dates.length !== periods.length || periods.length !== values.length) {
    return failed("cohort_response_invalid", countContext);
  }
  const matches = dates.flatMap((date, index) => {
    if (periods[index] !== "d7" || typeof date !== "string") return [];
    const timestamp = Date.parse(date);
    return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === cohortDate ? [{ value: values[index] }] : [];
  });
  if (matches.length !== 1 || matches[0].value == null) return failed(matches.length > 1 ? "cohort_d7_ambiguous" : "cohort_d7_unavailable", countContext);
  const payerCount = uniquePayerCount(matches[0].value, counts.denominator);
  if (payerCount.error) return failed(payerCount.error, { sample_size: counts.denominator, redownloads: counts.redownloads });
  return {
    status: "measured",
    value: Number((payerCount.value / counts.denominator).toFixed(6)),
    numerator: payerCount.value,
    denominator: counts.denominator,
    sample_size: counts.denominator,
    rate_percent: matches[0].value,
    rate_precision: payerCount.precision,
    redownloads: counts.redownloads,
    cohort_date: cohortDate,
    cohort_window_days: 7,
    source: "apple_download_to_paid_d7_experimental",
    source_refs: sourceRefs,
    experimental: true,
    observed_at: observedAt,
  };
}

function summarize(product, downloads, engagement, metadata, detailedDownloads = [], installToPaid = rateUnavailable("paid_customer_cohort_unavailable")) {
  if (!downloads.length || !engagement.length) return pending(product, "empty_report", installToPaid, metadata);
  const expectedApp = (row) => !row["App Apple Identifier"] || row["App Apple Identifier"] === product.app_id;
  if (![...downloads, ...engagement].every(expectedApp)) {
    const observed = [...new Set([...downloads, ...engagement].map((row) => row["App Apple Identifier"] || "missing"))];
    throw new Error(`${product.product_id} ASC app identity mismatch: ${observed.join(",")}`);
  }
  const dateOf = (row) => {
    const value = String(row.Date || "");
    return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) ? value : null;
  };
  if ([...downloads, ...engagement].some((row) => dateOf(row) === null)) {
    return pending(product, "report_date_invalid", installToPaid, metadata);
  }
  const engagementDates = new Set(engagement.map(dateOf));
  const dates = [...new Set(downloads.map(dateOf))].filter((day) => engagementDates.has(day)).sort();
  if (!dates.length) return pending(product, "report_window_mismatch", installToPaid, metadata);
  const includedDates = new Set(dates);
  const alignedDownloads = downloads.filter((row) => includedDates.has(dateOf(row)));
  const alignedEngagement = engagement.filter((row) => includedDates.has(dateOf(row)));
  const alignedDetailedDownloads = detailedDownloads.filter((row) => dateOf(row) !== null && includedDates.has(dateOf(row)));
  const downloadSource = "app_store_connect_app_downloads_standard";
  const engagementSource = "app_store_connect_discovery_engagement_detailed";
  const campaignDownloads = product.campaign_token ? alignedDetailedDownloads.filter((row) => row.Campaign === product.campaign_token && row["Download Type"] === "First-time download") : [];
  const campaignEngagement = product.campaign_token ? alignedEngagement.filter((row) => row.Campaign === product.campaign_token) : [];
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
      first_time_downloads: measured(sum(alignedDownloads, (row) => row["Download Type"] === "First-time download"), downloadSource),
      redownloads: measured(sum(alignedDownloads, (row) => row["Download Type"] === "Redownload"), downloadSource),
      updates: measured(sum(alignedDownloads, (row) => ["Auto-update", "Manual update"].includes(row["Download Type"])), downloadSource),
      total_downloads: measured(sum(alignedDownloads, (row) => ["First-time download", "Redownload"].includes(row["Download Type"])), downloadSource),
      impressions: measured(sum(alignedEngagement, (row) => row.Event === "Impression"), engagementSource),
      unique_impressions: measured(sum(alignedEngagement, (row) => row.Event === "Impression", "Unique Counts"), engagementSource),
      product_page_views: measured(sum(alignedEngagement, (row) => row.Event === "Page View" && row["Page Type"] === "Product page"), engagementSource),
      unique_product_page_views: measured(sum(alignedEngagement, (row) => row.Event === "Page View" && row["Page Type"] === "Product page", "Unique Counts"), engagementSource),
      campaign_first_time_downloads: campaignDownloads.length ? measured(sum(campaignDownloads, () => true), "app_store_connect_app_downloads_detailed") : campaignUnavailable(),
      campaign_impressions: campaignEngagement.length ? measured(sum(campaignEngagement, (row) => row.Event === "Impression"), "app_store_connect_discovery_engagement_detailed") : campaignUnavailable(),
    },
  };
  const downloadRefs = metadata.filter((report) => report.report_name === "App Downloads Standard").map(reportSourceRef);
  const engagementRefs = metadata.filter((report) => report.report_name === "App Store Discovery and Engagement Detailed").map(reportSourceRef);
  baseMetrics.metrics.install_to_paid = installToPaid;
  baseMetrics.metrics = { ...baseMetrics.metrics, ...derivedFunnelRates(baseMetrics.metrics, {
    impression_to_page_view: engagementRefs,
    page_view_to_install: [...downloadRefs, ...engagementRefs],
    impression_to_install: [...downloadRefs, ...engagementRefs],
    install_to_paid: installToPaid.source_refs || [],
  }) };
  return baseMetrics;
}

function pending(product, reason = "report_pending", installToPaid = rateUnavailable("paid_customer_cohort_unavailable"), reports = []) {
  const rateMetrics = new Set(["impression_to_page_view", "page_view_to_install", "impression_to_install"]);
  return {
    product_id: product.product_id,
    app_id: product.app_id,
    app_name: product.app_name,
    source_status: installToPaid.status === "measured" ? "partial" : "unavailable",
    attribution_status: "unattributed",
    attribution_reason: "campaign_not_configured",
    confidence: installToPaid.status === "measured" ? "experimental_paid_cohort_only" : "none",
    data_from: null,
    data_to: null,
    reports,
    campaign_id: product.campaign_token || null,
    campaign_status: "unavailable",
    metrics: Object.fromEntries(["first_time_downloads", "redownloads", "updates", "total_downloads", "impressions", "unique_impressions", "product_page_views", "unique_product_page_views", "campaign_first_time_downloads", "campaign_impressions", "impression_to_page_view", "page_view_to_install", "impression_to_install"].map((name) => [name, rateMetrics.has(name) ? rateUnavailable(reason) : unavailable(reason)]).concat([
      ["install_to_paid", installToPaid],
    ])),
  };
}

function sourceFailureReason(error) {
  const message = String(error && error.message || error || "");
  if (/session expired|no usable apple web session/i.test(message)) return "asc_web_session_expired";
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
  return downloadInstance(requestId, { report_id: reportId, report_name: reportName }, daily, directory);
}

async function downloadInstance(requestId, report, instance, directory) {
  const segments = (await ascJson(["analytics", "instances", "links", "--instance-id", instance.id, "--output", "json"])).data;
  if (!segments?.length) return null;
  const fullReport = {
    ...report,
    instance_id: instance.id,
    processing_date: instance.processingDate,
    granularity: instance.granularity,
    segments: segments.map(({ id }) => id),
  };
  return downloadKnown(requestId, fullReport, directory);
}

async function downloadKnown(requestId, report, directory) {
  const output = await Promise.all(report.segments.map(async (segmentId, index) => {
    const file = path.join(directory, `${report.report_id}-${report.instance_id}-${index}.csv`);
    await exec("asc", ["--read-only", "analytics", "download", "--request-id", requestId, "--instance-id", report.instance_id, "--segment-id", segmentId, "--decompress", "--output", file], { env: ASC_ENV });
    return rows(fs.readFileSync(file, "utf8"));
  }));
  return { rows: output.flat(), metadata: { report_id: report.report_id, report_name: report.report_name, instance_id: report.instance_id, processing_date: report.processing_date, granularity: report.granularity || "DAILY" } };
}

function latestMatureCohortDate(observedAt) {
  const timestamp = Date.parse(observedAt);
  // Wait until the end of the UTC download day plus seven full days.
  return Number.isFinite(timestamp) ? new Date(timestamp - 8 * DAY_MS).toISOString().slice(0, 10) : null;
}

function validReportDate(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`));
}

function dateDifferenceDays(laterDate, earlierDate) {
  if (!validReportDate(laterDate) || !validReportDate(earlierDate)) return null;
  const difference = (Date.parse(`${laterDate}T00:00:00Z`) - Date.parse(`${earlierDate}T00:00:00Z`)) / DAY_MS;
  return Number.isInteger(difference) ? difference : null;
}

function addUtcDays(date, days) {
  return validReportDate(date) && Number.isInteger(days)
    ? new Date(Date.parse(`${date}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10)
    : null;
}

function cohortR3ProcessingDate(latestDownloads, cohortDate) {
  if (!validReportDate(cohortDate) || !Array.isArray(latestDownloads?.rows) || !validReportDate(latestDownloads?.metadata?.processing_date)) return null;
  const latestDataDate = latestDownloads.rows.map((row) => row.Date).filter(validReportDate).sort().at(-1);
  const processingLag = dateDifferenceDays(latestDownloads.metadata.processing_date, latestDataDate);
  if (processingLag === null || processingLag < 0 || processingLag > 7) return null;
  return addUtcDays(cohortDate, processingLag);
}

async function downloadR3AtProcessingDate(product, processingDate, directory) {
  const reportId = `r3-${product.request_id}`;
  const view = await ascJson(["analytics", "view", "--request-id", product.request_id, "--processing-date", processingDate, "--granularity", "DAILY", "--output", "json"]);
  const report = view.data?.find((candidate) => candidate.id === reportId);
  const instance = report?.instances?.find((candidate) => candidate.granularity === "DAILY" && candidate.processingDate === processingDate);
  if (!instance) return null;
  return downloadInstance(product.request_id, { report_id: reportId, report_name: "App Downloads Standard (D7 cohort denominator)" }, instance, directory);
}

async function collectInstallToPaidD7(product, latestDownloads, observedAt, reportDay, directory) {
  const latestMatureDate = latestMatureCohortDate(observedAt);
  const cohortDate = validReportDate(reportDay) && reportDay < latestMatureDate ? reportDay : latestMatureDate;
  if (!cohortDate) return { metric: d7Unavailable("cohort_observation_time_invalid", null, observedAt), report: null };
  const processingDate = cohortR3ProcessingDate(latestDownloads, cohortDate);
  if (!processingDate) {
    return { metric: d7Unavailable("cohort_report_lag_unavailable", cohortDate, observedAt), report: null };
  }
  let denominatorReport;
  try {
    denominatorReport = await downloadR3AtProcessingDate(product, processingDate, directory);
  } catch (error) {
    return { metric: d7Unavailable(`cohort_report_${sourceFailureReason(error)}`, cohortDate, observedAt), report: null };
  }
  if (!denominatorReport) return { metric: d7Unavailable("cohort_report_instance_unavailable", cohortDate, observedAt), report: null };
  const countCheck = exactDownloadCounts(product, denominatorReport.rows, cohortDate);
  if (countCheck.error) {
    return {
      metric: d7Unavailable(countCheck.error, cohortDate, observedAt, [reportSourceRef(denominatorReport.metadata)]),
      report: denominatorReport.metadata,
    };
  }
  const cohortRef = `asc-web-cohort:${product.app_id}:${cohortDate}:d7`;
  try {
    const response = await ascJson([
      "web", "analytics", "cohorts", "--app", product.app_id,
      "--start", cohortDate, "--end", cohortDate, "--frequency", "day",
      "--measures", D7_MEASURE, "--periods", "d1,d7,d35", "--output", "json",
    ]);
    return {
      metric: installToPaidD7(product, response, denominatorReport.rows, cohortDate, observedAt, denominatorReport.metadata),
      report: denominatorReport.metadata,
    };
  } catch (error) {
    return {
      metric: d7Unavailable(`cohort_${sourceFailureReason(error)}`, cohortDate, observedAt, [reportSourceRef(denominatorReport.metadata), cohortRef]),
      report: denominatorReport.metadata,
    };
  }
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
    if (!downloaded) return pending(product);
    const observedAt = new Date().toISOString();
    const cohort = await collectInstallToPaidD7(product, downloaded, observedAt, reportDay, directory);
    const metadata = [downloaded.metadata, ...(detailed ? [detailed.metadata] : []), ...(engaged ? [engaged.metadata] : []), ...(cohort.report ? [cohort.report] : [])];
    if (!engaged) return pending(product, "empty_report", cohort.metric, metadata);
    return summarize(product, downloaded.rows, engaged.rows, metadata, detailed?.rows || [], cohort.metric);
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
module.exports = { PRODUCTS, cohortR3ProcessingDate, collectProduct, derivedFunnelRates, installToPaidD7, latestMatureCohortDate, pending, persistAscAcquisition, rows, sourceFailureReason, summarize };
