"use strict";

const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { mobileAppsRowsToFinancialRecords } = require("./financial-record-mobile-apps.js");
const { projectFinancialRecord } = require("./financial-record-contract.js");
const { createJsonlFinancialRecordStore } = require("./financial-record-store.js");
const { ingestFinancialRecords } = require("./financial-manager-ingest.js");
const {
  buildFinancialManagerReport,
  renderFinancialManagerDetailed,
  renderFinancialManagerTelegram,
} = require("./financial-manager-report.js");

function row(productId, businessDate, revenueValue, { unavailable = false } = {}) {
  if (unavailable) {
    return { product_id: productId, business_date: businessDate, sources: { revenuecat: { status: "unavailable" } } };
  }
  return {
    product_id: productId, business_date: businessDate,
    sources: {
      revenuecat: {
        status: "available",
        data: { charts: { revenue: { latest_complete: { Revenue: { value: revenueValue, incomplete: false } } } } },
      },
    },
  };
}

function mappedAniccaSubscriptionRow(sourceRowIndex) {
  return {
    source_row_index: sourceRowIndex,
    apple_identifier: "6762049696",
    sku: "ai.anicca.app.ios.yearly.b",
    parent_app_id: "6755129214",
    catalog_record_type: "subscription",
    catalog_record_id: "6762049696",
    catalog_product_id: "ai.anicca.app.ios.yearly.b",
    catalog_evidence_ref: "appstoreconnect://subscriptions/6762049696",
    catalog_evidence_sha256: "f".repeat(64),
  };
}

const ASC_APP_IDS_FOR_TEST = {
  "anicca-ios": "6755129214",
  "honne-ai": "6759667221",
  "dhamma-quotes": "6757726663",
  "sleep-reset": "6762143790",
  "studio-cherie": "6766485903",
  thankful: "6759514159",
  "breath-reset": "6760253231",
  "sleep-ritual": "6759916261",
  "desk-stretch-timer": "6760048397",
  "micro-mood": "6759877003",
};

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256(value) {
  return createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function financeReportRows(rowsByProduct, {
  reportId = "finance-2026-12-Z1",
  reportSha256 = "e".repeat(64),
  periodStart = "2026-08-30",
  periodEnd = "2026-09-26",
  businessDate = "2026-10-02",
  sourceObservedAt = "2026-10-02T00:00:00Z",
} = {}) {
  const mappedRows = Object.values(rowsByProduct).flat()
    .sort((left, right) => left.source_row_index - right.source_row_index);
  const unassignedRows = [];
  const unassignedRowsSha256 = sha256(unassignedRows);
  const reportContent = {
    report_id: reportId,
    report_status: "final",
    period_start: periodStart,
    period_end: periodEnd,
    unassigned_row_count: 0,
    unassigned_rows_sha256: unassignedRowsSha256,
    rows: mappedRows,
  };
  const contentSha256 = sha256(reportContent);
  const reportEvidenceRef = `appstoreconnect://financial-reports/${reportId}/${reportSha256}`;
  const unassignedEvidenceRef = `appstoreconnect://financial-report-mappings/${reportId}/${"f".repeat(64)}`;

  return Object.entries(ASC_APP_IDS_FOR_TEST).map(([productId, appId]) => {
    const data = {
      report_id: reportId,
      report_sha256: reportSha256,
      content_sha256: contentSha256,
      report_status: "final",
      app_id: appId,
      period_start: periodStart,
      period_end: periodEnd,
      rows: rowsByProduct[productId] || [],
      unassigned_row_count: 0,
      unassigned_rows_sha256: unassignedRowsSha256,
      report_evidence_ref: reportEvidenceRef,
      unassigned_evidence_ref: unassignedEvidenceRef,
    };
    return {
      ...row(productId, businessDate, 0),
      sources: {
        app_store_financial: {
          status: "available",
          reason: null,
          evidence_sha256: sha256(data),
          observed_at: sourceObservedAt,
          data,
        },
      },
    };
  });
}

test("ASC proceeds without a verified report-content hash and evidence cannot become verified", () => {
  const records = mobileAppsRowsToFinancialRecords([{
    ...row("anicca-ios", "2026-10-02", 0),
    sources: {
      app_store_financial: { status: "available", data: {
        report_id: "finance-2026-12-Z1", report_sha256: "e".repeat(64), report_status: "final",
        app_id: "6755129214", period_start: "2026-08-30", period_end: "2026-09-26",
        rows: [{ ...mappedAniccaSubscriptionRow(0), partner_share_currency: "JPY",
          extended_partner_share: "999999", sale_or_return: "S",
          transaction_date: "2026-09-12", settlement_date: "2026-09-12" }],
      } },
    },
  }], { subjectId: "tenant-1", observedAt: "2026-10-03T00:00:00Z" });

  assert.deepEqual(records, []);
});

test("Financial Manager rejects ASC proceeds whose normalized row no longer matches the report hash", () => {
  const rows = financeReportRows({
    "anicca-ios": [{ ...mappedAniccaSubscriptionRow(0), partner_share_currency: "JPY",
      extended_partner_share: "4250", sale_or_return: "S",
      transaction_date: "2026-09-12", settlement_date: "2026-09-12" }],
  });
  const source = rows.find((item) => item.product_id === "anicca-ios").sources.app_store_financial;
  source.data.rows[0].extended_partner_share = "999999";
  source.evidence_sha256 = sha256(source.data);

  assert.deepEqual(mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-03T00:00:00Z",
  }), []);
});

