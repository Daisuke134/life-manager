"use strict";

const fs = require("node:fs");
const path = require("node:path");

const DEFAULT_CATALOG = path.resolve(__dirname, "../config/product-loop-catalog.json");
const HOSTS = new Set(["local", "cloud"]);
const COMPLETION_STATES = new Set(["verified", "setup_required", "not_applicable", "unknown"]);
const COMPLETION_CONTRACT_FIELDS = [
  "goal",
  "context",
  "admission",
  "receipt",
  "observability",
  "evaluation",
];
const RUNTIME_TERMINAL_RESULTS = new Set(["pass", "fail", "blocked", "running"]);
const RELEASE_SHA = /^[a-f0-9]{40}$/iu;

function readProductLoopCatalog(catalogFile = DEFAULT_CATALOG) {
  const value = JSON.parse(fs.readFileSync(catalogFile, "utf8"));
  if (value?.schema_version !== 1 || !value.host_requirements
    || !Array.isArray(value.host_requirements.local) || !Array.isArray(value.host_requirements.cloud)
    || !Array.isArray(value.loops) || value.loops.length !== 14) {
    throw new Error("product loop catalog invalid");
  }
  const ids = new Set();
  for (const loop of value.loops) {
    if (!loop || typeof loop.id !== "string" || !/^[a-z][a-z0-9-]*$/u.test(loop.id)
      || ids.has(loop.id) || typeof loop.name !== "string" || !loop.name.trim()
      || typeof loop.description !== "string" || !loop.description.trim()
      || !Array.isArray(loop.requirements) || !loop.hosts || typeof loop.hosts !== "object") {
      throw new Error("product loop catalog invalid");
    }
    ids.add(loop.id);
    for (const host of HOSTS) {
      const target = loop.hosts[host];
      if (!target || !["guided", "setup_required"].includes(target.availability)
        || !(target.command === null || (Array.isArray(target.command)
          && target.command.length > 0 && target.command.every((part) => typeof part === "string" && part)))) {
        throw new Error("product loop host contract invalid");
      }
      if (target.availability === "guided" && target.command === null) {
        throw new Error("guided product loop command unavailable");
      }
    }
    if (!Array.isArray(loop.job_ids) || loop.job_ids.length < 1
      || loop.job_ids.some((jobId) => typeof jobId !== "string" || !jobId.trim())
      || new Set(loop.job_ids).size !== loop.job_ids.length) {
      throw new Error("product loop job mapping invalid");
    }
  }
  return Object.freeze({
    host_requirements: Object.freeze({
      local: Object.freeze([...value.host_requirements.local]),
      cloud: Object.freeze([...value.host_requirements.cloud]),
    }),
    loops: Object.freeze(value.loops.map((loop) => Object.freeze(loop))),
  });
}

function planProductOnboarding(input = {}, options = {}) {
  const host = String(input.host || "").trim();
  if (!HOSTS.has(host)) throw new Error("onboarding host must be local or cloud");
  if (!Array.isArray(input.selected_loop_ids) || input.selected_loop_ids.length === 0) {
    throw new Error("select at least one product loop");
  }
  if (input.selected_loop_ids.includes("all")) throw new Error("start all is not an onboarding option");
  const selected = new Set(input.selected_loop_ids);
  if (selected.size !== input.selected_loop_ids.length
    || [...selected].some((id) => typeof id !== "string" || !id)) {
    throw new Error("selected product loops invalid");
  }
  const verified = new Set(Array.isArray(input.verified_requirements) ? input.verified_requirements : []);
  const catalog = readProductLoopCatalog(options.catalogFile);
  const byId = new Map(catalog.loops.map((loop) => [loop.id, loop]));
  const unknown = [...selected].filter((id) => !byId.has(id));
  if (unknown.length) throw new Error(`unknown product loop: ${unknown.join(",")}`);
  const loops = input.selected_loop_ids.map((id) => {
    const loop = byId.get(id);
    const target = loop.hosts[host];
    const missing = [...catalog.host_requirements[host], ...loop.requirements]
      .filter((requirement, index, values) => values.indexOf(requirement) === index && !verified.has(requirement));
    if (target.availability === "setup_required" && !missing.includes("host_adapter")) {
      missing.push("host_adapter");
    }
    return Object.freeze({
      id: loop.id,
      name: loop.name,
      description: loop.description,
      host,
      state: missing.length ? "setup_required" : "ready_to_start",
      missing: Object.freeze(missing),
      command: target.command ? Object.freeze([...target.command]) : null,
    });
  });
  return Object.freeze({
    schema_version: "product.onboarding.v1",
    host,
    selected_loop_ids: Object.freeze([...input.selected_loop_ids]),
    loops: Object.freeze(loops),
    starts_automatically: false,
    external_effects: Object.freeze([]),
  });
}

