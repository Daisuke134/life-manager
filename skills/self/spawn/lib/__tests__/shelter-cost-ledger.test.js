// VCSDD anicca-agent-spawn, Phase 2a (RED). REQ-303 shelter-cost-ledger.js — append-only JSONL,
// exactly {readShelterCostEntries, appendShelterCostEntry}, mirrors ledger.js's own no-update/upsert
// discipline. shelter-cost-ledger.js does not exist yet — expected to fail at require() time.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const os = require("node:os");
const fs = require("node:fs");
const path = require("node:path");
const {
  readShelterCostEntries,
  readShelterCostEntriesResolved,
  appendShelterCostEntry,
} = require("../shelter-cost-ledger");

function tmpFile() {
  return path.join(fs.mkdtempSync(path.join(os.tmpdir(), "anicca-shelter-cost-ledger-")), "shelter-cost.jsonl");
}

test("readShelterCostEntries returns [] when the file does not exist", () => {
  const f = path.join(os.tmpdir(), "definitely-missing-" + Date.now(), "shelter-cost.jsonl");
  assert.deepEqual(readShelterCostEntries(f), []);
  assert.deepEqual(readShelterCostEntriesResolved(f), []);
});

test("appendShelterCostEntry then readShelterCostEntries round-trips one row per real deploy attempt", () => {
  const f = tmpFile();
  const row = { ts: 1720000000000, settledLeaseCostUsd: 3.5 };
  appendShelterCostEntry(f, row);
  const rows = readShelterCostEntries(f);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0], row);
});

test("appendShelterCostEntry is append-only (preserves prior rows, never mutates them)", () => {
  const f = tmpFile();
  appendShelterCostEntry(f, { ts: 1, settledLeaseCostUsd: 3.5 });
  appendShelterCostEntry(f, { ts: 2, settledLeaseCostUsd: 4.25 });
  const rows = readShelterCostEntries(f);
  assert.deepEqual(
    rows.map((r) => r.settledLeaseCostUsd),
    [3.5, 4.25]
  );
});

test("resolved reader applies a jobAddress correction without changing source rows or bytes", () => {
  const f = tmpFile();
  const first = { ts: 1720000000.125, jobAddress: "wrong-address", settledLeaseCostUsd: 3.5, keep: "metadata" };
  const correction = {
    correction: true,
    correctedField: "jobAddress",
    correctsTs: first.ts,
    correctedJobAddress: "correct-address",
    ts: 1720000001.25,
    reason: "provider readback corrected the address",
  };
  const second = { ts: 1720000002.5, settledLeaseCostUsd: 4.25 };
  for (const row of [first, correction, second]) appendShelterCostEntry(f, row);
  const sourceBytes = fs.readFileSync(f);

  const resolved = readShelterCostEntriesResolved(f);
  assert.deepEqual(resolved, [
    { ...first, jobAddress: "correct-address" },
    second,
  ]);
  assert.deepEqual(resolved.map((row) => row.settledLeaseCostUsd), [3.5, 4.25]);
  assert.deepEqual(readShelterCostEntries(f), [first, correction, second]);
  assert.deepEqual(fs.readFileSync(f), sourceBytes);
});

test("resolved reader rejects corrections without a unique preceding normal row", () => {
  const correction = {
    correction: true,
    correctedField: "jobAddress",
    correctsTs: 1720000000.125,
    correctedJobAddress: "correct-address",
    ts: 1720000001.25,
    reason: "correction fixture",
  };

  const orphan = tmpFile();
  appendShelterCostEntry(orphan, correction);
  assert.throws(() => readShelterCostEntriesResolved(orphan), /orphan|no preceding/i);

  const futureTarget = tmpFile();
  appendShelterCostEntry(futureTarget, correction);
  appendShelterCostEntry(futureTarget, { ts: correction.correctsTs, jobAddress: "later", settledLeaseCostUsd: 1 });
  assert.throws(() => readShelterCostEntriesResolved(futureTarget), /orphan|no preceding/i);
});

