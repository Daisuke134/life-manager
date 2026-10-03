"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { mobileAppsRowsToFinancialRecords } = require("./financial-record-mobile-apps.js");
const { projectFinancialRecord } = require("./financial-record-contract.js");
const { buildFinancialManagerReport } = require("./financial-manager-report.js");

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

test("all six CFO-bound RevenueCat products can be ingested as separate estimates", () => {
  const products = ["anicca-ios", "honne-ai", "breath-reset", "sleep-ritual", "desk-stretch-timer", "micro-mood"];
  const records = mobileAppsRowsToFinancialRecords(products.map((productId) => row(productId, "2026-09-26", 1)), {
    subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z",
  });
  assert.deepEqual(records.map((record) => record.idempotency_key.split(":")[2]).sort(), [...products].sort());
  assert.ok(records.every((record) => record.verification.status === "unverified"));
});

test("final ASC proceeds supersede RevenueCat chart revenue without double counting", () => {
  const records = mobileAppsRowsToFinancialRecords([{
    ...row("anicca-ios", "2026-09-26", 12.5),
    sources: {
      revenuecat: row("anicca-ios", "2026-09-26", 12.5).sources.revenuecat,
      app_store_financial: {
        status: "available",
        data: {
          report_id: "sales-2026-09", report_sha256: "a".repeat(64), report_status: "final",
          app_id: "6755129214", period_start: "2026-09-01", period_end: "2026-10-01",
          rows: [{ ...mappedAniccaSubscriptionRow(0), partner_share_currency: "USD", extended_partner_share: "9.99",
            sale_or_return: "S", product_type_identifier: "IA1", transaction_date: "2026-09-26", settlement_date: "2026-10-01" }],
        },
      },
    },
  }], { subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z" });
  assert.equal(records.length, 1);
  assert.equal(records[0].amount_minor, 999);
  assert.equal(records[0].currency, "USD");
  assert.equal(records[0].source.provider, "app-store-connect-financial");
  assert.equal(records[0].verification.status, "verified");
  assert.equal(records[0].occurred_at, "2026-10-01T00:00:00Z");
});

test("ASC detail rows must match the mapped app identifier", () => {
  const records = mobileAppsRowsToFinancialRecords([{
    ...row("anicca-ios", "2026-09-26", 12.5),
    sources: {
      app_store_financial: { status: "available", data: {
        report_id: "sales-2026-09", report_sha256: "a".repeat(64), report_status: "final",
        apple_identifier: "6755129214", period_start: "2026-09-01", period_end: "2026-09-30",
        rows: [{ source_row_index: 0, apple_identifier: "6762049696", partner_share_currency: "JPY",
          extended_partner_share: "4250", sale_or_return: "S", product_type_identifier: "IAY",
          transaction_date: "2026-09-12", settlement_date: "2026-09-12" }],
      } },
    },
  }], { subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z" });
  assert.deepEqual(records, []);
});

test("ASC subscription ID plus exact SKU map settled proceeds to the parent app", () => {
  const records = mobileAppsRowsToFinancialRecords([{
    ...row("anicca-ios", "2026-10-02", 99.99),
    sources: {
      revenuecat: row("anicca-ios", "2026-10-02", 99.99).sources.revenuecat,
      app_store_financial: { status: "available", data: {
        report_id: "finance-2026-12-Z1", report_sha256: "e".repeat(64), report_status: "final",
        app_id: "6755129214", period_start: "2026-08-30", period_end: "2026-09-26",
        rows: [{ source_row_index: 0, apple_identifier: "6762049696",
          sku: "ai.anicca.app.ios.yearly.b", parent_app_id: "6755129214",
          catalog_record_type: "subscription", catalog_record_id: "6762049696",
          catalog_product_id: "ai.anicca.app.ios.yearly.b",
          catalog_evidence_ref: "appstoreconnect://subscriptions/6762049696",
          catalog_evidence_sha256: "f".repeat(64), partner_share_currency: "JPY",
          extended_partner_share: "4250", sale_or_return: "S",
          product_type_identifier: "IAY", transaction_date: "2026-09-12",
          settlement_date: "2026-09-12" }],
      } },
    },
  }], { subjectId: "tenant-1", observedAt: "2026-10-03T00:00:00Z" });
  assert.equal(records.length, 1);
  assert.equal(records[0].amount_minor, 4250);
  assert.equal(records[0].currency, "JPY");
  assert.equal(records[0].verification.status, "verified");
  assert.equal(records[0].idempotency_key, "mobile-apps-asc:v1:anicca-ios:finance-2026-12-Z1:0");
});

test("ASC negative return rows become positive debit refunds", () => {
  const records = mobileAppsRowsToFinancialRecords([{
    ...row("anicca-ios", "2026-09-26", 12.5),
    sources: {
      app_store_financial: { status: "available", data: {
        report_id: "sales-2026-09", report_sha256: "b".repeat(64), report_status: "final",
        app_id: "6755129214", period_start: "2026-09-01", period_end: "2026-09-30",
        rows: [{ ...mappedAniccaSubscriptionRow(1), partner_share_currency: "USD",
          extended_partner_share: "-1.25", sale_or_return: "R", product_type_identifier: "IA1",
          transaction_date: "2026-09-20", settlement_date: "2026-09-25" }],
      } },
    },
  }], { subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z" });
  assert.equal(records.length, 1);
  assert.equal(records[0].kind, "business_cost");
  assert.equal(records[0].direction, "debit");
  assert.equal(records[0].amount_minor, 125);
});

test("ASC detail rows settled outside their final report period fail closed", () => {
  const records = mobileAppsRowsToFinancialRecords([{
    ...row("anicca-ios", "2026-09-26", 12.5),
    sources: {
      app_store_financial: { status: "available", data: {
        report_id: "sales-2026-09", report_sha256: "c".repeat(64), report_status: "final",
        app_id: "6755129214", period_start: "2026-09-01", period_end: "2026-09-30",
        rows: [{ ...mappedAniccaSubscriptionRow(2), partner_share_currency: "USD",
          extended_partner_share: "9.99", sale_or_return: "S", product_type_identifier: "IA1",
          transaction_date: "2026-09-26", settlement_date: "2026-10-01" }],
      } },
    },
  }], { subjectId: "tenant-1", observedAt: "2026-10-02T00:00:00Z" });
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
  const settled = mobileAppsRowsToFinancialRecords([{
    ...row("anicca-ios", "2026-09-26", 12.5),
    sources: {
      app_store_financial: { status: "available", data: {
        report_id: "sales-2026-09", report_sha256: "d".repeat(64), report_status: "final",
        app_id: "6755129214", period_start: "2026-09-01", period_end: "2026-09-30",
        rows: [{ ...mappedAniccaSubscriptionRow(0), partner_share_currency: "USD",
          extended_partner_share: "9.99", sale_or_return: "S", product_type_identifier: "IA1",
          transaction_date: "2026-09-26", settlement_date: "2026-09-30" }],
      } },
    },
  }], options);
  const { report } = buildFinancialManagerReport([legacyEstimate, ...settled], "2026-09-30");
  assert.deepEqual(report.business.revenue, [{ currency: "USD", amountMinor: 999 }]);
  assert.deepEqual(report.business.byProvider.map(({ provider }) => provider), ["app-store-connect-financial"]);
});
