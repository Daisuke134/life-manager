"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const {
  buildProductLoopCompletionManifest,
  readProductLoopCatalog,
} = require("../lib/product-onboarding.js");

const ROOT = path.resolve(__dirname, "../../..");

function manifestWithStates(state) {
  const catalog = readProductLoopCatalog();
  const releaseSha = "6".repeat(40);
  return buildProductLoopCompletionManifest({
    host: "local",
    release_sha: releaseSha,
    observations: catalog.loops.map((loop, index) => ({
      id: loop.id,
      state: index === 0 && state === "unknown" ? "unknown" : "setup_required",
      reason: index === 0 && state === "unknown" ? "evidence_not_collected" : "host_adapter_pending",
      contract: {},
    })),
  });
}

test("local completion gate CLI emits a private PASS projection", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-local-gate-pass-"));
  const manifestPath = path.join(root, "manifest.json");
  const outputPath = path.join(root, "gate.json");
  fs.writeFileSync(manifestPath, JSON.stringify(manifestWithStates("setup_required")));

  const result = spawnSync(process.execPath, [
    path.join(ROOT, "apps/life-manager/scripts/local-completion-gate.js"),
    "--manifest", manifestPath,
    "--output", outputPath,
  ], { cwd: ROOT, encoding: "utf8" });

  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(fs.readFileSync(outputPath, "utf8")).decision, "pass");
  assert.equal(fs.statSync(outputPath).mode & 0o777, 0o600);
  fs.rmSync(root, { recursive: true, force: true });
});

test("local completion gate CLI exits nonzero and explains unknown loops", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-local-gate-block-"));
  const manifestPath = path.join(root, "manifest.json");
  fs.writeFileSync(manifestPath, JSON.stringify(manifestWithStates("unknown")));

  const result = spawnSync(process.execPath, [
    path.join(ROOT, "apps/life-manager/scripts/local-completion-gate.js"),
    "--manifest", manifestPath,
  ], { cwd: ROOT, encoding: "utf8" });

  assert.equal(result.status, 1);
  assert.equal(JSON.parse(result.stdout).decision, "block");
  assert.deepEqual(JSON.parse(result.stdout).reasons, ["unknown_product_loop"]);
  fs.rmSync(root, { recursive: true, force: true });
});
