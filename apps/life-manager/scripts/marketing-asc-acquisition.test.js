"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { importContentObject } = require("../lib/content-object-store.js");
const { PRODUCTS, cohortR3ProcessingDate, derivedFunnelRates, installToPaidD7, latestMatureCohortDate, pending, persistAscAcquisition, rows, sourceFailureReason, summarize } = require("./marketing-asc-acquisition.js");

test("ASC acquisition portfolio matches the six currently published App Store apps", () => {
  assert.deepEqual(PRODUCTS.map(({ product_id, app_id, request_id }) => [product_id, app_id, request_id]), [
    ["anicca-ios", "6755129214", "04c74879-547f-4e35-b231-1fafd485801d"],
    ["honne-ai", "6759667221", "c7c05836-181e-49cc-ae71-b57b7a0b466e"],
    ["dhamma-quotes", "6757726663", "25b5906d-025b-4b9d-8226-dc1ea25bd13f"],
    ["sleep-reset", "6762143790", "f4f4e486-d5cd-4b16-9d06-a1850fc9a477"],
    ["studio-cherie", "6766485903", "b1c18c4e-77f3-4b63-bee4-259353531c3d"],
    ["thankful", "6759514159", "a1149f87-b22a-42cb-85a8-324eb54d2f1a"],
  ]);
});

test("ASC source failures preserve actionable agreement and permission reasons", () => {
  assert.equal(sourceFailureReason(new Error("A required agreement is missing or has expired")), "asc_agreement_required");
  assert.equal(sourceFailureReason(new Error("HTTP 403 Forbidden")), "asc_permission_denied");
  assert.equal(sourceFailureReason(new Error("deadline exceeded")), "source_timeout");
});

test("ASC funnel rates are measured with explicit numerators and denominators", () => {
  const rates = derivedFunnelRates({
    first_time_downloads: { status: "measured", value: 2 },
    unique_impressions: { status: "measured", value: 10 },
    unique_product_page_views: { status: "measured", value: 4 },
  });
  assert.deepEqual(rates.impression_to_page_view, {
    status: "measured", value: 0.4, numerator: 4, denominator: 10, source_refs: [],
  });
  assert.deepEqual(rates.page_view_to_install, {
    status: "measured", value: 0.5, numerator: 2, denominator: 4, source_refs: [],
  });
  assert.deepEqual(rates.impression_to_install, {
    status: "measured", value: 0.2, numerator: 2, denominator: 10, source_refs: [],
  });
  assert.deepEqual(rates.install_to_paid, {
    status: "unavailable", value: null, reason: "paid_customer_cohort_unavailable", numerator: null, denominator: null, source_refs: [],
  });
});

test("ASC funnel rates fail closed on unavailable metrics and zero denominators", () => {
  const rates = derivedFunnelRates({
    first_time_downloads: { status: "measured", value: 2 },
    unique_impressions: { status: "measured", value: 0 },
    unique_product_page_views: { status: "unavailable", value: null, reason: "provider_403" },
  });
  assert.equal(rates.impression_to_install.status, "unavailable");
  assert.equal(rates.impression_to_install.reason, "denominator_zero");
  assert.equal(rates.page_view_to_install.reason, "source_metric_unavailable:unique_product_page_views");
  assert.equal(rates.install_to_paid.reason, "paid_customer_cohort_unavailable");
});

