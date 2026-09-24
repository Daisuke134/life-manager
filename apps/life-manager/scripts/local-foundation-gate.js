#!/usr/bin/env node

"use strict";

const fs = require("node:fs");
const path = require("node:path");

const {
  buildProductLoopFoundationManifest,
  evaluateLocalFoundationGate,
} = require("../lib/product-onboarding.js");

function usage() {
  return "usage: local-foundation-gate.js --release-sha SHA --runtime-status PATH [--output PATH]";
}

function parseArgs(args) {
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (!["--release-sha", "--runtime-status", "--output"].includes(key)) throw new Error(usage());
    const value = args[index + 1];
    if (!value || value.startsWith("--")) throw new Error(usage());
    values[key.slice(2).replaceAll("-", "_")] = value;
    index += 1;
  }
  if (!values.release_sha || !values.runtime_status) throw new Error(usage());
  return values;
}

function writePrivate(pathname, content) {
  const parent = path.dirname(pathname);
  let parentExisted = true;
  try {
    if (!fs.statSync(parent).isDirectory()) throw new Error("output parent is not a directory");
  } catch (error) {
    if (error && error.code === "ENOENT") parentExisted = false;
    else throw error;
  }
  fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
  if (!parentExisted) fs.chmodSync(parent, 0o700);
  const temporary = `${pathname}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, content, { encoding: "utf8", mode: 0o600 });
  fs.chmodSync(temporary, 0o600);
  fs.renameSync(temporary, pathname);
  fs.chmodSync(pathname, 0o600);
}

function increment(map, key) {
  const normalized = key == null
    ? "none"
    : (typeof key === "string" && key.trim() ? key : "invalid");
  map[normalized] = (map[normalized] || 0) + 1;
}

function foundationDiagnostics(manifest) {
  const loops = Array.isArray(manifest?.loops) ? manifest.loops : [];
  const stateCounts = {};
  const reasonCounts = {};
  const nextActionCounts = {};
  for (const loop of loops) {
    increment(stateCounts, loop?.state);
    increment(reasonCounts, loop?.reason);
    increment(nextActionCounts, loop?.next_action);
  }
  const actionableLoops = loops
    .filter((loop) => loop?.state !== "healthy")
    .map((loop) => ({
      id: loop?.id ?? null,
      name: loop?.name ?? null,
      state: loop?.state ?? null,
      reason: loop?.reason ?? null,
      next_action: loop?.next_action ?? null,
      unknown_effect_job_ids: Array.isArray(loop?.unknown_effect_job_ids)
        ? [...loop.unknown_effect_job_ids] : [],
      diagnostic_incomplete_job_ids: Array.isArray(loop?.diagnostic_incomplete_job_ids)
        ? [...loop.diagnostic_incomplete_job_ids] : [],
      runtime_evidence: loop?.runtime_evidence && typeof loop.runtime_evidence === "object"
        ? {
          missing_job_ids: Array.isArray(loop.runtime_evidence.missing_job_ids)
            ? [...loop.runtime_evidence.missing_job_ids] : [],
          release_mismatch_job_ids: Array.isArray(loop.runtime_evidence.release_mismatch_job_ids)
            ? [...loop.runtime_evidence.release_mismatch_job_ids] : [],
          non_pass_job_ids: Array.isArray(loop.runtime_evidence.non_pass_job_ids)
            ? [...loop.runtime_evidence.non_pass_job_ids] : [],
        }
        : null,
    }));
  return {
    state_counts: stateCounts,
    reason_counts: reasonCounts,
    next_action_counts: nextActionCounts,
    actionable_loops: actionableLoops,
  };
}

function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const runtimeRows = JSON.parse(fs.readFileSync(options.runtime_status, "utf8"));
  const manifest = buildProductLoopFoundationManifest({
    host: "local",
    release_sha: options.release_sha,
    runtime_rows: runtimeRows,
  });
  const gate = evaluateLocalFoundationGate(manifest);
  const content = `${JSON.stringify({
    manifest,
    gate,
    diagnostics: foundationDiagnostics(manifest),
  }, null, 2)}\n`;
  if (options.output) writePrivate(options.output, content);
  else process.stdout.write(content);
  return gate.decision === "pass" ? 0 : 1;
}

try {
  process.exitCode = main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