function buildRuntimeEvidence(catalogLoop, runtimeByJobId, releaseSha) {
  const observedJobIds = catalogLoop.job_ids.filter((jobId) => runtimeByJobId.has(jobId));
  const missingJobIds = catalogLoop.job_ids.filter((jobId) => !runtimeByJobId.has(jobId));
  const releaseMismatchJobIds = observedJobIds.filter((jobId) => {
    const row = runtimeByJobId.get(jobId);
    return row.installed_release_sha !== releaseSha || row.event_release_sha !== releaseSha;
  });
  const nonPassJobIds = observedJobIds.filter((jobId) => (
    runtimeByJobId.get(jobId).last_terminal_result !== "pass"
  ));
  const releaseMatch = missingJobIds.length === 0 && releaseMismatchJobIds.length === 0;
  const terminalPass = missingJobIds.length === 0 && nonPassJobIds.length === 0;
  const reason = missingJobIds.length > 0 ? "runtime_evidence_missing"
    : releaseMismatchJobIds.length > 0 ? "runtime_release_drift"
      : nonPassJobIds.length > 0 ? "runtime_terminal_not_pass" : null;
  return Object.freeze({
    observed_job_ids: Object.freeze([...observedJobIds]),
    missing_job_ids: Object.freeze([...missingJobIds]),
    release_mismatch_job_ids: Object.freeze([...releaseMismatchJobIds]),
    non_pass_job_ids: Object.freeze([...nonPassJobIds]),
    release_match: releaseMatch,
    terminal_pass: terminalPass,
    ready: releaseMatch && terminalPass,
    reason,
  });
}

function indexRuntimeRows(runtimeRows, catalog) {
  if (!Array.isArray(runtimeRows)) throw new Error("completion runtime rows invalid");
  const catalogJobIds = new Set(catalog.loops.flatMap((loop) => loop.job_ids));
  const rows = new Map();
  for (const row of runtimeRows) {
    if (!row || typeof row !== "object" || Array.isArray(row)
      || typeof row.loop_id !== "string" || !row.loop_id.trim()) {
      throw new Error("completion runtime row invalid");
    }
    for (const field of ["installed_release_sha", "event_release_sha", "last_terminal_result"]) {
      if (!Object.hasOwn(row, field)) throw new Error(`completion runtime row missing ${field}`);
    }
    for (const field of ["installed_release_sha", "event_release_sha"]) {
      if (row[field] !== null && (typeof row[field] !== "string" || !RELEASE_SHA.test(row[field]))) {
        throw new Error(`completion runtime ${field} invalid`);
      }
    }
    if (row.last_terminal_result !== null
      && !RUNTIME_TERMINAL_RESULTS.has(row.last_terminal_result)) {
      throw new Error("completion runtime terminal result invalid");
    }
    if (!catalogJobIds.has(row.loop_id)) continue;
    if (rows.has(row.loop_id)) throw new Error(`duplicate completion runtime row: ${row.loop_id}`);
    rows.set(row.loop_id, row);
  }
  return rows;
}

