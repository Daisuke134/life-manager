"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { financialRecordId } = require("../../../runtime/contracts/common-record.cjs");
const {
  buildFinancialManagerReport, renderFinancialManagerDetailed: renderFinancialManagerTelegram,
  renderFinancialManagerTelegram: renderFinancialManagerShort,
} = require("./financial-manager-report.js");

function record(key, { kind, amount, occurredAt, provider = "stripe", scope = "business", direction = null }) {
  return {
    schema_version: 1, record_type: "financial_record",
    record_id: financialRecordId("tenant-1", key), subject_id: "tenant-1",
    scope, kind,
    direction: direction || (kind === "asset_balance" ? "snapshot" : (
      ["business_revenue", "payout"].includes(kind) ? "credit" : "debit"
    )),
    amount_minor: amount, currency: "JPY", occurred_at: occurredAt,
    recorded_at: occurredAt, idempotency_key: key,
    source: {
      provider, source_type: scope === "personal" ? "moneytree" : "payment_processor",
      external_ref: key,
    },
    verification: {
      status: "verified", observed_at: occurredAt,
      evidence_refs: [`${provider}://receipt/${key}`],
    },
  };
}

test("Financial Manager folds daily, seven-day, monthly and provider views into one report", () => {
  const { report } = buildFinancialManagerReport([
    record("today-revenue", { kind: "business_revenue", amount: 1000, occurredAt: "2026-09-07T01:00:00Z" }),
    record("yesterday-cost", { kind: "business_cost", amount: 200, occurredAt: "2026-09-06T01:00:00Z" }),
    record("older-revenue", { kind: "business_revenue", amount: 300, occurredAt: "2026-09-01T01:00:00Z", provider: "gumroad" }),
    record("previous-month", { kind: "business_revenue", amount: 9000, occurredAt: "2026-08-31T14:59:59Z" }),
  ], "2026-09-07");

  assert.deepEqual(report.business.today.revenue, [{ currency: "JPY", amountMinor: 1000 }]);
  assert.deepEqual(report.business.last7Days, {
    period: { start: "2026-09-01", end: "2026-09-07" },
    revenue: [{ currency: "JPY", amountMinor: 1300 }],
    costs: [{ currency: "JPY", amountMinor: 200 }],
    profit: [{ currency: "JPY", amountMinor: 1100 }], payouts: [],
  });
  assert.deepEqual(report.business.revenue, [{ currency: "JPY", amountMinor: 1300 }]);
  assert.deepEqual(report.business.byProvider.map((item) => item.provider), ["gumroad", "stripe"]);
  const text = renderFinancialManagerTelegram(report);
  assert.match(text, /事業（今日）/);
  assert.match(text, /事業（直近7日）/);
  assert.match(text, /事業（2026-09）/);
  assert.match(text, /収益内訳（今月・プロバイダー別）/);
  assert.doesNotMatch(text, /9,000/);
  assert.doesNotMatch(text, /確認済みデータなし/);
});

test("balance-only report omits empty business and liability noise", () => {
  const { report } = buildFinancialManagerReport([
    record("balance", {
      kind: "asset_balance", amount: 5000, occurredAt: "2026-09-07T01:00:00Z",
      provider: "moneytree", scope: "personal",
    }),
  ], "2026-09-07");
  const text = renderFinancialManagerTelegram(report);
  assert.match(text, /個人資産/);
  assert.doesNotMatch(text, /事業（/);
  assert.doesNotMatch(text, /負債/);
  assert.doesNotMatch(text, /確認済みデータなし/);
});

test("Financial Manager uses the tenant timezone at a non-JST day boundary", () => {
  const rows = [record("los-angeles-day", {
    kind: "business_revenue", amount: 500,
    // 23:30 on 2026-08-31 in Los Angeles, but already Sep 1 in Tokyo.
    occurredAt: "2026-09-01T06:30:00.000Z",
  })];
  const { report } = buildFinancialManagerReport(rows, "2026-08-31", {
    timezone: "America/Los_Angeles",
  });
  assert.deepEqual(report.business.today.revenue, [{ currency: "JPY", amountMinor: 500 }]);
  assert.deepEqual(report.business.revenue, [{ currency: "JPY", amountMinor: 500 }]);
});