test("ASC funnel totals and rates use only the dates present in both reports", () => {
  const result = summarize(PRODUCTS[0], [
    { Date: "2026-09-30", "App Apple Identifier": PRODUCTS[0].app_id, "Download Type": "First-time download", Counts: "2" },
    { Date: "2026-10-01", "App Apple Identifier": PRODUCTS[0].app_id, "Download Type": "First-time download", Counts: "9" },
  ], [
    { Date: "2026-09-30", "App Apple Identifier": PRODUCTS[0].app_id, Event: "Impression", Counts: "8", "Unique Counts": "6" },
    { Date: "2026-10-02", "App Apple Identifier": PRODUCTS[0].app_id, Event: "Impression", Counts: "20", "Unique Counts": "10" },
  ], [
    { report_id: "r3-anicca", report_name: "App Downloads Standard", instance_id: "downloads-2026-09-30", processing_date: "2026-10-02" },
    { report_id: "r15-anicca", report_name: "App Store Discovery and Engagement Detailed", instance_id: "engagement-2026-09-30", processing_date: "2026-10-02" },
  ]);
  assert.equal(result.data_from, "2026-09-30");
  assert.equal(result.data_to, "2026-09-30");
  assert.equal(result.metrics.first_time_downloads.value, 2);
  assert.equal(result.metrics.unique_impressions.value, 6);
  assert.equal(result.metrics.impression_to_install.value, 0.333333);
  assert.deepEqual(result.metrics.impression_to_page_view.source_refs, ["asc-report:r15-anicca:engagement-2026-09-30:2026-10-02"]);
  assert.deepEqual(result.metrics.page_view_to_install.source_refs, [
    "asc-report:r3-anicca:downloads-2026-09-30:2026-10-02",
    "asc-report:r15-anicca:engagement-2026-09-30:2026-10-02",
  ]);
  assert.deepEqual(result.metrics.impression_to_install.source_refs, result.metrics.page_view_to_install.source_refs);
});

test("ASC funnel rates are unavailable when download and engagement reports do not overlap", () => {
  const result = summarize(PRODUCTS[0], [
    { Date: "2026-10-01", "App Apple Identifier": PRODUCTS[0].app_id, "Download Type": "First-time download", Counts: "2" },
  ], [
    { Date: "2026-09-30", "App Apple Identifier": PRODUCTS[0].app_id, Event: "Impression", Counts: "8", "Unique Counts": "6" },
  ], []);
  assert.equal(result.source_status, "unavailable");
  assert.equal(result.metrics.impression_to_install.reason, "report_window_mismatch");
});

test("an independent measured D7 cohort survives an acquisition-report window mismatch", () => {
  const d7 = installToPaidD7(PRODUCTS[0], D7_COHORT_RESPONSE, D7_DOWNLOAD_ROWS, D7_COHORT_DATE, D7_OBSERVED_AT, D7_REPORT);
  const result = summarize(PRODUCTS[0], [
    { Date: "2026-10-01", "App Apple Identifier": PRODUCTS[0].app_id, "Download Type": "First-time download", Counts: "2" },
  ], [
    { Date: "2026-10-02", "App Apple Identifier": PRODUCTS[0].app_id, Event: "Impression", Counts: "8", "Unique Counts": "6" },
  ], [], [], d7);
  assert.equal(result.source_status, "partial");
  assert.equal(result.metrics.impression_to_install.reason, "report_window_mismatch");
  assert.equal(result.metrics.install_to_paid.status, "measured");
  assert.equal(result.metrics.install_to_paid.cohort_date, D7_COHORT_DATE);
  assert.equal(result.metrics.install_to_paid.denominator, 3);
});

