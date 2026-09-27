"use strict";

// Projects capafy_hourly_reconcile.py's daily revenue trend (capafy-skill-analytics.json,
// field daily_revenue_trend_last_30d) into FinancialRecords: one business_revenue record
// per day with gross revenue, one business_cost record per day with refunds. Zero-value
// days emit nothing (a successful zero is not a fabricated record).

const { financialRecordId } = require("./financial-record-contract.js");

function toMinor(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return 0;
  return Math.round(number * 100);
}

function capafyRowsToFinancialRecords(rows, { subjectId, observedAt }) {
  if (!Array.isArray(rows)) return [];
  const records = [];
  for (const row of rows) {
    const date = row && row.date;
    if (typeof date !== "string" || !date) continue;
    const occurredAt = `${date}T00:00:00Z`;
    const components = [
      ["revenue", "business_revenue", "credit", toMinor(row.revenue)],
      ["refund", "business_cost", "debit", toMinor(row.refundAmount)],
    ];
    for (const [component, kind, direction, amountMinor] of components) {
      if (amountMinor <= 0) continue;
      const idempotencyKey = `capafy-financial:v1:${date}:${component}`;
      records.push({
        schema_version: 1,
        record_type: "financial_record",
        record_id: financialRecordId(subjectId, idempotencyKey),
        subject_id: subjectId,
        scope: "business",
        kind,
        direction,
        amount_minor: amountMinor,
        currency: "USD",
        occurred_at: occurredAt,
        recorded_at: observedAt,
        idempotency_key: idempotencyKey,
        source: { provider: "capafy", source_type: "marketplace", external_ref: date },
        verification: {
          status: "verified", observed_at: observedAt,
          evidence_refs: [`capafy://revenue-trend/${date}/${component}`],
        },
      });
    }
  }
  return records;
}

module.exports = { capafyRowsToFinancialRecords };