test("resolved reader rejects ambiguous same-ts targets both before and after a correction", () => {
  const first = { ts: 1720000000.125, jobAddress: "first", settledLeaseCostUsd: 1 };
  const second = { ts: first.ts, jobAddress: "second", settledLeaseCostUsd: 2 };
  const correction = {
    correction: true,
    correctedField: "jobAddress",
    correctsTs: first.ts,
    correctedJobAddress: "correct-address",
    ts: 1720000001.25,
    reason: "correction fixture",
  };

  const duplicateBefore = tmpFile();
  for (const row of [first, second, correction]) appendShelterCostEntry(duplicateBefore, row);
  assert.throws(() => readShelterCostEntriesResolved(duplicateBefore), /ambiguous/i);

  const duplicateAfter = tmpFile();
  for (const row of [first, correction, second]) appendShelterCostEntry(duplicateAfter, row);
  assert.throws(() => readShelterCostEntriesResolved(duplicateAfter), /ambiguous/i);
});

test("resolved reader rejects unsupported and malformed correction rows", () => {
  const baseCorrection = {
    correction: true,
    correctedField: "jobAddress",
    correctsTs: 1720000000.125,
    correctedJobAddress: "correct-address",
    ts: 1720000001.25,
    reason: "correction fixture",
  };
  const target = { ts: baseCorrection.correctsTs, jobAddress: "old", settledLeaseCostUsd: 1 };
  const unsupported = tmpFile();
  for (const row of [target, { ...baseCorrection, correctedField: "settledLeaseCostUsd" }]) {
    appendShelterCostEntry(unsupported, row);
  }
  assert.throws(() => readShelterCostEntriesResolved(unsupported), /unsupported correction field/i);

  const malformedRows = [
    { ...baseCorrection, correction: false },
    { ...baseCorrection, correctedJobAddress: "" },
    { ...baseCorrection, correctsTs: "1720000000.125" },
    { ...baseCorrection, ts: "1720000001.25" },
    { ...baseCorrection, reason: "" },
  ];
  for (const correction of malformedRows) {
    const f = tmpFile();
    for (const row of [target, correction]) appendShelterCostEntry(f, row);
    assert.throws(() => readShelterCostEntriesResolved(f), /malformed correction/i);
  }
});

test("resolved reader rejects normal rows with missing or unsafe timestamp and cost values", () => {
  const invalidRows = [
    { ts: "1720000000.125", settledLeaseCostUsd: 1 },
    { ts: true, settledLeaseCostUsd: 1 },
    { ts: null, settledLeaseCostUsd: 1 },
    { ts: 1720000000.125, settledLeaseCostUsd: "1" },
    { ts: 1720000000.125, settledLeaseCostUsd: true },
    { ts: 1720000000.125, settledLeaseCostUsd: null },
    { ts: 1720000000.125, settledLeaseCostUsd: -1 },
    { settledLeaseCostUsd: 1 },
    { ts: 1720000000.125 },
    null,
    true,
    1,
    "row",
    [],
  ];

  for (const row of invalidRows) {
    const f = tmpFile();
    appendShelterCostEntry(f, row);
    assert.throws(() => readShelterCostEntriesResolved(f), /malformed normal row/i);
  }

  const notJsonNumber = tmpFile();
  fs.writeFileSync(notJsonNumber, '{"ts":1,"settledLeaseCostUsd":NaN}\n');
  assert.throws(() => readShelterCostEntriesResolved(notJsonNumber));
});

test("module exports only raw readers, resolved reader, and append — no update/upsert primitive", () => {
  const mod = require("../shelter-cost-ledger");
  assert.deepEqual(Object.keys(mod).sort(), [
    "appendShelterCostEntry",
    "readShelterCostEntries",
    "readShelterCostEntriesResolved",
  ]);
});