test("ASC product totals remain unattributed and unavailable stays null on replay", async () => {
  const parsed = rows("Date\tApp Name\tApp Apple Identifier\tDownload Type\tCounts\n2026-08-20\tDaily Affirmations - Anicca\t6755129214\tFirst-time download\t1\n");
  const anicca = summarize(PRODUCTS[0], parsed, [{ Date: "2026-08-20", "App Name": PRODUCTS[0].app_name, "App Apple Identifier": PRODUCTS[0].app_id, Event: "Impression", "Page Type": "No page", Counts: "9", "Unique Counts": "5" }], []);
  assert.equal(anicca.metrics.first_time_downloads.value, 1);
  assert.equal(anicca.metrics.impressions.value, 9);
  assert.equal(anicca.attribution_status, "unattributed");
  assert.equal(summarize(PRODUCTS[0], [], [], []).metrics.first_time_downloads.value, null);
  assert.equal(summarize(PRODUCTS[0], [], [], []).metrics.install_to_paid.reason, "paid_customer_cohort_unavailable");
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-asc-join-"));
  const objectDir = path.join(dataDir, "objects");
  const attributionDir = path.join(dataDir, "tenants/dais-local/marketing/attribution");
  fs.mkdirSync(attributionDir, { recursive: true });
  const lineageFile = path.join(dataDir, "lineage.json");
  const lineage = { rows: [{ product_id: "anicca-ios", account_id: "@anicca.jp", platform: "tiktok", provider_post_id: "post-1", public_url: "https://www.tiktok.com/@anicca.jp/video/1", campaign_id: null }, { product_id: "honne-ai", account_id: "@honne_reveal", platform: "tiktok", provider_post_id: "post-2", public_url: "https://www.tiktok.com/@honne_reveal/video/2", campaign_id: null }] };
  fs.writeFileSync(lineageFile, JSON.stringify(lineage));
  const imported = importContentObject(lineageFile, { objectDir });
  fs.writeFileSync(path.join(attributionDir, "lineage.json"), JSON.stringify({ ...lineage, snapshot_ref: imported.ref }));
  const collector = (product) => product.product_id === "anicca-ios" ? anicca : pending(product);
  const first = await persistAscAcquisition(dataDir, "2026-08-23", collector);
  const replay = await persistAscAcquisition(dataDir, "2026-08-23", collector);
  assert.equal(first.created, true);
  assert.equal(replay.created, false);
  assert.equal(first.snapshot_ref, replay.snapshot_ref);
  assert.equal(first.products[1].metrics.first_time_downloads.value, null);
  assert.ok(first.rows.every((row) => row.acquisition_status === "unattributed"));
});

test("ASC campaign totals are measured only from a matching detailed-report token", () => {
  const honne = PRODUCTS[1]; const downloads = [{ Date: "2026-08-23", "App Apple Identifier": honne.app_id, "Download Type": "First-time download", Counts: "7" }]; const engagement = [{ Date: "2026-08-23", "App Apple Identifier": honne.app_id, Event: "Impression", Counts: "20", "Unique Counts": "12", Campaign: honne.campaign_token }]; const detailed = [{ ...downloads[0], Campaign: honne.campaign_token, Counts: "6" }];
  const measured = summarize(honne, downloads, engagement, [], detailed); assert.equal(measured.metrics.campaign_first_time_downloads.value, 6); assert.equal(measured.metrics.campaign_impressions.value, 20); assert.equal(measured.campaign_status, "measured");
  const withheld = summarize(honne, downloads, engagement.map((row) => ({ ...row, Campaign: "other" })), [], detailed.map((row) => ({ ...row, Campaign: "other" }))); assert.equal(withheld.metrics.campaign_first_time_downloads.value, null); assert.equal(withheld.metrics.campaign_first_time_downloads.status, "unavailable");
});

const D7_COHORT_DATE = "2026-09-26";
const D7_OBSERVED_AT = "2026-10-04T00:00:00.000Z";
const D7_COHORT_RESPONSE = {
  appId: "6755129214",
  startDate: D7_COHORT_DATE,
  endDate: D7_COHORT_DATE,
  frequency: "day",
  measures: ["cohort-download-to-paid-rate"],
  periods: ["d1", "d7", "d35"],
  result: { results: {
    "cohort-download-to-paid-rate": [0, 0, 0, 0, 0, 0, 0, 0],
    date: ["2026-09-26T00:00:00Z", "2026-09-26T00:00:00Z", "2026-09-26T00:00:00Z", "2026-09-26T00:00:00Z", null, null, null, null],
    period: ["d1", "d7", "d35", null, "d1", "d7", "d35", null],
  } },
};
const D7_DOWNLOAD_ROWS = [
  { Date: D7_COHORT_DATE, "App Apple Identifier": "6755129214", "Download Type": "First-time download", Counts: "1" },
  { Date: D7_COHORT_DATE, "App Apple Identifier": "6755129214", "Download Type": "First-time download", Counts: "2" },
  { Date: D7_COHORT_DATE, "App Apple Identifier": "6755129214", "Download Type": "Restore", Counts: "1" },
  { Date: "2026-09-25", "App Apple Identifier": "6755129214", "Download Type": "First-time download", Counts: "1" },
];
const D7_REPORT = { report_id: "r3-04c74879-547f-4e35-b231-1fafd485801d", instance_id: "a678bf6c-4881-454f-adce-8cbeb0458713", processing_date: "2026-09-27" };

