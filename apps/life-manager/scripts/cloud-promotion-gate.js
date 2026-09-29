#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const SHA40 = /^[a-f0-9]{40}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const REQUIRED_EVIDENCE = Object.freeze(["cl00", "cl01", "cl02", "cl03", "cl04"]);
const REQUIRED_MIGRATION = "2026-09-29-lm-cloud-free-onboarding.sql";
const REQUIRED_MIGRATIONS = Object.freeze([
  "20260928_agentcore_cloud_runtime.sql",
  "2026-09-29-lm-agent-identity-refs.sql",
  "2026-09-29-lm-browser-no-human.sql",
  "2026-09-29-lm-cloud-cost-reservations.sql",
  REQUIRED_MIGRATION,
]);

function migrationManifestSha256() {
  const hash = crypto.createHash("sha256");
  const directory = path.resolve(__dirname, "../migrations");
  for (const filename of REQUIRED_MIGRATIONS) {
    hash.update(filename);
    hash.update("\0");
    hash.update(fs.readFileSync(path.join(directory, filename)));
  }
  return hash.digest("hex");
}

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

function verifiedDigitalOceanProvider(provider, candidate) {
  const infrastructure = record(provider) ? provider.infrastructure_receipt : null;
  const parity = record(provider) ? provider.agent_parity_receipt : null;
  const readback = record(infrastructure) ? infrastructure.readback : null;
  const proof = record(readback) ? readback.proof : null;
  const teardown = record(readback) ? readback.teardown : null;
  return record(infrastructure) && infrastructure.status === "verified"
    && infrastructure.release_sha === candidate
    && /^digitalocean-infrastructure:\/\/sha256\/[a-f0-9]{64}$/.test(String(infrastructure.provider_receipt_id || ""))
    && record(readback.after_balance)
    && Array.isArray(teardown) && teardown.length >= 2
    && teardown.every((row) => record(row) && row.removed === true && /^sess_[A-Za-z0-9_-]+$/.test(String(row.session_id || "")))
    && record(proof) && proof.tenant_isolated === true && proof.browser_continuity === true
    && proof.official_readback === true && proof.replay_zero === true && proof.no_ask === true
    && proof.human_input_count === 0 && proof.effect === "none"
    && record(parity) && parity.status === "verified" && parity.release_sha === candidate
    && /^digitalocean-agent-parity:\/\/sha256\/[a-f0-9]{64}$/.test(String(parity.provider_receipt_id || ""))
    && SHA256.test(String(parity.receipt_hash || "")) && SHA256.test(String(parity.evidence_hash || ""))
    && parity.replay_zero === true && parity.human_input_count === 0;
}

function verifiedProvider(provider, candidate) {
  if (!record(provider)) return false;
  if (provider.name === "aws-agentcore") {
    return provider.region === "ap-northeast-1"
      && SHA256.test(String(provider.config_sha256 || ""))
      && provider.config_sha256 === provider.expected_config_sha256;
  }
  if (provider.name === "digitalocean-managed-agents") {
    return verifiedDigitalOceanProvider(provider, candidate);
  }
  return false;
}

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
      || JSON.stringify(migration.ordered_versions) !== JSON.stringify(REQUIRED_MIGRATIONS)
      || migration.applied !== true || migration.replay_safe !== true
      || migration.manifest_sha256 !== migrationManifestSha256()) reasons.push("migration_unverified");

  if (!verifiedProvider(input.provider, candidate)) reasons.push("provider_unverified");

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

module.exports = { REQUIRED_MIGRATION, REQUIRED_MIGRATIONS, migrationManifestSha256, evaluatePromotionCandidate, main };