test("economic source coverage stays private and does not change the notification digest", () => {
  const rows = [record("covered", {
    kind: "business_revenue", amount: 500, occurredAt: "2026-09-01T06:30:00.000Z",
  })];
  const coverage = { schema_version: 1, subject_id: "tenant-1", complete: false, loops: [] };
  const withCoverage = buildFinancialManagerReport(rows, "2026-09-07", {
    economicSourceCoverage: coverage,
  });
  const withoutCoverage = buildFinancialManagerReport(rows, "2026-09-07");
  assert.deepEqual(withCoverage.report.economicSourceCoverage, coverage);
  assert.equal(withCoverage.digest, withoutCoverage.digest);
  assert.doesNotMatch(renderFinancialManagerTelegram(withCoverage.report), /economic|coverage|tenant-1/i);
});

test("stale personal balance is shown as last-known and source warning, never current cash", () => {
  const stale = record("stale-balance", {
    kind: "asset_balance", amount: 504302, occurredAt: "2026-08-26T03:09:37.000Z",
    provider: "moneytree", scope: "personal",
  });
  stale.verification = {
    status: "stale", observed_at: "2026-10-02T06:00:00.000Z", evidence_refs: [],
  };
  const { report } = buildFinancialManagerReport([stale], "2026-10-02", {
    sourceFreshness: { moneytree: { status: "stale", reason: "provider_auth_invalid" } },
  });
  const text = renderFinancialManagerTelegram(report);
  assert.deepEqual(report.personal.assets, []);
  assert.deepEqual(report.personal.staleAssets, [{ currency: "JPY", amountMinor: 504302 }]);
  assert.match(text, /前回観測残高（stale）/);
  assert.match(text, /最新確認: 未確認/);
  assert.match(text, /moneytree:stale/);
});

test("provider freshness warning demotes an old verified balance to last-known", () => {
  const verified = record("old-balance", {
    kind: "asset_balance", amount: 504302, occurredAt: "2026-08-26T03:09:37.000Z",
    provider: "moneytree", scope: "personal",
  });
  const { report } = buildFinancialManagerReport([verified], "2026-10-02", {
    sourceFreshness: { moneytree: { status: "partial", reason: "source_freshness_unknown" } },
  });
  assert.deepEqual(report.personal.assets, []);
  assert.deepEqual(report.personal.staleAssets, [{ currency: "JPY", amountMinor: 504302 }]);
  assert.equal(report.verifiedRecordCount, 0);
  assert.equal(report.excludedRecordCount, 1);
});

test("business source coverage is visible without turning a gap into zero", () => {
  const { report } = buildFinancialManagerReport([], "2026-10-02", {
    businessSourceCoverage: [{
      source: "loop-pnl", state: "partial", observedAt: "2026-10-03T00:00:00.000Z",
      receiptCount: 1, gapReason: "source_unconnected",
    }],
    businessReadback: {
      status: "partial", sourceReceiptRefs: ["loop-pnl://sha256/receipt"],
      coverageGaps: [{ product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "source_unconnected" }],
      coverageSummary: [{ sourceId: "stripe-financial-record", reason: "source_unconnected", count: 1, productLoopIds: ["self-build"], categories: [] }],
    },
  });
  assert.deepEqual(report.businessSourceCoverage[0], {
    source: "loop-pnl", state: "partial", observedAt: "2026-10-03T00:00:00.000Z",
    receiptCount: 1, gapReason: "source_unconnected",
  });
  assert.equal(report.business.revenue.length, 0);
  const text = renderFinancialManagerTelegram(report);
  assert.match(text, /事業ソース照合\nloop-pnl:partial/);
  assert.match(text, /self-build\/source_unconnected/);
  assert.match(text, /事業gap要約\nstripe-financial-record\/source_unconnected=1/);
  assert.doesNotMatch(text, /収益: ¥0/);
});

