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
const RECEIPT_REF = /^[a-z][a-z0-9+.-]*:\/\/\S{1,1024}$/iu;
const RESOURCE_CLASS = /^[a-z][a-z0-9_.:-]{0,63}$/iu;
const NOTIFICATION_STATES = new Set(["internal_only", "user_visible", "not_configured"]);

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
  const runtimeJobIsHealthy = (row) => row.last_terminal_result === "pass"
    || (row.desired_mode === "continuous"
      && row.effect_class === "none"
      && row.last_terminal_result === "running");
  const nonPassJobIds = observedJobIds.filter((jobId) => (
    !runtimeJobIsHealthy(runtimeByJobId.get(jobId))
  ));
  const releaseMatch = missingJobIds.length === 0 && releaseMismatchJobIds.length === 0;
  const terminalPass = missingJobIds.length === 0 && observedJobIds.every((jobId) => (
    runtimeByJobId.get(jobId).last_terminal_result === "pass"
  ));
  const runtimeHealthy = missingJobIds.length === 0 && nonPassJobIds.length === 0;
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
    runtime_healthy: runtimeHealthy,
    ready: releaseMatch && runtimeHealthy,
    reason,
  });
}

function runtimeEvidenceMatchesCatalog(loop, catalogLoop) {
  const evidence = loop && loop.runtime_evidence;
  if (!evidence || typeof evidence !== "object" || Array.isArray(evidence)
    || !catalogLoop || !Array.isArray(catalogLoop.job_ids)
    || !Array.isArray(evidence.observed_job_ids)
    || !Array.isArray(evidence.missing_job_ids)
    || !Array.isArray(evidence.release_mismatch_job_ids)
    || !Array.isArray(evidence.non_pass_job_ids)) {
    return false;
  }
  const sameSequence = (actual, expected) => actual.length === expected.length
    && actual.every((value, index) => value === expected[index]);
  return sameSequence(evidence.observed_job_ids, catalogLoop.job_ids)
    && evidence.missing_job_ids.length === 0
    && evidence.release_mismatch_job_ids.length === 0
    && evidence.non_pass_job_ids.length === 0
    && evidence.release_match === true
    && evidence.runtime_healthy === true
    && evidence.ready === true
    && evidence.reason === null
    && typeof evidence.terminal_pass === "boolean";
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
    if (Object.hasOwn(row, "job_id")
      && (typeof row.job_id !== "string" || row.job_id.trim() !== row.loop_id)) {
      throw new Error("completion runtime job identity mismatch");
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

function buildDefaultProductLoopObservations(input = {}, options = {}) {
  const host = String(input.host || "").trim();
  if (!HOSTS.has(host)) throw new Error("default observation host must be local or cloud");
  const releaseSha = String(input.release_sha || "").trim();
  if (!RELEASE_SHA.test(releaseSha)) throw new Error("default observation release sha invalid");
  const catalog = readProductLoopCatalog(options.catalogFile);
  const runtimeByJobId = indexRuntimeRows(input.runtime_rows || [], catalog);
  const contract = Object.freeze(Object.fromEntries(
    COMPLETION_CONTRACT_FIELDS.map((field) => [field, false]),
  ));
  return Object.freeze(catalog.loops.map((loop) => {
    const runtimeEvidence = buildRuntimeEvidence(loop, runtimeByJobId, releaseSha);
    const setupRequired = loop.hosts[host].availability === "setup_required";
    return Object.freeze({
      id: loop.id,
      state: setupRequired ? "setup_required" : "unknown",
      reason: runtimeEvidence.reason || (setupRequired ? "host_adapter_pending" : "official_receipt_required"),
      owner_id: null,
      release_sha: null,
      official_receipt: false,
      official_receipt_ref: null,
      replay_zero: false,
      resource_class: "unknown",
      notification_state: "internal_only",
      contract,
    });
  }));
}

function evaluateCloudPromotionGate(input = {}, options = {}) {
  const reasons = [];
  const releaseSha = typeof input.release_sha === "string" ? input.release_sha : "";
  if (!RELEASE_SHA.test(releaseSha)) reasons.push("release_invalid");

  const localGate = input.local_gate;
  if (!localGate || typeof localGate !== "object" || Array.isArray(localGate)
    || localGate.schema_version !== "product.local.completion.v1"
    || localGate.host !== "local" || !Array.isArray(localGate.reasons)) {
    reasons.push("local_gate_invalid");
  } else {
    if (localGate.decision !== "pass") reasons.push("local_gate_blocked");
    if (localGate.release_sha !== releaseSha) reasons.push("local_release_mismatch");
  }

  const cloudManifest = input.cloud_manifest;
  if (!cloudManifest || typeof cloudManifest !== "object" || Array.isArray(cloudManifest)
    || cloudManifest.schema_version !== "product.loop.completion.v1"
    || cloudManifest.host !== "cloud" || cloudManifest.release_sha !== releaseSha) {
    reasons.push("cloud_manifest_invalid");
  } else {
    if (!Array.isArray(cloudManifest.loops) || cloudManifest.loops.length !== 14) {
      reasons.push("cloud_manifest_loop_count_mismatch");
    } else {
      const actualIds = cloudManifest.loops.map((loop) => loop && loop.id);
      let expectedLoops = [];
      let expectedIds = [];
      try {
        expectedLoops = readProductLoopCatalog(options.catalogFile).loops;
        expectedIds = expectedLoops.map((loop) => loop.id);
      } catch {
        reasons.push("cloud_manifest_catalog_invalid");
      }
      const expectedById = new Map(expectedLoops.map((loop) => [loop.id, loop]));
      const sameIds = actualIds.length === expectedIds.length
        && [...actualIds].sort().every((id, index) => id === [...expectedIds].sort()[index]);
      if (!sameIds) reasons.push("cloud_manifest_loop_identity_mismatch");
      if (cloudManifest.loops.some((loop) => !loop
        || !["verified", "setup_required", "not_applicable"].includes(loop.state)
        || typeof loop.resource_class !== "string" || !RESOURCE_CLASS.test(loop.resource_class)
        || typeof loop.notification_state !== "string" || !NOTIFICATION_STATES.has(loop.notification_state))) {
        reasons.push("cloud_manifest_state_invalid");
      }
      if (cloudManifest.loops.some((loop) => loop && loop.state === "verified"
        && (!loop.runtime_evidence || loop.runtime_evidence.ready !== true))) {
        reasons.push("cloud_manifest_runtime_evidence_incomplete");
      }
      if (cloudManifest.loops.some((loop) => loop && loop.state === "verified"
        && loop.runtime_evidence
        && !runtimeEvidenceMatchesCatalog(loop, expectedById.get(loop.id)))) {
        reasons.push("cloud_manifest_runtime_evidence_invalid");
      }
      if (cloudManifest.loops.some((loop) => loop && loop.state === "verified"
        && loop.official_receipt_release_sha !== releaseSha)) {
        reasons.push("cloud_manifest_receipt_release_mismatch");
      }
    }
    if (cloudManifest.completion !== true || cloudManifest.unknown_count !== 0) {
      reasons.push("cloud_manifest_incomplete");
    }
  }

  const canary = input.cloud_canary;
  if (!canary || typeof canary !== "object" || Array.isArray(canary)) {
    reasons.push("cloud_canary_invalid");
  } else {
    if (canary.tenant_isolated !== true) reasons.push("tenant_isolation_unverified");
    if (canary.immutable_source !== true) reasons.push("immutable_source_unverified");
    if (canary.official_readback !== "verified") reasons.push("cloud_readback_missing");
    if (canary.replay_zero !== true) reasons.push("cloud_replay_not_zero");
    if (canary.local_state_copied !== false) reasons.push("local_state_copy_unverified");
    if (canary.local_credentials_copied !== false) reasons.push("local_credentials_copy_unverified");
  }

  const uniqueReasons = [...new Set(reasons)];
  return Object.freeze({
    schema_version: "product.cloud.promotion.v1",
    decision: uniqueReasons.length ? "block" : "pass",
    release_sha: releaseSha,
    reasons: Object.freeze(uniqueReasons),
  });
}

function evaluateLocalCompletionGate(manifest, options = {}) {
  const reasons = [];
  let catalog;
  try {
    catalog = readProductLoopCatalog(options.catalogFile);
  } catch {
    reasons.push("catalog_invalid");
  }
  const validManifest = manifest && typeof manifest === "object" && !Array.isArray(manifest);
  if (!validManifest) {
    reasons.push("manifest_invalid");
  } else {
    if (manifest.schema_version !== "product.loop.completion.v1") reasons.push("manifest_schema_invalid");
    if (manifest.host !== "local") reasons.push("host_not_local");
    if (typeof manifest.release_sha !== "string" || !RELEASE_SHA.test(manifest.release_sha)) {
      reasons.push("manifest_release_invalid");
    }
    if (!Array.isArray(manifest.loops)) {
      reasons.push("manifest_loops_invalid");
    } else if (catalog) {
      const byId = new Map(manifest.loops.map((loop) => [loop && loop.id, loop]));
      for (const catalogLoop of catalog.loops) {
        const loop = byId.get(catalogLoop.id);
        if (!loop) {
          reasons.push("product_loop_missing");
          continue;
        }
        const state = String(loop.state || "").trim();
        if (state === "unknown") {
          reasons.push("unknown_product_loop");
        } else if (!["verified", "setup_required", "not_applicable"].includes(state)) {
          reasons.push("invalid_product_loop_state");
        }
        if (state !== "verified" && !(typeof loop.reason === "string" && loop.reason.trim())) {
          reasons.push("unexplained_product_loop_state");
        }
        if (typeof loop.resource_class !== "string" || !RESOURCE_CLASS.test(loop.resource_class)) {
          reasons.push("resource_class_invalid");
        }
        if (typeof loop.notification_state !== "string" || !NOTIFICATION_STATES.has(loop.notification_state)) {
          reasons.push("notification_boundary_invalid");
        }
        if (state === "verified" && (
          loop.official_receipt !== true
          || typeof loop.official_receipt_ref !== "string" || !RECEIPT_REF.test(loop.official_receipt_ref)
          || loop.official_receipt_release_sha !== manifest.release_sha
          || loop.replay_zero !== true
          || loop.resource_class === "unknown"
          || loop.notification_state === "not_configured"
          || typeof loop.owner_id !== "string" || !loop.owner_id.trim()
          || loop.release_sha !== manifest.release_sha
          || !loop.contract || COMPLETION_CONTRACT_FIELDS.some((field) => loop.contract[field] !== true)
          || !loop.runtime_evidence || loop.runtime_evidence.ready !== true
        )) {
          reasons.push("verified_evidence_incomplete");
        }
        if (state === "verified" && loop.runtime_evidence
          && !runtimeEvidenceMatchesCatalog(loop, catalogLoop)) {
          reasons.push("verified_runtime_evidence_invalid");
        }
      }
      if (manifest.loops.length !== catalog.loops.length) reasons.push("manifest_loop_count_mismatch");
      const unknownCount = manifest.loops.filter((loop) => loop && loop.state === "unknown").length;
      if (manifest.unknown_count !== unknownCount) reasons.push("manifest_unknown_count_mismatch");
      if (manifest.completion !== (unknownCount === 0)) reasons.push("manifest_completion_mismatch");
    }
  }
  const uniqueReasons = [...new Set(reasons)];
  return Object.freeze({
    schema_version: "product.local.completion.v1",
    decision: uniqueReasons.length ? "block" : "pass",
    host: validManifest && manifest.host === "local" ? "local" : null,
    release_sha: validManifest && typeof manifest.release_sha === "string"
      ? manifest.release_sha : null,
    reasons: Object.freeze(uniqueReasons),
  });
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
    const officialReceiptRef = typeof observation.official_receipt_ref === "string"
      && observation.official_receipt_ref.trim() ? observation.official_receipt_ref.trim() : null;
    const officialReceiptReleaseSha = typeof observation.official_receipt_release_sha === "string"
      && RELEASE_SHA.test(observation.official_receipt_release_sha.trim())
      ? observation.official_receipt_release_sha.trim() : null;
    const resourceClass = typeof observation.resource_class === "string"
      && observation.resource_class.trim() ? observation.resource_class.trim() : "unknown";
    if (!RESOURCE_CLASS.test(resourceClass)) {
      throw new Error(`completion resource class invalid: ${catalogLoop.id}`);
    }
    const notificationState = observation.notification_state === undefined
      ? "internal_only" : String(observation.notification_state).trim();
    if (!NOTIFICATION_STATES.has(notificationState)) {
      throw new Error(`completion notification boundary invalid: ${catalogLoop.id}`);
    }
    if (officialReceiptRef && !RECEIPT_REF.test(officialReceiptRef)) {
      throw new Error(`completion official receipt reference invalid: ${catalogLoop.id}`);
    }
    if (observation.replay_zero !== undefined && typeof observation.replay_zero !== "boolean") {
      throw new Error(`completion replay-zero proof invalid: ${catalogLoop.id}`);
    }
    const replayZero = observation.replay_zero === true;
    if (state === "verified"
      && (!officialReceipt || !ownerId || observedRelease !== releaseSha
        || !officialReceiptRef || officialReceiptReleaseSha !== releaseSha || !replayZero
        || resourceClass === "unknown" || notificationState === "not_configured"
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
      official_receipt_ref: officialReceiptRef,
      official_receipt_release_sha: officialReceiptReleaseSha,
      replay_zero: replayZero,
      resource_class: resourceClass,
      notification_state: notificationState,
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
  buildDefaultProductLoopObservations,
  buildProductLoopCompletionManifest,
  evaluateCloudPromotionGate,
  evaluateLocalCompletionGate,
  planProductOnboarding,
  readProductLoopCatalog,
};
