"use strict";

const crypto = require("node:crypto");
const { projectFinancialRecord } = require("./financial-record-contract.js");

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonical(value[key])}`
    )).join(",")}}`;
  }
  return JSON.stringify(value);
}

function newestBalances(records) {
  const latest = new Map();
  for (const record of records) {
    if (!["asset_balance", "liability_balance"].includes(record.kind)) continue;
    const key = `${record.source.provider}\n${record.source.external_ref}`;
    const current = latest.get(key);
    if (!current || current.occurred_at < record.occurred_at
      || (current.occurred_at === record.occurred_at
        && current.recorded_at < record.recorded_at)) latest.set(key, record);
  }
  return [...latest.values()];
}

function add(map, currency, value) {
  const next = (map.get(currency) || 0) + value;
  if (!Number.isSafeInteger(next)) throw new Error("Financial Manager total exceeds safe units");
  map.set(currency, next);
}

function sortedAmounts(map) {
  return [...map].sort(([left], [right]) => left.localeCompare(right))
    .map(([currency, amountMinor]) => ({ currency, amountMinor }));
}

function summarizeStalePersonalTransactions(records) {
  const income = new Map();
  const expenses = new Map();
  const dates = [];
  for (const record of records) {
    if (record.scope !== "personal") continue;
    if (record.kind === "personal_income") add(income, record.currency, record.amount_minor);
    if (record.kind === "personal_expense") add(expenses, record.currency, record.amount_minor);
    if (["personal_income", "personal_expense"].includes(record.kind)) dates.push(record.occurred_at);
  }
  dates.sort();
  return {
    income: sortedAmounts(income), expenses: sortedAmounts(expenses),
    period: dates.length ? { start: dates[0], end: dates.at(-1) } : null,
  };
}

function summarizeBusiness(records) {
  const revenue = new Map();
  const costs = new Map();
  const payouts = new Map();
  for (const record of records) {
    if (record.kind === "business_revenue") add(revenue, record.currency, record.amount_minor);
    if (["business_cost", "fee", "tax"].includes(record.kind)) {
      add(costs, record.currency, record.amount_minor);
    }
    if (record.kind === "payout") add(payouts, record.currency, record.amount_minor);
  }
  const profit = new Map(revenue);
  for (const [currency, amount] of costs) add(profit, currency, -amount);
  return {
    revenue: sortedAmounts(revenue), costs: sortedAmounts(costs),
    profit: sortedAmounts(profit), payouts: sortedAmounts(payouts),
  };
}

const PROVIDER_LANES = Object.freeze(["poi", "transit", "geocoder"]);

function boundedLaneText(value) {
  const text = String(value == null ? "" : value).trim();
  return text && text.length <= 64 && /^[A-Za-z0-9_.:-]+$/.test(text) ? text : null;
}

function normalizeProviderLanes(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const lanes = {};
  for (const name of PROVIDER_LANES) {
    const row = value[name];
    if (!row || typeof row !== "object" || Array.isArray(row)) continue;
    const status = ["fresh", "partial", "stale", "unavailable", "unknown"].includes(row.status)
      ? row.status : "unknown";
    const calls = Number(row.fallbackCalls);
    const cap = Number(row.fallbackCap);
    lanes[name] = {
      status,
      primary: boundedLaneText(row.primary),
      fallbackCalls: Number.isFinite(calls) && calls >= 0 ? calls : 0,
      fallbackCap: Number.isFinite(cap) && cap >= 0 ? cap : 0,
      ...(Number.isFinite(Number(row.eventCount)) ? { eventCount: Number(row.eventCount) } : {}),
      ...(Number.isFinite(Number(row.providerUnits)) ? { providerUnits: Number(row.providerUnits) } : {}),
      ...(Number.isFinite(Number(row.estimatedUsd)) ? { estimatedUsd: Number(row.estimatedUsd) } : {}),
      ...(Number.isFinite(Number(row.unknownCount)) ? { unknownCount: Number(row.unknownCount) } : {}),
    };
  }
  return Object.keys(lanes).length ? lanes : null;
}

