"use strict";

const {
  containsSensitiveDisplayValue,
  formatCurrencyAmount,
  safeDate,
  safeHttpsLink,
} = require("./panel-display-policy.js");
const {
  SCORE_NAMES,
  validScoreOrgan,
} = require("./panel-score-display-contract.js");

const SAFE_TIMELINE_SENTENCE = "予定の詳細を安全に表示できず、次はカレンダーで開始時刻を確認してください。";
const CONNECTION_NAMES = Object.freeze(["calendar", "telegram", "location", "call", "email", "wallet"]);
const CONNECTION_STATES = new Set(["connected", "action_required", "error", "unavailable"]);
const CONTROL_NAMES = Object.freeze(["delegation", "physical_automation", "mental_automation", "financial_automation"]);
const API_COST_UNITS = new Set(["request", "tokens", "grounded_prompt", "seconds_proxy"]);
const SAFE_API_COST_LABEL = /^[A-Za-z0-9][A-Za-z0-9 .:_/-]{0,127}$/;

class PanelSectionUnavailableError extends Error {
  constructor(section) {
    super("section_unavailable");
    this.name = "PanelSectionUnavailableError";
    this.code = "section_unavailable";
    this.section = section;
  }
}

function fail(section) {
  throw new PanelSectionUnavailableError(section);
}

function record(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function exactKeys(value, keys) {
  if (!record(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length
    && actual.every((key, index) => key === expected[index]);
}

function validDisplayText(value) {
  return typeof value === "string"
    && value.trim().length > 0
    && value.length <= 1000
    && !containsSensitiveDisplayValue(value);
}

function validTimeZone(value) {
  if (typeof value !== "string" || containsSensitiveDisplayValue(value)) return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: value }).format(0);
    return true;
  } catch {
    return false;
  }
}

function clockText(value, timeZone) {
  const parsed = Date.parse(String(value || ""));
  if (!Number.isFinite(parsed)) return null;
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(parsed));
}

function timelineStatus(decision) {
  return Object.freeze({
    offline: "カレンダーで確認",
    travel: "移動準備",
    ready: "準備完了",
    question: "確認が必要",
  })[decision] || "確認が必要";
}

const CALL_OUTCOME_COPY = Object.freeze({
  conversation: Object.freeze({ sentence: "会話できました。", status: "会話できた" }),
  no_answer: Object.freeze({ sentence: "予定前に発信しました（応答なし）。", status: "応答なし" }),
  dial_failed: Object.freeze({ sentence: "発信できませんでした。", status: "発信失敗" }),
});

function projectVoiceUsage(value) {
  if (!record(value)
    || typeof value.available !== "boolean"
    || !Number.isInteger(value.limit_seconds) || value.limit_seconds !== 3600
    || !/^\d{4}-\d{2}-\d{2}$/.test(String(value.reset_at || ""))) {
    fail("timeline");
  }
  if (!value.available) {
    if (value.used_seconds !== null || value.remaining_seconds !== null) fail("timeline");
    return {
      available: false, used_seconds: null, limit_seconds: value.limit_seconds,
      remaining_seconds: null, reset_at: value.reset_at,
    };
  }
  if (!Number.isInteger(value.used_seconds) || value.used_seconds < 0
    || !Number.isInteger(value.remaining_seconds) || value.remaining_seconds < 0
    || value.used_seconds > value.limit_seconds
    || value.remaining_seconds !== value.limit_seconds - value.used_seconds) {
    fail("timeline");
  }
  return {
    available: true, used_seconds: value.used_seconds, limit_seconds: value.limit_seconds,
    remaining_seconds: value.remaining_seconds, reset_at: value.reset_at,
  };
}

