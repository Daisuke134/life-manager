"use strict";

const { sha256Canonical, classifyLabel } = require("./cfo-registry.js");

const URI_SCHEME = /^[a-z][a-z0-9+.-]*:/i;
const LEDGER_STATUSES = new Set(["available", "present_empty", "stale_alias", "planned", "unavailable"]);

function compareText(left, right) {
  const leftText = String(left);
  const rightText = String(right);
  const length = Math.min(leftText.length, rightText.length);
  for (let index = 0; index < length; index += 1) {
    const difference = leftText.charCodeAt(index) - rightText.charCodeAt(index);
    if (difference !== 0) return difference;
  }
  return leftText.length - rightText.length;
}

function evidenceRefs(registry) {
  return [...new Set([
    ...registry.financial_units.flatMap((unit) => unit.evidence_refs),
    ...registry.runtime_exclusions.flatMap((exclusion) => exclusion.evidence_refs),
  ])].sort(compareText);
}

function normalizeLaunchctlList(stdout) {
  return String(stdout).split(/\r?\n/).slice(1).map((line) => line.trim().split(/\s+/)).filter((parts) => parts.length >= 3)
    .map(([pid, status, label]) => ({
      label,
      state: /^\d+$/.test(pid) ? "running" : pid === "-" ? "not_running" : "unknown",
      last_exit_code: /^-?\d+$/.test(status) ? Number(status) : null,
    })).filter((item) => /^ai\.anicca\./.test(item.label)).sort((a, b) => compareText(a.label, b.label));
}

function collectSourceObservations(registry, exists) {
  return evidenceRefs(registry).map((evidence_ref) => ({
    evidence_ref,
    availability: URI_SCHEME.test(evidence_ref)
      ? "not_applicable"
      : exists(evidence_ref) ? "present" : "unavailable",
  }));
}

function collectLedgerObservations(registry, probe) {
  return registry.ledger_sources.map((source) => {
    const candidate = typeof probe === "function" ? probe(source) : null;
    const item = {
      ledger_source_id: source.ledger_source_id,
      availability: candidate && LEDGER_STATUSES.has(candidate.availability)
        ? candidate.availability : source.default_status,
    };
    if (candidate && Number.isInteger(candidate.evidence_count) && candidate.evidence_count >= 0) {
      item.evidence_count = candidate.evidence_count;
    }
    return item;
  }).sort((left, right) => compareText(left.ledger_source_id, right.ledger_source_id));
}

function normalizeLedgerObservations(registry, observations) {
  const byId = new Map();
  for (const observation of Array.isArray(observations) ? observations : []) {
    if (observation && typeof observation.ledger_source_id === "string" && !byId.has(observation.ledger_source_id)) {
      byId.set(observation.ledger_source_id, observation);
    }
  }
  return registry.ledger_sources.map((source) => {
    const candidate = byId.get(source.ledger_source_id);
    const item = {
      ledger_source_id: source.ledger_source_id,
      availability: candidate && LEDGER_STATUSES.has(candidate.availability)
        ? candidate.availability : source.default_status,
    };
    if (candidate && Number.isInteger(candidate.evidence_count) && candidate.evidence_count >= 0) {
      item.evidence_count = candidate.evidence_count;
    }
    return item;
  }).sort((left, right) => compareText(left.ledger_source_id, right.ledger_source_id));
}

function buildInventory({ registry, runtimeObservations = [], sourceObservations = [], ledgerObservations, generatedAt, inventoryId }) {
  const relevant = (label) => typeof label === "string"
    && registry.relevant_runtime_prefixes.some((prefix) => label.startsWith(prefix));
  const runtime_observations = runtimeObservations.filter((item) => relevant(item.label)).map((item) => {
    const classification = classifyLabel(registry, item.label);
    return {
      label: item.label,
      state: item.state,
      last_exit_code: item.last_exit_code,
      classification: classification.kind,
      target_ids: [...classification.targetIds].sort(compareText),
    };
  }).sort((left, right) => compareText(left.label, right.label));
  const knownRefs = new Set(evidenceRefs(registry));
  const source_observations = sourceObservations.filter((item) => knownRefs.has(item.evidence_ref)).map(({ evidence_ref, availability }) => ({
    evidence_ref,
    availability,
  })).sort((left, right) => compareText(left.evidence_ref, right.evidence_ref)
    || compareText(left.availability, right.availability)).filter((item, index, all) => (
    index === 0 || item.evidence_ref !== all[index - 1].evidence_ref
  ));
  const labelsByUnit = new Map(registry.financial_units.map((unit) => [unit.financial_unit_id, new Set()]));
  runtime_observations.filter((item) => item.classification === "financial_unit").forEach((item) => {
    item.target_ids.forEach((targetId) => labelsByUnit.get(targetId)?.add(item.label));
  });
  const presentRefs = new Set(source_observations.filter((item) => item.availability === "present").map((item) => item.evidence_ref));
  const financial_units = registry.financial_units.map((unit) => {
    const runtime_labels = [...labelsByUnit.get(unit.financial_unit_id)].sort(compareText);
    const source_evidence_refs = unit.evidence_refs.filter((ref) => presentRefs.has(ref)).sort(compareText);
    return {
      financial_unit_id: unit.financial_unit_id,
      unit_kind: unit.unit_kind,
      display_order: unit.display_order,
      display_name: unit.display_name,
      lifecycle: unit.lifecycle,
      runtime_labels,
      source_evidence_refs,
      evidence_status: runtime_labels.length || source_evidence_refs.length ? "observed" : "unverified",
    };
  }).sort((left, right) => left.display_order - right.display_order || compareText(left.financial_unit_id, right.financial_unit_id));
  const unmapped_relevant_labels = [...new Set(runtime_observations.filter((item) => item.classification === "unmapped").map((item) => item.label))].sort(compareText);
  const ambiguous_labels = [...new Map(runtime_observations.filter((item) => item.classification === "ambiguous").map((item) => [item.label, {
    label: item.label,
    target_ids: [...item.target_ids].sort(compareText),
  }])).values()].sort((left, right) => compareText(left.label, right.label));
  const result = unmapped_relevant_labels.length || ambiguous_labels.length ? "fail" : "pass";
  const registry_sha256 = sha256Canonical(registry);
  const ledger_observations = ledgerObservations === undefined
    ? collectLedgerObservations(registry)
    : normalizeLedgerObservations(registry, ledgerObservations);
  const core = { receipt_version: 1, registry_sha256, financial_units, runtime_observations, source_observations, ledger_observations, unmapped_relevant_labels, ambiguous_labels, result };
  const { receipt_version, ...deterministic } = core;
  return {
    receipt_version,
    inventory_id: inventoryId,
    generated_at: generatedAt,
    ...deterministic,
    observation_hash: observationHash(core),
  };
}

function observationHash(receiptCore) {
  return sha256Canonical(receiptCore);
}

module.exports = {
  normalizeLaunchctlList,
  collectSourceObservations,
  collectLedgerObservations,
  buildInventory,
  observationHash,
};
