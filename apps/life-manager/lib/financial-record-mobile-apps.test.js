"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { mobileAppsRowsToFinancialRecords } = require("./financial-record-mobile-apps.js");
const { projectFinancialRecord } = require("./financial-record-contract.js");

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

test("available RevenueCat revenue becomes a verified business_revenue record", () => {
  const records = mobileAppsRowsToFinancialRecords([row("anicca-ios", "2026-09-26", 12.5)], {
    subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z",
  });
  for (const record of records) projectFinancialRecord(record);
  assert.equal(records.length, 1);
  assert.equal(records[0].amount_minor, 1250);
  assert.equal(records[0].currency, "UNKNOWN");
  assert.equal(records[0].kind, "business_revenue");
  assert.equal(records[0].source.provider, "mobile-apps");
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
          apple_identifier: "6755129214", period_start: "2026-09-01", period_end: "2026-09-30",
          rows: [{ source_row_index: 0, partner_share_currency: "USD", extended_partner_share: "9.99",
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
