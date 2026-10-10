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

test("an empty API usage stream never proves zero actual spend", () => {
  const r = row("capafy", "verified", { USD: "3" });
  r.cost = { status: "zero", amounts: {}, sources: ["agent-usage"], receipts: [] };
  r.refund = { status: "zero", amounts: {} };
  const text = renderResultSummary(table([r]));
  assert.match(text, /今日の確認済み支出\(小計\): 未確認 \| 差引: 未確認/);
  assert.doesNotMatch(text, /支出: 0/);
});

test("economic attribution summary keeps historical and trailing facts, MRR, runway, and gaps", () => {
  const verified = {
    status: "verified", currencies: { USD: {
      status: "verified", unknown_categories: [], settled_external_revenue: "5",
      refund: "1", provider_fee: "1", model_cost: "1", tool_cost: "1",
      browser_cost: "1", infra_cost: "1", payment_fee: "1",
      other_measured_cost: "1", total_cost: "7", net: "-3",
    }}, coverage_gaps: [], excluded: [],
  };
  const unknown = { status: "unknown", currencies: {}, coverage_gaps: [
    { product_loop_id: "writer", reason: "missing_category" },
  ], excluded: [] };
  const projection = {
    snapshot_at: "2026-10-01T00:00:00Z", trailing_start: "2026-09-24T00:00:00Z",
    duplicate_receipts: [{ provider: "stripe", receipt_id: "shared:1" }],
    historical: { loops: { capafy: verified, writer: unknown }, company: verified },
    trailing: { loops: { capafy: verified, writer: unknown }, company: verified },
    mrr: { company: { status: "verified", currencies: { USD: "30" }, reasons: [], coverage_gaps: [] },
      loops: { capafy: { status: "verified", currencies: { USD: "30" }, reasons: [], coverage_gaps: [] } } },
    runway: { status: "verified", currencies: { USD: {
      status: "verified", liquid_balance: "100", net_cash_burn: "3", window_days: "7",
      runway_days: "233.333333333333333333",
    }}, reasons: [] },
  };
  const text = renderResultSummary({
    reporting_date: "2026-10-01", timezone: "Asia/Tokyo", economic_attribution: projection,
  });
  assert.match(text, /historical/);
  assert.match(text, /trailing/);
  assert.match(text, /MRR: USD 30/);
  assert.match(text, /runway: USD 233\.333333333333333333 days/);
  assert.match(text, /duplicate_receipts: stripe\/shared:1/);
  assert.match(text, /未確認: writer/);
  assert.doesNotMatch(text, /writer: 0/);
});

test("summary displays billed Google invoice separately from cash paid and B0 net", () => {
  const unknown = { status: "unknown", currencies: {}, coverage_gaps: [], excluded: [] };
  const projection = {
    snapshot_at: "2026-10-08T00:45:00Z", trailing_start: "2026-09-08T00:45:00Z",
    duplicate_receipts: [],
    historical: { loops: {}, company: unknown },
    trailing: { loops: {}, company: unknown },
    mrr: { company: unknown, loops: {} },
    runway: { status: "unknown", currencies: {}, reasons: [] },
  };
  const text = renderResultSummary({
    reporting_date: "2026-10-08", timezone: "Asia/Tokyo", economic_attribution: projection,
    google_billed_expenses: {
      status: "verified", reason: null,
      invoices: [{
        status: "verified", invoice_period: "2026-09", currency: "JPY",
        billed_total_jpy: "110", cash_paid_status: "unknown",
        allocation_status: "unattributed", source_ref: `google-cloud-cost-table://sha256/${"a".repeat(64)}`,
        adjustments: {
          usage_gross_jpy: "100.123456", credits_jpy: "-0.003456",
          tax_jpy: "10", rounding_jpy: "-0.12",
        },
        service_sku: [{
          service: "Places API", sku: "Places Text Search", usage_gross_jpy: "100.123456",
          credits_jpy: "-0.003456", net_billed_jpy: "100.12",
        }],
      }],
    },
  });

  assert.match(text, /Google Cloud 請求済み費用 \(2026-09\): JPY 110/);
  assert.match(text, /使用量 100\.123456 \/ クレジット -0\.003456 \/ 税 10 \/ 丸め -0\.12/);
  assert.match(text, /Places API.*JPY 100\.12/);
  assert.match(text, /使用量 100\.123456 \/ クレジット -0\.003456 \/ 税 10 \/ 丸め -0\.12/);
  assert.match(text, /支払状況: 未確認/);
  assert.match(text, /loop帰属: 未帰属/);
  assert.match(text, /B0確定済み純損益には未加算/);
  assert.match(text, /trailing cost-complete net: 未確認/);
});