function projectTimeline(candidate) {
  if (
    !record(candidate)
    || !/^\d{4}-\d{2}-\d{2}$/.test(String(candidate.date || ""))
    || !validTimeZone(candidate.timezone)
    || !Array.isArray(candidate.events)
    || !Array.isArray(candidate.calls)
  ) fail("timeline");

  const items = [];
  for (const event of candidate.events) {
    if (!record(event)) fail("timeline");
    const hostile = containsSensitiveDisplayValue(event);
    const time = clockText(event.start_at, candidate.timezone);
    items.push({
      sentence: hostile || !time
        ? SAFE_TIMELINE_SENTENCE
        : `${time}開始の予定です。詳細はカレンダーで確認してください。`,
      status: hostile ? "確認が必要" : timelineStatus(event.interpretation && event.interpretation.decision),
    });
  }
  for (const call of candidate.calls) {
    if (!record(call)) fail("timeline");
    const time = clockText(call.called_at, candidate.timezone);
    const legacyConversation = typeof call.answered_at === "string" && Number.isFinite(Date.parse(call.answered_at));
    const outcome = call.call_outcome || (legacyConversation ? "conversation" : null);
    const copy = outcome ? CALL_OUTCOME_COPY[outcome] : null;
    if (outcome && !copy) fail("timeline");
    items.push({
      sentence: time
        ? `${time}の電話は${copy ? copy.sentence : "結果を確認中です。"}`
        : "電話の状態を安全に表示できませんでした。",
      status: copy ? copy.status : "確認中",
    });
  }
  return { date: candidate.date, timezone: candidate.timezone, voice_usage: projectVoiceUsage(candidate.voice_usage), items };
}

function financialAmount(row) {
  const currency = typeof row.currency === "string" ? row.currency : "USD";
  if (row.amount != null) return formatCurrencyAmount(row.amount, currency);
  if (row.amount_minor != null) return formatCurrencyAmount(Number(row.amount_minor) / 100, currency);
  if (
    typeof row.amount_atomic === "string"
    && /^\d+$/.test(row.amount_atomic)
    && Number.isInteger(row.amount_decimals)
    && row.amount_decimals >= 0
    && row.amount_decimals <= 6
    && /^[A-Z]{3}$/.test(currency)
  ) {
    const padded = row.amount_atomic.padStart(row.amount_decimals + 1, "0");
    const whole = row.amount_decimals === 0 ? padded : padded.slice(0, -row.amount_decimals);
    const rawFraction = row.amount_decimals === 0 ? "" : padded.slice(-row.amount_decimals);
    const fraction = rawFraction.replace(/0+$/, "").padEnd(2, "0");
    return `${currency} ${whole}.${fraction}`;
  }
  if (row.est_usd != null) {
    const meta = record(row.meta) ? row.meta : {};
    const estimate = Number(row.est_usd);
    const zeroKnown = meta.cache_hit === true || meta.estimate_status === "estimated"
      || meta.estimate_status === "not_applicable";
    if (meta.estimate_status !== "unavailable" && Number.isFinite(estimate)
      && (estimate !== 0 || zeroKnown)) return formatCurrencyAmount(estimate, "USD");
  }
  return null;
}

function ledgerItem(row, label) {
  if (!record(row)) return {
    label,
    date: "日付不明",
    amount: "金額不明",
    link: null,
  };
  const linkSource = row.link || row.on_chain_url || row.transaction_url || row.href || null;
  return {
    label,
    date: safeDate(row.ts || row.occurred_at || row.date || row.created_at) || "日付不明",
    amount: financialAmount(row) || "金額不明",
    link: safeHttpsLink(linkSource),
  };
}

function safeApiCostLabel(value) {
  return typeof value === "string"
    && SAFE_API_COST_LABEL.test(value)
    && !containsSensitiveDisplayValue(value);
}

function apiCostCount(value) {
  if (typeof value === "string" && !/^\d+$/.test(value)) return null;
  if (typeof value !== "number" && typeof value !== "string") return null;
  const count = Number(value);
  return Number.isSafeInteger(count) && count >= 0 ? count : null;
}

function apiCostDecimal(value) {
  if (value == null) return null;
  const source = typeof value === "number" && Number.isFinite(value)
    ? String(value) : typeof value === "string" ? value.trim() : "";
  if (source.length === 0 || source.length > 100
    || !/^\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(source)) return undefined;
  const [mantissa, exponentText] = source.toLowerCase().split("e");
  if (exponentText == null) return source;
  const exponent = Number(exponentText);
  if (!Number.isSafeInteger(exponent) || Math.abs(exponent) > 80) return undefined;
  const [whole, fraction = ""] = mantissa.split(".");
  const digits = `${whole}${fraction}`;
  const decimalPosition = whole.length + exponent;
  if (decimalPosition <= 0) return `0.${"0".repeat(-decimalPosition)}${digits}`;
  if (decimalPosition >= digits.length) return `${digits}${"0".repeat(decimalPosition - digits.length)}`;
  return `${digits.slice(0, decimalPosition)}.${digits.slice(decimalPosition)}`;
}

