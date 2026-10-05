// REQ-303: append-only JSONL shelter-cost ledger. ledger.js's readChildren/appendChild are already
// generic over (file, row) despite their children-specific name — reused here unmodified rather than
// re-implementing the identical read/append logic a second time. One entry per real deploy attempt,
// {ts, settledLeaseCostUsd}, appended once the settled lease cost first becomes observable.
const { readChildren, appendChild } = require("./ledger.js");

function readShelterCostEntries(file) {
  return readChildren(file);
}

function readShelterCostEntriesResolved(file) {
  const rows = readShelterCostEntries(file);
  const normalRows = [];
  const correctionRows = [];
  const normalRowsByTs = new Map();

  rows.forEach((row, index) => {
    const isRecord = row && typeof row === "object" && !Array.isArray(row);
    if (isRecord && Object.prototype.hasOwnProperty.call(row, "correction")) {
      correctionRows.push({ row, index });
      return;
    }

    if (
      !isRecord ||
      !Number.isFinite(row.ts) ||
      !Number.isFinite(row.settledLeaseCostUsd) ||
      row.settledLeaseCostUsd < 0
    ) {
      throw new Error(`readShelterCostEntriesResolved: malformed normal row at index ${index}`);
    }

    normalRows.push({ row, index });
    const matches = normalRowsByTs.get(row.ts) || [];
    matches.push(index);
    normalRowsByTs.set(row.ts, matches);
  });

  const correctedJobAddressByIndex = new Map();
  for (const { row, index } of correctionRows) {
    if (
      row.correction !== true ||
      !Number.isFinite(row.ts) ||
      typeof row.correctedField !== "string" ||
      row.correctedField.length === 0 ||
      !Number.isFinite(row.correctsTs) ||
      typeof row.correctedJobAddress !== "string" ||
      row.correctedJobAddress.length === 0 ||
      typeof row.reason !== "string" ||
      row.reason.length === 0
    ) {
      throw new Error(`readShelterCostEntriesResolved: malformed correction row at index ${index}`);
    }
    if (row.correctedField !== "jobAddress") {
      throw new Error(`readShelterCostEntriesResolved: unsupported correction field "${row.correctedField}"`);
    }

    const matches = normalRowsByTs.get(row.correctsTs) || [];
    if (matches.length > 1) {
      throw new Error(`readShelterCostEntriesResolved: ambiguous target timestamp ${row.correctsTs}`);
    }
    if (matches.length === 0 || matches[0] >= index) {
      throw new Error(`readShelterCostEntriesResolved: orphan correction for timestamp ${row.correctsTs} (no unique preceding normal row)`);
    }
    correctedJobAddressByIndex.set(matches[0], row.correctedJobAddress);
  }

  const spendIdentities = new Map();
  const resolvedRows = normalRows.map(({ row, index }) => {
    const resolved = correctedJobAddressByIndex.has(index)
      ? { ...row, jobAddress: correctedJobAddressByIndex.get(index) }
      : row;
    const identity = resolved.jobAddress || `no-address-${resolved.ts}`;
    const group = spendIdentities.get(identity) || { indices: [], corrected: false };
    group.indices.push(index);
    group.corrected ||= correctedJobAddressByIndex.has(index);
    spendIdentities.set(identity, group);
    return resolved;
  });

  for (const { indices, corrected } of spendIdentities.values()) {
    if (corrected && indices.length > 1) {
      throw new Error(`readShelterCostEntriesResolved: corrected spend identity collision between normal rows ${indices.join(",")}`);
    }
  }

  return resolvedRows;
}

function appendShelterCostEntry(file, row) {
  return appendChild(file, row);
}

module.exports = { readShelterCostEntries, readShelterCostEntriesResolved, appendShelterCostEntry };
