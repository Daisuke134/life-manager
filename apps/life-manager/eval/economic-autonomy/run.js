"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const { validateCase, validateRun } = require("./records.js");
const { scoreEconomicAutonomy } = require("./score.js");

const FIXTURES_DIR = path.join(__dirname, "fixtures");
const MAX_FIXTURE_BYTES = 1024 * 1024;
const MAX_CASES = 10_000;
const MAX_CASE_FILE_BYTES = 16 * 1024 * 1024;
const BUNDLE_KEYS = Object.freeze([
  "episode", "financialRecords", "attributions", "autonomyEvents", "costCoverage",
]);
const STARTED_AT = "2000-01-01T00:00:00.000Z";
const FINISHED_AT = "2000-01-01T00:00:00.001Z";

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`LM-EAB ${label} invalid`);
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) {
    throw new Error(`LM-EAB ${label} invalid`);
  }
}

function parseCasesText(text) {
  if (typeof text !== "string" || Buffer.byteLength(text) > MAX_CASE_FILE_BYTES) {
    throw new Error("LM-EAB case corpus size invalid");
  }
  const lines = text.split("\n").filter((line) => line.trim() !== "");
  if (lines.length === 0 || lines.length > MAX_CASES) {
    throw new Error("LM-EAB case count invalid");
  }
  const cases = lines.map((line, index) => {
    let value;
    try {
      value = JSON.parse(line);
    } catch {
      throw new Error(`LM-EAB case JSON invalid at line ${index + 1}`);
    }
    return validateCase(value);
  });
  if (new Set(cases.map((item) => item.case_id)).size !== cases.length) {
    throw new Error("LM-EAB duplicate case_id");
  }
  return Object.freeze(cases);
}

function resolveFixture(fixtureRef) {
  let parsed;
  try {
    parsed = new URL(fixtureRef);
  } catch {
    throw new Error("LM-EAB fixture reference invalid");
  }
  const filename = parsed.pathname.slice(1);
  if (parsed.protocol !== "fixture:" || parsed.hostname !== "economic-autonomy"
    || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json$/u.test(filename)) {
    throw new Error("LM-EAB fixture reference invalid");
  }
  const fixtureRoot = fs.realpathSync(FIXTURES_DIR);
  const candidate = fs.realpathSync(path.resolve(FIXTURES_DIR, filename));
  if (!candidate.startsWith(`${fixtureRoot}${path.sep}`)) {
    throw new Error("LM-EAB fixture boundary invalid");
  }
  return candidate;
}

function defaultReadFixture(fixtureRef) {
  const fixturePath = resolveFixture(fixtureRef);
  const stat = fs.statSync(fixturePath);
  if (!stat.isFile() || stat.size > MAX_FIXTURE_BYTES) {
    throw new Error("LM-EAB fixture size invalid");
  }
  const bytes = fs.readFileSync(fixturePath);
  if (bytes.length > MAX_FIXTURE_BYTES) throw new Error("LM-EAB fixture size invalid");
  return bytes;
}

function parseBundle(bytes) {
  if (!Buffer.isBuffer(bytes) || bytes.length > MAX_FIXTURE_BYTES) {
    throw new Error("LM-EAB fixture size invalid");
  }
  let bundle;
  try {
    bundle = JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new Error("LM-EAB fixture JSON invalid");
  }
  exactKeys(bundle, BUNDLE_KEYS, "fixture bundle");
  return bundle;
}

function evaluateCase(rawCase, options = {}) {
  const item = validateCase(rawCase);
  const runId = options.runId || `run-${item.input_sha256.slice(0, 16)}`;
  const readFixture = options.readFixture || defaultReadFixture;
  const bytes = readFixture(item.fixture_ref);
  if (!Buffer.isBuffer(bytes) || sha256(bytes) !== item.input_sha256) {
    throw new Error(`LM-EAB fixture hash mismatch for ${item.case_id}`);
  }
  const bundle = parseBundle(bytes);
  const score = scoreEconomicAutonomy({
    scoreId: `score-${item.case_id}`,
    runId,
    caseId: item.case_id,
    ...bundle,
  });
  const expected = item.expected;
  if (score.eligible !== expected.eligible
    || score.settled_net_profit_minor !== expected.settled_net_profit_minor
    || score.recurring_revenue_minor !== expected.recurring_revenue_minor
    || JSON.stringify(score.reason_codes) !== JSON.stringify(expected.reason_codes)) {
    throw new Error(`LM-EAB expected mismatch for ${item.case_id}`);
  }
  return score;
}

function validateCorpus(cases) {
  for (const split of ["tuning", "held_out"]) {
    const rows = cases.filter((item) => item.split === split);
    if (rows.length === 0
      || !rows.some((item) => item.expected.eligible)
      || !rows.some((item) => !item.expected.eligible)) {
      throw new Error(`LM-EAB ${split} coverage invalid`);
    }
  }
}

function readCasesFile(casesPath) {
  const stat = fs.statSync(casesPath);
  if (!stat.isFile() || stat.size > MAX_CASE_FILE_BYTES) {
    throw new Error("LM-EAB case corpus size invalid");
  }
  const bytes = fs.readFileSync(casesPath);
  if (bytes.length > MAX_CASE_FILE_BYTES) throw new Error("LM-EAB case corpus size invalid");
  return bytes;
}

function runCorpus(casesPath) {
  const caseBytes = readCasesFile(casesPath);
  const cases = parseCasesText(caseBytes.toString("utf8"));
  validateCorpus(cases);
  const caseSetSha256 = sha256(caseBytes);
  const runId = `run-${caseSetSha256.slice(0, 16)}`;
  const scores = cases.map((item) => evaluateCase(item, { runId }));
  const firstBundle = parseBundle(defaultReadFixture(cases[0].fixture_ref));
  for (const item of cases.slice(1)) {
    const bundle = parseBundle(defaultReadFixture(item.fixture_ref));
    if (bundle.episode.release_sha256 !== firstBundle.episode.release_sha256
      || bundle.episode.model !== firstBundle.episode.model
      || bundle.episode.toolchain_sha256 !== firstBundle.episode.toolchain_sha256) {
      throw new Error("LM-EAB mixed runtime identity");
    }
  }
  const run = validateRun({
    schema_version: 1,
    record_type: "economic_autonomy_run",
    run_id: runId,
    case_set_sha256: caseSetSha256,
    release_sha256: firstBundle.episode.release_sha256,
    model: firstBundle.episode.model,
    toolchain_sha256: firstBundle.episode.toolchain_sha256,
    started_at: STARTED_AT,
    finished_at: FINISHED_AT,
    status: "completed",
    score_ids: scores.map((score) => score.score_id),
    trace_refs: cases.map((item) => `fixture://economic-autonomy/${item.case_id}`),
    error: null,
  });
  return Object.freeze({ run, scores: Object.freeze(scores) });
}

function main(argv) {
  if (argv.length !== 2 || argv[0] !== "--cases") {
    throw new Error("usage: node run.js --cases <cases.jsonl>");
  }
  const result = runCorpus(path.resolve(argv[1]));
  process.stdout.write(`${JSON.stringify(result.run)}\n`);
  for (const score of result.scores) process.stdout.write(`${JSON.stringify(score)}\n`);
}

if (require.main === module) {
  try {
    main(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`LM-EAB failed: ${error instanceof Error ? error.message : "unknown error"}\n`);
    process.exitCode = 1;
  }
}

module.exports = {
  FIXTURES_DIR,
  evaluateCase,
  parseCasesText,
  runCorpus,
};