test("Financial Manager requires the unassigned-row evidence pointer in an ASC report", () => {
  const rows = financeReportRows({
    "anicca-ios": [{ ...mappedAniccaSubscriptionRow(0), partner_share_currency: "JPY",
      extended_partner_share: "4250", sale_or_return: "S",
      transaction_date: "2026-09-12", settlement_date: "2026-09-12" }],
  });
  const source = rows.find((item) => item.product_id === "anicca-ios").sources.app_store_financial;
  delete source.data.unassigned_evidence_ref;
  source.evidence_sha256 = sha256(source.data);

  assert.deepEqual(mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-03T00:00:00Z",
  }), []);
});

test("Financial Manager rejects an ASC source whose evidence hash does not match its payload", () => {
  const rows = financeReportRows({
    "anicca-ios": [{ ...mappedAniccaSubscriptionRow(0), partner_share_currency: "JPY",
      extended_partner_share: "4250", sale_or_return: "S",
      transaction_date: "2026-09-12", settlement_date: "2026-09-12" }],
  });
  rows.find((item) => item.product_id === "anicca-ios")
    .sources.app_store_financial.evidence_sha256 = "0".repeat(64);

  assert.deepEqual(mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-03T00:00:00Z",
  }), []);
});

test("Financial Manager requires the hash of unassigned report rows", () => {
  const rows = financeReportRows({
    "anicca-ios": [{ ...mappedAniccaSubscriptionRow(0), partner_share_currency: "JPY",
      extended_partner_share: "4250", sale_or_return: "S",
      transaction_date: "2026-09-12", settlement_date: "2026-09-12" }],
  });
  const source = rows.find((item) => item.product_id === "anicca-ios").sources.app_store_financial;
  delete source.data.unassigned_rows_sha256;
  source.evidence_sha256 = sha256(source.data);

  assert.deepEqual(mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-03T00:00:00Z",
  }), []);
});

test("RevenueCat chart revenue remains an unverified estimate", () => {
  const records = mobileAppsRowsToFinancialRecords([row("anicca-ios", "2026-09-26", 12.5)], {
    subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z",
  });
  for (const record of records) projectFinancialRecord(record);
  assert.equal(records.length, 1);
  assert.equal(records[0].amount_minor, 1250);
  assert.equal(records[0].currency, "UNKNOWN");
  assert.equal(records[0].kind, "business_revenue");
  assert.equal(records[0].verification.status, "unverified");
  assert.equal(records[0].source.provider, "mobile-apps");
});

