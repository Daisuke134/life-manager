"use strict";

const { createHash } = require("node:crypto");

// Projects marketing-metrics-daily's business-outcomes.jsonl (RevenueCat "revenue" chart,
// collected by skills/earn/marketing-engine/measure/business_outcomes.py) into FinancialRecords.
// RevenueCat estimates remain unverified. The producer retains the chart's explicit yaxis_currency
// when present; missing or unsupported currency stays UNKNOWN.

const { financialRecordId } = require("./financial-record-contract.js");

const ASC_APP_IDS = {
  "anicca-ios": "6755129214",
  "honne-ai": "6759667221",
  "dhamma-quotes": "6757726663",
  "sleep-reset": "6762143790",
  "studio-cherie": "6766485903",
  "thankful": "6759514159",
  "breath-reset": "6760253231",
  "sleep-ritual": "6759916261",
  "desk-stretch-timer": "6760048397",
  "micro-mood": "6759877003",
};
const MOBILE_APPS_PRODUCTS = Object.freeze(Object.keys(ASC_APP_IDS));
const UNKNOWN_CURRENCY = "UNKNOWN";
const CURRENCY_EXPONENTS = { JPY: 0, USD: 2, EUR: 2, GBP: 2 };
const SHA256 = /^[a-f0-9]{64}$/;

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.keys(value).sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`);
    return `{${entries.join(",")}}`;
  }
  const serialized = JSON.stringify(value);
  if (serialized === undefined) throw new TypeError("canonical_json_undefined");
  return serialized;
}

function canonicalSha256(value) {
  return createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function ascFinancialReportKey(data) {
  return JSON.stringify([
    data.report_id, data.report_sha256, data.content_sha256, data.report_status,
    data.period_start, data.period_end, data.unassigned_row_count,
    data.unassigned_rows_sha256, data.report_evidence_ref, data.unassigned_evidence_ref,
  ]);
}

function validUnassignedEvidenceRef(data) {
  const prefix = `appstoreconnect://financial-report-mappings/${data.report_id}/`;
  return typeof data.unassigned_evidence_ref === "string"
    && data.unassigned_evidence_ref.startsWith(prefix)
    && SHA256.test(data.unassigned_evidence_ref.slice(prefix.length));
}

function verifiedAscFinancialReportKeys(rows) {
  const groups = new Map();
  for (const row of rows) {
    const source = row?.sources?.app_store_financial;
    if (!source || source.status !== "available") continue;
    const data = source.data;
    if (!data || typeof data.report_id !== "string") continue;

    const key = ascFinancialReportKey(data);
    let group = groups.get(key);
    if (!group) {
      group = { invalid: false, sourcesByProduct: new Map(), rowsByIndex: new Map(), data };
      groups.set(key, group);
    }
    const appId = ASC_APP_IDS[row.product_id];
    const reportIdValid = /^[a-zA-Z0-9._:-]+$/.test(data.report_id);
    const envelopeValid = data.report_status === "final"
      && reportIdValid
      && SHA256.test(String(data.report_sha256 || ""))
      && SHA256.test(String(data.content_sha256 || ""))
      && SHA256.test(String(data.unassigned_rows_sha256 || ""))
      && Number.isInteger(data.unassigned_row_count)
      && data.unassigned_row_count >= 0
      && data.app_id === appId
      && typeof data.period_start === "string"
      && /^\d{4}-\d{2}-\d{2}$/.test(data.period_start)
      && typeof data.period_end === "string"
      && /^\d{4}-\d{2}-\d{2}$/.test(data.period_end)
      && data.period_start <= data.period_end
      && data.report_evidence_ref
        === `appstoreconnect://financial-reports/${data.report_id}/${data.report_sha256}`
      && validUnassignedEvidenceRef(data)
      && Array.isArray(data.rows)
      && SHA256.test(String(source.evidence_sha256 || ""))
      && source.evidence_sha256 === canonicalSha256(data);
    if (!envelopeValid || !appId || typeof row.business_date !== "string") {
      group.invalid = true;
      continue;
    }

    const previous = group.sourcesByProduct.get(row.product_id);
    if (!previous || row.business_date > previous.businessDate) {
      group.sourcesByProduct.set(row.product_id, { businessDate: row.business_date, data });
    } else if (row.business_date === previous.businessDate
      && canonicalSha256(previous.data) !== canonicalSha256(data)) {
      group.invalid = true;
    }

    for (const item of data.rows) {
      if (!item || typeof item !== "object" || Array.isArray(item)
        || !Number.isInteger(item.source_row_index) || item.source_row_index < 0) {
        group.invalid = true;
        continue;
      }
      const existing = group.rowsByIndex.get(item.source_row_index);
      if (existing) {
        if (existing.productId !== row.product_id
          || canonicalSha256(existing.item) !== canonicalSha256(item)) group.invalid = true;
      } else {
        group.rowsByIndex.set(item.source_row_index, { productId: row.product_id, item });
      }
    }
  }

  const valid = new Set();
  for (const [key, group] of groups) {
    if (group.invalid || group.sourcesByProduct.size !== MOBILE_APPS_PRODUCTS.length
      || MOBILE_APPS_PRODUCTS.some((productId) => !group.sourcesByProduct.has(productId))) continue;
    const data = group.data;
    const reportContent = {
      report_id: data.report_id,
      report_status: data.report_status,
      period_start: data.period_start,
      period_end: data.period_end,
      unassigned_row_count: data.unassigned_row_count,
      unassigned_rows_sha256: data.unassigned_rows_sha256,
      rows: [...group.rowsByIndex.values()].map(({ item }) => item)
        .sort((left, right) => left.source_row_index - right.source_row_index),
    };
    if (canonicalSha256(reportContent) === data.content_sha256) valid.add(key);
  }
  return valid;
}

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
  if (exponent == null || !Number.isFinite(number)) return null;
  const amount = Math.round(number * (10 ** exponent));
  return Number.isSafeInteger(amount) ? amount : null;
}

