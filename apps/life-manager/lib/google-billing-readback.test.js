"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { readGoogleBillingCsv } = require("./google-billing-readback.js");

function csvFile(t, text) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-google-billing-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, "cost.csv");
  fs.writeFileSync(file, text);
  return file;
}

const HEADER = "Service description,SKU description,Cost,Taxes,Currency,Invoice month,Project ID\n";
const japaneseCells = (overrides = {}) => {
  const cells = Array(18).fill("");
  for (const [index, value] of Object.entries(overrides)) cells[Number(index)] = value;
  return cells.join(",");
};

const JAPANESE_COST_TABLE = [
  "請求書番号,5712284328,",
  "発行日,2026-09-30,",
  "請求 ID,8842-6035-3600,",
  "通貨,JPY,",
  "合計お支払い額,¥27889,",
  "請求先アカウント名,請求先アカウント ID,プロジェクト名,プロジェクト ID,プロジェクト階層,サービスの説明,サービス ID,SKU の説明,SKU ID,消費モデルの説明,クレジットの種類,費用のタイプ,使用開始日,使用の終了日,使用量,使用量の単位,四捨五入前の費用（¥）,費用（¥）",
  "請求先アカウント,017949-09509F-6A3FB6,anicca,anicca-461216,,Geocoding API,svc,Geocoding,sku,Default,,使用量,2026-09-01,2026-09-30,19403,count,7493.014626,7493",
  "請求先アカウント,017949-09509F-6A3FB6,anicca,anicca-461216,,Places API,svc,Places - Text Search,sku,Default,,使用量,2026-09-01,2026-09-30,5672,count,3427.199739,3427",
  "請求先アカウント,017949-09509F-6A3FB6,anicca,gen-lang-client-0072731773,,Gemini API,svc,Generate content,sku,Default,,使用量,2026-09-01,2026-09-30,100,count,14434.236886,14434",
  japaneseCells({ 0: "請求先アカウント", 1: "017949-09509F-6A3FB6", 2: "anicca", 3: "anicca-461216", 11: "税金", 16: "2535", 17: "2535" }),
  japaneseCells({ 11: "丸めエラー", 16: "-0.451251", 17: "-0" }),
  japaneseCells({ 11: "合計", 16: "27889.000000", 17: "27889" }),
].join("\n") + "\n";

const CROSS_MONTH_JAPANESE_COST_TABLE = [
  "通貨,JPY,",
  "合計お支払い額,¥0.000300,",
  "請求先アカウント名,請求先アカウント ID,プロジェクト名,プロジェクト ID,プロジェクト階層,サービスの説明,サービス ID,SKU の説明,SKU ID,消費モデルの説明,クレジットの種類,費用のタイプ,使用開始日,使用の終了日,使用量,使用量の単位,四捨五入前の費用（¥）,費用（¥）",
  japaneseCells({
    5: "Cloud Storage", 7: "Standard storage", 11: "使用量",
    12: "2026-08-31", 13: "2026-09-30", 14: "0.000300", 15: "byte-seconds",
    16: "0.000300", 17: "0",
  }),
].join("\n") + "\n";

test("Google Billing CSV separates JPY cost and tax and binds a file receipt", (t) => {
  const file = csvFile(t, `${HEADER}Google Maps,Geocoding,25354,2535,JPY,2026-09,life-manager\n`);
  const result = readGoogleBillingCsv(file, { invoiceMonth: "2026-09", observedAt: "2026-10-02T00:00:00.000Z" });
  assert.equal(result.status, "settled");
  assert.match(result.receiptRef, /^google-billing:\/\/sha256\/[a-f0-9]{64}$/);
  assert.deepEqual(result.totals, { costJpy: "25354", taxJpy: "2535", totalJpy: "27889" });
  assert.deepEqual(result.rows[0], {
    service: "Google Maps", sku: "Geocoding", costJpy: "25354", taxJpy: "2535",
    currency: "JPY", invoiceMonth: "2026-09", projectId: "life-manager",
  });
});

