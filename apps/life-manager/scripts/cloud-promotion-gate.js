#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

const SHA40 = /^[a-f0-9]{40}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const REQUIRED_EVIDENCE = Object.freeze(["cl00", "cl01", "cl02", "cl03", "cl04"]);
const REQUIRED_MIGRATION = "2026-09-29-lm-cloud-free-onboarding.sql";

function usage() { return "usage: cloud-promotion-gate.js --input PATH [--output PATH]"; }

function parseArgs(args) {
  const values = {};
  for (let index = 0; index < args.length; index += 1) {
    const key = args[index];
    if (!["--input", "--output"].includes(key)) throw new Error(usage());
    const value = args[index + 1];
    if (!value || value.startsWith("--")) throw new Error(usage());
    values[key.slice(2)] = value;
    index += 1;
  }
  if (!values.input) throw new Error(usage());
  return values;
}

function record(value) { return Boolean(value && typeof value === "object" && !Array.isArray(value)); }

function evaluatePromotionCandidate(input = {}) {
  const reasons = [];
  const candidate = String(input.candidate_sha || "");
  if (input.schema_version !== "life-manager.cloud-promotion.v1") reasons.push("schema_invalid");
  if (!SHA40.test(candidate)) reasons.push("candidate_sha_invalid");
  if (!SHA40.test(String(input.origin_main_sha || "")) || input.origin_main_sha !== candidate) reasons.push("candidate_not_origin_main");

  const manifest = input.local_manifest;
  if (!record(manifest) || manifest.complete !== true || manifest.release_sha !== candidate
      || !SHA256.test(String(manifest.sha256 || ""))) reasons.push("local_manifest_incomplete");

  const evidence = input.evidence;
  for (const gate of REQUIRED_EVIDENCE) {
    const row = record(evidence) ? evidence[gate] : null;
    if (!record(row) || row.status !== "verified" || row.release_sha !== candidate
        || typeof row.ref !== "string" || !row.ref.trim()) reasons.push(`${gate}_unverified`);
  }

  const migration = input.migration;
  if (!record(migration) || migration.latest_version !== REQUIRED_MIGRATION
      || migration.applied !== true || migration.replay_safe !== true
      || !SHA256.test(String(migration.manifest_sha256 || ""))) reasons.push("migration_unverified");

  const agentcore = input.agentcore;
  if (!record(agentcore) || agentcore.region !== "ap-northeast-1"
      || !SHA256.test(String(agentcore.config_sha256 || ""))
      || agentcore.config_sha256 !== agentcore.expected_config_sha256) reasons.push("agentcore_config_mismatch");

  const sessions = input.sessions;
  if (!record(sessions) || sessions.old_release_active !== 0
      || !Number.isSafeInteger(sessions.current_release_active) || sessions.current_release_active < 0) reasons.push("old_release_sessions_active");

  const cost = input.cost;
  if (!record(cost) || cost.cap_breaches !== 0 || cost.unsettled_unknown !== 0
      || cost.within_plan_caps !== true) reasons.push("cost_gate_failed");

  const rollback = input.rollback;
  if (!record(rollback) || rollback.verified !== true
      || !SHA40.test(String(rollback.release_sha || "")) || rollback.release_sha === candidate) reasons.push("rollback_target_invalid");

  const unique = [...new Set(reasons)];
  return Object.freeze({
    schema_version: "life-manager.cloud-promotion-decision.v1",
    decision: unique.length === 0 ? "pass" : "block",
    candidate_sha: candidate,
    rollback_sha: record(rollback) && SHA40.test(String(rollback.release_sha || "")) ? rollback.release_sha : null,
    reasons: Object.freeze(unique),
  });
}

function writePrivate(pathname, content) {
  const parent = path.dirname(pathname);
  fs.mkdirSync(parent, { recursive: true, mode: 0o700 });
  const temporary = `${pathname}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, content, { encoding: "utf8", mode: 0o600 });
  fs.chmodSync(temporary, 0o600);
  fs.renameSync(temporary, pathname);
  fs.chmodSync(pathname, 0o600);
}

function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  const gate = evaluatePromotionCandidate(JSON.parse(fs.readFileSync(options.input, "utf8")));
  const content = `${JSON.stringify(gate, null, 2)}\n`;
  if (options.output) writePrivate(options.output, content); else process.stdout.write(content);
  return gate.decision === "pass" ? 0 : 1;
}

if (require.main === module) {
  try { process.exitCode = main(); }
  catch (error) { process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`); process.exitCode = 1; }
}

module.exports = { REQUIRED_MIGRATION, evaluatePromotionCandidate, main };