test("daily D7 cohort is not mature until every download in its UTC date bucket has had seven full days", () => {
  assert.equal(latestMatureCohortDate("2026-10-03T23:59:59.999Z"), "2026-09-25");
  assert.equal(latestMatureCohortDate(D7_OBSERVED_AT), D7_COHORT_DATE);
});

test("D7 denominator lookup uses the exact historical processing date derived from observed report lag", () => {
  assert.equal(cohortR3ProcessingDate({ metadata: { processing_date: "2026-10-03" }, rows: [
    { Date: "2026-10-02" }, { Date: "2026-10-01" },
  ] }, D7_COHORT_DATE), "2026-09-27");
  assert.equal(cohortR3ProcessingDate({ metadata: { processing_date: "2026-10-03" }, rows: [] }, D7_COHORT_DATE), null);
  assert.equal(cohortR3ProcessingDate({ metadata: { processing_date: "2026-09-25" }, rows: [{ Date: "2026-10-02" }] }, D7_COHORT_DATE), null);
});

test("Install-to-Paid D7 joins the exact app/date first-time downloads and ignores restores and adjacent dates", () => {
  const metric = installToPaidD7(PRODUCTS[0], D7_COHORT_RESPONSE, D7_DOWNLOAD_ROWS, D7_COHORT_DATE, D7_OBSERVED_AT, D7_REPORT);
  assert.equal(metric.status, "measured");
  assert.equal(metric.value, 0);
  assert.equal(metric.numerator, 0);
  assert.equal(metric.denominator, 3);
  assert.equal(metric.sample_size, 3);
  assert.equal(metric.rate_percent, 0);
  assert.equal(metric.rate_precision, 0);
  assert.equal(metric.cohort_date, D7_COHORT_DATE);
  assert.equal(metric.cohort_window_days, 7);
  assert.equal(metric.experimental, true);
  assert.equal(metric.observed_at, D7_OBSERVED_AT);
  assert.deepEqual(metric.source_refs, [
    "asc-report:r3-04c74879-547f-4e35-b231-1fafd485801d:a678bf6c-4881-454f-adce-8cbeb0458713:2026-09-27",
    "asc-web-cohort:6755129214:2026-09-26:d7",
  ]);
});

