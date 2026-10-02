"use strict";

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const DEFAULT_REQUIRED_SOURCES = Object.freeze(["moneytree", "businessReadback", "googleBilling"]);

function addDays(value, days) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

function validReceipt(row) {
  return ["sent", "duplicate"].includes(row?.delivery?.status)
    && typeof row.delivery.providerMessageId === "string"
    && row.delivery.providerMessageId.trim().length > 0;
}

function sourceFailures(row, requiredSources) {
  const freshness = row?.sourceFreshness;
  if (!freshness || typeof freshness !== "object" || Array.isArray(freshness)) {
    return ["source_freshness_missing"];
  }
  const failures = [];
  for (const source of requiredSources) {
    const value = freshness[source];
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      failures.push(`source_freshness_missing:${source}`);
    } else if (value.status !== "fresh") {
      failures.push(`source_not_fresh:${source}`);
    }
  }
  return failures;
}

function evaluateCfoObservationPeriods(periods, {
  requiredDays = 7,
  latestDate = null,
  requiredSources = DEFAULT_REQUIRED_SOURCES,
} = {}) {
  if (!Number.isInteger(requiredDays) || requiredDays < 1 || requiredDays > 31) {
    throw new Error("cfo observation required days invalid");
  }
  if (!Array.isArray(requiredSources) || requiredSources.length === 0
    || requiredSources.some((source) => typeof source !== "string" || !source.trim())) {
    throw new Error("cfo observation required sources invalid");
  }
  const byDate = new Map();
  const failures = [];
  for (const row of Array.isArray(periods) ? periods : []) {
    const date = String(row?.reportingDate || "");
    if (!DATE.test(date)) {
      failures.push("reporting_date_invalid");
      continue;
    }
    if (byDate.has(date)) {
      failures.push(`duplicate_period:${date}`);
      continue;
    }
    byDate.set(date, row);
  }
  const available = [...byDate.keys()].sort();
  const end = latestDate == null ? available.at(-1) : String(latestDate);
  if (!end || !DATE.test(end)) throw new Error("cfo observation latest date invalid");
  const expected = Array.from({ length: requiredDays }, (_, index) => (
    addDays(end, index - requiredDays + 1)
  ));
  const missing = expected.filter((date) => !byDate.has(date));
  failures.push(...missing.map((date) => `period_missing:${date}`));

  let deliveryDays = 0;
  let freshDays = 0;
  let settledCostDays = 0;
  for (const date of expected) {
    const row = byDate.get(date);
    if (!row) continue;
    if (validReceipt(row)) deliveryDays += 1;
    else failures.push(`delivery_receipt_missing:${date}`);
    const sourceErrors = sourceFailures(row, requiredSources);
    if (sourceErrors.length === 0) freshDays += 1;
    failures.push(...sourceErrors.map((error) => `${error}:${date}`));
    if (row.providerCostSettlement?.status === "settled") settledCostDays += 1;
  }
  const contiguous = missing.length === 0;
  const ready = contiguous && deliveryDays === requiredDays;
  const complete = ready && freshDays === requiredDays && settledCostDays === requiredDays;
  return Object.freeze({
    schemaVersion: 1, requiredDays, latestDate: end, expectedDays: expected,
    observedDays: expected.filter((date) => byDate.has(date)),
    deliveryDays, freshDays, settledCostDays, ready, complete,
    failures: [...new Set(failures)].sort(),
  });
}

module.exports = { DEFAULT_REQUIRED_SOURCES, evaluateCfoObservationPeriods };
