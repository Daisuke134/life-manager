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