function emptyApiCostCounts() {
  return {
    event_count: 0,
    request_count: 0,
    cache_hit_count: 0,
    cache_miss_count: 0,
    estimated_event_count: 0,
    settled_event_count: 0,
    unknown_estimate_event_count: 0,
    unknown_actual_event_count: 0,
    not_applicable_count: 0,
  };
}

function projectApiCostGroup(row) {
  if (!record(row)) return null;
  const sku = row.sku == null ? "unknown" : row.sku;
  if (!safeApiCostLabel(row.provider)
    || !safeApiCostLabel(sku)
    || !safeApiCostLabel(row.operation)
    || !API_COST_UNITS.has(row.unit)) return null;
  const eventCount = apiCostCount(row.event_count);
  const requestCount = apiCostCount(row.request_count);
  const cacheHitCount = apiCostCount(row.cache_hit_count);
  const cacheMissCount = apiCostCount(row.cache_miss_count);
  const unknownEstimateCount = apiCostCount(row.unknown_estimate_event_count);
  const unknownActualCount = apiCostCount(row.unknown_actual_event_count);
  const notApplicableCount = apiCostCount(row.not_applicable_count);
  const providerUnits = apiCostDecimal(row.provider_units);
  const estimatedCost = apiCostDecimal(row.estimated_cost_usd);
  const settledCost = apiCostDecimal(row.settled_cost_usd);
  if ([eventCount, requestCount, cacheHitCount, cacheMissCount, unknownEstimateCount,
    unknownActualCount, notApplicableCount].some((value) => value == null)
    || providerUnits === undefined || estimatedCost === undefined || settledCost === undefined
    || eventCount === 0
    || requestCount > eventCount
    || (row.unit !== "request" && requestCount !== 0)
    || cacheHitCount + cacheMissCount !== eventCount
    || unknownEstimateCount > eventCount
    || unknownActualCount + notApplicableCount > eventCount) return null;

  const estimatedEventCount = eventCount - unknownEstimateCount;
  const settledEventCount = eventCount - unknownActualCount - notApplicableCount;
  if ((estimatedEventCount === 0) !== (estimatedCost === null)
    || (settledEventCount === 0) !== (settledCost === null)) return null;
  const estimateStatus = unknownEstimateCount === 0 ? "estimated"
    : estimatedEventCount === 0 ? "unknown" : "partial";
  const actualStatus = settledEventCount > 0
    ? (unknownActualCount > 0 ? "partial" : "settled")
    : unknownActualCount > 0 ? "unknown" : "not_applicable";
  return {
    provider: row.provider,
    sku,
    operation: row.operation,
    unit: row.unit,
    event_count: eventCount,
    request_count: requestCount,
    cache_hit_count: cacheHitCount,
    cache_miss_count: cacheMissCount,
    provider_units: providerUnits,
    estimated_cost_usd: estimatedCost,
    settled_cost_usd: settledCost,
    estimate_status: estimateStatus,
    actual_status: actualStatus,
    unknown_estimate_event_count: unknownEstimateCount,
    unknown_actual_event_count: unknownActualCount,
    not_applicable_count: notApplicableCount,
  };
}

