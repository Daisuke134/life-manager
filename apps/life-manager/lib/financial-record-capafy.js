"use strict";

// Projects capafy_hourly_reconcile.py's daily revenue trend (capafy-skill-analytics.json,
// field daily_revenue_trend_last_30d) into FinancialRecords: one business_revenue record
// per day with gross revenue, one business_cost record per day with refunds. Zero-value
// days emit nothing (a successful zero is not a fabricated record).

const { financialRecordId, projectFinancialRecord } = require("./financial-record-contract.js");

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

// This service-owned reader accepts only a trusted collector, never a VM/model receipt.
async function readCapafyFinancialRecords({ binding, periodStart, periodEnd } = {}, { readOfficialSnapshot } = {}) {
  if (typeof readOfficialSnapshot !== "function") throw new Error("capafy_collector_unconfigured");
  const invalid = () => { throw new Error("capafy_snapshot_invalid"); };
  const day = (value) => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
  if (!binding || binding.provider !== "capafy"
    || !/^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(binding.tenantId || "")
    || typeof binding.subjectId !== "string" || !binding.subjectId.trim()
    || !day(periodStart) || !day(periodEnd) || periodStart > periodEnd) invalid();
  const owner = Object.freeze({ ...binding });
  let snapshot;
  try { snapshot = await readOfficialSnapshot({ binding: owner, periodStart, periodEnd }); }
  catch { throw new Error("capafy_snapshot_unavailable"); }
  if (!snapshot || snapshot.tenantId !== owner.tenantId || snapshot.provider !== "capafy"
    || snapshot.subjectId !== owner.subjectId || snapshot.complete !== true || snapshot.currency !== "USD"
    || snapshot.periodStart !== periodStart || snapshot.periodEnd !== periodEnd
    || typeof snapshot.observedAt !== "string" || !Number.isFinite(Date.parse(snapshot.observedAt))
    || !/(Z|[+-]\d{2}:\d{2})$/.test(snapshot.observedAt)
    || Date.parse(snapshot.observedAt) < Date.parse(periodEnd)
    || !Array.isArray(snapshot.rows) || !Array.isArray(snapshot.evidenceRefs)
    || snapshot.evidenceRefs.length < 1 || snapshot.evidenceRefs.length > 32
    || snapshot.evidenceRefs.some((ref) => typeof ref !== "string" || !/^capafy:\/\/[A-Za-z0-9._:/-]{1,512}$/.test(ref))) invalid();
  const minor = (value) => {
    if (!["string", "number"].includes(typeof value) || !/^\d+(?:\.\d{1,2})?$/.test(String(value))) invalid();
    const [whole, fraction = ""] = String(value).split(".");
    const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
    if (cents > BigInt(Number.MAX_SAFE_INTEGER)) invalid();
    return Number(cents);
  };
  const amounts = new Map();
  for (const row of snapshot.rows) {
    if (!row || !day(row.date) || row.date < periodStart || row.date > periodEnd || amounts.has(row.date)) invalid();
    amounts.set(row.date, { business_revenue: minor(row.revenue), business_cost: minor(row.refundAmount) });
  }
  try {
    return capafyRowsToFinancialRecords(snapshot.rows, { subjectId: owner.tenantId, observedAt: snapshot.observedAt })
      .map((record) => projectFinancialRecord({ ...record,
        amount_minor: amounts.get(record.source.external_ref)[record.kind],
        verification: { ...record.verification, evidence_refs: [...snapshot.evidenceRefs] },
      }));
  } catch { return invalid(); }
}

module.exports = { capafyRowsToFinancialRecords, readCapafyFinancialRecords };
