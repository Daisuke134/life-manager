"use strict";

// Projects marketing-metrics-daily's business-outcomes.jsonl (RevenueCat "revenue" chart,
// collected by skills/earn/marketing-engine/measure/business_outcomes.py) into FinancialRecords.
// RevenueCat's chart API returns no currency field for these apps, so the currency is honestly
// recorded as UNKNOWN rather than assumed to be USD (same convention skills/cfo/loop_pnl.py uses).

const { financialRecordId } = require("./financial-record-contract.js");

const MOBILE_APPS_PRODUCTS = ["anicca-ios", "honne-ai"];
const ASC_APP_IDS = { "anicca-ios": "6755129214", "honne-ai": "6759667221" };
const UNKNOWN_CURRENCY = "UNKNOWN";
const CURRENCY_EXPONENTS = { JPY: 0, USD: 2, EUR: 2, GBP: 2 };

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

function ascMinorAmount(value, currency) {
  const exponent = CURRENCY_EXPONENTS[currency];
  const number = Number(value);
  if (exponent == null || !Number.isFinite(number) || number < 0) return null;
  const amount = Math.round(number * (10 ** exponent));
  return Number.isSafeInteger(amount) ? amount : null;
}

function ascFinancialRecords(row, { subjectId, observedAt } = {}) {
  const source = row?.sources?.app_store_financial;
  if (!source || source.status !== "available") return { available: false, records: [] };
  const data = source.data;
  if (!data || data.report_status !== "final" || typeof data.report_id !== "string"
    || !/^[a-zA-Z0-9._:-]+$/.test(data.report_id)
    || data.apple_identifier !== ASC_APP_IDS[row.product_id]
    || !/^[a-f0-9]{64}$/.test(String(data.report_sha256 || ""))
    || !Array.isArray(data.rows)) return { available: true, records: [] };
  const records = [];
  for (const item of data.rows) {
    if (!item || !Number.isInteger(item.source_row_index) || item.source_row_index < 0) return { available: true, records: [] };
    const currency = String(item.partner_share_currency || "").toUpperCase();
    const amount = ascMinorAmount(item.extended_partner_share, currency);
    const sale = item.sale_or_return;
    if (amount == null || !["S", "R"].includes(sale)) return { available: true, records: [] };
    if (amount === 0) continue;
    const transactionDate = String(item.transaction_date || item.settlement_date || "");
    const settlementDate = String(item.settlement_date || "");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(transactionDate) || !/^\d{4}-\d{2}-\d{2}$/.test(settlementDate)
      || transactionDate > settlementDate) return { available: true, records: [] };
    const idempotencyKey = `mobile-apps-asc:v1:${row.product_id}:${data.report_id}:${item.source_row_index}`;
    records.push({
      schema_version: 1, record_type: "financial_record",
      record_id: financialRecordId(subjectId, idempotencyKey), subject_id: subjectId,
      scope: "business", kind: sale === "S" ? "business_revenue" : "business_cost",
      direction: sale === "S" ? "credit" : "debit", amount_minor: amount, currency,
      occurred_at: `${transactionDate}T00:00:00Z`, recorded_at: observedAt,
      idempotency_key: idempotencyKey,
      source: { provider: "app-store-connect-financial", source_type: "app_store", external_ref: `${data.report_id}:${item.source_row_index}` },
      verification: { status: "verified", observed_at: observedAt,
        evidence_refs: [`appstoreconnect://financial-reports/${data.report_id}/${data.report_sha256}#${item.source_row_index}`] },
    });
  }
  return { available: true, records };
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
    const asc = ascFinancialRecords(row, { subjectId, observedAt });
    if (asc.available) {
      records.push(...asc.records);
      continue;
    }
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

module.exports = { mobileAppsRowsToFinancialRecords, MOBILE_APPS_PRODUCTS, ascFinancialRecords };
