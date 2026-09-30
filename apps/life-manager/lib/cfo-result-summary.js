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
function renderResultSummary(table) {
  if (!table || !Array.isArray(table.rows) || !/^\d{4}-\d{2}-\d{2}$/.test(table.reporting_date)) {
    throw new Error("cfo_result_table_invalid");
  }
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
  return lines.join("\n");
}
module.exports = { renderResultSummary, decimalUnits, decimalText };
