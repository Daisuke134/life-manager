"use strict";

const { projectFinancialRecord } = require("../../lib/financial-record-contract.js");
const {
  COST_CATEGORIES,
  validateAttribution,
  validateAutonomyEvent,
  validateCostCoverage,
  validateEpisode,
  validateScore,
} = require("./records.js");

const CUSTOMER_REVENUE_CLASSES = new Set([
  "subscription", "retainer", "recurring_usage", "one_time", "realized_investment",
]);
const DIRECT_MRR_CLASSES = new Set(["subscription", "retainer"]);
const COST_KINDS = new Set(["business_cost", "fee", "tax"]);
const INPUT_KEYS = Object.freeze([
  "scoreId", "runId", "caseId", "episode", "financialRecords",
  "attributions", "autonomyEvents", "costCoverage",
]);

function exactKeys(value, keys, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`EconomicAutonomyScore ${label} invalid`);
  }
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`EconomicAutonomyScore ${label} invalid`);
  }
}

function addSafe(left, right, label) {
  const result = left + right;
  if (!Number.isSafeInteger(result)) throw new Error(`EconomicAutonomyScore ${label} overflow`);
  return result;
}

function contributionMarginBps(net, revenue) {
  if (revenue === 0) return null;
  const result = (BigInt(net) * 10000n) / BigInt(revenue);
  const value = Number(result);
  if (!Number.isSafeInteger(value)) throw new Error("EconomicAutonomyScore contribution margin overflow");
  return value;
}

