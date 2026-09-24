"use strict";

const crypto = require("node:crypto");
const {
  joinEconomicFunnelObservation,
  validateEconomicSourceObservation,
} = require("./economic-source-contract.js");
const { projectFinancialRecord } = require("./financial-record-contract.js");

const READ_STATES = new Set(["observed", "not_configured", "unavailable"]);
const POSITIVE_TERMINALS = new Set(["settled", "paid", "received", "completed"]);
const COST_PREFIXES = ["x402-cost:v1:", "agent-economy-cost:v1:taskmarket:"];

function digest(value) {
  return crypto.createHash("sha256").update(String(value)).digest("hex");
}

function instant(value, label) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) {
    throw new Error(`Agent Economy ${label} invalid`);
  }
  return new Date(value).toISOString();
}

function readState(value, label) {
  if (!READ_STATES.has(value)) throw new Error(`Agent Economy ${label} read state invalid`);
  return value;
}

function proofIdentity(receipt) {
  if (receipt.proof.provider_receipt_id) {
    return `${receipt.provider}\n${receipt.proof.provider_receipt_id}`;
  }
  return `${receipt.proof.chain_id}\n${receipt.proof.tx_hash}\n${receipt.proof.log_index}`;
}

function providerReceiptId(value) {
  return `agent-economy-${digest(value)}`;
}

function evidenceRef(sourceKind, material) {
  return `economic-source://agent-economy/${sourceKind}/${digest(material)}`;
}

function observationId(sourceKind, state, observedAt, receiptIds) {
  return `ae-source-${sourceKind}-${digest(JSON.stringify({ state, observedAt, receiptIds }))}`;
}

function sourceObservation({ sourceKind, adapter, state, subjectId, observedAt, receiptIds }) {
  const evidence = evidenceRef(sourceKind, JSON.stringify({ state, observedAt, receiptIds }));
  return validateEconomicSourceObservation({
    schema_version: 1,
    record_type: "economic_source_observation",
    observation_id: observationId(sourceKind, state, observedAt, receiptIds),
    product_loop_id: "agent-economy",
    subject_id: subjectId,
    source_kind: sourceKind,
    adapter,
    implementation: "implemented",
    state,
    observed_at: observedAt,
    provider_receipt_ids: receiptIds,
    evidence_refs: [evidence],
  });
}

function stateWithoutRows(read, hasOfficialReceipts) {
  if (read !== "observed") return read;
  return hasOfficialReceipts ? "empty" : "unavailable";
}

async function buildAgentEconomyEconomicSourceBundle(input = {}) {
  const subjectId = String(input.subjectId || "").trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u.test(subjectId)) {
    throw new Error("Agent Economy subject invalid");
  }
  const observedAt = instant(input.observedAt, "observed_at");
  const revenueReadState = readState(input.revenueReadState, "revenue");
  const costReadState = readState(input.costReadState, "cost");
  const receipts = Array.isArray(input.receipts) ? input.receipts : [];
  const revenueRecords = Array.isArray(input.revenueRecords) ? input.revenueRecords : [];
  const rawCostRecords = Array.isArray(input.costRecords) ? input.costRecords : [];
  if (revenueReadState !== "observed" && (receipts.length || revenueRecords.length)) {
    throw new Error("Agent Economy revenue read state contradicts records");
  }
  if (costReadState !== "observed" && rawCostRecords.length) {
    throw new Error("Agent Economy cost read state contradicts records");
  }

  const revenueModule = await import("../../../skills/agent-economy/lib/revenue-receipt.mjs");
  if (receipts.some((receipt) => !revenueModule.isNormalizedRevenueReceipt(receipt))) {
    throw new Error("normalized verified revenue receipt required");
  }
  const revenueReceiptIds = [...new Set(receipts.map((receipt) => (
    providerReceiptId(proofIdentity(receipt))
  )))].sort();
  if (revenueReceiptIds.length > 10_000) throw new Error("Agent Economy receipt limit exceeded");

  const checkedRevenueRecords = revenueRecords.map(projectFinancialRecord);
  if (checkedRevenueRecords.some((record) => (
    record.subject_id !== subjectId || record.verification.status !== "verified"
  ))) throw new Error("Agent Economy revenue FinancialRecord invalid");

  const checkedCostRecords = rawCostRecords.map(projectFinancialRecord)
    .filter((record) => COST_PREFIXES.some((prefix) => record.idempotency_key.startsWith(prefix)));
  if (checkedCostRecords.some((record) => (
    record.subject_id !== subjectId
    || record.verification.status !== "verified"
    || record.kind !== "business_cost"
    || record.direction !== "debit"
  ))) throw new Error("Agent Economy cost FinancialRecord invalid");
  const costReceiptIds = [...new Set(checkedCostRecords.map((record) => (
    providerReceiptId(`${record.source.provider}\n${record.source.external_ref}\n${record.idempotency_key}`)
  )))].sort();
  if (costReceiptIds.length > 10_000) throw new Error("Agent Economy cost receipt limit exceeded");

  const funnelState = revenueReadState === "observed" && receipts.length
    ? "observed_verified" : stateWithoutRows(revenueReadState, false);
  const financialState = revenueReadState === "observed" && checkedRevenueRecords.length
    ? "observed_verified" : stateWithoutRows(revenueReadState, receipts.length > 0);
  const costState = costReadState === "observed" && checkedCostRecords.length
    ? "observed_verified" : stateWithoutRows(costReadState, false);

  const funnelSource = sourceObservation({
    sourceKind: "funnel", adapter: "agent-economy-revenue-receipt", state: funnelState,
    subjectId, observedAt, receiptIds: funnelState === "observed_verified" ? revenueReceiptIds : [],
  });
  const financialSource = sourceObservation({
    sourceKind: "financial", adapter: "agent-economy-financial-record", state: financialState,
    subjectId, observedAt,
    receiptIds: ["observed_verified", "empty"].includes(financialState) ? revenueReceiptIds : [],
  });
  const costSource = sourceObservation({
    sourceKind: "cost", adapter: "x402-cost-observer", state: costState,
    subjectId, observedAt, receiptIds: costState === "observed_verified" ? costReceiptIds : [],
  });

  const paymentCount = receipts.filter((receipt) => POSITIVE_TERMINALS.has(receipt.terminal_state)).length;
  const funnelStateForCount = funnelState === "observed_verified"
    ? (paymentCount > 0 ? "observed_verified" : "empty") : funnelState;
  const funnelReceiptIds = funnelState === "observed_verified" ? revenueReceiptIds : [];
  const funnel = {
    schema_version: 1,
    record_type: "economic_funnel_observation",
    funnel_observation_id: `ae-funnel-payment-${digest(JSON.stringify({
      source: funnelSource.observation_id, state: funnelStateForCount, count: paymentCount,
    }))}`,
    source_observation_id: funnelSource.observation_id,
    product_loop_id: "agent-economy",
    subject_id: subjectId,
    stage: "payment",
    cohort_sha256: digest(`${subjectId}\nagent-economy\npayment`),
    state: funnelStateForCount,
    count: ["observed_verified", "empty"].includes(funnelStateForCount) ? paymentCount : null,
    observed_at: observedAt,
    provider_receipt_ids: funnelReceiptIds,
    evidence_refs: funnelSource.evidence_refs,
  };
  const joinedFunnel = joinEconomicFunnelObservation(funnelSource, funnel).funnel;

  return Object.freeze({
    sourceObservations: Object.freeze([funnelSource, financialSource, costSource]),
    funnelObservations: Object.freeze([joinedFunnel]),
  });
}

module.exports = { buildAgentEconomyEconomicSourceBundle };
