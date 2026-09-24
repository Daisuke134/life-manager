#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { readProductLoopCatalog } = require("../lib/product-onboarding.js");
const {
  RECOVERY_CLASSES,
  classifyRecoveryJob,
} = require("../../../runtime/loop/recovery-class.cjs");

const DEFAULT_REGISTRY = path.resolve(__dirname, "../../../config/loop-registry.json");
const AVAILABILITIES = new Set(["guided", "ready", "setup_required", "unsupported"]);
const REQUIRED_JOB_FIELDS = [
  "entrypoint",
  "label",
  "provider_route",
  "domain",
  "effect_class",
  "cadence",
  "state_root",
];

function usage() {
  return "usage: loop-contract-gate.js [--catalog PATH] [--registry PATH] [--output PATH]";
}

function parseArgs(args) {
  const values = {};
  for (let i = 0; i < args.length; i += 1) {
    const key = args[i];
    if (!["--catalog", "--registry", "--output"].includes(key)) throw new Error(usage());
    const value = args[i + 1];
    if (!value || value.startsWith("--")) throw new Error(usage());
    values[key.slice(2)] = value;
    i += 1;
  }
  return values;
}

function readRegistry(registryFile) {
  const value = JSON.parse(fs.readFileSync(registryFile, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)
    || !value.loops || typeof value.loops !== "object" || Array.isArray(value.loops)) {
    throw new Error("loop registry invalid");
  }
  return value;
}

function addError(errors, code, pathValue, detail) {
  errors.push({ code, path: pathValue, detail });
}

