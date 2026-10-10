"use strict";

// Fixed point decimal totals without currency conversion or floating point sums.
function decimalUnits(value) {
  const text = String(value);
  if (!/^-?\d+(\.\d{1,18})?$/.test(text)) throw new Error("cfo_amount_invalid");
  const negative = text.startsWith("-");
  const [whole, fraction = ""] = text.replace(/^-/, "").split(".");
  const amount = BigInt(whole) * 10n ** 18n + BigInt(fraction.padEnd(18, "0"));
  return negative ? -amount : amount;
}
function decimalText(value) {
  const negative = value < 0;
  const amount = negative ? -value : value;
  const fraction = String(amount % (10n ** 18n)).padStart(18, "0").replace(/0+$/, "");
  return `${negative ? "-" : ""}${amount / (10n ** 18n)}${fraction ? `.${fraction}` : ""}`;
}
function economicField(scope, field) {
  if (!scope || scope.status !== "verified" || !scope.currencies || typeof scope.currencies !== "object") return null;
  const entries = [];
  for (const [currency, value] of Object.entries(scope.currencies).sort(([a], [b]) => a.localeCompare(b))) {
    const amount = value && typeof value === "object" ? value[field] : value;
    if (amount === null || amount === undefined) return null;
    if (!/^[A-Z][A-Z0-9_]{2,19}$/.test(currency)) throw new Error("cfo_currency_invalid");
    entries.push(`${currency} ${decimalText(decimalUnits(amount))}`);
  }
  return entries.length ? entries.join(" / ") : null;
}
function jpy(value) {
  return Number.isSafeInteger(value) ? `¥${value.toLocaleString("ja-JP")}` : "未確認";
}
function renderPersonalMoneytree(personal) {
  if (!personal || personal.owner !== "dais_personal") return "";
  const lines = [
    "個人 Moneytree（会社P&Lには合算しない）",
    `状態: ${personal.status || "unknown"} | freshness: ${personal.freshness_status || "unknown"} (provider sync: 未確認)`,
  ];
  if (personal.cache_status === "write_failed") {
    lines.push(`snapshot cache: write_failed (${personal.cache_error_class || "unknown"})`);
  }
  if (Array.isArray(personal.balances) && personal.balances.length) {
    for (const balance of personal.balances) {
      lines.push(`残高（最終観測）: ${balance.institution} ${jpy(balance.balance_jpy)} (${balance.observed_at || "観測時刻未確認"}) receipt: ${balance.evidence_ref || "未取得"}`);
    }
  } else {
    lines.push("残高: 未確認");
  }
  const windows = Array.isArray(personal.windows) ? personal.windows : [];
  const complete = windows.filter((window) => window.coverage_status === "complete").length;
  lines.push(`取引coverage: ${windows.length ? `${complete}/${windows.length} windows complete` : "未確認"} (${personal.range_start || "?"}..${personal.range_end || "?"})`);
  for (const window of windows) {
    const start = window.query_start_date || "?";
    const end = window.query_end_date || "?";
    const total = window.provider_total_count === null || window.provider_total_count === undefined
      ? "未確認" : window.provider_total_count;
    const returned = window.returned_count === null || window.returned_count === undefined
      ? "未確認" : window.returned_count;
    const failure = window.error_class ? ` error: ${window.error_class}` : "";
    const mismatch = Number.isSafeInteger(window.range_mismatch_count) && window.range_mismatch_count > 0
      ? ` range-mismatch: ${window.range_mismatch_count}` : "";
    lines.push(`window ${start}..${end}: ${window.coverage_status || "unknown"} (${returned}/${total}) receipt: ${window.evidence_ref || "未取得"}${mismatch}${failure}`);
  }
  for (const window of personal.refresh_windows || []) {
    lines.push(`refresh window ${window.query_start_date}..${window.query_end_date}: ${window.coverage_status || "unknown"} receipt: ${window.evidence_ref || "未取得"} error: ${window.error_class || "unknown"}`);
  }
  if (Array.isArray(personal.monthly) && personal.monthly.length) {
    for (const month of personal.monthly) {
      const receipts = Array.isArray(month.evidence_refs) && month.evidence_refs.length
        ? month.evidence_refs.join(", ") : "未取得";
      lines.push(`${month.month} (${month.coverage_status || "unknown"}): 収入 ${jpy(month.income_jpy)} / 支出（観測小計） ${jpy(month.expense_jpy)} / 現金移動 ${jpy(month.cash_movement_jpy)} receipt: ${receipts}`);
      for (const category of month.categories || []) {
        const observed = [
          Number.isSafeInteger(category.income_jpy) ? `収入 ${jpy(category.income_jpy)}` : null,
          Number.isSafeInteger(category.expense_jpy) ? `支出 ${jpy(category.expense_jpy)}` : null,
          Number.isSafeInteger(category.cash_movement_jpy) ? `現金移動 ${jpy(category.cash_movement_jpy)}` : null,
        ].filter(Boolean);
        if (observed.length) lines.push(`  ${category.category}: ${observed.join(" / ")}`);
      }
    }
  } else {
    lines.push("取引集計: 未確認");
  }
  lines.push(`最新取引: ${personal.latest_transaction_date || "未確認"}`);
  const candidates = Array.isArray(personal.recurring_charge_candidates)
    ? personal.recurring_charge_candidates : [];
  if (candidates.length) {
    lines.push(`定期支出候補（未確認）: ${candidates.map(candidate => (
      `${candidate.merchant} ${candidate.month_count}か月 ${jpy(candidate.total_observed_jpy)} receipt: ${(candidate.evidence_refs || []).join(", ") || "未取得"}`
    )).join(" / ")}`);
  } else {
    lines.push("定期支出候補: 未確認");
  }
  return lines.join("\n");
}
function appendPersonalMoneytree(message, personal) {
  const section = renderPersonalMoneytree(personal);
  return section ? `${message}\n\n${section}` : message;
}
function economicLoops(projection, window) {
  return projection?.[window]?.loops && typeof projection[window].loops === "object"
    ? projection[window].loops : {};
}
function googleBilledExpenseLines(value) {
  if (!value || typeof value !== "object") return [];
  if (value.status === "unavailable" || !Array.isArray(value.invoices) || !value.invoices.length) {
    return ["Google Cloud 請求済み費用: 未確認"];
  }
  const lines = [];
  for (const invoice of value.invoices) {
    const period = typeof invoice?.invoice_period === "string"
      && /^\d{4}-\d{2}$/.test(invoice.invoice_period) ? invoice.invoice_period : null;
    if (invoice?.status !== "verified" || !period || invoice.currency !== "JPY"
      || typeof invoice.billed_total_jpy !== "string") {
      lines.push(`Google Cloud 請求済み費用${period ? ` (${period})` : ""}: 未確認`);
      continue;
    }
    const totals = new Map();
    let detailValid = Array.isArray(invoice.service_sku);
    for (const item of invoice.service_sku || []) {
      if (!item || typeof item.service !== "string" || !item.service.trim()
        || /[\r\n]/.test(item.service) || item.service.length > 160
        || typeof item.net_billed_jpy !== "string") {
        detailValid = false;
        break;
      }
      try {
        const amount = decimalUnits(item.net_billed_jpy);
        totals.set(item.service, (totals.get(item.service) || 0n) + amount);
      } catch {
        detailValid = false;
        break;
      }
    }
    let billedTotal;
    try { billedTotal = decimalText(decimalUnits(invoice.billed_total_jpy)); }
    catch { billedTotal = null; }
    if (billedTotal === null) {
      lines.push(`Google Cloud 請求済み費用 (${period}): 未確認`);
      continue;
    }
    lines.push(`Google Cloud 請求済み費用 (${period}): JPY ${billedTotal}`);
    const serviceTotals = [...totals].sort(([a], [b]) => a.localeCompare(b))
      .map(([service, amount]) => `${service} JPY ${decimalText(amount)}`);
    lines.push(`  サービス内訳: ${detailValid && serviceTotals.length ? serviceTotals.join(" / ") : "未確認"}`);
    const adjustmentFields = [
      ["使用量", "usage_gross_jpy"], ["クレジット", "credits_jpy"],
      ["税", "tax_jpy"], ["丸め", "rounding_jpy"],
    ];
    let adjustmentText = "未確認";
    try {
      adjustmentText = adjustmentFields.map(([label, field]) => {
        const value = invoice.adjustments?.[field];
        if (typeof value !== "string") throw new Error("invoice_adjustment_invalid");
        return `${label} ${decimalText(decimalUnits(value))}`;
      }).join(" / ");
    } catch { adjustmentText = "未確認"; }
    lines.push(`  請求内訳: ${adjustmentText}`);
    let paid = "未確認";
    if (invoice.cash_paid_status === "confirmed" && typeof invoice.cash_paid_jpy === "string") {
      try { paid = `JPY ${decimalText(decimalUnits(invoice.cash_paid_jpy))}`; }
      catch { paid = "未確認"; }
    }
    lines.push(`  支払状況: ${paid} | loop帰属: 未帰属 | B0確定済み純損益には未加算`);
    if (typeof invoice.source_ref === "string"
      && /^google-cloud-cost-table:\/\/sha256\/[a-f0-9]{64}$/.test(invoice.source_ref)) {
      lines.push(`  出典: ${invoice.source_ref}`);
    }
  }
  if (value.status !== "verified") lines.push("Google Cloud 請求書照合: 一部未確認");
  return lines;
}
function providerBilledExpenseLines(value, googleBilledExpenses) {
  if (!value || typeof value !== "object") return [];
  if (!Array.isArray(value.invoices) || !value.invoices.length) {
    return ["Provider billed expense: 未確認"];
  }
  const googleCloudPeriods = new Set(
    (Array.isArray(googleBilledExpenses?.invoices) ? googleBilledExpenses.invoices : [])
      .filter(invoice => invoice?.status === "verified" && invoice.currency === "JPY"
        && typeof invoice.invoice_period === "string" && /^\d{4}-\d{2}$/.test(invoice.invoice_period))
      .map(invoice => invoice.invoice_period),
  );
  const lines = [];
  let googleOverlapUnresolved = false;
  for (const invoice of value.invoices) {
    const provider = typeof invoice?.provider === "string"
      && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(invoice.provider) ? invoice.provider : null;
    const period = typeof invoice?.invoice_period === "string"
      && /^\d{4}-\d{2}$/.test(invoice.invoice_period) ? invoice.invoice_period : null;
    const currency = typeof invoice?.currency === "string"
      && /^[A-Z]{3}$/.test(invoice.currency) ? invoice.currency : null;
    // A verified Google Cost Table owns the Google Cloud invoice display for that JPY period.
    if ((provider === "google_cloud" || provider === "google-cloud")
      && currency === "JPY" && googleCloudPeriods.has(period)) {
      googleOverlapUnresolved = true;
      lines.push(`Provider billed expense (${provider}, ${period}): Google Cloud請求表と期間重複、請求同一性未確認`);
      continue;
    }
    let billedTotal;
    try { billedTotal = decimalText(decimalUnits(invoice?.billed_total)); }
    catch { billedTotal = null; }
    if (invoice?.status !== "verified" || !provider || !period || !currency || billedTotal === null) {
      const label = [provider, period].filter(Boolean).join(", ");
      lines.push(`Provider billed expense${label ? ` (${label})` : ""}: 未確認`);
      continue;
    }
    lines.push(`Provider billed expense (${provider}, ${period}): ${currency} ${billedTotal}`);
    const cash = invoice.cash_paid_status === "paid" ? "支払済み（provider確認）" : "未確認";
    const allocation = invoice.allocation_status === "attributed" ? "配賦済み"
      : invoice.allocation_status === "unattributed" ? "未帰属" : "未確認";
    lines.push(`  支払状況: ${cash} | loop配賦: ${allocation} | 請求表示はB0 netに二重加算しない`);
  }
  if (value.status !== "verified" || googleOverlapUnresolved) {
    lines.push("Provider billed expense source: 一部未確認");
  }
  return lines;
}
function renderEconomicSummary(table, projection) {
  if (!projection || !projection.historical || !projection.trailing || !projection.mrr || !projection.runway) {
    throw new Error("cfo_result_table_invalid");
  }
  const unknown = new Set();
  for (const window of ["historical", "trailing"]) {
    for (const [loopId, scope] of Object.entries(economicLoops(projection, window))) {
      if (!["verified", "zero"].includes(scope?.status)) unknown.add(loopId);
    }
  }
  const historicalRevenue = economicField(projection.historical.company, "settled_external_revenue");
  const trailingRevenue = economicField(projection.trailing.company, "settled_external_revenue");
  const historicalNet = economicField(projection.historical.company, "net");
  const trailingNet = economicField(projection.trailing.company, "net");
  const trailingCost = economicField(projection.trailing.company, "total_cost");
  const mrr = economicField(projection.mrr.company, "monthly");
  const loopMrr = Object.entries(projection.mrr.loops || {}).map(([loopId, scope]) => {
    const amount = economicField(scope, "monthly");
    return amount ? `${loopId} ${amount}` : null;
  }).filter(Boolean);
  const runway = [];
  if (["verified", "positive_cashflow"].includes(projection.runway.status) && projection.runway.currencies) {
    for (const [currency, value] of Object.entries(projection.runway.currencies).sort(([a], [b]) => a.localeCompare(b))) {
      if (!value || !["verified", "positive_cashflow"].includes(value.status)) continue;
      if (value.runway_days === null || value.runway_days === undefined) runway.push(`${currency} positive_cashflow`);
      else runway.push(`${currency} ${decimalText(decimalUnits(value.runway_days))} days`);
    }
  }
  const lines = [
    `Life Manager ${table.reporting_date} (${table.timezone || "Asia/Tokyo"})`,
    `snapshot_at: ${projection.snapshot_at || "未確認"}`,
    `trailing_start: ${projection.trailing_start || "未確認"}`,
    `historical revenue: ${historicalRevenue || "未確認"}`,
    `historical cost-complete net: ${historicalNet || "未確認"}`,
    `trailing revenue: ${trailingRevenue || "未確認"}`,
    `trailing cost-complete cost: ${trailingCost || "未確認"}`,
    `trailing cost-complete net: ${trailingNet || "未確認"}`,
    `MRR: ${mrr || "未確認"}`,
    `確認済みloop MRR: ${loopMrr.join(" / ") || "未確認"}`,
    `runway: ${runway.join(" / ") || "未確認"}`,
    "銀行への入金: 未確認",
  ];
  if (Object.hasOwn(table, "google_billed_expenses")) {
    lines.push(...googleBilledExpenseLines(table.google_billed_expenses));
  }
  if (Object.hasOwn(table, "actual_billed_expenses")) {
    lines.push(...providerBilledExpenseLines(
      table.actual_billed_expenses, table.google_billed_expenses,
    ));
  }
  for (const window of ["historical", "trailing"]) {
    for (const [loopId, scope] of Object.entries(economicLoops(projection, window))) {
      if (scope?.status === "unknown" && Array.isArray(scope.coverage_gaps)) {
        for (const gap of scope.coverage_gaps) unknown.add(`${loopId}(${gap.reason || "gap"})`);
      }
    }
  }
  if (unknown.size) lines.push(`未確認: ${[...unknown].join(", ")}`);
  for (const duplicate of projection.duplicate_receipts || []) {
    lines.push(`duplicate_receipts: ${duplicate.provider}/${duplicate.receipt_id}`);
  }
  lines.push("unknownは0にせず、未確認として保持。売上は銀行入金の証拠ではありません。");
  return lines.join("\n");
}
function renderResultSummary(table) {
  if (!table || !/^\d{4}-\d{2}-\d{2}$/.test(table.reporting_date)) {
    throw new Error("cfo_result_table_invalid");
  }
  if (table.economic_attribution) {
    return appendPersonalMoneytree(renderEconomicSummary(table, table.economic_attribution), table.personal_moneytree);
  }
  if (!Array.isArray(table.rows)) throw new Error("cfo_result_table_invalid");
  const totals = new Map();
  const known = [];
  const unknown = [];
  for (const row of table.rows) {
    const cell = row.revenue;
    if (!/^[a-z0-9-]+$/.test(row.loop_id)) throw new Error("cfo_loop_invalid");
    if (["not_applicable"].includes(cell?.status) || String(cell?.reason || "").startsWith("not_applicable:")) continue;
    if (!["verified", "zero"].includes(cell?.status)) { unknown.push(row.loop_id); continue; }
    const pairs = Object.entries(cell.amounts || {});
    if (cell.status === "verified" && (!pairs.length || !cell.receipts?.length)) {
      throw new Error("cfo_result_receipt_missing");
    }
    const display = [];
    for (const [currency, value] of pairs) {
      const units = decimalUnits(value);
      if (!/^[A-Z][A-Z0-9_]{2,19}$/.test(currency)) throw new Error("cfo_currency_invalid");
      // UNKNOWN has no currency identity and must not be added to a monetary total.
      if (currency === "UNKNOWN") { unknown.push(`${row.loop_id}(通貨)`); display.push(`通貨未確認 ${decimalText(units)}`); }
      else {
        totals.set(currency, (totals.get(currency) || 0n) + units);
        display.push(`${currency} ${decimalText(units)}`);
      }
    }
    known.push(`${row.loop_id}: ${display.join(" / ") || "0(照合済み)"}`);
  }
  const total = [...totals].sort(([a], [b]) => a.localeCompare(b))
    .map(([currency, units]) => `${currency} ${decimalText(units)}`).join(" / ");
  const aggregate = kind => {
    const sums = new Map();
    let complete = true, observed = false;
    for (const row of table.rows) {
      const cell = row[kind];
      if (String(cell?.reason || "").startsWith("not_applicable:") || cell?.status === "not_applicable") continue;
      if (!["verified", "zero"].includes(cell?.status)) { complete = false; continue; }
      observed = true;
      // An empty API usage estimate is not a provider invoice proving zero spend.
      if (kind === "cost" && (cell.sources || []).includes("agent-usage")) complete = false;
      if (cell.incomplete) complete = false;
      if (kind === "cost" && cell.status === "zero" && (cell.sources || []).every(source => source === "agent-usage")) continue;
      for (const [currency, value] of Object.entries(cell.amounts || {})) {
        if (["UNKNOWN", "USD_API_EQUIV"].includes(currency)) { complete = false; continue; }
        if (!cell.receipts?.length) throw new Error("cfo_cost_receipt_missing");
        sums.set(currency, (sums.get(currency) || 0n) + decimalUnits(value));
      }
    }
    return { sums, complete: complete && observed };
  };
  const costs = aggregate("cost");
  const refunds = aggregate("refund");
  const displaySums = sums => [...sums].sort(([a], [b]) => a.localeCompare(b))
    .map(([currency, value]) => `${currency} ${decimalText(value)}`).join(" / ") || "0";
  const canNet = !unknown.length && costs.complete && refunds.complete;
  const net = new Map(totals);
  for (const summary of [costs, refunds]) for (const [currency, value] of summary.sums) {
    net.set(currency, (net.get(currency) || 0n) - value);
  }
  const lines = [
    `Life Manager ${table.reporting_date} (${table.timezone || "Asia/Tokyo"})`,
    `${unknown.length ? "確認済み小計" : "今日の確認済み収益"}: ${total || (known.length ? "0(照合済みソースのみ)" : "未確認")}`,
  ];
  // Sales and realized trading P&L are not bank deposits. Keep the missing settlement explicit.
  lines.push("銀行への入金: 未確認");
  lines.push(`今日の確認済み支出${costs.complete ? "" : "(小計)"}: ${costs.sums.size || costs.complete ? displaySums(costs.sums) : "未確認"} | 差引: ${canNet ? displaySums(net) : "未確認"}`);
  if (known.length) lines.push(known.join(" | "));
  if (unknown.length) lines.push(`未確認: ${[...new Set(unknown)].join(", ")}`);
  lines.push("投資は実現損益。他は売上。API価格換算は請求額ではありません。トークン数・定額契約の日割り: 未確認。");
  return appendPersonalMoneytree(lines.join("\n"), table.personal_moneytree);
}
module.exports = { renderResultSummary, decimalUnits, decimalText };
