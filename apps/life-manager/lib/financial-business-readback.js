"use strict";

const crypto = require("node:crypto");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonical(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function uniqueGaps(projection) {
  const gaps = [];
  const visit = (value) => {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (Array.isArray(value.coverage_gaps)) {
      for (const gap of value.coverage_gaps) {
        if (!gap || typeof gap !== "object") continue;
        const normalized = {
          ...(gap.product_loop_id ? { product_loop_id: String(gap.product_loop_id) } : {}),
          ...(gap.source_id ? { source_id: String(gap.source_id) } : {}),
          ...(gap.reason ? { reason: String(gap.reason) } : {}),
          ...(gap.category ? { category: String(gap.category) } : {}),
        };
        if (normalized.reason) gaps.push(normalized);
      }
    }
    Object.values(value).forEach(visit);
  };
  visit(projection);
  const seen = new Map();
  for (const gap of gaps) seen.set(canonical(gap), gap);
  return [...seen.values()].sort((left, right) => canonical(left).localeCompare(canonical(right)));
}

function unavailable(reason) {
  const gapReason = String(reason || "read_failed").replace(/[^a-z0-9_:-]/gi, "_").slice(0, 80) || "read_failed";
  return Object.freeze({
    status: "unavailable", table: null, observedAt: null, sourceReceiptRefs: [],
    coverageGaps: [{ source_id: "loop-pnl", reason: gapReason }],
    businessSourceCoverage: [{
      source: "loop-pnl", state: "unavailable", observedAt: null, receiptCount: 0,
      gapReason,
    }],
  });
}

function readBusinessReadback({
  reportingDate, trailingStart = null, pythonBin = "python3", env = process.env,
  scriptPath = path.resolve(__dirname, "../../../skills/cfo/loop_pnl.py"), timeoutMs = 120_000,
} = {}) {
  if (!DATE.test(String(reportingDate || ""))) return unavailable("reporting_date_invalid");
  const args = [scriptPath, "--date", String(reportingDate), "--json"];
  if (trailingStart != null) args.push("--trailing-start", String(trailingStart));
  let result;
  try {
    result = spawnSync(pythonBin, args, {
      encoding: "utf8", timeout: timeoutMs, env: { ...env },
    });
  } catch {
    return unavailable("read_failed");
  }
  if (result.error || result.status !== 0) return unavailable("read_failed");
  let table;
  try { table = JSON.parse(String(result.stdout || "")); }
  catch { return unavailable("table_invalid"); }
  if (!table || table.reporting_date !== String(reportingDate)) {
    return unavailable("reporting_date_mismatch");
  }
  const projection = table.economic_attribution;
  if (!projection || typeof projection !== "object"
    || !RFC3339.test(String(projection.snapshot_at || ""))) {
    return unavailable("projection_missing");
  }
  const coverageGaps = uniqueGaps(projection);
  const receiptRef = `loop-pnl://sha256/${sha256(canonical(table))}`;
  const status = coverageGaps.length ? "partial" : "fresh";
  const observedAt = String(projection.snapshot_at);
  return Object.freeze({
    status, table: Object.freeze(table), observedAt,
    sourceReceiptRefs: Object.freeze([receiptRef]), coverageGaps: Object.freeze(coverageGaps),
    businessSourceCoverage: Object.freeze([{
      source: "loop-pnl", state: status, observedAt, receiptCount: 1,
      gapReason: coverageGaps[0]?.reason || null,
    }]),
  });
}

module.exports = { canonical, readBusinessReadback, sha256, uniqueGaps };