test("summary renders unreconciled Google invoice as unknown rather than zero", () => {
  const unknown = { status: "unknown", currencies: {}, coverage_gaps: [], excluded: [] };
  const projection = {
    snapshot_at: "2026-10-08T00:45:00Z", trailing_start: "2026-09-08T00:45:00Z",
    duplicate_receipts: [],
    historical: { loops: {}, company: unknown },
    trailing: { loops: {}, company: unknown },
    mrr: { company: unknown, loops: {} },
    runway: { status: "unknown", currencies: {}, reasons: [] },
  };
  const text = renderResultSummary({
    reporting_date: "2026-10-08", timezone: "Asia/Tokyo", economic_attribution: projection,
    google_billed_expenses: {
      status: "unverified", reason: "invoice_total_mismatch",
      invoices: [{ status: "unverified", invoice_period: "2026-09", billed_total_jpy: null }],
    },
  });

  assert.match(text, /Google Cloud 請求済み費用 \(2026-09\): 未確認/);
  assert.doesNotMatch(text, /JPY 0/);
});

test("summary displays provider billed expense without claiming cash paid or changing B0 net", () => {
  const unknown = { status: "unknown", currencies: {}, coverage_gaps: [], excluded: [] };
  const projection = {
    snapshot_at: "2026-10-10T00:00:00Z", trailing_start: "2026-09-10T00:00:00Z",
    duplicate_receipts: [],
    historical: { loops: {}, company: unknown },
    trailing: { loops: {}, company: unknown },
    mrr: { company: unknown, loops: {} },
    runway: { status: "unknown", currencies: {}, reasons: [] },
  };
  const text = renderResultSummary({
    reporting_date: "2026-10-10", timezone: "Asia/Tokyo", economic_attribution: projection,
    actual_billed_expenses: {
      status: "verified", reason: null,
      invoices: [{
        status: "verified", provider: "openai", invoice_period: "2026-09", currency: "USD",
        billed_total: "14.34", cash_paid_status: "unknown",
        allocation_status: "unattributed", source_ref: `lm-actual-cost://openai/readback/${"a".repeat(64)}`,
        invoice_id: "must-not-be-rendered",
      }],
    },
  });

  assert.match(text, /Provider billed expense \(openai, 2026-09\): USD 14\.34/);
  assert.match(text, /支払状況: 未確認/);
  assert.match(text, /loop配賦: 未帰属/);
  assert.match(text, /B0 netに二重加算しない/);
  assert.match(text, /trailing cost-complete net: 未確認/);
  assert.doesNotMatch(text, /must-not-be-rendered/);
});