test("RevenueCat estimate uses explicit chart currency without becoming settled", () => {
  const source = row("anicca-ios", "2026-09-26", 12.5);
  source.sources.revenuecat.data.charts.revenue.currency = "USD";
  const records = mobileAppsRowsToFinancialRecords([source], {
    subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z",
  });
  assert.equal(records.length, 1);
  assert.equal(records[0].amount_minor, 1250);
  assert.equal(records[0].currency, "USD");
  assert.equal(records[0].verification.status, "unverified");
});

test("all six CFO-bound RevenueCat products can be ingested as separate estimates", () => {
  const products = ["anicca-ios", "honne-ai", "breath-reset", "sleep-ritual", "desk-stretch-timer", "micro-mood"];
  const records = mobileAppsRowsToFinancialRecords(products.map((productId) => row(productId, "2026-09-26", 1)), {
    subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z",
  });
  assert.deepEqual(records.map((record) => record.idempotency_key.split(":")[2]).sort(), [...products].sort());
  assert.ok(records.every((record) => record.verification.status === "unverified"));
});

test("final ASC proceeds supersede RevenueCat chart revenue without double counting", () => {
  const rows = financeReportRows({
    "anicca-ios": [{ ...mappedAniccaSubscriptionRow(0), partner_share_currency: "USD",
      extended_partner_share: "9.99", sale_or_return: "S", product_type_identifier: "IA1",
      transaction_date: "2026-09-26", settlement_date: "2026-10-01" }],
  }, { reportId: "sales-2026-09", reportSha256: "a".repeat(64),
    periodStart: "2026-09-01", periodEnd: "2026-10-01" });
  rows.find((item) => item.product_id === "anicca-ios").sources.revenuecat
    = row("anicca-ios", "2026-09-26", 12.5).sources.revenuecat;
  const records = mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z",
  });
  assert.equal(records.length, 1);
  assert.equal(records[0].amount_minor, 999);
  assert.equal(records[0].currency, "USD");
  assert.equal(records[0].source.provider, "app-store-connect-financial");
  assert.equal(records[0].verification.status, "verified");
  assert.equal(records[0].occurred_at, "2026-10-01T00:00:00Z");
});

test("ASC detail rows must match the mapped app identifier", () => {
  const wrongIdentifier = { ...mappedAniccaSubscriptionRow(0), apple_identifier: "6755129214",
    partner_share_currency: "JPY", extended_partner_share: "4250", sale_or_return: "S",
    transaction_date: "2026-09-12", settlement_date: "2026-09-12" };
  const records = mobileAppsRowsToFinancialRecords(financeReportRows({ "anicca-ios": [wrongIdentifier] }, {
    reportId: "sales-2026-09", reportSha256: "a".repeat(64),
    periodStart: "2026-09-01", periodEnd: "2026-09-30",
  }), { subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z" });
  assert.deepEqual(records, []);
});

test("ASC subscription ID plus exact SKU map settled proceeds to the parent app", () => {
  const source = { source_row_index: 0, apple_identifier: "6762049696",
    sku: "ai.anicca.app.ios.yearly.b", parent_app_id: "6755129214",
    catalog_record_type: "subscription", catalog_record_id: "6762049696",
    catalog_product_id: "ai.anicca.app.ios.yearly.b",
    catalog_evidence_ref: "appstoreconnect://subscriptions/6762049696",
    catalog_evidence_sha256: "f".repeat(64), partner_share_currency: "JPY",
    extended_partner_share: "4250", sale_or_return: "S", product_type_identifier: "IAY",
    transaction_date: "2026-09-12", settlement_date: "2026-09-12" };
  const rows = financeReportRows({ "anicca-ios": [source] });
  rows.find((item) => item.product_id === "anicca-ios").sources.revenuecat
    = row("anicca-ios", "2026-10-02", 99.99).sources.revenuecat;
  const records = mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-03T00:00:00Z",
  });
  assert.equal(records.length, 1);
  assert.equal(records[0].amount_minor, 4250);
  assert.equal(records[0].currency, "JPY");
  assert.equal(records[0].verification.status, "verified");
  assert.equal(records[0].verification.observed_at, "2026-10-02T00:00:00Z");
  assert.deepEqual(records[0].verification.evidence_refs, [
    "appstoreconnect://financial-reports/finance-2026-12-Z1/eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee/rows/0",
    `appstoreconnect://financial-report-mappings/finance-2026-12-Z1/${"f".repeat(64)}`,
    "appstoreconnect://subscriptions/6762049696",
  ]);
  assert.equal(records[0].idempotency_key, "mobile-apps-asc:v1:anicca-ios:finance-2026-12-Z1:0");
});