function buildProductLoopCompletionManifest(input = {}, options = {}) {
  const host = String(input.host || "").trim();
  if (!HOSTS.has(host)) throw new Error("completion host must be local or cloud");
  const releaseSha = String(input.release_sha || "").trim();
  if (!/^[a-f0-9]{40}$/iu.test(releaseSha)) throw new Error("completion release sha invalid");
  if (!Array.isArray(input.observations)) throw new Error("completion observations invalid");

  const catalog = readProductLoopCatalog(options.catalogFile);
  const runtimeRowsProvided = Object.hasOwn(input, "runtime_rows");
  const runtimeByJobId = runtimeRowsProvided ? indexRuntimeRows(input.runtime_rows, catalog) : null;
  const catalogIds = new Set(catalog.loops.map((loop) => loop.id));
  const observations = new Map();
  for (const observation of input.observations) {
    if (!observation || typeof observation.id !== "string" || !catalogIds.has(observation.id)
      || observations.has(observation.id)) {
      throw new Error("completion observations must contain each catalog loop exactly once");
    }
    observations.set(observation.id, observation);
  }
  if (observations.size !== catalog.loops.length) {
    throw new Error("completion observations must contain each catalog loop exactly once");
  }

  const loops = catalog.loops.map((catalogLoop) => {
    const observation = observations.get(catalogLoop.id);
    const runtimeEvidence = runtimeRowsProvided
      ? buildRuntimeEvidence(catalogLoop, runtimeByJobId, releaseSha) : null;
    const state = String(observation.state || "").trim();
    if (!COMPLETION_STATES.has(state)) throw new Error(`completion state invalid: ${catalogLoop.id}`);
    const reason = typeof observation.reason === "string" ? observation.reason.trim() : "";
    if (state !== "verified" && !reason) {
      throw new Error(`completion reason required: ${catalogLoop.id}`);
    }
    const sourceContract = observation.contract && typeof observation.contract === "object"
      ? observation.contract : {};
    const contract = Object.fromEntries(COMPLETION_CONTRACT_FIELDS.map((field) => [
      field, sourceContract[field] === true,
    ]));
    const ownerId = typeof observation.owner_id === "string" && observation.owner_id.trim()
      ? observation.owner_id.trim() : null;
    const observedRelease = typeof observation.release_sha === "string"
      && observation.release_sha.trim() ? observation.release_sha.trim() : null;
    const officialReceipt = observation.official_receipt === true;
    if (state === "verified"
      && (!officialReceipt || !ownerId || observedRelease !== releaseSha
        || COMPLETION_CONTRACT_FIELDS.some((field) => contract[field] !== true))) {
      throw new Error(`verified loop requires official receipt and matching release: ${catalogLoop.id}`);
    }
    if (state === "verified" && runtimeEvidence && !runtimeEvidence.ready) {
      throw new Error(`verified loop runtime evidence incomplete: ${catalogLoop.id}`);
    }
    return Object.freeze({
      id: catalogLoop.id,
      name: catalogLoop.name,
      job_ids: Object.freeze([...catalogLoop.job_ids]),
      host,
      state,
      reason,
      owner_id: ownerId,
      release_sha: observedRelease,
      official_receipt: officialReceipt,
      contract: Object.freeze(contract),
      runtime_evidence: runtimeEvidence,
    });
  });
  const counts = Object.fromEntries([...COMPLETION_STATES].map((state) => [
    state, loops.filter((loop) => loop.state === state).length,
  ]));
  return Object.freeze({
    schema_version: "product.loop.completion.v1",
    host,
    release_sha: releaseSha,
    loops: Object.freeze(loops),
    counts: Object.freeze(counts),
    unknown_count: counts.unknown,
    completion: counts.unknown === 0,
  });
}

module.exports = {
  DEFAULT_CATALOG,
  buildProductLoopCompletionManifest,
  planProductOnboarding,
  readProductLoopCatalog,
};
