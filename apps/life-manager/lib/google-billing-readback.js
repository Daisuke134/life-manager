"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");

const REQUIRED_HEADERS = ["Service description", "SKU description", "Cost", "Currency", "Invoice month"];
const BILLING_MONTH = /^\d{4}-\d{2}$/;

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') { field += '"'; index += 1; }
      else if (character === '"') quoted = false;
      else field += character;
      continue;
    }
    if (character === '"' && field === "") { quoted = true; continue; }
    if (character === ",") { row.push(field); field = ""; continue; }
    if (character === "\n") {
      row.push(field.endsWith("\r") ? field.slice(0, -1) : field);
      if (row.some((value) => value !== "")) rows.push(row);
      row = []; field = ""; continue;
    }
    field += character;
  }
  if (quoted) throw new Error("google_billing_csv_invalid_quote");
  if (field !== "" || row.length) {
    row.push(field);
    if (row.some((value) => value !== "")) rows.push(row);
  }
  return rows;
}

function decimalUnits(value) {
  const text = String(value == null ? "" : value).trim().replace(/,/g, "");
  if (!text) return 0n;
  const negative = text.startsWith("(") && text.endsWith(")") || text.startsWith("-");
  const stripped = text.replace(/^\(/, "").replace(/\)$/, "").replace(/^-/, "");
  if (!/^\d+(?:\.\d+)?$/.test(stripped)) throw new Error("google_billing_amount_invalid");
  const [whole, fraction = ""] = stripped.split(".");
  if (fraction.length > 6) throw new Error("google_billing_amount_invalid");
  const units = BigInt(whole) * 1_000_000n + BigInt(fraction.padEnd(6, "0") || 0);
  return negative ? -units : units;
}

function decimalText(units) {
  const negative = units < 0n;
  const value = negative ? -units : units;
  const fraction = String(value % 1_000_000n).padStart(6, "0").replace(/0+$/, "");
  return `${negative ? "-" : ""}${value / 1_000_000n}${fraction ? `.${fraction}` : ""}`;
}

function sha256(buffer) {
  return crypto.createHash("sha256").update(buffer).digest("hex");
}

function readGoogleBillingCsv(filePath, { invoiceMonth, observedAt = null } = {}) {
  if (!BILLING_MONTH.test(String(invoiceMonth || ""))) throw new Error("google_billing_invoice_month_invalid");
  let bytes;
  try { bytes = fs.readFileSync(filePath); }
  catch (error) {
    if (error && error.code === "ENOENT") {
      return { status: "unknown", rows: [], receiptRef: null, totals: null, observedAt };
    }
    throw error;
  }
  const rows = parseCsv(bytes.toString("utf8"));
  if (!rows.length) throw new Error("google_billing_csv_header_invalid");
  const headers = rows[0].map((value, index) => index === 0 ? value.replace(/^\uFEFF/, "").trim() : value.trim());
  const missing = REQUIRED_HEADERS.filter((header) => !headers.includes(header));
  const taxHeader = headers.includes("Taxes") ? "Taxes" : headers.includes("Tax") ? "Tax" : null;
  if (missing.length || !taxHeader) throw new Error(`google_billing_csv_header_invalid:${missing[0] || "Taxes"}`);
  const index = (header) => headers.indexOf(header);
  const receiptRef = `google-billing://sha256/${sha256(bytes)}`;
  const selected = [];
  for (const values of rows.slice(1)) {
    if (values.length !== headers.length) throw new Error("google_billing_csv_row_invalid");
    const month = values[index("Invoice month")].trim();
    if (month !== String(invoiceMonth)) continue;
    const currency = values[index("Currency")].trim().toUpperCase();
    if (currency !== "JPY") throw new Error("google_billing_currency_invalid");
    const cost = decimalUnits(values[index("Cost")]);
    const tax = decimalUnits(values[index(taxHeader)]);
    const projectIndex = index("Project ID");
    selected.push({
      service: values[index("Service description")].trim(),
      sku: values[index("SKU description")].trim(),
      costJpy: decimalText(cost), taxJpy: decimalText(tax), currency,
      invoiceMonth: month, projectId: projectIndex >= 0 ? values[projectIndex].trim() : null,
    });
  }
  if (!selected.length) return { status: "unknown", rows: [], receiptRef, totals: null, observedAt };
  let cost = 0n; let tax = 0n;
  for (const row of selected) { cost += decimalUnits(row.costJpy); tax += decimalUnits(row.taxJpy); }
  return {
    status: "settled", rows: selected, receiptRef,
    totals: { costJpy: decimalText(cost), taxJpy: decimalText(tax), totalJpy: decimalText(cost + tax) },
    observedAt,
  };
}

module.exports = { decimalText, decimalUnits, parseCsv, readGoogleBillingCsv, sha256 };