test("Install-to-Paid D7 fails closed for immature cohorts, missing denominator, redownloads, and identity mismatches", () => {
  const expected = [
    ["immature", D7_COHORT_RESPONSE, D7_DOWNLOAD_ROWS, "2026-10-03T23:59:59.999Z", "cohort_immature"],
    ["missing exact-date denominator", D7_COHORT_RESPONSE, D7_DOWNLOAD_ROWS.filter((row) => row.Date !== D7_COHORT_DATE), D7_OBSERVED_AT, "cohort_denominator_unavailable"],
    ["zero denominator", D7_COHORT_RESPONSE, [{ Date: D7_COHORT_DATE, "App Apple Identifier": "6755129214", "Download Type": "First-time download", Counts: "0" }], D7_OBSERVED_AT, "denominator_zero"],
    ["redownload present", D7_COHORT_RESPONSE, [...D7_DOWNLOAD_ROWS, { Date: D7_COHORT_DATE, "App Apple Identifier": "6755129214", "Download Type": "Redownload", Counts: "1" }], D7_OBSERVED_AT, "redownloads_present"],
    ["wrong report app identity", D7_COHORT_RESPONSE, [{ Date: D7_COHORT_DATE, "App Apple Identifier": "6759667221", "Download Type": "First-time download", Counts: "1" }], D7_OBSERVED_AT, "cohort_app_mismatch"],
    ["invalid download count", D7_COHORT_RESPONSE, [{ Date: D7_COHORT_DATE, "App Apple Identifier": "6755129214", "Download Type": "First-time download", Counts: "1.5" }], D7_OBSERVED_AT, "cohort_download_count_invalid"],
    ["wrong app", { ...D7_COHORT_RESPONSE, appId: "6759667221" }, D7_DOWNLOAD_ROWS, D7_OBSERVED_AT, "cohort_app_mismatch"],
    ["wrong cohort date", { ...D7_COHORT_RESPONSE, result: { results: { date: ["2026-09-25T00:00:00Z"], period: ["d7"], "cohort-download-to-paid-rate": [0] } } }, D7_DOWNLOAD_ROWS, D7_OBSERVED_AT, "cohort_d7_unavailable"],
    ["missing D7 point", { ...D7_COHORT_RESPONSE, result: { results: { ...D7_COHORT_RESPONSE.result.results, date: ["2026-09-26T00:00:00Z"], period: ["d1"], "cohort-download-to-paid-rate": [0] } } }, D7_DOWNLOAD_ROWS, D7_OBSERVED_AT, "cohort_d7_unavailable"],
    ["privacy-suppressed D7 rate", { ...D7_COHORT_RESPONSE, result: { results: { date: ["2026-09-26T00:00:00Z"], period: ["d7"], "cohort-download-to-paid-rate": [null] } } }, D7_DOWNLOAD_ROWS, D7_OBSERVED_AT, "cohort_d7_unavailable"],
  ];
  for (const [label, response, downloads, observedAt, reason] of expected) {
    const metric = installToPaidD7(PRODUCTS[0], response, downloads, D7_COHORT_DATE, observedAt, D7_REPORT);
    assert.equal(metric.status, "unavailable", label);
    assert.equal(metric.reason, reason, label);
    assert.equal(metric.value, null, label);
    assert.equal(metric.experimental, true, label);
  }
  const privacySuppressed = installToPaidD7(PRODUCTS[0], {
    ...D7_COHORT_RESPONSE,
    result: { results: { date: ["2026-09-26T00:00:00Z"], period: ["d7"], "cohort-download-to-paid-rate": [null] } },
  }, D7_DOWNLOAD_ROWS, D7_COHORT_DATE, D7_OBSERVED_AT, D7_REPORT);
  assert.equal(privacySuppressed.reason, "cohort_d7_unavailable");
  assert.equal(privacySuppressed.sample_size, 3);
  assert.equal(privacySuppressed.redownloads, 0);
});

test("Install-to-Paid D7 requires one integer payer count at provider percentage precision", () => {
  const oneOfThree = { ...D7_COHORT_RESPONSE, result: { results: {
    "cohort-download-to-paid-rate": [33.3], date: ["2026-09-26T00:00:00Z"], period: ["d7"],
  } } };
  const metric = installToPaidD7(PRODUCTS[0], oneOfThree, D7_DOWNLOAD_ROWS, D7_COHORT_DATE, D7_OBSERVED_AT, D7_REPORT);
  assert.equal(metric.status, "measured");
  assert.equal(metric.numerator, 1);
  assert.equal(metric.denominator, 3);
  assert.equal(metric.value, 0.333333);
  assert.equal(metric.rate_precision, 1);

  const impossible = { ...D7_COHORT_RESPONSE, result: { results: {
    "cohort-download-to-paid-rate": [50], date: ["2026-09-26T00:00:00Z"], period: ["d7"],
  } } };
  const nonInteger = installToPaidD7(PRODUCTS[0], impossible, D7_DOWNLOAD_ROWS, D7_COHORT_DATE, D7_OBSERVED_AT, D7_REPORT);
  assert.equal(nonInteger.status, "unavailable");
  assert.equal(nonInteger.reason, "cohort_rate_unreconcilable");

  const ambiguousRate = { ...D7_COHORT_RESPONSE, result: { results: {
    "cohort-download-to-paid-rate": [50], date: ["2026-09-26T00:00:00Z"], period: ["d7"],
  } } };
  const ambiguous = installToPaidD7(PRODUCTS[0], ambiguousRate, [
    { Date: D7_COHORT_DATE, "App Apple Identifier": "6755129214", "Download Type": "First-time download", Counts: "201" },
  ], D7_COHORT_DATE, D7_OBSERVED_AT, D7_REPORT);
  assert.equal(ambiguous.status, "unavailable");
  assert.equal(ambiguous.reason, "cohort_rate_ambiguous");
});