test("B7 economic snapshot stays separate from FinancialRecord totals and preserves unknowns", () => {
  const receiptRef = `loop-pnl://sha256/${"a".repeat(64)}`;
  const financialRecords = [
    record("financial-record-revenue", {
      kind: "business_revenue", amount: 1200, occurredAt: "2026-10-02T01:00:00.000Z",
    }),
  ];
  const { report } = buildFinancialManagerReport(financialRecords, "2026-10-02", {
    businessReadback: {
      status: "partial",
      observedAt: "2026-10-03T00:00:00.000000Z",
      sourceReceiptRefs: [receiptRef],
      coverageGaps: [{
        product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "missing_category",
      }],
      table: {
        reporting_date: "2026-10-02",
        excluded_receipt_ids: ["private-receipt-id"],
        raw_provider_payload: { account_name: "private account" },
        economic_attribution: {
          snapshot_at: "2026-10-03T00:00:00.000000Z",
          trailing: {
            window_start: "2026-09-03T00:00:00.000000Z",
            window_end: "2026-10-03T00:00:00.000000Z",
            company: {
              status: "unknown",
              currencies: { USD: {
                status: "unknown", settled_external_revenue: null, total_cost: null, net: null,
              } },
            },
            loops: {
              "self-build": {
                status: "unknown",
                currencies: { USD: {
                  status: "unknown", settled_external_revenue: null, total_cost: null, net: null,
                } },
                coverage_gaps: [{
                  product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "missing_category",
                }],
              },
              affiliate: {
                status: "verified",
                currencies: { USD: { status: "verified", settled_external_revenue: "987.65" } },
              },
            },
          },
          mrr: {
            company: { status: "unknown", currencies: {}, reasons: ["mrr_coverage_unknown"] },
          },
          runway: { status: "unknown", currencies: {}, reasons: ["liquid_balance_missing"] },
        },
      },
    },
  });

  const financialRecordBusiness = buildFinancialManagerReport(financialRecords, "2026-10-02").report.business;
  assert.deepEqual(report.business, financialRecordBusiness);
  assert.deepEqual(report.business.revenue, [{ currency: "JPY", amountMinor: 1200 }]);
  assert.deepEqual(report.b7EconomicSnapshot, {
    status: "partial",
    observedAt: "2026-10-03T00:00:00.000000Z",
    sourceReceiptRefs: [receiptRef],
    trailing: {
      windowStart: "2026-09-03T00:00:00.000000Z",
      windowEnd: "2026-10-03T00:00:00.000000Z",
      company: {
        status: "unknown",
        currencies: { USD: {
          status: "unknown", settled_external_revenue: null, total_cost: null, net: null,
        } },
      },
      loops: { "self-build": {
        status: "unknown",
        currencies: { USD: {
          status: "unknown", settled_external_revenue: null, total_cost: null, net: null,
        } },
      }, affiliate: {
        status: "verified",
        currencies: { USD: { status: "verified", settled_external_revenue: "987.65" } },
      } },
    },
    mrr: { status: "unknown", currencies: {}, reasons: ["mrr_coverage_unknown"] },
    runway: { status: "unknown", currencies: {}, reasons: ["liquid_balance_missing"] },
  });
  assert.doesNotMatch(JSON.stringify(report), /private-receipt-id|private account|raw_provider_payload/);
  assert.deepEqual(report.businessReadback.coverageGaps, [{
    product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "missing_category",
  }]);

  const text = renderFinancialManagerShort(report);
  assert.match(text, /B7事業スナップショット.*FinancialRecord.*別・合算なし/);
  assert.match(text, /company:unknown USD unknown.*settled_external_revenue=未確認/);
  assert.match(text, /self-build:unknown USD unknown.*settled_external_revenue=未確認/);
  assert.match(text, /affiliate:verified USD verified settled_external_revenue=987\.65/);
  assert.match(text, /net=未確認/);
  assert.match(text, /self-build:unknown/);
  assert.match(text, /MRR: unknown.*mrr_coverage_unknown/);
  assert.match(text, /Runway: unknown.*liquid_balance_missing/);
  assert.match(text, /2026-10-03T00:00:00\.000000Z/);
  assert.match(text, new RegExp(receiptRef.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.doesNotMatch(text, /private-receipt-id|private account|settled_external_revenue=0|total_cost=0|net=0/);
  assert.match(renderFinancialManagerTelegram(report), /B7事業スナップショット/);
});

test("provider cost report keeps Google settlement receipt and unknown state separate", () => {
  const settled = buildFinancialManagerReport([], "2026-10-02", {
    providerCostSettlement: {
      status: "settled", observedAt: "2026-10-02T02:00:00.000Z",
      receiptRef: "google-billing://receipt",
      invoiceMonth: "2026-09",
      totals: { costJpy: "25354", taxJpy: "2535", totalJpy: "27889" },
      serviceTotals: [{ service: "Gemini API", costJpy: "14434.236886", currency: "JPY" }],
    },
  }).report;
  assert.equal(settled.providerCostSettlement.totals.totalJpy, "27889");
  assert.match(renderFinancialManagerTelegram(settled), /Google請求: settled 2026-09 ¥27,889/);
  assert.match(renderFinancialManagerTelegram(settled), /Google請求内訳\nGemini API: ¥14,434\.236886/);
  const unknown = buildFinancialManagerReport([], "2026-10-02", {
    providerCostSettlement: { status: "unknown", totals: null, receiptRef: null },
  }).report;
  assert.match(renderFinancialManagerTelegram(unknown), /Google請求: 未確認/);
});

test("provider budget state is visible in the CFO report", () => {
  const report = buildFinancialManagerReport([], "2026-10-02", {
    providerBudget: { state: "degraded", totalUsd: 10, unknownCount: 1, reasons: ["unknown_cost"] },
  }).report;
  assert.equal(report.providerBudget.state, "degraded");
  assert.match(renderFinancialManagerTelegram(report), /Provider予算: degraded/);
});

test("provider cap state and next action are visible in the CFO report", () => {
  const report = buildFinancialManagerReport([], "2026-10-02", {
    providerBudget: {
      state: "stopped", totalUsd: 5, unknownCount: 0, reasons: ["cap_exceeded"],
      capKey: "google_maps:route", capState: "stopped", nextAction: "use_cache_or_stop",
      providerUnits: 101, estimatedUsd: 5, settledUsd: 0,
    },
  }).report;
  assert.equal(report.providerBudget.capKey, "google_maps:route");
  assert.equal(report.providerBudget.nextAction, "use_cache_or_stop");
  assert.match(renderFinancialManagerTelegram(report), /use_cache_or_stop/);
});

test("provider lane freshness and fallback caps are visible in the CFO report", () => {
  const report = buildFinancialManagerReport([], "2026-10-02", {
    providerLanes: {
      poi: { status: "fresh", primary: "openpoi", fallbackCalls: 0, fallbackCap: 100 },
      transit: { status: "fresh", primary: "transit_api", fallbackCalls: 1, fallbackCap: 100 },
      geocoder: { status: "partial", primary: "google_maps", fallbackCalls: 2, fallbackCap: 200 },
    },
  }).report;
  assert.equal(report.providerLanes.geocoder.status, "partial");
  const text = renderFinancialManagerTelegram(report);
  assert.match(text, /Provider lane/);
  assert.match(text, /geocoder:partial/);
  assert.match(text, /2\/200/);
});

test("provider lane readback failure stays visible and does not become zero", () => {
  const report = buildFinancialManagerReport([], "2026-10-02", {
    providerLaneReadback: {
      status: "partial", observedAt: "2026-10-02T02:00:00.000Z",
      failures: ["provider_lane_readback_failed"], lanes: null,
    },
  }).report;
  assert.equal(report.providerLaneReadback.status, "partial");
  assert.equal(report.partial, true);
  assert.match(renderFinancialManagerTelegram(report), /Provider lane readback: partial/);
  assert.match(renderFinancialManagerTelegram(report), /provider_lane_readback_failed/);
});

test("stale personal transactions are shown as last-known, never current spending", () => {
  const income = record("stale-income", {
    kind: "personal_income", amount: 806201, occurredAt: "2026-08-25T00:00:00.000Z",
    provider: "moneytree", scope: "personal", direction: "credit",
  });
  const expense = record("stale-expense", {
    kind: "personal_expense", amount: 205500, occurredAt: "2026-08-25T00:00:00.000Z",
    provider: "moneytree", scope: "personal", direction: "debit",
  });
  for (const row of [income, expense]) row.verification = {
    status: "stale", observed_at: "2026-10-02T07:00:00.000Z", evidence_refs: [],
  };
  const { report } = buildFinancialManagerReport([income, expense], "2026-10-02", {
    sourceFreshness: { moneytree: { status: "partial", reason: "transaction_completeness_unknown" } },
  });
  assert.deepEqual(report.business.today.costs, []);
  assert.deepEqual(report.personal.staleIncome, [{ currency: "JPY", amountMinor: 806201 }]);
  assert.deepEqual(report.personal.staleExpenses, [{ currency: "JPY", amountMinor: 205500 }]);
  assert.match(renderFinancialManagerTelegram(report), /前回観測取引（stale）/);
  assert.match(renderFinancialManagerTelegram(report), /¥205,500/);
  assert.doesNotMatch(renderFinancialManagerTelegram(report), /今日の確認済み支出: ¥205,500/);
});