function normalizeProviderLaneReadback(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const status = ["fresh", "partial", "stale", "unavailable", "unknown"].includes(value.status)
    ? value.status : "unknown";
  const failures = Array.isArray(value.failures)
    ? value.failures.map((item) => String(item)).filter((item) => /^[a-z0-9_:-]{1,128}$/.test(item)).slice(0, 32)
    : [];
  return {
    status,
    observedAt: value.observedAt == null ? null : String(value.observedAt),
    failures,
  };
}

function inRange(records, start, end) {
  return records.filter((record) => {
    const occurred = Date.parse(record.occurred_at);
    return occurred >= start && occurred < end;
  });
}

function addDays(key, days) {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

function zonedMidnight(key, timezone) {
  const [year, month, day] = key.split("-").map(Number);
  const wallUtc = Date.UTC(year, month - 1, day);
  let instant = wallUtc;
  for (let pass = 0; pass < 2; pass += 1) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en", {
      timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
    }).formatToParts(new Date(instant)).filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]));
    const represented = Date.UTC(
      Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour), Number(parts.minute), Number(parts.second),
    );
    instant = wallUtc - (represented - instant);
  }
  return instant;
}

function buildFinancialManagerReport(rawRecords, reportingDate, {
  timezone = "Asia/Tokyo", economicSourceCoverage = null, sourceFreshness = null,
  businessSourceCoverage = [], businessReadback = null, providerCostSettlement = null, providerBudget = null,
  providerLanes = null, providerLaneReadback = null,
} = {}) {
  const records = rawRecords.map(projectFinancialRecord);
  const staleProviders = new Set(Object.entries(sourceFreshness || {})
    .filter(([, value]) => value && value.status !== "fresh")
    .map(([provider]) => provider));
  const verified = records.filter((record) => record.verification.status === "verified"
    && !staleProviders.has(record.source.provider));
  const stale = records.filter((record) => record.verification.status === "stale"
    || (record.verification.status === "verified" && staleProviders.has(record.source.provider)));
  const month = reportingDate.slice(0, 7);
  const [year, monthNumber] = month.split("-").map(Number);
  const monthStart = zonedMidnight(`${month}-01`, timezone);
  const nextYear = monthNumber === 12 ? year + 1 : year;
  const nextMonth = monthNumber === 12 ? 1 : monthNumber + 1;
  const monthEnd = zonedMidnight(
    `${String(nextYear).padStart(4, "0")}-${String(nextMonth).padStart(2, "0")}-01`, timezone,
  );
  const verifiedBusiness = verified.filter((record) => record.scope === "business");
  const currentBusiness = inRange(verifiedBusiness, monthStart, monthEnd);
  const dayStart = zonedMidnight(reportingDate, timezone);
  const dayEnd = zonedMidnight(addDays(reportingDate, 1), timezone);
  const sevenDayStartLabel = addDays(reportingDate, -6);
  const sevenDayStart = zonedMidnight(sevenDayStartLabel, timezone);
  const balances = newestBalances(verified);
  const staleBalances = newestBalances(stale);
  const staleTransactions = summarizeStalePersonalTransactions(stale);
  const assets = new Map();
  const liabilities = new Map();
  const staleAssets = new Map();
  const staleLiabilities = new Map();
  for (const record of balances) {
    add(record.kind === "asset_balance" ? assets : liabilities, record.currency, record.amount_minor);
  }
  for (const record of staleBalances) {
    add(record.kind === "asset_balance" ? staleAssets : staleLiabilities, record.currency, record.amount_minor);
  }
  const included = [...balances, ...currentBusiness];
  const providers = [...new Set(included.map((record) => record.source.provider))].sort();
  const netWorth = new Map(assets);
  for (const [currency, amount] of liabilities) add(netWorth, currency, -amount);
  const monthSummary = summarizeBusiness(currentBusiness);
  const byProvider = [...new Set(currentBusiness.map((record) => record.source.provider))]
    .sort()
    .map((provider) => ({
      provider,
      ...summarizeBusiness(currentBusiness.filter((record) => record.source.provider === provider)),
    }));
  const report = {
    schemaVersion: 1,
    reportingDate,
    verifiedRecordCount: included.length,
    excludedRecordCount: records.length - verified.length,
    personal: {
      assets: sortedAmounts(assets), liabilities: sortedAmounts(liabilities),
      netWorth: sortedAmounts(netWorth),
      staleAssets: sortedAmounts(staleAssets), staleLiabilities: sortedAmounts(staleLiabilities),
      staleIncome: staleTransactions.income, staleExpenses: staleTransactions.expenses,
      staleTransactionPeriod: staleTransactions.period,
    },
    business: {
      period: month,
      ...monthSummary,
      today: {
        period: reportingDate,
        ...summarizeBusiness(inRange(verifiedBusiness, dayStart, dayEnd)),
        byProvider: [...new Set(inRange(verifiedBusiness, dayStart, dayEnd).map(r => r.source.provider))]
          .sort().map(provider => ({ provider, ...summarizeBusiness(
            inRange(verifiedBusiness, dayStart, dayEnd).filter(r => r.source.provider === provider)) })),
      },
      last7Days: {
        period: { start: sevenDayStartLabel, end: reportingDate },
        ...summarizeBusiness(inRange(verifiedBusiness, sevenDayStart, dayEnd)),
      },
      byProvider,
    },
    providers,
    economicSourceCoverage,
    sourceFreshness: sourceFreshness || {},
    partial: Object.values(sourceFreshness || {}).some((value) => value && value.status !== "fresh")
      || Boolean(providerBudget && providerBudget.state && providerBudget.state !== "normal"),
    businessSourceCoverage: Array.isArray(businessSourceCoverage) ? businessSourceCoverage : [],
    providerLanes: normalizeProviderLanes(providerLanes),
    providerLaneReadback: normalizeProviderLaneReadback(providerLaneReadback),
    businessReadback: businessReadback ? {
      status: businessReadback.status || "unknown",
      observedAt: businessReadback.observedAt || null,
      sourceReceiptRefs: Array.isArray(businessReadback.sourceReceiptRefs)
        ? businessReadback.sourceReceiptRefs : [],
      coverageGaps: Array.isArray(businessReadback.coverageGaps)
      ? businessReadback.coverageGaps : [],
      coverageSummary: Array.isArray(businessReadback.coverageSummary)
        ? businessReadback.coverageSummary.map((row) => ({
          sourceId: String(row.sourceId || "unreported"), reason: String(row.reason || "unknown"),
          count: Number(row.count) || 0,
          productLoopIds: Array.isArray(row.productLoopIds) ? row.productLoopIds.map(String) : [],
          categories: Array.isArray(row.categories) ? row.categories.map(String) : [],
        })) : [],
    } : null,
    providerCostSettlement: providerCostSettlement ? {
      status: providerCostSettlement.status || "unknown",
      observedAt: providerCostSettlement.observedAt || null,
      receiptRef: providerCostSettlement.receiptRef || null,
      invoiceMonth: providerCostSettlement.invoiceMonth || null,
      invoiceTotalJpy: providerCostSettlement.invoiceTotalJpy || null,
      roundingJpy: providerCostSettlement.roundingJpy || null,
      totals: providerCostSettlement.totals || null,
      serviceTotals: Array.isArray(providerCostSettlement.serviceTotals)
        ? providerCostSettlement.serviceTotals.map((row) => ({
          service: String(row.service || ""), costJpy: String(row.costJpy || ""), currency: "JPY",
        })) : [],
    } : null,
    providerBudget: providerBudget ? {
      state: providerBudget.state || "unknown",
      totalUsd: providerBudget.totalUsd == null ? null : providerBudget.totalUsd,
      unknownCount: providerBudget.unknownCount == null ? null : providerBudget.unknownCount,
      reasons: Array.isArray(providerBudget.reasons) ? providerBudget.reasons : [],
      ...(providerBudget.capKey != null ? { capKey: String(providerBudget.capKey) } : {}),
      ...(providerBudget.capState != null ? { capState: String(providerBudget.capState) } : {}),
      ...(providerBudget.nextAction != null ? { nextAction: String(providerBudget.nextAction) } : {}),
      ...(providerBudget.providerUnits != null ? { providerUnits: Number(providerBudget.providerUnits) || 0 } : {}),
      ...(providerBudget.estimatedUsd != null ? { estimatedUsd: Number(providerBudget.estimatedUsd) || 0 } : {}),
      ...(providerBudget.settledUsd != null ? { settledUsd: Number(providerBudget.settledUsd) || 0 } : {}),
    } : null,
  };
  if (report.providerLanes && Object.values(report.providerLanes).some((lane) => lane.status !== "fresh")) {
    report.partial = true;
  }
  const digestReport = { ...report };
  delete digestReport.verifiedRecordCount;
  delete digestReport.excludedRecordCount;
  delete digestReport.economicSourceCoverage;
  return {
    report,
    digest: crypto.createHash("sha256").update(canonical(digestReport)).digest("hex"),
  };
}

