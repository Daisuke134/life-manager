"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { readProductLoopCatalog } = require("../lib/product-onboarding.js");

const ROOT = path.resolve(__dirname, "../../..");

function inputWithDecision(decision) {
  const catalog = readProductLoopCatalog();
  const releaseSha = "9".repeat(40);
  return {
    release_sha: releaseSha,
    local_gate: {
      schema_version: "product.local.completion.v1",
      decision,
      host: "local",
      release_sha: releaseSha,
      reasons: decision === "pass" ? [] : ["unknown_product_loop"],
    },
    cloud_manifest: {
      schema_version: "product.loop.completion.v1",
      host: "cloud",
      release_sha: releaseSha,
      completion: true,
      unknown_count: 0,
      loops: catalog.loops.map((loop) => ({
        id: loop.id,
        state: "setup_required",
      })),
    },
    cloud_canary: {
      tenant_isolated: true,
      immutable_source: true,
      official_readback: "verified",
      replay_zero: true,
      local_state_copied: false,
      local_credentials_copied: false,
    },
  };
}

test("cloud promotion gate CLI emits a private PASS projection", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cloud-gate-pass-"));
  const inputPath = path.join(root, "input.json");
  const outputPath = path.join(root, "gate.json");
  fs.writeFileSync(inputPath, JSON.stringify(inputWithDecision("pass")));

  const result = spawnSync(process.execPath, [
    path.join(ROOT, "apps/life-manager/scripts/cloud-promotion-gate.js"),
    "--input", inputPath,
    "--output", outputPath,
  ], { cwd: ROOT, encoding: "utf8" });

  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(fs.readFileSync(outputPath, "utf8")).decision, "pass");
  assert.equal(fs.statSync(outputPath).mode & 0o777, 0o600);
  fs.rmSync(root, { recursive: true, force: true });
});

test("cloud promotion gate CLI blocks a local failure", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-cloud-gate-block-"));
  const inputPath = path.join(root, "input.json");
  fs.writeFileSync(inputPath, JSON.stringify(inputWithDecision("block")));

  const result = spawnSync(process.execPath, [
    path.join(ROOT, "apps/life-manager/scripts/cloud-promotion-gate.js"),
    "--input", inputPath,
  ], { cwd: ROOT, encoding: "utf8" });

  assert.equal(result.status, 1);
  assert.equal(JSON.parse(result.stdout).decision, "block");
  assert.deepEqual(JSON.parse(result.stdout).reasons, ["local_gate_blocked"]);
  fs.rmSync(root, { recursive: true, force: true });
});