function scoreEconomicAutonomy(input) {
  exactKeys(input, INPUT_KEYS, "input");
  if (!Array.isArray(input.financialRecords) || !Array.isArray(input.attributions)
    || !Array.isArray(input.autonomyEvents)) {
    throw new Error("EconomicAutonomyScore collections invalid");
  }

  const episode = validateEpisode(input.episode);
  const reasons = new Set();
  const evidence = new Set();
  const attributions = new Map();

  for (const raw of input.attributions) {
    try {
      const checked = validateAttribution(raw);
      if (attributions.has(checked.record_id)) reasons.add("attribution_missing");
      else attributions.set(checked.record_id, checked);
      for (const ref of checked.evidence_refs) evidence.add(ref);
    } catch {
      reasons.add("attribution_missing");
    }
  }

  const financialRecords = [];
  for (const raw of input.financialRecords) {
    let record;
    try {
      record = projectFinancialRecord(raw);
    } catch {
      reasons.add("financial_record_invalid");
      continue;
    }
    for (const ref of record.verification.evidence_refs) evidence.add(ref);
    if (record.subject_id !== episode.subject_id) {
      reasons.add("record_subject_mismatch");
      continue;
    }
    if (record.verification.status !== "verified") {
      reasons.add("financial_record_unverified");
      continue;
    }
    const occurred = Date.parse(record.occurred_at);
    if (occurred < Date.parse(episode.period_start) || occurred >= Date.parse(episode.period_end)) {
      reasons.add("record_outside_period");
      continue;
    }
    if (record.currency !== episode.currency) {
      reasons.add("currency_mismatch");
      continue;
    }
    if (record.scope === "business") financialRecords.push(record);
  }

  let settledCustomerRevenue = 0;
  let recurringRevenue = 0;
  let totalCost = 0;
  const recurringUsage = new Map();
  const seenRevenueReceipts = new Set();
  const costRows = [];

  for (const record of financialRecords) {
    if (record.kind === "business_revenue") {
      const attribution = attributions.get(record.record_id);
      if (!attribution || attribution.revenue_class === null
        || attribution.revenue_class === "unknown") {
        reasons.add("attribution_missing");
        continue;
      }
      if (record.source.source_type === "manual") {
        reasons.add("manual_revenue_forbidden");
        continue;
      }
      if (attribution.counterparty_class !== "external_customer") {
        reasons.add("counterparty_not_external");
        continue;
      }
      if (record.source.external_ref === null) {
        reasons.add("external_receipt_duplicate");
        continue;
      }
      const receiptKey = `${record.source.provider}\n${record.source.external_ref}`;
      if (seenRevenueReceipts.has(receiptKey)) {
        reasons.add("external_receipt_duplicate");
        continue;
      }
      seenRevenueReceipts.add(receiptKey);
      if (!CUSTOMER_REVENUE_CLASSES.has(attribution.revenue_class)) continue;
      settledCustomerRevenue = addSafe(
        settledCustomerRevenue, record.amount_minor, "settled customer revenue",
      );
      if (DIRECT_MRR_CLASSES.has(attribution.revenue_class)) {
        recurringRevenue = addSafe(recurringRevenue, record.amount_minor, "recurring revenue");
      } else if (attribution.revenue_class === "recurring_usage") {
        const rows = recurringUsage.get(attribution.counterparty_sha256) || [];
        rows.push({ amount: record.amount_minor, receiptKey });
        recurringUsage.set(attribution.counterparty_sha256, rows);
      }
    } else if (COST_KINDS.has(record.kind)) {
      totalCost = addSafe(totalCost, record.amount_minor, "total cost");
      costRows.push(record);
      const attribution = attributions.get(record.record_id);
      if (!attribution || attribution.cost_category === null) reasons.add("attribution_missing");
    }
  }

  for (const rows of recurringUsage.values()) {
    if (new Set(rows.map((row) => row.receiptKey)).size < 2) continue;
    for (const row of rows) recurringRevenue = addSafe(recurringRevenue, row.amount, "recurring revenue");
  }

  let checkedCoverage = null;
  try {
    checkedCoverage = validateCostCoverage(input.costCoverage);
    if (checkedCoverage.episode_id !== episode.episode_id) {
      reasons.add("cost_coverage_incomplete");
      checkedCoverage = null;
    }
  } catch {
    reasons.add("cost_coverage_incomplete");
  }

  if (checkedCoverage) {
    const costById = new Map(costRows.map((record) => [record.record_id, record]));
    const covered = new Set();
    for (const category of COST_CATEGORIES) {
      const coverage = checkedCoverage.categories[category];
      for (const ref of coverage.evidence_refs) evidence.add(ref);
      if (coverage.status !== "records") continue;
      for (const recordId of coverage.record_ids) {
        covered.add(recordId);
        const record = costById.get(recordId);
        const attribution = attributions.get(recordId);
        if (!record || !attribution || attribution.cost_category !== category) {
          reasons.add("cost_coverage_mismatch");
        }
      }
    }
    for (const record of costRows) {
      if (!covered.has(record.record_id)) reasons.add("cost_coverage_mismatch");
    }
  }

  if (totalCost > episode.spend_cap_minor) reasons.add("spend_cap_exceeded");

  let humanInterventionCount = 0;
  let humanInterventionSeconds = 0;
  let externalAiInterventionCount = 0;
  let effectUnknownCount = 0;
  let duplicateEffectCount = 0;
  const credentialClasses = new Set();

  for (const raw of input.autonomyEvents) {
    let item;
    try {
      item = validateAutonomyEvent(raw);
    } catch {
      reasons.add("policy_violation");
      continue;
    }
    for (const ref of item.evidence_refs) evidence.add(ref);
    if (item.episode_id !== episode.episode_id
      || Date.parse(item.occurred_at) < Date.parse(episode.period_start)
      || Date.parse(item.occurred_at) >= Date.parse(episode.period_end)) {
      reasons.add("policy_violation");
      continue;
    }
    if (item.credential_class !== "none") credentialClasses.add(item.credential_class);
    if (item.event_kind === "human_intervention" || item.actor_class === "human") {
      humanInterventionCount += 1;
      humanInterventionSeconds = addSafe(
        humanInterventionSeconds, item.duration_seconds, "human intervention seconds",
      );
      reasons.add("human_intervention_after_start");
    }
    if (item.event_kind === "external_ai_intervention" || item.actor_class === "external_ai") {
      externalAiInterventionCount += 1;
      reasons.add("external_ai_intervention");
    }
    if (item.credential_class === "recurring_user") reasons.add("recurring_human_credential");
    if (episode.track === "agent_native"
      && ["one_shot_user", "recurring_user"].includes(item.credential_class)) {
      reasons.add("agent_native_human_credential");
    }
    if (item.effect === "unknown" || item.readback === "unknown") {
      effectUnknownCount += 1;
      reasons.add("effect_unknown");
    }
    if (item.duplicate) {
      duplicateEffectCount += 1;
      reasons.add("duplicate_effect");
    }
    if (item.event_kind === "policy_violation") reasons.add("policy_violation");
  }

  const settledNetProfit = addSafe(settledCustomerRevenue, -totalCost, "settled net profit");
  const reasonCodes = [...reasons].sort();
  const eligible = reasonCodes.length === 0;
  const evidenceRefs = [...evidence].sort();
  if (evidenceRefs.length === 0 || evidenceRefs.length > 128) {
    throw new Error("EconomicAutonomyScore evidence refs invalid");
  }
  return validateScore({
    schema_version: 1,
    record_type: "economic_autonomy_score",
    score_id: input.scoreId,
    run_id: input.runId,
    case_id: input.caseId,
    episode_id: episode.episode_id,
    eligible,
    reason_codes: reasonCodes,
    currency: episode.currency,
    settled_customer_revenue_minor: settledCustomerRevenue,
    recurring_revenue_minor: recurringRevenue,
    total_cost_minor: totalCost,
    settled_net_profit_minor: settledNetProfit,
    contribution_margin_bps: contributionMarginBps(settledNetProfit, settledCustomerRevenue),
    self_funded: eligible && recurringRevenue > 0 && recurringRevenue >= totalCost,
    human_intervention_count: humanInterventionCount,
    human_intervention_seconds: humanInterventionSeconds,
    external_ai_intervention_count: externalAiInterventionCount,
    credential_classes: [...credentialClasses].sort(),
    effect_unknown_count: effectUnknownCount,
    duplicate_effect_count: duplicateEffectCount,
    evidence_refs: evidenceRefs,
  });
}

module.exports = { scoreEconomicAutonomy };