function money({ currency, amountMinor }) {
  const digits = new Map([
    ["JPY", 0], ["USD", 2], ["EUR", 2], ["GBP", 2], ["USDC", 6], ["USDT", 6],
  ]).get(currency);
  if (digits === undefined) return `${currency} minor ${amountMinor}`;
  const negative = amountMinor < 0;
  const units = BigInt(Math.abs(amountMinor));
  const scale = 10n ** BigInt(digits);
  const whole = (units / scale).toLocaleString("ja-JP");
  const rawFraction = String(units % scale).padStart(digits, "0");
  const fraction = digits === 0 ? "" : `.${rawFraction.replace(/0+$/, "").padEnd(2, "0")}`;
  const formatted = `${negative ? "-" : ""}${whole}${fraction}`;
  return currency === "JPY" ? `¥${formatted}` : `${currency} ${formatted}`;
}

function moneyJpyText(value) {
  if (typeof value !== "string" || !/^-?\d+$/.test(value)) return "未確認";
  return `¥${BigInt(value).toLocaleString("ja-JP")}`;
}

function moneyJpyDecimalText(value) {
  if (typeof value !== "string" || !/^-?\d+(?:\.\d+)?$/.test(value)) return "未確認";
  const negative = value.startsWith("-");
  const unsigned = negative ? value.slice(1) : value;
  const [whole, fraction = ""] = unsigned.split(".");
  return `¥${negative ? "-" : ""}${BigInt(whole).toLocaleString("ja-JP")}${fraction ? `.${fraction}` : ""}`;
}