test("Google Billing CSV filters invoice month and never reports no matching rows as settled zero", (t) => {
  const file = csvFile(t, `${HEADER}Google Cloud,Compute,100,10,JPY,2026-08,life-manager\n`);
  const result = readGoogleBillingCsv(file, { invoiceMonth: "2026-09", observedAt: "2026-10-02T00:00:00.000Z" });
  assert.equal(result.status, "unknown");
  assert.deepEqual(result.rows, []);
  assert.equal(result.totals, null);
});

test("Google Billing CSV rejects malformed headers/amounts and missing files fail closed", (t) => {
  const badHeader = csvFile(t, "Service description,Cost\nGoogle,not-a-number\n");
  assert.throws(() => readGoogleBillingCsv(badHeader, { invoiceMonth: "2026-09" }), /header/);
  const badAmount = csvFile(t, `${HEADER}Google,Geocoding,nope,0,JPY,2026-09,life-manager\n`);
  assert.throws(() => readGoogleBillingCsv(badAmount, { invoiceMonth: "2026-09" }), /amount/);
  const missing = readGoogleBillingCsv("/tmp/lm-google-billing-missing.csv", { invoiceMonth: "2026-09" });
  assert.equal(missing.status, "unknown");
  assert.equal(missing.receiptRef, null);
  assert.equal(missing.totals, null);
});

test("Google Cost Table Japanese export parses invoice header, SKU rows, tax, and total", (t) => {
  const file = csvFile(t, JAPANESE_COST_TABLE);
  const result = readGoogleBillingCsv(file, { invoiceMonth: "2026-09", observedAt: "2026-10-02T08:00:00.000Z" });
  assert.equal(result.status, "settled");
  assert.deepEqual(result.totals, { costJpy: "25354.451251", taxJpy: "2535", totalJpy: "27889" });
  assert.equal(result.invoiceTotalJpy, "27889");
  assert.equal(result.invoiceMonth, "2026-09");
  assert.equal(result.rows.length, 3);
  assert.deepEqual(result.rows.map((row) => [row.service, row.sku, row.costJpy]), [
    ["Geocoding API", "Geocoding", "7493.014626"],
    ["Places API", "Places - Text Search", "3427.199739"],
    ["Gemini API", "Generate content", "14434.236886"],
  ]);
  assert.deepEqual(result.serviceTotals, [
    { service: "Geocoding API", costJpy: "7493.014626", currency: "JPY" },
    { service: "Places API", costJpy: "3427.199739", currency: "JPY" },
    { service: "Gemini API", costJpy: "14434.236886", currency: "JPY" },
  ]);
});

test("Google Cost Table Japanese export includes prior-month usage in selected invoice", (t) => {
  const file = csvFile(t, CROSS_MONTH_JAPANESE_COST_TABLE);
  const result = readGoogleBillingCsv(file, { invoiceMonth: "2026-09", observedAt: "2026-10-02T08:00:00.000Z" });
  assert.equal(result.status, "settled");
  assert.equal(result.totals.costJpy, "0.0003");
  assert.equal(result.totals.totalJpy, "0.0003");
  assert.equal(result.invoiceMonth, "2026-09");
  assert.deepEqual(result.serviceTotals, [
    { service: "Cloud Storage", costJpy: "0.0003", currency: "JPY" },
  ]);
});

test("Google Cost Table Japanese export rejects missing, invalid, and year-zero usage dates", (t) => {
  const errors = ["", "2026-02-30", "0000-01-01"].map((usageDate) => {
    const file = csvFile(t, CROSS_MONTH_JAPANESE_COST_TABLE.replace("2026-08-31", usageDate));
    try {
      readGoogleBillingCsv(file, { invoiceMonth: "2026-09" });
      return null;
    } catch (error) {
      return error.message;
    }
  });
  assert.deepEqual(errors, [
    "google_billing_usage_date_invalid",
    "google_billing_usage_date_invalid",
    "google_billing_usage_date_invalid",
  ]);
});
