"use strict";

// Projects marketing-metrics-daily's business-outcomes.jsonl (RevenueCat "revenue" chart,
// collected by skills/earn/marketing-engine/measure/business_outcomes.py) into FinancialRecords.
// RevenueCat's chart API returns no currency field for these apps, so the currency is honestly
// recorded as UNKNOWN rather than assumed to be USD (same convention skills/cfo/loop_pnl.py uses).

const { financialRecordId } = require("./financial-record-contract.js");

const MOBILE_APPS_PRODUCTS = ["anicca-ios", "honne-ai"];
const UNKNOWN_CURRENCY = "UNKNOWN";

function toMinor(value, exponent) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  const amount = Math.round(number * 10 ** exponent);
  return amount >= 0 ? amount : null;
}

function chartValue(charts, chartName, metricName) {
  const chart = charts && charts[chartName];
  const latest = chart && chart.latest_complete;
  const metric = latest && latest[metricName];
  if (metric && typeof metric === "object" && metric.incomplete !== true
    && typeof metric.value === "number") return metric.value;
  return null;
}

function mobileAppsRowsToFinancialRecords(rows, {
  subjectId, observedAt, products = MOBILE_APPS_PRODUCTS,
} = {}) {
  if (!Array.isArray(rows)) return [];
  const allowed = new Set(products);
  const records = [];
  for (const row of rows) {
    const productId = row && row.product_id;
    const businessDate = row && row.business_date;
    if (!allowed.has(productId) || typeof businessDate !== "string" || !businessDate) continue;
    const revenuecat = row.sources && row.sources.revenuecat;
    if (!revenuecat || revenuecat.status !== "available") continue;
    const value = chartValue(revenuecat.data && revenuecat.data.charts, "revenue", "Revenue");
    if (value === null) continue;
    // RevenueCat charts are USD-decimal (2-exponent); an unknown currency is still recorded
    // in its 2-decimal minor unit since that is the only scale the provider exposes.
    const amountMinor = toMinor(value, 2);
    if (amountMinor === null || amountMinor === 0) continue;
    const idempotencyKey = `mobile-apps-financial:v1:${productId}:${businessDate}:revenue`;
    records.push({
      schema_version: 1,
      record_type: "financial_record",
      record_id: financialRecordId(subjectId, idempotencyKey),
      subject_id: subjectId,
      scope: "business",
      kind: "business_revenue",
      direction: "credit",
      amount_minor: amountMinor,
      currency: UNKNOWN_CURRENCY,
      occurred_at: `${businessDate}T00:00:00Z`,
      recorded_at: observedAt,
      idempotency_key: idempotencyKey,
      source: { provider: "mobile-apps", source_type: "app_store", external_ref: `${productId}:${businessDate}` },
      verification: {
        status: "verified", observed_at: observedAt,
        evidence_refs: [`revenuecat://${productId}/revenue/${businessDate}`],
      },
    });
  }
  return records;
}

module.exports = { mobileAppsRowsToFinancialRecords, MOBILE_APPS_PRODUCTS };