test("ASC proceeds stay unavailable when both source and snapshot observation times are missing", () => {
  const sale = { ...mappedAniccaSubscriptionRow(0), partner_share_currency: "JPY",
    extended_partner_share: "4250", sale_or_return: "S", product_type_identifier: "IAY",
    transaction_date: "2026-09-12", settlement_date: "2026-09-12" };
  const rows = financeReportRows({ "anicca-ios": [sale] }, { sourceObservedAt: null });
  assert.throws(() => mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-04T01:00:00Z",
  }), /ASC financial source observation time missing/);
});

test("ASC snapshots with a reused row identity but conflicting evidence fail closed", () => {
  const sale = { ...mappedAniccaSubscriptionRow(0), partner_share_currency: "JPY",
    extended_partner_share: "4250", sale_or_return: "S", product_type_identifier: "IAY",
    transaction_date: "2026-09-12", settlement_date: "2026-09-12" };
  const changedSale = { ...sale, extended_partner_share: "5000" };
  const original = financeReportRows({ "anicca-ios": [sale] }, {
    reportId: "finance-2026-12-Z1", reportSha256: "a".repeat(64),
    periodStart: "2026-08-30", periodEnd: "2026-09-26",
    businessDate: "2026-09-27", sourceObservedAt: "2026-09-27T01:00:00Z",
  });
  const changed = financeReportRows({ "anicca-ios": [changedSale] }, {
    reportId: "finance-2026-12-Z1", reportSha256: "b".repeat(64),
    periodStart: "2026-08-30", periodEnd: "2026-09-26",
    businessDate: "2026-10-03", sourceObservedAt: "2026-10-04T00:00:00Z",
  });

  assert.throws(() => mobileAppsRowsToFinancialRecords([...original, ...changed], {
    subjectId: "tenant-1", observedAt: "2026-10-04T01:00:00Z",
  }), /ASC financial record identity conflict/);
});

test("ASC financial rows stay idempotent across repeated business-date snapshots and CFO runs", async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-mobile-asc-idempotency-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const store = createJsonlFinancialRecordStore({ directoryPath: path.join(root, "records") });
  const sale = { ...mappedAniccaSubscriptionRow(0), partner_share_currency: "JPY",
    extended_partner_share: "4250", sale_or_return: "S", product_type_identifier: "IAY",
    transaction_date: "2026-09-12", settlement_date: "2026-09-12" };
  const earlierSnapshot = financeReportRows({ "anicca-ios": [sale] }, {
    reportId: "finance-2026-12-Z1", reportSha256: "a".repeat(64),
    periodStart: "2026-08-30", periodEnd: "2026-09-26",
    businessDate: "2026-09-27", sourceObservedAt: "2026-09-27T01:00:00Z",
  });
  const repeatedSnapshot = financeReportRows({ "anicca-ios": [sale] }, {
    reportId: "finance-2026-12-Z1", reportSha256: "a".repeat(64),
    periodStart: "2026-08-30", periodEnd: "2026-09-26",
    businessDate: "2026-10-03", sourceObservedAt: "2026-10-04T00:00:00Z",
  });
  const readMobileAppsRows = async () => [...earlierSnapshot, ...repeatedSnapshot];
  const options = {
    store, subjectId: "tenant-1",
    readMoneytreeAccounts: async () => [], readMoneytreeTransactions: async () => [],
    readMobileAppsRows,
  };

  const first = await ingestFinancialRecords({ ...options, now: new Date("2026-10-04T01:00:00Z") });
  assert.equal(first.created, 1);
  const persisted = await store.read({ subjectId: "tenant-1" });
  const ascRows = persisted.filter((record) => record.source.provider === "app-store-connect-financial");
  assert.equal(ascRows.length, 1);
  assert.equal(ascRows[0].amount_minor, 4250);
  assert.equal(ascRows[0].recorded_at, "2026-10-04T01:00:00.000Z");

  const replay = await ingestFinancialRecords({ ...options, now: new Date("2026-10-04T02:00:00Z") });
  assert.equal(replay.created, 0);
  assert.deepEqual(await store.read({ subjectId: "tenant-1" }), persisted);
});