function ascFinancialRecords(row, { subjectId, observedAt } = {}, verifiedReportKeys = new Set()) {
  const source = row?.sources?.app_store_financial;
  if (!source || source.status !== "available") return { available: false, records: [] };
  const data = source.data;
  if (!data || data.report_status !== "final" || typeof data.report_id !== "string"
    || !/^[a-zA-Z0-9._:-]+$/.test(data.report_id)
    || data.app_id !== ASC_APP_IDS[row.product_id]
    || !/^\d{4}-\d{2}-\d{2}$/.test(String(data.period_start || ""))
    || !/^\d{4}-\d{2}-\d{2}$/.test(String(data.period_end || ""))
    || data.period_start > data.period_end
    || !SHA256.test(String(data.report_sha256 || ""))
    || !SHA256.test(String(data.content_sha256 || ""))
    || !SHA256.test(String(data.unassigned_rows_sha256 || ""))
    || !Number.isInteger(data.unassigned_row_count) || data.unassigned_row_count < 0
    || data.report_evidence_ref
      !== `appstoreconnect://financial-reports/${data.report_id}/${data.report_sha256}`
    || !validUnassignedEvidenceRef(data)
    || !verifiedReportKeys.has(ascFinancialReportKey(data))
    || !Array.isArray(data.rows)) return { available: true, records: [] };
  const records = [];
  for (const item of data.rows) {
    if (!item || !Number.isInteger(item.source_row_index) || item.source_row_index < 0) return { available: true, records: [] };
    const catalogType = item.catalog_record_type;
    const catalogCollection = catalogType === "subscription" ? "subscriptions"
      : catalogType === "in_app_purchase" ? "in-app-purchases" : null;
    const catalogEvidenceRef = catalogCollection
      ? `appstoreconnect://${catalogCollection}/${item.catalog_record_id}` : null;
    const currency = String(item.partner_share_currency || "").toUpperCase();
    const amount = ascMinorAmount(item.extended_partner_share, currency);
    const sale = item.sale_or_return;
    if (amount == null || !["S", "R"].includes(sale)
      || !item.apple_identifier || item.apple_identifier !== item.catalog_record_id
      || !item.sku || item.sku !== item.catalog_product_id
      || item.parent_app_id !== data.app_id
      || !catalogEvidenceRef || item.catalog_evidence_ref !== catalogEvidenceRef
      || !/^[a-f0-9]{64}$/.test(String(item.catalog_evidence_sha256 || ""))
      || (sale === "S" && amount < 0) || (sale === "R" && amount > 0)) {
      return { available: true, records: [] };
    }
    if (amount === 0) continue;
    const transactionDate = String(item.transaction_date || item.settlement_date || "");
    const settlementDate = String(item.settlement_date || "");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(transactionDate) || !/^\d{4}-\d{2}-\d{2}$/.test(settlementDate)
      || transactionDate > settlementDate || settlementDate < data.period_start || settlementDate > data.period_end) {
      return { available: true, records: [] };
    }
    const verifiedAt = source.observed_at || row.observed_at || observedAt;
    if (typeof verifiedAt !== "string" || !Number.isFinite(Date.parse(verifiedAt))
      || !(/[zZ]|[+-]\d\d:\d\d$/.test(verifiedAt))) return { available: true, records: [] };
    const idempotencyKey = `mobile-apps-asc:v1:${row.product_id}:${data.report_id}:${item.source_row_index}`;
    records.push({
      schema_version: 1, record_type: "financial_record",
      record_id: financialRecordId(subjectId, idempotencyKey), subject_id: subjectId,
      scope: "business", kind: sale === "S" ? "business_revenue" : "business_cost",
      direction: sale === "S" ? "credit" : "debit", amount_minor: Math.abs(amount), currency,
      occurred_at: `${settlementDate}T00:00:00Z`, recorded_at: observedAt,
      idempotency_key: idempotencyKey,
      source: { provider: "app-store-connect-financial", source_type: "app_store", external_ref: `${data.report_id}:${item.source_row_index}` },
      verification: { status: "verified", observed_at: verifiedAt,
        evidence_refs: [
          `appstoreconnect://financial-reports/${data.report_id}/${data.report_sha256}/rows/${item.source_row_index}`,
          data.unassigned_evidence_ref,
          item.catalog_evidence_ref,
        ] },
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
  const verifiedReportKeys = verifiedAscFinancialReportKeys(rows);
  for (const row of rows) {
    const productId = row && row.product_id;
    const businessDate = row && row.business_date;
    if (!allowed.has(productId) || typeof businessDate !== "string" || !businessDate) continue;
    const asc = ascFinancialRecords(row, { subjectId, observedAt }, verifiedReportKeys);
    if (asc.available) {
      records.push(...asc.records);
      continue;
    }
    const revenuecat = row.sources && row.sources.revenuecat;
    if (!revenuecat || revenuecat.status !== "available") continue;
    const charts = revenuecat.data && revenuecat.data.charts;
    const value = chartValue(charts, "revenue", "Revenue");
    if (value === null) continue;
    const chartCurrency = String(charts?.revenue?.currency || "").toUpperCase();
    const hasCurrency = Object.prototype.hasOwnProperty.call(CURRENCY_EXPONENTS, chartCurrency);
    const currency = hasCurrency ? chartCurrency : UNKNOWN_CURRENCY;
    const amountMinor = toMinor(value, hasCurrency ? CURRENCY_EXPONENTS[currency] : 2);
    if (amountMinor === null || amountMinor === 0) continue;
    const idempotencyKey = `mobile-apps-financial:v2:${productId}:${businessDate}:revenue`;
    records.push({
      schema_version: 1,
      record_type: "financial_record",
      record_id: financialRecordId(subjectId, idempotencyKey),
      subject_id: subjectId,
      scope: "business",
      kind: "business_revenue",
      direction: "credit",
      amount_minor: amountMinor,
      currency,
      occurred_at: `${businessDate}T00:00:00Z`,
      recorded_at: observedAt,
      idempotency_key: idempotencyKey,
      source: { provider: "mobile-apps", source_type: "app_store", external_ref: `${productId}:${businessDate}` },
      verification: {
        status: "unverified", observed_at: observedAt,
        evidence_refs: [`revenuecat://${productId}/revenue/${businessDate}`],
      },
    });
  }
  return records;
}

module.exports = { mobileAppsRowsToFinancialRecords, MOBILE_APPS_PRODUCTS, ascFinancialRecords };
