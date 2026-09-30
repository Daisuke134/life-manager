"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { renderResultSummary } = require("./cfo-result-summary.js");
function table(rows) { return { reporting_date: "2026-09-30", timezone: "Asia/Tokyo", rows }; }
function row(loop_id, status, amounts = {}) {
  return { loop_id, revenue: { status, amounts, receipts: status === "verified" ? ["official:1"] : [] } };
}
test("partial revenue never becomes a total or zero for missing loops", () => {
  const text = renderResultSummary(table([row("capafy", "verified", { USD: "1.10" }), row("investment", "unverified")]));
  assert.match(text, /確認済み小計: USD 1.1/);
  assert.match(text, /未確認: investment/);
  assert.doesNotMatch(text, /investment: 0/);
});
test("currencies stay separate; unknown app currency is excluded; decimal sums are exact", () => {
  const text = renderResultSummary(table([
    row("capafy", "verified", { USD: "0.1" }), row("agent-economy", "verified", { USD: "0.2" }),
    row("gig-lancers", "verified", { JPY: "1500" }), row("mobile-apps", "verified", { UNKNOWN: "4.2" }),
  ]));
  assert.match(text, /JPY 1500 \/ USD 0.3/);
  assert.match(text, /mobile-apps\(通貨\)/);
  assert.doesNotMatch(text, /0.30000000000000004/);
});
test("verified zero is distinct from no source and aggregate/non-economic rows are skipped", () => {
  const text = renderResultSummary(table([row("capafy", "zero"), row("cfo", "not_applicable")]));
  assert.match(text, /capafy: 0\(照合済み\)/);
  assert.doesNotMatch(text, /cfo:/);
  assert.match(renderResultSummary(table([row("capafy", "unverified")])), /確認済み小計: 未確認/);
});
test("a verified value requires an official receipt", () => {
  const item = row("capafy", "verified", { USD: "3" }); item.revenue.receipts = [];
  assert.throws(() => renderResultSummary(table([item])), /receipt_missing/);
});

test("spend and net stay unverified when cost sources or actual bank settlement are missing", () => {
  const r = row("capafy", "verified", { USD: "3" });
  r.cost = { status: "verified", amounts: { USD_API_EQUIV: "0.2" }, receipts: ["usage:1"] };
  r.refund = { status: "zero", amounts: {} };
  const text = renderResultSummary(table([r]));
  assert.match(text, /銀行への入金: 未確認/);
  assert.match(text, /差引: 未確認/);
  assert.doesNotMatch(text, /差引: USD 2.8/);
});
test("complete receipt-backed costs and refunds give same-currency net, never bank income", () => {
  const r = row("capafy", "verified", { USD: "3" });
  r.cost = { status: "verified", amounts: { USD: "0.2" }, receipts: ["bill:1"] };
  r.refund = { status: "verified", amounts: { USD: "0.1" }, receipts: ["refund:1"] };
  const text = renderResultSummary(table([r]));
  assert.match(text, /支出: USD 0.2 \| 差引: USD 2.7/);
  assert.match(text, /銀行への入金: 未確認/);
});