test("CFO delivery shows a newly verified prior-period ASC settlement without changing period totals", () => {
  const sale = { ...mappedAniccaSubscriptionRow(0), partner_share_currency: "JPY",
    extended_partner_share: "4250", sale_or_return: "S", product_type_identifier: "IAY",
    transaction_date: "2026-09-12", settlement_date: "2026-09-12" };
  const rows = financeReportRows({ "anicca-ios": [sale] }, {
    reportId: "finance-2026-12-Z1", reportSha256: "c".repeat(64),
    periodStart: "2026-08-30", periodEnd: "2026-09-26",
    businessDate: "2026-10-03", sourceObservedAt: "2026-10-04T00:30:00Z",
  });
  const records = mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-04T01:00:00Z",
  });
  const { report } = buildFinancialManagerReport(records, "2026-10-04");
  const telegram = renderFinancialManagerTelegram(report);
  const detailed = renderFinancialManagerDetailed(report);

  assert.deepEqual(report.business.revenue, []);
  assert.deepEqual(report.business.today.revenue, []);
  assert.deepEqual(report.business.last7Days.revenue, []);
  assert.equal(report.verifiedRecordCount, 1);
  assert.equal(report.business.newlyVerifiedPastPeriod.length, 1);
  assert.deepEqual(report.business.newlyVerifiedPastPeriod[0], {
    productId: "anicca-ios",
    settlementDate: "2026-09-12",
    recordedAt: "2026-10-04T01:00:00.000Z",
    kind: "business_revenue",
    amountMinor: 4250,
    currency: "JPY",
    provider: "app-store-connect-financial",
    externalRef: "finance-2026-12-Z1:0",
    evidenceRefs: [
      `appstoreconnect://financial-reports/finance-2026-12-Z1/${"c".repeat(64)}/rows/0`,
      `appstoreconnect://financial-report-mappings/finance-2026-12-Z1/${"f".repeat(64)}`,
      "appstoreconnect://subscriptions/6762049696",
    ],
  });
  for (const output of [telegram, detailed]) {
    assert.match(output, /新たに確認した過去期間のApp Store精算/);
    assert.match(output, /anicca-ios/);
    assert.match(output, /2026-09-12/);
    assert.match(output, /¥4,250/);
    assert.match(output, /app-store-connect-financial/);
    assert.match(output, /finance-2026-12-Z1:0/);
    assert.match(output, /appstoreconnect:\/\/financial-reports\/finance-2026-12-Z1/);
    assert.match(output, /今月・直近7日には重複計上しない/);
  }
});

test("published ASC apps retain their parent-app binding in Financial Manager", () => {
  const rows = financeReportRows({
    "dhamma-quotes": [{ source_row_index: 0, apple_identifier: "1234567890",
      sku: "com.dailydhamma.app.monthly", parent_app_id: "6757726663",
      catalog_record_type: "subscription", catalog_record_id: "1234567890",
      catalog_product_id: "com.dailydhamma.app.monthly",
      catalog_evidence_ref: "appstoreconnect://subscriptions/1234567890",
      catalog_evidence_sha256: "f".repeat(64), partner_share_currency: "JPY",
      extended_partner_share: "500", sale_or_return: "S", product_type_identifier: "IAY",
      transaction_date: "2026-10-02", settlement_date: "2026-10-02" }],
  }, { reportId: "finance-2026-12-Z1", reportSha256: "c".repeat(64),
    periodStart: "2026-09-27", periodEnd: "2026-10-24" });
  const records = mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-03T00:00:00Z",
  });

  assert.equal(records.length, 1);
  assert.equal(records[0].amount_minor, 500);
  assert.equal(records[0].currency, "JPY");
  assert.equal(records[0].verification.status, "verified");
  assert.equal(records[0].idempotency_key,
    "mobile-apps-asc:v1:dhamma-quotes:finance-2026-12-Z1:0");
});