function projectApiCostPeriod(candidate) {
  if (!record(candidate)
    || typeof candidate.period_start !== "string"
    || typeof candidate.period_end !== "string"
    || !Number.isFinite(Date.parse(candidate.period_start))
    || !Number.isFinite(Date.parse(candidate.period_end))) fail("ledger");
  const period = {
    period_start: candidate.period_start,
    period_end: candidate.period_end,
  };
  const unavailable = () => ({
    status: "unavailable", ...period, counts: null, groups: null,
  });
  if (candidate.status === "unavailable" && candidate.rows === null) return unavailable();
  if (candidate.status === "verified_empty" && Array.isArray(candidate.rows)
    && candidate.rows.length === 0) {
    return { status: "verified_empty", ...period, counts: emptyApiCostCounts(), groups: [] };
  }
  if (candidate.status !== "available" || !Array.isArray(candidate.rows)
    || candidate.rows.length === 0) return unavailable();
  const groups = candidate.rows.map(projectApiCostGroup);
  if (groups.some((group) => group === null)) return unavailable();
  const counts = emptyApiCostCounts();
  for (const group of groups) {
    counts.event_count += group.event_count;
    counts.request_count += group.request_count;
    counts.cache_hit_count += group.cache_hit_count;
    counts.cache_miss_count += group.cache_miss_count;
    counts.estimated_event_count += group.event_count - group.unknown_estimate_event_count;
    counts.settled_event_count += group.event_count - group.unknown_actual_event_count - group.not_applicable_count;
    counts.unknown_estimate_event_count += group.unknown_estimate_event_count;
    counts.unknown_actual_event_count += group.unknown_actual_event_count;
    counts.not_applicable_count += group.not_applicable_count;
  }
  if (Object.values(counts).some((value) => !Number.isSafeInteger(value))) return unavailable();
  return { status: "available", ...period, counts, groups };
}

function financialLabel(row) {
  const labels = {
    financial_external_income: "外部収益",
    financial_realized_loss: "実現損失",
    financial_fee: "手数料",
    financial_user_transfer: "ユーザー送金",
    financial_self_funding: "自己資金",
    financial_deposit: "入金",
    financial_internal_move: "内部移動",
    financial_unverified: "未検証",
  };
  return labels[record(row) ? row.kind : ""] || "収支";
}

const REPORT_MONEY_FIELDS = Object.freeze([
  "gross_usd_micros",
  "realized_loss_usd_micros",
  "financial_fee_usd_micros",
  "api_cost_usd_micros",
  "operating_net_usd_micros",
  "balance_usdc_atomic",
  "distributable_usdc_atomic",
]);

function integerText(value, signed = false) {
  return (signed ? /^-?\d+$/ : /^\d+$/).test(String(value == null ? "" : value));
}

function projectReportReceipt(receipt, expectedKind) {
  if (!record(receipt)
    || receipt.status !== "sent"
    || receipt.report_kind !== expectedKind
    || !/^[0-9a-f]{64}$/.test(String(receipt.snapshot_hash || ""))
    || !Number.isInteger(Number(receipt.telegram_message_id))
    || Number(receipt.telegram_message_id) <= 0
    || !record(receipt.snapshot)
    || receipt.snapshot.kind !== expectedKind
    || receipt.snapshot.period_key !== receipt.period_key
    || (expectedKind === "daily" && !/^\d{4}-\d{2}-\d{2}$/.test(receipt.period_key))
    || (expectedKind === "weekly" && !/^\d{4}-W\d{2}$/.test(receipt.period_key))) {
    fail("ledger");
  }
  for (const field of REPORT_MONEY_FIELDS) {
    if (!integerText(receipt.snapshot[field], field === "operating_net_usd_micros")) fail("ledger");
  }
  if (receipt.snapshot.self_funded_bps !== null
    && (!Number.isInteger(receipt.snapshot.self_funded_bps) || receipt.snapshot.self_funded_bps < 0)) {
    fail("ledger");
  }
  if (!new Set(["running", "negative_net", "no_external_income", "reserve_floor"])
    .has(receipt.snapshot.stop_reason)) fail("ledger");
  const railPnl = Array.isArray(receipt.snapshot.rail_pnl) ? receipt.snapshot.rail_pnl : null;
  if (!railPnl) fail("ledger");
  const rails = railPnl.map((row) => {
    if (!record(row)
      || !new Set(["SELL", "WORK", "CAPITAL", "UNCLASSIFIED"]).has(row.rail)
      || !integerText(row.net_usd_micros, true)) fail("ledger");
    return { rail: row.rail, net_usd_micros: String(row.net_usd_micros) };
  });
  const projected = {
    period_key: receipt.period_key,
    snapshot_hash: receipt.snapshot_hash,
    telegram_message_id: Number(receipt.telegram_message_id),
  };
  for (const field of REPORT_MONEY_FIELDS) projected[field] = String(receipt.snapshot[field]);
  projected.self_funded_bps = receipt.snapshot.self_funded_bps;
  projected.stop_reason = receipt.snapshot.stop_reason;
  projected.rail_pnl = rails;
  return projected;
}