test("verified Google Cost Table owns its period and suppresses duplicate provider-bill display", () => {
  const unknown = { status: "unknown", currencies: {}, coverage_gaps: [], excluded: [] };
  const projection = {
    snapshot_at: "2026-10-10T00:00:00Z", trailing_start: "2026-09-10T00:00:00Z",
    duplicate_receipts: [],
    historical: { loops: {}, company: unknown },
    trailing: { loops: {}, company: unknown },
    mrr: { company: unknown, loops: {} },
    runway: { status: "unknown", currencies: {}, reasons: [] },
  };
  const text = renderResultSummary({
    reporting_date: "2026-10-10", timezone: "Asia/Tokyo", economic_attribution: projection,
    google_billed_expenses: {
      status: "verified", reason: null,
      invoices: [{
        status: "verified", invoice_period: "2026-09", currency: "JPY",
        billed_total_jpy: "27889", cash_paid_status: "unknown",
        allocation_status: "unattributed", adjustments: {
          usage_gross_jpy: "25354", credits_jpy: "0", tax_jpy: "2535", rounding_jpy: "0",
        },
        service_sku: [{
          service: "Places API", sku: "Places Text Search", net_billed_jpy: "25354",
        }],
      }],
    },
    actual_billed_expenses: {
      status: "verified", reason: null,
      invoices: [{
        status: "verified", provider: "google-cloud", invoice_period: "2026-09",
        currency: "JPY", billed_total: "27889", cash_paid_status: "unknown",
        allocation_status: "unattributed",
      }],
    },
  });

  assert.match(text, /Google Cloud 請求済み費用 \(2026-09\): JPY 27889/);
  assert.doesNotMatch(text, /Provider billed expense \(google-cloud, 2026-09\): JPY 27889/);
  assert.match(text, /Provider billed expense \(google-cloud, 2026-09\): Google Cloud請求表と期間重複、請求同一性未確認/);
});

test("provider billing summary renders a safe underscore provider identifier", () => {
  const unknown = { status: "unknown", currencies: {}, coverage_gaps: [], excluded: [] };
  const projection = {
    snapshot_at: "2026-10-10T00:00:00Z", trailing_start: "2026-09-10T00:00:00Z",
    duplicate_receipts: [],
    historical: { loops: {}, company: unknown },
    trailing: { loops: {}, company: unknown },
    mrr: { company: unknown, loops: {} },
    runway: { status: "unknown", currencies: {}, reasons: [] },
  };
  const text = renderResultSummary({
    reporting_date: "2026-10-10", timezone: "Asia/Tokyo", economic_attribution: projection,
    actual_billed_expenses: {
      status: "verified", reason: null,
      invoices: [{
        status: "verified", provider: "google_cloud", invoice_period: "2026-09",
        currency: "JPY", billed_total: "31425", cash_paid_status: "unknown",
        allocation_status: "unattributed",
      }],
    },
  });

  assert.match(text, /Provider billed expense \(google_cloud, 2026-09\): JPY 31425/);
});

test("verified loop MRR stays visible while company and unknown loop MRR stay unknown", () => {
  const unknown = { status: "unknown", currencies: {}, reasons: ["mrr_coverage_unknown"], coverage_gaps: [] };
  const projection = {
    snapshot_at: "2026-10-01T00:00:00Z", trailing_start: "2026-09-24T00:00:00Z",
    historical: { loops: {}, company: unknown },
    trailing: { loops: {}, company: unknown },
    mrr: { company: unknown, loops: {
      "mobile-apps": { status: "verified", currencies: { USD: "20.34" } },
      writer: unknown,
    } },
    runway: { status: "unknown", currencies: {}, reasons: ["trailing_burn_unknown"] },
  };
  const text = renderResultSummary({
    reporting_date: "2026-10-01", timezone: "Asia/Tokyo", economic_attribution: projection,
  });
  assert.match(text, /MRR: 未確認/);
  assert.match(text, /確認済みloop MRR: mobile-apps USD 20\.34/);
  assert.doesNotMatch(text, /writer USD 0/);
});