function rows(label, values) {
  return values.length ? values.map((value) => `${label}：${money(value)}`).join("\n") : `${label}：確認済みデータなし`;
}

function hasAmounts(summary) {
  return ["revenue", "costs", "profit", "payouts"].some((key) => summary[key].length > 0);
}

function businessLines(label, summary) {
  if (!hasAmounts(summary)) return [];
  return [
    label,
    ...(summary.revenue.length ? [rows("収益", summary.revenue)] : []),
    ...(summary.costs.length ? [rows("コスト", summary.costs)] : []),
    ...(summary.profit.length ? [rows("利益", summary.profit)] : []),
    ...(summary.payouts.length ? [rows("入金移動（収益に重複計上しない）", summary.payouts)] : []),
  ];
}

function renderFinancialManagerDetailed(report) {
  const lines = ["💰 Financial Manager"];
  if (report.personal.assets.length || report.personal.liabilities.length) {
    lines.push(
      "", "個人資産",
      ...(report.personal.assets.length ? [rows("資産", report.personal.assets)] : []),
      ...(report.personal.liabilities.length ? [rows("負債", report.personal.liabilities)] : []),
      ...(report.personal.netWorth.length ? [rows("純資産", report.personal.netWorth)] : []),
    );
  }
  if (report.personal.staleAssets.length || report.personal.staleLiabilities.length) {
    lines.push(
      "", "前回観測残高（stale）",
      ...(report.personal.staleAssets.length ? [rows("資産", report.personal.staleAssets)] : []),
      ...(report.personal.staleLiabilities.length ? [rows("負債", report.personal.staleLiabilities)] : []),
      "最新確認: 未確認",
    );
  }
  if (report.personal.staleIncome.length || report.personal.staleExpenses.length) {
    lines.push(
      "", "前回観測取引（stale）",
      ...(report.personal.staleIncome.length ? [rows("収入", report.personal.staleIncome)] : []),
      ...(report.personal.staleExpenses.length ? [rows("支出", report.personal.staleExpenses)] : []),
      `観測範囲: ${report.personal.staleTransactionPeriod?.start || "未確認"} ～ ${report.personal.staleTransactionPeriod?.end || "未確認"}`,
      "最新確認: 未確認",
    );
  }
  lines.push(...businessLines("\n事業（今日）", report.business.today));
  lines.push(...businessLines("\n事業（直近7日）", report.business.last7Days));
  lines.push(...businessLines(`\n事業（${report.business.period}）`, report.business));
  if (report.businessSourceCoverage?.length) {
    lines.push("\n事業ソース照合", report.businessSourceCoverage.map((source) => (
      `${source.source}:${source.state}（観測 ${source.observedAt || "未確認"}、receipt ${source.receiptCount || 0}`
      + `${source.gapReason ? `、理由 ${source.gapReason}` : ""}）`
    )).join("\n"));
  }
  if (report.businessReadback?.coverageGaps?.length) {
    lines.push(`事業未確認: ${report.businessReadback.coverageGaps.map((gap) => (
      `${gap.product_loop_id || "source"}/${gap.reason || "gap"}`
    )).join("、")}`);
  }
  if (report.businessReadback?.coverageSummary?.length) {
    lines.push("事業gap要約", report.businessReadback.coverageSummary.map((gap) => (
      `${gap.sourceId}/${gap.reason}=${gap.count}`
      + `${gap.categories.length ? ` [${gap.categories.join(",")}]` : ""}`
      + `${gap.productLoopIds.length ? ` (${gap.productLoopIds.join(",")})` : ""}`
    )).join("\n"));
  }
  if (report.providerCostSettlement) {
    const settlement = report.providerCostSettlement;
    lines.push(`Google請求: ${settlement.status === "settled"
      ? `${settlement.status} ${settlement.invoiceMonth ? `${settlement.invoiceMonth} ` : ""}${moneyJpyText(settlement.totals?.totalJpy)}` : "未確認"}`);
    if (settlement.status === "settled" && settlement.serviceTotals?.length) {
      lines.push("Google請求内訳", settlement.serviceTotals.map((row) => (
        `${row.service}: ${moneyJpyDecimalText(row.costJpy)}`
      )).join("\n"));
    }
  }
  if (report.providerBudget) {
    lines.push(`Provider予算: ${report.providerBudget.state}${report.providerBudget.unknownCount ? `（unknown ${report.providerBudget.unknownCount}）` : ""}`
      + `${report.providerBudget.capKey ? ` [${report.providerBudget.capKey}]` : ""}`
      + `${report.providerBudget.nextAction ? ` →${report.providerBudget.nextAction}` : ""}`);
  }
  if (report.providerLanes) {
    lines.push("Provider lane", Object.entries(report.providerLanes).map(([lane, value]) => (
      `${lane}:${value.status} primary=${value.primary || "未確認"} fallback=${value.fallbackCalls}/${value.fallbackCap}`
    )).join(" | "));
  }
  if (report.providerLaneReadback && report.providerLaneReadback.status !== "fresh") {
    lines.push(`Provider lane readback: ${report.providerLaneReadback.status}`
      + `${report.providerLaneReadback.failures.length ? ` (${report.providerLaneReadback.failures.join(",")})` : ""}`);
  }
  const revenueProviders = report.business.byProvider.filter((item) => item.revenue.length);
  if (revenueProviders.length) {
    lines.push("\n収益内訳（今月・プロバイダー別）");
    for (const item of revenueProviders) {
      lines.push(item.provider, rows("収益", item.revenue));
    }
  }
  lines.push(
    "",
    `確認済み記録：${report.verifiedRecordCount}件`,
    `未確認のため合計から除外：${report.excludedRecordCount}件`,
    `根拠プロバイダー：${report.providers.join("、") || "なし"}`,
  );
  const freshness = Object.entries(report.sourceFreshness || {})
    .filter(([, value]) => value && value.status !== "fresh")
    .map(([source, value]) => `${source}:${value.status || "unknown"}(${value.reason || "未確認"}`
      + `${value.next_action ? `→${value.next_action}` : ""})`);
  if (freshness.length) lines.push(`⚠️ 未確認/古いソース：${freshness.join("、")}`);
  return lines.join("\n");
}