test("ASC negative return rows become positive debit refunds", () => {
  const source = { ...mappedAniccaSubscriptionRow(1), partner_share_currency: "USD",
    extended_partner_share: "-1.25", sale_or_return: "R", product_type_identifier: "IA1",
    transaction_date: "2026-09-20", settlement_date: "2026-09-25" };
  const rows = financeReportRows({ "anicca-ios": [source] }, {
    reportId: "sales-2026-09", reportSha256: "b".repeat(64),
    periodStart: "2026-09-01", periodEnd: "2026-09-30",
  });
  const records = mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z",
  });
  assert.equal(records.length, 1);
  assert.equal(records[0].kind, "business_cost");
  assert.equal(records[0].direction, "debit");
  assert.equal(records[0].amount_minor, 125);
});

test("ASC detail rows settled outside their final report period fail closed", () => {
  const source = { ...mappedAniccaSubscriptionRow(2), partner_share_currency: "USD",
    extended_partner_share: "9.99", sale_or_return: "S", product_type_identifier: "IA1",
    transaction_date: "2026-09-26", settlement_date: "2026-10-01" };
  const rows = financeReportRows({ "anicca-ios": [source] }, {
    reportId: "sales-2026-09", reportSha256: "c".repeat(64),
    periodStart: "2026-09-01", periodEnd: "2026-09-30",
  });
  const records = mobileAppsRowsToFinancialRecords(rows, {
    subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z",
  });
  assert.deepEqual(records, []);
});

test("invalid available ASC proceeds fail closed instead of falling back to RevenueCat", () => {
  const records = mobileAppsRowsToFinancialRecords([{
    ...row("anicca-ios", "2026-09-26", 12.5),
    sources: {
      revenuecat: row("anicca-ios", "2026-09-26", 12.5).sources.revenuecat,
      app_store_financial: { status: "available", data: { report_status: "pending" } },
    },
  }], { subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z" });
  assert.deepEqual(records, []);
});

test("zero revenue, unavailable status, and unknown products yield nothing fabricated", () => {
  const options = { subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z" };
  assert.deepEqual(mobileAppsRowsToFinancialRecords([row("anicca-ios", "2026-09-26", 0)], options), []);
  assert.deepEqual(
    mobileAppsRowsToFinancialRecords([row("honne-ai", "2026-09-26", 5, { unavailable: true })], options),
    [],
  );
  assert.deepEqual(
    mobileAppsRowsToFinancialRecords([row("some-other-product", "2026-09-26", 5)], options),
    [],
  );
  assert.deepEqual(mobileAppsRowsToFinancialRecords(null, options), []);
});

test("Financial Manager totals exclude persisted RevenueCat estimates when settled ASC proceeds exist", () => {
  const options = { subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z" };
  const estimate = mobileAppsRowsToFinancialRecords([row("anicca-ios", "2026-09-26", 12.5)], options)[0];
  // Simulate an estimate written by the previous version before estimate-only records were marked unverified.
  const legacyEstimate = { ...estimate, verification: { ...estimate.verification, status: "verified" } };
  const settledRows = financeReportRows({
    "anicca-ios": [{ ...mappedAniccaSubscriptionRow(0), partner_share_currency: "USD",
      extended_partner_share: "9.99", sale_or_return: "S", product_type_identifier: "IA1",
      transaction_date: "2026-09-26", settlement_date: "2026-09-30" }],
  }, { reportId: "sales-2026-09", reportSha256: "d".repeat(64),
    periodStart: "2026-09-01", periodEnd: "2026-09-30" });
  const settled = mobileAppsRowsToFinancialRecords(settledRows, options);
  const { report } = buildFinancialManagerReport([legacyEstimate, ...settled], "2026-09-30");
  assert.deepEqual(report.business.revenue, [{ currency: "USD", amountMinor: 999 }]);
  assert.deepEqual(report.business.byProvider.map(({ provider }) => provider), ["app-store-connect-financial"]);
});
