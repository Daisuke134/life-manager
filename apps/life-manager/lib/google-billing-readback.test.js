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