function projectLedger(candidate) {
  if (
    !record(candidate)
    || !Array.isArray(candidate.apiCostEntries)
    || !record(candidate.apiCostPeriods)
    || !Array.isArray(candidate.financialEntries)
    || !Array.isArray(candidate.reportReceipts)
  ) fail("ledger");
  const periods = {
    daily: projectApiCostPeriod(candidate.apiCostPeriods.daily),
    monthly: projectApiCostPeriod(candidate.apiCostPeriods.monthly),
  };
  const apiItems = candidate.apiCostEntries.map((row) => ledgerItem(row, "API利用料"));
  const financialItems = candidate.financialEntries.map((row) => ledgerItem(row, financialLabel(row)));
  let total = 0;
  let unknownEstimateEntries = 0;
  let unknownActualEntries = 0;
  for (const row of candidate.apiCostEntries) {
    const meta = record(row && row.meta) ? row.meta : {};
    const estimate = row && row.est_usd != null ? Number(row.est_usd) : NaN;
    const zeroHasExplicitStatus = meta.estimate_status === "estimated"
      || meta.estimate_status === "not_applicable";
    const estimateKnown = Number.isFinite(estimate) && estimate >= 0
      && meta.estimate_status !== "unavailable"
      && (estimate !== 0 || zeroHasExplicitStatus);
    if (estimateKnown) total += estimate;
    else unknownEstimateEntries += 1;

    const actual = meta.actual_usd == null ? NaN : Number(meta.actual_usd);
    const actualKnown = meta.billing_status === "settled" && Number.isFinite(actual) && actual >= 0;
    const notApplicable = meta.billing_status === "not_applicable" && actual === 0;
    if (!actualKnown && !notApplicable) unknownActualEntries += 1;
  }
  const estimateStatus = apiItems.length === 0 ? "unknown"
    : (unknownEstimateEntries > 0 ? "partial" : "estimated");
  const actualStatus = apiItems.length === 0 || unknownActualEntries === apiItems.length ? "unknown"
    : (unknownActualEntries > 0 ? "partial" : "complete");
  const totalText = apiItems.length === 0 ? "金額不明"
    : `${formatCurrencyAmount(total, "USD")}${unknownEstimateEntries > 0
      ? `（既知推定小計・金額不明${unknownEstimateEntries}件）` : "（推定）"}`;
  const latest = { daily: null, weekly: null };
  for (const receipt of candidate.reportReceipts) {
    const kind = record(receipt) ? receipt.report_kind : "";
    if ((kind === "daily" || kind === "weekly") && latest[kind] === null) {
      latest[kind] = projectReportReceipt(receipt, kind);
    }
  }
  return {
    api_cost: {
      no_data: apiItems.length === 0,
      total: totalText,
      estimate_status: estimateStatus,
      unknown_estimate_entries: unknownEstimateEntries,
      actual_status: actualStatus,
      unknown_actual_entries: unknownActualEntries,
      items: apiItems,
      periods,
    },
    financial: {
      no_data: financialItems.length === 0,
      items: financialItems,
    },
    reports: latest,
  };
}

function validateScores(candidate) {
  if (!exactKeys(candidate, ["organs"]) || !exactKeys(candidate.organs, SCORE_NAMES)) fail("scores");
  if (containsSensitiveDisplayValue(candidate)) fail("scores");
  for (const organ of SCORE_NAMES) {
    if (!validScoreOrgan(organ, candidate.organs[organ])) fail("scores");
  }
  return candidate;
}

function validateGates(candidate) {
  if (!exactKeys(candidate, ["gates"]) || !Array.isArray(candidate.gates) || candidate.gates.length !== 2) fail("gates");
  const expectedIds = ["location", "payout"];
  for (let index = 0; index < candidate.gates.length; index += 1) {
    const gate = candidate.gates[index];
    if (
      !exactKeys(gate, ["id", "unlocked", "unlock_method"])
      || gate.id !== expectedIds[index]
      || typeof gate.unlocked !== "boolean"
      || !validDisplayText(gate.unlock_method)
    ) fail("gates");
  }
  return candidate;
}