function validateLoopContract({ catalog, registry, recoveryFixtures }) {
  const errors = [];
  const loops = Array.isArray(catalog && catalog.loops) ? catalog.loops : null;
  if (!loops || loops.length === 0) {
    addError(errors, "catalog_loops_missing", "loops", "catalog must contain at least one loop");
    return { ok: false, catalog_loops: 0, registry_jobs: Object.keys(registry.loops).length, errors };
  }

  const loopIds = new Set();
  const mappedJobs = new Map();
  const declaredRecoveryClasses = catalog?.recovery_contract?.classes;
  if (!Array.isArray(declaredRecoveryClasses)
    || declaredRecoveryClasses.length !== RECOVERY_CLASSES.length
    || declaredRecoveryClasses.some((item, index) => item !== RECOVERY_CLASSES[index])) {
    addError(errors, "recovery_contract_invalid", "recovery_contract.classes", "closed class set required");
  }
  const fixtureClasses = Array.isArray(recoveryFixtures?.classes)
    ? recoveryFixtures.classes.map((row) => row?.id) : [];
  for (const recoveryClass of RECOVERY_CLASSES) {
    if (fixtureClasses.filter((id) => id === recoveryClass).length !== 1) {
      addError(errors, "recovery_fixture_missing", `recovery_contract.classes[${recoveryClass}]`,
        "exactly one retained class fixture is required");
    }
  }
  for (const [index, loop] of loops.entries()) {
    const prefix = `loops[${index}]`;
    if (!loop || typeof loop !== "object" || Array.isArray(loop)) {
      addError(errors, "catalog_loop_invalid", prefix, "loop must be an object");
      continue;
    }
    if (typeof loop.id !== "string" || !loop.id.trim()) addError(errors, "loop_id_missing", `${prefix}.id`, "required");
    else if (loopIds.has(loop.id)) addError(errors, "loop_id_duplicate", `${prefix}.id`, loop.id);
    else loopIds.add(loop.id);
    if (typeof loop.name !== "string" || !loop.name.trim()) addError(errors, "loop_name_missing", `${prefix}.name`, "required");
    if (!Array.isArray(loop.requirements)) addError(errors, "requirements_invalid", `${prefix}.requirements`, "must be an array");
    if (!loop.hosts || typeof loop.hosts !== "object" || Array.isArray(loop.hosts)) {
      addError(errors, "hosts_missing", `${prefix}.hosts`, "local/cloud host adapters are required");
    } else {
      for (const host of ["local", "cloud"]) {
        const adapter = loop.hosts[host];
        if (!adapter || typeof adapter !== "object" || Array.isArray(adapter)) {
          addError(errors, "host_adapter_missing", `${prefix}.hosts.${host}`, "required");
        } else if (!AVAILABILITIES.has(adapter.availability)) {
          addError(errors, "host_availability_invalid", `${prefix}.hosts.${host}.availability`, String(adapter.availability));
        }
      }
    }
    if (!Array.isArray(loop.job_ids) || loop.job_ids.length === 0) {
      addError(errors, "job_ids_missing", `${prefix}.job_ids`, "at least one canonical runtime job is required");
      continue;
    }
    if (new Set(loop.job_ids).size !== loop.job_ids.length) {
      addError(errors, "job_ids_duplicate", `${prefix}.job_ids`, "job IDs must be unique per product loop");
    }
    const observedRecoveryClasses = new Set();
    for (const jobId of loop.job_ids) {
      const jobPath = `${prefix}.job_ids[${jobId}]`;
      const job = registry.loops[jobId];
      if (!job || typeof job !== "object") {
        addError(errors, "runtime_job_missing", jobPath, "job is absent from config/loop-registry.json");
        continue;
      }
      mappedJobs.set(jobId, (mappedJobs.get(jobId) || 0) + 1);
      try {
        observedRecoveryClasses.add(classifyRecoveryJob(job));
      } catch (error) {
        addError(errors, "recovery_job_unclassified", jobPath, String(error?.message || error));
      }
      for (const field of REQUIRED_JOB_FIELDS) {
        if (job[field] === undefined || job[field] === null || job[field] === "") {
          addError(errors, "runtime_job_field_missing", `${jobPath}.${field}`, "required by the shared loop contract");
        }
      }
      if (typeof job.entrypoint === "string"
        && (path.isAbsolute(job.entrypoint) || job.entrypoint.split("/").includes(".."))) {
        addError(errors, "entrypoint_not_repository_relative", `${jobPath}.entrypoint`, job.entrypoint);
      }
      if (typeof job.label === "string" && !job.label.startsWith("ai.anicca.")) {
        addError(errors, "label_not_managed", `${jobPath}.label`, job.label);
      }
    }
    const declared = Array.isArray(loop.recovery_classes) ? loop.recovery_classes : [];
    const observed = [...observedRecoveryClasses].sort();
    if (declared.length === 0
      || declared.some((item, itemIndex) => !RECOVERY_CLASSES.includes(item)
        || (itemIndex > 0 && declared[itemIndex - 1] >= item))
      || JSON.stringify(declared) !== JSON.stringify(observed)) {
      addError(errors, "recovery_class_mismatch", `${prefix}.recovery_classes`,
        `declared=${JSON.stringify(declared)} observed=${JSON.stringify(observed)}`);
    }
  }

  // Product-loop mapping is the business grouping, but every registry job is
  // still executable runtime. Validate unmapped jobs against the same
  // repository-relative ownership contract so a future job cannot bypass the
  // shared foundation merely by being absent from the 14-product catalog.
  for (const [jobId, job] of Object.entries(registry.loops)) {
    if (mappedJobs.has(jobId)) continue;
    const jobPath = jobId;
    if (!job || typeof job !== "object" || Array.isArray(job)) {
      addError(errors, "runtime_job_invalid", jobPath, "job must be an object");
      continue;
    }
    for (const field of REQUIRED_JOB_FIELDS) {
      if (job[field] === undefined || job[field] === null || job[field] === "") {
        addError(errors, "runtime_job_field_missing", `${jobPath}.${field}`, "required by the shared loop contract");
      }
    }
    if (typeof job.entrypoint === "string"
      && (path.isAbsolute(job.entrypoint) || job.entrypoint.split("/").includes(".."))) {
      addError(errors, "entrypoint_not_repository_relative", `${jobPath}.entrypoint`, job.entrypoint);
    }
    if (typeof job.label === "string" && !job.label.startsWith("ai.anicca.")) {
      addError(errors, "label_not_managed", `${jobPath}.label`, job.label);
    }
  }

  const sharedJobs = [...mappedJobs.entries()].filter(([, count]) => count > 1).map(([id]) => id);
  for (const jobId of sharedJobs) {
    addError(errors, "runtime_job_mapped_multiple_times", `job_ids[${jobId}]`,
      "each runtime job must belong to exactly one Product Loop");
  }
  return {
    ok: errors.length === 0,
    catalog_loops: loops.length,
    registry_jobs: Object.keys(registry.loops).length,
    mapped_jobs: mappedJobs.size,
    shared_job_ids: sharedJobs,
    errors,
  };
}

function writePrivate(output, content) {
  fs.mkdirSync(path.dirname(output), { recursive: true, mode: 0o700 });
  fs.writeFileSync(output, content, { encoding: "utf8", mode: 0o600 });
  fs.chmodSync(output, 0o600);
}

function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const catalogFile = path.resolve(options.catalog || path.resolve(__dirname, "../config/product-loop-catalog.json"));
  const registryFile = path.resolve(options.registry || DEFAULT_REGISTRY);
  const catalog = readProductLoopCatalog(catalogFile);
  const recoveryFixtureFile = path.resolve(__dirname, "../../..", catalog.recovery_contract.fixture);
  const result = validateLoopContract({
    catalog,
    registry: readRegistry(registryFile),
    recoveryFixtures: JSON.parse(fs.readFileSync(recoveryFixtureFile, "utf8")),
  });
  const content = `${JSON.stringify(result, null, 2)}\n`;
  if (options.output) writePrivate(path.resolve(options.output), content);
  else process.stdout.write(content);
  return result.ok ? 0 : 1;
}

if (require.main === module) {
  try {
    process.exitCode = main();
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}

module.exports = { validateLoopContract, readRegistry };