function renderFinancialManagerTelegram(report) {
  const today = report.business.today;
  const amounts = values => values.length ? values.map(money).join(" / ") : "未確認";
  const lines = [`Life Manager ${report.reportingDate}`, `今日の確認済み売上: ${amounts(today.revenue)}`];
  if (report.personal.staleAssets.length || report.personal.staleLiabilities.length) {
    lines.push(`前回観測残高（stale）: ${amounts(report.personal.staleAssets)} / 最新確認: 未確認`);
  }
  if (report.personal.staleIncome.length || report.personal.staleExpenses.length) {
    lines.push(`前回観測取引（stale）: 収入 ${amounts(report.personal.staleIncome)} / 支出 ${amounts(report.personal.staleExpenses)} / 最新確認: 未確認`);
  }
  const providers = today.byProvider || [];
  if (providers.length) lines.push(providers.filter(p => p.revenue.length)
    .map(p => `${p.provider}: ${amounts(p.revenue)}`).join(" | "));
  lines.push(`銀行への入金: 未確認 | 今日の確認済み支出: ${amounts(today.costs)} | 差引: 未確認`);
  if (report.businessSourceCoverage?.length) {
    lines.push(`事業ソース照合: ${report.businessSourceCoverage.map((source) => (
      `${source.source}:${source.state}${source.gapReason ? `(${source.gapReason})` : ""}`
    )).join(" | ")}`);
  }
  if (report.businessReadback?.coverageGaps?.length) {
    lines.push(`事業未確認: ${report.businessReadback.coverageGaps.map((gap) => (
      `${gap.product_loop_id || "source"}/${gap.reason || "gap"}`
    )).join("、")}`);
  }
  if (report.businessReadback?.coverageSummary?.length) {
    lines.push(`事業gap要約: ${report.businessReadback.coverageSummary.map((gap) => (
      `${gap.sourceId}/${gap.reason}=${gap.count}`
    )).join(" | ")}`);
  }
  if (report.providerCostSettlement) {
    const settlement = report.providerCostSettlement;
    lines.push(`Google請求: ${settlement.status === "settled"
      ? `${settlement.status} ${settlement.invoiceMonth ? `${settlement.invoiceMonth} ` : ""}${moneyJpyText(settlement.totals?.totalJpy)}` : "未確認"}`);
    if (settlement.status === "settled" && settlement.serviceTotals?.length) {
      lines.push(`Google請求内訳: ${settlement.serviceTotals.map((row) => (
        `${row.service} ${moneyJpyDecimalText(row.costJpy)}`
      )).join(" / ")}`);
    }
  }
  if (report.providerBudget) {
    lines.push(`Provider予算: ${report.providerBudget.state}${report.providerBudget.unknownCount ? ` (unknown ${report.providerBudget.unknownCount})` : ""}`
      + `${report.providerBudget.capKey ? ` [${report.providerBudget.capKey}]` : ""}`
      + `${report.providerBudget.nextAction ? ` ->${report.providerBudget.nextAction}` : ""}`);
  }
  if (report.providerLanes) {
    lines.push(`Provider lane: ${Object.entries(report.providerLanes).map(([lane, value]) => (
      `${lane}:${value.status} ${value.fallbackCalls}/${value.fallbackCap}`
    )).join(" | ")}`);
  }
  if (report.providerLaneReadback && report.providerLaneReadback.status !== "fresh") {
    lines.push(`Provider lane readback: ${report.providerLaneReadback.status}`
      + `${report.providerLaneReadback.failures.length ? ` (${report.providerLaneReadback.failures.join(",")})` : ""}`);
  }
  lines.push("トークン数・定額契約の日割り: 未確認");
  // Absence of records is never proof of zero, and revenue minus incomplete costs is not profit.
  const missing = (report.economicSourceCoverage?.loops || [])
    .filter(loop => ["customer_revenue", "investment"].includes(loop.role)
      && !["empty", "observed_verified", "not_applicable"].includes(loop.sources?.financial?.state))
    .map(loop => loop.product_loop_id);
  lines.push(missing.length ? `未確認: ${missing.join(", ")}` : "全ソースの照合は未確認。売上は利益ではありません。");
  const freshness = Object.entries(report.sourceFreshness || {})
    .filter(([, value]) => value && value.status !== "fresh")
    .map(([source, value]) => `${source}:${value.status || "unknown"}(${value.reason || "未確認"}`
      + `${value.next_action ? `→${value.next_action}` : ""})`);
  if (freshness.length) lines.push(`未確認/古いソース: ${freshness.join("、")}`);
  return lines.filter(Boolean).join("\n");
}

module.exports = { buildFinancialManagerReport, renderFinancialManagerTelegram, renderFinancialManagerDetailed };