test("personal Moneytree balances and observed spending stay separate from company economics", () => {
  const receiptRef = `moneytree-observation://sha256/${"a".repeat(64)}`;
  const personal = {
    schema_version: 1, owner: "dais_personal", status: "partial",
    observed_at: "2026-10-07T07:00:00.000Z", provider_sync_at: null,
    freshness_status: "unknown", range_start: "2025-10-07", range_end: "2026-10-07",
    windows: [
      { coverage_status: "complete", evidence_ref: receiptRef },
      { coverage_status: "partial", evidence_ref: receiptRef },
    ],
    balances: [{ institution: "三菱UFJ銀行 普通", balance_jpy: 42000,
      observed_at: "2026-10-07T07:00:00.000Z", evidence_ref: receiptRef }],
    monthly: [{ month: "2026-09", income_jpy: null, expense_jpy: 1000, cash_movement_jpy: null,
      coverage_status: "observed", evidence_refs: [receiptRef],
      categories: [{ category: "娯楽", expense_jpy: 1000 }] }],
    latest_transaction_date: "2026-09-05",
    recurring_charge_candidates: [{ merchant: "Video Service", month_count: 2, total_observed_jpy: 2200,
      evidence_refs: [receiptRef] }],
  };
  const text = renderResultSummary({
    ...table([row("capafy", "verified", { USD: "5" })]), personal_moneytree: personal,
  });

  assert.match(text, /個人 Moneytree/);
  assert.match(text, /会社.*合算しない/);
  assert.match(text, /freshness: unknown/);
  assert.match(text, /三菱UFJ銀行 普通.*¥42,000/);
  assert.match(text, /2026-09.*収入 未確認.*支出.*¥1,000/);
  assert.match(text, /定期支出候補.*Video Service.*2か月.*¥2,200/);
  assert.match(text, /receipt: moneytree-observation:\/\/sha256\//);
  assert.match(text, /USD 5/);
  assert.doesNotMatch(text, /差引:.*個人/);
});

test("personal Moneytree with no observed flow never renders missing amounts as zero", () => {
  const text = renderResultSummary({
    ...table([row("capafy", "unverified")]),
    personal_moneytree: {
      schema_version: 1, owner: "dais_personal", status: "unavailable",
      observed_at: null, provider_sync_at: null, freshness_status: "unknown",
      range_start: "2025-10-07", range_end: "2026-10-07", windows: [], balances: [],
      monthly: [], latest_transaction_date: null, recurring_charge_candidates: [],
    },
  });
  assert.match(text, /個人 Moneytree/);
  assert.match(text, /残高: 未確認/);
  assert.match(text, /取引集計: 未確認/);
  assert.doesNotMatch(text, /¥0/);
});

test("empty Moneytree months remain visible as unknown with their source receipt", () => {
  const receiptRef = `moneytree-observation://sha256/${"b".repeat(64)}`;
  const text = renderResultSummary({
    ...table([row("capafy", "unverified")]),
    personal_moneytree: {
      schema_version: 1, owner: "dais_personal", status: "partial",
      observed_at: "2026-10-07T07:00:00.000Z", provider_sync_at: null,
      freshness_status: "unknown", range_start: "2025-10-07", range_end: "2026-10-07",
      windows: [{ query_start_date: "2025-10-07", query_end_date: "2026-01-06",
        provider_total_count: 0, returned_count: 0, limit: 1000,
        coverage_status: "unknown", evidence_ref: receiptRef }],
      balances: [],
      monthly: [{ month: "2025-10", income_jpy: null, expense_jpy: null,
        cash_movement_jpy: null, coverage_status: "unknown", evidence_refs: [receiptRef], categories: [] }],
      latest_transaction_date: null, recurring_charge_candidates: [],
    },
  });
  assert.match(text, /2025-10 \(unknown\): 収入 未確認 \/ 支出（観測小計） 未確認/);
  assert.match(text, /window 2025-10-07\.\.2026-01-06: unknown \(0\/0\) receipt: moneytree-observation/);
  assert.doesNotMatch(text, /¥0/);
});

test("legacy report text stays byte-for-byte unchanged without personal Moneytree data", () => {
  assert.equal(renderResultSummary(table([row("capafy", "verified", { USD: "1.1" })])),
    "Life Manager 2026-09-30 (Asia/Tokyo)\n"
    + "今日の確認済み収益: USD 1.1\n"
    + "銀行への入金: 未確認\n"
    + "今日の確認済み支出(小計): 未確認 | 差引: 未確認\n"
    + "capafy: USD 1.1\n"
    + "投資は実現損益。他は売上。API価格換算は請求額ではありません。トークン数・定額契約の日割り: 未確認。");
});
