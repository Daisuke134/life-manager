"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { evaluatePromotionCandidate, REQUIRED_MIGRATION } = require("./cloud-promotion-gate.js");

const ROOT = path.resolve(__dirname, "../../..");
const CANDIDATE = "9".repeat(40);
const ROLLBACK = "8".repeat(40);
const HASH = "a".repeat(64);

function validInput() {
  return {
    schema_version: "life-manager.cloud-promotion.v1", candidate_sha: CANDIDATE, origin_main_sha: CANDIDATE,
    local_manifest: { complete: true, release_sha: CANDIDATE, sha256: HASH },
    evidence: Object.fromEntries(["cl00", "cl01", "cl02", "cl03", "cl04"].map((gate) => [gate,
      { status: "verified", release_sha: CANDIDATE, ref: `evidence://${gate}/receipt` }])),
    migration: { latest_version: REQUIRED_MIGRATION, applied: true, replay_safe: true, manifest_sha256: HASH },
    agentcore: { region: "ap-northeast-1", config_sha256: HASH, expected_config_sha256: HASH },
    sessions: { old_release_active: 0, current_release_active: 1 },
    cost: { cap_breaches: 0, unsettled_unknown: 0, within_plan_caps: true },
    rollback: { verified: true, release_sha: ROLLBACK },
  };
}

test("promotion passes only a complete main-derived immutable candidate", () => {
  assert.deepEqual(evaluatePromotionCandidate(validInput()), {
    schema_version: "life-manager.cloud-promotion-decision.v1", decision: "pass",
    candidate_sha: CANDIDATE, rollback_sha: ROLLBACK, reasons: [],
  });
});

test("each required promotion boundary independently blocks", () => {
  const cases = [
    ["candidate_not_origin_main", (x) => { x.origin_main_sha = "7".repeat(40); }],
    ["local_manifest_incomplete", (x) => { x.local_manifest.complete = false; }],
    ["cl00_unverified", (x) => { x.evidence.cl00.status = "pending"; }],
    ["cl01_unverified", (x) => { x.evidence.cl01.release_sha = ROLLBACK; }],
    ["cl02_unverified", (x) => { x.evidence.cl02.ref = ""; }],
    ["cl03_unverified", (x) => { delete x.evidence.cl03; }],
    ["cl04_unverified", (x) => { x.evidence.cl04 = null; }],
    ["migration_unverified", (x) => { x.migration.replay_safe = false; }],
    ["agentcore_config_mismatch", (x) => { x.agentcore.expected_config_sha256 = "b".repeat(64); }],
    ["old_release_sessions_active", (x) => { x.sessions.old_release_active = 1; }],
    ["cost_gate_failed", (x) => { x.cost.unsettled_unknown = 1; }],
    ["rollback_target_invalid", (x) => { x.rollback.release_sha = CANDIDATE; }],
  ];
  for (const [reason, mutate] of cases) {
    const input = validInput(); mutate(input);
    const result = evaluatePromotionCandidate(input);
    assert.equal(result.decision, "block", reason);
    assert.ok(result.reasons.includes(reason), `${reason}: ${result.reasons.join(",")}`);
  }
});

test("CLI writes a private decision and returns nonzero for a blocked candidate", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cloud-promotion-"));
  const inputPath = path.join(root, "input.json");
  const outputPath = path.join(root, "decision.json");
  const input = validInput(); input.evidence.cl00.status = "provider_pending";
  fs.writeFileSync(inputPath, JSON.stringify(input));
  const result = spawnSync(process.execPath, [path.join(ROOT, "apps/life-manager/scripts/cloud-promotion-gate.js"),
    "--input", inputPath, "--output", outputPath], { cwd: ROOT, encoding: "utf8" });
  assert.equal(result.status, 1, result.stderr);
  assert.equal(JSON.parse(fs.readFileSync(outputPath)).decision, "block");
  assert.equal(fs.statSync(outputPath).mode & 0o777, 0o600);
  fs.rmSync(root, { recursive: true, force: true });
});