function validCallLanguage(value) {
  return value === null || value === "ja" || value === "en";
}

function validSettings(candidate) {
  return exactKeys(candidate, ["call_language", "call_schedule", "connections"])
    && validCallLanguage(candidate.call_language)
    && exactKeys(candidate.call_schedule, ["time_zone", "minutes_before", "wake_policy"])
    && validTimeZone(candidate.call_schedule.time_zone)
    && Array.isArray(candidate.call_schedule.minutes_before)
    && candidate.call_schedule.minutes_before.length === 2
    && candidate.call_schedule.minutes_before[0] === 10
    && candidate.call_schedule.minutes_before[1] === 5
    && new Set(["travel-only", "all-events"]).has(candidate.call_schedule.wake_policy)
    && exactKeys(candidate.connections, ["calendar", "gmail", "telegram"])
    && Object.values(candidate.connections).every((value) => typeof value === "boolean")
    && !containsSensitiveDisplayValue(candidate);
}

function validateSettings(candidate) {
  if (!validSettings(candidate)) fail("settings");
  return candidate;
}

function validConnection(value) {
  if (!record(value)) return false;
  const allowedKeys = new Set(["state", "reason", "actions", "actionLabel"]);
  if (Object.keys(value).some((key) => !allowedKeys.has(key))) return false;
  if (typeof value.state !== "string" || !CONNECTION_STATES.has(value.state)) return false;
  if (!validDisplayText(value.reason)) return false;
  if (
    Object.hasOwn(value, "actions")
    && (!Array.isArray(value.actions) || value.actions.some((action) => !validDisplayText(action)))
  ) return false;
  if (Object.hasOwn(value, "actionLabel") && !validDisplayText(value.actionLabel)) return false;
  return true;
}

function validControlSettings(value) {
  return exactKeys(value, ["call_enabled", "notifications_enabled", "daily_automation_enabled", "call_time_zone", "call_language", "wake_policy"])
    && typeof value.call_enabled === "boolean"
    && typeof value.notifications_enabled === "boolean"
    && typeof value.daily_automation_enabled === "boolean"
    && validTimeZone(value.call_time_zone)
    && validCallLanguage(value.call_language)
    && new Set(["travel-only", "all-events"]).has(value.wake_policy);
}

function validControls(value) {
  if (!exactKeys(value, CONTROL_NAMES)) return false;
  if (!exactKeys(value.delegation, ["state", "reason"]) || value.delegation.state !== "unavailable" || !validDisplayText(value.delegation.reason)) return false;
  return CONTROL_NAMES.slice(1).every((name) => exactKeys(value[name], ["state"]) && value[name].state === "unavailable");
}

function validateControlCenter(candidate) {
  if (!exactKeys(candidate, ["identity", "context", "connections", "settings", "controls", "csrf"])) fail("control-center");
  if (
    !exactKeys(candidate.identity, ["name", "uidRef"])
    || candidate.identity.name !== "Life Manager user"
    || !/^user:[0-9a-f]{12}$/.test(candidate.identity.uidRef)
    || !exactKeys(candidate.context, ["timeZone", "locationAvailable"])
    || !validTimeZone(candidate.context.timeZone)
    || typeof candidate.context.locationAvailable !== "boolean"
    || !exactKeys(candidate.connections, CONNECTION_NAMES)
    || CONNECTION_NAMES.some((name) => !validConnection(candidate.connections[name]))
    || !validControlSettings(candidate.settings)
    || !validControls(candidate.controls)
    || !validDisplayText(candidate.csrf)
    || containsSensitiveDisplayValue(candidate)
  ) fail("control-center");
  return candidate;
}

function presentPanelSection(section, candidate) {
  if (section === "timeline") return projectTimeline(candidate);
  if (section === "ledger") return projectLedger(candidate);
  if (section === "scores") return validateScores(candidate);
  if (section === "gates") return validateGates(candidate);
  if (section === "settings") return validateSettings(candidate);
  if (section === "control-center") return validateControlCenter(candidate);
  fail(section);
}

module.exports = {
  PanelSectionUnavailableError,
  SAFE_TIMELINE_SENTENCE,
  presentPanelSection,
};
