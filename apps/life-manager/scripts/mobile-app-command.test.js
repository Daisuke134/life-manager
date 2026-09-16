"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { resolveMobileAppLoop } = require("./mobile-app-command.js");

const root = path.resolve(__dirname, "../../..");
const manifest = require("../config/mobile-app-loops.json");
const destinations = require("../../../config/marketing-destinations.json");
const products = require("../config/mobile-products.json");
const registry = require("../../../config/loop-registry.json");

test("all mobile publication loops share one command and one manifest", () => {
  assert.deepEqual(
    new Set(Object.keys(manifest.loops)),
    new Set(destinations.targets.map((item) => item.loop_name)),
  );
  for (const hold of destinations.holds) {
    assert.ok(!destinations.targets.some((item) => item.integration_id === hold.integration_id), hold.postiz_profile);
  }
  assert.deepEqual(
    new Set(products.products.map((item) => item.product_id)),
    new Set(Object.values(manifest.loops).map((item) => item.product_id)),
  );
  assert.doesNotMatch(JSON.stringify(products), /\/Users\/|openclaw|hermes|credential/iu);
  for (const [loopId, expected] of Object.entries(manifest.loops)) {
    const entry = registry.loops[loopId];
    assert.ok(entry, loopId);
    assert.equal(entry.entrypoint, "apps/life-manager/scripts/mobile-app");
    assert.equal(entry.adapter, "exec");
    assert.deepEqual(entry.command, [loopId]);
    const resolved = resolveMobileAppLoop(loopId);
    assert.equal(resolved.productId, expected.product_id);
    assert.equal(path.basename(resolved.runner), expected.runner);
    assert.equal(resolved.action, expected.action);
    const product = products.products.find((item) => item.product_id === expected.product_id);
    assert.ok(product, expected.product_id);
    assert.equal(resolved.origin, product.origin);
    assert.equal(resolved.workspaceRel, `mobile-products/${expected.product_id}`);
    assert.deepEqual(resolved.source, {
      ...product.source,
      git_remote: new URL(product.source.git_remote).toString(),
    });
  }
});

test("every configured mobile publication action is accepted by its real runner", () => {
  for (const loopId of Object.keys(manifest.loops)) {
    const resolved = resolveMobileAppLoop(loopId);
    const runner = require(resolved.runner);
    assert.doesNotThrow(() => runner.parseArgs([resolved.action]), loopId);
  }
});

test("Obou ebook hold cannot be scheduled as a Mobile publisher", () => {
  const obou = "life-manager-anicca-obou-instagram";
  assert.equal(manifest.loops[obou], undefined);
  assert.equal(registry.loops[obou], undefined);
  assert.ok(registry.retired_labels.includes("ai.anicca.life-manager-anicca-obou-instagram"));
});

test("retired per-lane boot wrappers are absent", () => {
  for (const file of fs.readdirSync(path.join(root, "apps/life-manager/scripts"))) {
    assert.ok(!/-production-boot\.sh$/.test(file) || /^(instagram|tiktok)-metrics-production-boot\.sh$/.test(file), file);
  }
});

test("the shared mobile wrapper is host portable and uses the repository timeout", () => {
  const wrapper = fs.readFileSync(path.join(root, "apps/life-manager/scripts/mobile-app"), "utf8");
  assert.match(wrapper, /command -v node/);
  assert.match(wrapper, /command -v python3/);
  assert.match(wrapper, /runtime\/run-with-timeout\.py/);
  assert.match(wrapper, /LIFE_MANAGER_MOBILE_PRODUCT_ORIGIN/);
  assert.match(wrapper, /LIFE_MANAGER_MOBILE_PRODUCT_WORKSPACE_REL/);
  assert.doesNotMatch(wrapper, /\/opt\/homebrew|\/Users\/|openclaw|hermes|profitable-claude/iu);
});

test("unknown loop ids fail closed", () => {
  assert.throws(() => resolveMobileAppLoop("unknown-mobile-loop"), /manifest entry invalid/);
  assert.throws(() => resolveMobileAppLoop("../escape"), /loop id invalid/);
});

test("an unregistered or mismatched product fails before runner execution", (t) => {
  const directory = fs.mkdtempSync(path.join(require("node:os").tmpdir(), "lm-mobile-loop-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const registryFile = path.join(directory, "products.json");
  fs.writeFileSync(registryFile, JSON.stringify({ schema_version: 1, products: [] }));
  assert.throws(
    () => resolveMobileAppLoop("life-manager-honne-ja", undefined, registryFile),
    /product is not registered/,
  );
});
